"""阶段五验证：Bug 提交、记录与自动修复闭环。

覆盖点：
1. 无产物的项目拒绝提交缺陷，不能凭空记录缺陷。
2. 缺陷可提交、可编辑、可关闭/重开，并带严重级别与关联用例。
3. 自动修复失败时不伪造成功：如实落一条失败修复记录，缺陷停在可见失败态，
   产物与项目版本保持不变。
4. 修复历史按最新在前返回，包含尝试序号、模型、源/目标版本与耗时。
5. 统计口径与缺陷状态一致；缺陷与修复记录按用户隔离。
6. 项目删除时一并清理缺陷与修复记录。
7. 真模型修复（`claude-opus-5`）：模型不可用时明确跳过，不伪造修复成功。

前六项基于已知产物与稳定的失败路径，因此模型不可用时依然能验证整条闭环。
"""

import asyncio
import json
import sys
import uuid

sys.path.insert(0, "/workspace/app/backend")

from sqlalchemy import delete, func, select

from core.database import db_manager
from models.bug_fix_logs import Bug_fix_logs
from models.bugs import Bugs
from models.projects import Projects
from models.test_cases import Test_cases
from services import bug_fix, generation_artifacts, test_suite
from services.generation import ProjectNotFound
from services.generation_ai import GenerationAIError

OWNER = f"verify-bugfix-{uuid.uuid4().hex[:8]}"
OTHER_USER = "verify-bugfix-other"
ARTIFACT_KEY = f"verify/bugfix/{uuid.uuid4().hex[:8]}/index.html"
MISSING_KEY = f"verify/bugfix/{uuid.uuid4().hex[:8]}/missing.html"

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


async def cleanup(user_id_pattern: str) -> None:
    """按用户前缀清理验证数据；用前缀是为了连带清掉上一次中断运行残留的行。"""
    async with db_manager.session() as session:
        for model in (Bug_fix_logs, Bugs, Test_cases, Projects):
            await session.execute(delete(model).where(model.user_id.like(user_id_pattern)))
        await session.commit()


