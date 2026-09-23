#!/usr/bin/env python3
"""Render diagram DSLs through Kroki into project-local SVG or PNG assets."""

from __future__ import annotations

import asyncio
from pathlib import Path, PurePosixPath
from typing import Optional

import aiohttp
from pydantic import BaseModel, Field, field_validator
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from metagpt.config2 import Config
from metagpt.logs import logger
from metagpt.utils.report import ArtifactsReporter
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script


class EmptyResponseError(RuntimeError):
    """Empty response that should be retried."""


class RetryableKrokiHTTPError(aiohttp.ClientError):
    """Kroki HTTP error that should be retried."""


class ChartGenerationRequest(BaseModel):
    """Single chart or diagram render request."""

    diagram_type: str = Field(
        ...,
        description="Kroki diagram type, for example: mermaid, plantuml, d2, graphviz.",
    )
    code: str = Field(
        ...,
        description="Raw diagram source code to render. Preserve DSL syntax exactly as written.",
    )
    filename: str = Field(
        ...,
        description='Target filename, for example "architecture.svg" or "uml/sequence.png".',
    )
    output_format: str = Field(
        default="svg",
        description="Output format. Supported values: svg, png. Prefer svg for frontend embedding.",
    )

    @field_validator("diagram_type")
    @classmethod
    def validate_diagram_type(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if not normalized:
            raise ValueError("diagram_type cannot be empty")
        return normalized

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not (value or "").strip():
            raise ValueError("code cannot be empty")
        return value

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value: str) -> str:
        normalized = (value or "").strip()
        if not normalized:
            raise ValueError("filename cannot be empty")
        return normalized

    @field_validator("output_format")
    @classmethod
    def validate_output_format(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"svg", "png"}:
            raise ValueError("output_format must be svg or png")
        return normalized


