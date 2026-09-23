"""502 修复验证：HTTP 层实测生成接口的请求耗时与持久化。

背景：`/api/v1/generation/projects` 曾把真实模型调用内联在请求里（单次最长 180 秒），
超过 Cloudflare 约 100 秒的网关时限，用户看到的是 502。修复后阶段执行交给后台工作器，
请求只做数据库读写与限时等待，因此每个请求都必须远低于网关时限。

本脚本绕过平台认证（覆盖 `get_current_user` 依赖），直接对 ASGI 应用发真实 HTTP 请求，
逐个打印创建与轮询的耗时，最后断言：
- 每个请求耗时都低于网关安全线；
- 创建后项目确实落库（排除「额度被扣但没有项目」的历史现象）；
- 并发轮询不会产生 5xx。
"""

import asyncio
import sys
import time
from types import SimpleNamespace

sys.path.insert(0, "/workspace/app/backend")

import httpx
from sqlalchemy import delete, func, select

from core.database import db_manager
from dependencies.auth import get_current_user
from main import app
from models.build_tasks import Build_tasks
from models.project_versions import Project_versions
from models.projects import Projects
from models.usage_quotas import Usage_quotas

TEST_USER = "verify-gateway-user"
PROMPT = "做一个团队任务协作应用，支持添加任务和按状态统计"

# Cloudflare 的网关时限约 100 秒；这里保守地要求每个请求都在 25 秒内返回。
GATEWAY_SAFE_SECONDS = 25.0
MAX_POLLS = 20


async def cleanup():
    async with db_manager.session() as session:
        for model in (Build_tasks, Project_versions):
            await session.execute(delete(model).where(model.user_id == TEST_USER))
        await session.execute(delete(Projects).where(Projects.user_id == TEST_USER))
        await session.execute(delete(Usage_quotas).where(Usage_quotas.user_id == TEST_USER))
        await session.commit()


async def project_rows() -> int:
    async with db_manager.session() as session:
        return await session.scalar(
            select(func.count()).select_from(Projects).where(Projects.user_id == TEST_USER)
        ) or 0


async def main():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=TEST_USER)
    await cleanup()

    slowest = 0.0
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://localhost", timeout=120) as client:
        started = time.perf_counter()
        response = await client.post("/api/v1/generation/projects", json={"prompt": PROMPT, "template_key": ""})
        elapsed = time.perf_counter() - started
        slowest = max(slowest, elapsed)
        print(f"POST /projects -> {response.status_code} in {elapsed:.2f}s", flush=True)
        assert response.status_code == 201, response.text[:300]
        payload = response.json()
        project_id = payload["project"]["id"]
        print("  project", project_id, "status:", payload["project"]["status"], flush=True)

        # 创建即落库：额度被扣但没有项目行的历史现象必须消失。
        assert await project_rows() == 1, "创建后项目未落库"

        final_status = payload["project"]["status"]
        for attempt in range(1, MAX_POLLS + 1):
            if final_status in ("succeeded", "failed"):
                break
            started = time.perf_counter()
            response = await client.get(f"/api/v1/generation/projects/{project_id}")
            elapsed = time.perf_counter() - started
            slowest = max(slowest, elapsed)
            assert response.status_code == 200, response.text[:300]
            final_status = response.json()["project"]["status"]
            stages = {t["stage"]: t["stage_state"] for t in response.json()["stages"]}
            print(f"GET poll {attempt} -> {response.status_code} in {elapsed:.2f}s status: {final_status}", stages, flush=True)
            await asyncio.sleep(1)

        # 并发轮询：多端同时刷新不应出现 5xx，也不应重复执行阶段。
        started = time.perf_counter()
        burst = await asyncio.gather(
            *[client.get(f"/api/v1/generation/projects/{project_id}") for _ in range(4)]
        )
        burst_elapsed = time.perf_counter() - started
        slowest = max(slowest, burst_elapsed)
        codes = [item.status_code for item in burst]
        print(f"burst 4x GET -> {codes} in {burst_elapsed:.2f}s", flush=True)
        assert all(code == 200 for code in codes), f"并发轮询出现异常状态：{codes}"

    async with db_manager.session() as session:
        row = await session.scalar(select(Projects).where(Projects.id == project_id))
        tasks = list(
            await session.scalars(select(Build_tasks).where(Build_tasks.project_id == project_id))
        )
        print("FINAL status:", row.status, "current_stage:", row.current_stage, flush=True)
        print("FINAL artifact_key:", repr(row.artifact_key), flush=True)
        for task in tasks:
            print(f"  stage {task.stage}: {task.stage_state} {task.error_message[:90]}", flush=True)
        quota_used = await session.scalar(
            select(Usage_quotas.used).where(Usage_quotas.user_id == TEST_USER)
        )
        print("FINAL quota used:", quota_used, flush=True)

    app.dependency_overrides.clear()
    await cleanup()

    print("SLOWEST request:", round(slowest, 2), "s (gateway safe line:", GATEWAY_SAFE_SECONDS, "s)", flush=True)
    assert slowest < GATEWAY_SAFE_SECONDS, "存在逼近网关时限的请求"
    print("RESULT gateway timeouts: OK (no request near the gateway limit)", flush=True)


if __name__ == "__main__":
    asyncio.run(main())