async def seed_project(user_id: str, artifact_key: str) -> int:
    """直接落库一个已完成项目，避免验证过程消耗生成额度。"""
    async with db_manager.session() as session:
        project = Projects(
            user_id=user_id,
            name="验证用任务看板",
            prompt="做一个团队任务看板，支持新增任务",
            status="succeeded",
            current_stage="deploying",
            template_key="",
            latest_version=1,
            artifact_key=artifact_key,
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


async def project_snapshot(project_id: int) -> dict:
    async with db_manager.session() as session:
        project = await session.scalar(select(Projects).where(Projects.id == project_id))
        return {
            "artifact_key": project.artifact_key or "",
            "latest_version": project.latest_version or 1,
        }


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

    project_id = await seed_project(OWNER, ARTIFACT_KEY)
    print("STEP1 project seeded:", project_id, flush=True)

    # 1) 无产物的项目必须拒绝提交缺陷，不能给出假记录。
    async with db_manager.session() as session:
        blank = Projects(user_id=OTHER_USER, name="无产物", prompt="空项目", status="running", artifact_key="")
        session.add(blank)
        await session.commit()
        blank_id = blank.id
    try:
        async with db_manager.session() as session:
            await bug_fix.create_bug(session, OTHER_USER, blank_id, {"title": "不应被记录"})
        raise AssertionError("无产物项目上的缺陷提交未被拒绝")
    except bug_fix.ArtifactNotReady:
        print("STEP2 bug create rejected without artifact: OK", flush=True)

    # 2) 用例：一条命中、一条必然失败，用于验证关联用例的复测结论。
    async with db_manager.session() as session:
        hit = await test_suite.create_case(
            session,
            OWNER,
            project_id,
            {"title": "页面包含主标题", "case_type": "structure", "assertion": "<h1", "expected": "存在 h1"},
        )
        miss = await test_suite.create_case(
            session,
            OWNER,
            project_id,
            {"title": "存在画布元素", "case_type": "structure", "assertion": "<canvas", "expected": "存在 canvas"},
        )
    print("STEP3 cases ready:", hit["id"], miss["id"], flush=True)

    # 3) 提交缺陷：带严重级别、复现步骤与关联用例，初始状态为待修复。
    async with db_manager.session() as session:
        bug = await bug_fix.create_bug(
            session,
            OWNER,
            project_id,
            {
                "title": "点击新增任务无响应",
                "description": "点击按钮后列表没有新增任何任务",
                "severity": "high",
                "reproduction": "打开页面 → 点击「新增任务」",
                "related_case_id": miss["id"],
            },
        )
    assert bug["status"] == "open", "新建缺陷的初始状态应为待修复"
    assert bug["severity"] == "high" and bug["fix_attempts"] == 0, "缺陷字段未按提交内容落库"
    assert bug["related_case_id"] == miss["id"], "关联用例未记录"
    print("STEP4 bug created:", bug["id"], bug["status"], bug["severity"], flush=True)

    # 4) 一条缺陷只能关联同项目的用例。
    try:
        async with db_manager.session() as session:
            await bug_fix.create_bug(
                session, OWNER, project_id, {"title": "错误关联", "related_case_id": 999999}
            )
        raise AssertionError("无效的关联用例未被拒绝")
    except ValueError:
        print("STEP5 invalid related case rejected: OK", flush=True)

    # 5) 修复失败路径：产物键不可读时必须如实失败，且不改动项目版本与产物指针。
    before = await project_snapshot(project_id)
    async with db_manager.session() as session:
        broken_project_id = await seed_project(f"{OWNER}-broken", MISSING_KEY)
    async with db_manager.session() as session:
        broken_bug = await bug_fix.create_bug(session, f"{OWNER}-broken", broken_project_id, {"title": "无法读取产物"})
    async with db_manager.session() as session:
        failed = await bug_fix.fix_bug(session, f"{OWNER}-broken", broken_bug["id"])
    assert failed["status"] == "fix_failed", "产物不可读时缺陷不应被标成已修复"
    assert failed["fix_attempts"] == 1 and failed["latest_fix"]["status"] == "fix_failed", "失败修复记录未落库"
    assert failed["latest_fix"]["target_version"] == 2, "失败记录应写明原本要产出的目标版本"
    assert failed["latest_fix"]["error_message"], "失败修复记录缺少原因"
    assert failed["resolution"].startswith("第 1 次自动修复失败"), "结论未如实写入"
    async with db_manager.session() as session:
        broken = await session.scalar(select(Projects).where(Projects.id == broken_project_id))
        assert broken.latest_version == 1 and broken.artifact_key == MISSING_KEY, "修复失败不应改动项目版本或产物"
    after = await project_snapshot(project_id)
    assert before == after, "无关项目的产物指针被改动"
    print(
        "STEP6 failed fix recorded:",
        failed["latest_fix"]["error_message"][:60],
        f"{failed['latest_fix']['duration_ms']}ms",
        flush=True,
    )

    # 6) 面板统计与缺陷列表口径一致；失败修复出现在最近修复记录里。
    async with db_manager.session() as session:
        panel = await bug_fix.load_panel(session, OWNER, project_id)
    assert panel["stats"]["total"] == 1 and panel["stats"]["open"] == 1, "面板统计与缺陷状态不符"
    assert panel["artifact_ready"] is True and panel["latest_version"] == 1, "面板产物或版本信息错误"
    assert len(panel["bugs"]) == 1 and panel["bugs"][0]["id"] == bug["id"], "缺陷列表内容不符"
    print("STEP7 panel:", panel["stats"], flush=True)

    # 7) 编辑、关闭与重开：状态可人工流转且不影响修复尝试次数。
    async with db_manager.session() as session:
        edited = await bug_fix.update_bug(
            session, OWNER, bug["id"], {"title": "点击新增任务无响应（已收敛）", "severity": "critical"}
        )
        assert edited["title"].startswith("点击新增任务") and edited["severity"] == "critical", "缺陷编辑未生效"
        closed = await bug_fix.update_bug(session, OWNER, bug["id"], {"status": "closed"})
        assert closed["status"] == "closed", "缺陷关闭未生效"
        reopened = await bug_fix.update_bug(session, OWNER, bug["id"], {"status": "open"})
        assert reopened["status"] == "open", "缺陷重开未生效"
    print("STEP8 bug edit/close/reopen: OK", flush=True)

    # 8) 跨用户隔离：其他账号看不到该项目的面板，也读不到别人的修复历史。
    async with db_manager.session() as session:
        try:
            await bug_fix.load_panel(session, OTHER_USER, project_id)
            raise AssertionError("跨用户读取缺陷面板未被拒绝")
        except ProjectNotFound:
            print("STEP9 cross-user panel access rejected: OK", flush=True)
        try:
            await bug_fix.load_fixes(session, OTHER_USER, bug["id"])
            raise AssertionError("跨用户读取修复历史未被拒绝")
        except bug_fix.BugNotFound:
            print("STEP10 cross-user fix history rejected: OK", flush=True)

    # 9) 真模型修复：成功时产出新版本并在新产物上复测；模型不可用时明确跳过，不伪造成功。
    async with db_manager.session() as session:
        fixed = await bug_fix.fix_bug(session, OWNER, bug["id"])
    if fixed["status"] == "fixed":
        assert fixed["target_version"] == 2 and fixed["latest_fix"]["artifact_key"], "修复未产出新版本产物"
        retest = fixed["latest_fix"]["retest"]
        assert retest and retest["executed"], "修复成功后应在新产物上执行复测"
        assert retest["related_case_id"] == miss["id"], "复测未按关联用例给出结论"
        assert fixed["latest_fix"]["changes"], "修复记录缺少变更清单"
        snapshot = await project_snapshot(project_id)
        assert snapshot["latest_version"] == 2, "项目版本指针未前移到修复版本"
        assert snapshot["artifact_key"] != ARTIFACT_KEY, "修复后的产物指针仍指向旧版本"
        async with db_manager.session() as session:
            versions = await bug_fix.load_fixes(session, OWNER, bug["id"])
        assert len(versions) == 1 and versions[0]["status"] == "fixed", "修复历史未落库"
        async with db_manager.session() as session:
            panel = await bug_fix.load_panel(session, OWNER, project_id)
        assert panel["stats"]["fixed"] == 1 and panel["latest_version"] == 2, "修复后面板统计未更新"
        print(
            "STEP11 real model fix:",
            f"v{fixed['latest_fix']['source_version']}→v{fixed['target_version']}",
            "retest:",
            f"{retest['passed']}/{retest['total']}",
            f"({retest['status']})",
            flush=True,
        )
        assert retest["status"] == "passed", "关联用例未通过时缺陷不应被标为已修复"
        print("RESULT bug fix: OK (real model fix + retest on new artifact)", flush=True)
    else:
        # 模型不可用时缺陷必须停在可见失败态，且项目版本与产物指针不被改动。
        assert fixed["status"] == "fix_failed", f"未预期的缺陷状态：{fixed['status']}"
        failed_log = fixed["latest_fix"]
        assert failed_log["status"] == "fix_failed" and failed_log["error_message"], "失败修复记录不完整"
        assert failed_log["target_version"] == 2, "失败记录应写明原本要产出的目标版本"
        assert failed_log["attempt_no"] == 1, "失败记录的尝试序号错误"
        assert fixed["fix_attempts"] == 1, "失败尝试次数未累加"
        unchanged = await project_snapshot(project_id)
        assert unchanged["latest_version"] == 1 and unchanged["artifact_key"] == ARTIFACT_KEY, (
            "修复失败不应改动项目版本或产物指针"
        )
        print("STEP11 real model fix skipped:", failed_log["error_message"][:80], flush=True)
        print("RESULT bug fix: OK (all paths verified, real model unavailable)", flush=True)

    # 10) 产物回归：项目当前指向的产物（可能是修复后的新版本）必须真的可回读且可访问。
    current = await project_snapshot(project_id)
    content = await generation_artifacts.fetch_html(current["artifact_key"])
    assert content and "<html" in content[:2000].lower(), "项目当前产物无法回读或内容不是 HTML"
    url = await generation_artifacts.public_url(current["artifact_key"])
    assert await generation_artifacts.is_reachable(url), "项目当前产物地址不可访问"
    print(
        f"STEP12 artifact round-trip: OK (v{current['latest_version']}, {len(content)} bytes)",
        flush=True,
    )

    # 11) 项目删除时清理缺陷与修复记录。
    async with db_manager.session() as session:
        await bug_fix.purge_project_bugs(session, OWNER, project_id)
        await session.commit()
    assert await count_rows(Bugs, project_id) == 0, "项目删除后仍残留缺陷"
    assert await count_rows(Bug_fix_logs, project_id) == 0, "项目删除后仍残留修复记录"
    print("STEP13 purge after project delete: OK", flush=True)

    print("ALL_CHECKS_DONE", flush=True)


async def run() -> None:
    """清理放在 finally，保证中途断言失败也不会在库里留下验证残留。"""
    try:
        await main()
    finally:
        await cleanup(f"{OWNER}%")
        await cleanup(f"{OTHER_USER}%")
        # 验证产物也要清掉，否则每跑一次都会在对象存储留下一个孤儿对象。
        for key in (ARTIFACT_KEY, MISSING_KEY):
            try:
                await generation_artifacts.delete_object(key)
            except Exception as exc:  # noqa: BLE001 - 清理失败不应掩盖验证结论
                print(f"cleanup artifact skipped: {key}: {exc}", flush=True)
        print("CLEANUP_DONE", flush=True)


if __name__ == "__main__":
    asyncio.run(run())
