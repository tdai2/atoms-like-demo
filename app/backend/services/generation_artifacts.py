"""生成产物的对象存储读写。

产物（生成出的单文件应用）不入库，只把对象键与访问地址写回业务表：
- 上传：取预签名上传地址后直接 PUT 内容。
- 校验/测试：按对象键取下载地址后回读真实内容。
- 发布：把下载地址写入 `projects.preview_url`，供预览窗以 iframe 访问。
"""

import logging
from typing import Optional

import httpx

from schemas.storage import FileUpDownRequest
from services.storage import StorageService

try:
    from core.telemetry import observe_external_http
except Exception:  # noqa: BLE001 - 诊断能力在部分模板版本中可能缺失
    async def observe_external_http(operation):
        return await operation

logger = logging.getLogger(__name__)

BUCKET_NAME = "generation-artifacts"
HTML_CONTENT_TYPE = "text/html; charset=utf-8"


class ArtifactError(Exception):
    """产物读写失败。"""


def artifact_key(project_id: int, version: int) -> str:
    """项目产物在对象存储中的键，按项目与版本隔离。"""
    return f"projects/{project_id}/v{version}/index.html"


async def upload_html(object_key: str, html: str) -> None:
    """把生成出的 HTML 上传到对象存储。"""
    service = StorageService()
    request = FileUpDownRequest(bucket_name=BUCKET_NAME, object_key=object_key)
    upload = await service.create_upload_url(request)
    if not upload.upload_url:
        raise ArtifactError("对象存储未返回上传地址")
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await observe_external_http(
                client.put(
                    upload.upload_url,
                    content=html.encode("utf-8"),
                    headers={"Content-Type": HTML_CONTENT_TYPE},
                )
            )
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise ArtifactError(f"产物上传失败：{exc}") from exc
    logger.info("artifact uploaded: %s", object_key)


async def fetch_html(object_key: str) -> Optional[str]:
    """按对象键回读产物内容，读取失败时返回 None。"""
    service = StorageService()
    request = FileUpDownRequest(bucket_name=BUCKET_NAME, object_key=object_key)
    download = await service.create_download_url(request)
    if not download.download_url:
        raise ArtifactError("对象存储未返回下载地址")
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await observe_external_http(client.get(download.download_url))
            response.raise_for_status()
            return response.text
    except httpx.HTTPError as exc:
        logger.warning("artifact fetch failed: %s", exc)
        return None


async def public_url(object_key: str) -> str:
    """可访问的产物地址，写入 `projects.preview_url`。"""
    service = StorageService()
    request = FileUpDownRequest(bucket_name=BUCKET_NAME, object_key=object_key)
    download = await service.create_download_url(request)
    if not download.download_url:
        raise ArtifactError("对象存储未返回访问地址")
    return download.download_url


async def is_reachable(url: str) -> bool:
    """发布前确认产物地址真的可访问，避免写入失效链接。"""
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await observe_external_http(client.get(url))
            return response.status_code == 200 and "<html" in response.text[:2000].lower()
    except httpx.HTTPError as exc:
        logger.warning("preview url unreachable: %s", exc)
        return False
