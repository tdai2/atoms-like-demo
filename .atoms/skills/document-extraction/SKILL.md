---
name: document-extraction
description: Read when you need to convert Office files such as DOCX, XLSX, or PPTX into Markdown in the current work directory.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the task involves reading or converting Office documents before further processing.
Typical cases: turning DOCX briefs into Markdown, extracting PPT content, converting spreadsheets for frontend or analysis workflows.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/extract.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, and pass the request as stdin JSON. A small document can run in the foreground; for large documents, OCR, or batches set `run_in_background` to `true` and later read the returned tab with `Terminal.read_tab`.

## Inputs

- `documents`: JSON array of document extraction requests.
- `file_path`: absolute path to a `.docx`, `.xlsx`, or `.pptx` file.
- `enable_ocr`: optional boolean. Use `true` when extracted document images also need OCR sidecar output.

## Returns

Each result item may include:

- `status`
- `file_path`
- `file_type`
- `markdown_path`
- `ocr_json_path`
- `warnings`
- `message`

## Rules / Constraints

- `file_path` must be absolute.
- Supported formats are DOCX, XLSX, and PPTX.
- The Markdown file is written into the current work directory.
- Extracted images are stored in a sibling `<stem>_assets/` directory when needed.
- When `enable_ocr` is `true`, the tool can also write `<stem>.ocr.json`.
- OCR only covers the first 20 extracted images. For remaining images, read `image-understanding` and run its script with the returned image paths.
- Read the converted content from `markdown_path`, then decide whether more parsing or OCR is needed.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/document-extraction/scripts/extract.py" <<'JSON'
{
  "documents": [
  {
    "file_path": "/absolute/path/to/uploads/client-brief.docx",
    "enable_ocr": true
  },
  {
    "file_path": "/absolute/path/to/uploads/q3-roadmap.pptx"
  }
  ]
}
JSON
```
