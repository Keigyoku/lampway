<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# UE cube generator: capability handoff

The first stage is a read-only probe, not a tonemapper cube generator. Run only in an explicitly disposable QA project using the actual UE 5.8.2 editor and an actual rendering backend. The QA project must already expose Python and editor scripting; this command changes no security settings or plugins.

```bash
timeout 120s "$UE_EDITOR_CMD" "$UE_QA_PROJECT" -unattended -NoSplash -RenderOffscreen \
  -ExecutePythonScript="$LAMPWAY_REPO/scripts/lampway/ue_cube_generator_probe.py" > "$UE_QA_LOG" 2>&1
```

Set those four variables to absolute local paths; retain the log outside the repository. Do not pass `-NullRHI`. Do not run against production assets or a desktop session. Parse the complete `LAMPWAY_UE_CUBE_PROBE` JSON line: `available: true` proves that the named Python surface exists, while `available: false` includes specific missing APIs and prints `error:` / `help[1]:`. A zero editor process exit does not prove Python succeeded. Missing or duplicate markers are a failed probe.

The marker records the actual raw engine version and queried render CVars. UE's console getter may return zero for an absent CVar, so the marker does not establish CVar existence. Verify `r.LUT.Shaper` and its precise log2 parameters against the actual local engine source/settings before generating any sidecar. No inferred, analytic or synthetic cube is a genuine UE cube.

A subsequent capture stage must sample unlit linear RGB through actual SceneCapture rendering, read float pixels with normalization disabled, verify raw scene-color input probes and a nonidentity tone-curve output, and preserve the exact engine/profile/shaper/settings plus capture provenance. Output display encoding must match Lampway's sRGB OCIO view: `SCS_FINAL_TONE_CURVE_HDR` alone is a linear capture and must not be mislabeled as an encoded display cube. Physical output proof is pending the actual UE run.

Official Python surface references (5.6 reference only; local 5.8.2 probe is authoritative): [RenderingLibrary](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/RenderingLibrary?application_version=5.6), [SceneCaptureComponent2D](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/SceneCaptureComponent2D?application_version=5.6), [PostProcessSettings](https://dev.epicgames.com/documentation/en-us/unreal-engine/python-api/class/PostProcessSettings?application_version=5.6).

Synthetic tests: `python -m pytest -q tests/lampway_tools/test_ue_cube_generator_probe.py`. These test refusal and claim discipline; they do not validate UE rendering or a cube.
