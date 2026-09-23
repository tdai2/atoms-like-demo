#!/usr/bin/env python3
"""
Music generation tool: Generates music/BGM using the async task API and returns platform-provided CDN URLs.

This tool is intentionally separate from AudioCreator. AudioCreator is for text-to-speech;
MusicCreator is for BGM, instrumental music, and song/music assets.

Description:
- Submits requests to POST /v1/audio/music/async which returns immediately with task_id and pre_urls.
- Polls GET /v1/async-tasks/:task_id until completion.
- Archives the generated file under workspace/assets/music/ for later lookup.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

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

# Maximum number of music tracks that can be submitted in a single call
MAX_MUSIC_BATCH_SIZE = 20


class MusicGenerationRequest(BaseModel):
    """Single music generation request."""

    prompt: str = Field(..., description="Music style/theme prompt.")
    filename: str = Field(..., description='Target filename (e.g., "teaser_bgm.wav").')
    model: Optional[str] = Field(default=None, description="Music generation model name.")
    n: int = Field(default=1, ge=1, le=4, description="Number of music samples to generate.")
    response_format: Optional[Literal["url", "b64_json"]] = Field(
        default=None,
        description="Prefer url so generated music can be used directly by apps.",
    )
    negative_prompt: Optional[str] = Field(default=None, description="Elements to avoid. Lyria-only/preferred.")
    seed: Optional[int] = Field(default=None, description="Random seed. Lyria-only/preferred.")
    lyrics: Optional[str] = Field(default=None, description="Lyrics text. Minimax-only/preferred.")
    audio_format: Optional[str] = Field(default=None, description="mp3 / wav / flac. Minimax-only/preferred.")
    sample_rate: Optional[int] = Field(default=None, description="Sample rate. Minimax-only/preferred.")
    bitrate: Optional[int] = Field(default=None, description="Bitrate. Minimax-only/preferred.")
    voice_id: Optional[str] = Field(default=None, description="Voice id. Minimax-only/preferred.")

    @model_validator(mode="after")
    def validate_filename(self) -> "MusicGenerationRequest":
        if not Path(self.filename).suffix:
            raise ValueError('filename must include extension (e.g., "teaser_bgm.wav")')
        return self


class MusicCreator(BaseModel):
    """Tool for generating music/BGM assets via async task API."""

    api_key: str = Field(default_factory=lambda: Config.default().multimodal.music_generation.api_key)
    base_url: str = Field(default_factory=lambda: Config.default().multimodal.music_generation.base_url)
    model: str = Field(default_factory=lambda: Config.default().multimodal.music_generation.model)
    allowed_models: list[str] = Field(default_factory=lambda: Config.default().multimodal.music_generation.allowed_models)
    response_format: str = Field(
        default_factory=lambda: Config.default().multimodal.music_generation.response_format
    )
    max_concurrency: int = Field(
        default_factory=lambda: getattr(Config.default().multimodal.music_generation, "max_concurrency", 4)
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
    def _build_payload(req: MusicGenerationRequest, model: str, response_format: str) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": model,
            "prompt": req.prompt,
            "n": req.n,
            "response_format": req.response_format or response_format,
            "filename": normalize_request_filename(req.filename),
        }
        for key in (
            "negative_prompt",
            "seed",
            "lyrics",
            "audio_format",
            "sample_rate",
            "bitrate",
            "voice_id",
        ):
            value = getattr(req, key)
            if value is not None:
                payload[key] = value
        return payload

    async def _submit_one_async(self, req: MusicGenerationRequest) -> dict:
        """Submit a single music task to POST /v1/audio/music/async."""
        model = validate_allowed_model(req.model or self.model, self.allowed_models, "music generation")
        payload = self._build_payload(req, model, self.response_format)

        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        logger.info(f"Submitting async music task: {req.filename}")
        data = await apost(
            url=f"{self.base_url.rstrip('/')}/audio/music/async",
            json=payload,
            headers=headers,
            timeout=300,
            as_json=True,
            raise_for_status=True,
        )

        task_id = data.get("id") or data.get("task_id") or ""
        status = data.get("status") or "queued"
        pre_urls = data.get("pre_urls") or []

        if not task_id:
            raise RuntimeError("Async music API returned empty task_id")

        return {
            "task_id": task_id,
            "status": status,
            "filename": req.filename,
            "pre_urls": pre_urls,
            "_req": req,
            "_meta": {
                "prompt": req.prompt,
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
                ) else str(task_obj.get("error", "Music generation failed"))
                raise RuntimeError(error_msg or "Music generation failed")
            if waited >= float(self.max_poll_seconds):
                raise TimeoutError(f"Music generation timeout after {self.max_poll_seconds}s (task_id={task_id})")
            await asyncio.sleep(float(self.poll_interval_seconds))
            waited += float(self.poll_interval_seconds)

    async def _poll_task_with_resubmit(self, item: dict) -> dict:
        """Poll a task until complete; on rate-limit failure, resubmit with backoff."""
        return await poll_task_with_resubmit(
            item,
            poll_fn=self._poll_task_until_complete,
            submit_fn=self._submit_one_async,
            max_task_retries=self.max_task_retries,
            media_label="Music",
        )

    @staticmethod
    def _collect_outputs(task_obj: dict) -> list[dict[str, Any]]:
        """Extract per-sample outputs (url or b64_json) from a completed task object."""
        outputs: list[dict[str, Any]] = []
        urls = task_obj.get("urls") or []
        if not urls and task_obj.get("url"):
            urls = [task_obj["url"]]
        for url in urls:
            if isinstance(url, str) and url:
                outputs.append({"url": url, "b64_json": ""})
        b64 = task_obj.get("b64_json")
        if not outputs and isinstance(b64, str) and b64:
            outputs.append({"url": "", "b64_json": b64})
        return outputs

    @staticmethod
    def _sample_filename(filename: str, index: int) -> str:
        if index == 0:
            return filename
        stem = Path(filename).stem
        suffix = Path(filename).suffix
        return f"{stem}_{index}{suffix}"

    async def _finalize_one(self, item: dict, task_obj: dict) -> list[dict[str, Any]]:
        """Archive, report, and probe each output sample of a completed task."""
        filename = item["filename"]
        meta = item["_meta"]
        outputs = self._collect_outputs(task_obj)
        if not outputs:
            raise RuntimeError("Music generation completed but returned no url/b64_json")

        model = task_obj.get("model") or meta["model"]
        results: list[dict[str, Any]] = []
        for index, out in enumerate(outputs):
            url = out["url"]
            b64_json = out["b64_json"]
            sample_filename = self._sample_filename(filename, index)
            result = {
                "status": "success",
                "path": url,
                "absolute_path": url,
                "url": url,
                "b64_json": b64_json,
                "message": "Music generated successfully." if url else "Music generated successfully as base64.",
                "filename": sample_filename,
                "prompt": meta["prompt"],
                "model": model,
                "format": task_obj.get("format"),
                "duration": None,
                "seed": task_obj.get("seed"),
            }
            annotate_resubmit_result(result, item, "music")

            archive_path = ""
            if url:
                logger.info(f"Music created (CDN): {url}")
                try:
                    archive_info = await archive_cdn_media(
                        working_dir=self.working_dir,
                        media_dir="music",
                        url=url,
                        timeout=max(self.max_poll_seconds, 300),
                        fallback_filename=sample_filename,
                        is_overview_asset=is_overview_asset_context(),
                    )
                    archive_path = archive_info["workspace_absolute_path"]
                    result["filename"] = archive_info["filename"]
                    logger.info(f"Music archived to workspace: {archive_path}")
                except Exception as e:
                    logger.warning(
                        f"Music archive skipped for CDN URL {url}: {type(e).__name__}: {str(e)}"
                    )

            report_item = {
                "filename": result["filename"],
                "status": "success",
                "artifact_type": "music",
                "data_name": "inline_audio",
                "path": url or b64_json,
                "asset_type": "music",
            }
            if archive_path:
                report_item["local_path"] = archive_path
            await self.artifacts_reporter.async_report(report_item, "object")

            result["duration"] = await probe_media_duration_seconds(
                local_path=archive_path or None,
                url=url,
                timeout=30,
            )
            results.append(result)
        return results

    async def _poll_and_finalize_music(
        self,
        pending_items: list[dict],
        *,
        initial_failed_results: Optional[list[dict]] = None,
    ) -> str:
        """Poll all pending music tasks until complete, then archive and report.

        This coroutine is handed to BgTaskResult.poll and runs inside BackgroundTaskPool.
        """
        results: list[dict] = list(initial_failed_results or [])
        for item in pending_items:
            filename = item["filename"]
            try:
                task_obj = await self._poll_task_with_resubmit(item)
                results.extend(await self._finalize_one(item, task_obj))
            except Exception as e:
                logger.error(
                    f"Music poll/finalize failed for '{filename}': {type(e).__name__}: {str(e)}"
                )
                await self.artifacts_reporter.async_report(
                    {"filename": filename, "status": "failed", "artifact_type": "music"},
                    "object",
                )
                results.append({
                    "status": "failed",
                    "filename": filename,
                    "url": "",
                    "message": f"Music generation failed: {type(e).__name__}: {str(e)}",
                })

        success = [r for r in results if r.get("status") == "success"]
        summary_parts = [f"{len(success)}/{len(results)} music tracks generated."]
        failed = [r for r in results if r.get("status") != "success"]
        if failed:
            summary_parts.append("Failed: " + ", ".join(r.get("filename", "?") for r in failed))
        return json.dumps({"summary": " ".join(summary_parts), "results": results}, ensure_ascii=False)

    async def generate_music(self, tracks: list[dict], **_: object) -> BgTaskResult:
        """Generate music tracks: submit all tasks immediately via async API, return pre_urls,
        then poll remaining in background.

        Note:
            A maximum of MAX_MUSIC_BATCH_SIZE tracks can be submitted per call.

        Args:
            tracks: A list of music generation requests. Each item is a dict with:
                - prompt: str, required, music style/theme prompt.
                - filename: str, required, logical output filename with extension.
                - model: str, optional, default from `multimodal.music_generation.model`.
                - n: int, optional, 1-4.
                - response_format: "url" or "b64_json", default from config.
                - negative_prompt, seed: optional Lyria parameters.
                - lyrics, audio_format, sample_rate, bitrate, voice_id: optional Minimax parameters.

        Returns:
            BgTaskResult: Immediate result with submitted task IDs and pre_urls;
                pending tasks are polled in the background and the agent
                receives a notification when all complete. Successful items may
                include measured `duration` in seconds, or `null` if probing failed.
        """
        if tracks and len(tracks) > MAX_MUSIC_BATCH_SIZE:
            return BgTaskResult(
                result={
                    "status": "failed",
                    "message": (
                        "Too many music tracks. Please keep to a minimal number and retry. "
                        f"You submitted {len(tracks)}."
                    ),
                    "requested_count": len(tracks),
                    "max_batch_size": MAX_MUSIC_BATCH_SIZE,
                },
                poll=None,
            )

        requested: list[MusicGenerationRequest] = []
        invalid_results: list[dict] = []
        for item in tracks or []:
            try:
                if isinstance(item, MusicGenerationRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(MusicGenerationRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid music generation request ignored: {item}, err={e}")
                invalid_results.append(
                    {
                        "status": "failed",
                        "filename": item.get("filename", "") if isinstance(item, dict) else "",
                        "url": "",
                        "message": f"Invalid music generation request: {type(e).__name__}: {e}",
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
                        f"All {len(invalid_results)} music generation requests were invalid."
                        if invalid_results
                        else "No music tracks to generate."
                    ),
                }
            )

        # Report running status before starting generation
        for req in requested:
            await self.artifacts_reporter.async_report(
                {"filename": req.filename, "status": "running", "artifact_type": "music"},
                "object",
            )

        # ---- Async submit phase ----
        submit_results: list[dict] = []
        submit_errors: list[dict] = list(invalid_results)

        async def _safe_submit(req: MusicGenerationRequest) -> dict:
            try:
                return await self._submit_one_async(req)
            except Exception as e:
                logger.error(
                    f"Music submit failed for '{req.filename}': {type(e).__name__}: {str(e)}"
                )
                await self.artifacts_reporter.async_report(
                    {"filename": req.filename, "status": "failed", "artifact_type": "music"},
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
            if item["status"] == "completed":
                try:
                    task_obj = await self._retrieve_task(item["task_id"])
                    done_results.extend(await self._finalize_one(item, task_obj))
                except Exception as e:
                    logger.warning(f"Finalize failed for already-completed {item['task_id']}: {e}")
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
                    f"All {len(done_results)} music tracks generated."
                    if done_results
                    else f"All {len(submit_errors)} submissions failed."
                )
            ),
        }

        if not pending_items:
            return BgTaskResult(result=immediate)

        # ---- Async phase: hand remaining to background poll ----
        poll = self._poll_and_finalize_music(
            pending_items,
            initial_failed_results=submit_errors,
        )
        return BgTaskResult(result=immediate, poll=poll, command_name="generate music")


SKILL = "music-generation"


def execute(request: dict):
    creator = MusicCreator(working_dir=str(Path.cwd()))
    return SkillScriptExecution.from_runtime(
        creator, creator.generate_music(tracks=request.get("tracks", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
