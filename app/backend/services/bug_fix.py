"""阶段五：Bug 提交、记录与自动修复闭环。

职责：
- 记录：用户提交的缺陷按项目归属落库，包含严重级别、复现步骤与可选关联用例。
- 自动修复：把项目当前真实产物与缺陷描述一起交给模型，产出一份完整可运行的新源码，
  作为新版本上传对象存储，并把项目指针前移到新版本（旧版本对象保留，可追溯）。
- 复测：修复后立刻在**新产物**上重跑启用用例，用确定性断言判断缺陷是否真的消失；
  通过与否由产物决定，不由模型自述。
- 历史：每次修复落一条 `bug_fix_logs`，记录模型、源/目标版本、变更清单、复测结果与耗时。

事务边界沿用阶段三与阶段四：短事务读取 → 不持有连接的慢调用（模型 / 对象存储）→ 短事务回写。
模型调用失败会如实落成一条失败修复记录，并让缺陷停在可见失败态，不伪造修复成功。
"""

import json
import logging
import time
from typing import Any, Dict, List, Optional

from sqlalchemy import delete as sql_delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.bug_fix_logs import Bug_fix_logs
from models.bugs import Bugs
from models.project_versions import Project_versions
from models.projects import Projects
from models.test_cases import Test_cases
from services import generation_ai, generation_artifacts, test_suite
from services.generation import ProjectNotFound, spec_from_project
from services.generation_ai import GenerationAIError
from services.generation_artifacts import ArtifactError
from services.test_suite import NoTestCases

logger = logging.getLogger(__name__)

FIX_HISTORY_LIMIT = 20

SEVERITIES = ("low", "medium", "high", "critical")
DEFAULT_SEVERITY = "medium"

STATUS_OPEN = "open"
STATUS_FIXING = "fixing"
STATUS_FIXED = "fixed"
STATUS_FAILED = "fix_failed"
STATUS_CLOSED = "closed"
# 用户可手动设置的缺陷状态；fixing / fix_failed 由自动修复流程写入。
MANUAL_STATUSES = (STATUS_OPEN, STATUS_FIXED, STATUS_CLOSED)


class BugNotFound(Exception):
    """缺陷不存在或不属于当前用户。"""


class ArtifactNotReady(Exception):
    """项目尚未产出可访问的产物，无法提交缺陷或执行修复。"""


class BugBusy(Exception):
    """该缺陷正在修复中，不能并发触发第二次修复。"""


