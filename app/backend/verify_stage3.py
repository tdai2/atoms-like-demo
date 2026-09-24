"""阶段三真实链路验证：对象存储可用性 + 真实模型调用 + 预览地址可达性。"""

import asyncio
import sys

sys.path.insert(0, "/workspace/app/backend")

BUCKET = "generation-artifacts"
KEY = "verify/stage3/healthcheck.html"
SAMPLE = (
    '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><title>健康检查</title></head>'
    "<body><h1>阶段三产物校验</h1><button>测试按钮</button>"
    "<script>document.addEventListener('click',function(){})</script></body></html>"
)


async def check_storage():
    import httpx

    from schemas.storage import FileUpDownRequest, ObjectRequest
    from services.storage import StorageService

    service = StorageService()
    buckets = await service.list_buckets()
    names = [b.bucket_name for b in buckets.buckets]
    print("STEP1 buckets:", names, flush=True)

    upload = await service.create_upload_url(FileUpDownRequest(bucket_name=BUCKET, object_key=KEY))
    print("STEP2 upload_url:", bool(upload.upload_url), flush=True)

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.put(
            upload.upload_url,
            content=SAMPLE.encode("utf-8"),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )
        print("STEP3 put status:", response.status_code, flush=True)
        response.raise_for_status()

    info = await service.get_object_info(ObjectRequest(bucket_name=BUCKET, object_key=KEY))
    print("STEP4 object size:", info.size, flush=True)
    return True


async def check_artifacts():
    from services import generation_artifacts

    html = await generation_artifacts.fetch_html(KEY)
    print("STEP5 fetch_html ok:", bool(html), "len:", len(html or ""), flush=True)

    url = await generation_artifacts.public_url(KEY)
    print("STEP6 public_url:", url[:120], flush=True)

    reachable = await generation_artifacts.is_reachable(url)
    print("STEP7 reachable:", reachable, flush=True)
    return bool(html) and reachable


async def check_ai():
    from services import generation_ai

    spec = await generation_ai.parse_requirements("做一个团队任务协作应用，支持添加任务和按状态统计")
    print("STEP8 parse ok:", spec["app_name"], spec["display_name"], spec["pages"], flush=True)

    plan = await generation_ai.plan_architecture("做一个团队任务协作应用", spec)
    print("STEP9 plan files:", [f["path"] for f in plan["files"]], flush=True)

    result = await generation_ai.write_application("做一个团队任务协作应用，支持添加任务和按状态统计", spec, plan)
    print("STEP10 code files:", result["files"], "html len:", len(result["content"]), flush=True)
    print("STEP11 has html tag:", "<html" in result["content"].lower(), flush=True)
    return True


async def main():
    storage_ok = await check_storage()
    artifacts_ok = await check_artifacts()
    ai_ok = await check_ai()
    print("RESULT storage:", storage_ok, "artifacts:", artifacts_ok, "ai:", ai_ok, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
