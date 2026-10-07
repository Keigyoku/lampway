<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# UE-only cube capture handoff

This stage is implemented but has not run in actual UE. It samples the engine renderer; it contains no Filmic/ACES tone-curve implementation. Its output precision is deliberately **8 bits per channel**, recorded in the sidecar. It is suitable for an initial genuine engine-capture receipt, not a high-precision parity claim. Local UE execution must establish that the transient material compiles, the component APIs work, and both render controls pass.

First run the [capability probe](ue_cube_generator_handoff.md). Capture additionally needs `RenderingLibrary.read_render_target_pixel`, `TextureRenderTargetFormat.RTF_RGBA8`, `StaticMeshComponent`, `Vector4`, and normal mesh dynamic-material setters. The frozen first probe does not test these added LDR APIs. If any is missing, capture refuses with `error:` / `help[1]:`; no fallback generates an analytic cube.

In an explicitly disposable empty QA project, create `Saved/LampwayCubeQA/request.json` containing these exact fields:

- `disposable_qa_project`: `true`.
- `profile`: the complete actual UE profile JSON object. Engine version/changelist and every `project.cvars` integer must match actual UE readback. This initial sampler supports sRGB working space, Filmic and neutral grading. Verify the working space in the actual QA project settings; the script does not independently read that setting.
- `name`: a new simple basename such as `ue58_capture_01`; existing outputs are refused.
- `shaper`: the five numeric `LogAffineTransform` fields documented in [UE Look](../../docs/ue-look.md). Supply the exact log2 grid parameters verified against this engine's source and `r.LUT.Shaper` setting. No built-in default or guessed shaper exists in this script.
- `shaper_source`: the actual engine revision, native source location and setting establishing those five numbers. This is caller evidence, not an automated source verification.
- `max_seconds`: an explicit value from 1 through 3600, such as 600. External process timeout also bounds startup/shader compilation.

Before launching UE, inspect the offline plan (read-only): `python scripts/lampway/ue_cube_generator_capture.py --plan "$UE_QA_REQUEST"`. A 32³ cube requires 32,780 actual captures including controls. Runtime is unmeasured until local control capture calibration; no seconds-per-capture is invented. The supplied time allowance is a hard refusal bound, not an estimated completion time. An 8³ pilot must not be passed off as a valid 32³ profile cube or used to change renderer settings silently.

```bash
timeout 720s "$UE_EDITOR_CMD" "$UE_QA_PROJECT" -unattended -NoSplash -RenderOffscreen \
  -ExecutePythonScript="$LAMPWAY_REPO/scripts/lampway/ue_cube_generator_capture.py" > "$UE_QA_CAPTURE_LOG" 2>&1
```

Use a real rendering backend and already-authorized scripting support. No desktop session, production project, `-NullRHI`, security-setting changes or paid/egress operations are needed. Outputs remain in that project's `Saved/LampwayCubeQA`; do not commit or redistribute them. No scene/material asset is saved. Temporary actors are destroyed on success or Python failure.

The script samples a flat unlit emissive plane with an isolated show-only capture. Four raw HDR readbacks verify the supplied linear RGB reaches the renderer. Corresponding engine FinalColorLDR outputs are recorded. A second capture disables the native tone curve and gamut expansion; the neutral-gray display pixel must differ by more than one output code value, or the run refuses. Exposure is manual with physical camera disabled and bias zero; bloom, vignette, motion blur, chromatic aberration and grading effects are disabled for the transform measurement. Applied postprocess values and override flags are read back; a mismatch refuses. Engine defaults/profile scene exposure are not baked into this transform.

Successful completion requires exactly one `LAMPWAY_UE_CUBE_COMPLETE` marker, a complete size³ cube and a hash-matching `lampway.ue-cube-meta/1` sidecar. Editor exit zero alone is insufficient. Retain the complete log and validate the resulting files with Lampway's existing cube validator against the same profile. The sidecar records actual engine version/changelist/raw identifier, exact requested profile hash, input shaper provenance, engine capture mode, display encoding/precision, postprocess readback and raw/disabled-tone controls. It does not prove the owner's supplied shaper source or working-space statement independently; retain their actual source/settings receipt alongside it.

Pure tests (synthetic fixtures only): `python -m pytest -q tests/lampway_tools/test_ue_cube_generator_probe.py tests/lampway_tools/test_ue_cube_generator_capture.py`. Actual UE render/cube proof remains pending.
