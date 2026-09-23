"""生成流水线编排。

职责：
- 按周期校验并累计用户生成配额（`usage_quotas`）。
- 创建项目、版本与六阶段任务行（`projects` / `project_versions` / `build_tasks`）。
- 依据任务创建时间推进阶段状态机，使时间线由服务端状态驱动，而不是前端定时器。
- 失败时停在失败阶段并暴露原因，重试时开启新一批任务（`run_no` 递增）。

本服务不调用外部 AI / HTTP，因此不涉及跨事务的慢调用。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.build_tasks import Build_tasks
from models.project_versions import Project_versions
from models.projects import Projects
from models.usage_quotas import Usage_quotas

logger = logging.getLogger(__name__)

# 每个阶段的模拟耗时（秒）。阶段推进完全由服务端时间驱动，前端只负责轮询。
STAGE_SECONDS = 0.9
FREE_PLAN = "free"
FREE_QUOTA = 20

STAGES: List[Tuple[str, str]] = [
    ("parsing", "解析需求"),
    ("planning", "生成方案"),
    ("coding", "编写代码"),
    ("building", "构建校验"),
    ("testing", "测试验证"),
    ("deploying", "发布预览"),
]

# 首次运行在第 4 个阶段（构建校验）失败，用于演示「失败可见 + 重试修复」。
FAIL_STAGE_ORDER = 4
FAIL_KEYWORDS = ("失败", "报错", "fail", "error")

KEYWORD_ENTITIES: List[Tuple[Sequence[str], List[str]]] = [
    (("任务", "待办", "todo", "协作", "清单"), ["任务", "成员", "评论"]),
    (("客户", "crm", "线索", "销售"), ["客户", "商机", "跟进记录"]),
    (("商品", "订单", "商城", "电商", "购物车"), ["商品", "订单", "购物车"]),
    (("文章", "博客", "内容", "文档"), ["文章", "分类", "标签"]),
    (("看板", "指标", "报表", "数据", "dashboard"), ["指标", "数据源", "告警规则"]),
]
KEYWORD_PAGES: List[Tuple[Sequence[str], List[str]]] = [
    (("落地页", "官网", "品牌", "landing", "营销"), ["首页", "套餐", "订阅表单"]),
    (("看板", "指标", "报表", "数据", "dashboard"), ["总览", "趋势分析", "渠道明细"]),
    (("任务", "待办", "todo", "协作"), ["任务列表", "看板视图", "统计"]),
    (("商城", "电商", "商品", "订单"), ["商品列表", "商品详情", "结算"]),
]
DEFAULT_ENTITIES = ["用户", "业务记录"]
DEFAULT_PAGES = ["首页", "列表页", "详情页"]


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


def _as_utc(value: Optional[datetime]) -> datetime:
    if value is None:
        return datetime.now(timezone.utc)
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _match(text: str, table: Sequence[Tuple[Sequence[str], List[str]]], fallback: List[str]) -> List[str]:
    for keywords, values in table:
        if any(k in text for k in keywords):
            return list(values)
    return list(fallback)


def build_spec(prompt: str, template_key: str) -> Dict[str, Any]:
    """从需求文本推导结构化方案：应用名、页面、数据实体与技术栈。"""
    text = (prompt or "").lower()
    pages = _match(text, KEYWORD_PAGES, DEFAULT_PAGES)
    entities = _match(text, KEYWORD_ENTITIES, DEFAULT_ENTITIES)

    stack = ["React", "TypeScript", "Tailwind"]
    if any(k in text for k in ("看板", "指标", "报表", "数据", "dashboard")):
        stack.append("Recharts")
    if any(k in text for k in ("任务", "待办", "todo", "协作")):
        stack.append("Zustand")
    if any(k in text for k in ("登录", "账号", "用户", "会员")):
        stack.append("Auth")

    slug = template_key or "app"
    display_name = (prompt or "").strip()[:18] or "未命名应用"

    return {
        "app_name": slug,
        "display_name": display_name,
        "pages": pages,
        "entities": entities,
        "stack": stack,
        "files": len(pages) * 2 + len(entities) + 4,
        "failing": any(k in text for k in FAIL_KEYWORDS),
    }


def _test_metrics(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
    unit_total = len(spec["pages"]) * 6 + len(spec["entities"]) * 2
    smoke_total = len(spec["pages"]) + 2
    coverage = min(96, 78 + len(spec["entities"]) * 2 + len(spec["pages"]))
    return [
        {"id": "unit", "label": "单元用例", "value": f"{unit_total} / {unit_total}", "passed": True},
        {"id": "smoke", "label": "冒烟用例", "value": f"{smoke_total} / {smoke_total}", "passed": True},
        {"id": "coverage", "label": "语句覆盖率", "value": f"{coverage}%", "passed": True},
    ]


def stage_output(spec: Dict[str, Any], stage: str, repaired: bool = False) -> Tuple[str, str]:
    """返回某个阶段的执行日志与产出摘要。"""
    pages = "、".join(spec["pages"])
    entities = "、".join(spec["entities"])

    if stage == "parsing":
        return (
            f"识别到 {len(spec['entities'])} 个数据实体：{entities}\n"
            f"规划出 {len(spec['pages'])} 个页面：{pages}",
            f"结构化需求：{len(spec['entities'])} 个实体 / {len(spec['pages'])} 个页面",
        )
    if stage == "planning":
        return (
            f"技术栈选定：{' + '.join(spec['stack'])}\n"
            f"组件树：App -> {len(spec['pages'])} 个页面 -> {len(spec['entities'])} 个数据模型",
            f"选型：{' / '.join(spec['stack'])}",
        )
    if stage == "coding":
        return (
            f"生成 {len(spec['pages'])} 个页面组件与 {len(spec['entities'])} 个数据模型\n"
            f"共写入 {spec['files']} 个文件",
            f"产出 {spec['files']} 个文件",
        )
    if stage == "building":
        if repaired:
            return (
                "按上一次失败日志修正依赖引用\n类型检查通过\n产物大小 268 KB",
                "修复后构建通过，产物 268 KB",
            )
        return (
            "依赖安装完成（4.2s）\n类型检查通过\n产物大小 268 KB",
            "构建通过，产物 268 KB",
        )
    if stage == "testing":
        metrics = _test_metrics(spec)
        return (
            "\n".join(f"{m['label']}：{m['value']}" for m in metrics),
            f"{metrics[0]['value']} 单元用例、{metrics[1]['value']} 冒烟用例全部通过",
        )
    if stage == "deploying":
        return (
            "归档构建产物到对象存储\n登记版本与产物引用键",
            "产物已归档，可访问预览链接随阶段三开放",
        )
    return ("", "")


async def get_or_create_quota(db: AsyncSession, user_id: str) -> Usage_quotas:
    """按周期返回用户配额行，缺失时以统一默认值创建（幂等）。"""
    period = current_period()
    quota = await db.scalar(
        select(Usage_quotas).where(Usage_quotas.user_id == user_id, Usage_quotas.period == period)
    )
    if quota is None:
        quota = Usage_quotas(user_id=user_id, period=period, plan=FREE_PLAN, used=0, quota_limit=FREE_QUOTA)
        db.add(quota)
        await db.commit()
    return quota


async def _create_run(db: AsyncSession, user_id: str, project: Projects, run_no: int, spec: Dict[str, Any]) -> None:
    repair = run_no > 1
    for index, (stage, stage_name) in enumerate(STAGES):
        log, summary = stage_output(spec, stage, repaired=repair)
        db.add(
            Build_tasks(
                user_id=user_id,
                project_id=project.id,
                run_no=run_no,
                stage=stage,
                stage_name=stage_name,
                stage_order=index + 1,
                stage_state="running" if index == 0 else "pending",
                stage_log=log if index == 0 else "",
                error_message="",
                output_summary=summary if index == 0 else "",
            )
        )
    project.status = "running"
    project.current_stage = STAGES[0][0]


def _latest_run_no(tasks: Sequence[Build_tasks]) -> int:
    return max((t.run_no or 1) for t in tasks)


async def create_project(
    db: AsyncSession, user_id: str, prompt: str, template_key: str = ""
) -> Tuple[Projects, Usage_quotas]:
    """创建项目、首个版本与一批六阶段任务，并占用一次生成额度。"""
    quota = await get_or_create_quota(db, user_id)
    used = quota.used or 0
    limit = quota.quota_limit or FREE_QUOTA
    if used >= limit:
        raise QuotaExceeded(quota.plan or FREE_PLAN, used, limit)

    spec_summary = build_spec(prompt, template_key)
    project = Projects(
        user_id=user_id,
        name=spec_summary["display_name"],
        prompt=prompt,
        status="running",
        current_stage=STAGES[0][0],
        template_key=template_key or "",
        preview_url="",
        latest_version=1,
    )
    db.add(project)
    await db.commit()

    spec = build_spec(prompt, template_key)
    await _create_run(db, user_id, project, 1, spec)
    db.add(
        Project_versions(
            user_id=user_id,
            project_id=project.id,
            version=1,
            diff_summary=f"首个版本：{len(spec['pages'])} 个页面、{len(spec['entities'])} 个数据实体",
            files_key=f"projects/{project.id}/v1",
        )
    )
    quota.used = used + 1
    await db.commit()
    logger.info("project %s created for user %s", project.id, user_id)
    return project, quota


async def retry_project(db: AsyncSession, user_id: str, project_id: int) -> Projects:
    """开启新一批任务重跑流水线，不重复消耗配额。"""
    project = await db.scalar(select(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    if project is None:
        raise ProjectNotFound

    task_rows = list(
        await db.scalars(select(Build_tasks).where(Build_tasks.project_id == project_id).order_by(Build_tasks.id))
    )
    spec = build_spec(project.prompt, project.template_key or "")
    await _create_run(db, user_id, project, _latest_run_no(task_rows) + 1, spec)
    await db.commit()
    return project


async def sync_pipeline(db: AsyncSession, user_id: str, project_id: int) -> Dict[str, Any]:
    """按已流逝时间推进阶段状态机，并返回当前流水线快照。"""
    project = await db.scalar(select(Projects).where(Projects.id == project_id, Projects.user_id == user_id))
    if project is None:
        raise ProjectNotFound

    task_rows = list(
        await db.scalars(select(Build_tasks).where(Build_tasks.project_id == project_id).order_by(Build_tasks.id))
    )
    if not task_rows:
        raise ProjectNotFound

    run_no = _latest_run_no(task_rows)
    tasks = sorted((t for t in task_rows if (t.run_no or 1) == run_no), key=lambda t: t.stage_order or 0)
    spec = build_spec(project.prompt, project.template_key or "")

    started_at = min(_as_utc(t.created_at) for t in tasks)
    elapsed = (datetime.now(timezone.utc) - started_at).total_seconds()
    finished_stages = min(len(STAGES), int(elapsed // STAGE_SECONDS))

    fail_at = FAIL_STAGE_ORDER if (spec["failing"] and run_no == 1) else None
    if fail_at is not None and finished_stages >= fail_at:
        finished_stages = fail_at - 1

    changed = False
    for index, task in enumerate(tasks):
        order = index + 1
        if fail_at is not None and order == fail_at:
            if task.stage_state != "failed":
                task.stage_state = "failed"
                task.error_message = "构建失败：缺少依赖 react-router-dom，类型检查未通过"
                task.stage_log = "依赖安装完成（5.1s）\n类型检查失败：找不到模块 'react-router-dom'"
                task.output_summary = "构建失败，停在构建校验阶段"
                changed = True
            continue
        if order <= finished_stages:
            target, log, summary = "done", *stage_output(spec, task.stage, repaired=run_no > 1)
        elif order == finished_stages + 1 and not (fail_at is not None and order > fail_at):
            target, log, summary = "running", *stage_output(spec, task.stage, repaired=run_no > 1)
        else:
            target, log, summary = "pending", "", ""
        if task.stage_state != target:
            task.stage_state = target
            changed = True
        if target != "pending" and not task.stage_log:
            task.stage_log = log
            changed = True
        if target != "pending" and not task.output_summary:
            task.output_summary = summary
            changed = True

    if fail_at is not None:
        failed = next((t for t in tasks if (t.stage_order or 0) == fail_at), None)
        project.status, project.current_stage, project.preview_url = (
            "failed",
            failed.stage if failed else STAGES[fail_at - 1][0],
            "",
        )
    elif finished_stages >= len(STAGES):
        project.status = "succeeded"
        project.current_stage = STAGES[-1][0]
        # 阶段二不产出可访问的部署地址，预览链接留待真实模型生成阶段接入。
        project.preview_url = ""
    else:
        project.status = "running"
        project.current_stage = STAGES[finished_stages][0]
        project.preview_url = ""

    if changed:
        await db.commit()

    return {
        "project": project,
        "tasks": tasks,
        "spec": spec,
        "run_no": run_no,
        "test_report": _test_metrics(spec) if project.status == "succeeded" else [],
    }
