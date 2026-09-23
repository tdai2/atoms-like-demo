#!/usr/bin/env python3
"""
Audio generation tool: Generates audio using async task API and returns platform-provided CDN URL.

Description:
- Submits TTS requests to POST /v1/audio/speech/async which returns immediately with task_id and pre_urls.
- Polls GET /v1/async-tasks/:task_id until completion.
- Archives the generated file under workspace/assets/audios/ for later lookup.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel, Field

from metagpt.config2 import Config
from metagpt.const import DEFAULT_WORKSPACE_ROOT
from metagpt.logs import logger
from metagpt.utils.ahttp_client import aget, apost
from metagpt.utils.bg_tool import BgTaskResult
from metagpt.utils.common import normalize_request_filename, validate_allowed_model
from metagpt.utils.media_task_retry import annotate_resubmit_result, poll_task_with_resubmit
from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script
from metagpt.utils.workspace_media import archive_cdn_media, is_overview_asset_context, probe_media_duration_seconds

# Maximum number of audios that can be submitted in a single call
MAX_AUDIO_BATCH_SIZE = 50

# Voice mapping: (model, gender) -> voice
VOICE_MAP: dict[tuple[str, str], str] = {
    # qwen3-tts-flash
    ("qwen3-tts-flash", "male"): "echo",  # Ethan
    ("qwen3-tts-flash", "female"): "alloy",  # Cherry
    # gemini-2.5-pro-preview-tts
    ("gemini-2.5-pro-preview-tts", "male"): "echo",  # Puck
    ("gemini-2.5-pro-preview-tts", "female"): "alloy",  # Zephyr
    # eleven
    ("eleven_v3", "male"): "echo",
    ("eleven_v3", "female"): "alloy",
    ("eleven_turbo_v2", "male"): "echo",  # bIHbv24MWmeRgasZH58o
    ("eleven_turbo_v2", "female"): "alloy",  # cgSgspJ2msm6clMCkdW9
    # OpenAI gpt-4o-mini-tts
    ("gpt-4o-mini-tts", "male"): "echo",
    ("gpt-4o-mini-tts", "female"): "nova",
}
# Fallback voices when model not found in map
DEFAULT_VOICE = {"male": "Ethan", "female": "Cherry"}


class AudioGenerationRequest(BaseModel):
    """Single audio generation request."""

    text: str = Field(..., description="Text content to convert to audio (TTS input)")
    filename: str = Field(..., description='Target filename (e.g., "intro.mp3")')
    model: Optional[str] = Field(default=None, description="TTS model name. If not specified, uses configured default.")
    gender: Literal["male", "female"] = Field(default="female", description="Voice gender: male or female.")
    speed: float = Field(default=1.0, description="Speech speed multiplier (default 1.0)")


class AudioCreator(BaseModel):
    """Tool for generating audio (TTS) via async task API."""

    api_key: str = Field(default_factory=lambda: Config.default().multimodal.audio_generation.api_key)
    base_url: str = Field(default_factory=lambda: Config.default().multimodal.audio_generation.base_url)

    # Default TTS model name
    model: str = Field(default_factory=lambda: Config.default().multimodal.audio_generation.model)
    allowed_models: list[str] = Field(default_factory=lambda: Config.default().multimodal.audio_generation.allowed_models)

    # Concurrency configuration
    max_concurrency: int = Field(
        default_factory=lambda: getattr(Config.default().multimodal.audio_generation, "max_concurrency", 4)
    )
    working_dir: str = Field(default_factory=lambda: str(DEFAULT_WORKSPACE_ROOT.resolve()), exclude=True)

    # Polling parameters
    poll_interval_seconds: float = Field(default=3.0, description="Polling interval (seconds)")
    max_poll_seconds: int = Field(default=600, description="Maximum polling wait time (seconds)")
    max_task_retries: int = Field(
        default=3, description="Max resubmissions when a task fails due to upstream rate limiting"
    )

    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    @staticmethod
    def _get_voice(model: str, gender: str) -> str:
        """Get voice based on model and gender from mapping table."""
        voice = VOICE_MAP.get((model, gender))
        if voice:
            return voice
        return DEFAULT_VOICE.get(gender, "alloy")

    async def _submit_one_async(self, req: AudioGenerationRequest) -> dict:
        """Submit a single audio task to POST /v1/audio/speech/async."""
        filename = req.filename
        request_filename = normalize_request_filename(filename)
        model = validate_allowed_model(req.model or self.model, self.allowed_models, "audio generation")
        voice = self._get_voice(model, req.gender)

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        payload = {
            "model": model,
            "input": req.text,
            "voice": voice,
            "speed": req.speed,
            "response_format": "mp3",
            "filename": request_filename,
        }
        logger.info(f"Submitting async audio task: {filename}")
        data = await apost(
            url=f"{self.base_url.rstrip('/')}/audio/speech/async",
            json=payload,
            headers=headers,
            timeout=300,
            as_json=True,
            raise_for_status=True,
        )

        task_id = data.get("id") or data.get("task_id") or ""
        status = data.get("status") or "pending"
        pre_urls = data.get("pre_urls") or []

        if not task_id:
            raise RuntimeError("Async audio API returned empty task_id")

        return {
            "task_id": task_id,
            "status": status,
            "filename": filename,
            "pre_urls": pre_urls,
            "_req": req,
            "_meta": {
                "text": req.text,
                "gender": req.gender,
                "voice": voice,
                "model": model,
            },
        }

    async def _retrieve_task(self, task_id: str) -> dict:
        """GET /v1/async-tasks/:task_id — retrieve task status."""
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = await aget(
            url=f"{self.base_url.rstrip('/')}/async-tasks/{task_id}",
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
                ) else str(task_obj.get("error", "Audio generation failed"))
                raise RuntimeError(error_msg or "Audio generation failed")
            if waited >= float(self.max_poll_seconds):
                raise TimeoutError(f"Audio generation timeout after {self.max_poll_seconds}s (task_id={task_id})")
            await asyncio.sleep(float(self.poll_interval_seconds))
            waited += float(self.poll_interval_seconds)

    async def _poll_task_with_resubmit(self, item: dict) -> dict:
        """Poll a task until complete; on rate-limit failure, resubmit with backoff."""
        return await poll_task_with_resubmit(
            item,
            poll_fn=self._poll_task_until_complete,
            submit_fn=self._submit_one_async,
            max_task_retries=self.max_task_retries,
            media_label="Audio",
        )

    async def _poll_and_finalize_audios(
        self,
        pending_items: list[dict],
        *,
        initial_failed_results: Optional[list[dict]] = None,
    ) -> str:
        """Poll all pending audio tasks until complete, then archive and report.

        This coroutine is handed to BgTaskResult.poll and runs inside BackgroundTaskPool.
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
                    raise RuntimeError("Audio generation completed but missing url in response")

                result = {
                    "status": "success",
                    "path": url,
                    "absolute_path": url,
                    "url": url,
                    "message": "Audio generated successfully.",
                    "filename": filename,
                    "text": meta["text"],
                    "gender": meta["gender"],
                    "voice": meta["voice"],
                    "model": meta["model"],
                    "duration": None,
                }
                annotate_resubmit_result(result, item, "audio")

                # Archive to workspace
                archive_path = ""
                try:
                    archive_info = await archive_cdn_media(
                        working_dir=self.working_dir,
                        media_dir="audios",
                        url=url,
                        timeout=300,
                        fallback_filename=filename,
                        is_overview_asset=is_overview_asset_context(),
                    )
                    archive_path = archive_info["workspace_absolute_path"]
                    logger.info(f"Audio archived to workspace: {archive_path}")
                except Exception as e:
                    logger.warning(f"Audio archive skipped for CDN URL {url}: {type(e).__name__}: {str(e)}")

                # Report artifact
                report_item = {
                    "filename": filename,
                    "status": "success",
                    "artifact_type": "audio",
                    "data_name": "inline_audio",
                    "path": url,
                }
                if archive_path:
                    report_item["local_path"] = archive_path
                await self.artifacts_reporter.async_report(report_item, "object")

                # Probe duration
                result["duration"] = await probe_media_duration_seconds(
                    local_path=archive_path or None,
                    url=url,
                    timeout=30,
                )
                results.append(result)
            except Exception as e:
                logger.error(
                    f"Audio poll/finalize failed for '{filename}': {type(e).__name__}: {str(e)}"
                )
                await self.artifacts_reporter.async_report(
                    {"filename": filename, "status": "failed", "artifact_type": "audio"},
                    "object",
                )
                results.append({
                    "status": "failed",
                    "filename": filename,
                    "url": "",
                    "message": f"Audio generation failed: {type(e).__name__}: {str(e)}",
                })

        success = [r for r in results if r.get("status") == "success"]
        summary_parts = [f"{len(success)}/{len(results)} audios generated."]
        failed = [r for r in results if r.get("status") != "success"]
        if failed:
            summary_parts.append(
                "Failed: " + ", ".join(r.get("filename", "?") for r in failed)
            )
        return json.dumps({"summary": " ".join(summary_parts), "results": results}, ensure_ascii=False)

    async def generate_audios(self, audios: list[dict], **_: object) -> BgTaskResult:
        """Generate multiple audio files: submit all tasks immediately via async API, return pre_urls,
        then poll remaining in background.

        Note:
            A maximum of MAX_AUDIO_BATCH_SIZE audios can be submitted per call.
            If more are provided, the call returns immediately with an error
            prompt asking to submit in batches.

        Args:
            audios: A list of audio generation requests. Each item is a dict with:
                - text: str, required, text content to convert to audio (TTS input)
                - filename: str, required, target filename with extension (e.g., "intro.mp3"). This is only a
                  logical output name for identification; the tool does NOT write a local file with this name.
                - model: str, optional, TTS model name. If not specified, uses configured default.
                - gender: str, optional, voice gender "male" or "female" (default: "female")

        Returns:
            BgTaskResult: Immediate result with submitted task IDs and pre_urls;
                pending tasks are polled in the background and the agent
                receives a notification when all complete.

        Example:
            audios = [
                {"text": "Welcome to our website", "filename": "intro.mp3"},
                {"text": "Product description", "filename": "narration.mp3", "gender": "male"}
            ]
            result = await generate_audios(audios)
            # Use result["pending_tasks"][0]["pre_urls"] directly in HTML/React
        """
        if audios and len(audios) > MAX_AUDIO_BATCH_SIZE:
            return BgTaskResult(
                result={
                    "status": "failed",
                    "message": (
                        "Too many audio files. Please keep to a minimal number and retry. "
                        f"You submitted {len(audios)}."
                    ),
                    "requested_count": len(audios),
                    "max_batch_size": MAX_AUDIO_BATCH_SIZE,
                },
                poll=None,
            )

        requested: list[AudioGenerationRequest] = []
        invalid_results: list[dict] = []
        for item in audios or []:
            try:
                if isinstance(item, AudioGenerationRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(AudioGenerationRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid audio generation request ignored: {item}, err={e}")
                invalid_results.append(
                    {
                        "status": "failed",
                        "filename": item.get("filename", "") if isinstance(item, dict) else "",
                        "url": "",
                        "message": f"Invalid audio generation request: {type(e).__name__}: {e}",
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
                        f"All {len(invalid_results)} audio generation requests were invalid."
                        if invalid_results
                        else "No audios to generate."
                    ),
                }
            )

        # Report running status before starting generation
        for req in requested:
            await self.artifacts_reporter.async_report(
                {"filename": req.filename, "status": "running", "artifact_type": "audio"},
                "object",
            )
        # ---- Async submit phase ----
        submit_results: list[dict] = []
        submit_errors: list[dict] = list(invalid_results)

        async def _safe_submit(req: AudioGenerationRequest) -> dict:
            try:
                return await self._submit_one_async(req)
            except Exception as e:
                logger.error(
                    f"Audio submit failed for '{req.filename}': {type(e).__name__}: {str(e)}"
                )
                await self.artifacts_reporter.async_report(
                    {"filename": req.filename, "status": "failed", "artifact_type": "audio"},
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
                        meta = item["_meta"]
                        # Archive to workspace (best-effort) so we can probe duration locally.
                        archive_path = ""
                        try:
                            archive_info = await archive_cdn_media(
                                working_dir=self.working_dir,
                                media_dir="audios",
                                url=url,
                                timeout=300,
                                fallback_filename=item["filename"],
                                is_overview_asset=is_overview_asset_context(),
                            )
                            archive_path = archive_info["workspace_absolute_path"]
                            logger.info(f"Audio archived to workspace: {archive_path}")
                        except Exception as e:
                            logger.warning(f"Audio archive skipped for CDN URL {url}: {type(e).__name__}: {str(e)}")
                        duration = await probe_media_duration_seconds(
                            local_path=archive_path or None,
                            url=url,
                            timeout=30,
                        )
                        done_result = {
                            "status": "success",
                            "url": url,
                            "filename": item["filename"],
                            "text": meta["text"],
                            "gender": meta["gender"],
                            "voice": meta["voice"],
                            "model": meta["model"],
                            "duration": duration,
                        }
                        if archive_path:
                            done_result["local_path"] = archive_path
                        done_results.append(done_result)
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
                    "task_id": it["task_id"],
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
                    f"All {len(done_results)} audios generated."
                    if done_results
                    else f"All {len(submit_errors)} submissions failed."
                )
            ),
        }

        if not pending_items:
            return BgTaskResult(result=immediate)

        # ---- Async phase: hand remaining to background poll ----
        poll = self._poll_and_finalize_audios(
            pending_items,
            initial_failed_results=submit_errors,
        )
        return BgTaskResult(result=immediate, poll=poll, command_name="generate audios")


SKILL = "audio-generation"


def execute(request: dict):
    creator = AudioCreator(working_dir=str(Path.cwd()))
    return SkillScriptExecution.from_runtime(
        creator, creator.generate_audios(audios=request.get("audios", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
