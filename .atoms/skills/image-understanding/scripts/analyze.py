#!/usr/bin/env python3
"""Batch image understanding tool for summary, OCR, and QA tasks."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from metagpt.config2 import Config
from metagpt.configs.llm_config import LLMConfig
from metagpt.llm import LLM
from metagpt.logs import logger
from metagpt.provider.constant import MULTI_MODAL_MODELS
from metagpt.utils.common import encode_image
from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script

IMAGE_SYSTEM_PROMPT = """You are a careful image understanding assistant.

Rules:
- Answer only from the provided image.
- Do not invent unreadable text or uncertain details.
- If any text or detail is unclear, say so explicitly.
- In OCR mode, preserve the original visible text and do not translate it.
- In QA mode, answer the user's question directly and say when the image does not support a confident answer.
- If the user explicitly requests an output format, follow it.
- Otherwise, follow the format required by the current task type.
"""

IMAGE_MODE_PROMPTS = {
    "summary": """Task type: Image understanding.
Understand the image faithfully and respond in concise plain text.
Prefer natural language. Use bullets only when they clearly improve readability.
Focus on what the image shows, including the main subject, layout or spatial relationships, charts/tables/UI states when relevant, and visible text when important and clearly legible.""",
    "ocr": """Task type: OCR.
Extract clearly legible text from the image in natural reading order as Markdown.
If the user gives a focused extraction instruction, prioritize the requested text. Otherwise, extract all clearly legible text.
Do not translate, correct, or paraphrase the text. If a fragment is unreadable, mark it as [unclear].""",
    "qa": """Task type: Visual question answering.
