---
name: audio-transcription
description: Read when you need to transcribe a local audio file or an http(s) audio URL into text.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when you need text from existing audio.
Typical cases: captions, transcript generation, subtitle source text, meeting notes, spoken-content extraction.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/transcribe.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, and pass the request as stdin JSON. A small request can run in the foreground; for a large file or batch set `run_in_background` to `true` and later read the returned tab with `Terminal.read_tab`.

## Inputs

- `audios`: JSON array of transcription requests.
- `audio`: absolute local path or http(s) URL.
- `model`: optional.

## Returns

Each result item may include:

- `status`
- `audio`
- `source_name`
- `text`
- `message`
- `model`

## Rules / Constraints

- Local audio must use an absolute path.
- Read transcript content from `text`.
- This script does not write transcript files to disk for you.
- If you need subtitles or captions in project files, write them yourself after reading the returned text.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/audio-transcription/scripts/transcribe.py" <<'JSON'
{
  "audios": [
  {
    "audio": "/absolute/path/to/media/founder-interview.mp3"
  },
  {
    "audio": "https://example.com/media/demo.wav"
  }
  ]
}
JSON
```
