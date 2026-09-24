"""阶段四验证：测试用例生成、真实执行与结果记录。

覆盖点：
1. 用例生成依赖真实产物：无 `artifact_key` 时必须明确拒绝，不能凭空产出用例。
2. 执行结果由真实产物决定：断言命中的用例通过，未命中的用例失败并给出原因。
3. 停用的用例不参与执行；运行记录包含统计、耗时与逐用例结果。
4. 运行历史按时间倒序可查，且与用例同源隔离（跨用户不可见）。
5. 项目删除时一并清理用例与执行记录，不留无主数据。
6. 模型生成的用例（真调用 `claude-opus-5`）：模型不可用时明确跳过，不伪造通过。

断言全部基于已知产物内容，因此脚本在模型不可用时依然能验证执行链路本身。
"""

import asyncio
import json
import sys
import uuid

sys.path.insert(0, "/workspace/app/backend")

from sqlalchemy import delete, func, select

from core.database import db_manager
from models.projects import Projects
from models.test_cases import Test_cases
from models.test_runs import Test_runs
from services import generation_artifacts, test_suite
from services.generation import ProjectNotFound
from services.generation_ai import GenerationAIError

OWNER = f"verify-testsuite-{uuid.uuid4().hex[:8]}"
OTHER_USER = "verify-testsuite-other"
ARTIFACT_KEY = f"verify/testsuite/{uuid.uuid4().hex[:8]}/index.html"

# 已知产物：包含 <h1>、<button>、脚本绑定与中文文案，缺少 <canvas>。
SAMPLE_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head><meta charset="utf-8" /><title>任务看板</title>
<style>body{display:grid}</style></head>
<body>
  <h1>团队任务看板</h1>
  <button id="add">新增任务</button>
  <script>document.getElementById('add').addEventListener('click', function () {});</script>
