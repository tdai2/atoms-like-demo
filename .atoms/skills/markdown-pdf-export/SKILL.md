---
name: markdown-pdf-export
description: Read when you need to convert a local Markdown file into a print-first PDF for delivery, export, or sharing.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project already has a Markdown file and needs a PDF export.
Typical cases: report export, printable proposal, presentation handout, final deliverable PDF.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/export.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, and pass the request as stdin JSON. It normally runs in the foreground; for a large document set `run_in_background` to `true` and later read the returned tab with `Terminal.read_tab`.

## Inputs

- `markdown_path`: source Markdown file path.
- `output_path`: optional target PDF path or output directory. If omitted, the tool uses the source directory and the same stem.
- `title`: optional PDF title override.
- `enable_math`: optional boolean for MathJax rendering. Defaults to `true`.
- `enable_mermaid`: optional boolean for Mermaid rendering. Defaults to `true`.
- `keep_html`: optional boolean to keep the intermediate HTML file.

## Returns

The result may include:

- `status`
- `input_path`
- `output_path`
- `html_path`
- `message`

## Rules / Constraints

- Use this only when the source content already exists as a local Markdown file.
- Prefer leaving `enable_math` and `enable_mermaid` enabled unless the document clearly does not need them.
- Use `keep_html: true` only when you need to debug rendering or keep the intermediate HTML artifact.
- Read the final PDF location from `output_path`.
- This is an internal export tool, not an end-user runtime feature.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/markdown-pdf-export/scripts/export.py" <<'JSON'
{
  "markdown_path": "/absolute/path/to/reports/quarterly-summary.md",
  "output_path": "/absolute/path/to/reports/quarterly-summary.pdf",
  "title": "Quarterly Summary",
  "enable_math": true,
  "enable_mermaid": true,
  "keep_html": false
}
JSON
```