def _iso(value: Any) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _load_json(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    if fallback is None:
        return value
    return value if isinstance(value, type(fallback)) else fallback


async def _load_project(db: AsyncSession, user_id: str, project_id: int) -> Projects:
    project = await db.scalar(select(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    if project is None:
        raise ProjectNotFound
    return project


def _fix_view(log: Bug_fix_logs) -> Dict[str, Any]:
    changes = _load_json(log.changes_json, [])
    return {
        "id": log.id,
        "bug_id": log.bug_id,
        "status": log.status or STATUS_FAILED,
        "attempt_no": log.attempt_no or 0,
        "model": log.model or "",
        "source_version": log.source_version or 0,
        "target_version": log.target_version or 0,
        "artifact_key": log.artifact_key or "",
        "diff_summary": log.diff_summary or "",
        "changes": changes if isinstance(changes, list) else [],
        "retest": _load_json(log.retest_json, None),
        "error_message": log.error_message or "",
        "duration_ms": log.duration_ms or 0,
        "created_at": _iso(log.created_at),
    }


def _bug_view(bug: Bugs, latest: Optional[Bug_fix_logs] = None) -> Dict[str, Any]:
    return {
        "id": bug.id,
        "project_id": bug.project_id,
        "title": bug.title or "",
        "description": bug.description or "",
        "severity": bug.severity or DEFAULT_SEVERITY,
        "reproduction": bug.reproduction or "",
        "related_case_id": bug.related_case_id,
        "status": bug.status or STATUS_OPEN,
        "fix_attempts": bug.fix_attempts or 0,
        "latest_fix_id": bug.latest_fix_id,
        "resolution": bug.resolution or "",
        "target_version": bug.target_version,
        "created_at": _iso(bug.created_at),
        "updated_at": _iso(bug.updated_at),
        "latest_fix": _fix_view(latest) if latest is not None else None,
    }


def _stats(bugs: List[Bugs]) -> Dict[str, int]:
    counter = {STATUS_OPEN: 0, STATUS_FIXING: 0, STATUS_FIXED: 0, STATUS_FAILED: 0, STATUS_CLOSED: 0}
    for bug in bugs:
        key = bug.status or STATUS_OPEN
        counter[key if key in counter else STATUS_OPEN] += 1
    return {"total": len(bugs), **counter}


async def load_panel(db: AsyncSession, user_id: str, project_id: int) -> Dict[str, Any]:
    """缺陷面板快照：缺陷列表（含最近一次修复）、修复历史与状态统计。"""
    project = await _load_project(db, user_id, project_id)
    bugs = list(
        await db.scalars(
            select(Bugs).where(Bugs.project_id == project_id, Bugs.user_id == user_id).order_by(Bugs.id.desc())
        )
    )
    logs = list(
        await db.scalars(
            select(Bug_fix_logs)
            .where(Bug_fix_logs.project_id == project_id, Bug_fix_logs.user_id == user_id)
            .order_by(Bug_fix_logs.id.desc())
            .limit(FIX_HISTORY_LIMIT)
        )
    )
    latest_by_bug: Dict[int, Bug_fix_logs] = {}
    for log in logs:
        latest_by_bug.setdefault(log.bug_id, log)
    return {
        "project_id": project.id,
        "artifact_ready": bool(project.artifact_key),
        "latest_version": project.latest_version or 1,
        "stats": _stats(bugs),
        "bugs": [_bug_view(bug, latest_by_bug.get(bug.id)) for bug in bugs],
        "fixes": [_fix_view(log) for log in logs],
    }


def _normalize_severity(value: Any) -> str:
    severity = str(value or "").strip().lower()
    return severity if severity in SEVERITIES else DEFAULT_SEVERITY


async def _load_related_case(
    db: AsyncSession, user_id: str, project_id: int, case_id: Optional[int]
) -> Optional[Test_cases]:
    if not case_id:
        return None
    case = await db.scalar(
        select(Test_cases).where(
            Test_cases.id == case_id,
            Test_cases.user_id == user_id,
            Test_cases.project_id == project_id,
        )
    )
    if case is None:
        raise ValueError("关联的测试用例不存在或不属于该项目")
    return case


async def create_bug(db: AsyncSession, user_id: str, project_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """提交缺陷：按项目归属落库，初始状态为待修复。"""
    project = await _load_project(db, user_id, project_id)
    if not project.artifact_key:
        raise ArtifactNotReady
    title = str(data.get("title") or "").strip()
    if not title:
        raise ValueError("请填写缺陷标题")
    case = await _load_related_case(db, user_id, project_id, data.get("related_case_id"))
    bug = Bugs(
        user_id=user_id,
        project_id=project_id,
        title=title[:120],
        description=str(data.get("description") or "").strip()[:2000],
        severity=_normalize_severity(data.get("severity")),
        reproduction=str(data.get("reproduction") or "").strip()[:1200],
        related_case_id=case.id if case is not None else None,
        status=STATUS_OPEN,
        fix_attempts=0,
        resolution="",
        target_version=project.latest_version or 1,
    )
    db.add(bug)
    await db.commit()
    logger.info("project %s bug %s created", project_id, bug.id)
    return _bug_view(bug)


async def update_bug(db: AsyncSession, user_id: str, bug_id: int, data: Dict[str, Any]) -> Dict[str, Any]:
    """编辑缺陷内容，或手动关闭 / 重新打开；`fixing` 状态不允许被手动覆盖。"""
    bug = await db.scalar(select(Bugs).where(Bugs.id == bug_id, Bugs.user_id == user_id))
    if bug is None:
        raise BugNotFound

    if data.get("title") is not None:
        title = str(data["title"]).strip()
        if not title:
            raise ValueError("请填写缺陷标题")
        bug.title = title[:120]
    if data.get("description") is not None:
        bug.description = str(data["description"]).strip()[:2000]
    if data.get("reproduction") is not None:
        bug.reproduction = str(data["reproduction"]).strip()[:1200]
    if data.get("severity") is not None:
        bug.severity = _normalize_severity(data.get("severity"))
    if data.get("related_case_id") is not None:
        case = await _load_related_case(db, user_id, bug.project_id, data.get("related_case_id"))
        bug.related_case_id = case.id if case is not None else None
    if data.get("status") is not None:
        status = str(data["status"]).strip().lower()
        if status not in MANUAL_STATUSES:
            raise ValueError("缺陷状态只能是待修复、已修复或已关闭")
        if (bug.status or STATUS_OPEN) == STATUS_FIXING:
            raise BugBusy
        bug.status = status
    await db.commit()
    return _bug_view(bug)


async def delete_bug(db: AsyncSession, user_id: str, bug_id: int) -> None:
    bug = await db.scalar(select(Bugs).where(Bugs.id == bug_id, Bugs.user_id == user_id))
    if bug is None:
        raise BugNotFound
    await db.execute(sql_delete(Bug_fix_logs).where(Bug_fix_logs.bug_id == bug_id, Bug_fix_logs.user_id == user_id))
    await db.delete(bug)
    await db.commit()


async def _retest(db: AsyncSession, user_id: str, project_id: int, related_case_id: Optional[int]) -> Dict[str, Any]:
    """在修复后的新产物上重跑启用用例，用确定性断言判断缺陷是否真的消失。"""
    try:
        run = await test_suite.execute_run(db, user_id, project_id, triggered_by="fix")
    except NoTestCases:
        return {
            "ok": True,
            "resolution": "修复已应用；当前项目没有启用用例，因此未执行复测",
            "payload": {"executed": False, "reason": "no_cases"},
        }
    except Exception as exc:  # noqa: BLE001 - 复测异常不能吞掉已应用的修复，如实记录
        logger.warning("project %s retest after fix failed: %s", project_id, exc)
        return {
            "ok": False,
            "resolution": f"修复已应用，但复测未能完成：{exc}",
            "payload": {"executed": False, "reason": str(exc)[:300]},
        }

    related = next((item for item in run["results"] if item["case_id"] == related_case_id), None)
    ok = run["failed"] == 0 and (related is None or related["passed"])
    if ok:
        resolution = f"修复已应用，新版本复测 {run['passed']}/{run['total']} 条用例全部通过"
    elif related is not None and not related["passed"]:
        resolution = f"修复已应用，但关联用例复测仍未通过：{related['detail']}"
    else:
        resolution = f"修复已应用，但复测仍有 {run['failed']} 条用例失败"
    return {
        "ok": ok,
        "resolution": resolution,
        "payload": {
            "executed": True,
            "run_id": run["id"],
            "status": run["status"],
            "total": run["total"],
            "passed": run["passed"],
            "failed": run["failed"],
            "duration_ms": run["duration_ms"],
            "related_case_id": related_case_id,
            "related_case": related,
            "results": run["results"],
        },
    }


async def fix_bug(db: AsyncSession, user_id: str, bug_id: int, repair_hint: str = "") -> Dict[str, Any]:
    """按缺陷报告自动修复产物，并在修复后的新产物上复测。

    流程：短事务记录「修复中」→ 回读产物与模型改写（不持有事务）→ 新版本上传与校验
    → 短事务落版本、前移项目指针与修复记录 → 复测 → 短事务回写复测结果与缺陷结论。
    """
    bug = await db.scalar(select(Bugs).where(Bugs.id == bug_id, Bugs.user_id == user_id))
    if bug is None:
        raise BugNotFound
    project = await _load_project(db, user_id, bug.project_id)
    source_key = project.artifact_key or ""
    if not source_key:
        raise ArtifactNotReady
    if (bug.status or STATUS_OPEN) == STATUS_FIXING:
        raise BugBusy

    source_version = project.latest_version or 1
    target_version = source_version + 1
    attempt_no = (bug.fix_attempts or 0) + 1
    related_case = await db.scalar(
        select(Test_cases).where(
            Test_cases.id == bug.related_case_id,
            Test_cases.user_id == user_id,
            Test_cases.project_id == project.id,
        )
    ) if bug.related_case_id else None
    snapshot = {
        "project_id": project.id,
        "prompt": project.prompt or "",
        "spec": spec_from_project(project),
        "title": bug.title or "",
        "description": bug.description or "",
        "reproduction": bug.reproduction or "",
        "related_assertion": (related_case.assertion or "") if related_case is not None else "",
        "related_case_id": bug.related_case_id,
    }
    # 读取结束：先落「修复中」再释放事务，避免用户在修复期间重复提交。
    bug.status = STATUS_FIXING
    bug.fix_attempts = attempt_no
    await db.commit()

    started = time.perf_counter()
    try:
        html = await generation_artifacts.fetch_html(source_key)
        if not html:
            raise ArtifactError("无法从对象存储回读当前产物，自动修复中止")
        result = await generation_ai.fix_application(
            snapshot["prompt"],
            snapshot["spec"],
            html,
            snapshot["title"],
            snapshot["description"],
            snapshot["reproduction"],
            snapshot["related_assertion"],
            repair_hint,
        )
        new_key = generation_artifacts.artifact_key(snapshot["project_id"], target_version)
        await generation_artifacts.upload_html(new_key, result["content"])
        reachable = await generation_artifacts.is_reachable(await generation_artifacts.public_url(new_key))
        if not reachable:
            raise ArtifactError("修复后的产物地址不可访问，已放弃本次修复")
    except (GenerationAIError, ArtifactError) as exc:
        logger.warning("project %s bug %s fix attempt %s failed: %s", bug.project_id, bug.id, attempt_no, exc)
        log = Bug_fix_logs(
            user_id=user_id,
            project_id=bug.project_id,
            bug_id=bug.id,
            status=STATUS_FAILED,
            attempt_no=attempt_no,
            model=generation_ai.FIX_MODEL,
            source_version=source_version,
            target_version=target_version,
            artifact_key="",
            changes_json="[]",
            diff_summary="本次修复未产出可用产物",
            retest_json="",
            error_message=str(exc)[:900],
            duration_ms=int((time.perf_counter() - started) * 1000),
        )
        db.add(log)
        await db.commit()
        bug.status = STATUS_FAILED
        bug.latest_fix_id = log.id
        bug.resolution = f"第 {attempt_no} 次自动修复失败：{exc}"
        await db.commit()
        return _bug_view(bug, log)

    # 修复已产出可用产物：落版本、前移项目指针，并记录本次修复。
    diff_summary = result["summary"] or "已按缺陷描述修复产物"
    db.add(
        Project_versions(
            user_id=user_id,
            project_id=bug.project_id,
            version=target_version,
            diff_summary=f"缺陷修复：{diff_summary}",
            files_key=new_key,
        )
    )
    project.artifact_key = new_key
    project.latest_version = target_version
    project.status = "succeeded"
    log = Bug_fix_logs(
        user_id=user_id,
        project_id=bug.project_id,
        bug_id=bug.id,
        status=STATUS_FIXED,
        attempt_no=attempt_no,
        model=generation_ai.FIX_MODEL,
        source_version=source_version,
        target_version=target_version,
        artifact_key=new_key,
        changes_json=json.dumps(result["changes"], ensure_ascii=False),
        diff_summary=diff_summary,
        retest_json="",
        error_message="",
        duration_ms=0,
    )
    db.add(log)
    await db.commit()

    retest = await _retest(db, user_id, bug.project_id, snapshot["related_case_id"])
    log.status = STATUS_FIXED if retest["ok"] else STATUS_FAILED
    log.retest_json = json.dumps(retest["payload"], ensure_ascii=False)
    log.duration_ms = int((time.perf_counter() - started) * 1000)
    bug.status = STATUS_FIXED if retest["ok"] else STATUS_FAILED
    bug.latest_fix_id = log.id
    bug.target_version = target_version
    bug.resolution = retest["resolution"]
    await db.commit()
    logger.info(
        "project %s bug %s fixed as v%s, retest %s",
        bug.project_id,
        bug.id,
        target_version,
        "passed" if retest["ok"] else "failed",
    )
    return _bug_view(bug, log)


async def load_fixes(db: AsyncSession, user_id: str, bug_id: int) -> List[Dict[str, Any]]:
    """单个缺陷的修复历史，最新在前。"""
    bug = await db.scalar(select(Bugs).where(Bugs.id == bug_id, Bugs.user_id == user_id))
    if bug is None:
        raise BugNotFound
    logs = list(
        await db.scalars(
            select(Bug_fix_logs)
            .where(Bug_fix_logs.bug_id == bug_id, Bug_fix_logs.user_id == user_id)
            .order_by(Bug_fix_logs.id.desc())
        )
    )
    return [_fix_view(log) for log in logs]


async def purge_project_bugs(db: AsyncSession, user_id: str, project_id: int) -> None:
    """随项目删除一并清理缺陷与修复记录，避免留下无主数据。"""
    await db.execute(
        sql_delete(Bug_fix_logs).where(Bug_fix_logs.project_id == project_id, Bug_fix_logs.user_id == user_id)
    )
    await db.execute(sql_delete(Bugs).where(Bugs.project_id == project_id, Bugs.user_id == user_id))
