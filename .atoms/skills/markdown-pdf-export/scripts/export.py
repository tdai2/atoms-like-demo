#!/usr/bin/env python3
"""Convert local Markdown documents into print-first PDF files."""

from __future__ import annotations

import asyncio
from pathlib import Path

from pydantic import BaseModel, Field

from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script


class MarkdownPdfExporter(BaseModel):
    """Convert Markdown with browser-side MathJax and Mermaid rendering."""

    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    @staticmethod
    def _get_output_filename(markdown_path: str, output_path: str) -> str:
        from metagpt.utils.markdown_pdf import converter as converter_module

        source_name = Path(markdown_path or "document.md").expanduser().name or "document.md"
        fallback_filename = Path(source_name).with_suffix(".pdf").name
        try:
            markdown_file = Path(markdown_path or source_name).expanduser().resolve(strict=False)
            return converter_module._resolve_output_path(markdown_file, output_path).name or fallback_filename
        except Exception:
            return fallback_filename

    async def convert_file(
        self,
        markdown_path: str,
        output_path: str = "",
        title: str = "",
        enable_math: bool = True,
        enable_mermaid: bool = True,
        keep_html: bool = False,
    ) -> dict:
        from metagpt.utils.markdown_pdf import converter as converter_module

        input_path = str(Path(markdown_path).expanduser().resolve(strict=False))
        output_filename = self._get_output_filename(markdown_path, output_path)
        await self.artifacts_reporter.async_report(
            {
                "filename": output_filename,
                "status": "running",
                "artifact_type": "markdown_pdf",
            },
            "object",
        )
        try:
            artifacts = await asyncio.to_thread(
                converter_module._convert_markdown_file_to_pdf_with_details,
                markdown_path=markdown_path,
                output_path=output_path,
                title=title,
                enable_math=enable_math,
                enable_mermaid=enable_mermaid,
                keep_html=keep_html,
            )
            await self.artifacts_reporter.async_report(
                {
                    "filename": Path(artifacts.output_path).name or output_filename,
                    "status": "success",
                    "artifact_type": "markdown_pdf",
                    "data_name": "path",
                    "path": artifacts.output_path,
                },
                "object",
            )
            return {
                "status": "success",
                "input_path": artifacts.input_path,
                "output_path": artifacts.output_path,
                "html_path": artifacts.html_path,
                "message": f"Markdown PDF created successfully: {artifacts.output_path}",
            }
        except Exception as exc:
            await self.artifacts_reporter.async_report(
                {
                    "filename": output_filename,
                    "status": "failed",
                    "artifact_type": "markdown_pdf",
                },
                "object",
            )
            return {
                "status": "failed",
                "input_path": input_path,
                "output_path": "",
                "html_path": "",
                "message": str(exc),
            }

SKILL = "markdown-pdf-export"


def execute(request: dict):
    exporter = MarkdownPdfExporter()
    return SkillScriptExecution.from_runtime(
        exporter,
        exporter.convert_file(
            markdown_path=request.get("markdown_path", ""),
            output_path=request.get("output_path", ""),
            title=request.get("title", ""),
            enable_math=request.get("enable_math", True),
            enable_mermaid=request.get("enable_mermaid", True),
            keep_html=request.get("keep_html", False),
        ),
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
