#!/usr/bin/env python3
"""
Audio transcription tool: Converts audio to text using OpenAI SDK standard API.

Description:
- Supports local files (absolute path) and remote http(s) URLs.
- Returns transcription text directly, without writing files to disk.
"""

from __future__ import annotations

import asyncio
import io
import json
from pathlib import Path
from typing import Optional

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel, Field, PrivateAttr, model_validator
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from metagpt.config2 import Config
from metagpt.logs import logger
from metagpt.utils.ahttp_client import aget_bytes
from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script


class EmptyResponseError(RuntimeError):
    """Empty/invalid response that should be retried."""


class AudioTranscriptionRequest(BaseModel):
    """Single audio transcription request."""

    audio: str = Field(..., description="Audio source (absolute path or http(s) URL).")
    model: Optional[str] = Field(default=None, description="STT model name. If not specified, uses configured default.")


class AudioTranscriber(BaseModel):
    """Tool for transcribing audio to text (STT)."""

    api_key: str = Field(default_factory=lambda: Config.default().multimodal.audio_transcription.api_key)
    base_url: str = Field(default_factory=lambda: Config.default().multimodal.audio_transcription.base_url)

    model: str = Field(default_factory=lambda: Config.default().multimodal.audio_transcription.model)

    max_concurrency: int = Field(
        default_factory=lambda: getattr(Config.default().multimodal.audio_transcription, "max_concurrency", 4)
    )

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
    async def _create_transcription(self, client: AsyncOpenAI, params: dict) -> str:
        """Create transcription (with retry)."""
        resp = await client.audio.transcriptions.create(**params)  # type: ignore[arg-type]
        logger.debug(f"Platform transcription response: {resp}")
        if resp is None:
            raise EmptyResponseError("Empty response from transcription API")

        text = self._extract_text(resp)
        if not text:
            raise EmptyResponseError("Transcription completed but missing text in response.")
        return text

    @staticmethod
    def _get_source_name(audio_ref: str) -> str:
        """Get a readable display name from audio source."""
        ref = (audio_ref or "").strip()
        if ref.startswith(("http://", "https://")):
            return ref.split("?")[0].rstrip("/").split("/")[-1] or "remote_audio"
        return Path(ref).name or "local_audio"

    async def _load_audio(self, audio_ref: str) -> io.BytesIO:
        """Load audio from local path/URL and convert it to an uploadable file-like object."""
        ref = (audio_ref or "").strip()
        if not ref:
            raise ValueError("audio source is empty")

        if ref.startswith("data:"):
            raise ValueError("audio only supports local path or http(s) URL, data URI not supported")

        if ref.startswith(("http://", "https://")):
            data = await aget_bytes(url=ref, timeout=120, raise_for_status=True)
            name = self._get_source_name(ref)
            upload = io.BytesIO(data)
            upload.name = name  # type: ignore[attr-defined]
            return upload

        p = Path(ref).expanduser()
        if not p.is_absolute():
            raise ValueError("Local audio must use absolute path (or use http(s) URL instead)")
        if not p.exists() or not p.is_file():
            raise FileNotFoundError(f"Audio file not found: {str(p)}")

        upload = io.BytesIO(p.read_bytes())
        upload.name = p.name  # type: ignore[attr-defined]
        return upload

    @staticmethod
    def _extract_text(resp: object) -> Optional[str]:
        """Extract transcription text from SDK response."""
        text = getattr(resp, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()

        content = getattr(resp, "content", None)
        if isinstance(content, bytes):
            content = content.decode("utf-8", errors="ignore")
        if not isinstance(content, str) or not content.strip():
            return None

        try:
            data = json.loads(content)
        except json.JSONDecodeError:
            return None

        text = data.get("text")
        if not isinstance(text, str) or not text.strip():
            return None

        return text.strip()

    def _build_text_result(self, text: str, source: str, source_name: str, model: str) -> dict:
        """Build a normalized transcription result."""
        logger.info(f"Audio transcribed: {source_name}")
        return {
            "status": "success",
            "text": text,
            "audio": source,
            "source_name": source_name,
            "message": "Audio transcribed successfully.",
            "model": model,
        }

    async def _transcribe_one(self, req: AudioTranscriptionRequest) -> dict:
        """Transcribe a single audio request."""
        source_name = self._get_source_name(req.audio)
        model = req.model or self.model

        logger.info(f"Start transcribing audio: {source_name}")
        audio_file = await self._load_audio(req.audio)
        try:
            params: dict[str, object] = {
                "file": audio_file,
                "model": model,
                "response_format": "json",
            }

            text = await self._create_transcription(self._client, params)
        finally:
            audio_file.close()

        await self.artifacts_reporter.async_report(
            {
                "filename": source_name,
                "status": "success",
                "artifact_type": "transcription",
                "data_name": "inline_text",
                "text": text,
                "source": req.audio,
            },
            "object",
        )
        return self._build_text_result(
            text=text,
            source=req.audio,
            source_name=source_name,
            model=model,
        )

    async def transcribe_audios(self, audios: list[dict], **_: object) -> dict:
        """Transcribe multiple audio inputs concurrently.

        Args:
            audios: A list of transcription requests. Each item is a dict with:
                - audio: str, required, audio source (absolute path or http(s) URL)
                - model: str, optional, STT model name. If not specified, uses configured default.

        Returns:
            dict: Batch result summary with per-audio transcription results.

        Example:
            audios = [
                {"audio": "https://example.com/demo.mp3"},
                {"audio": "/abs/path/meeting.wav", "model": "gpt-4o-transcribe"}
            ]
            result = await transcribe_audios(audios)
            text = result["results"][0]["text"]
        """
        requested: list[AudioTranscriptionRequest] = []
        for item in audios or []:
            try:
                if isinstance(item, AudioTranscriptionRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(AudioTranscriptionRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid audio transcription request ignored: {item}, err={e}")

        if not requested:
            return {
                "status": "success",
                "results": [],
                "success_count": 0,
                "failed_count": 0,
                "message": "No audios to transcribe.",
            }

        for req in requested:
            await self.artifacts_reporter.async_report(
                {
                    "filename": self._get_source_name(req.audio),
                    "status": "running",
                    "artifact_type": "transcription",
                },
                "object",
            )

        sem = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(req: AudioTranscriptionRequest) -> dict:
            source_name = self._get_source_name(req.audio)
            async with sem:
                try:
                    return await self._transcribe_one(req)
                except Exception as e:
                    logger.error(
                        f"Audio transcription failed for '{source_name}': {type(e).__name__}: {str(e)}",
                        exc_info=True,
                    )
                    await self.artifacts_reporter.async_report(
                        {
                            "filename": source_name,
                            "status": "failed",
                            "artifact_type": "transcription",
                        },
                        "object",
                    )
                    return {
                        "status": "failed",
                        "text": "",
                        "audio": req.audio,
                        "source_name": source_name,
                        "message": f"Audio transcription failed: {type(e).__name__}: {str(e)}",
                        "error_type": type(e).__name__,
                    }

        results = await asyncio.gather(*[_run_one(r) for r in requested])
        failed = [r for r in results if r.get("status") != "success"]
        status = "success" if not failed else ("failed" if len(failed) == len(results) else "partial_success")

        return {
            "status": status,
            "results": results,
            "success_count": len(results) - len(failed),
            "failed_count": len(failed),
            "message": f"Transcribed {len(results) - len(failed)}/{len(results)} audios",
        }

SKILL = "audio-transcription"


def execute(request: dict):
    transcriber = AudioTranscriber()
    return SkillScriptExecution.from_runtime(
        transcriber, transcriber.transcribe_audios(audios=request.get("audios", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
