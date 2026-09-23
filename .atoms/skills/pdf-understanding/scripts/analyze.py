#!/usr/bin/env python3
"""Batch PDF understanding tool backed by a dedicated Claude model."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import Literal, Optional

import fitz
from pydantic import BaseModel, Field

from metagpt.config2 import Config
from metagpt.configs.llm_config import LLMConfig
from metagpt.llm import LLM
from metagpt.logs import logger
from metagpt.utils.common import pdfs_within_limits
from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script

PDF_SYSTEM_PROMPT = """You are a careful PDF analysis assistant.

Rules:
- Answer only from the attached PDF.
- If the PDF does not contain the requested information, say so clearly.
- Do not invent or infer unsupported facts.
- Mention page numbers for important facts whenever the PDF makes that possible.
- Match the user's instruction language.
"""

PDF_MODE_PROMPTS = {
    "qa": """Task type: Question answering.
Read the attached PDF and answer the user's question directly, clearly, and only with information supported by the document.""",
    "extract": """Task type: Structured extraction.
Read the attached PDF and extract the requested information as concise Markdown with clear headings and bullets when helpful.""",
}

DEFAULT_PAGE_WINDOW = 80


class PdfAnalysisRequest(BaseModel):
    """Single PDF analysis request."""

    pdf_path: str = Field(..., description="Local PDF path.")
    instruction: str = Field(..., description="Question or extraction instruction for this PDF.")
    mode: Literal["qa", "extract"] = Field(default="qa", description="Analysis mode: qa or extract.")
    page_start: int = Field(default=1, description="1-based start page. Defaults to 1.")
    page_end: Optional[int] = Field(
        default=None,
        description=(
            "1-based end page. If omitted, the tool analyzes up to 80 pages starting from page_start. "
            "If it exceeds the PDF length, it is truncated to the last page."
        ),
    )


