"""阶段三端到端验证：真实模型 + 对象存储的六阶段流水线。

直接调用服务层（绕过 HTTP 认证），模拟前端轮询推进六个阶段，
校验阶段状态契约、产物可访问性与配额扣减，最后清理测试数据。
"""

import asyncio
import sys

sys.path.insert(0, "/workspace/app/backend")

from sqlalchemy import delete, select

from core.database import db_manager
from models.build_tasks import Build_tasks
from models.project_versions import Project_versions
from models.projects import Projects
from models.usage_quotas import Usage_quotas
from services import generation
from services.generation import QuotaExceeded

TEST_USER = "verify-stage3-user"
PROMPT = "做一个团队任务协作应用，支持添加任务、勾选完成和按状态统计"


async def cleanup(session):
    for model in (Build_tasks, Project_versions):
        await session.execute(delete(model).where(model.user_id == TEST_USER))
    await session.execute(delete(Projects).where(Projects.user_id == TEST_USER))
    await session.execute(delete(Usage_quotas).where(Usage_quotas.user_id == TEST_USER))
    await session.commit()


async def main():
    async with db_manager.session() as session:
        await cleanup(session)

        project, quota = await generation.create_project(session, TEST_USER, PROMPT)
        print("STEP1 created project:", project.id, project.name, "quota used:", quota.used, flush=True)

        seen_stages = []
        snapshot = None
        for _ in range(12):
            snapshot = await generation.sync_pipeline(session, TEST_USER, project.id)
            states = {t.stage: t.stage_state for t in snapshot["tasks"]}
            fingerprint = tuple(sorted(states.items()))
            if fingerprint not in seen_stages:
                seen_stages.append(fingerprint)
                print("STEP2 poll", len(seen_stages), states, "status:", snapshot["project"].status, flush=True)
            if snapshot["project"].status in generation.TERMINAL_STATUSES:
                break
            await asyncio.sleep(1)

        project_row = await session.scalar(select(Projects).where(Projects.id == project.id))
        tasks = list(
            await session.scalars(
                select(Build_tasks).where(Build_tasks.project_id == project.id).order_by(Build_tasks.stage_order)
            )
        )
        print("STEP3 final status:", project_row.status, flush=True)
        print("STEP4 stages:", [(t.stage, t.stage_state) for t in tasks], flush=True)
        print("STEP5 artifact_key:", project_row.artifact_key, flush=True)
        print("STEP6 preview_url persisted(should be empty):", repr(project_row.preview_url), flush=True)
        print("STEP7 resolved preview_url:", (snapshot.get("preview_url") or "")[:100], flush=True)
        print("STEP8 test_report:", snapshot["test_report"], flush=True)

        versions = list(
            await session.scalars(select(Project_versions).where(Project_versions.project_id == project.id))
        )
        print("STEP9 versions:", [(v.version, v.files_key) for v in versions], flush=True)

        assert project_row.status == "succeeded", "流水线未成功"
        assert all(t.stage_state == "done" for t in tasks), "存在未完成阶段"
        assert snapshot.get("preview_url"), "未解析出预览地址"
        assert not project_row.preview_url, "库中不应持久化签名预览地址"

        # 重试链路：成功后重试应开启新一批任务且不额外消耗配额
        await generation.retry_project(session, TEST_USER, project.id)
        quota_after = await generation.get_or_create_quota(session, TEST_USER)
        runs = list(
            await session.scalars(
                select(Build_tasks).where(Build_tasks.project_id == project.id).order_by(Build_tasks.id)
            )
        )
        print(
            "STEP10 retry run_nos:",
            sorted({t.run_no for t in runs}),
            "quota used:",
            quota_after.used,
            flush=True,
        )
        assert sorted({t.run_no for t in runs}) == [1, 2], "重试未开启新一批任务"
        assert quota_after.used == 1, "重试不应重复消耗配额"

        # 配额用尽链路
        quota_after.used = quota_after.quota_limit
        await session.commit()
        try:
            await generation.create_project(session, TEST_USER, "再做一个应用")
            raise AssertionError("额度用尽时未拦截")
        except QuotaExceeded as exc:
            print("STEP11 quota guard ok:", exc.used, "/", exc.limit, flush=True)

        await cleanup(session)
        print("RESULT pipeline: OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
