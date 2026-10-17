<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 18 — Rig scale and units: unit factor, applying object scale with animation, size matching

Status: **CANONICAL**. Implemented by: GRT `addition/ops_scale.py` + `addition/utils.py` (Apply Armature Scale, credited in GRT
`Preferences.py:82-88` to Xin, gitlab x190/apply_armature_scale); MB `AutoScalenew.py` (`mb.autoscaler`, `mb.charautoffs`), MB
`ApplyScalear.py`, MB `MagicBoneTop_Panel.py:16154-16530` (`Button_SetScalerf`); Lampway LT `features/animation.py:216-221` (root
scale by pelvis height), LT `features/export_checks.py:65-113` (unit-scale read against a reference).

## A. Problem

Skeletons arrive in metres, centimetres or inches, with object scale, with scene unit scale, with animation keyed in the scaled
space. Lampway works in metres in the body frame (canon 01); the engine imports centimetres (canon 21). Three different
operations hide under "scale": (1) declaring the unit of the data, (2) applying an object scale into the rest without moving
anything, (3) matching one character's size to another. They are never the same step.

## B. Method

1. **Unit factor from measurement, never assumed.** Read object scale, scene `unit_settings.scale_length`, and the measured
   height (floor to top of `head`, or pelvis height when no head); compare to the reference skeleton's; accept a factor in
   {1, 0.01, 100, 0.0254, 39.37} only when the ratio lands within 5 % of it, else refuse naming the ratio (the reference-height
   read is LT `export_checks.py:96`). MB multiplies the object by 100 and sets the scene unit to 0.01 unconditionally
   (`AutoScalenew.py:213-216, 290`) — correct only for a metre-authored source.
   A caller may explicitly declare `unit=m|cm|in` at the normalization door;
   record that declaration as `unit_metadata`, retain the measured reference
   ratio, and apply only the declared unit factor. A different character size
   (for example1.258 times the reference) is not a guessed unit conversion.
2. **Applying a uniform object scale s** to an animated armature: rest heads x s, pose-bone location keys x s (all bones, both
   handles), and unkeyed current pose locations x s. Object-level location keys and rotation keys stay untouched. Uniform rest writes preserve the authored armature-space rotation, scaling only matrix translation and length through edit RNA; the native recursive parent-local roll re-extraction is not needed for a scalar transform. Exact (golden R03 uniform control: 0.0 m).
3. **A non-uniform object scale S** has NO rotation-only equivalent once bones are posed: `S R_rest B` is not a rotation times a
   rest when S is not uniform. Translation keys transfer exactly by `loc' = R'^T S R_rest loc` with `R' = polar(S R_rest)`
   (R03: world offset (0.4, -0.1, 0.9) kept); rotation keys do not. The tool therefore applies S to an UNANIMATED armature
   (rest frames re-orthonormalised by the polar factor, heads scaled) and REFUSES on an animated one, naming the bones with
   rotation keys and the scale. GRT multiplies each pose-bone location channel by the object scale of the same index
   (`addition/utils.py:110-123`): exact for uniform scale, wrong otherwise — measured headless on Blender 5.2.1 with GRT 4.3.0,
   scale (2, 1, 3), a bone along +X: the bone moved 0.2236 m (R03 falsifier reproduces Blender's numbers exactly).
4. **Size matching is not part of rigging.** The example keeps its own size (canon 20: its joints ARE the measurement). A size
   ratio is computed, recorded and used only where a method needs it: root travel in retargeting (pelvis-height ratio, LT
   `animation.py:216-221`; canon 19) and proportion comparisons (canon 10). MB asks the person to scale the character until its
   hips meet an empty at the mannequin's pelvis height (`MagicBoneTop_Panel.py:16310`: location (0, -2.3795, 98.6932) cm;
   "use only scale to Align character feet with the ground", `:16408-16410`) — a manual size normalisation the canon replaces by
   the recorded ratio.

## C. Invariants

- **INV-18.1** After applying scale, every bone's world head and every keyed world pose of an unanimated or uniformly scaled
  armature is unchanged (tolerance 1e-6 m).
- **INV-18.2** A non-uniform scale is never applied to an animated armature.
- **INV-18.3** A unit factor is a recorded decision with its measured ratio; no silent x100.
- **INV-18.4** Scaling never runs on a copy the user did not ask for and never deletes keys.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-05 (measured) | GRT Apply Armature Scale, non-uniform (2, 1, 3): bone moved 0.2236 m; uniform (2, 2, 2): 0.0 | refuse non-uniform on animated rigs | headless probe; GRT `addition/utils.py:110-123` |
| 2026-10-05 (read) | MB Apply Scale: a generator consumed by a nested loop leaves the FIRST location f-curve unscaled; only `scale[0]` is used; it runs only when `scale[0] > 1` | test the transfer, never trust the loop | MB `ApplyScalear.py:18`, `:108-121` |
| 2026-10-05 (measured) | MB Apply Scale reads `action.fcurves`, which Blender 5.2 does not have (`Action.fcurves` False, `Action.layers` True) | an add-on that claims 5.1 still carries the 4.3 API in places | headless probe; MB `ApplyScalear.py:108` |
| 2026-09-30 | FBX bones carried scale 100 although the frames were right | the unit is part of the export recipe (canon 21) | memory native-body-canonical-for-fit |

| 2026-10-09 (measured) | Actual own-warrior root at object scale0.01 with unkeyed pelvis translation: old normalization drift4.82m; corrected scalar rest/pose transfer drift9.685754776e-7m; four saved variants3.5762786865e-7m | transfer unkeyed locations, retain authored rest rotation and unchanged1e-6m guard; rollback restores NLA keys on their original action IDs | isolated original-input copies, normalization follow-up |

## E. Golden tests (`goldens/R03_apply_scale`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G18.1 non-uniform, translation | bone rest (local X -> world -Y), S (2, 1, 3), loc (0.1, 0.2, 0.3) | new loc (0.1, 0.4, 0.9), world (0.4, -0.1, 0.9) kept | per-channel: world (0.2, -0.2, 0.9), 0.2236 m (= Blender 5.2 measured) |
| G18.2 uniform | S (2, 2, 2) | both methods exact | — |
| G18.3 refusal (to build in the tool's tests) | an animated armature, S (2, 1, 3), one rotation key | refused, bone named | applying it |

## F. Implementation gap

- Lampway (`4e9001c7`): no apply-scale tool; `export_checks.skeleton_check` READS the unit ratio against a reference and reports
  a 100x export (`export_checks.py:96`, `:107-108`) but nothing fixes it.

## G. Agent-facing tool contract — `lampway_rig_normalize` (spec: `rig_tools/rig_normalize.md`)

```json
{"armature": "object", "unit": "auto|m|cm|in", "apply_scale": true, "reference": "fit_body package | reference FBX", "dry_run": false}
```
Refusals: non-uniform scale on an animated armature (bones listed); unit ratio not within 5 % of a known factor (ratio printed);
negative scale (mirroring is a separate, explicit operation). Receipt: `{unit_factor, measured_ratio, applied_scale,
keys_scaled: {bones, fcurves}, max_world_drift_m}` — the drift measured by re-evaluating 8 frames before and after.

## H. Decisions owed by the captain

1. Whether Lampway ever auto-converts units without a dry run first (recommended: dry run by default, the receipt shows the
   factor, a second call applies).
