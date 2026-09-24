"""生成流水线后台工作器。

为什么需要它：阶段执行包含最长 180 秒的模型调用，若内联在 HTTP 请求里，请求会超过上游
网关时限（Cloudflare 约 100 秒），用户看到的是 502/524 而不是可见的阶段失败。这里把阶段
执行搬到后台任务：接口只负责只读快照与调度，模型调用在独立会话中串行推进。

并发与恢复：
- 进程内按项目去重，同一项目同时只有一个工作器；
- 阶段本身仍是数据库原子抢占（`pending → running`），因此多进程部署也不会重复执行；
- 进程重启会让「进行中」的阶段失去执行者，所以启动时与用户访问项目时都会重新调度，
  超过陈旧阈值的阶段由工作器回收为可见失败态。
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Dict, Optional

from sqlalchemy import select

from core.database import db_manager
from models.projects import Projects
from services import generation

logger = logging.getLogger(__name__)

# 单轮最多推进的阶段数：正常 6 个（重试后重新计数），留出余量即可。
MAX_STAGES_PER_RUN = 12
# 启动恢复时最多接管的项目数，避免一次拉起过多后台任务。
RESUME_PROJECT_LIMIT = 20
NON_TERMINAL_STATUSES = ("queued", "pending", "running")
# 请求返回前留给工作器的起步时间：这段时间内完成的阶段会直接体现在响应里，
# 超过则请求先返回，阶段在后台继续执行并落库（前端下次轮询即可看到最新状态）。
# 该上限远低于上游网关时限，因此轮询不会再有 502/524。
INLINE_KICK_SECONDS = 10.0

_tasks: Dict[int, asyncio.Task] = {}


def schedule(user_id: str, project_id: int, orphan_before: Optional[datetime] = None) -> Optional[asyncio.Task]:
    """确保项目有后台工作器在推进；已有工作器在跑时直接复用并返回它。"""
    existing = _tasks.get(project_id)
    if existing is not None and not existing.done():
        return existing
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # 没有运行中的事件循环（例如在同步上下文里被调用）时安静跳过，等待下次调度。
        logger.debug("no running event loop, skip scheduling project %s", project_id)
        return None
    task = loop.create_task(_drive(user_id, project_id, orphan_before))
    _tasks[project_id] = task
    task.add_done_callback(lambda _finished, pid=project_id: _tasks.pop(pid, None))
    return task


async def kick(
    user_id: str,
    project_id: int,
    orphan_before: Optional[datetime] = None,
    wait_seconds: Optional[float] = None,
) -> None:
    """启动工作器，并在有限时间内等待它推进，超时即返回（不中断阶段执行）。

    这样设计是为了兼容两种部署形态：
    - 常驻进程：请求很快返回，阶段继续在后台跑完，用户轮询即可看到结果；
    - 无服务器（会冻结进程）：本请求内的起步时间就是一次真实推进，后续每次轮询都会继续
      推进，因此进度始终向前，且单个请求永远不会逼近网关超时。
    """
    task = schedule(user_id, project_id, orphan_before)
    if task is None:
        return
    budget = INLINE_KICK_SECONDS if wait_seconds is None else wait_seconds
    if budget <= 0:
        return
    try:
        # shield：超时只结束本次等待，不取消阶段执行——阶段必须完整跑完并回写数据库。
        await asyncio.wait_for(asyncio.shield(task), timeout=budget)
    except asyncio.TimeoutError:
        logger.info("project %s stage still running in background", project_id)
    except Exception:  # noqa: BLE001 - 工作器异常已在 _drive 中记录，不应影响接口响应
        logger.debug("pipeline runner stopped with error for project %s", project_id, exc_info=True)


async def run_pipeline(
    user_id: str, project_id: int, orphan_before: datetime | None = None
) -> None:
    """同步推进直到终态或无可执行阶段，等价于「用户持续轮询直至完成」。"""
    for _ in range(MAX_STAGES_PER_RUN):
        outcome = await generation.advance_pipeline(user_id, project_id, orphan_before)
        if outcome != "advanced":
            return


async def _drive(user_id: str, project_id: int, orphan_before: datetime | None = None) -> None:
    try:
        await run_pipeline(user_id, project_id, orphan_before)
    except asyncio.CancelledError:
        raise
    except Exception as exc:  # noqa: BLE001 - 工作器异常不影响接口，记录后由下次调度重试
        logger.error("pipeline runner failed for project %s: %s", project_id, exc, exc_info=True)


async def resume_pending_projects() -> int:
    """接管未完成项目，返回接管数量。

    进程重启后没有工作器在推进，项目会一直停在「生成中」。启动时刻之前的「进行中」阶段
    必然属于上一个进程，因此这里把它作为孤儿立即回收（标记失败、允许免费重试），
    其它「待执行」阶段则由工作器继续推进。
    """
    started_at = datetime.now(timezone.utc)
    async with db_manager.session() as db:
        rows = list(
            await db.scalars(
                select(Projects)
                .where(Projects.status.in_(NON_TERMINAL_STATUSES))
                .order_by(Projects.id.desc())
                .limit(RESUME_PROJECT_LIMIT)
            )
        )
    for project in rows:
        schedule(project.user_id, project.id, orphan_before=started_at)
    if rows:
        logger.info("resumed %s unfinished generation projects", len(rows))
    return len(rows)