class ChartRenderer(BaseModel):
    """Render diagrams through Kroki and save them in the current project."""

    base_url: str = Field(
        default_factory=lambda: Config.default().multimodal.chart_generation.base_url or "https://kroki.io"
    )
    timeout_seconds: int = Field(default_factory=lambda: Config.default().multimodal.chart_generation.timeout_seconds)
    max_concurrency: int = Field(default_factory=lambda: Config.default().multimodal.chart_generation.max_concurrency)
    subdir_path: str = Field(default="public/assets/charts")
    working_dir: Optional[str] = Field(default=None, exclude=True)
    artifacts_reporter: ArtifactsReporter = Field(default_factory=ArtifactsReporter)

    @retry(
        reraise=True,
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, max=10),
        retry=retry_if_exception_type(
            (aiohttp.ClientError, asyncio.TimeoutError, ConnectionError, EmptyResponseError)
        ),
    )
    async def _render_chart_bytes(self, diagram_type: str, code: str, output_format: str) -> bytes:
        url = f"{self.base_url.rstrip('/')}/{diagram_type}/{output_format}"
        timeout = aiohttp.ClientTimeout(total=self.timeout_seconds)

        async with aiohttp.ClientSession(timeout=timeout, trust_env=True) as session:
            async with session.post(
                url,
                data=code.encode("utf-8"),
                headers={"Content-Type": "text/plain; charset=utf-8"},
            ) as response:
                if response.status >= 400:
                    error_text = await response.text()
                    if response.status == 429 or response.status >= 500:
                        raise RetryableKrokiHTTPError(f"Kroki HTTP {response.status}: {error_text}")
                    raise RuntimeError(f"Kroki HTTP {response.status}: {error_text}")

                payload = await response.read()
                if not payload:
                    raise EmptyResponseError("Empty response from Kroki")
                return payload

    def _normalize_output_filename(self, filename: str, output_format: str) -> Path:
        normalized_input = (filename or "").strip().replace("\\", "/")
        candidate = PurePosixPath(normalized_input)
        if candidate.is_absolute():
            raise ValueError("filename must be relative to the chart asset directory")

        parts = tuple(part for part in candidate.parts if part not in ("", "."))
        if not parts:
            raise ValueError("filename cannot be empty")
        if any(part == ".." for part in parts):
            raise ValueError("filename must not contain parent directory traversal")

        candidate = PurePosixPath(*parts)
        if candidate.suffix:
            suffix = candidate.suffix.lstrip(".").lower()
            if suffix != output_format:
                raise ValueError("filename extension must match output_format")
            return Path(*candidate.parts)

        return Path(*candidate.with_suffix(f".{output_format}").parts)

    def _resolve_output_path(self, filename: str, output_format: str) -> tuple[str, Path]:
        if not self.working_dir:
            raise RuntimeError("working_dir not set for ChartRenderer")

        normalized = self._normalize_output_filename(filename, output_format)
        output_path = Path(self.working_dir) / self.subdir_path / normalized
        output_path.parent.mkdir(parents=True, exist_ok=True)
        relative_path = (Path(self.subdir_path) / normalized).as_posix()
        return relative_path, output_path

    @staticmethod
    def _to_frontend_path(relative_path: str) -> str:
        normalized = relative_path.replace("\\", "/")
        if normalized.startswith("public/"):
            return "/" + normalized[len("public/") :]
        return normalized

    def _build_local_result(self, relative_path: str, output_path: Path, filename: str) -> dict:
        logger.info(f"Chart created: {output_path}")
        return {
            "status": "success",
            "filename": filename,
            "path": relative_path,
            "absolute_path": str(output_path),
            "url": self._to_frontend_path(relative_path),
        }

    @staticmethod
    def _build_failed_result(filename: str, error: Exception, invalid_request: bool = False) -> dict:
        prefix = "Invalid chart generation request" if invalid_request else "Chart generation failed"
        return {
            "status": "failed",
            "filename": filename,
            "message": f"{prefix}: {type(error).__name__}: {str(error)}",
            "error_type": type(error).__name__,
        }

    async def _generate_one(self, req: ChartGenerationRequest) -> dict:
        relative_path, output_path = self._resolve_output_path(req.filename, req.output_format)
        normalized_filename = output_path.relative_to(Path(self.working_dir) / self.subdir_path).as_posix()

        logger.info(f"Start rendering chart: {normalized_filename} ({req.diagram_type}/{req.output_format})")
        payload = await self._render_chart_bytes(req.diagram_type, req.code, req.output_format)
        output_path.write_bytes(payload)

        result = self._build_local_result(relative_path, output_path, normalized_filename)
        await self.artifacts_reporter.async_report(
            {
                "filename": normalized_filename,
                "status": "success",
                "artifact_type": "chart_image",
                "data_name": "path",
                "path": str(output_path),
                "image_url": "",
            },
            "object",
        )
        return result

    async def generate_charts(self, charts: list[dict], **_: object) -> dict:
        if not charts:
            return {
                "status": "success",
                "results": [],
                "success_count": 0,
                "failed_count": 0,
                "message": "No charts to generate.",
            }

        items_in_order: list[dict] = []
        valid_requests: list[ChartGenerationRequest] = []
        for item in charts:
            try:
                if isinstance(item, ChartGenerationRequest):
                    req = item
                elif isinstance(item, dict):
                    req = ChartGenerationRequest.model_validate(item)
                else:
                    raise TypeError(type(item))

                valid_requests.append(req)
                items_in_order.append({"kind": "valid", "request": req})
            except Exception as exc:
                filename = item.get("filename", "") if isinstance(item, dict) else ""
                failed_result = self._build_failed_result(
                    filename=str(filename or ""),
                    error=exc,
                    invalid_request=True,
                )
                logger.warning(f"Invalid chart generation request: {item}, err={exc}")
                items_in_order.append({"kind": "invalid", "result": failed_result})
                await self.artifacts_reporter.async_report(
                    {
                        "filename": failed_result["filename"] or "unknown",
                        "status": "failed",
                        "artifact_type": "chart_image",
                    },
                    "object",
                )

        for req in valid_requests:
            try:
                filename = self._normalize_output_filename(req.filename, req.output_format).as_posix()
            except Exception:
                filename = req.filename
            await self.artifacts_reporter.async_report(
                {"filename": filename, "status": "running", "artifact_type": "chart_image"},
                "object",
            )

        sem = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(req: ChartGenerationRequest) -> dict:
            async with sem:
                try:
                    return await self._generate_one(req)
                except Exception as exc:
                    normalized_filename = req.filename
                    try:
                        normalized_filename = self._normalize_output_filename(
                            req.filename, req.output_format
                        ).as_posix()
                    except Exception:
                        pass

                    logger.error(
                        f"Chart generation failed for '{normalized_filename}': "
                        f"{type(exc).__name__}: {str(exc)}",
                        exc_info=True,
                    )
                    await self.artifacts_reporter.async_report(
                        {
                            "filename": normalized_filename,
                            "status": "failed",
                            "artifact_type": "chart_image",
                        },
                        "object",
                    )
                    return self._build_failed_result(filename=normalized_filename, error=exc)

        valid_results = await asyncio.gather(*[_run_one(req) for req in valid_requests]) if valid_requests else []
        valid_iter = iter(valid_results)
        results = [next(valid_iter) if item["kind"] == "valid" else item["result"] for item in items_in_order]

        failed = [result for result in results if result.get("status") != "success"]
        status = "success" if not failed else ("failed" if len(failed) == len(results) else "partial_success")
        return {
            "status": status,
            "results": results,
            "success_count": len(results) - len(failed),
            "failed_count": len(failed),
            "message": f"Generated {len(results) - len(failed)}/{len(results)} charts",
        }

SKILL = "chart-rendering"


def execute(request: dict):
    renderer = ChartRenderer(working_dir=str(Path.cwd()))
    return SkillScriptExecution.from_runtime(
        renderer, renderer.generate_charts(charts=request.get("charts", []))
    )


def main() -> int:
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