class PdfAnalyzer(BaseModel):
    """Tool for concurrent PDF question answering and structured extraction."""

    base_url: str = Field(default_factory=lambda: Config.default().multimodal.pdf_understanding.base_url)
    api_key: str = Field(default_factory=lambda: Config.default().multimodal.pdf_understanding.api_key)
    model: str = Field(default_factory=lambda: Config.default().multimodal.pdf_understanding.model)
    temperature: float = Field(default_factory=lambda: Config.default().multimodal.pdf_understanding.temperature)
    max_token: int = Field(default_factory=lambda: Config.default().multimodal.pdf_understanding.max_token)
    timeout: int = Field(default_factory=lambda: Config.default().multimodal.pdf_understanding.timeout)
    max_concurrency: int = Field(
        default_factory=lambda: getattr(Config.default().multimodal.pdf_understanding, "max_concurrency", 4)
    )
    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    def _build_llm_config(self) -> LLMConfig:
        """Build a dedicated LLM config for PDF understanding."""
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

    @staticmethod
    def _normalize_pdf_path(pdf_path: str) -> Path:
        return Path((pdf_path or "").strip()).expanduser().resolve(strict=False)

    @staticmethod
    def _get_source_name(pdf_path: str) -> str:
        return Path((pdf_path or "").strip()).expanduser().name or "document.pdf"

    @staticmethod
    def _is_claude_model(model: str) -> bool:
        return "claude" in (model or "").lower()

    @staticmethod
    def _build_user_prompt(instruction: str, mode: Literal["qa", "extract"]) -> str:
        return f"""{PDF_MODE_PROMPTS[mode]}

User instruction:
{instruction.strip()}
"""

    def _resolve_page_range(
        total_pages: int,
        page_start: int = 1,
        page_end: Optional[int] = None,
    ) -> tuple[int, int]:
        """Resolve and validate the requested 1-based page range."""
        if total_pages <= 0:
            raise ValueError("PDF has no pages.")
        if page_start < 1:
            raise ValueError("page_start must be greater than or equal to 1.")
        if page_start > total_pages:
            raise ValueError(f"page_start {page_start} exceeds total PDF pages {total_pages}.")

        if page_end is None:
            page_end = min(total_pages, page_start + DEFAULT_PAGE_WINDOW - 1)
        else:
            page_end = min(page_end, total_pages)

        if page_end < page_start:
            raise ValueError("page_end must be greater than or equal to page_start.")

        selected_pages = page_end - page_start + 1
        if selected_pages > DEFAULT_PAGE_WINDOW:
            raise ValueError(
                f"Requested page range contains {selected_pages} pages. "
                f"The maximum supported range per request is {DEFAULT_PAGE_WINDOW} pages."
            )

        return page_start, page_end

    @classmethod
    def _encode_pdf_page_range(
        cls,
        pdf_path: Path,
        page_start: int = 1,
        page_end: Optional[int] = None,
    ) -> tuple[str, int, int, int]:
        """Extract a validated page range and encode it as base64 PDF."""
        source_doc = fitz.open(pdf_path)
        try:
            total_pages = source_doc.page_count
            start, end = cls._resolve_page_range(
                total_pages=total_pages,
                page_start=page_start,
                page_end=page_end,
            )
            subset_doc = fitz.open()
            try:
                subset_doc.insert_pdf(source_doc, from_page=start - 1, to_page=end - 1)
                subset_bytes = subset_doc.tobytes(garbage=4, deflate=True)
            finally:
                subset_doc.close()
        finally:
            source_doc.close()
        return base64.b64encode(subset_bytes).decode("utf-8"), start, end, total_pages

    @staticmethod
    def _build_success_message(page_start: int, page_end: int, total_pages: int) -> str:
        selected_range = f"page {page_start}" if page_start == page_end else f"pages {page_start}-{page_end}"
        total_label = "page" if total_pages == 1 else "pages"
        return f"PDF analyzed successfully using {selected_range} of {total_pages} total {total_label}."

    @staticmethod
    def _build_result(
        *,
        status: str,
        pdf_path: str,
        instruction: str,
        mode: str,
        model: str,
        result: str,
        message: str,
        page_start: int,
        page_end: Optional[int],
        total_pages: Optional[int] = None,
        error_type: str = "",
    ) -> dict:
        payload = {
            "status": status,
            "result": result,
            "pdf_path": pdf_path,
            "instruction": instruction,
            "mode": mode,
            "model": model,
            "message": message,
            "page_start": page_start,
            "page_end": page_end,
            "total_pages": total_pages,
        }
        if error_type:
            payload["error_type"] = error_type
        return payload

    def _validate_request_context(self, req: PdfAnalysisRequest, resolved_path: str, model: str) -> None:
        if not req.instruction or not req.instruction.strip():
            raise ValueError("instruction is required for PDF analysis.")
        if not self._is_claude_model(model):
            raise ValueError("PdfAnalyzer v1 only supports Claude models because it relies on native PDF input.")

        path = Path(resolved_path)
        if path.suffix.lower() != ".pdf":
            raise ValueError("pdf_path must point to a local PDF file.")
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"PDF file not found: {resolved_path}")

    async def _report_status(
        self,
        req: PdfAnalysisRequest,
        status: Literal["running", "success", "failed"],
        resolved_path: str = "",
        text: str = "",
        page_start: Optional[int] = None,
        page_end: Optional[int] = None,
        total_pages: Optional[int] = None,
    ) -> None:
        payload = {
            "filename": self._get_source_name(resolved_path or req.pdf_path),
            "status": status,
            "artifact_type": "pdf_analysis",
        }
        if status == "success":
            payload.update(
                {
                    "data_name": "inline_text",
                    "text": text,
                    "source": resolved_path or str(self._normalize_pdf_path(req.pdf_path)),
                    "mode": req.mode,
                    "page_start": page_start,
                    "page_end": page_end,
                    "total_pages": total_pages,
                }
            )
        await self.artifacts_reporter.async_report(payload, "object")

    async def _analyze_one(self, req: PdfAnalysisRequest) -> dict:
        llm_config = self._build_llm_config()
        model = llm_config.model or self.model or ""
        resolved_path = str(self._normalize_pdf_path(req.pdf_path))
        self._validate_request_context(req, resolved_path, model)

        pdf_b64, start, end, total_pages = self._encode_pdf_page_range(
            pdf_path=Path(resolved_path),
            page_start=req.page_start,
            page_end=req.page_end,
        )
        ok_to_attach, total_pdf_bytes, total_pdf_pages = pdfs_within_limits([pdf_b64])
        if not ok_to_attach:
            size_mb = total_pdf_bytes / 1024 / 1024
            raise ValueError(
                "PDF exceeds native attachment limits: "
                f"{size_mb:.2f}MB and {total_pdf_pages} pages "
                "(limits: 15MB total, 80 pages total)."
            )

        llm = LLM(llm_config=llm_config)
        user_prompt = self._build_user_prompt(instruction=req.instruction, mode=req.mode)
        result = await llm.aask(
            msg=user_prompt,
            system_msgs=[PDF_SYSTEM_PROMPT],
            pdfs=[pdf_b64],
            timeout=self.timeout,
            stream=True,
        )
        if not result or not result.strip():
            raise RuntimeError("PDF analysis returned an empty result.")
        result_text = result.strip()
        await self._report_status(
            req,
            status="success",
            resolved_path=resolved_path,
            text=result_text,
            page_start=start,
            page_end=end,
            total_pages=total_pages,
        )

        return self._build_result(
            status="success",
            pdf_path=resolved_path,
            instruction=req.instruction,
            mode=req.mode,
            model=model,
            result=result_text,
            message=self._build_success_message(start, end, total_pages),
            page_start=start,
            page_end=end,
            total_pages=total_pages,
        )

    async def analyze_pdfs(self, pdfs: list[dict], **_: object) -> dict:
        """Analyze multiple local PDFs concurrently.

        Args:
            pdfs: A list of PDF analysis requests. Each item is a dict with:
                - pdf_path: str, required, local PDF path
                - instruction: str, required, question or extraction instruction
                - mode: str, optional, "qa" or "extract" (default: "qa")
                - page_start: int, optional, 1-based start page (default: 1)
                - page_end: int, optional, 1-based end page. If omitted, analyze up to 80 pages from page_start.
                  Values beyond the PDF length are truncated to the last page.

        Returns:
            dict: Batch result summary with per-PDF results.
        """
        requested: list[PdfAnalysisRequest] = []
        for item in pdfs or []:
            try:
                if isinstance(item, PdfAnalysisRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(PdfAnalysisRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid PDF analysis request ignored: {item}, err={e}")

        if not requested:
            return {
                "status": "success",
                "results": [],
                "success_count": 0,
                "failed_count": 0,
                "message": "No PDFs to analyze.",
            }

        for req in requested:
            await self._report_status(req, status="running")

        sem = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(req: PdfAnalysisRequest) -> dict:
            async with sem:
                model = self._build_llm_config().model or self.model or ""
                resolved_path = str(self._normalize_pdf_path(req.pdf_path))
                try:
                    return await self._analyze_one(req)
                except Exception as e:
                    error_message = f"PDF analysis failed for '{resolved_path}': {type(e).__name__}: {str(e)}"
                    if isinstance(e, (ValueError, FileNotFoundError)):
                        logger.warning(error_message)
                    else:
                        logger.opt(exception=e).error(error_message)
                    await self._report_status(req, status="failed", resolved_path=resolved_path)
                    return self._build_result(
                        status="failed",
                        pdf_path=resolved_path,
                        instruction=req.instruction,
                        mode=req.mode,
                        model=model,
                        result="",
                        message=f"PDF analysis failed: {type(e).__name__}: {str(e)}",
                        page_start=req.page_start,
                        page_end=req.page_end,
                        total_pages=None,
                        error_type=type(e).__name__,
                    )

        results = await asyncio.gather(*[_run_one(req) for req in requested])
        failed = [result for result in results if result.get("status") != "success"]
        status = "success" if not failed else ("failed" if len(failed) == len(results) else "partial_success")
        return {
            "status": status,
            "results": results,
            "success_count": len(results) - len(failed),
            "failed_count": len(failed),
            "message": f"Analyzed {len(results) - len(failed)}/{len(results)} PDFs",
        }

SKILL = "pdf-understanding"


def execute(request: dict):
    analyzer = PdfAnalyzer()
    return SkillScriptExecution.from_runtime(
        analyzer, analyzer.analyze_pdfs(pdfs=request.get("pdfs", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
