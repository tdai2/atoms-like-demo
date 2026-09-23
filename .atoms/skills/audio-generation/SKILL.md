---
name: audio-generation
description: Read when you need text-to-speech audio assets such as narration, voice-over, walkthrough audio, or short spoken clips.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs generated speech audio.
Typical cases: narrator tracks, onboarding voice-over, guided audio, spoken product descriptions.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/generate.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, pass the request as stdin JSON, and set `run_in_background` to `true`.

After Terminal returns a `tab_id`, continue other runnable work. If none remains, call `Sleep.sleep` with `duration_seconds=300` as the only tool call; it wakes when the background task completes. Do not poll `Terminal.read_tab` while the tab is running. When notified, call `Terminal.read_tab(tab_id)` until `has_more` is false and read the final `completed.result` event. Do not rerun the script to check progress.

## Inputs

- `audios`: JSON array of audio generation requests. Submit at most 50 items per script call; split larger workloads across calls.
- `text`: text to speak.
- `filename`: logical output filename such as `intro.mp3`.
- `model`: optional.
- `gender`: optional. `male` or `female`. Defaults to `female`.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `path`
- `absolute_path`
- `message`
- `model`
- `voice`
- `gender`
- `duration`

## Rules / Constraints

- `filename` is a logical name for tracking, not a promised local file path.
- Use the returned CDN `url` directly in your code.
- If the script returns `duration`, prefer it as the measured audio length. Only fall back to manual `ffprobe` when exact timing matters and `duration` is missing or `null`.
- Keep speech text polished before generation; the script returns audio, not a draft-writing workflow.
- Use this after `todo.md` when generating project assets.
- If the user wants runtime in-app TTS, implement that through backend APIs instead of this internal command.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling, set `run_in_background` to `true`, and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/audio-generation/scripts/generate.py" <<'JSON'
{
  "audios": [
  {
    "text": "Welcome to the dashboard. Here you can track performance, review tasks, and manage your team workflow.",
    "filename": "dashboard-intro.mp3",
    "gender": "female"
  }
  ]
}
JSON
```
