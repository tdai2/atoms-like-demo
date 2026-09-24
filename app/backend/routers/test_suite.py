"""阶段四接口：测试用例与执行记录。

前缀 `/api/v1/testing`，与生成编排接口（`/api/v1/generation`）区分开：
生成接口负责产出应用，本模块负责产出并执行测试用例。

接口只做数据库读写；唯一的外部调用是「生成用例」时的模型调用与「执行」时的对象存储回读，
两者都在独立短事务之间进行，期间不持有数据库事务。
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_db
from dependencies.auth import get_current_user
from schemas.auth import UserResponse
from services import test_suite
from services.generation import ProjectNotFound
from services.generation_ai import GenerationAIError
from services.generation_artifacts import ArtifactError
from services.test_suite import ArtifactNotReady, CaseNotFound, NoTestCases

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/testing", tags=["testing"])


class CaseView(BaseModel):
    id: int
    project_id: int
    title: str
    case_type: str
    preconditions: str
    steps: str
    expected: str
    assertion: str
    source: str
    case_state: str


class CaseResultView(BaseModel):
    case_id: int
    title: str
    case_type: str
    passed: bool
    detail: str


class RunView(BaseModel):
    id: int
    project_id: int
    status: str
    triggered_by: str
    total: int
    passed: int
    failed: int
    duration_ms: int
    results: List[CaseResultView]
    created_at: Optional[str] = None


class SuiteView(BaseModel):
    project_id: int
    artifact_ready: bool
    cases: List[CaseView]
    latest_run: Optional[RunView] = None
    runs: List[RunView]


class CaseCreateRequest(BaseModel):
    title: str = Field(..., min_length=1, description="用例标题")
    case_type: str = Field("content", description="structure / behavior / content")
    preconditions: str = ""
    steps: str = ""
    expected: str = ""
    assertion: str = Field(..., min_length=1, description="能在产物源码中匹配到的断言片段")


class CaseUpdateRequest(BaseModel):
    title: Optional[str] = None
    case_type: Optional[str] = None
    preconditions: Optional[str] = None
    steps: Optional[str] = None
    expected: Optional[str] = None
    assertion: Optional[str] = None
    case_state: Optional[str] = Field(None, description="active 或 disabled")


def _map_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProjectNotFound):
        return HTTPException(status_code=404, detail="项目不存在或无权访问")
    if isinstance(exc, CaseNotFound):
        return HTTPException(status_code=404, detail="测试记录不存在或无权访问")
    if isinstance(exc, ArtifactNotReady):
        return HTTPException(status_code=409, detail="项目尚未产出可访问的产物，请先完成生成")
    if isinstance(exc, NoTestCases):
        return HTTPException(status_code=400, detail="当前项目没有可执行的测试用例，请先生成或新增用例")
    if isinstance(exc, (GenerationAIError, ArtifactError)):
        return HTTPException(status_code=502, detail=str(exc))
    if isinstance(exc, ValueError):
        return HTTPException(status_code=400, detail=str(exc))
    logger.error("testing api failed: %s", exc, exc_info=True)
    return HTTPException(status_code=500, detail="测试服务暂时不可用，请稍后重试")


async def _run(mutator, *args) -> Any:
    """统一把服务层异常映射为 HTTP 状态码，避免各处重复 try/except。"""
    try:
        return await mutator(*args)
    except Exception as exc:  # noqa: BLE001 - 统一收敛为可读的 HTTP 错误
        raise _map_error(exc) from exc


@router.get("/projects/{project_id}/suite", response_model=SuiteView)
async def get_test_suite(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """测试面板快照：用例列表、最近一次运行与运行历史。"""
    return await _run(test_suite.load_suite, db, str(current_user.id), project_id)


@router.post("/projects/{project_id}/cases/generate", response_model=SuiteView)
async def generate_test_cases(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """按方案与真实产物内容生成一批用例，替换上一批自动用例。"""
    return await _run(test_suite.generate_cases, db, str(current_user.id), project_id)


@router.post("/projects/{project_id}/cases", response_model=CaseView, status_code=201)
async def create_test_case(
    project_id: int,
    data: CaseCreateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """手动新增用例。"""
    return await _run(test_suite.create_case, db, str(current_user.id), project_id, data.model_dump())


@router.put("/cases/{case_id}", response_model=CaseView)
async def update_test_case(
    case_id: int,
    data: CaseUpdateRequest,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """编辑用例内容或启用状态。"""
    return await _run(
        test_suite.update_case, db, str(current_user.id), case_id, data.model_dump(exclude_unset=True)
    )


@router.delete("/cases/{case_id}")
async def delete_test_case(
    case_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """删除用例。"""
    await _run(test_suite.delete_case, db, str(current_user.id), case_id)
    return {"id": case_id, "message": "用例已删除"}


@router.post("/projects/{project_id}/runs", response_model=RunView, status_code=201)
async def execute_test_run(
    project_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """执行全部启用用例，逐条记录真实结果。"""
    return await _run(test_suite.execute_run, db, str(current_user.id), project_id)


@router.get("/runs/{run_id}", response_model=RunView)
async def get_test_run(
    run_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """单次运行的逐用例结果。"""
    return await _run(test_suite.get_run, db, str(current_user.id), run_id)
