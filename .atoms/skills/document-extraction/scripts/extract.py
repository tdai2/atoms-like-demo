#!/usr/bin/env python3
"""Office document extraction tool: DOCX, Excel, PPT -> Markdown.

Parsing runs in isolated subprocesses for memory/fault isolation — each document
gets its own process so that a crash or memory leak in one parser cannot affect
others or the main event loop.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import traceback
from contextlib import suppress
from pathlib import Path
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

from metagpt.logs import logger
from metagpt.utils.skill_script import SkillScriptExecution, run_skill_script

WORKER_MODE_ARG = "--worker"
WORKER_SHUTDOWN_GRACE_SECONDS = 3
MAX_OCR_IMAGES = 20
SUPPORTED_EXTENSIONS = {
    ".docx": "docx",
    ".xlsx": "excel",
    ".pptx": "ppt",
}
SUPPORTED_EXTENSIONS_TEXT = ", ".join(sorted(SUPPORTED_EXTENSIONS))


class DocumentExtractionRequest(BaseModel):
    """Single document extraction request."""

    file_path: str = Field(..., description="Absolute document path (.docx/.xlsx/.pptx)")
    output_dir: str = Field(default="", description="Internal absolute output directory for extracted artifacts.")
    enable_ocr: bool = Field(
        default=False,
        description="Whether to run OCR on extracted images and save a sidecar JSON file.",
    )


# ---------------------------------------------------------------------------
# Worker entry point — runs in a subprocess spawned by _run_worker_subprocess
# ---------------------------------------------------------------------------


def extract_document_payload(req_data: dict[str, Any]) -> dict[str, Any]:
    """Parse a single document in the worker process and return a JSON-safe payload."""
    req = DocumentExtractionRequest.model_validate(req_data)
    resolved_path, path, file_type = DocumentExtractor._resolve_document(req.file_path)
    reader = DocumentExtractor._get_reader(file_type)
    output_dir = DocumentExtractor._resolve_output_dir(resolved_path, req.output_dir)
    reader.configure_output_directory(path, output_dir)
    markdown_path = DocumentExtractor._get_markdown_output_path(path, output_dir)
    try:
        sections = DocumentExtractor._parse_document(reader, file_type, path)
        markdown_text = reader.convert_to_markdown(sections).strip()
        if not markdown_text:
            raise RuntimeError("Document extraction returned empty result.")
        reader.save_markdown(sections, markdown_path)
        warnings = [str(warning).strip() for warning in getattr(reader, "warnings", []) if str(warning).strip()]
        images = DocumentExtractor._collect_image_payloads(sections)

        # Clean up temp dir when no images need to be kept
        has_images = any(s.images for s in sections)
        if not has_images:
            DocumentExtractor._cleanup_reader(reader)

        return {
            "status": "success",
            "file_path": resolved_path,
            "file_type": file_type,
            "markdown_path": str(markdown_path),
            "section_count": len(sections),
            "warnings": warnings,
            "images": images,
        }
    except Exception:
        DocumentExtractor._cleanup_reader(reader)
        raise


def _worker_main(argv: Optional[list[str]] = None) -> int:
    """CLI entry point for the worker subprocess."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) not in (2, 3) or args[0] != WORKER_MODE_ARG:
            raise ValueError("worker requires '--worker <file_path> [output_dir]'")
        req_data: dict[str, Any] = {"file_path": args[1]}
        if len(args) == 3:
            req_data["output_dir"] = args[2]
        payload = extract_document_payload(req_data)
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()
        return 0
    except Exception as exc:
        sys.stdout.write(
            json.dumps(
                {
                    "status": "failed",
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                },
                ensure_ascii=False,
            )
            + "\n"
        )
        sys.stdout.flush()
        traceback.print_exc(file=sys.stderr)
        return 1


# ---------------------------------------------------------------------------
# Main tool class
# ---------------------------------------------------------------------------


