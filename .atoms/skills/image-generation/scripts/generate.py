#!/usr/bin/env python3
"""
Generate and edit images through OneAPI or Gemini native image APIs.
"""

import asyncio
import base64
import io
import json
import mimetypes
from enum import Enum
from io import BytesIO
from pathlib import Path
from typing import Awaitable, Optional, Union

from urllib.parse import urlparse

from aiohttp import FormData
from PIL import Image
from pydantic import BaseModel, Field
from tenacity import (
    AsyncRetrying,
    retry_if_exception,
    stop_after_attempt,
    wait_random_exponential,
)

from metagpt.config2 import Config
from metagpt.logs import logger
from metagpt.utils.ahttp_client import aget, aget_bytes, apost
from metagpt.utils.bg_tool import BgTaskResult
from metagpt.utils.common import normalize_request_filename, validate_allowed_model
from metagpt.utils.media_task_retry import (
    annotate_resubmit_result,
    is_rate_limited_message,
    poll_task_with_resubmit,
)
from metagpt.utils.report import ArtifactsReporter, EditorReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script
from metagpt.utils.workspace_media import archive_cdn_media, available_filename, is_overview_asset_context, resolve_workspace_root

OPENAI_TRANSPARENT_BACKGROUND_MODEL = "gpt-image-1.5"
NEWAPI_HOST = "newapi.deepwisdom.ai"

# Maximum number of images that can be submitted in a single call
MAX_IMAGE_BATCH_SIZE = 50


class ImageChannel(str, Enum):
    NEWAPI_GEMINI = "newapi_gemini"
    NEWAPI_NO_RESPONSE_FORMAT = "newapi_no_response_format"
    ONEAPI = "oneapi"


class ImageGenerationRequest(BaseModel):
    """A single image generation request."""

    description: str = Field(..., description="Detailed description of the image to generate")
    filename: str = Field(..., description='Target filename (e.g., "hero-image.jpg", "logo.png")')
    style: str = Field(
        default="photorealistic",
        description="Image style (photorealistic, cartoon, sketch, watercolor, minimalist, 3d)",
    )
    size: str = Field(
        default="1024x1024",
        description="Image size (e.g., 1024x1024, 1024x576, 1024x768). If omitted, defaults to 1024x1024.",
    )
    model: Optional[str] = Field(
        default=None,
        description="Image model name. If not specified, uses the configured default.",
    )
    image: Optional[str] = Field(
        default=None,
        description="Optional reference image for image-to-image editing (absolute local path or http(s) URL).",
    )
    background: Optional[str] = Field(
        default=None,
        description=(
            "Optional background mode. Use 'transparent' with OpenAI gpt-image models to request a transparent "
            "background. Unsupported or missing filename extensions are replaced with .png."
        ),
    )


