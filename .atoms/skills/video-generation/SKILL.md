---
name: video-generation
description: Read when you need to generate a single short visual-only source clip such as a hero background, atmosphere loop, one-shot image-to-video clip, keyframe video, or reference-to-video clip. Do NOT use this for a deliverable that pairs the clip with narration/voiceover or any separate audio track, or that needs the video timed to match an audio length — that belongs to promo-video-production (Remotion), because a single generated clip cannot stretch or sync to a voiceover and the audio would be cut off.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the project needs generated video content as a source asset.
Typical cases: hero background loops, atmosphere clips, short motion scenes, product reference clips, one-shot image-to-video clips, or first/last-frame transitions.

Do not use this single-clip workflow as the final delivery path for a complete multi-shot video. If the request includes a timeline, shot list, captions, narration/audio, editing direction, CTA/end card, multiple scenes, or a total duration beyond one short clip, read `promo-video-production` first and treat AI-generated videos as source clips inside the Remotion timeline.

If the task is specifically to edit an existing source video, prefer the `video-editing` skill and its script. This skill remains the general entry for text-to-video, image-to-video, keyframe-to-video, and reference-to-video generation.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/generate.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`, keep the current working directory, pass the request as stdin JSON, and set `run_in_background` to `true`.

After Terminal returns a `tab_id`, continue other runnable work. If none remains, call `Sleep.sleep` with `duration_seconds=300` as the only tool call; it wakes when the background task completes. Do not poll `Terminal.read_tab` while the tab is running. When notified, call `Terminal.read_tab(tab_id)` until `has_more` is false and read the final `completed.result` event. Do not rerun the script to check progress.

## `generate_videos` Inputs

- `videos`: JSON array of video generation requests. Submit at most 50 items per script call; split larger workloads across calls.
- `prompt`: final prompt for the video model.
- `filename`: logical output name with extension such as `.mp4`.
- `model`: optional.
- `size`: optional. Defaults to `1280x720`. Keep this default unless the task clearly requires another size.
- `seconds`: optional. Defaults to `4`. Keep this default unless the task clearly requires another duration. For `seedance-2.5`, request only `4` to `30` seconds; for `seedance-2.0`, request only `4` to `15` seconds.
- `image`: optional legacy alias of `input_reference`. Must be an absolute local path or an http(s) URL.
- `input_reference`: optional OpenAI-compatible image upload. The current gateway maps `image` / `input_reference` to first-frame generation; prefer `first_frame` for new requests.
- `first_frame`: optional first-frame image reference.
- `last_frame`: optional last-frame image reference. Requires `first_frame`.
- `reference_images`: optional reference image array for reference-to-video.
- `reference_videos`: optional reference video array for reference-to-video, video edit, or video extend.
- `reference_audios`: optional reference audio array for reference-to-video models that support audio reference.
- `resolution`: optional resolution level such as `720p`, `1080p`, or `4k`.
- `ratio`: optional aspect ratio such as `16:9`, `9:16`, or `1:1`. For `seedance-2.5` first/last-frame requests, including the gateway's `image` / `input_reference` compatibility path, use `adaptive`. Ordinary `reference_images` items with `role: "reference_image"` may use a fixed ratio.
- `audio`: optional boolean to request model-generated audio when supported. For a Remotion promo source clip set `audio=false` — the clip is a visual layer and promo audio comes only from the timeline's narration + global BGM; a baked-in clip track would stack on the BGM (also render the clip's `<OffthreadVideo>` with `muted`).
- `audio_setting`: optional video-edit audio behavior, `auto` or `origin`.
- `negative_prompt`: optional elements to avoid.

Reference item fields:

- `url`: required. http(s) URL, supported data URI / gs:// URI, or absolute local path.
- `role`: optional. Common values: `reference_image`, `first_frame`, `last_frame`, `style`, `grid`, `reference_video`, `video`, `extend`, `reference_audio`.
- `tag`: optional prompt binding tag such as `@subject1`.
- `voice_url`: optional voice reference for supported R2V models.

Reference prompt binding:

- If `reference_images`, `reference_videos`, or `reference_audios` are provided, the `prompt` must explicitly bind each reference before the scene description.
- Use provider-readable ordinal labels that match array order: `Video 1` is `reference_videos[0]`, `Image 1` is `reference_images[0]`, and `Audio 1` is `reference_audios[0]`.
- Include any `tag` in the binding line when useful, but do not rely on tags alone. The scene should refer to `Image 1`, `Video 1`, `Audio 1`, or the tag.
- Do not only describe references with natural-language names such as "the brown-haired girl" or "the guitarist"; that does not reliably bind the uploaded assets to the prompt.

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

- `filename` is a logical identifier, not a guaranteed local file path.
- Before running the script, turn the user requirement and active storyboard or planning artifact into each final `prompt`. The script does not call an LLM to rewrite prompts and does not accept a separate project-context field.
- Build the prompt from the relevant details: subject identity and texture, core action and physical interaction, composition and spatial depth, environment and secondary motion, lighting and atmosphere, then presentation constraints. Repeat the relevant project style, palette, tone, and continuity requirements in every prompt. Keep it focused, normally under 1200 characters.
- Fit the action to `seconds`: around 4 seconds should contain one clear visual beat; 10 seconds or more may use a richer physical progression. Describe a readable starting state, natural motion, and stable ending state without overloading one clip.
- Add physically plausible secondary motion when useful, such as fabric reacting to wind, drifting dust, fluid ripples, reflections, shadows, parallax, or subtle environmental movement. For an otherwise static scene, add restrained environmental or camera motion so it does not look frozen.
- For a product showcase, keep the product identity, placement, proportions, material, and requested style stable. Enrich the display surface, reflections, lighting, atmosphere, spatial depth, and secondary motion; do not add hands, usage actions, extra branding, or commercial-storyboard logic unless requested.
- Do not impose shot counts, timecodes, hard cuts, or complex camera choreography unless the user or storyboard requires them. A Remotion source clip should normally say `single continuous shot, no cuts, no scene changes`; a standalone commercial clip may use an explicit short shot sequence only when that one clip must cover multiple angles or selling points.
- Keep the user's language. Preserve exact counts, brand names, logos, on-screen text, reference bindings, and compliance or shooting constraints verbatim. Do not invent narration, dialogue, music direction, captions, subtitles, end cards, extra subjects, or unrelated props.
- Avoid morphing, identity changes, anatomy errors, changing logos/text, or sudden object appearance/disappearance unless explicitly requested. Use `negative_prompt` for concise model-specific exclusions when helpful.
- For reference-guided generation, keep the `Reference map:` block as the literal start of the prompt, then describe motion, camera, environment, and lighting without renaming or re-describing the referenced subject. Preserve its identity and appearance across frames.
- For a Remotion promo source clip, use `seedance-2.5` (text-only generation passes no reference; reference-guided generation passes `reference_images`). To keep a product or subject consistent across clips, reuse one canonical reference image in `reference_images` on every clip.
- For a true multi-shot edited deliverable (timeline, captions, narration), use the Remotion timeline rather than asking one generated clip to be the whole video.
- Use the returned CDN `url` directly in your code.
- Use absolute local paths or http(s) URLs for internal local file references. Runtime backend APIs may accept browser data URIs.
- Do not provide both top-level `first_frame` and a `reference_images` item with `role: "first_frame"`.
- Do not provide both top-level `last_frame` and a `reference_images` item with `role: "last_frame"`.
- `last_frame` requires `first_frame`.
- If the user provides uploaded asset paths, pass them through `reference_images`, `reference_videos`, `reference_audios`, `first_frame`, or `input_reference`; never only describe those assets in the prompt.
- For multi-reference R2V prompts, begin the prompt with a reference map, for example: `Reference map:\nVideo 1 = @player, main performer\nImage 1 = @girl, brown-haired girl\n\nScene:\nVideo 1 sits beside Image 1`.
- `1280x720` and `4` seconds are the safest defaults across current video models, so do not change them unless the requirement clearly needs it.
- `seedance-2.5` accepts `seconds` only from `4` to `30`; never pass a value outside this range.
- For `seedance-2.5` first/last-frame generation, the tool always sends `ratio: "adaptive"`. This includes `image` / `input_reference`, which the current gateway maps to first-frame generation. It does not apply to ordinary `reference_images` items with `role: "reference_image"`.
- `seedance-2.0` accepts `seconds` only from `4` to `15`; never pass `1`, `2`, or `3` seconds to this model. If a beat feels shorter, generate a 4-second clip and trim it in the consuming timeline/component.
- This script is for internal asset creation after the active planning artifact, not for end-user runtime video generation.
- If the user wants in-app video generation, implement it through backend AI APIs.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling, set `run_in_background` to `true`, and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/video-generation/scripts/generate.py" <<'JSON'
{
  "videos": [
  {
    "prompt": "4-second single continuous shot, no cuts, no scene changes. A premium modern workspace at sunrise in a warm amber and dark-walnut palette. Start on a wide, orderly desk silhouette; make one slow, stable forward glide as sunlight travels through soft haze and subtle dust motes drift above brushed-metal and wood surfaces; end with the hero workspace centered and sharply readable. No people, text, logos, flicker, or sudden object changes.",
    "filename": "hero-workspace-loop.mp4"
  },
  {
    "prompt": "Preserve the poster's subject, layout, typography, colors, and branding exactly. Add only subtle depth-separated parallax, a gentle light sweep across the product, and restrained atmospheric particles during one continuous 4-second shot; no cuts, warping, new text, or identity changes.",
    "filename": "poster-motion.mp4",
    "image": "/absolute/path/to/assets/poster-reference.png"
  },
  {
    "prompt": "Reference map:\nImage 1 = @product_front, product front view\nImage 2 = @product_side, product side view\n\nScene:\n5-second premium product showcase in a dark navy studio with restrained electric-blue rim light. Preserve the exact product identity, proportions, materials, and branding from both references. Begin with Image 1 as the stable hero view, transition naturally to reveal the side details represented by Image 2 through coherent camera motion, and end on a clean three-quarter product pose; controlled reflections, subtle haze, no added hands, text, logos, or morphing.",
    "filename": "product-reference-teaser.mp4",
    "model": "seedance-2.5",
    "reference_images": [
      {"url": "https://example.com/product-front.png", "role": "reference_image", "tag": "@product_front"},
      {"url": "https://example.com/product-side.png", "role": "reference_image", "tag": "@product_side"}
    ],
    "resolution": "720p",
    "ratio": "16:9",
    "seconds": 5
  }
  ]
}
JSON
```
