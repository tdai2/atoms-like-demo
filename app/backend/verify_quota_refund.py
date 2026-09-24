"""可靠性验证：阶段推进失败时，额度必须退还且失败态对用户可见。

背景：创建接口只做数据库落库（不再内联模型调用），阶段执行由后台工作器承担。
因此这里断言的是「阶段失败 → 额度退还 → 项目保留为可见失败态」，而不是创建请求直接失败。

不依赖模型成功返回：真实调用模型，若外部服务失败（例如余额不足），断言额度回到 0。
若模型可用则跳过失败断言，仅验证阶段推进链路本身。
"""

import asyncio
import sys

sys.path.insert(0, "/workspace/app/backend")

from sqlalchemy import delete, func, select

from core.database import db_manager
from models.build_tasks import Build_tasks
from models.projects import Projects
from models.project_versions import Project_versions
from models.usage_quotas import Usage_quotas
from services import generation, pipeline_runner

TEST_USER = "verify-refund-user"
PROMPT = "做一个团队任务协作应用，支持添加任务和按状态统计"


async def cleanup():
    async with db_manager.session() as session:
        await session.execute(delete(Build_tasks).where(Build_tasks.user_id == TEST_USER))
        await session.execute(delete(Project_versions).where(Project_versions.user_id == TEST_USER))
        await session.execute(delete(Projects).where(Projects.user_id == TEST_USER))
        await session.execute(delete(Usage_quotas).where(Usage_quotas.user_id == TEST_USER))
        await session.commit()


async def read_snapshot(project_id: int):
    async with db_manager.session() as reader:
        return await generation.sync_pipeline(reader, TEST_USER, project_id)


async def quota_used() -> int:
    """直接读列值，避免读到同一会话中身份映射缓存的旧对象。"""
    async with db_manager.session() as session:
        return await session.scalar(select(Usage_quotas.used).where(Usage_quotas.user_id == TEST_USER)) or 0


async def project_count() -> int:
    async with db_manager.session() as session:
        return await session.scalar(
            select(func.count()).select_from(Projects).where(Projects.user_id == TEST_USER)
        ) or 0


async def main():
    await cleanup()

    # 创建阶段只落库：即使模型完全不可用，这一步也必须成功返回。
    async with db_manager.session() as session:
        project, quota = await generation.create_project(session, TEST_USER, PROMPT)
    print("STEP1 created project:", project.id, "quota used:", quota.used, flush=True)
    assert quota.used == 1, "创建项目未占用额度"

    # 后台工作器真正调用模型；这里只像前端那样读取快照。
    await pipeline_runner.run_pipeline(TEST_USER, project.id)
    snapshot = await read_snapshot(project.id)
    status = snapshot["project"].status
    print("STEP2 after pipeline status:", status, flush=True)

    if status == "failed":
        failed_task = next(t for t in snapshot["tasks"] if t.stage_state == "failed")
        print("STEP3 failed stage:", failed_task.stage, "msg:", failed_task.error_message[:80], flush=True)

        used_after = await quota_used()
        print("STEP4 quota used after failure:", used_after, flush=True)
        assert used_after == 0, "首轮无产物失败后额度未退还"

        # 失败不清空：项目与任务必须保留，用户可以看到失败原因并重试。
        assert await project_count() == 1, "失败后项目应保留为可见失败态"

        # 免费重试：第二轮继续推进不应再次扣额度，也不应重复退款。
        async with db_manager.session() as session:
            await generation.retry_project(session, TEST_USER, project.id)
        await pipeline_runner.run_pipeline(TEST_USER, project.id)
        used_retry = await quota_used()
        print("STEP5 quota used after retry:", used_retry, flush=True)
        assert used_retry == 0, "免费重试不应消耗额度"
        print("RESULT quota refund: OK (real model failure path)", flush=True)
    else:
        used_ok = await quota_used()
        print("STEP4 model available, quota used:", used_ok, flush=True)
        assert used_ok == 1, "生成成功时额度应保持已占用"
        print("RESULT quota refund: SKIPPED (model available, no failure to verify)", flush=True)

    await cleanup()


if __name__ == "__main__":
    asyncio.run(main())
