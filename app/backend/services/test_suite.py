"""阶段四：测试用例的生成、执行与结果记录。

职责：
- 用例生成：基于项目已落库的方案与对象存储中的真实产物，用模型产出可自动执行的用例。
- 用例管理：手动新增、编辑、删除，并保留来源（自动 / 手动）与启用状态。
- 用例执行：在真实产物内容上做确定性断言，逐条落库通过/失败与原因。
- 运行记录：每次执行落一条 `test_runs`，包含统计与逐用例结果，形成可追溯的历史。

事务边界沿用阶段三的三段式：短事务读取 → 不持有连接的慢调用（模型 / 对象存储）→ 短事务回写。

需要说明的是：断言是否通过由真实产物决定，模型只负责「找出值得验证的点」，
因此执行阶段不调用模型，也不存在「模型判定自己通过」的假成功路径。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.projects import Projects
from models.test_cases import Test_cases
from models.test_runs import Test_runs
from services import generation_ai, generation_artifacts
from services.generation import ProjectNotFound, spec_from_project
from services.generation_artifacts import ArtifactError

logger = logging.getLogger(__name__)

RUN_HISTORY_LIMIT = 10
AUTO_SOURCE = "auto"
MANUAL_SOURCE = "manual"
ACTIVE_STATE = "active"
DISABLED_STATE = "disabled"

_UPDATABLE_FIELDS = ("title", "case_type", "preconditions", "steps", "expected", "assertion", "case_state")


class NoTestCases(Exception):
    """项目下没有可执行的测试用例。"""


class ArtifactNotReady(Exception):
    """项目尚未产出可访问的产物，无法生成或执行用例。"""


class CaseNotFound(Exception):
    """测试用例不存在或不属于当前用户。"""


def _load_json(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


async def _load_project(db: AsyncSession, user_id: str, project_id: int) -> Projects:
    project = await db.scalar(select(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    if project is None:
        raise ProjectNotFound
    return project


async def _load_cases(db: AsyncSession, user_id: str, project_id: int) -> List[Test_cases]:
    return list(
        await db.scalars(
            select(Test_cases)
            .where(Test_cases.project_id == project_id, Test_cases.user_id == user_id)
            .order_by(Test_cases.id)
        )
    )


def _case_view(case: Test_cases) -> Dict[str, Any]:
    return {
        "id": case.id,
        "project_id": case.project_id,
        "title": case.title or "",
        "case_type": case.case_type or "content",
        "preconditions": case.preconditions or "",
        "steps": case.steps or "",
        "expected": case.expected or "",
        "assertion": case.assertion or "",
        "source": case.source or MANUAL_SOURCE,
        "case_state": case.case_state or ACTIVE_STATE,
    }


def _run_view(run: Test_runs) -> Dict[str, Any]:
    results = _load_json(run.results_json, [])
    return {
        "id": run.id,
        "project_id": run.project_id,
        "status": run.status or "failed",
        "triggered_by": run.triggered_by or MANUAL_SOURCE,
        "total": run.total or 0,
        "passed": run.passed or 0,
        "failed": run.failed or 0,
        "duration_ms": run.duration_ms or 0,
        "results": results if isinstance(results, list) else [],
        "created_at": run.created_at.isoformat() if run.created_at else None,
    }


async def load_suite(db: AsyncSession, user_id: str, project_id: int) -> Dict[str, Any]:
    """面板一次读取所需的全部数据：用例、最近一次运行与运行历史。"""
    project = await _load_project(db, user_id, project_id)
    cases = await _load_cases(db, user_id, project_id)
    runs = list(
        await db.scalars(
            select(Test_runs)
            .where(Test_runs.project_id == project_id, Test_runs.user_id == user_id)
            .order_by(Test_runs.id.desc())
            .limit(RUN_HISTORY_LIMIT)
        )
    )
    return {
        "project_id": project.id,
        "artifact_ready": bool(project.artifact_key),
        "cases": [_case_view(case) for case in cases],
        "latest_run": _run_view(runs[0]) if runs else None,
        "runs": [_run_view(run) for run in runs],
    }


async def generate_cases(db: AsyncSession, user_id: str, project_id: int) -> Dict[str, Any]:
    """按方案与真实产物内容生成测试用例，整体替换上一批自动用例（手动用例保留）。"""
    project = await _load_project(db, user_id, project_id)
    artifact_key = project.artifact_key or ""
    if not artifact_key:
        raise ArtifactNotReady
    spec = spec_from_project(project)
    plan = _load_json(project.plan_json, {"files": [], "component_tree": [], "notes": ""})
    # 读取阶段结束：后面的模型与对象存储调用不再持有数据库事务。
    await db.commit()

    html = await generation_artifacts.fetch_html(artifact_key)
    if not html:
        raise ArtifactError("无法从对象存储回读产物，暂时无法生成测试用例")
    cases = await generation_ai.write_test_cases(spec, plan, html)

    await db.execute(
        sql_delete(Test_cases).where(
            Test_cases.project_id == project_id,
            Test_cases.user_id == user_id,
            Test_cases.source == AUTO_SOURCE,
        )
    )
    for item in cases:
        db.add(
            Test_cases(
                user_id=user_id,
                project_id=project_id,
                title=item["title"],
                case_type=item["case_type"],
                preconditions=item["preconditions"],
                steps=item["steps"],
                expected=item["expected"],
                assertion=item["assertion"],
                source=AUTO_SOURCE,
                case_state=ACTIVE_STATE,
            )
        )
    await db.commit()
    logger.info("project %s generated %s test cases", project_id, len(cases))
    return await load_suite(db, user_id, project_id)


def _normalize_case_payload(data: Dict[str, Any]) -> Dict[str, str]:
    title = str(data.get("title") or "").strip()
    assertion = str(data.get("assertion") or "").strip().strip('"').strip("'").strip().lower()
    if not title:
        raise ValueError("请填写用例标题")
    if not assertion:
        raise ValueError("请填写断言片段：它必须是能在产物源码中匹配到的内容")
    case_type = str(data.get("case_type") or "content").strip().lower()
    if case_type not in generation_ai.CASE_TYPES:
        case_type = "content"
    preconditions = str(data.get("preconditions") or "").strip() or "已发布可访问的产物"
    return {
        "title": title[:120],
        "case_type": case_type,
        "preconditions": preconditions[:300],
        "steps": str(data.get("steps") or "").strip()[:600],
        "expected": str(data.get("expected") or "").strip()[:300],
        "assertion": assertion[:200],
    }


async def create_case(db: AsyncSession, user_id: str, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """手动新增用例，来源固定为手动，便于与自动用例区分。"""
    await _load_project(db, user_id, project_id)
    fields = _normalize_case_payload(data)
    case = Test_cases(
        user_id=user_id,
        project_id=project_id,
        source=MANUAL_SOURCE,
        case_state=ACTIVE_STATE,
        **fields,
    )
    db.add(case)
    await db.commit()
    return _case_view(case)


async def update_case(db: AsyncSession, user_id: str, case_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """编辑用例；未提交的字段保持原值。"""
    case = await db.scalar(select(Test_cases).where(Test_cases.id == case_id, Test_cases.user_id == user_id))
    if case is None:
        raise CaseNotFound

    merged = {field: getattr(case, field) for field in _UPDATABLE_FIELDS}
    merged.update({key: value for key, value in data.items() if key in _UPDATABLE_FIELDS and value is not None})
    if "assertion" in data and data.get("assertion") is not None:
        normalized = _normalize_case_payload({"title": merged.get("title"), "assertion": data.get("assertion"),
                                             "case_type": merged.get("case_type"),
                                             "preconditions": merged.get("preconditions"),
                                             "steps": merged.get("steps"),
                                             "expected": merged.get("expected")})
        merged.update(normalized)

    case_state = str(merged.get("case_state") or ACTIVE_STATE).strip().lower()
    case.case_state = DISABLED_STATE if case_state == DISABLED_STATE else ACTIVE_STATE
    for field in ("title", "case_type", "preconditions", "steps", "expected", "assertion"):
        if merged.get(field) is not None:
            setattr(case, field, str(merged[field]))
    await db.commit()
    return _case_view(case)


async def delete_case(db: AsyncSession, user_id: str, case_id: int) -> None:
    case = await db.scalar(select(Test_cases).where(Test_cases.id == case_id, Test_cases.user_id == user_id))
    if case is None:
        raise CaseNotFound
    await db.delete(case)
    await db.commit()


async def execute_run(
    db: AsyncSession, user_id: str, project_id: int, triggered_by: str = MANUAL_SOURCE
) -> Dict[str, Any]:
    """在真实产物内容上执行全部启用用例，逐条记录结果并落一条运行记录。"""
    project = await _load_project(db, user_id, project_id)
    artifact_key = project.artifact_key or ""
    if not artifact_key:
        raise ArtifactNotReady
    cases = [
        case
        for case in await _load_cases(db, user_id, project_id)
        if (case.case_state or ACTIVE_STATE) != DISABLED_STATE
    ]
    if not cases:
        raise NoTestCases
    # 复制执行所需的只读输入，随后释放事务再做对象存储回读。
    snapshot = [
        {
            "case_id": case.id,
            "title": case.title or "",
            "case_type": case.case_type or "content",
            "assertion": (case.assertion or "").strip().lower(),
        }
        for case in cases
    ]
    await db.commit()

    started = time.perf_counter()
    html = await generation_artifacts.fetch_html(artifact_key)
    if not html:
        raise ArtifactError("无法从对象存储回读产物，测试执行中止")
    lowered = html.lower()

    results: List[Dict[str, Any]] = []
    passed = 0
    for item in snapshot:
        ok = bool(item["assertion"]) and item["assertion"] in lowered
        if ok:
            passed += 1
        results.append(
            {
                "case_id": item["case_id"],
                "title": item["title"],
                "case_type": item["case_type"],
                "passed": ok,
                "detail": "在产物源码中匹配到断言片段"
                if ok
                else f"未在产物源码中找到 `{item['assertion']}`",
            }
        )
    total = len(results)
    run = Test_runs(
        user_id=user_id,
        project_id=project_id,
        status="passed" if passed == total else "failed",
        triggered_by=triggered_by,
        total=total,
        passed=passed,
        failed=total - passed,
        duration_ms=int((time.perf_counter() - started) * 1000),
        results_json=json.dumps(results, ensure_ascii=False),
        error_message="",
    )
    db.add(run)
    await db.commit()
    logger.info("project %s test run %s: %s/%s passed", project_id, run.id, passed, total)
    return _run_view(run)


async def get_run(db: AsyncSession, user_id: str, run_id: int) -> Dict[str, Any]:
    run = await db.scalar(select(Test_runs).where(Test_runs.id == run_id, Test_runs.user_id == user_id))
    if run is None:
        raise CaseNotFound
    return _run_view(run)


async def purge_project_tests(db: AsyncSession, user_id: str, project_id: int) -> None:
    """随项目删除一并清理用例与运行记录，避免留下无主的测试数据。"""
    await db.execute(
        sql_delete(Test_cases).where(Test_cases.project_id == project_id, Test_cases.user_id == user_id)
    )
    await db.execute(sql_delete(Test_runs).where(Test_runs.project_id == project_id, Test_runs.user_id == user_id))
