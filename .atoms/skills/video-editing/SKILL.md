---
name: video-editing
description: Read when you need to edit an existing video with AI, such as changing style, replacing background, changing outfit/object appearance, preserving the original motion, or keeping the source audio.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs an existing video to be edited.
Typical cases: change a video's visual style, replace a background, change clothing or product appearance, apply a reference image to a source video, or preserve the original video rhythm/audio while changing visuals.

Do not use this skill for pure text-to-video, image-to-video, keyframe-to-video, or ordinary reference-to-video generation. Use `video-generation` for those.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/edit.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, pass the request as stdin JSON, and set `run_in_background` to `true`.

After Terminal returns a `tab_id`, continue other runnable work. If none remains, call `Sleep.sleep` with `duration_seconds=300` as the only tool call; it wakes when the background task completes. Do not poll `Terminal.read_tab` while the tab is running. When notified, call `Terminal.read_tab(tab_id)` until `has_more` is false and read the final `completed.result` event. Do not rerun the script to check progress.

## Inputs

- `edits`: JSON array of video edit requests. Submit at most 50 items per script call; split larger workloads across calls.
- `prompt`: edit instruction. State what should change and what should stay the same.
- `filename`: logical output name with extension such as `.mp4`.
- `source_video`: required source video. Use an http(s) URL, supported data URI, or gs:// URI. Prefer a CDN/HTTP URL.
- `model`: optional. The configured default remains `happyhorse-1.0-video-edit`. Use `seedance-2.5` when that model is requested; use `wan2.7-videoedit` only when that channel is explicitly required and has been verified for the current source video.
- `seconds`: optional. For `seedance-2.5`, the tool ignores this value and sends API duration `-1` as required by the model.
- `reference_images`: optional references for style, outfit, product, object, or background edits.
- `reference_audios`: optional references for models/channels that support audio references.
- `resolution`: optional resolution level such as `720p`, `1080p`, or `4k`.
- `ratio`: optional aspect ratio such as `16:9`, `9:16`, or `1:1`. For `seedance-2.5`, the tool always sends `adaptive`.
- `audio_setting`: optional. Use `origin` to keep input video audio when supported; use `auto` to let the model decide.
- `negative_prompt`: optional elements to avoid.

Reference image/audio item fields:

- `url`: required. http(s) URL, supported data URI / gs:// URI, or absolute local path.
- `role`: optional. For edit reference images, usually `reference_image`, `style`, or omitted.
- `tag`: optional prompt binding tag such as `@outfit`.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `path`
- `absolute_path`
- `message`
- `model`
- `size`
- `seconds`

## Rules / Constraints

- `source_video` is required and maps to OneAPI `reference_videos: [{url, role: "video"}]`.
- Do not use local filesystem paths for `source_video`; publish/upload the video first and pass the resulting URL.
- Use exactly one source video per edit request.
- `seedance-2.5` accepts source videos only from 4 to 30 seconds. The tool probes the source before submission, rejects an unknown or out-of-range duration, sends duration `-1`, and forces `ratio: "adaptive"`.
- `happyhorse-1.0-video-edit` supports one source video and up to 5 reference images.
- `wan2.7-videoedit` supports one source video and up to 4 reference images, but may be stricter about source video/audio handling.
- Use `audio_setting: "origin"` only when preserving the input video audio matters.
- `filename` is a logical identifier, not a guaranteed local file path.
- Use the returned CDN `url` directly in project code.
- This script is for internal asset creation after `todo.md`, not for end-user runtime video editing.
- If the user wants in-app video editing, implement it through backend AI APIs with `client.ai.genvideo(...)` and `reference_videos[].role = "video"`.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling, set `run_in_background` to `true`, and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/video-editing/scripts/edit.py" <<'JSON'
{
  "edits": [
  {
    "prompt": "Change the background to a snowy mountain scene while preserving the original subject motion and camera rhythm",
    "filename": "snow-mountain-edit.mp4",
    "source_video": "https://example.com/source.mp4",
    "model": "happyhorse-1.0-video-edit",
    "reference_images": [
      {"url": "https://example.com/snow-mountain.jpg", "role": "reference_image"}
    ],
    "resolution": "1080p",
    "ratio": "16:9",
    "audio_setting": "origin"
  }
  ]
}
JSON
```
