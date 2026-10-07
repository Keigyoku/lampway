<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# UE-only cube capture handoff

This stage is implemented but has not run in actual UE. It samples the engine renderer; it contains no Filmic/ACES tone-curve implementation. Its output precision is deliberately **8 bits per channel**, recorded in the sidecar. It is suitable for an initial genuine engine-capture receipt, not a high-precision parity claim. Local UE execution must establish that the transient material compiles, the component APIs work, and both render controls pass.

First run the [capability probe](ue_cube_generator_handoff.md). Capture additionally needs `RenderingLibrary.read_render_target_pixel`, `TextureRenderTargetFormat.RTF_RGBA8`, `StaticMeshComponent`, `Vector4`, and normal mesh dynamic-material setters. The first probe does not test these added LDR APIs. Run the supplemental read-only check before capture:

```bash
timeout 120s "$UE_EDITOR_CMD" "$UE_QA_PROJECT" -unattended -NoSplash -RenderOffscreen \
  -ExecutePythonScript="$LAMPWAY_REPO/scripts/lampway/ue_cube_generator_supplemental_probe.py" \
  > "$UE_QA_SUPPLEMENTAL_LOG" 2>&1
```

Require exactly one `LAMPWAY_UE_CUBE_SUPPLEMENTAL_PROBE` marker with `available:true`. This checks Python surface availability and neutral-grading properties; shader compilation and pixels remain unverified. If any is missing, capture refuses with `error:` / `help[1]:`; no fallback generates an analytic cube.

In an explicitly disposable empty QA project, create `Saved/LampwayCubeQA/request.json` containing these exact fields:

- `disposable_qa_project`: `true`.
- `profile`: the complete actual UE profile JSON object. Engine version/changelist and every `project.cvars` integer must match actual UE readback. This initial sampler supports sRGB working space, Filmic and neutral grading. Verify the working space in the actual QA project settings; the script does not independently read that setting.
- `name`: a new simple basename such as `ue58_capture_01`; existing outputs are refused.
- `shaper`: the five numeric `LogAffineTransform` fields documented in [UE Look](../../docs/ue-look.md). Supply the exact log2 grid parameters verified against this engine's source and `r.LUT.Shaper` setting. No built-in default or guessed shaper exists in this script.
- `shaper_source`: the actual engine revision, native source location and setting establishing those five numbers. This is caller evidence, not an automated source verification.
- `max_seconds`: an explicit value from 1 through 3600, such as 600. External process timeout also bounds startup/shader compilation.

The following is a JSON skeleton, not a runnable request. Replace the `profile` placeholder object with the complete measured profile, and replace every shaper placeholder string with its exact native numeric value (JSON numbers, not strings). Supply source evidence rather than retaining the placeholder text. `max_seconds` is the explicit capture budget, not an engine setting.

```json
{
  "disposable_qa_project": true,
  "profile": {
    "REPLACE_WITH_COMPLETE_ACTUAL_UE_PROFILE_OBJECT": true
  },
  "name": "ue58_capture_01",
  "shaper": {
    "base": "<EXACT_NATIVE_BASE_NUMBER>",
    "lin_side_slope": "<EXACT_NATIVE_LIN_SIDE_SLOPE_NUMBER>",
    "lin_side_offset": "<EXACT_NATIVE_LIN_SIDE_OFFSET_NUMBER>",
    "log_side_slope": "<EXACT_NATIVE_LOG_SIDE_SLOPE_NUMBER>",
    "log_side_offset": "<EXACT_NATIVE_LOG_SIDE_OFFSET_NUMBER>"
  },
  "shaper_source": "<ACTUAL_ENGINE_REVISION_NATIVE_SOURCE_LOCATION_AND_R_LUT_SHAPER_SETTING_RECEIPT>",
  "max_seconds": 600
}
```

Before launching UE, inspect the offline plan (read-only): `python scripts/lampway/ue_cube_generator_capture.py --plan "$UE_QA_REQUEST"`. A 32³ cube requires 32,780 actual captures including controls. Runtime is unmeasured until local control capture calibration; no seconds-per-capture is invented. The supplied time allowance is a hard refusal bound, not an estimated completion time. An 8³ pilot must not be passed off as a valid 32³ profile cube or used to change renderer settings silently.

```bash
timeout 720s "$UE_EDITOR_CMD" "$UE_QA_PROJECT" -unattended -NoSplash -RenderOffscreen \
  -ExecutePythonScript="$LAMPWAY_REPO/scripts/lampway/ue_cube_generator_capture.py" > "$UE_QA_CAPTURE_LOG" 2>&1
```