class DocumentExtractor(BaseModel):
    """Extract Office documents (DOCX/Excel/PPT) into Markdown files.

    Supports Word documents, Excel spreadsheets, and PowerPoint presentations.
    Parsing runs in isolated subprocesses for memory safety and fault isolation.
    The tool writes a `.md` file to the current working directory by default
    and, when needed, stores extracted images in a sibling `<stem>_assets/` directory.
    """

    max_concurrency: int = Field(default=4, description="Maximum concurrent extractions.")
    worker_timeout_seconds: int = Field(default=300, description="Per-document subprocess timeout.")
    artifacts_reporter: Any = Field(default=None, exclude=True, repr=False)
    working_dir: str = Field(default="", exclude=True)

    def _get_artifacts_reporter(self):
        if self.artifacts_reporter is None:
            from metagpt.utils.report import ArtifactsReporter

            self.artifacts_reporter = ArtifactsReporter()
        return self.artifacts_reporter

    @staticmethod
    def _normalize_path(file_path: str, working_dir: str = "") -> Path:
        path = Path((file_path or "").strip()).expanduser()
        if not path.is_absolute():
            raise ValueError("file_path must be an absolute path.")
        return path.resolve(strict=False)

    @staticmethod
    def _get_source_name(file_path: str) -> str:
        return Path((file_path or "").strip()).expanduser().name or "document"

    @staticmethod
    def _get_file_type(path: Path) -> Optional[str]:
        return SUPPORTED_EXTENSIONS.get(path.suffix.lower())

    @classmethod
    def _resolve_document(cls, file_path: str, working_dir: str = "") -> tuple[str, Path, str]:
        resolved_path = str(cls._normalize_path(file_path, working_dir))
        path = Path(resolved_path)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(f"File not found: {resolved_path}")
        file_type = cls._get_file_type(path)
        if not file_type:
            raise ValueError(f"Unsupported format: {path.suffix}. Supported: {SUPPORTED_EXTENSIONS_TEXT}")
        return resolved_path, path, file_type

    @staticmethod
    def _resolve_output_dir(file_path: str, output_dir: str = "") -> Path:
        if output_dir:
            return Path(output_dir).expanduser().resolve(strict=False)
        return Path(file_path).expanduser().resolve(strict=False).parent

    @staticmethod
    def _get_markdown_output_path(document_path: str | Path, output_dir: str | Path = "") -> Path:
        document_path = Path(document_path)
        if output_dir:
            return Path(output_dir) / f"{document_path.stem}.md"
        return document_path.with_suffix(".md")

    @staticmethod
    def _get_reader(file_type: str):
        """Lazy-import the appropriate reader to avoid hard dependencies."""
        if file_type == "docx":
            from metagpt.utils.documents.docx_reader import DocxReader

            return DocxReader()
        if file_type == "excel":
            from metagpt.utils.documents.excel_reader import ExcelReader

            return ExcelReader()
        if file_type == "ppt":
            from metagpt.utils.documents.ppt_reader import PptReader

            return PptReader()
        raise ValueError(f"Unsupported file type: {file_type}")

    @staticmethod
    def _parse_document(reader, file_type: str, file_path: Path):
        if file_type == "docx":
            return reader.parse_docx(file_path)
        if file_type == "excel":
            return reader.parse_excel(file_path)
        if file_type == "ppt":
            return reader.parse_ppt(file_path)
        raise ValueError(f"Unsupported file type: {file_type}")

    @staticmethod
    def _collect_image_payloads(sections) -> list[dict[str, Any]]:
        images: list[dict[str, Any]] = []
        for section in sections:
            for image in getattr(section, "images", []) or []:
                image_path = str(Path(image.path).expanduser().resolve(strict=False))
                images.append(
                    {
                        "index": int(image.index),
                        "path": image_path,
                        "caption": (image.caption or "").strip(),
                    }
                )
        return sorted(images, key=lambda item: (item["index"], item["path"]))

    @staticmethod
    def _get_ocr_output_path(markdown_path: str | Path) -> Path:
        return Path(markdown_path).with_suffix(".ocr.json")

    @staticmethod
    async def _analyze_images(images: list[dict[str, str]]) -> dict[str, Any]:
        script = Path(__file__).resolve().parents[2] / "image-understanding" / "scripts" / "analyze.py"
        child_env = os.environ.copy()
        child_env["METAGPT_REPORTER_URL"] = ""
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            str(script),
            env=child_env,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate(
            json.dumps({"images": images}, ensure_ascii=False).encode("utf-8")
        )
        events = []
        for line in stdout.decode("utf-8", errors="replace").splitlines():
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "mgx_skill_event":
                events.append(payload)
        completed = next((event for event in reversed(events) if event.get("event") == "completed"), None)
        if proc.returncode != 0 or completed is None:
            detail = stderr.decode("utf-8", errors="replace").strip()
            failed = next((event for event in reversed(events) if event.get("event") == "failed"), None)
            if failed:
                detail = str(failed.get("error") or detail)
            raise RuntimeError(detail or "Image-understanding Skill returned no completed event.")
        result = completed.get("result")
        if not isinstance(result, dict):
            raise RuntimeError("Image-understanding Skill returned an invalid result.")
        return result

    @staticmethod
    def _build_ocr_image_records(images: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return sorted(
            [
                {
                    "index": int(image.get("index") or 0),
                    "image_path": image_path,
                    "caption": str(image.get("caption") or "").strip(),
                    "ocr_result": "",
                    "ocr_status": "pending",
                    "message": "",
                }
                for image in images or []
                for image_path in [str(image.get("path") or "").strip()]
                if image_path
            ],
            key=lambda item: (item["index"], item["image_path"]),
        )

    @staticmethod
    def _dedupe_warnings(warnings: list[str]) -> list[str]:
        return list(dict.fromkeys([str(warning).strip() for warning in warnings if str(warning).strip()]))

    async def _run_image_ocr(self, image_records: list[dict[str, Any]]) -> list[str]:
        warnings: list[str] = []
        if not image_records:
            warnings.append("OCR was requested, but no extracted images were found in the document.")
            return warnings

        process_count = min(len(image_records), MAX_OCR_IMAGES)
        skipped_count = len(image_records) - process_count
        if skipped_count > 0:
            warnings.append(
                f"OCR only processed the first {MAX_OCR_IMAGES} extracted images; "
                f"{skipped_count} image(s) were skipped. Use the image-understanding Skill "
                "for the remaining image_path values if needed."
            )
            skip_message = (
                f"Skipped because document extraction OCR only processes the first {MAX_OCR_IMAGES} extracted images. "
                "Use the image-understanding Skill for this image if needed."
            )
            for record in image_records[process_count:]:
                record["ocr_status"] = "skipped_limit_exceeded"
                record["message"] = skip_message

        requests = [{"image_path": record["image_path"], "mode": "ocr"} for record in image_records[:process_count]]
        try:
            batch_result = await self._analyze_images(requests)
        except Exception as exc:
            warning = f"Image OCR failed: {type(exc).__name__}: {exc}"
            warnings.append(warning)
            for record in image_records[:process_count]:
                record["ocr_status"] = "failed"
                record["message"] = warning
            return self._dedupe_warnings(warnings)

        results = batch_result.get("results") or []
        for index, record in enumerate(image_records[:process_count]):
            payload = results[index] if index < len(results) else {}
            result_status = str(payload.get("status") or "").strip()
            result_text = str(payload.get("result") or "").strip()
            result_message = str(payload.get("message") or "").strip()
            if result_status == "success":
                record["ocr_status"] = "success"
                record["ocr_result"] = result_text
                record["message"] = result_message
            else:
                record["ocr_status"] = "failed"
                record["message"] = result_message or "Image OCR failed."

        failed_count = sum(1 for record in image_records[:process_count] if record["ocr_status"] != "success")
        if failed_count:
            warnings.append(f"Image OCR failed for {failed_count}/{process_count} extracted image(s).")
        return self._dedupe_warnings(warnings)

    async def _write_ocr_sidecar(
        self,
        *,
        resolved_path: str,
        markdown_path: str,
        images: list[dict[str, Any]],
    ) -> tuple[str, list[str]]:
        image_records = self._build_ocr_image_records(images)
        warnings = await self._run_image_ocr(image_records)

        ocr_json_path = self._get_ocr_output_path(markdown_path)
        payload: dict[str, Any] = {
            "file_path": resolved_path,
            "markdown_path": markdown_path,
            "ocr_enabled": True,
            "ocr_limit": MAX_OCR_IMAGES,
            "image_count": len(image_records),
            "ocr_processed_count": sum(1 for record in image_records if record["ocr_status"] in {"success", "failed"}),
            "ocr_skipped_count": sum(1 for record in image_records if record["ocr_status"] == "skipped_limit_exceeded"),
            "images": image_records,
        }
        if warnings:
            payload["warnings"] = warnings

        ocr_json_path.parent.mkdir(parents=True, exist_ok=True)
        ocr_json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(ocr_json_path), warnings

    @staticmethod
    def _build_result(
        *,
        status: str,
        file_path: str,
        file_type: str,
        markdown_path: str,
        message: str,
        error_type: str = "",
        warnings: Optional[list[str]] = None,
        ocr_json_path: str = "",
    ) -> dict:
        payload = {
            "status": status,
            "markdown_path": markdown_path,
            "file_path": file_path,
            "file_type": file_type,
            "message": message,
        }
        if error_type:
            payload["error_type"] = error_type
        if warnings:
            payload["warnings"] = warnings
        if ocr_json_path:
            payload["ocr_json_path"] = ocr_json_path
        return payload

    @staticmethod
    def _cleanup_reader(reader) -> None:
        tmp_dir = getattr(reader, "tmp_dir", None)
        if tmp_dir:
            reader.cleanup_temp_directory(tmp_dir)
            reader.tmp_dir = None

    async def _report_status(
        self,
        req: DocumentExtractionRequest,
        status: Literal["running", "success", "failed"],
        resolved_path: str = "",
        markdown_path: str = "",
        file_type: str = "",
        warnings: Optional[list[str]] = None,
        ocr_json_path: str = "",
    ) -> None:
        payload: dict = {
            "filename": self._get_source_name(resolved_path or req.file_path),
            "status": status,
            "artifact_type": "document_extraction",
        }
        if status == "success":
            payload.update(
                {
                    "data_name": "path",
                    "path": markdown_path,
                    "source": resolved_path or str(self._normalize_path(req.file_path, self.working_dir)),
                    "file_type": file_type,
                }
            )
            if warnings:
                payload["warnings"] = warnings
            if ocr_json_path:
                payload["ocr_json_path"] = ocr_json_path
        await self._get_artifacts_reporter().async_report(payload, "object")

    @staticmethod
    async def _terminate_worker(proc) -> None:
        if proc is None:
            return
        with suppress(ProcessLookupError):
            if proc.returncode is None:
                proc.kill()
            await proc.wait()

    @staticmethod
    async def _drain_worker_after_termination(
        communicate_task: Optional[asyncio.Task],
    ) -> tuple[bytes, bytes]:
        """Collect remaining worker output without allowing cleanup to hang forever."""
        if communicate_task is None:
            return b"", b""
        try:
            return await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=WORKER_SHUTDOWN_GRACE_SECONDS,
            )
        except asyncio.TimeoutError:
            communicate_task.cancel()
            with suppress(BaseException):
                await communicate_task
            return b"", b""
        except asyncio.CancelledError:
            communicate_task.cancel()
            with suppress(BaseException):
                await communicate_task
            raise
        except Exception:
            with suppress(BaseException):
                await communicate_task
            return b"", b""

    async def _run_worker_subprocess(self, resolved_path: str, output_dir: str) -> dict[str, Any]:
        """Run extraction in an isolated subprocess and read its JSON payload."""
        proc = None
        communicate_task = None
        stderr_bytes = b""
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                str(Path(__file__).resolve()),
                WORKER_MODE_ARG,
                resolved_path,
                output_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            communicate_task = asyncio.create_task(proc.communicate())
            stdout_bytes, stderr_bytes = await asyncio.wait_for(
                asyncio.shield(communicate_task),
                timeout=self.worker_timeout_seconds,
            )
        except asyncio.TimeoutError as exc:
            await self._terminate_worker(proc)
            _stdout_bytes, stderr_bytes = await self._drain_worker_after_termination(communicate_task)
            stderr = stderr_bytes.decode("utf-8", errors="replace").strip()
            detail = f" Last stderr: {stderr.splitlines()[-1]}" if stderr else ""
            raise RuntimeError(
                f"Document extraction timed out after {self.worker_timeout_seconds}s for '{resolved_path}'.{detail}"
            ) from exc
        except asyncio.CancelledError:
            if communicate_task is not None:
                communicate_task.cancel()
            await self._terminate_worker(proc)
            if communicate_task is not None:
                with suppress(BaseException):
                    await communicate_task
            raise
        except Exception:
            if communicate_task is not None:
                communicate_task.cancel()
            await self._terminate_worker(proc)
            if communicate_task is not None:
                with suppress(BaseException):
                    await communicate_task
            raise

        # The worker protocol puts its JSON payload on the first non-empty line.
        # ``communicate`` drains the complete stream, so a large payload is not
        # subject to StreamReader's per-line limit.
        stdout_lines = [
            line.strip()
            for line in stdout_bytes.decode("utf-8", errors="replace").splitlines()
            if line.strip()
        ]
        stderr = stderr_bytes.decode("utf-8", errors="replace").strip()

        if not stdout_lines:
            raise RuntimeError(f"Worker returned no output for '{resolved_path}': {stderr or '(empty)'}")

        try:
            payload = json.loads(stdout_lines[0])
        except json.JSONDecodeError as exc:
            tail = stderr.splitlines()[-1] if stderr else stdout_lines[0][:200]
            raise RuntimeError(f"Worker returned invalid JSON: {tail}") from exc

        if payload.get("status") != "success":
            error_type = payload.get("error_type") or "RuntimeError"
            message = payload.get("message") or stderr or "Worker failed."
            raise RuntimeError(f"{error_type}: {message}")

        return payload

    async def _extract_one(self, req: DocumentExtractionRequest) -> dict:
        """Extract a single document via an isolated worker subprocess."""
        resolved_path, _, file_type = self._resolve_document(req.file_path, self.working_dir)
        output_dir = str(self._resolve_output_dir(resolved_path, self.working_dir))
        worker_payload = await self._run_worker_subprocess(resolved_path, output_dir)

        markdown_path = str(worker_payload.get("markdown_path") or "").strip()
        if not markdown_path:
            raise RuntimeError("Document extraction did not produce a markdown file.")
        section_count = int(worker_payload.get("section_count") or 0)
        warnings = [str(warning).strip() for warning in worker_payload.get("warnings") or [] if str(warning).strip()]
        images = worker_payload.get("images") or []
        ocr_json_path = ""

        if req.enable_ocr:
            ocr_json_path, ocr_warnings = await self._write_ocr_sidecar(
                resolved_path=resolved_path,
                markdown_path=markdown_path,
                images=images,
            )
            warnings = self._dedupe_warnings([*warnings, *ocr_warnings])

        await self._report_status(
            req,
            status="success",
            resolved_path=resolved_path,
            markdown_path=markdown_path,
            file_type=file_type,
            warnings=warnings,
            ocr_json_path=ocr_json_path,
        )
        message = f"Document extracted successfully ({file_type}, {section_count} sections): {markdown_path}"
        if ocr_json_path:
            message += f"; OCR sidecar: {ocr_json_path}"
        if warnings:
            message += f" [{len(warnings)} warning(s)]"
        return self._build_result(
            status="success",
            file_path=resolved_path,
            file_type=file_type,
            markdown_path=markdown_path,
            message=message,
            warnings=warnings,
            ocr_json_path=ocr_json_path,
        )

    async def extract_documents(self, documents: list[dict], **_: object) -> dict:
        """Extract content from multiple Office documents concurrently.

        Each document is parsed in its own subprocess for memory/fault isolation.

        Args:
            documents: List of dicts with absolute 'file_path' values (required).
                Set 'enable_ocr' to True to OCR extracted images into a sidecar `.ocr.json` file.

        Returns:
            Batch result summary with per-document results.
        """
        requested: list[DocumentExtractionRequest] = []
        for item in documents or []:
            try:
                if isinstance(item, DocumentExtractionRequest):
                    requested.append(item)
                elif isinstance(item, dict):
                    requested.append(DocumentExtractionRequest.model_validate(item))
                else:
                    raise TypeError(type(item))
            except Exception as e:
                logger.warning(f"Invalid document extraction request ignored: {item}, err={e}")

        if not requested:
            return {
                "status": "success",
                "results": [],
                "success_count": 0,
                "failed_count": 0,
                "message": "No documents to extract.",
            }

        for req in requested:
            await self._report_status(req, status="running")

        sem = asyncio.Semaphore(self.max_concurrency)

        async def _run_one(req: DocumentExtractionRequest) -> dict:
            async with sem:
                resolved_path = req.file_path
                file_type = "unknown"
                try:
                    resolved_path = str(self._normalize_path(req.file_path, self.working_dir))
                    file_type = self._get_file_type(Path(resolved_path)) or "unknown"
                    return await self._extract_one(req)
                except Exception as e:
                    log_fn = logger.warning if isinstance(e, (ValueError, FileNotFoundError)) else logger.error
                    log_fn(
                        f"Document extraction failed for '{resolved_path}': {type(e).__name__}: {e}",
                        exc_info=not isinstance(e, (ValueError, FileNotFoundError)),
                    )
                    await self._report_status(req, status="failed", resolved_path=resolved_path)
                    return self._build_result(
                        status="failed",
                        file_path=resolved_path,
                        file_type=file_type,
                        markdown_path="",
                        error_type=type(e).__name__,
                        message=f"Document extraction failed: {type(e).__name__}: {e}",
                    )

        results = await asyncio.gather(*[_run_one(req) for req in requested])
        failed = [r for r in results if r.get("status") != "success"]
        status = "success" if not failed else ("failed" if len(failed) == len(results) else "partial_success")
        return {
            "status": status,
            "results": results,
            "success_count": len(results) - len(failed),
            "failed_count": len(failed),
            "message": f"Extracted {len(results) - len(failed)}/{len(results)} documents.",
        }


SKILL = "document-extraction"


def execute(request: dict):
    extractor = DocumentExtractor(working_dir=str(Path.cwd()))
    return SkillScriptExecution.from_runtime(
        extractor,
        extractor.extract_documents(documents=request.get("documents", [])),
    )


def main(argv: Optional[list[str]] = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] == WORKER_MODE_ARG:
        return _worker_main(args)
    return run_skill_script(SKILL, execute)


if __name__ == "__main__":
    raise SystemExit(main())
