---
name: pdf-understanding
description: Read when you need to understand a local PDF, answer questions about it, or extract structured information from it.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the task needs real PDF understanding rather than simple string lookup.
Typical cases: summarizing reports, answering PDF questions, extracting tables or structured facts, interpreting visual layout.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/analyze.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, and pass the request as stdin JSON. A short page range can run in the foreground; for large ranges or batches set `run_in_background` to `true` and later read the returned tab with `Terminal.read_tab`.

## Inputs

- `pdfs`: JSON array of PDF analysis requests.
- `pdf_path`: local PDF path.
- `instruction`: question or extraction instruction.
- `mode`: `qa` or `extract`. Defaults to `qa`.
- `page_start`: optional 1-based start page. Defaults to `1`.
- `page_end`: optional 1-based end page. If omitted, the tool analyzes up to 80 pages starting from `page_start`. If it exceeds the actual PDF length, the tool truncates it to the last page.

## Returns

Each result item may include:

- `status`
- `pdf_path`
- `instruction`
- `mode`
- `result`
- `message`
- `page_start`
- `page_end`
- `total_pages`

## Rules / Constraints

- Use `Editor.read` only for simple text lookup or direct extraction when PDF understanding is unnecessary.
- Use this skill for summarization, Q&A, structured extraction, or any task that depends on PDF layout, charts, or tables.
- The current script only supports local PDF files and Claude-based PDF understanding.
- Keep page ranges reasonable. The underlying analyzer supports up to 80 pages per request window.
- If `page_end` is beyond the real page count, the request does not fail; the tool returns the actual resolved `page_end` in the result.
- Read the useful answer from `result`.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/pdf-understanding/scripts/analyze.py" <<'JSON'
{
  "pdfs": [
  {
    "pdf_path": "/absolute/path/to/docs/annual-report.pdf",
    "instruction": "Summarize the main revenue drivers and mention the relevant page numbers.",
    "mode": "extract",
    "page_start": 1,
    "page_end": 20
  }
  ]
}
JSON
```
