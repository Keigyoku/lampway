# Prompt library (branch lp/prompts, from lp/video; includes the Higgsfield params + preset fixes 077c5fad, 48179c6a)

Build path for the coordinator: <workspace>/wt-prompts/build/Prod (synced with scripts/lampway/sync_python.sh --bin-dir build/Prod/bin).

## What was built (specs/prompts/PROMPT_LIBRARY.md sections 1-5)
- Engine: server/lampway_server/prompts/ (schema.py + prompt_template.schema.json, library.py, render.py, runlog.py, service.py). Five-part spine, typed/bounded
  variables, <=5 negatives, timed beats, ordered input roles, per-model adapters, gates, provenance, variant_of. User/project templates override by id; a new
  version never overwrites an old one; save writes the user scope only.
- 18 built-ins (7 video incl. anim-walk-side-track with side truck + long lens + GRID floor; 11 image, wording ported VERBATIM from the shelf prompt files,
  checked against fixtures tests/fixtures/prompts_verbatim/).
- Run log prompt_runs.jsonl (run / rating / gate lines merged per job), stats by id@version (mean rating, mean cost, gate pass rates), A/B via variant_of.
- Routes /app/prompts (list, get, PUT, render, rate, stats, runs, runs/{job}/gates); agent tools lampway_prompt_*; the job queue renders payload.template at
  submit (bad template = 422) and logs every image/video job.
- Image parity (section 5): moodboard image_gen job service, lampway_meshpaint (templates mesh-paint-albedo-front/side[-first], ordered named references),
  the imagegen module/CLI (--template/--var/--model/--print-prompt/--ref role=path), the Tripo Studio image action, lampway_image_gen, and the Higgsfield image
  provider all take template+variables, store the rendered prompt, enforce reference ORDER and validate size/resolution per model family (openai: size, <=3840
  edge and ~8.3 MP; FLUX/Gemini/Seedream/Riverflow: resolution + aspect_ratio). tests/test_prompt_surfaces.py proves no image path keeps a hard-coded prompt.
  The old scripts/texlib/prompts/prompt_meshpaint_v2*.txt are deleted.
- Blender client: Prompts panel (LAMPWAY_PT_prompts), operators lampway.prompts_refresh/prompt_load/prompt_preview/prompt_fork/prompt_use/prompt_rate; variable
  form generated from the schema; prompt_attach puts template+variables on Video Gen / Image Gen payloads only while the prompt is still the rendered text.

## Tests
- server: full suite green (rc 0) on the merged branch; prompt files test_prompt_{library,render,images,runs,surfaces}.py.
- client (real Blender binary): full lampway_tools suite 333 passed, 11 skipped; new test_prompts_client.py 5 passed (stand-in HTTP server records what is sent).

## Honest gaps
- The moodboard payload hooks (video_gen_ops.py, imagegen_ops.py) are covered by a source-inspection test plus the attach unit test, not by driving the live
  moodboard tabs.
- The drawer pickers inside the Video/Image Gen tabs are not built; use is via the Prompts panel ("Use in generation" fills the tab's prompt box).
- Higgsfield: upload size limits still unmeasured; the preset-recommendation response key names are assumed from the coordinator's description (not recorded).
- Seedance token estimate not checked against a real bill; OpenRouter acceptance of video data URLs unverified.
