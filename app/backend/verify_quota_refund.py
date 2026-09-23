"""可靠性验证：模型不可用时必须退还额度且不留下半成品项目。

不依赖模型成功返回：真实调用模型，若外部服务失败（例如余额不足），
断言配额回到 0、没有残留项目与任务，用户额度不会被白扣。
"""

import asyncio
import sys

sys.path.insert(0, "/workspace/app/backend")

from sqlalchemy import delete, func, select

from core.database import db_manager
from models.build_tasks import Build_tasks
from models.projects import Projects
from models.usage_quotas import Usage_quotas
from services import generation

TEST_USER = "verify-refund-user"
PROMPT = "做一个团队任务协作应用，支持添加任务和按状态统计"


async def cleanup(session):
    await session.execute(delete(Build_tasks).where(Build_tasks.user_id == TEST_USER))
    await session.execute(delete(Projects).where(Projects.user_id == TEST_USER))
    await session.execute(delete(Usage_quotas).where(Usage_quotas.user_id == TEST_USER))
    await session.commit()


async def main():
    async with db_manager.session() as session:
        await cleanup(session)

        failed = False
        try:
            await generation.create_project(session, TEST_USER, PROMPT)
        except Exception as exc:  # noqa: BLE001 - 这里就是要验证失败路径
            failed = True
            print("STEP1 model call failed as expected:", type(exc).__name__, flush=True)

        quota = await generation.get_or_create_quota(session, TEST_USER)
        project_count = await session.scalar(
            select(func.count()).select_from(Projects).where(Projects.user_id == TEST_USER)
        )
        task_count = await session.scalar(
            select(func.count()).select_from(Build_tasks).where(Build_tasks.user_id == TEST_USER)
        )
        print("STEP2 quota used:", quota.used, "/", quota.quota_limit, flush=True)
        print("STEP3 leftover projects:", project_count, "tasks:", task_count, flush=True)

        assert quota.used == 0, "模型失败后额度未退还"
        assert project_count == 0, "模型失败后残留了半成品项目"
        assert task_count == 0, "模型失败后残留了阶段任务"
        print("STEP4 refund ok, no partial project" + (" (real model failure path)" if failed else " (model succeeded)"), flush=True)

        await cleanup(session)
        print("RESULT quota refund: OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