Understand the image and answer the user's question directly in concise plain text.
Base the answer only on what is clearly supported by the image. If the answer is uncertain or not visible, say so explicitly.""",
}


class ImageAnalysisRequest(BaseModel):
    """Single image analysis request."""

    image_path: str = Field(..., description="Image source: absolute local path or http(s) URL.")
    mode: Literal["summary", "ocr", "qa"] = Field(default="summary", description="Analysis mode: summary, ocr, or qa.")
    instruction: str = Field(
        default="",
        description="Optional extra instruction or question about the image. Required when mode is qa.",
    )


class ImageAnalyzer(BaseModel):
    """Tool for concurrent image summary, OCR, and QA."""

    base_url: str = Field(default_factory=lambda: Config.default().multimodal.image_understanding.base_url)
    api_key: str = Field(default_factory=lambda: Config.default().multimodal.image_understanding.api_key)
    model: str = Field(default_factory=lambda: Config.default().multimodal.image_understanding.model)
    temperature: float = Field(default_factory=lambda: Config.default().multimodal.image_understanding.temperature)
    max_token: int = Field(default_factory=lambda: Config.default().multimodal.image_understanding.max_token)
    timeout: int = Field(default_factory=lambda: Config.default().multimodal.image_understanding.timeout)
    max_concurrency: int = Field(
        default_factory=lambda: getattr(Config.default().multimodal.image_understanding, "max_concurrency", 4)
    )
    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    def _build_llm_config(self) -> LLMConfig:
        """Build a dedicated LLM config for image understanding."""
        base_llm_config = Config.default().llm
        return base_llm_config.model_copy(
            update={
                "model": self.model or base_llm_config.model,
                "base_url": self.base_url or base_llm_config.base_url,
                "api_key": self.api_key or base_llm_config.api_key,
                "temperature": self.temperature,
                "max_token": self.max_token,
                "timeout": self.timeout,
            }
        )

    def _normalize_image_path(self, image_path: str) -> str:
        image_path = (image_path or "").strip()
        if not image_path:
            raise ValueError("image_path is required for image analysis.")

        if image_path.startswith(("http://", "https://")):
            return image_path

        path = Path(image_path).expanduser()
        if not path.is_absolute():
            raise ValueError("Local image must use absolute path (or use http(s) URL instead).")
        return str(path.resolve(strict=False))

    @staticmethod
    def _get_source_name(image_path: str) -> str:
        if image_path.startswith(("http://", "https://")):
            return image_path.split("?")[0].rstrip("/").split("/")[-1] or "remote_image"
        return Path((image_path or "").strip()).expanduser().name or "image"

    @staticmethod
    def _supports_image_input(model: str) -> bool:
        normalized = (model or "").lower()
        return any(keyword in normalized for keyword in MULTI_MODAL_MODELS)

    @staticmethod
    def _build_user_prompt(mode: Literal["summary", "ocr", "qa"], instruction: str = "") -> str:
        prompt = IMAGE_MODE_PROMPTS[mode]
        if instruction and instruction.strip():
            prompt += f"\n\nUser instruction:\n{instruction.strip()}"
        return prompt

    @staticmethod
    def _build_success_message(mode: Literal["summary", "ocr", "qa"], instruction: str = "") -> str:
        if mode == "ocr":
            return "Image OCR completed successfully."
        if mode == "qa":
            return "Image question answered successfully."
        if instruction and instruction.strip():
            return "Image analysis completed successfully."
        return "Image summarized successfully."

    @staticmethod
    def _build_result(
        *,
        status: str,
        image_path: str,
        mode: str,
        instruction: str,
        model: str,
        result: str,
        message: str,
        error_type: str = "",
    ) -> dict:
        payload = {
            "status": status,
            "result": result,
            "image_path": image_path,
            "mode": mode,
            "instruction": instruction,
            "model": model,
            "message": message,
        }
        if error_type:
            payload["error_type"] = error_type
        return payload

    @staticmethod
    def _extract_raw_request_fields(item: object) -> tuple[str, str, str]:
        if not isinstance(item, dict):
            return "", "summary", ""

        raw_image_path = item.get("image_path")
        raw_mode = item.get("mode")
        raw_instruction = item.get("instruction")
        image_path = "" if raw_image_path is None else str(raw_image_path).strip()
        mode = "summary" if raw_mode is None else str(raw_mode).strip() or "summary"
        instruction = "" if raw_instruction is None else str(raw_instruction).strip()
        return image_path, mode, instruction

    def _get_report_source(self, image_path: str) -> str:
        try:
            return self._normalize_image_path(image_path)
        except Exception:
            return (image_path or "").strip()

    def _validate_request_context(self, req: ImageAnalysisRequest, resolved_path: str, model: str) -> None:
        if req.mode == "qa" and not req.instruction.strip():
            raise ValueError("instruction is required when mode is qa.")
        if not self._supports_image_input(model):
            raise ValueError("ImageAnalyzer requires a multimodal model that supports image input.")

        if resolved_path.startswith(("http://", "https://")):
            return

        path = Path(resolved_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"Image file not found: {resolved_path}")

    async def _report_status(
        self,
        req: ImageAnalysisRequest,
        status: Literal["running", "success", "failed"],
        resolved_path: str = "",
        text: str = "",
    ) -> None:
        source = self._get_report_source(resolved_path or req.image_path)
        payload = {
            "filename": self._get_source_name(source or req.image_path),
            "status": status,
            "artifact_type": "image_understanding",
            "mode": req.mode,
        }
        if source:
            payload["source"] = source
        if req.instruction.strip():
            payload["instruction"] = req.instruction.strip()
        if status == "success":
            payload.update({"data_name": "inline_text", "text": text})
        await self.artifacts_reporter.async_report(payload, "object")

    async def _report_invalid_request(
        self,
        *,
        image_path: str,
        mode: str,
        instruction: str,
    ) -> None:
        source = self._get_report_source(image_path)
        payload = {
            "filename": self._get_source_name(source or image_path),
            "status": "failed",
            "artifact_type": "image_understanding",
            "mode": mode,
        }
        if source:
            payload["source"] = source
        if instruction:
            payload["instruction"] = instruction
        await self.artifacts_reporter.async_report(payload, "object")

    async def _analyze_one(self, req: ImageAnalysisRequest) -> dict:
        llm_config = self._build_llm_config()
        model = llm_config.model or self.model or ""
        resolved_path = self._normalize_image_path(req.image_path)
        self._validate_request_context(req, resolved_path, model)

        image_input = (
            resolved_path if resolved_path.startswith(("http://", "https://")) else encode_image(resolved_path)
        )
        llm = LLM(llm_config=llm_config)
        result = await llm.aask(
            msg=self._build_user_prompt(req.mode, req.instruction),
            system_msgs=[IMAGE_SYSTEM_PROMPT],
            images=[image_input],
            timeout=self.timeout,
            stream=True,
        )
        if not result or not result.strip():
            raise RuntimeError("Image analysis returned an empty result.")

        result_text = result.strip()
        await self._report_status(req, status="success", resolved_path=resolved_path, text=result_text)
        return self._build_result(
            status="success",
            image_path=resolved_path,
            mode=req.mode,
            instruction=req.instruction.strip(),
            model=model,
            result=result_text,
            message=self._build_success_message(req.mode, req.instruction),
        )

    async def analyze_images(self, images: list[dict], **_: object) -> dict:
        """Analyze multiple images concurrently.

        Args:
            images: A list of image analysis requests. Each item is a dict with:
                - image_path: str, required, absolute local image path or http(s) URL
                - mode: str, optional, "summary", "ocr", or "qa" (default: "summary")
                - instruction: str, optional for summary/ocr, required for qa

        Returns:
            dict: Batch result summary with per-image results.
        """
        if not images:
            return {
                "status": "success",
                "results": [],
                "success_count": 0,
                "failed_count": 0,
                "message": "No images to analyze.",
            }

        configured_model = self._build_llm_config().model or self.model or ""
        requested: list[ImageAnalysisRequest] = []
        prepared_items: list[ImageAnalysisRequest | dict] = []
        for item in images:
            try:
                if isinstance(item, ImageAnalysisRequest):
                    req = item
                elif isinstance(item, dict):
                    req = ImageAnalysisRequest.model_validate(item)
                else:
                    raise TypeError(type(item))
                requested.append(req)
                prepared_items.append(req)
            except Exception as e:
                image_path, mode, instruction = self._extract_raw_request_fields(item)
                message = f"Invalid image analysis request: {type(e).__name__}: {str(e)}"
                logger.warning(f"{message}. raw={item}")
                await self._report_invalid_request(
                    image_path=image_path,
                    mode=mode,
                    instruction=instruction,
                )
                prepared_items.append(
                    self._build_result(
                        status="failed",
                        image_path=self._get_report_source(image_path),
                        mode=mode,
                        instruction=instruction,
                        model=configured_model,
                        result="",
                        message=message,
                        error_type=type(e).__name__,
                    )
                )

        for req in requested:
            await self._report_status(req, status="running")

        sem = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(req: ImageAnalysisRequest) -> dict:
            async with sem:
                resolved_path = (req.image_path or "").strip()
                try:
                    resolved_path = str(self._normalize_image_path(req.image_path))
                    return await self._analyze_one(req)
                except Exception as e:
                    log_fn = logger.warning if isinstance(e, (ValueError, FileNotFoundError)) else logger.error
                    log_fn(
                        f"Image analysis failed for '{resolved_path}': {type(e).__name__}: {str(e)}",
                        exc_info=not isinstance(e, (ValueError, FileNotFoundError)),
                    )
                    message = f"Image analysis failed: {type(e).__name__}: {str(e)}"
                    await self._report_status(
                        req,
                        status="failed",
                        resolved_path=resolved_path,
                    )
                    return self._build_result(
                        status="failed",
                        image_path=resolved_path,
                        mode=req.mode,
                        instruction=req.instruction.strip(),
                        model=configured_model,
                        result="",
                        message=message,
                        error_type=type(e).__name__,
                    )

        analyzed_results = await asyncio.gather(*[_run_one(req) for req in requested]) if requested else []
        analyzed_iter = iter(analyzed_results)
        results = [next(analyzed_iter) if isinstance(item, ImageAnalysisRequest) else item for item in prepared_items]
        failed = [result for result in results if result.get("status") != "success"]
        status = "success" if not failed else ("failed" if len(failed) == len(results) else "partial_success")
        return {
            "status": status,
            "results": results,
            "success_count": len(results) - len(failed),
            "failed_count": len(failed),
            "message": f"Processed {len(results) - len(failed)}/{len(results)} image requests",
        }

SKILL = "image-understanding"


def execute(request: dict):
    analyzer = ImageAnalyzer()
    return SkillScriptExecution.from_runtime(
        analyzer, analyzer.analyze_images(images=request.get("images", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
