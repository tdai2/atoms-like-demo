"""阶段三端到端验证：真实模型 + 对象存储的六阶段流水线。

阶段执行由后台工作器负责（`services.pipeline_runner`），本脚本像前端一样只读快照，
校验阶段状态契约、产物可访问性与配额扣减，最后清理测试数据。

读取一律使用独立短会话：工作器在各自的会话里写库，复用同一个会话会读到身份映射缓存里的旧值。
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
from services import generation, pipeline_runner
from services.generation import QuotaExceeded

TEST_USER = "verify-stage3-user"
PROMPT = "做一个团队任务协作应用，支持添加任务、勾选完成和按状态统计"


async def cleanup():
    async with db_manager.session() as session:
        for model in (Build_tasks, Project_versions):
            await session.execute(delete(model).where(model.user_id == TEST_USER))
        await session.execute(delete(Projects).where(Projects.user_id == TEST_USER))
        await session.execute(delete(Usage_quotas).where(Usage_quotas.user_id == TEST_USER))
        await session.commit()


async def read_snapshot(project_id: int):
    """像前端轮询那样读取快照，不执行任何阶段。"""
    async with db_manager.session() as reader:
        return await generation.sync_pipeline(reader, TEST_USER, project_id)


async def main():
    await cleanup()

    async with db_manager.session() as session:
        project, quota = await generation.create_project(session, TEST_USER, PROMPT)
    print("STEP1 created project:", project.id, "quota used:", quota.used, flush=True)

    seen_stages = []
    snapshot = None
    for _ in range(30):
        await pipeline_runner.run_pipeline(TEST_USER, project.id)
        snapshot = await read_snapshot(project.id)
        states = {t.stage: t.stage_state for t in snapshot["tasks"]}
        fingerprint = tuple(sorted(states.items()))
        if fingerprint not in seen_stages:
            seen_stages.append(fingerprint)
            print("STEP2 poll", len(seen_stages), states, "status:", snapshot["project"].status, flush=True)
        if snapshot["project"].status in generation.TERMINAL_STATUSES:
            break
        await asyncio.sleep(1)

    async with db_manager.session() as session:
        project_row = await session.scalar(select(Projects).where(Projects.id == project.id))
        tasks = list(
            await session.scalars(
                select(Build_tasks).where(Build_tasks.project_id == project.id).order_by(Build_tasks.stage_order)
            )
        )
        versions = list(
            await session.scalars(select(Project_versions).where(Project_versions.project_id == project.id))
        )
        print("STEP3 final status:", project_row.status, flush=True)
        print("STEP4 stages:", [(t.stage, t.stage_state) for t in tasks], flush=True)
        print("STEP5 artifact_key:", project_row.artifact_key, flush=True)
        print("STEP6 preview_url persisted(should be empty):", repr(project_row.preview_url), flush=True)
        print("STEP7 resolved preview_url:", (snapshot.get("preview_url") or "")[:100], flush=True)
        print("STEP8 test_report:", snapshot["test_report"], flush=True)
        print("STEP9 versions:", [(v.version, v.files_key) for v in versions], flush=True)
        persisted_preview = project_row.preview_url
        artifact_key = project_row.artifact_key
        final_status = project_row.status
        stage_states = [t.stage_state for t in tasks]
        first_error = next((t.error_message for t in tasks if t.error_message), "")

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

    await cleanup()

    assert final_status == "succeeded", f"流水线未成功：{final_status} / {first_error[:160]}"
    assert all(state == "done" for state in stage_states), f"存在未完成阶段：{stage_states}"
    assert artifact_key, "未产出产物对象键"
    assert snapshot.get("preview_url"), "未解析出预览地址"
    assert not persisted_preview, "库中不应持久化签名预览地址"
    print("RESULT pipeline: OK", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
