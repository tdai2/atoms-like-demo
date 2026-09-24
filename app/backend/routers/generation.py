"""生成编排接口。

前缀 `/api/v1/generation`，与自动生成的实体 CRUD 路由（`/api/v1/entities/*`）区分开，
由本模块承担「创建任务 + 逐阶段执行 + 配额校验」的编排语义。

前端统一通过 web-sdk `client.apiCall.invoke` 调用；所有接口都只做数据库读写与预览地址解析，
阶段执行交给后台工作器（`services.pipeline_runner`），因此轮询不会被模型调用拖到网关超时。
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_manager, get_db
from dependencies.auth import get_current_user
from models.build_tasks import Build_tasks
from models.project_versions import Project_versions
from models.projects import Projects
from schemas.auth import UserResponse
from services import generation, pipeline_runner, test_suite
from services.generation import (
    ProjectNotFound,
    QuotaExceeded,
    count_projects,
    create_project,
    get_or_create_quota,
    retry_project,
    spec_from_project,
    sync_pipeline,
    template_spec,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/generation", tags=["generation"])


class CreateProjectRequest(BaseModel):
    prompt: str = Field(..., min_length=1, description="用户提交的自然语言需求")
    template_key: str = Field("", description="作为起点的模板标识，可省略")


class StageView(BaseModel):
    stage: str
    stage_name: str
    stage_order: int
    stage_state: str
    stage_log: str
    error_message: str
    output_summary: str


class ProjectView(BaseModel):
    id: int
    name: str
    prompt: str
    status: str
    current_stage: str
    template_key: str
    preview_url: str
    latest_version: int
    artifact_key: str
    created_at: Optional[str] = None


class SpecView(BaseModel):
    app_name: str
    display_name: str
    pages: List[str]
    entities: List[str]
    stack: List[str]
    files: int
    component_tree: List[str]
    notes: str
    entry: str


class QuotaView(BaseModel):
    plan: str
    used: int
    limit: int
    period: str


class MetricView(BaseModel):
    id: str
    label: str
    value: str
    passed: bool


class PipelineResponse(BaseModel):
    run_no: int
    spec: SpecView
    stages: List[StageView]
    test_report: List[MetricView]
    quota: QuotaView
    project: ProjectView


class ProjectListResponse(BaseModel):
    quotas: QuotaView
    items: List[ProjectView]
    total: int


class VersionView(BaseModel):
    version: int
    diff_summary: str
    files_key: str
    created_at: Optional[str] = None


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _project_view(project: Projects, preview_url: str = "") -> ProjectView:
    """项目视图；`preview_url` 由调用方按对象键即时解析后传入，不从库里读签名链接。"""
    return ProjectView(
        id=project.id,
        name=project.name,
        prompt=project.prompt,
        status=project.status or "queued",
        current_stage=project.current_stage or "",
        template_key=project.template_key or "",
        preview_url=preview_url,
        latest_version=project.latest_version or 1,
        artifact_key=project.artifact_key or "",
        created_at=_iso(project.created_at),
    )


def _quota_view(quota) -> QuotaView:
    return QuotaView(
        plan=quota.plan or generation.FREE_PLAN,
        used=quota.used or 0,
        limit=quota.quota_limit or generation.FREE_QUOTA,
        period=quota.period,
    )


def _spec_view(spec: Dict[str, Any]) -> SpecView:
    return SpecView(
        app_name=spec.get("app_name") or "app",
        display_name=spec.get("display_name") or "未命名应用",
        pages=list(spec.get("pages") or []),
        entities=list(spec.get("entities") or []),
        stack=list(spec.get("stack") or []),
        files=int(spec.get("files") or 0),
        component_tree=list(spec.get("component_tree") or []),
        notes=spec.get("notes") or "",
        entry=spec.get("entry") or "index.html",
    )


def _pipeline_response(snapshot: Dict[str, Any], quota) -> PipelineResponse:
    return PipelineResponse(
        run_no=snapshot["run_no"],
        spec=_spec_view(snapshot["spec"]),
        stages=[
            StageView(
                stage=t.stage,
                stage_name=t.stage_name or t.stage,
                stage_order=t.stage_order or 0,
                stage_state=t.stage_state,
                stage_log=t.stage_log or "",
                error_message=t.error_message or "",
                output_summary=t.output_summary or "",
            )
            for t in snapshot["tasks"]
        ],
        test_report=snapshot["test_report"],
        quota=_quota_view(quota),
        project=_project_view(snapshot["project"], snapshot.get("preview_url") or ""),
    )


async def _snapshot_with_quota(user_id: str, project_id: int) -> PipelineResponse:
    """用独立短会话读取最新快照与额度。

    请求会话在等待后台工作器期间必须归还数据库连接，否则后台阶段与多端并发轮询会互相
    争抢连接池，表现为 `QueuePool limit ... timed out` 引起的 5xx（经网关放大为 502）。
    因此快照统一在这里用短会话重新读取，保证返回的是最新状态。
    """
    try:
        async with db_manager.session() as reader:
            snapshot = await sync_pipeline(reader, user_id, project_id)
            quota = await get_or_create_quota(reader, user_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    return _pipeline_response(snapshot, quota)


async def _load_project(db: AsyncSession, user_id: str, project_id: int) -> Projects:
    project = await db.scalar(select(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    return project


@router.post("/projects", response_model=PipelineResponse, status_code=201)
async def create_generation_project(
    data: CreateProjectRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """创建生成任务：落库项目与六阶段任务并占用一次额度。

    本接口不执行模型调用，返回的是待执行快照（首个阶段为 pending），
    六个阶段由后台工作器逐个推进，避免创建请求被上游模型拖到网关超时。
    """
    prompt = (data.prompt or "").strip()
    if not prompt:
        raise HTTPException(status_code=400, detail="请先描述你想要的应用")
    try:
        project, _quota = await create_project(db, str(current_user.id), prompt, data.template_key or "")
    except QuotaExceeded as exc:
        raise HTTPException(
            status_code=429,
            detail=f"本周期生成额度已用尽（{exc.used}/{exc.limit}），升级套餐后可继续生成",
        )
    except Exception as exc:  # noqa: BLE001 - 落库失败时给出可重试的错误
        logger.error("create project failed: %s", exc)
        raise HTTPException(status_code=500, detail="生成任务创建失败，请稍后重试")
    user_id = str(current_user.id)
    # 创建已完成落库，这里用独立短会话读取最新快照：额度可能已被后台退款逻辑改写。
    return await _snapshot_with_quota(user_id, project.id)


@router.get("/projects", response_model=ProjectListResponse)
async def list_generation_projects(
    limit: int = Query(20, ge=1, le=100),
    skip: int = Query(0, ge=0),
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """当前账号的项目列表，按创建时间倒序。"""
    user_id = str(current_user.id)
    quota = await get_or_create_quota(db, user_id)
    total = await count_projects(db, user_id)
    rows = list(
        await db.scalars(
            select(Projects)
            .where(Projects.user_id == user_id)
            .order_by(Projects.created_at.desc(), Projects.id.desc())
            .offset(skip)
            .limit(limit)
        )
    )
    return ProjectListResponse(quotas=_quota_view(quota), items=[_project_view(p) for p in rows], total=total)


@router.get("/projects/{project_id}", response_model=PipelineResponse)
async def get_generation_project(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """读取项目流水线快照；项目未完成时确保后台工作器在推进。"""
    user_id = str(current_user.id)
    try:
        async with db_manager.session() as reader:
            snapshot = await sync_pipeline(reader, user_id, project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    if (snapshot["project"].status or "") not in generation.TERMINAL_STATUSES:
        # 先释放请求连接，再等待工作器起步；工作器阶段执行期间会独立占用连接，
        # 若此处继续持有连接，并发轮询就会把连接池耗尽并放大为网关 502。
        await pipeline_runner.kick(user_id, project_id)
    return await _snapshot_with_quota(user_id, project_id)


@router.post("/projects/{project_id}/retry", response_model=PipelineResponse)
async def retry_generation_project(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """失败后重跑流水线（携带上一轮报错修复），不重复消耗配额。"""
    user_id = str(current_user.id)
    try:
        await retry_project(db, user_id, project_id)
    except ProjectNotFound:
        raise HTTPException(status_code=404, detail="项目不存在或无权访问")
    # 重试已落库并释放连接，随后调度工作器并用短会话读取最新快照。
    await pipeline_runner.kick(user_id, project_id)
    return await _snapshot_with_quota(user_id, project_id)


@router.get("/projects/{project_id}/versions", response_model=List[VersionView])
async def list_project_versions(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """项目版本链，按版本号倒序。"""
    user_id = str(current_user.id)
    await _load_project(db, user_id, project_id)
    rows = list(
        await db.scalars(
            select(Project_versions)
            .where(Project_versions.project_id == project_id, Project_versions.user_id == user_id)
            .order_by(Project_versions.version.desc())
        )
    )
    return [
        VersionView(
            version=v.version,
            diff_summary=v.diff_summary or "",
            files_key=v.files_key or "",
            created_at=_iso(v.created_at),
        )
        for v in rows
    ]


@router.delete("/projects/{project_id}")
async def delete_generation_project(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除项目，同时清理其任务、版本与测试用例/执行记录。"""
    user_id = str(current_user.id)
    await _load_project(db, user_id, project_id)
    await db.execute(
        sql_delete(Build_tasks).where(Build_tasks.project_id == project_id, Build_tasks.user_id == user_id)
    )
    await db.execute(
        sql_delete(Project_versions).where(
            Project_versions.project_id == project_id, Project_versions.user_id == user_id
        )
    )
    await test_suite.purge_project_tests(db, user_id, project_id)
    await db.execute(sql_delete(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    await db.commit()
    return {"id": project_id, "message": "项目已删除"}


@router.get("/templates/{template_key}", response_model=SpecView)
async def get_template_spec(template_key: str):
    """按模板标识返回推荐方案，供模板详情页展示（不调用模型）。"""
    return _spec_view(template_spec(template_key))
