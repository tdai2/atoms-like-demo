---
name: music-generation
description: Read when you need generated background music, instrumental BGM, ambience, jingles, or song/music assets from a text prompt.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs generated music rather than speech.
Typical cases: product teaser BGM, app/game ambience, intro/outro music, social video background music, short jingles.

Do not use this for narration, voice-over, spoken product descriptions, or TTS. Read `audio-generation` and run its script for speech.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/generate.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, pass the request as stdin JSON, and set `run_in_background` to `true`.

After Terminal returns a `tab_id`, continue other runnable work. If none remains, call `Sleep.sleep` with `duration_seconds=300` as the only tool call; it wakes when the background task completes. Do not poll `Terminal.read_tab` while the tab is running. When notified, call `Terminal.read_tab(tab_id)` until `has_more` is false and read the final `completed.result` event. Do not rerun the script to check progress.

## Inputs

- `tracks`: JSON array of music generation requests. Submit at most 20 items per script call; split larger workloads across calls.
- `prompt`: music style, mood, instrumentation, tempo, and constraints.
- `filename`: logical tracking name. For the default Lyria model, use an `.mp3` name such as `teaser_bgm.mp3`.
- `model`: optional. Defaults to configured music model.
- `n`: optional. Number of samples, 1-4.
- `response_format`: optional. Prefer `url`.
- `negative_prompt`: optional. Elements to avoid.
- `seed`: optional.
- `lyrics`: optional. Use only for song/lyric models such as Minimax.
- `audio_format`, `sample_rate`, `bitrate`, `voice_id`: optional Minimax-only fields. Omit them for Lyria.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `b64_json`
- `path`
- `absolute_path`
- `message`
- `model`
- `format`
- `duration`
- `seed`

## Rules / Constraints

- `filename` is a logical name for tracking. Its suffix does not request the provider's output encoding.
- Lyria does not expose an output-format selector. Use `.mp3` for its logical filename, but treat the returned URL, filename, and `format` as authoritative.
- Prefer `response_format: "url"` and use the returned URL directly in app code. `response_format` selects URL versus base64 output; it does not select MP3, WAV, or FLAC.
- If the script returns `duration`, treat it as the preferred measured track length. Only fall back to manual `ffprobe` when exact timing matters and `duration` is missing or `null`.
- Be explicit about mood, pacing, instrumentation, and whether vocals are allowed.
- For background music, include constraints like `no vocals` or `instrumental` when appropriate.
- Prefer short natural-language music descriptions over comma-separated keyword piles.
- A good prompt usually says: what the track is for, how it should feel, how it should move/build, which instruments/textures matter, and any hard constraints.
- If structure or approximate duration matters, describe the phases in short clauses and restate the target total length in prose.
- Time-stamped or labeled sections are fine when they help the music follow scene beats or chapter changes.
- BPM can be a useful hint, but it should not be the whole prompt.
- If another workflow skill has stricter timing or sequencing rules, follow that workflow for order, duration handling, and validation. This skill only covers how to prepare the music-generation script request.
- If a workflow skill, storyboard, or approved draft prompt already gives a segmented music structure, preserve that structure in the final `prompt` instead of flattening it into one undifferentiated paragraph.
- This script is for internal asset creation after the active workflow's planning artifact is locked. If the current workflow already names a storyboard or other source-of-truth file, follow that file instead of creating a separate `todo.md`.
- If the user wants runtime in-app music generation, implement that through backend APIs instead of this internal command.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling, set `run_in_background` to `true`, and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/music-generation/scripts/generate.py" <<'JSON'
{
  "tracks": [
  {
    "prompt": "[0:00 - 0:08] Intro: airy synth pads and a clean pulse, leave clear space for dialogue.\n[0:08 - 0:22] Build: add subtle percussion and a warm bass pulse, energy rises gently.\n[0:22 - 0:30] Close: polished electronic resolve with a soft fade.\nInstrumental background track for a product teaser. No vocals. Target total length: around 30 seconds.",
    "filename": "product-teaser-bgm.mp3",
    "model": "lyria-3-pro-preview",
    "response_format": "url"
  }
  ]
}
JSON
```
