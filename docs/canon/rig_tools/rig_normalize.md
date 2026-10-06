<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_normalize` — units and object scale, applied without moving anything

**Build order 3.** Canon 18.

## Purpose

Make an armature unit-correct and scale-free (object scale 1) with every rest joint and every keyed pose landing where it was,
or refuse when that is impossible (non-uniform scale on an animated rig).

## Upstream

Re-implemented. GRT's Apply Armature Scale (`addition/ops_scale.py`, `addition/utils.py:78-125`; credited to Xin,
gitlab x190/apply_armature_scale, GRT `Preferences.py:82-88`) multiplies each pose-bone location channel by the object scale of
the same index — exact for uniform scale, 0.2236 m wrong on R03's non-uniform case (measured on Blender 5.2.1). MB's auto scale
multiplies by 100 unconditionally (`AutoScalenew.py:290`) and its Apply Scale skips the first location f-curve and reads the
removed `action.fcurves` (`ApplyScalear.py:108-121`). Neither is ported; their behaviour is the falsifier.

## Contract

```json
{"armature": "object", "unit": "auto|m|cm|in", "apply_scale": true, "reference": "fit_body package | reference FBX", "dry_run": true}
```
Method: canon 18 B.1-B.3 — uniform s: rest heads x s, pose-bone location keys and handles x s, rotation keys untouched;
non-uniform S: applied only to an unanimated rig (rests re-orthonormalised by `polar(S R)`), refused otherwise.
Refusals: non-uniform scale with rotation keys (bones named); negative scale; unit ratio not within 5 % of a known factor; the
input not inspected (no `rig_inspect` receipt sha).
Receipt: `{unit_factor, measured_ratio, applied_scale, keys_scaled: {bones, fcurves}, max_world_drift_m, frames_checked: 8,
sha256: {input, output}}` — the drift measured by evaluating 8 frames before and after; above 1e-6 m the call fails and rolls
back.

## Goldens

R03 (exact translation transfer; the per-channel falsifier equal to Blender's measured numbers; the uniform control); G18.3
(refusal, built in the tool's test with a rotation key).

## Place in the three-input pipeline

Every external rig (example or animation source) is normalized before mapping and conforming; the native body never needs it
(cm-native import recorded once).

## Upgrades

New. `skeleton_export_check`'s unit read (`export_checks.py:96`) stays the export-side detector.
