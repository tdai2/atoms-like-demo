---
name: chart-rendering
description: Read when you need to render Mermaid, PlantUML, D2, Graphviz, or similar diagrams into frontend-ready chart assets.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs rendered diagrams or explanatory visuals rather than plain text descriptions.
Typical cases: architecture diagrams, process flows, dependency graphs, sequence diagrams, timelines.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/render.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, and pass the request as stdin JSON. A small batch can run in the foreground; for a large batch set `run_in_background` to `true` and later read the returned tab with `Terminal.read_tab`.

## Inputs

- `charts`: JSON array of chart render requests.
- `diagram_type`: Kroki diagram type such as `mermaid`, `plantuml`, `d2`, or `graphviz`.
- `code`: raw diagram DSL source.
- `filename`: relative output filename.
- `output_format`: optional, default `svg`; supported formats vary by `diagram_type`.

## Returns

Each result item may include:

- `status`
- `filename`
- `path`
- `absolute_path`
- `url`
- `message`

## Rules / Constraints

- Prefer `svg`. Kroki exposes D2 only as SVG, so use `output_format: "svg"` and an `.svg` filename; convert the SVG separately if PNG is required.
- `filename` must stay relative. Do not use absolute paths or parent traversal.
- Use result item `url` directly in frontend code. It is already a local web path such as `/assets/charts/architecture.svg`.
- Use `absolute_path` only when another tool needs the real file path.
- Put the exact DSL source in `code`; do not paraphrase it.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/chart-rendering/scripts/render.py" <<'JSON'
{
  "charts": [
    {
      "diagram_type": "mermaid",
      "code": "flowchart TD\n  User[User] --> UI[Frontend]\n  UI --> API[Backend API]\n  API --> DB[(Database)]",
      "filename": "architecture/app-flow.svg",
      "output_format": "svg"
    }
  ]
}
JSON
```
