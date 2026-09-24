"""阶段五接口：Bug 提交、记录与自动修复。

前缀 `/api/v1/bugs`，与阶段四的 `/api/v1/testing` 分工明确：
测试模块负责「发现」问题并留下断言证据，本模块负责「记录并尝试修复」问题。

自动修复会调用模型改写产物并上传新版本，因此该接口给足超时；
其余接口只做数据库读写。
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services import bug_fix
from services.bug_fix import ArtifactNotReady, BugBusy, BugNotFound
from services.generation import ProjectNotFound
from services.generation_ai import GenerationAIError
from services.generation_artifacts import ArtifactError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/bugs", tags=["bugs"])


class FixView(BaseModel):
    id: int
    bug_id: int
    status: str
    attempt_no: int
    model: str
    source_version: int
    target_version: int
    artifact_key: str
    diff_summary: str
    changes: List[str]
    retest: Optional[Dict[str, Any]] = None
    error_message: str
    duration_ms: int
    created_at: Optional[str] = None


class BugView(BaseModel):
    id: int
    project_id: int
    title: str
    description: str
    severity: str
    reproduction: str
    related_case_id: Optional[int] = None
    status: str
    fix_attempts: int
    latest_fix_id: Optional[int] = None
    resolution: str
    target_version: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    latest_fix: Optional[FixView] = None


class BugStats(BaseModel):
    total: int
    open: int
    fixing: int
    fixed: int
    fix_failed: int
    closed: int


class BugPanelView(BaseModel):
    project_id: int
    artifact_ready: bool
    latest_version: int
    stats: BugStats
    bugs: List[BugView]
    fixes: List[FixView]


class BugCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="缺陷标题")
    description: str = Field("", description="缺陷表现")
    severity: str = Field("medium", description="low / medium / high / critical")
    reproduction: str = Field("", description="复现步骤")
    related_case_id: Optional[int] = Field(None, description="关联的测试用例编号，可省略")


class BugUpdateRequest(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    severity: Optional[str] = None
    reproduction: Optional[str] = None
    related_case_id: Optional[int] = None
    status: Optional[str] = Field(None, description="open / fixed / closed")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFound):
        return HTTPException(status_code=404, detail="项目不存在或无权访问")
    if isinstance(exc, BugNotFound):
        return HTTPException(status_code=404, detail="缺陷不存在或无权访问")
    if isinstance(exc, ArtifactNotReady):
        return HTTPException(status_code=409, detail="项目尚未产出可访问的产物，请先完成生成")
    if isinstance(exc, BugBusy):
        return HTTPException(status_code=409, detail="该缺陷正在修复中，请等待当前修复结束后再试")
    if isinstance(exc, (GenerationAIError, ArtifactError)):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    logger.error("bug api failed: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="缺陷服务暂时不可用，请稍后重试")


async def _run(mutator, *args) -> Any:
    """统一把服务层异常映射为 HTTP 状态码，避免各处重复 try/except。"""
    try:
        return await mutator(*args)
    except Exception as exc:  # noqa: BLE001 - 统一收敛为可读的 HTTP 错误
        raise _map_error(exc) from exc


@router.get("/projects/{project_id}", response_model=BugPanelView)
async def get_bug_panel(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """缺陷面板快照：缺陷列表、状态统计与最近修复记录。"""
    return await _run(bug_fix.load_panel, db, str(current_user.id), project_id)


@router.post("/projects/{project_id}", response_model=BugView, status_code=201)
async def create_bug(
    project_id: int,
    data: BugCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """提交一条缺陷记录。"""
    return await _run(bug_fix.create_bug, db, str(current_user.id), project_id, data.model_dump())


@router.put("/{bug_id}", response_model=BugView)
async def update_bug(
    bug_id: int,
    data: BugUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑缺陷内容，或手动关闭 / 重新打开。"""
    return await _run(
        bug_fix.update_bug, db, str(current_user.id), bug_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/{bug_id}")
async def delete_bug(
    bug_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除缺陷及其修复记录。"""
    await _run(bug_fix.delete_bug, db, str(current_user.id), bug_id)
    return {"id": bug_id, "message": "缺陷已删除"}


@router.post("/{bug_id}/fix", response_model=BugView)
async def fix_bug(
    bug_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """触发自动修复：改写产物为新版本，并在新产物上复测。"""
    return await _run(bug_fix.fix_bug, db, str(current_user.id), bug_id)


@router.get("/{bug_id}/fixes", response_model=List[FixView])
async def list_bug_fixes(
    bug_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单条缺陷的修复历史，最新在前。"""
    return await _run(bug_fix.load_fixes, db, str(current_user.id), bug_id)