class ImageCreator(BaseModel):
    """Tool for text-to-image and image-to-image creation."""

    api_key: str = Field(default_factory=lambda: Config.default().multimodal.image_generation.api_key)
    base_url: str = Field(default_factory=lambda: Config.default().multimodal.image_generation.base_url)
    model: str = Field(default_factory=lambda: Config.default().multimodal.image_generation.model)
    allowed_models: list[str] = Field(default_factory=lambda: Config.default().multimodal.image_generation.allowed_models)

    subdir_path: Optional[str] = Field(default="public/assets")

    # working directory
    working_dir: Optional[str] = Field(default=None, exclude=True)
    resource: EditorReporter = Field(default_factory=EditorReporter)
    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    # Async task polling parameters
    poll_interval_seconds: float = Field(default=3.0, description="Polling interval (seconds)")
    max_poll_seconds: int = Field(default=600, description="Maximum polling wait time (seconds)")
    max_task_retries: int = Field(
        default=3, description="Max resubmissions when a task fails due to upstream rate limiting"
    )

    async def generate_image(
        self,
        description: str,
        filename: str,
        style: str = "photorealistic",
        size: str = "1024x1024",
        model: Optional[str] = None,
        image: Optional[str] = None,
        background: Optional[str] = None,
    ) -> dict:
        """
        Generate an image using AI. If a reference image is provided, the tool performs image editing (img2img).
        The result is hosted on CDN when available and displayed automatically.

        Args:
            description: Detailed description of the image to generate
            filename: Target filename (e.g., "hero-image.jpg", "logo.png")
            style: Image style (photorealistic, cartoon, sketch, watercolor, minimalist, 3d)
            size: Image size (1024x1024, 1024x576, 1024x768)
            model: Optional image model override for this request.
            image: Optional reference image for image-to-image editing. Supports absolute local
                file paths and http(s) URLs.
            background: Optional background mode. Use "transparent" with OpenAI gpt-image
                models to request a transparent background.
        Returns:
            dict: Result with status and url

        Raises:
            RuntimeError: If working_dir not set or image generation fails
        """
        if not self.working_dir:
            raise RuntimeError("working_dir not set for ImageCreator")

        try:
            requested_model = model or self.model
            resolved_filename, request_options, effective_model = self._resolve_oneapi_request_options(
                filename, background, requested_model
            )
            effective_model = validate_allowed_model(effective_model, self.allowed_models, "image generation")
            request_filename = normalize_request_filename(resolved_filename)
            enhanced_prompt = self._build_enhanced_prompt(description, style, has_reference_image=bool(image))
            logger.info(f"Start creating the image. The prompt is: {enhanced_prompt}...")

            channel = self._resolve_image_channel(effective_model)
            if channel == ImageChannel.NEWAPI_GEMINI:
                image_bytes = await self._generate_via_newapi(
                    enhanced_prompt, request_filename=request_filename, image=image, model=effective_model
                )
                return await self._save_image_and_return_result(image_bytes, resolved_filename, description, style)

            # A local image service (e.g. vLLM-Omni) needs response_format=b64_json;
            # ONEAPI wants url; newapi-openai omits it entirely.
            if self._is_local_image_service(effective_model):
                response_format = "b64_json"
            elif channel == ImageChannel.ONEAPI:
                response_format = "url"
            else:
                response_format = None

            result = await self._generate_via_openai_compatible(
                enhanced_prompt,
                size=size,
                image=image,
                model=effective_model,
                request_options=request_options,
                request_filename=request_filename,
                response_format=response_format,
            )

            if isinstance(result, str):
                return await self._build_url_result(result, resolved_filename, description, style)

            logger.info("Image API returned bytes instead of URL, saving locally")
            return await self._save_image_and_return_result(result, resolved_filename, description, style)

        except Exception as e:
            error_msg = f"Image creation failed: {str(e)}"
            logger.error(error_msg)
            raise RuntimeError(error_msg) from e

    async def generate_images_with_manifest(self, images: list[dict], manifest_path: str, **kwargs: object) -> BgTaskResult:
        """generate_images + manifest lifecycle management.

        Wraps generate_images with manifest write/update logic without touching
        the core generation flow. Manifest is written immediately after submit,
        and updated after poll completion via a wrapped poll coroutine.
        """
        if images and len(images) > MAX_IMAGE_BATCH_SIZE:
            return await self.generate_images(images=images, **kwargs)

        # Deduplicate filenames before generation: check manifest (running/success)
        # then resolve collisions within the batch. Failed entries are not retained
        # in the manifest so their filenames remain available for retry.
        occupied: set[str] = set()
        if manifest_path:
            manifest_file = Path(manifest_path)
            if manifest_file.exists():
                try:
                    existing = json.loads(manifest_file.read_text(encoding="utf-8"))
                    for entry in existing.get("results", []):
                        fname = entry.get("filename", "")
                        if fname and entry.get("status") != "failed":
                            occupied.add(fname)
                except (json.JSONDecodeError, OSError):
                    pass

        for item in images or []:
            if isinstance(item, dict) and item.get("filename"):
                item["filename"] = available_filename(item["filename"], occupied)
                occupied.add(item["filename"])

        result = await self.generate_images(images=images, **kwargs)

        # Write initial manifest from the immediate result
        self._write_manifest_initial(manifest_path, result.result)

        # If there's a background poll, wrap it to update manifest on completion
        if result.poll is not None:
            pending_items = result.result.get("pending_tasks", [])
            filenames = [p.get("filename", "") for p in pending_items]
            result = BgTaskResult(
                result=result.result,
                poll=self._poll_with_manifest_update(result.poll, manifest_path, filenames),
                command_name=result.command_name,
            )

        return result

    async def _poll_with_manifest_update(
        self, poll_coro: Awaitable[tuple[str, list[dict]]], manifest_path: str, filenames: list[str]
    ) -> dict:
        """Wrap a poll coroutine to update manifest after it completes."""
        try:
            summary, poll_results = await poll_coro
        except (asyncio.TimeoutError, asyncio.CancelledError):
            # Task was cancelled or timed out — mark all as failed
            failed_results = [{"status": "failed", "filename": fn, "url": ""} for fn in filenames]
            self._update_manifest_from_poll(manifest_path, failed_results)
            raise
        self._update_manifest_from_poll(manifest_path, poll_results)
        success_count = sum(1 for item in poll_results if item.get("status") == "success")
        failed_count = len(poll_results) - success_count
        status = "success" if not failed_count else "failed" if not success_count else "partial_success"
        return {
            "status": status,
            "results": poll_results,
            "success_count": success_count,
            "failed_count": failed_count,
            "summary": summary,
        }

    async def generate_images(self, images: list[dict], **_: object) -> BgTaskResult:
        """Generate multiple images: submit all tasks immediately via async API, return pre_urls,
        then poll remaining in background.

        Note:
            A maximum of MAX_IMAGE_BATCH_SIZE images can be submitted per call.
            If more are provided, the call returns immediately with an error
            prompt asking to submit in batches.

        Args:
            images: A list of image generation requests (max 50 per call). Each item is a dict with:
                - description: Detailed description of the image to generate
                - filename: Target filename (e.g., "hero-image.jpg", "logo.png")
                - style: Image style (photorealistic, cartoon, sketch, watercolor, minimalist, 3d)
                  If omitted, defaults to "photorealistic".
                - size: (Optional) Image size for this image (e.g., 1024x1024, 1024x576, 1024x768).
                  If omitted, defaults to "1024x1024".
                - image: (Optional) Reference image for image-to-image editing. Supports absolute
                  local file paths and http(s) URLs.
                - background: (Optional) Use "transparent" to request a transparent background.
                  This temporarily switches the request model to gpt-image-1.5 and replaces
                  unsupported or missing filename extensions with .png.

        Returns:
            BgTaskResult: Immediate result with submitted task IDs and pre_urls;
                pending tasks are polled in the background and the agent
                receives a notification when all complete.
        """
        if not self.working_dir:
            raise RuntimeError("working_dir not set for ImageCreator")

        if images and len(images) > MAX_IMAGE_BATCH_SIZE:
            return BgTaskResult(
                result={
                    "status": "failed",
                    "message": (
                        "Too many images submitted. Please keep to a minimal number and retry. "
                        f"You submitted {len(images)}."
                    ),
                    "requested_count": len(images),
                    "max_batch_size": MAX_IMAGE_BATCH_SIZE,
                },
                poll=None,
            )

        # Parse requests
        requested: list[ImageGenerationRequest] = []
        invalid_results: list[dict] = []
        for item in images or []:
            try:
                if isinstance(item, ImageGenerationRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(ImageGenerationRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid image generation request ignored: {item}, err={e}")
                invalid_results.append(
                    {
                        "status": "failed",
                        "filename": item.get("filename", "") if isinstance(item, dict) else "",
                        "url": "",
                        "message": f"Invalid image generation request: {type(e).__name__}: {e}",
                    }
                )

        if not requested:
            return BgTaskResult(
                result={
                    "status": "failed" if invalid_results else "success",
                    "results": [],
                    "success_count": 0,
                    "failed_count": len(invalid_results),
                    "failed_results": invalid_results,
                    "message": (
                        f"All {len(invalid_results)} image generation requests were invalid."
                        if invalid_results
                        else "No images to generate."
                    ),
                }
            )

        # Split: image-to-image (has reference image) vs text-to-image.
        async_reqs = [r for r in requested if not r.image]
        edit_reqs = [r for r in requested if r.image]

        # Local image services: no async task API, text-to-image only.
        # Validate before any artifact status reporting.
        if self._is_local_image_service(self.model):
            mismatched = [r for r in requested if r.model and r.model != self.model]
            if mismatched:
                names = ", ".join(r.model for r in mismatched)
                raise ValueError(
                    f"per-request model overrides are not supported for local image "
                    f"services (global model={self.model!r}, got: {names})"
                )
            if edit_reqs:
                edit_names = ", ".join(r.filename for r in edit_reqs)
                raise ValueError(
                    f"Local image service does not support image-to-image editing "
                    f"(model={self.model!r}). Requests with reference images: {edit_names}"
                )

        # Report running status before starting generation
        for req in requested:
            await self.artifacts_reporter.async_report(
                {"filename": req.filename, "status": "running", "artifact_type": "image"}, "object"
            )

        # Channels without an async task API (e.g. Gemini newapi) fall back to the
        # synchronous path. Local services don't support image-to-image, so edit_reqs
        # has already been rejected above and async_reqs holds only text-to-image.
        if self._is_local_image_service(self.model) or self._is_newapi_host(self.base_url):
            # NewAPI has no async task API; preserve reference images in its sync batch.
            sync_reqs = requested if self._is_newapi_host(self.base_url) else async_reqs
            result = await self._generate_images_sync(sync_reqs)
            if invalid_results:
                immediate = result.result
                immediate["results"] = list(immediate.get("results", [])) + invalid_results
                immediate.setdefault("failed_results", []).extend(invalid_results)
                immediate["failed_count"] = int(immediate.get("failed_count", 0) or 0) + len(invalid_results)
                immediate["status"] = "partial_success" if immediate.get("success_count", 0) else "failed"
                immediate["message"] = (
                    f"Generated {immediate.get('success_count', 0)}/"
                    f"{immediate.get('success_count', 0) + immediate['failed_count']} images; "
                    f"{immediate['failed_count']} failed."
                )
            return result

        # Both text-to-image and image-to-image use the async task submit/poll flow.
        # Text-to-image posts JSON to /images/generations/async; image-to-image posts
        # multipart/form-data to /images/edits/async. Both are polled via the shared
        # /async-tasks/:task_id interface.
        async_reqs = list(requested)

        # ---- Async submit phase ----
        submit_results: list[dict] = []
        submit_errors: list[dict] = list(invalid_results)

        async def _safe_submit(req: ImageGenerationRequest) -> dict:
            try:
                return await self._submit_one_async(req)
            except Exception as e:
                logger.error(
                    f"Image submit failed for '{req.filename}': {type(e).__name__}: {str(e)}"
                )
                await self.artifacts_reporter.async_report(
                    {"filename": req.filename, "status": "failed", "artifact_type": "image"},
                    "object",
                )
                return {
                    "status": "failed",
                    "filename": req.filename,
                    "message": f"Submit failed: {type(e).__name__}: {str(e)}",
                }

        # Submit one request every 0.5s to avoid rate-limiting
        for i, req in enumerate(async_reqs):
            r = await _safe_submit(req)
            if r.get("status") == "failed":
                submit_errors.append(r)
            else:
                submit_results.append(r)
            if i < len(async_reqs) - 1:
                await asyncio.sleep(0.5)

        # ---- Check if any already completed ----
        done_results: list[dict] = []
        pending_items: list[dict] = []

        for item in submit_results:
            task_id = item["task_id"]
            status = item["status"]
            if status == "completed":
                try:
                    task_obj = await self._retrieve_task(task_id)
                    urls = task_obj.get("urls") or item.get("pre_urls") or []
                    url = urls[0] if urls else ""
                    if url:
                        result = await self._build_url_result(
                            url, item["filename"], item["_meta"]["description"], item["_meta"]["style"]
                        )
                        done_results.append(result)
                    else:
                        pending_items.append(item)
                except Exception as e:
                    logger.warning(f"Finalize failed for already-completed {task_id}: {e}")
                    pending_items.append(item)
            else:
                pending_items.append(item)

        # ---- Build immediate result ----
        if pending_items:
            status = "running"
        elif submit_errors:
            status = "partial_success" if done_results else "failed"
        else:
            status = "success"
        immediate = {
            "status": status,
            "done_count": len(done_results),
            "pending_count": len(pending_items),
            "failed_count": len(submit_errors),
            "done_results": done_results,
            "pending_tasks": [
                {
                    "task_id": it.get("task_id", ""),
                    "filename": it["filename"],
                    "status": it["status"],
                    "pre_urls": it["pre_urls"],
                }
                for it in pending_items
            ],
            "failed_results": submit_errors,
            "message": (
                f"{len(done_results)} completed, {len(pending_items)} still generating, "
                f"{len(submit_errors)} failed."
                if pending_items
                else (
                    f"All {len(done_results)} images generated."
                    if done_results
                    else f"All {len(submit_errors)} submissions failed."
                )
            ),
        }

        if not pending_items:
            return BgTaskResult(result=immediate)

        # ---- Async phase: hand remaining to background poll ----
        poll = self._poll_and_finalize_images(
            pending_items,
            initial_failed_results=submit_errors,
        )
        return BgTaskResult(result=immediate, poll=poll, command_name="generate images")

    @staticmethod
    def _retained_manifest_results(results: list[dict]) -> list[dict]:
        """Keep only entries that are useful for later image reuse or completion polling."""
        return [item for item in results if item.get("status") != "failed"]

    @classmethod
    def _build_manifest_payload(cls, results: list[dict], *, failed_count: int = 0) -> dict:
        """Build a cumulative manifest with stats matching retained manifest results."""
        failed_count += sum(1 for item in results if item.get("status") == "failed")
        retained_results = cls._retained_manifest_results(results)
        success_count = sum(1 for item in retained_results if item.get("status") == "success")
        running_count = sum(1 for item in retained_results if item.get("status") == "running")
        total_count = success_count + failed_count + running_count

        if running_count:
            status = "running" if failed_count == 0 else "partial_success"
            message = f"{success_count} completed, {running_count} still generating, {failed_count} failed."
        else:
            status = (
                "success"
                if failed_count == 0
                else "failed"
                if success_count == 0
                else "partial_success"
            )
            message = f"Generated {success_count}/{total_count} images total"

        return {
            "status": status,
            "results": retained_results,
            "success_count": success_count,
            "failed_count": failed_count,
            "running_count": running_count,
            "message": message,
        }

    async def _submit_one_async(self, req: ImageGenerationRequest) -> dict:
        """Submit a single image task to the async API and return initial status with pre_urls."""
        requested_model = req.model or self.model
        resolved_filename, request_options, effective_model = self._resolve_oneapi_request_options(
            req.filename, req.background, requested_model
        )
        effective_model = validate_allowed_model(effective_model, self.allowed_models, "image generation")
        request_filename = normalize_request_filename(resolved_filename)
        enhanced_prompt = self._build_enhanced_prompt(
            req.description, req.style, has_reference_image=bool(req.image)
        )

        headers = {"Authorization": f"Bearer {self.api_key}"}

        if req.image:
            # Image-to-image: submit to the async edit endpoint as multipart/form-data
            # (mirrors the synchronous /images/edits request shape).
            upload = await self._load_reference_image(req.image)
            content_type = mimetypes.guess_type(upload.name)[0] or "image/png"
            form = FormData()
            form.add_field("model", effective_model)
            form.add_field("prompt", enhanced_prompt)
            form.add_field("n", "1")
            form.add_field("size", req.size or "1024x1024")
            form.add_field("filename", request_filename)
            form.add_field("image", upload.getvalue(), filename=upload.name, content_type=content_type)
            for key, value in request_options.items():
                form.add_field(key, value)

            logger.info(f"Submitting async image edit task: {req.filename}")
            data = await apost(
                url=f"{self.base_url}/images/edits/async",
                data=form,
                headers=headers,
                timeout=300,
                as_json=True,
                raise_for_status=True,
            )
        else:
            payload: dict = {
                "model": effective_model,
                "prompt": enhanced_prompt,
                "n": 1,
                "size": req.size or "1024x1024",
                "filename": request_filename,
            }
            payload.update(request_options)

            logger.info(f"Submitting async image task: {req.filename}")
            data = await apost(
                url=f"{self.base_url}/images/generations/async",
                json=payload,
                headers={**headers, "Content-Type": "application/json"},
                timeout=300,
                as_json=True,
                raise_for_status=True,
            )

        task_id = data.get("id") or data.get("task_id") or ""
        status = data.get("status") or "pending"
        pre_urls = data.get("pre_urls") or []

        if not task_id:
            raise RuntimeError("Async image API returned empty task_id")

        return {
            "task_id": task_id,
            "status": status,
            "filename": resolved_filename,
            "pre_urls": pre_urls,
            "_req": req,
            "_meta": {
                "description": req.description,
                "style": req.style or "photorealistic",
                "size": req.size or "1024x1024",
            },
        }

    async def _retrieve_task(self, task_id: str) -> dict:
        """GET /v1/async-tasks/:task_id — retrieve task status."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = await aget(
            url=f"{self.base_url}/async-tasks/{task_id}",
            headers=headers,
            as_json=True,
            timeout=60,
            raise_for_status=True,
        )
        return data

    async def _poll_task_until_complete(self, task_id: str) -> dict:
        """Poll a task until status is completed/failed, with timeout."""
        waited = 0.0
        while True:
            task_obj = await self._retrieve_task(task_id)
            status = task_obj.get("status", "")
            if status == "completed":
                return task_obj
            if status == "failed":
                error_msg = task_obj.get("error", {}).get("message", "") if isinstance(
                    task_obj.get("error"), dict
                ) else str(task_obj.get("error", "Image generation failed"))
                raise RuntimeError(error_msg or "Image generation failed")
            if waited >= float(self.max_poll_seconds):
                raise TimeoutError(f"Image generation timeout after {self.max_poll_seconds}s (task_id={task_id})")
            await asyncio.sleep(float(self.poll_interval_seconds))
            waited += float(self.poll_interval_seconds)

    async def _poll_task_with_resubmit(self, item: dict) -> dict:
        """Poll a task until complete; on rate-limit failure, resubmit with backoff."""
        return await poll_task_with_resubmit(
            item,
            poll_fn=self._poll_task_until_complete,
            submit_fn=self._submit_one_async,
            max_task_retries=self.max_task_retries,
            media_label="Image",
        )

    async def _poll_images_summary(self, pending_items: list[dict]) -> str:
        """Poll wrapper that returns only the summary string for BackgroundTaskPool."""
        summary, _results = await self._poll_and_finalize_images(pending_items)
        return summary

    async def _poll_and_finalize_images(
        self,
        pending_items: list[dict],
        *,
        initial_failed_results: Optional[list[dict]] = None,
    ) -> tuple[str, list[dict]]:
        """Poll all pending image tasks until complete, then archive and report.

        This coroutine is handed to BgTaskResult.poll and runs inside BackgroundTaskPool.

        Returns:
            A tuple of (summary_string, structured_results_list).
        """
        results: list[dict] = list(initial_failed_results or [])
        for item in pending_items:
            filename = item["filename"]
            meta = item["_meta"]
            try:
                task_obj = await self._poll_task_with_resubmit(item)
                urls = task_obj.get("urls") or []
                url = urls[0] if urls else ""
                if not url:
                    raise RuntimeError("Image generation completed but missing url in response")

                result = await self._build_url_result(url, filename, meta["description"], meta["style"])
                annotate_resubmit_result(result, item, "image")
                results.append(result)

                # Report success to artifacts (for frontend status update)
                await self.artifacts_reporter.async_report(
                    {
                        "filename": filename,
                        "status": "success",
                        "artifact_type": "image",
                        "data_name": "inline_image",
                        "path": url,
                        "local_path": result.get("local_path", ""),
                    },
                    "object",
                )
            except Exception as e:
                logger.error(
                    f"Image poll/finalize failed for '{filename}': {type(e).__name__}: {str(e)}"
                )
                await self.artifacts_reporter.async_report(
                    {"filename": filename, "status": "failed", "artifact_type": "image"},
                    "object",
                )
                results.append({
                    "status": "failed",
                    "filename": filename,
                    "url": "",
                    "message": f"Image generation failed: {type(e).__name__}: {str(e)}",
                })

        success = [r for r in results if r.get("status") == "success"]
        urls = [r.get("url", "") for r in success if r.get("url")]
        summary_parts = [f"{len(success)}/{len(results)} images generated."]
        if urls:
            summary_parts.append("URLs: " + ", ".join(urls))
        failed = [r for r in results if r.get("status") != "success"]
        if failed:
            summary_parts.append(
                "Failed: " + ", ".join(r.get("filename", "?") for r in failed)
            )

        summary = " ".join(summary_parts)

        return summary, results

    def _update_manifest_from_poll(self, manifest_path: str, poll_results: list[dict]) -> None:
        """Update image_manifest.json after poll completion using structured results.

        Args:
            manifest_path: Path to the manifest file.
            poll_results: List of dicts with at least 'filename' and 'status' keys.
        """
        try:
            manifest_file = Path(manifest_path)
            if not manifest_file.exists():
                return
            current = json.loads(manifest_file.read_text(encoding="utf-8"))
            current_results = current.get("results", [])

            # Build filename -> result mapping from structured poll results
            result_map: dict[str, dict] = {}
            for r in poll_results:
                fn = r.get("filename", "")
                if fn:
                    result_map[fn] = r

            for item in current_results:
                if item.get("status") != "running":
                    continue
                fn = item.get("filename", "")
                if fn not in result_map:
                    continue
                final = result_map[fn]
                item["status"] = final.get("status", "failed")
                final_url = final.get("url", "")
                if final_url:
                    item["url"] = final_url
                    item["path"] = final.get("path", final_url)
                    item["absolute_path"] = final.get("absolute_path", final_url)

            existing_failed_count = int(current.get("failed_count", 0) or 0)
            manifest = self._build_manifest_payload(current_results, failed_count=existing_failed_count)
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(f"Updated image manifest after poll completion: {manifest_path}")
        except Exception as e:
            logger.warning(f"Failed to update image manifest after poll: {e}")

    def _write_manifest_initial(self, manifest_path: str, immediate: dict) -> None:
        """Write initial image_manifest.json with pre_urls for subagent consumption.

        Only running/success entries are kept in manifest results so that failed
        filenames become available for retry.
        """
        try:
            manifest_file = Path(manifest_path)
            manifest_file.parent.mkdir(parents=True, exist_ok=True)

            # Build results: use existing 'results' field if present (sync path),
            # otherwise construct from done_results + pending pre_urls (async path).
            failed_count = 0
            new_results: list[dict] = []
            if "results" in immediate and immediate["results"]:
                new_results = immediate["results"]
            else:
                for done in immediate.get("done_results", []):
                    if done.get("status") != "failed":
                        new_results.append(done)
                for pending in immediate.get("pending_tasks", []):
                    # Always register a running entry so the filename is tracked,
                    # even when there is no pre_url. The final url is filled in
                    # later by _update_manifest_from_poll.
                    pre_urls = pending.get("pre_urls") or []
                    url = pre_urls[0] if pre_urls else ""
                    new_results.append({
                        "status": "running",
                        "filename": pending.get("filename", ""),
                        "url": url,
                        "path": "",
                        "absolute_path": "",
                    })
                failed_count = int(immediate.get("failed_count", 0) or 0)

            # Read existing manifest
            existing_results: list[dict] = []
            existing_failed_count = 0
            if manifest_file.exists():
                try:
                    existing = json.loads(manifest_file.read_text(encoding="utf-8"))
                    existing_results = self._retained_manifest_results(existing.get("results", []))
                    existing_failed_count = int(existing.get("failed_count", 0) or 0)
                except (json.JSONDecodeError, OSError):
                    pass

            manifest = self._build_manifest_payload(
                existing_results + new_results,
                failed_count=existing_failed_count + failed_count,
            )
            manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
            logger.info(
                f"Saved image manifest: {manifest_path} "
                f"({len(new_results)} new, {len(existing_results)} existing)"
            )
        except Exception as e:
            logger.warning(f"Failed to write initial image manifest: {e}")

    async def _generate_images_sync(self, requested: list[ImageGenerationRequest]) -> BgTaskResult:
        """Synchronous generation path for channels that don't support async task API (e.g. Gemini)."""
        cfg = Config.default().multimodal.image_generation
        max_concurrency = int(getattr(cfg, "max_concurrency", None) or 4)

        _is_rate_limited_message = is_rate_limited_message

        def _build_failed_result(req: ImageGenerationRequest, err: Exception) -> dict:
            return {
                "status": "failed",
                "path": "",
                "absolute_path": "",
                "url": "",
                "message": f"Image generation failed: {str(err)}",
                "description": req.description,
                "style": req.style,
                "filename": req.filename,
            }

        async def _call_generate_image(req: ImageGenerationRequest) -> dict:
            kwargs = {
                "description": req.description,
                "filename": req.filename,
                "style": req.style or "photorealistic",
                "size": req.size or "1024x1024",
                "image": req.image,
                "background": req.background,
            }
            result = await self.generate_image(**kwargs)
            result["filename"] = req.filename
            return result

        async def _generate_once(req: ImageGenerationRequest) -> dict:
            try:
                return await _call_generate_image(req)
            except Exception as e:
                return _build_failed_result(req, e)

        async def _generate_serial_with_retry(req: ImageGenerationRequest) -> dict:
            try:
                async for attempt in AsyncRetrying(
                    retry=retry_if_exception(lambda e: _is_rate_limited_message(str(e))),
                    stop=stop_after_attempt(3),
                    wait=wait_random_exponential(min=2, max=30),
                    reraise=True,
                ):
                    with attempt:
                        return await _call_generate_image(req)
            except Exception as e:
                return _build_failed_result(req, e)

        results: list[Optional[dict]] = [None] * len(requested)
        fallback_to_serial = False

        for start in range(0, len(requested), max_concurrency):
            batch = requested[start : start + max_concurrency]
            batch_results = await asyncio.gather(*[_generate_once(req) for req in batch])
            for offset, res in enumerate(batch_results):
                results[start + offset] = res

            hit_rate_limit = any(
                (res.get("status") != "success") and _is_rate_limited_message(res.get("message", ""))
                for res in batch_results
            )
            if not hit_rate_limit:
                continue

            fallback_to_serial = True
            logger.warning(
                f"Rate limit detected; falling back to serial generation for {len(requested) - start} images"
            )

            for offset, (req, res) in enumerate(zip(batch, batch_results)):
                if res.get("status") != "success" and _is_rate_limited_message(res.get("message", "")):
                    results[start + offset] = await _generate_serial_with_retry(req)

            for idx in range(start + len(batch), len(requested)):
                results[idx] = await _generate_serial_with_retry(requested[idx])
            break

        final_results = [r for r in results if r is not None]
        failed = [r for r in final_results if r.get("status") != "success"]

        status: str
        if not failed:
            status = "success"
        elif len(failed) == len(final_results):
            status = "failed"
        else:
            status = "partial_success"

        msg = f"Generated {len(final_results) - len(failed)}/{len(final_results)} images"
        if fallback_to_serial:
            msg += " (rate limited; fell back to serial)"

        # Unified reporting to Artifacts (individual items)
        for res in final_results:
            filename = res.get("filename", "")

            if res.get("status") != "success":
                if not filename:
                    filename = "unknown"
                await self.artifacts_reporter.async_report(
                    {"filename": filename, "status": "failed", "artifact_type": "image"}, "object"
                )
                continue

            url = res.get("url", "")
            path = res.get("absolute_path", "")
            if not filename and url:
                filename = url.split("/")[-1]

            is_remote = url.startswith("http")

            item = {
                "filename": filename,
                "image_url": url,
                "status": "success",
                "artifact_type": "image",
            }

            if is_remote:
                item["data_name"] = "inline_image"
                item["path"] = url
                item["local_path"] = res.get("local_path", "")
            else:
                item["data_name"] = "path"
                item["path"] = path
                item["local_path"] = path

            await self.artifacts_reporter.async_report(item, "object")

        return BgTaskResult(result={
            "status": status,
            "results": final_results,
            "success_count": len(final_results) - len(failed),
            "failed_count": len(failed),
            "message": msg,
        })

    async def _save_image_and_return_result(
        self, image_bytes: bytes, filename: str, description: str, style: str
    ) -> dict:
        """Save image bytes to local assets directory and return result dict"""
        if is_overview_asset_context():
            workspace_root = resolve_workspace_root(self.working_dir)
            assets_dir = workspace_root / "overview_assets" / "images"
        else:
            assets_dir = Path(self.working_dir) / self.subdir_path
        requested_path = assets_dir / filename

        image_path = Path(await self._save_image(image_bytes, str(requested_path)))
        relative_name = image_path.relative_to(assets_dir).as_posix()
        relative_path = f"{self.subdir_path}/{relative_name}" if self.subdir_path else f"/{relative_name}"

        self.resource.report(str(image_path), "path")
        logger.info(f"Image created: {image_path}")

        return {
            "status": "success",
            "path": relative_path,
            "absolute_path": str(image_path),
            "local_path": str(image_path),
            "url": "",
            "message": f"Image generated and saved to {relative_path}",
            "description": description,
            "style": style,
            "filename": image_path.name,
        }

    async def _build_url_result(self, url: str, filename: str, description: str, style: str) -> dict:
        """Build result dict for URL response and best-effort archive the asset into workspace/assets."""
        # Report inline image for frontend display
        inline_image_data = {
            "status": "completed",
            "url": url,  # CDN URL
            "filename": filename,
            "description": description,
        }
        logger.info(f"Image created (CDN): {url}")
        try:
            archive_info = await archive_cdn_media(
                working_dir=self.working_dir,
                media_dir="images",
                url=url,
                timeout=300,
                fallback_filename=filename,
                is_overview_asset=is_overview_asset_context(),
            )
            inline_image_data["local_path"] = archive_info["workspace_absolute_path"]
            logger.info(f"Image archived to workspace: {archive_info['workspace_absolute_path']}")
        except Exception as e:
            logger.warning(f"Image archive skipped for CDN URL {url}: {type(e).__name__}: {str(e)}")
        self.resource.report(inline_image_data, "inline_image")

        return {
            "status": "success",
            "path": url,
            "absolute_path": url,
            "local_path": inline_image_data.get("local_path", ""),
            "url": url,
            "message": "Image generated successfully.\n\n"
            "Note: The image is on CDN and will be displayed automatically. "
            "Just describe what you created briefly, no need to mention filenames or URLs.",
            "description": description,
            "style": style,
            "filename": filename,
        }

    def _build_enhanced_prompt(self, description: str, style: Optional[str], has_reference_image: bool = False) -> str:
        """Building enhanced prompt"""
        enhanced = description

        if style:
            style_guides = {
                "photorealistic": "photorealistic, high detail, professional photography",
                "cartoon": "cartoon style, colorful, animated",
                "sketch": "pencil sketch, black and white, artistic",
                "watercolor": "watercolor painting, soft edges, artistic",
                "minimalist": "minimalist design, clean, simple",
                "3d": "3D render, blender, octane render",
            }
            if style in style_guides:
                enhanced += f", {style_guides.get(style,'')}"

        if has_reference_image:
            return f"Edit the reference image according to this instruction: {enhanced}"
        return f"Generate an image: {enhanced}"

    @staticmethod
    def _is_openai_gpt_image_model(model: Optional[str]) -> bool:
        """Whether the current model is an OpenAI gpt-image variant."""
        return (model or "").strip().lower().startswith("gpt-image")

    @staticmethod
    def _is_newapi_host(base_url: str) -> bool:
        host = urlparse((base_url or "").strip()).hostname or ""
        return host.lower() == NEWAPI_HOST

    def _is_local_image_service(self, model: Optional[str]) -> bool:
        """Whether this request targets a local OpenAI-compatible image service.

        Local services (e.g. vLLM-Omni) support /images/generations with
        response_format=b64_json but do not support response_format=url or the
        async batch API. Opt-in via config2.yaml by pointing
        multimodal.image_generation.base_url at the local service and setting
        model accordingly. Production never selects these models.
        """
        return bool(self.base_url) and (model or "").strip().lower() == "z-image"

    def _resolve_image_channel(self, model: Optional[str]) -> ImageChannel:
        if not self._is_newapi_host(self.base_url):
            return ImageChannel.ONEAPI
        if "gemini" in (model or "").strip().lower():
            return ImageChannel.NEWAPI_GEMINI
        return ImageChannel.NEWAPI_NO_RESPONSE_FORMAT

    def _resolve_oneapi_request_options(
        self, filename: str, background: Optional[str], requested_model: Optional[str] = None
    ) -> tuple[str, dict[str, str], str]:
        """Validate model/filename constraints and build OpenAI-compatible image options."""
        base_model = requested_model or self.model
        normalized_background = (background or "").strip().lower()
        if not normalized_background:
            return filename, {}, base_model

        effective_model = base_model
        request_options = {"background": normalized_background}
        if normalized_background == "transparent":
            effective_model = OPENAI_TRANSPARENT_BACKGROUND_MODEL
            if effective_model != base_model:
                logger.info(
                    f"Transparent background requested, temporarily switching image model from {base_model} to {effective_model}"
                )
        elif not self._is_openai_gpt_image_model(base_model):
            raise ValueError("background is only supported for OpenAI gpt-image models")

        if normalized_background != "transparent":
            return filename, request_options, effective_model

        suffix = Path(filename).suffix.lower()
        if suffix in {".png", ".webp"}:
            request_options["output_format"] = suffix.lstrip(".")
            return filename, request_options, effective_model

        resolved_filename = Path(filename).with_suffix(".png").as_posix()
        request_options["output_format"] = "png"
        return resolved_filename, request_options, effective_model

    async def _load_reference_image(self, image_ref: str) -> io.BytesIO:
        """Load reference image (local path/URL) and convert to uploadable file-like object."""
        ref = (image_ref or "").strip()
        if not ref:
            raise ValueError("Reference image is empty")

        if ref.startswith("data:"):
            raise ValueError("image only supports absolute local path or http(s) URL, data URI not supported")

        if ref.startswith(("http://", "https://")):
            data = await aget_bytes(url=ref, timeout=60, raise_for_status=True)
            upload = io.BytesIO(data)
            upload.name = ref.split("?")[0].rstrip("/").split("/")[-1] or "input_reference.png"  # type: ignore[attr-defined]
            return upload

        local_path = Path(ref).expanduser()
        if not local_path.is_absolute():
            raise ValueError("Local reference image must use absolute path (or use http(s) URL instead)")
        if not local_path.exists() or not local_path.is_file():
            raise FileNotFoundError(f"Reference image not found: {str(local_path)}")

        upload = io.BytesIO(local_path.read_bytes())
        upload.name = local_path.name  # type: ignore[attr-defined]
        return upload

    async def _generate_via_openai_compatible(
        self,
        prompt: str,
        size: str = "1024x1024",
        image: Optional[str] = None,
        model: Optional[str] = None,
        request_options: Optional[dict[str, str]] = None,
        request_filename: str = "",
        response_format: Optional[str] = "url",
    ) -> Union[str, bytes]:
        """Generate images through an OpenAI-compatible image endpoint.

        Args:
            prompt: Image generation prompt
            size: Image size
            image: Optional reference image for image editing
            model: Effective model name for this request.
            request_options: Optional OpenAI-compatible image parameters such as
                background/output_format.
            request_filename: Provider-facing filename without directory or extension.
            response_format: Value for the OpenAI ``response_format`` field (e.g.
                "url" or "b64_json"). Pass None to omit it entirely.

        Returns:
            Union[str, bytes]: Generated image URL or image bytes (fallback)
        """
        headers = {"Authorization": f"Bearer {self.api_key}"}
        effective_model = model or self.model
        request_options = request_options or {}

        if image:
            # OpenAI-compatible image edit endpoints expect multipart file upload for the reference image.
            upload = await self._load_reference_image(image)
            content_type = mimetypes.guess_type(upload.name)[0] or "image/png"
            form = FormData()
            form.add_field("model", effective_model)
            form.add_field("filename", request_filename)
            form.add_field("prompt", prompt)
            form.add_field("n", "1")
            form.add_field("size", size)
            if response_format is not None:
                form.add_field("response_format", response_format)
            form.add_field("image", upload.getvalue(), filename=upload.name, content_type=content_type)
            for key, value in request_options.items():
                form.add_field(key, value)

            data = await apost(
                url=f"{self.base_url}/images/edits",
                data=form,
                headers=headers,
                timeout=300,
                as_json=True,
                raise_for_status=True,
            )
        else:
            payload = {
                "model": effective_model,
                "filename": request_filename,
                "prompt": prompt,
                "n": 1,
                "size": size,
            }
            if response_format is not None:
                payload["response_format"] = response_format
            payload.update(request_options)

            data = await apost(
                url=f"{self.base_url}/images/generations",
                json=payload,
                headers={**headers, "Content-Type": "application/json"},
                timeout=300,
                as_json=True,
                raise_for_status=True,
            )

        return self._extract_url_from_oneapi_response(data)

    async def _generate_via_newapi(
        self, prompt: str, request_filename: str, image: Optional[str] = None, model: Optional[str] = None
    ) -> bytes:
        """Generate images by calling Gemini through newapi

        Args:
            prompt: Image generation prompt
            request_filename: Provider-facing filename without directory or extension.
            image: Optional reference image for image editing
            model: Effective Gemini model name for this request.

        Returns:
            bytes: Generated image byte data
        """
        effective_model = model or self.model
        url = f"{self.base_url}/models/{effective_model}:generateContent?key={self.api_key}"

        parts: list[dict] = [{"text": prompt}]
        if image:
            # Gemini native generateContent keeps multimodal inputs inside the JSON payload.
            upload = await self._load_reference_image(image)
            content_type = mimetypes.guess_type(upload.name)[0] or "image/png"
            parts.insert(
                0,
                {
                    "inline_data": {
                        "mime_type": content_type,
                        "data": base64.b64encode(upload.getvalue()).decode("utf-8"),
                    }
                },
            )

        payload = {
            "filename": request_filename,
            "contents": [{"parts": parts}],
            "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
        }

        data = await apost(
            url=url,
            json=payload,
            headers={
                "Content-Type": "application/json",
            },
            timeout=300,
            as_json=True,
            raise_for_status=True,
        )

        return self._extract_image_from_newapi_response(data)

    def _extract_url_from_oneapi_response(self, data: dict) -> Union[str, bytes]:
        """Extract image URL from oneapi response, fallback to b64_json if url not available

        Expected response format:
        {
            "created": 1234567890,
            "data": [
                {
                    "url": "https://...",
                    "b64_json": "..." (fallback)
                }
            ]
        }
        """
        data_list = data.get("data", [])
        if not data_list:
            raise RuntimeError("OneAPI returned empty result")

        first_item = data_list[0]

        # Try to get URL first
        url = first_item.get("url")
        if url:
            return url

        # Fallback to b64_json
        b64_data = first_item.get("b64_json")
        if b64_data:
            logger.info("URL not found in OneAPI response, falling back to b64_json")
            return base64.b64decode(b64_data)

        raise RuntimeError("Neither url nor b64_json found in OneAPI response")

    def _extract_image_from_newapi_response(self, data: dict) -> bytes:
        """Extract image data from newapi response (Gemini native format)"""
        candidates = data.get("candidates", [])
        if not candidates:
            raise RuntimeError("Newapi returned empty result")

        parts = candidates[0].get("content", {}).get("parts", [])
        for part in parts:
            inline_data = part.get("inlineData") or part.get("inline_data")
            if inline_data and inline_data.get("data"):
                return base64.b64decode(inline_data["data"])

        raise RuntimeError("Image data not found in newapi response")

    async def _save_image(self, image_bytes: bytes, save_path: str) -> str:
        """Save image to file"""
        save_path = Path(save_path)
        save_path.parent.mkdir(parents=True, exist_ok=True)

        img = Image.open(BytesIO(image_bytes))

        if save_path.suffix.lower() not in [".jpg", ".jpeg", ".png", ".webp"]:
            save_path = save_path.with_suffix(".jpg")
        if save_path.exists():
            stem = save_path.stem or save_path.name
            suffix = save_path.suffix
            counter = 2
            while True:
                candidate = save_path.with_name(f"{stem}_{counter}{suffix}")
                if not candidate.exists():
                    save_path = candidate
                    break
                counter += 1

        suffix = save_path.suffix.lower()
        if suffix in {".jpg", ".jpeg"} and img.mode not in {"RGB", "L"}:
            img = img.convert("RGB")
        elif suffix in {".png", ".webp"} and img.mode == "P" and "transparency" in img.info:
            img = img.convert("RGBA")

        if suffix in {".jpg", ".jpeg", ".webp"}:
            img.save(str(save_path), quality=95)
        else:
            img.save(str(save_path))
        return str(save_path)

SKILL = "image-generation"


def execute(request: dict):
    creator = ImageCreator(working_dir=str(Path.cwd()))
    manifest = resolve_workspace_root(Path.cwd()) / "app/frontend/image_manifest.json"
    return SkillScriptExecution.from_runtime(
        creator,
        creator.generate_images_with_manifest(
            images=request.get("images", []), manifest_path=str(manifest)
        ),
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