For a short bounded pilot, use a separate new output name and set only the QA request's `max_seconds` to `1`; retain the complete 32³ profile, shaper and actual engine settings. Run the same capture script with an external 120-second bound:

```bash
timeout 120s "$UE_EDITOR_CMD" "$UE_QA_PROJECT" -unattended -NoSplash -RenderOffscreen \
  -ExecutePythonScript="$LAMPWAY_REPO/scripts/lampway/ue_cube_generator_capture.py" > "$UE_QA_PILOT_LOG" 2>&1
```

The script attempts all 12 raw/display/disabled-tone control captures before the one-second full-grid allowance starts. If that allowance expires before the full grid completes, it refuses and writes no completed cube/sidecar. Runtime is unmeasured; the one-second budget is not a guarantee of how many samples complete. Reaching `LAMPWAY_UE_CUBE_PROGRESS 0/32768` indicates that the controls completed, but remains a private diagnostic marker, not physical acceptance or a valid cube. The external timeout also bounds startup and shader/control work; it may expire before the controls finish. Preserve the private log. Restore the explicit full-run capture budget and use another new name before the complete run; neither pilot nor full run changes renderer settings.

Use a real rendering backend and already-authorized scripting support. No desktop session, production project, `-NullRHI`, security-setting changes or paid/egress operations are needed. Outputs remain in that project's `Saved/LampwayCubeQA`; do not commit or redistribute them. No scene/material asset is saved. Temporary actors are destroyed on success or Python failure.

The script samples a flat unlit emissive plane with an isolated show-only capture. Four raw HDR readbacks verify the supplied linear RGB reaches the renderer. Corresponding engine FinalColorLDR outputs are recorded. A second capture disables the native tone curve and gamut expansion; the neutral-gray display pixel must differ by more than one output code value, or the run refuses. Exposure is manual with physical camera disabled and bias zero; bloom, vignette, motion blur, chromatic aberration and grading effects are disabled for the transform measurement. Applied postprocess values and override flags are read back; a mismatch refuses. Engine defaults/profile scene exposure are not baked into this transform.

Successful completion requires exactly one `LAMPWAY_UE_CUBE_COMPLETE` marker, a complete size³ cube and a hash-matching `lampway.ue-cube-meta/1` sidecar. Editor exit zero alone is insufficient. Retain the complete log and validate the resulting files with Lampway's existing cube validator against the same profile. The sidecar records actual engine version/changelist/raw identifier, exact requested profile hash, input shaper provenance, engine capture mode, display encoding/precision, postprocess readback and raw/disabled-tone controls. It does not prove the owner's supplied shaper source or working-space statement independently; retain their actual source/settings receipt alongside it.

Run the unchanged standalone cube validator against the actual request's profile and generated outputs. This imports only the pure `cube.py` module and requires no Blender process. Set `UE_QA_REQUEST` to the absolute `Saved/LampwayCubeQA/request.json` used for the completed run and retain the output privately:

```bash
python - "$LAMPWAY_REPO" "$UE_QA_REQUEST" > "$UE_QA_VALIDATION_LOG" 2>&1 <<'PY'
import importlib.util
import json
from pathlib import Path
import sys

repo = Path(sys.argv[1]).resolve()
request_path = Path(sys.argv[2]).resolve()
request = json.loads(request_path.read_text(encoding="utf-8"))
module_path = repo / "src/scripts/mixar/modules/lampway_tools/ue/cube.py"
spec = importlib.util.spec_from_file_location("lampway_cube_validation", module_path)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)
cube = request_path.parent / (request["name"] + ".cube")
sidecar = request_path.parent / (request["name"] + ".cube.json")
result = validator.require(request["profile"], cube=cube, meta=sidecar)
print(json.dumps(result, sort_keys=True))
PY
```

A missing or mismatched cube raises and gives a nonzero Python exit. A `state: valid` result checks the existing data contract; acceptance additionally requires the actual UE completion log, control readbacks, exact native shaper/source and working-space receipts. The validator does not independently prove how the cube was generated. Keep all generated cube bytes, sidecars and local path-bearing validation logs outside the repository.

Pure tests (synthetic fixtures only): `python -m pytest -q tests/lampway_tools/test_ue_cube_generator_probe.py tests/lampway_tools/test_ue_cube_generator_capture.py`. Actual UE render/cube proof remains pending.
