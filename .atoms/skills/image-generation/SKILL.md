---
name: image-generation
description: Read when you need to generate or edit project image assets such as hero banners, product visuals, logos, icons, or transparent cutouts.
alwaysApply: false
roles:
  - Alex
---

## When to use

Use this skill when the task needs new image assets or image-to-image editing for project delivery.
Typical cases: hero banners, product cards, logos, decorative visuals, section backgrounds, transparent PNG assets, product packshots, e-commerce / Amazon-style product photos, product detail / macro shots, storefront / lifestyle plates, and consistency-anchor hero images that later drive reference-guided video clips.

## Command

Select the registered `Terminal.run` command through structured tool calling to run `scripts/generate.py` from this Skill directory. Use the absolute script path derived from this `SKILL.md`; keep the Terminal working directory unchanged. Pass the complete request as stdin JSON and set `run_in_background` to `true`.

After Terminal returns a `tab_id`, continue other runnable work. If none remains, call `Sleep.sleep` with `duration_seconds=300` as the only tool call; it wakes when the background task completes. Do not poll `Terminal.read_tab` while the tab is running. When the completion notification arrives, call `Terminal.read_tab(tab_id)` until `has_more` is false, then read the `completed.result` event and `app/frontend/image_manifest.json`. Do not rerun the script to check progress.

## Inputs

- `images`: JSON array of image request objects. Submit at most 50 items per script call; split larger workloads across calls.
- `description`: final visual prompt for the image model.
- `filename`: descriptive output filename, usually in English.
- `style`: optional. Defaults to `photorealistic`. Common values: `photorealistic`, `cartoon`, `sketch`, `watercolor`, `minimalist`, `3d`.
- `size`: optional image size such as `1024x1024`, `1024x576`, `1024x768`. Defaults to `1024x1024`.
- `model`: optional image model for this request. Only include it when a specific model is requested; otherwise omit it and the configured default model will be used.
- `image`: optional reference image for image-to-image editing. Must be an absolute local path or an http(s) URL.
- `background`: optional. Use `transparent` for transparent output.

## Returns

Each result item may include:

- `status`
- `filename`
- `url`
- `path`
- `absolute_path`
- `message`

## Rules / Constraints

- Batch required images into as few calls as practical without exceeding 50 items per call.
- Before running the script, turn the user requirement and the active planning artifact into the final `description`. The script does not call an LLM to rewrite prompts and does not accept a separate project-context field.
- Include only the relevant visual dimensions: subject and exact count, composition and focal point, scene/background, lighting and mood, materials and texture, palette and medium, viewpoint and depth, plus the intended asset use and aspect-ratio composition. Keep the result focused, normally under 1200 characters.
- Write a pure visual description. Do not prepend instructions such as `Generate an image:` or repeat a long style-keyword list; the `style` field is handled separately.
- Repeat the relevant project palette, style, tone, and layout constraints in each `description`; do not assume the script can read Role memory. Later user requirements override earlier ones.
- Describe a still image, not a timeline: do not add camera movement, animation, or time progression. A frozen splash, wind-shaped fabric, or other static cue of motion is fine when useful.
- Keep the user's language. Preserve exact counts, brand names, logos, required on-image text, and rendering/compliance constraints verbatim. Do not invent readable text, labels, watermarks, logos, or brand marks.
- For image editing (`image` set), write a concise edit instruction describing only the requested change. Preserve the reference subject's identity, pose, layout, perspective, style, readable text, and branding unless the user explicitly asks to change them.
- For a packshot or catalog-style product image, request a clean/seamless or transparent background (`background: "transparent"` with a `.png` filename) and a clear product-centered composition.
- When `background` is `transparent`, do not describe a visible setting, backdrop, surface, or environmental clutter.
- When the image must show a specific real product/subject that already has a reference image, generate it image-to-image (pass the reference in `image` and describe the change), not text-only — otherwise the model reinvents the product. Backgrounds/atmosphere with no specific product stay text-only.
- Use descriptive English filenames so later code references stay clear.
- If a result item has `url`, use that URL directly in code. Do not download it.
- If there is no `url`, use the returned local asset path according to the tool result.
- Reference `image` only supports absolute local paths or http(s) URLs. Do not pass data URIs.
- Transparent background requests should use `background: "transparent"` and a `.png` or `.webp` filename, or no extension.
- Transparent background requests temporarily switch the underlying model to `gpt-image-1.5`.
- Run image generation after the active workflow's planning artifact is written and locked. If the current workflow already names a storyboard or other source-of-truth file, follow that file instead of creating a separate `todo.md`.
- If the user wants end-user in-app image generation, implement that through backend AI APIs instead of this internal command.

## Native Terminal tool-call example

Select `Terminal.run` through structured tool calling, set `run_in_background` to `true`, and pass the following shell text as its `cmd` argument. Do not emit this example as assistant text.

```bash
python "/absolute/path/to/.atoms/skills/image-generation/scripts/generate.py" <<'JSON'
{
  "images": [
  {
    "description": "Wide 16:9 homepage hero for a premium electric-motorcycle brand. One futuristic matte-black motorcycle in a three-quarter front view on a wet city street at blue hour, positioned on the right with clean negative space on the left for an HTML headline. Dark navy palette with restrained electric-blue reflections, low directional rim light, crisp metal and carbon-fiber textures, shallow atmospheric depth, photorealistic commercial photography, no text or logos in the image.",
    "filename": "hero-electric-motorcycle-dusk.jpg",
    "style": "photorealistic",
    "size": "1024x576"
  },
  {
    "description": "Minimal owl logo mark for a productivity app, symmetrical centered silhouette, clean geometric vector-like shapes, electric-blue and white palette, strong readability at small size, no text, no gradients, no background shadows, transparent background.",
    "filename": "logo-owl-mark.png",
    "style": "minimalist",
    "size": "1024x1024",
    "background": "transparent"
  }
  ]
}
JSON
```
