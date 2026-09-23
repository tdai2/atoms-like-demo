#!/usr/bin/env python3
"""
Video generation tool: Creates task and polls using OpenAI SDK standard flow, returning platform-provided CDN URL.

Reference:
- genvideo flow in `func-sea-templates/modules/aihub/backend/services/aihub.py` (create -> poll -> download)

Description:
- Our proxy platform stores generation results on CDN and provides an accessible `url` (or `output.url`) in the final video object.
- This tool keeps the CDN `url` for downstream use and also archives the generated file under
  `workspace/assets/videos/...` for later lookup.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
from pathlib import Path
from typing import Any, Literal, Optional

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, Field, PrivateAttr, model_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT
from metagpt.logs import logger
from metagpt.utils.ahttp_client import aget_bytes
from metagpt.utils.bg_tool import BgTaskResult
from metagpt.utils.common import get_mime_type, normalize_request_filename, validate_allowed_model
from metagpt.utils.media_task_retry import annotate_resubmit_result, poll_task_with_resubmit
from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script
from metagpt.utils.workspace_media import archive_cdn_media, is_overview_asset_context, probe_media_duration_seconds

# Maximum number of videos that can be submitted in a single call
MAX_VIDEO_BATCH_SIZE = 50


class EmptyResponseError(RuntimeError):
    """Empty/invalid response that should be retried."""


class VideoReferenceItem(BaseModel):
    """Reference item for reference-to-video / video-edit requests."""

    url: str = Field(..., description="Reference asset URL, data URI, gs:// URI, or absolute local path.")
    role: Optional[
        Literal[
            "reference_image",
            "first_frame",
            "last_frame",
            "style",
            "grid",
            "reference_video",
            "video",
            "extend",
            "reference_audio",
        ]
    ] = Field(default=None, description="Reference semantic role.")
    tag: Optional[str] = Field(default=None, description="Optional tag for prompt binding, e.g. @subject1.")
    voice_url: Optional[str] = Field(default=None, description="Optional voice reference URL for supported R2V models.")


class VideoGenerationRequest(BaseModel):
    """Single video generation request."""

    prompt: str = Field(..., description="Video generation prompt")
    filename: str = Field(..., description='Target filename (e.g., "demo.mp4")')
    model: Optional[str] = Field(
        default=None,
        description="Video model name. If not specified, uses the configured text-to-video or reference-guided video default.",
    )
    size: str = Field(
        default="1280x720",
        description="Resolution (720p). Do NOT change - 1280x720 is the most compatible across all models.",
    )
    seconds: int = Field(
        default=4,
        description="Duration in seconds. Do NOT change - 4 seconds is the most compatible across all models.",
    )
    image: Optional[str] = Field(
        default=None,
        description="Optional reference image for reference-guided video generation (absolute path or http(s) URL).",
    )
    input_reference: Optional[str] = Field(
        default=None,
        description="Optional reference image for reference-guided video generation. Prefer first_frame for new requests.",
    )
    first_frame: Optional[str] = Field(default=None, description="Optional first frame for image/keyframe video.")
    last_frame: Optional[str] = Field(default=None, description="Optional last frame for keyframe video.")
    audio: Optional[bool] = Field(default=None, description="Whether the video model should include audio.")
    negative_prompt: Optional[str] = Field(default=None, description="Elements to avoid in the generated video.")
    resolution: Optional[str] = Field(default=None, description="Resolution level, e.g. 720p / 1080p / 4k.")
    ratio: Optional[str] = Field(default=None, description="Aspect ratio, e.g. 16:9 / 9:16 / 1:1.")
    audio_setting: Optional[Literal["auto", "origin"]] = Field(
        default=None,
        description="Video-edit audio setting. origin keeps input video audio when supported.",
    )
    reference_images: list[VideoReferenceItem] = Field(default_factory=list)
    reference_videos: list[VideoReferenceItem] = Field(default_factory=list)
    reference_audios: list[VideoReferenceItem] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_reference_fields(self) -> "VideoGenerationRequest":
        image_first_frames = [item for item in self.reference_images if item.role == "first_frame"]
        image_last_frames = [item for item in self.reference_images if item.role == "last_frame"]
        if self.first_frame and image_first_frames:
            raise ValueError("Do not provide both first_frame and reference_images role=first_frame")
        if self.last_frame and image_last_frames:
            raise ValueError("Do not provide both last_frame and reference_images role=last_frame")
        if self.last_frame and not (self.first_frame or image_first_frames):
            raise ValueError("last_frame requires first_frame or reference_images role=first_frame")
        return self


class VideoGenerator(BaseModel):
    """Generate videos through the configured OneAPI video endpoint."""

    api_key: str = Field(default_factory=lambda: Config.default().multimodal.video_generation.api_key)
    base_url: str = Field(default_factory=lambda: Config.default().multimodal.video_generation.base_url)
    text_to_video_model: str = Field(
        default_factory=lambda: Config.default().multimodal.video_generation.text_to_video_model
    )
    text_to_video_allowed_models: list[str] = Field(
        default_factory=lambda: Config.default().multimodal.video_generation.text_to_video_allowed_models
    )
    reference_guided_video_model: str = Field(
        default_factory=lambda: Config.default().multimodal.video_generation.reference_guided_video_model
    )
    reference_guided_video_allowed_models: list[str] = Field(
        default_factory=lambda: Config.default().multimodal.video_generation.reference_guided_video_allowed_models
    )
    poll_interval_seconds: float = Field(default=2.0, description="Polling interval (seconds)")
    max_poll_seconds: int = Field(default=600, description="Maximum polling wait time (seconds)")
    max_task_retries: int = Field(
        default=3, description="Max resubmissions when a task fails due to upstream rate limiting"
    )

    working_dir: str = Field(default_factory=lambda: str(DEFAULT_WORKSPACE_ROOT.resolve()), exclude=True)

    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    _client: Optional[AsyncOpenAI] = PrivateAttr(default=None)

    @model_validator(mode="after")
    def init_client(self):
        """Initialize OpenAI SDK client after model initialization."""
        self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.base_url.rstrip("/"))
        return self

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type((RateLimitError, TimeoutError, ConnectionError, EmptyResponseError)),
    )
    async def _create_video(self, client: AsyncOpenAI, create_params: dict) -> object:
        """Create video (with retry)."""
        video = await client.videos.create(**create_params)  # type: ignore[arg-type]
        if video is None:
            raise EmptyResponseError("Empty response from video creation API")
        video_id = getattr(video, "id", None)
        if not video_id:
            raise EmptyResponseError("Video generation started but missing video id")
        return video

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type((RateLimitError, TimeoutError, ConnectionError, EmptyResponseError)),
    )
    async def _retrieve_video(self, client: AsyncOpenAI, video_id: str) -> object:
        """Retrieve video status (with retry)."""
        video = await client.videos.retrieve(video_id)
        if video is None:
            raise EmptyResponseError("Empty response from video retrieve API")
        return video

    @staticmethod
    def _get_response_value(video_obj: object, key: str, default: Any = None) -> Any:
        if isinstance(video_obj, dict):
            return video_obj.get(key, default)
        return getattr(video_obj, key, default)

    @staticmethod
    def _extract_cdn_url(video_obj: object) -> Optional[str]:
        """Extract CDN URL (supports multiple platform formats)."""
        # Try standard OpenAI format: video.url
        url = VideoGenerator._get_response_value(video_obj, "url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            return url

        # Try OpenAI format: video.videos[0].url
        videos = VideoGenerator._get_response_value(video_obj, "videos")
        if videos and isinstance(videos, (list, tuple)) and len(videos) > 0:
            video = videos[0]
            out_url = VideoGenerator._get_response_value(video, "url")
            if isinstance(out_url, str) and out_url.startswith(("http://", "https://")):
                return out_url

        # Try format: video.video_url
        video_url = VideoGenerator._get_response_value(video_obj, "video_url")
        if isinstance(video_url, str) and video_url.startswith(("http://", "https://")):
            return video_url

        # Try format: video.output['url']
        output = VideoGenerator._get_response_value(video_obj, "output")
        if isinstance(output, dict):
            output_url = output.get("url")
            if isinstance(output_url, str) and output_url.startswith(("http://", "https://")):
                return output_url

        # Try format: video.meta_data['url']
        meta_data = VideoGenerator._get_response_value(video_obj, "meta_data")
        if isinstance(meta_data, dict):
            meta_url = meta_data.get("url")
            if isinstance(meta_url, str) and meta_url.startswith(("http://", "https://")):
                return meta_url

        return None

    def _build_url_result(
        self,
        url: str,
        filename: str,
        prompt: str,
        model: object,
        size: str,
        seconds: int,
    ) -> dict:
        """Build result while preserving the CDN URL for downstream use."""
        logger.info(f"Video created (CDN): {url}")
        return {
            "status": "success",
            "path": url,
            "absolute_path": url,
            "url": url,
            "message": "Video generated successfully.\n\n"
            "Note: The video is on CDN and will be displayed/used by URL directly.",
            "filename": filename,
            "prompt": prompt,
            "model": model,
            "size": size,
            "seconds": seconds,
        }

    async def _load_reference_image(self, image_ref: str) -> io.BytesIO:
        """Load reference image (local path/URL) and convert to uploadable file-like object."""
        ref = (image_ref or "").strip()
        if not ref:
            raise ValueError("image reference is empty")

        if ref.startswith("data:"):
            # Agent side only allows address input (local path or URL); data URI can cause oversized payload and instability
            raise ValueError("image only supports local path or http(s) URL, data URI not supported")

        # URL: download content
        if ref.startswith(("http://", "https://")):
            data = await aget_bytes(url=ref, timeout=60, raise_for_status=True)

            # Use URL filename as upload filename (fallback if missing)
            name = ref.split("?")[0].rstrip("/").split("/")[-1] or "input_reference.png"
            upload = io.BytesIO(data)
            upload.name = name  # type: ignore[attr-defined]
            return upload

        # Local path: only absolute paths supported (relative paths not supported)
        p = Path(ref).expanduser()
        if not p.is_absolute():
            raise ValueError("Local reference image must use absolute path (or use http(s) URL instead)")
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Reference image not found: {str(p)}")

        upload = io.BytesIO(p.read_bytes())
        upload.name = p.name  # type: ignore[attr-defined]
        return upload

    @staticmethod
    async def _local_file_to_data_uri(path: Path) -> str:
        mime_type = await get_mime_type(path, force_read=True)
        if not mime_type or not mime_type.startswith(("image/", "video/", "audio/")):
            raise ValueError(
                f"Cannot determine a supported media MIME type for local reference file '{path}'. "
                f"Detected MIME type: '{mime_type or 'unknown'}'. "
                "Inspect or convert the file to a valid image, video, or audio format, or use a supported URL."
            )
        return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"

    async def _normalize_upload_reference_value(self, ref: str, *, upload_name_prefix: str) -> object:
        value = (ref or "").strip()
        if not value:
            raise ValueError(f"{upload_name_prefix} reference is empty")
        if value.startswith(("http://", "https://", "data:", "gs://")):
            return value
        return await self._load_reference_image(value)

    async def _normalize_reference_item_value(self, ref: str, *, field_name: str) -> str:
        value = (ref or "").strip()
        if not value:
            raise ValueError(f"{field_name} reference is empty")
        if value.startswith(("http://", "https://", "data:", "gs://")):
            return value
        p = Path(value).expanduser()
        if not p.is_absolute():
            raise ValueError(f"Local {field_name} reference must use absolute path or URL/data URI/gs://")
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Reference file not found: {str(p)}")
        return await self._local_file_to_data_uri(p)

    async def _normalize_reference_item(self, item: VideoReferenceItem) -> dict[str, Any]:
        normalized = item.model_dump(exclude_none=True)
        normalized["url"] = await self._normalize_reference_item_value(item.url, field_name="url")
        if item.voice_url:
            normalized["voice_url"] = await self._normalize_reference_item_value(
                item.voice_url, field_name="voice_url"
            )
        return normalized

    async def _poll_video_until_complete(self, video: object, video_id: str) -> object:
        status = self._get_response_value(video, "status")
        waited = 0.0
        while status in ("in_progress", "queued"):
            if waited >= float(self.max_poll_seconds):
                raise TimeoutError(f"Video generation timeout after {self.max_poll_seconds}s (id={video_id})")
            await asyncio.sleep(float(self.poll_interval_seconds))
            waited += float(self.poll_interval_seconds)
            video = await self._retrieve_video(self._client, video_id)
            status = self._get_response_value(video, "status")

        if status == "failed":
            error_obj = self._get_response_value(video, "error")
            error_msg = self._get_response_value(error_obj, "message") or "Video generation failed"
            raise RuntimeError(error_msg)

        return video

    async def _poll_video_with_resubmit(self, item: dict) -> object:
        """Poll a video task until complete; on rate-limit failure, resubmit with backoff."""

        async def _poll(video_id: str) -> object:
            video = await self._retrieve_video(self._client, video_id)
            return await self._poll_video_until_complete(video, video_id)

        return await poll_task_with_resubmit(
            item,
            poll_fn=_poll,
            submit_fn=self._submit_one,
            max_task_retries=self.max_task_retries,
            media_label="Video",
        )

    async def _archive_and_report_video(
        self,
        *,
        video: object,
        filename: str,
        prompt: str,
        model: object,
        size: str,
        requested_seconds: int,
    ) -> dict:
        logger.debug(f"Platform response: {video}")
        cdn_url = self._extract_cdn_url(video)
        logger.debug(f"Extracted CDN URL: {cdn_url}")
        duration = self._get_response_value(video, "seconds")
        if duration is None or not isinstance(duration, (int, float)):
            duration = requested_seconds
        else:
            duration = int(duration)
        if not cdn_url:
            raise RuntimeError("Video generation completed but missing CDN url.")

        result = self._build_url_result(
            url=cdn_url,
            filename=filename,
            prompt=prompt,
            model=model,
            size=size,
            seconds=duration,
        )

        archive_path = ""
        report_filename = filename
        try:
            archive_info = await archive_cdn_media(
                working_dir=self.working_dir,
                media_dir="videos",
                url=cdn_url,
                timeout=max(self.max_poll_seconds, 300),
                fallback_filename=filename,
                is_overview_asset=is_overview_asset_context(),
            )
            archive_path = archive_info["workspace_absolute_path"]
            report_filename = archive_info["filename"]
            result["filename"] = report_filename
            logger.info(f"Video archived to workspace: {archive_path}")
        except Exception as e:
            logger.warning(f"Video archive skipped for CDN URL {cdn_url}: {type(e).__name__}: {str(e)}")

        report_item = {
            "filename": report_filename,
            "status": "success",
            "artifact_type": "video",
            "data_name": "inline_video",
            "path": cdn_url,
        }
        if archive_path:
            report_item["local_path"] = archive_path
        await self.artifacts_reporter.async_report(
            report_item,
            "object",
        )

        # Probe the real media duration; fall back to the API/requested value.
        probed = await probe_media_duration_seconds(
            local_path=archive_path or None,
            url=cdn_url,
            timeout=30,
        )

        result["duration"] = probed if probed is not None else duration
        if archive_path:
            result["local_path"] = archive_path
        return result

    @staticmethod
    def _has_reference_guided_inputs(req: VideoGenerationRequest) -> bool:
        return bool(
            req.image
            or req.input_reference
            or req.first_frame
            or req.last_frame
            or req.reference_images
            or req.reference_videos
            or req.reference_audios
        )

    def _resolve_generation_model(self, req: VideoGenerationRequest) -> str:
        if any(item.role == "video" for item in req.reference_videos):
            raise ValueError("reference_videos role=video belongs to the video-editing Skill")
        if self._has_reference_guided_inputs(req):
            default_model = self.reference_guided_video_model
            allowed_models = self.reference_guided_video_allowed_models
            capability_name = "reference-guided video generation"
        else:
            default_model = self.text_to_video_model
            allowed_models = self.text_to_video_allowed_models
            capability_name = "text-to-video generation"
        return validate_allowed_model(req.model or default_model, allowed_models, capability_name)

    async def _submit_one(self, req: VideoGenerationRequest) -> dict:
        """Submit a single video task and return its initial status (no polling).

        Returns a dict with ``task_id``, ``status``, ``filename`` and the
        ``_meta`` needed by ``_poll_and_finalize``.
        """
        filename = req.filename
        if not Path(filename).suffix:
            raise ValueError('filename must include extension (e.g., "promo.mp4")')
        request_filename = normalize_request_filename(filename)

        resolved_model = self._resolve_generation_model(req)
        create_params: dict[str, object] = {
            "model": resolved_model,
            "prompt": req.prompt,
            "size": req.size,
            "seconds": str(req.seconds),
            "extra_body": {"filename": request_filename},
        }
        extra_body = create_params["extra_body"]
        if not isinstance(extra_body, dict):
            raise TypeError("extra_body must be a dict")

        # Reference-guided video generation: reference image must be address only (local path/URL);
        # uses OpenAI SDK file upload parameter input_reference.
        input_reference = req.input_reference or req.image
        if input_reference:
            create_params["input_reference"] = await self._normalize_upload_reference_value(
                input_reference,
                upload_name_prefix="input_reference",
            )
        if req.first_frame:
            extra_body["first_frame"] = await self._normalize_reference_item_value(
                req.first_frame,
                field_name="first_frame",
            )
        if req.last_frame:
            extra_body["last_frame"] = await self._normalize_reference_item_value(
                req.last_frame,
                field_name="last_frame",
            )

        for key in ("audio", "negative_prompt", "resolution", "ratio", "audio_setting"):
            value = getattr(req, key)
            if value is not None:
                extra_body[key] = value

        if req.reference_images:
            extra_body["reference_images"] = [
                await self._normalize_reference_item(item) for item in req.reference_images
            ]
        if req.reference_videos:
            extra_body["reference_videos"] = [
                await self._normalize_reference_item(item) for item in req.reference_videos
            ]
        if req.reference_audios:
            extra_body["reference_audios"] = [
                await self._normalize_reference_item(item) for item in req.reference_audios
            ]

        logger.info(f"Start creating video: {filename}")

        video = await self._create_video(self._client, create_params)
        video_id = self._get_response_value(video, "id")
        status = self._get_response_value(video, "status") or "queued"
        pre_url = self._get_response_value(video, "pre_url")
        pre_urls = self._get_response_value(video, "pre_urls") or ([pre_url] if pre_url else [])

        return {
            "task_id": video_id,
            "status": status,
            "filename": filename,
            "pre_urls": pre_urls,
            "_req": req,
            # internal metadata for _poll_and_finalize
            "_meta": {
                "prompt": req.prompt,
                "model": create_params["model"],
                "size": req.size,
                "seconds": req.seconds,
            },
        }

    async def _poll_and_finalize(
        self,
        pending_items: list[dict],
        *,
        initial_failed_results: Optional[list[dict]] = None,
    ) -> str:
        """Poll all pending video tasks until complete, then archive and report.

        This coroutine is handed to ``BgTaskResult.poll`` and runs inside
        ``BackgroundTaskPool``.  Its return value appears in the completion
        notification sent to the agent.
        """
        results: list[dict] = list(initial_failed_results or [])
        for item in pending_items:
            filename = item["filename"]
            meta = item["_meta"]
            try:
                # Poll until complete; resubmit the task on upstream rate-limit failures.
                video = await self._poll_video_with_resubmit(item)
                result = await self._archive_and_report_video(
                    video=video,
                    filename=filename,
                    prompt=meta["prompt"],
                    model=meta["model"],
                    size=meta["size"],
                    requested_seconds=meta["seconds"],
                )
                annotate_resubmit_result(result, item, "video")
                results.append(result)
            except Exception as e:
                logger.opt(exception=True).error(
                    "Video poll/finalize failed for '{}': {}: {}",
                    filename,
                    type(e).__name__,
                    str(e),
                )
                await self.artifacts_reporter.async_report(
                    {"filename": filename, "status": "failed", "artifact_type": "video"},
                    "object",
                )
                results.append({
                    "status": "failed",
                    "filename": filename,
                    "url": "",
                    "message": f"Video generation failed: {type(e).__name__}: {str(e)}",
                })

        success = [r for r in results if r.get("status") == "success"]
        summary_parts = [f"{len(success)}/{len(results)} videos generated."]
        failed = [r for r in results if r.get("status") != "success"]
        if failed:
            summary_parts.append(
                "Failed: " + ", ".join(r.get("filename", "?") for r in failed)
            )
        return json.dumps({"summary": " ".join(summary_parts), "results": results}, ensure_ascii=False)

    async def generate_videos(self, videos: list[dict], **_: object) -> BgTaskResult:
        """Generate multiple videos: submit all tasks immediately, return task IDs,
        then poll remaining in background.

        Note:
            A maximum of MAX_VIDEO_BATCH_SIZE videos can be submitted per call.
            If more are provided, the call returns immediately with an error
            prompt asking to submit in batches.

        Args:
            videos: A list of video generation requests. Each item is a dict with:
                - prompt: str, required, descriptive prompt for video generation
                - filename: str, required, target filename with extension (e.g., "promo.mp4"). This is only a
                  logical output name for identification; the tool does NOT write a local file with this name.
                - model: str, optional, video model name (if not specified, uses the configured
                  `multimodal.video_generation.text_to_video_model`; reference-guided video requests fall back to
                  `multimodal.video_generation.reference_guided_video_model`)
                - size: str, optional, resolution (default: "1280x720"). Do NOT change unless specifically required.
                - seconds: int, optional, duration in seconds (default: 4). Do NOT change - 4 seconds is the most
                  compatible duration across all supported models (veo-3.1, wanxiang-2.6, etc.).
                - image: str, optional, reference image address (absolute path or http(s) URL) for reference-guided video generation.
                  Tool will automatically read/download and upload as input_reference.
                - first_frame / last_frame: optional keyframe references.
                - reference_images / reference_videos / reference_audios: optional reference-guided video assets.
                - resolution / ratio / audio / audio_setting / negative_prompt: optional OneAPI video parameters.

        Returns:
            BgTaskResult: Immediate result with submitted task IDs;
                pending tasks are polled in the background and the agent
                receives a notification when all complete.

        Example:
            videos = [
                {"prompt": "Ocean waves at sunset", "filename": "hero-ocean.mp4"},
                {"prompt": "Product demonstration", "filename": "demo.mp4"}
            ]
            result = await generate_videos(videos)
            # Use result["results"][0]["url"] directly in HTML/React
        """
        # ---- Parse requests ----
        if videos and len(videos) > MAX_VIDEO_BATCH_SIZE:
            return BgTaskResult(
                result={
                    "status": "failed",
                    "message": (
                        "Too many videos submitted. Please keep to a minimal number and retry. "
                        f"You submitted {len(videos)}."
                    ),
                    "requested_count": len(videos),
                    "max_batch_size": MAX_VIDEO_BATCH_SIZE,
                },
                poll=None,
            )

        requested: list[VideoGenerationRequest] = []
        invalid_results: list[dict] = []
        for item in videos or []:
            try:
                if isinstance(item, VideoGenerationRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(VideoGenerationRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid video generation request ignored: {item}, err={e}")
                invalid_results.append(
                    {
                        "status": "failed",
                        "filename": item.get("filename", "") if isinstance(item, dict) else "",
                        "url": "",
                        "message": f"Invalid video generation request: {type(e).__name__}: {e}",
                    }
                )

        if not requested and invalid_results:
            return BgTaskResult(
                result={
                    "status": "failed",
                    "results": [],
                    "success_count": 0,
                    "failed_count": len(invalid_results),
                    "failed_results": invalid_results,
                    "message": f"All {len(invalid_results)} video generation requests were invalid.",
                }
            )

        if invalid_results:
            return await self._run_video_generation(
                requested,
                initial_failed_results=invalid_results,
            )
        return await self._run_video_generation(requested)

    async def _run_video_generation(
        self,
        requested: list[VideoGenerationRequest],
        *,
        initial_failed_results: Optional[list[dict]] = None,
    ) -> BgTaskResult:
        if not requested:
            return BgTaskResult(
                result={
                    "status": "failed" if initial_failed_results else "success",
                    "results": [],
                    "success_count": 0,
                    "failed_count": len(initial_failed_results or []),
                    "failed_results": list(initial_failed_results or []),
                    "message": (
                        f"All {len(initial_failed_results or [])} video generation requests were invalid."
                        if initial_failed_results
                        else "No videos to generate."
                    ),
                }
            )

        # Report running status before starting generation (align with ImageCreator behavior)
        for req in requested:
            await self.artifacts_reporter.async_report(
                {"filename": req.filename, "status": "running", "artifact_type": "video"},
                "object",
            )

        # ---- Synchronous phase: submit all tasks concurrently ----
        submit_results: list[dict] = []
        submit_errors: list[dict] = list(initial_failed_results or [])

        async def _safe_submit(req: VideoGenerationRequest) -> dict:
            try:
                return await self._submit_one(req)
            except Exception as e:
                logger.opt(exception=True).error(
                    "Video submit failed for '{}': {}: {}",
                    req.filename, type(e).__name__, str(e),
                )
                await self.artifacts_reporter.async_report(
                    {"filename": req.filename, "status": "failed", "artifact_type": "video"},
                    "object",
                )
                return {
                    "status": "failed",
                    "filename": req.filename,
                    "message": f"Submit failed: {type(e).__name__}: {str(e)}",
                }

        # Submit one request every 0.5s to avoid rate-limiting
        for i, req in enumerate(requested):
            r = await _safe_submit(req)
            if r.get("status") == "failed":
                submit_errors.append(r)
            else:
                submit_results.append(r)
            if i < len(requested) - 1:
                await asyncio.sleep(0.5)

        # ---- First query: check if any already completed ----
        done_results: list[dict] = []
        pending_items: list[dict] = []

        for item in submit_results:
            video_id = item["task_id"]
            status = item["status"]
            if status in ("completed",):
                # Rare but possible — finalize immediately
                try:
                    video = await self._retrieve_video(self._client, video_id)
                    meta = item["_meta"]
                    result = await self._archive_and_report_video(
                        video=video,
                        filename=item["filename"],
                        prompt=meta["prompt"],
                        model=meta["model"],
                        size=meta["size"],
                        requested_seconds=meta["seconds"],
                    )
                    done_results.append(result)
                except Exception as e:
                    logger.warning(f"Finalize failed for already-completed {video_id}: {e}")
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
                {"task_id": it["task_id"], "filename": it["filename"], "status": it["status"], "pre_urls": it["pre_urls"]}
                for it in pending_items
            ],
            "failed_results": submit_errors,
            "message": (
                f"{len(done_results)} completed, {len(pending_items)} still generating, "
                f"{len(submit_errors)} failed."
                if pending_items
                else (
                    f"All {len(done_results)} videos generated."
                    if done_results
                    else f"All {len(submit_errors)} submissions failed."
                )
            ),
        }

        if not pending_items:
            return BgTaskResult(result=immediate)

        # ---- Async phase: hand remaining to background poll ----
        poll = self._poll_and_finalize(
            pending_items,
            initial_failed_results=submit_errors,
        )
        return BgTaskResult(result=immediate, poll=poll, command_name="generate videos")


SKILL = "video-generation"


def execute(request: dict):
    creator = VideoGenerator(working_dir=str(Path.cwd()))
    return SkillScriptExecution.from_runtime(
        creator, creator.generate_videos(videos=request.get("videos", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
