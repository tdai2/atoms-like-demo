---
name: image-understanding
description: Read when you need image understanding, OCR, or visual question answering for a local image or an http(s) image URL.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when you need to inspect an image, extract text from it, or answer a question based on what the image shows.
Typical cases: OCR, UI screenshot analysis, chart reading, image QA, asset inspection.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/analyze.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, and pass the request as stdin JSON. A small request can run in the foreground; for a large batch set `run_in_background` to `true` and later read the returned tab with `Terminal.read_tab`.

## Inputs

- `images`: JSON array of image analysis requests.
- `image_path`: absolute local path or http(s) URL.
- `mode`: `summary`, `ocr`, or `qa`. Defaults to `summary`.
- `instruction`: optional for `summary` and `ocr`; required for `qa`.

## Returns

Each result item may include:

- `status`
- `image_path`
- `mode`
- `instruction`
- `result`
- `message`
- `model`

## Rules / Constraints

- Local images must use absolute paths. Relative paths are invalid.
- Use `summary` for general understanding, `ocr` for text extraction, and `qa` for direct questions.
- When `mode` is `qa`, always provide `instruction`.
- Read the useful content from `result`.
- If you need OCR or QA for images extracted from Office documents, this skill is also the follow-up tool.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/image-understanding/scripts/analyze.py" <<'JSON'
{
  "images": [
  {
    "image_path": "/absolute/path/to/mockups/pricing-table.png",
    "mode": "summary",
    "instruction": "Describe the layout and the main pricing differences."
  },
  {
    "image_path": "https://example.com/assets/invoice-scan.jpg",
    "mode": "ocr"
  },
  {
    "image_path": "/absolute/path/to/screenshots/dashboard.png",
    "mode": "qa",
    "instruction": "What error message is visible in the top-right alert?"
  }
  ]
}
JSON
```
