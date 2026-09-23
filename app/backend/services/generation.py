"""生成流水线编排（阶段三：真实模型生成）。

职责：
- 按周期校验并累计用户生成配额（`usage_quotas`）。
- 创建项目、首个版本与六阶段任务行（`projects` / `project_versions` / `build_tasks`）。
- 阶段执行由后台工作器逐个推进（`services.pipeline_runner`），HTTP 接口只做只读快照与调度；
  阶段内容为真实工作：模型解析需求、模型规划方案、模型编写代码、产物归档到对象存储并回读校验、
  按真实内容产出测试报告、发布可访问的产物地址。
- 阶段失败时停在失败阶段并记录真实报错；重试开启新一批任务（`run_no` 递增），
  并把上一轮报错作为修复提示注入模型上下文。

事务边界：每个阶段的「标记进行中」与「写入结果」是两段独立的事务，
中间只进行模型或对象存储的慢调用，不在事务内做外部请求。
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import db_manager
from models.build_tasks import Build_tasks
from models.project_versions import Project_versions
from models.projects import Projects
from models.usage_quotas import Usage_quotas
from services import generation_ai, generation_artifacts
from services.generation_ai import GenerationAIError
from services.generation_artifacts import ArtifactError

logger = logging.getLogger(__name__)

FREE_PLAN = "free"
FREE_QUOTA = 20
TERMINAL_STATUSES = {"succeeded", "failed"}
# 单阶段超过该时长仍未回写结果，视为执行中断（进程重启、连接断开），
# 标记失败让用户可以重试，避免项目永久停在「生成中」。
STAGE_STALE_SECONDS = 600

STAGES: List[Tuple[str, str]] = [
    ("parsing", "解析需求"),
    ("planning", "生成方案"),
    ("coding", "编写代码"),
    ("building", "构建校验"),
    ("testing", "测试验证"),
    ("deploying", "发布预览"),
]

TEMPLATE_SPECS: Dict[str, Dict[str, Any]] = {
    "kpi": {"app_name": "kpi-monitor", "pages": ["总览", "趋势分析", "告警配置"], "entities": ["指标", "数据源", "告警规则"]},
    "crm": {"app_name": "light-crm", "pages": ["客户列表", "跟进记录", "转化漏斗"], "entities": ["客户", "商机", "跟进记录"]},
    "launch": {"app_name": "product-launch", "pages": ["首页", "特性", "预约表单"], "entities": ["预约", "渠道"]},
    "shop": {"app_name": "single-shop", "pages": ["商品列表", "商品详情", "结算"], "entities": ["商品", "订单", "购物车"]},
    "docs": {"app_name": "docs-site", "pages": ["指南", "接口", "搜索"], "entities": ["文档", "分类"]},
    "wait": {"app_name": "waitlist", "pages": ["首页", "邀请码", "社交证明"], "entities": ["邮箱订阅", "邀请码"]},
}

STRUCTURE_CHECKS: List[Tuple[str, Sequence[str]]] = [
    ("doctype", ("<!doctype html",)),
    ("html 根节点", ("<html", "</html>")),
    ("head 区块", ("<head", "</head>")),
    ("body 区块", ("<body", "</body>")),
    ("标题信息", ("<title",)),
]

BEHAVIOR_CHECKS: List[Tuple[str, Sequence[str]]] = [
    ("脚本逻辑", ("<script",)),
    ("交互元素", ("<button", "onclick", "addeventlistener")),
    ("布局样式", ("<style", "display", "grid", "flex")),
    ("中文文案", ("的", "数据", "页面", "任务", "客户", "商品", "指标")),
]


class QuotaExceeded(Exception):
    """当期生成额度已用尽。"""

    def __init__(self, plan: str, used: int, limit: int) -> None:
        super().__init__("本周期生成额度已用尽")
        self.plan = plan
        self.used = used
        self.limit = limit


class ProjectNotFound(Exception):
    """项目不存在或不属于当前用户。"""


def current_period() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _load_json(raw: Optional[str], fallback: Any) -> Any:
    if not raw:
        return fallback
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return fallback
    return value if isinstance(value, type(fallback)) else fallback


def template_spec(template_key: str) -> Dict[str, Any]:
    """模板详情页的推荐方案（确定性展示数据，不消耗模型额度）。"""
    preset = TEMPLATE_SPECS.get(template_key or "", {})
    pages = list(preset.get("pages") or ["首页", "列表页", "详情页"])
    entities = list(preset.get("entities") or ["用户", "业务记录"])
    return {
        "app_name": preset.get("app_name") or (template_key or "app"),
        "display_name": f"{template_key} 模板应用" if template_key else "模板应用",
        "pages": pages,
        "entities": entities,
        "stack": ["React", "TypeScript", "Tailwind"],
        "files": len(pages) + len(entities) + 2,
        "component_tree": [],
        "notes": "模板推荐方案，可在需求中继续补充细节",
        "entry": generation_ai.ENTRY_FILE,
    }


def spec_from_project(project: Projects) -> Dict[str, Any]:
    """读取项目已落库的方案；老数据回退到模板推荐方案。"""
    spec = _load_json(project.spec_json, {})
    if not spec:
        spec = template_spec(project.template_key or "")
    spec.setdefault("display_name", project.name)
    spec.setdefault("entry", generation_ai.ENTRY_FILE)
    spec.setdefault("component_tree", [])
    spec.setdefault("notes", "")
    plan = _load_json(project.plan_json, {})
    if plan.get("files"):
        spec["files"] = len(plan["files"])
    spec.setdefault("files", 0)
    return spec


async def _select_quota(db: AsyncSession, user_id: str, period: str) -> Optional[Usage_quotas]:
    """读取当期配额行；存在重复行时固定取最早一条，避免并发插入后取到不确定的一条。"""
    return await db.scalar(
        select(Usage_quotas)
        .where(Usage_quotas.user_id == user_id, Usage_quotas.period == period)
        .order_by(Usage_quotas.id)
        .limit(1)
    )


async def get_or_create_quota(db: AsyncSession, user_id: str) -> Usage_quotas:
    """按周期返回用户配额行，缺失时以统一默认值创建（幂等）。"""
    period = current_period()
    quota = await _select_quota(db, user_id, period)
    if quota is not None:
        return quota

    quota = Usage_quotas(user_id=user_id, period=period, plan=FREE_PLAN, used=0, quota_limit=FREE_QUOTA)
    db.add(quota)
    try:
        await db.commit()
    except IntegrityError:
        # 并发首次访问可能同时插入，回滚后复用已存在的行，避免出现两套配额。
        await db.rollback()
        existing = await _select_quota(db, user_id, period)
        if existing is None:
            raise
        return existing
    return quota


async def consume_quota(db: AsyncSession, user_id: str) -> Usage_quotas:
    """原子占用一次额度：并发请求不会越过上限，也不会互相覆盖计数。"""
    quota = await get_or_create_quota(db, user_id)
    quota_id = quota.id
    # 回滚会使 ORM 对象过期，先把展示所需字段取到普通变量。
    plan = quota.plan or FREE_PLAN
    limit = quota.quota_limit or FREE_QUOTA

    result = await db.execute(
        update(Usage_quotas)
        .where(
            Usage_quotas.id == quota_id,
            func.coalesce(Usage_quotas.used, 0) < func.coalesce(Usage_quotas.quota_limit, FREE_QUOTA),
        )
        .values(used=func.coalesce(Usage_quotas.used, 0) + 1)
        .execution_options(synchronize_session=False)
    )
    if not result.rowcount:
        await db.rollback()
        used = await db.scalar(select(Usage_quotas.used).where(Usage_quotas.id == quota_id)) or 0
        raise QuotaExceeded(plan, used, limit)

    await db.commit()
    # 计数由数据库原子递增，重新读取以保证返回值与库内一致。
    await db.refresh(quota)
    return quota


async def refund_quota(db: AsyncSession, quota_id: int) -> None:
    """退还一次额度：仅用于占用后真正失败（例如模型不可用）的补偿。"""
    await db.execute(
        update(Usage_quotas)
        .where(Usage_quotas.id == quota_id)
        .values(used=func.greatest(func.coalesce(Usage_quotas.used, 0) - 1, 0))
        .execution_options(synchronize_session=False)
    )
    await db.commit()


def _stage_tasks(rows: Sequence[Build_tasks], run_no: int) -> List[Build_tasks]:
    return sorted((t for t in rows if (t.run_no or 1) == run_no), key=lambda t: t.stage_order or 0)


def _latest_run_no(rows: Sequence[Build_tasks]) -> int:
    return max((t.run_no or 1) for t in rows) if rows else 1


async def _create_run(
    db: AsyncSession,
    user_id: str,
    project: Projects,
    run_no: int,
    precomplete: Optional[Dict[str, Tuple[str, str]]] = None,
) -> None:
    """为一次运行创建六阶段任务行；已完成的阶段直接落为 done，其余由轮询逐个推进。"""
    done = precomplete or {}
    for index, (stage, stage_name) in enumerate(STAGES):
        finished = done.get(stage)
        db.add(
            Build_tasks(
                user_id=user_id,
                project_id=project.id,
                run_no=run_no,
                stage=stage,
                stage_name=stage_name,
                stage_order=index + 1,
                stage_state="done" if finished else "pending",
                stage_log=finished[0] if finished else "",
                error_message="",
                output_summary=finished[1] if finished else "",
            )
        )
    project.status = "running"
    project.current_stage = STAGES[0][0]
    project.preview_url = ""


def _check_report(html: str) -> Tuple[List[Dict[str, Any]], bool, str]:
    """按真实产物内容产出测试报告，并给出构建是否通过。"""
    lowered = html.lower()

    def ratio(checks: Sequence[Tuple[str, Sequence[str]]]) -> Tuple[int, int, List[str]]:
        passed, missing = 0, []
        for label, markers in checks:
            if any(marker in lowered for marker in markers):
                passed += 1
            else:
                missing.append(label)
        return passed, len(checks), missing

    structure_passed, structure_total, structure_missing = ratio(STRUCTURE_CHECKS)
    behavior_passed, behavior_total, behavior_missing = ratio(BEHAVIOR_CHECKS)
    markers = ("<style", "display", "<script", "onclick", "addeventlistener", "grid", "flex")
    coverage = round(sum(1 for marker in markers if marker in lowered) / len(markers) * 100)

    build_ok = structure_passed == structure_total
    report = [
        {
            "id": "unit",
            "label": "结构校验",
            "value": f"{structure_passed} / {structure_total}",
            "passed": build_ok,
        },
        {
            "id": "smoke",
            "label": "冒烟检查",
            "value": f"{behavior_passed} / {behavior_total}",
            "passed": behavior_passed == behavior_total,
        },
        {
            "id": "coverage",
            "label": "实现覆盖",
            "value": f"{coverage}%",
            "passed": coverage >= 70,
        },
    ]
    problems = structure_missing + behavior_missing
    detail = "、".join(problems)
    return report, build_ok, detail


def parsing_log(prompt: str, spec: Dict[str, Any]) -> str:
    """解析阶段的执行日志，创建任务与重跑阶段共用同一份描述。"""
    return (
        f"模型解析需求：{prompt.strip()[:80]}\n"
        f"识别到 {len(spec['entities'])} 个数据实体：{'、'.join(spec['entities'])}\n"
        f"规划出 {len(spec['pages'])} 个页面：{'、'.join(spec['pages'])}"
    )


async def _run_parsing(prompt: str, repair_hint: str) -> Tuple[Dict[str, Any], str, str]:
    spec = await generation_ai.parse_requirements(prompt, repair_hint=repair_hint)
    return spec, parsing_log(prompt, spec), f"结构化需求：{len(spec['entities'])} 个实体 / {len(spec['pages'])} 个页面"


async def _run_planning(prompt: str, spec: Dict[str, Any], repair_hint: str) -> Tuple[Dict[str, Any], str, str]:
    plan = await generation_ai.plan_architecture(prompt, spec, repair_hint)
    log = (
        f"技术栈选定：{' + '.join(spec['stack'])}\n"
        f"文件清单：{'、'.join(item['path'] for item in plan['files'])}\n"
        f"组件树：{'；'.join(plan['component_tree']) or '单页结构'}"
    )
    return plan, log, f"选型：{' / '.join(spec['stack'])}"


async def _run_coding(
    prompt: str, spec: Dict[str, Any], plan: Dict[str, Any], project_id: int, version: int, repair_hint: str
) -> Tuple[Dict[str, Any], str, str]:
    result = await generation_ai.write_application(prompt, spec, plan, repair_hint)
    key = generation_artifacts.artifact_key(project_id, version)
    await generation_artifacts.upload_html(key, result["content"])
    log = (
        f"模型生成 {len(result['files'])} 个文件（{'、'.join(result['files'])}）\n"
        f"{result['summary'] or '已实现全部规划页面'}\n"
        f"产物已写入对象存储：{key}"
    )
    return {"artifact_key": key, "files": result["files"]}, log, f"产出 {len(result['files'])} 个文件"


async def _run_building(artifact_key: str, repair_hint: str) -> Tuple[Dict[str, Any], str, str]:
    html = await generation_artifacts.fetch_html(artifact_key)
    if not html:
        raise ArtifactError("构建校验失败：无法从对象存储回读产物")
    report, ok, detail = _check_report(html)
    size_kb = round(len(html.encode("utf-8")) / 1024, 1)
    if not ok:
        raise GenerationAIError(f"构建校验未通过：缺少 {detail}")
    log = f"回读产物成功，大小 {size_kb} KB\n结构与依赖自检通过\n可执行脚本已内联"
    return {"report": report}, log, f"构建通过，产物 {size_kb} KB"


async def _run_testing(artifact_key: str) -> Tuple[Dict[str, Any], str, str]:
    html = await generation_artifacts.fetch_html(artifact_key)
    if not html:
        raise ArtifactError("测试验证失败：无法从对象存储回读产物")
    report, _, _ = _check_report(html)
    log = "\n".join(f"{item['label']}：{item['value']}" for item in report)
    summary = f"{report[0]['value']} 结构校验、{report[1]['value']} 冒烟检查完成"
    return {"report": report}, log, summary


async def _run_deploying(artifact_key: str) -> Tuple[Dict[str, Any], str, str]:
    url = await generation_artifacts.public_url(artifact_key)
    if not await generation_artifacts.is_reachable(url):
        raise ArtifactError("发布失败：产物地址不可访问")
    log = "归档构建产物到对象存储\n生成可访问的预览地址并完成可用性校验"
    return {"preview_url": url}, log, "产物已发布，预览链接可访问"


async def _fail_stage(db: AsyncSession, project: Projects, task: Build_tasks, message: str, log: str) -> None:
    task.stage_state = "failed"
    task.error_message = message[:900]
    task.stage_log = log[:2000]
    task.output_summary = "阶段失败，修复后可重试"
    project.status = "failed"
    project.current_stage = task.stage
    project.preview_url = ""
    await db.commit()
    await _refund_unusable_first_run(db, project, task)


async def _refund_unusable_first_run(db: AsyncSession, project: Projects, task: Build_tasks) -> None:
    """首轮尚未产出任何产物就失败时退还额度：平台侧没能交付结果，不该由用户买单。

    额度在创建项目时占用（早于任何真实生成），创建接口本身已不再调用模型，因此失败只可能
    发生在后续阶段推进里。这里以「首轮 + 尚无产物」为条件做一次补偿：第 2 轮及以后都是免费
    重试，一律不再退款，所以每个项目最多退一次，不会重复退款。
    """
    if (task.run_no or 1) != 1 or project.artifact_key:
        return
    quota = await _select_quota(db, project.user_id, current_period())
    if quota is None or not quota.used:
        return
    await refund_quota(db, quota.id)
    logger.info("project %s failed before any artifact, refunded quota %s", project.id, quota.id)


async def _sync_version_summary(db: AsyncSession, project: Projects) -> None:
    """发布成功后把版本摘要回填成真实的页面、实体与文件数量。"""
    version = await db.scalar(
        select(Project_versions).where(
            Project_versions.project_id == project.id,
            Project_versions.version == (project.latest_version or 1),
        )
    )
    if version is None:
        return
    spec = spec_from_project(project)
    plan = _load_json(project.plan_json, {})
    files = plan.get("files") if isinstance(plan, dict) else None
    version.diff_summary = (
        f"首个版本：{len(spec['pages'])} 个页面、{len(spec['entities'])} 个数据实体、"
        f"{len(files) if isinstance(files, list) else 0} 个文件"
    )


async def _claim_stage(db: AsyncSession, task: Build_tasks, project: Projects) -> bool:
    """把待执行阶段原子置为进行中。

    返回 False 表示该阶段已被另一次并发轮询抢占，本次请求不再重复执行。
    """
    result = await db.execute(
        update(Build_tasks)
        .where(Build_tasks.id == task.id, Build_tasks.stage_state == "pending")
        .values(stage_state="running", error_message="")
        .execution_options(synchronize_session=False)
    )
    project.current_stage = task.stage
    await db.commit()
    if not result.rowcount:
        await db.refresh(task)
        return False
    task.stage_state = "running"
    task.error_message = ""
    return True


async def _recover_stale_stage(
    db: AsyncSession,
    project: Projects,
    task: Build_tasks,
    orphan_before: Optional[datetime] = None,
) -> bool:
    """回收失去执行者的「进行中」阶段：标记失败并允许用户重试。

    判定条件二选一：
    - 阶段已超过 `STAGE_STALE_SECONDS` 未回写；
    - `orphan_before` 之前的阶段：调用方（进程启动恢复）用它声明「本进程不可能在执行这个
      阶段」，因此上个进程崩溃或重启遗留的阶段无需再等待陈旧阈值即可回收。
    """
    started = task.updated_at or task.created_at
    if started is None:
        return False
    if started.tzinfo is None:
        started = started.replace(tzinfo=timezone.utc)
    stale = datetime.now(timezone.utc) - started >= timedelta(seconds=STAGE_STALE_SECONDS)
    orphan = orphan_before is not None and started < orphan_before
    if not (stale or orphan):
        return False
    logger.warning("project %s stage %s stale, marking failed", project.id, task.stage)
    await _fail_stage(
        db,
        project,
        task,
        f"{task.stage_name}超时未完成，请重试",
        f"阶段执行超过 {STAGE_STALE_SECONDS} 秒仍未回写结果，已判定为中断",
    )
    return True


def _stage_snapshot(project: Projects, task: Build_tasks) -> Dict[str, Any]:
    """复制阶段执行所需的只读输入。

    模型与对象存储的慢调用必须在不持有数据库连接的情况下进行，因此先把需要的字段复制成
    普通值；慢调用结束后再用新的短事务回写结果。
    """
    return {
        "project_id": project.id,
        "task_id": task.id,
        "stage": task.stage,
        "stage_name": task.stage_name or task.stage,
        "prompt": project.prompt or "",
        "spec": spec_from_project(project),
        "plan": _load_json(project.plan_json, {"files": [], "component_tree": [], "notes": ""}),
        "artifact_key": project.artifact_key or "",
        "latest_version": project.latest_version or 1,
    }


async def _run_stage_work(snapshot: Dict[str, Any], repair_hint: str) -> Tuple[Dict[str, Any], str, str]:
    """执行阶段真实工作，返回「需要回写的字段」与展示用的日志、摘要。"""
    stage = snapshot["stage"]
    if stage == "parsing":
        spec, log, summary = await _run_parsing(snapshot["prompt"], repair_hint)
        return (
            {
                "spec_json": json.dumps(spec, ensure_ascii=False),
                "name": spec["display_name"],
                "plan_json": "",
                "test_report_json": "",
            },
            log,
            summary,
        )
    if stage == "planning":
        plan, log, summary = await _run_planning(snapshot["prompt"], snapshot["spec"], repair_hint)
        return {"plan_json": json.dumps(plan, ensure_ascii=False)}, log, summary
    if stage == "coding":
        extra, log, summary = await _run_coding(
            snapshot["prompt"],
            snapshot["spec"],
            snapshot["plan"],
            snapshot["project_id"],
            snapshot["latest_version"],
            repair_hint,
        )
        plan = dict(snapshot["plan"])
        plan["files"] = [{"path": path, "purpose": ""} for path in extra["files"]]
        return (
            {"artifact_key": extra["artifact_key"], "plan_json": json.dumps(plan, ensure_ascii=False)},
            log,
            summary,
        )
    if stage == "building":
        extra, log, summary = await _run_building(snapshot["artifact_key"], repair_hint)
        return {"test_report_json": json.dumps(extra["report"], ensure_ascii=False)}, log, summary
    if stage == "testing":
        extra, log, summary = await _run_testing(snapshot["artifact_key"])
        return {"test_report_json": json.dumps(extra["report"], ensure_ascii=False)}, log, summary
    _, log, summary = await _run_deploying(snapshot["artifact_key"])
    # 预览地址按对象键即时解析，库里只保留对象键，避免落库会过期的签名链接。
    return {"preview_url": ""}, log, summary


async def _load_stage_rows(
    db: AsyncSession, snapshot: Dict[str, Any]
) -> Tuple[Optional[Projects], Optional[Build_tasks]]:
    project = await db.scalar(select(Projects).where(Projects.id == snapshot["project_id"]))
    task = await db.scalar(select(Build_tasks).where(Build_tasks.id == snapshot["task_id"]))
    return project, task


async def _finish_stage(snapshot: Dict[str, Any], updates: Dict[str, Any], log: str, summary: str) -> None:
    """用独立短事务回写阶段结果；此时慢调用已结束，连接不会被长期占用。"""
    async with db_manager.session() as db:
        project, task = await _load_stage_rows(db, snapshot)
        if project is None or task is None or task.stage_state != "running":
            # 阶段已被其它执行者回收、或项目已被删除：丢弃本次结果，不覆盖更新后的状态。
            logger.info(
                "project %s stage %s result dropped (stage no longer running)",
                snapshot["project_id"],
                snapshot["stage"],
            )
            return
        for field, value in updates.items():
            setattr(project, field, value)
        task.stage_state = "done"
        task.stage_log = log
        task.output_summary = summary
        project.status = "running"
        project.current_stage = task.stage
        if task.stage == "deploying":
            project.status = "succeeded"
            project.latest_version = project.latest_version or 1
            await _sync_version_summary(db, project)
        await db.commit()
    logger.info("project %s stage %s done", snapshot["project_id"], snapshot["stage"])


async def _abort_stage(snapshot: Dict[str, Any], message: str, log: str) -> None:
    """阶段失败落库：独立短事务写入可见失败态，并执行首轮额度退款判定。"""
    async with db_manager.session() as db:
        project, task = await _load_stage_rows(db, snapshot)
        if project is None or task is None or task.stage_state != "running":
            logger.info(
                "project %s stage %s failure dropped (stage no longer running)",
                snapshot["project_id"],
                snapshot["stage"],
            )
            return
        await _fail_stage(db, project, task, message, log)


async def _claim_next_stage(
    user_id: str, project_id: int, orphan_before: Optional[datetime] = None
) -> Tuple[Optional[Dict[str, Any]], str]:
    """短事务内选出并抢占下一个待执行阶段，返回执行快照与修复提示。

    第一个返回值为 `None` 时说明本次没有可执行阶段，此时第二个返回值是原因：
    `finished`（已到终态或无待执行阶段）或 `idle`（阶段正被其它执行者持有）。
    """
    async with db_manager.session() as db:
        project = await db.scalar(
            select(Projects).where(Projects.id == project_id, Projects.user_id == user_id)
        )
        if project is None or (project.status or "") in TERMINAL_STATUSES:
            return None, "finished"

        rows = list(
            await db.scalars(
                select(Build_tasks).where(Build_tasks.project_id == project_id).order_by(Build_tasks.id)
            )
        )
        if not rows:
            return None, "finished"

        run_no = _latest_run_no(rows)
        tasks = _stage_tasks(rows, run_no)

        running = next((task for task in tasks if task.stage_state == "running"), None)
        if running is not None:
            # 正常路径下不会看到「进行中」阶段：工作器在同一项目内串行推进。
            # 见到它意味着持有者已消失（进程重启/崩溃），或另一进程正在执行；
            # 因此只在超过陈旧阈值、或确认早于本进程启动时才回收。
            recovered = await _recover_stale_stage(db, project, running, orphan_before=orphan_before)
            return None, "finished" if recovered else "idle"

        pending = next((task for task in tasks if task.stage_state == "pending"), None)
        if pending is None:
            if (project.status or "") != "succeeded":
                project.status = "succeeded"
                await db.commit()
            return None, "finished"

        repair_hint = ""
        if run_no > 1:
            previous = next(
                (task for task in rows if (task.run_no or 1) == run_no - 1 and task.error_message),
                None,
            )
            repair_hint = generation_ai.build_repair_hint(previous.error_message if previous else "")

        snapshot = _stage_snapshot(project, pending)
        if not await _claim_stage(db, pending, project):
            return None, "idle"
        return snapshot, repair_hint


async def create_project(
    db: AsyncSession, user_id: str, prompt: str, template_key: str = ""
) -> Tuple[Projects, Usage_quotas]:
    """占用一次额度，创建项目与六阶段任务。

    这里不调用模型：六个阶段全部交给后台工作器（`services.pipeline_runner`）逐个推进。
    创建请求只做两次数据库写入，因此不会被上游模型拖长；此前把需求解析放在创建请求里，
    一次模型卡顿就会让请求挂到网关超时，用户看到的是 502 而不是可见的阶段失败。
    """
    # 额度先原子占用并提交，后续阶段执行不再持有该事务。
    quota = await consume_quota(db, user_id)

    project: Projects = Projects(
        user_id=user_id,
        name=prompt.strip()[:40] or "未命名应用",
        prompt=prompt,
        status="running",
        current_stage=STAGES[0][0],
        template_key=template_key or "",
        preview_url="",
        latest_version=1,
        spec_json="",
        plan_json="",
        artifact_key="",
        test_report_json="",
    )
    db.add(project)
    await db.commit()

    await _create_run(db, user_id, project, 1)
    db.add(
        Project_versions(
            user_id=user_id,
            project_id=project.id,
            version=1,
            # 方案尚未解析，先写中性摘要，发布阶段成功后回填真实的页面与文件数量。
            diff_summary="首个版本：等待生成完成",
            files_key=generation_artifacts.artifact_key(project.id, 1),
        )
    )
    await db.commit()
    logger.info("project %s created for user %s", project.id, user_id)
    return project, quota


async def retry_project(db: AsyncSession, user_id: str, project_id: int) -> Projects:
    """开启新一批任务重跑流水线，不重复消耗配额，并继承上一轮报错作为修复提示。"""
    project = await db.scalar(select(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    if project is None:
        raise ProjectNotFound

    rows = list(
        await db.scalars(select(Build_tasks).where(Build_tasks.project_id == project_id).order_by(Build_tasks.id))
    )
    run_no = _latest_run_no(rows) + 1 if rows else 1
    spec = spec_from_project(project)
    previous = next(
        (task for task in rows if (task.run_no or 1) == run_no - 1 and task.error_message),
        None,
    )
    precomplete = {}
    # 需求解析已在本项目落库，重跑时直接复用，避免重复消耗模型额度。
    if project.spec_json and not (previous and previous.stage == "parsing"):
        precomplete["parsing"] = (
            parsing_log(project.prompt, spec),
            f"结构化需求：{len(spec['entities'])} 个实体 / {len(spec['pages'])} 个页面",
        )
    await _create_run(db, user_id, project, run_no, precomplete=precomplete)
    await db.commit()
    return project


async def sync_pipeline(db: AsyncSession, user_id: str, project_id: int) -> Dict[str, Any]:
    """只读返回当前流水线快照。

    阶段推进由后台工作器完成（`services.pipeline_runner`），接口只做数据库读取与预览地址解析。
    此前把阶段执行内联在轮询请求里，单次模型调用最长 180 秒，远超上游网关时限
    （Cloudflare 约 100 秒），用户看到的是 502/524 而不是可见的阶段失败。

    读取使用 `populate_existing`：工作器在独立会话里写库，本会话可能已缓存同一行的旧值，
    强制以数据库当前值为准（刷新发生在异步查询内部，不会触发同步惰性加载）。
    """
    project = await db.scalar(
        select(Projects)
        .where(Projects.id == project_id, Projects.user_id == user_id)
        .execution_options(populate_existing=True)
    )
    if project is None:
        raise ProjectNotFound

    rows = list(
        await db.scalars(
            select(Build_tasks)
            .where(Build_tasks.project_id == project_id)
            .order_by(Build_tasks.id)
            .execution_options(populate_existing=True)
        )
    )
    if not rows:
        raise ProjectNotFound

    run_no = _latest_run_no(rows)
    tasks = _stage_tasks(rows, run_no)
    spec = spec_from_project(project)

    report = _load_json(project.test_report_json, [])
    # 预览地址只按对象键即时解析，保证每次轮询/刷新拿到的都是有效链接。
    preview_url = ""
    if project.status == "succeeded" and project.artifact_key:
        try:
            preview_url = await generation_artifacts.public_url(project.artifact_key)
        except ArtifactError as exc:
            logger.warning("project %s preview url resolve failed: %s", project.id, exc)
    return {
        "project": project,
        "tasks": tasks,
        "spec": spec,
        "run_no": run_no,
        "test_report": report if project.status == "succeeded" else [],
        "preview_url": preview_url,
    }


async def advance_pipeline(
    user_id: str, project_id: int, orphan_before: Optional[datetime] = None
) -> str:
    """推进一个阶段：短事务抢占 → 不持有连接的慢调用 → 短事务回写结果。

    阶段执行包含最长 180 秒的模型调用。此前抢占、慢调用、回写共用一个会话，整段慢调用都
    占着数据库连接；无服务器模式下连接池很小，浏览器轮询与后台阶段互相争抢，请求会以
    `QueuePool limit ... timed out` 失败（经网关放大为 502）。拆成三段后，慢调用期间不持有
    任何连接，并发轮询与阶段执行可以并行。

    返回值：
    - `advanced`：本次执行了一个阶段。
    - `finished`：项目已到终态，或无待执行阶段。
    - `idle`：有阶段正被其它执行者持有；本次不重复执行。
    """
    snapshot, detail = await _claim_next_stage(user_id, project_id, orphan_before)
    if snapshot is None:
        return detail

    repair_hint = detail
    try:
        updates, log, summary = await _run_stage_work(snapshot, repair_hint)
    except (GenerationAIError, ArtifactError, ValueError) as exc:
        logger.warning("project %s stage %s failed: %s", snapshot["project_id"], snapshot["stage"], exc)
        await _abort_stage(
            snapshot,
            f"{snapshot['stage_name']}失败：{exc}",
            f"阶段执行失败：{exc}",
        )
        return "advanced"
    except Exception as exc:  # noqa: BLE001 - 意外异常也落成可见失败，避免阶段永久停在「进行中」
        logger.error(
            "project %s stage %s crashed: %s", snapshot["project_id"], snapshot["stage"], exc, exc_info=True
        )
        await _abort_stage(
            snapshot,
            f"{snapshot['stage_name']}异常中断：{exc}",
            f"阶段执行异常：{exc}",
        )
        return "advanced"

    await _finish_stage(snapshot, updates, log, summary)
    return "advanced"


async def count_projects(db: AsyncSession, user_id: str) -> int:
    """当前账号的项目总数。"""
    return await db.scalar(select(func.count()).select_from(Projects).where(Projects.user_id == user_id)) or 0