</body>
</html>"""


async def cleanup(user_id: str) -> None:
    async with db_manager.session() as session:
        await session.execute(delete(Test_cases).where(Test_cases.user_id == user_id))
        await session.execute(delete(Test_runs).where(Test_runs.user_id == user_id))
        await session.execute(delete(Projects).where(Projects.user_id == user_id))
        await session.commit()


async def seed_project() -> int:
    """直接落库一个已完成项目，避免验证过程消耗生成额度或触发模型。"""
    async with db_manager.session() as session:
        project = Projects(
            user_id=OWNER,
            name="验证用任务看板",
            prompt="做一个团队任务看板，支持新增任务",
            status="succeeded",
            current_stage="deploying",
            template_key="",
            latest_version=1,
            artifact_key=ARTIFACT_KEY,
            spec_json=json.dumps(
                {
                    "app_name": "task-board",
                    "display_name": "任务看板",
                    "pages": ["首页"],
                    "entities": ["任务"],
                    "stack": ["HTML", "JavaScript"],
                    "files": 1,
                    "component_tree": ["TaskBoard"],
                    "notes": "",
                    "entry": "index.html",
                },
                ensure_ascii=False,
            ),
            plan_json=json.dumps({"files": [{"path": "index.html"}], "component_tree": ["TaskBoard"]}),
        )
        session.add(project)
        await session.commit()
        return project.id


async def count_rows(model, project_id: int) -> int:
    async with db_manager.session() as session:
        return await session.scalar(
            select(func.count()).select_from(model).where(model.project_id == project_id)
        ) or 0


async def main() -> None:
    await cleanup(OWNER)
    await cleanup(OTHER_USER)
    await generation_artifacts.upload_html(ARTIFACT_KEY, SAMPLE_HTML)
    print("STEP0 artifact uploaded:", ARTIFACT_KEY, flush=True)

    project_id = await seed_project()
    print("STEP1 project seeded:", project_id, flush=True)

    # 1) 无产物的项目必须拒绝生成与执行，不能给出假成功。
    async with db_manager.session() as session:
        blank = Projects(user_id=OTHER_USER, name="无产物", prompt="空项目", status="running", artifact_key="")
        session.add(blank)
        await session.commit()
        blank_id = blank.id
    for call, label in (
        (lambda s: test_suite.generate_cases(s, OTHER_USER, blank_id), "generate"),
        (lambda s: test_suite.execute_run(s, OTHER_USER, blank_id), "execute"),
    ):
        try:
            async with db_manager.session() as session:
                await call(session)
            raise AssertionError(f"{label} 在无产物项目上未拒绝")
        except test_suite.ArtifactNotReady:
            print(f"STEP2 {label} rejected without artifact: OK", flush=True)

    # 2) 手工用例先覆盖确定性断言，再补一条必然失败的用例验证失败会如实记下。
    async with db_manager.session() as session:
        hit = await test_suite.create_case(
            session,
            OWNER,
            project_id,
            {
                "title": "页面包含主标题",
                "case_type": "structure",
                "assertion": "<h1",
                "expected": "存在 h1 主标题",
                "steps": "打开应用，确认顶部标题",
            },
        )
        miss = await test_suite.create_case(
            session,
            OWNER,
            project_id,
            {"title": "存在画布元素", "case_type": "structure", "assertion": "<canvas", "expected": "存在 canvas"},
        )
        paused = await test_suite.create_case(
            session,
            OWNER,
            project_id,
            {"title": "存在交互按钮", "case_type": "behavior", "assertion": "<button", "expected": "存在按钮"},
        )
        await test_suite.update_case(session, OWNER, paused["id"], {"case_state": "disabled"})
    print("STEP3 cases ready:", hit["id"], miss["id"], paused["id"], flush=True)

    # 3) 执行：停用用例不参与；命中通过，未命中失败并带原因。
    async with db_manager.session() as session:
        run = await test_suite.execute_run(session, OWNER, project_id)
    print("STEP4 run:", run["status"], f"{run['passed']}/{run['total']}", f"{run['duration_ms']}ms", flush=True)
    assert run["total"] == 2, f"停用用例应被排除，实际执行 {run['total']} 条"
    assert run["passed"] == 1 and run["failed"] == 1, "通过/失败统计与产物不符"
    assert run["status"] == "failed", "存在失败用例时运行状态应为 failed"
    assert run["duration_ms"] >= 0 and run["created_at"], "运行记录缺少耗时或时间"
    failed_result = next(r for r in run["results"] if not r["passed"])
    assert failed_result["case_id"] == miss["id"] and "<canvas" in failed_result["detail"], "失败原因未如实记录"
    assert any(r["passed"] for r in run["results"]), "命中断言的用例应通过"

    # 4) 启用全部用例后再执行一次，历史需按时间倒序返回两次运行。
    async with db_manager.session() as session:
        await test_suite.update_case(session, OWNER, paused["id"], {"case_state": "active"})
        second = await test_suite.execute_run(session, OWNER, project_id)
        suite = await test_suite.load_suite(session, OWNER, project_id)
    assert second["total"] == 3 and second["passed"] == 2, "启用用例后应执行全部三条"
    assert [item["id"] for item in suite["runs"]][0] == second["id"], "运行历史应按最新在前返回"
    assert len(suite["runs"]) == 2 and suite["latest_run"]["id"] == second["id"], "最近一次运行取错"
    assert len(suite["cases"]) == 3, "用例列表数量不符"
    assert suite["artifact_ready"] is True, "产物就绪标记错误"
    print("STEP5 history:", [item["id"] for item in suite["runs"]], "cases:", len(suite["cases"]), flush=True)

    # 5) 跨用户隔离：其他账号看不到该项目，运行记录也不可读。
    async with db_manager.session() as session:
        try:
            await test_suite.load_suite(session, OTHER_USER, project_id)
            raise AssertionError("跨用户读取项目未被拒绝")
        except ProjectNotFound:
            print("STEP6 cross-user project access rejected: OK", flush=True)
        try:
            await test_suite.get_run(session, OTHER_USER, second["id"])
            raise AssertionError("跨用户读取运行记录未被拒绝")
        except test_suite.CaseNotFound:
            print("STEP7 cross-user run access rejected: OK", flush=True)

    # 6) 删除用例：单条删除后运行记录保留，作为历史证据不受影响。
    async with db_manager.session() as session:
        await test_suite.delete_case(session, OWNER, miss["id"])
        suite_after_delete = await test_suite.load_suite(session, OWNER, project_id)
    assert len(suite_after_delete["cases"]) == 2, "删除用例未生效"
    assert len(suite_after_delete["runs"]) == 2, "删除用例不应影响已完成的运行历史"
    print("STEP8 case deleted, runs kept:", len(suite_after_delete["runs"]), flush=True)

    # 7) 模型生成用例：真调用 claude-opus-5，模型不可用时明确跳过。
    try:
        async with db_manager.session() as session:
            generated = await test_suite.generate_cases(session, OWNER, project_id)
        auto_cases = [c for c in generated["cases"] if c["source"] == "auto"]
        manual_cases = [c for c in generated["cases"] if c["source"] == "manual"]
        assert len(auto_cases) >= 6, f"自动用例数量不足：{len(auto_cases)}"
        assert len(manual_cases) == 2, "生成自动用例不应影响手工用例"
        async with db_manager.session() as session:
            auto_run = await test_suite.execute_run(session, OWNER, project_id)
        print(
            "STEP9 model cases:",
            len(auto_cases),
            "auto run:",
            f"{auto_run['passed']}/{auto_run['total']}",
            flush=True,
        )
        print("RESULT test suite: OK (with real model generation)", flush=True)
    except GenerationAIError as exc:
        print(f"STEP9 model case generation unavailable: {str(exc)[:90]}", flush=True)
        print("RESULT test suite: OK (deterministic execution verified, model generation skipped)", flush=True)

    # 8) 项目删除时清理测试数据。
    async with db_manager.session() as session:
        await test_suite.purge_project_tests(session, OWNER, project_id)
        await session.commit()
    assert await count_rows(Test_cases, project_id) == 0, "项目删除后仍残留测试用例"
    assert await count_rows(Test_runs, project_id) == 0, "项目删除后仍残留运行记录"
    print("STEP10 purge after project delete: OK", flush=True)

    await cleanup(OWNER)
    await cleanup(OTHER_USER)
    print("CLEANUP_DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
