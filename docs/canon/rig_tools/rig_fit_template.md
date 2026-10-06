<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_fit_template` — rig the fitted example at its OWN joints

**Build order 7.** Canon 20 (with 11 for joints from views, 16 synthesis, 17 frames, 07 weights).

## Purpose

The rig step of the three-input pipeline: the native skeleton placed at joints measured on the fitted example, the example's
own weights from the procedural body, an inside check, and a provenance check that refuses the 2026-09-28 defect (joints copied
from the template's body).

## Upstream

- **GRT Unreal module (re-implemented from documented behaviour):** `grt.append_mannequin` appends a collection with three
  armatures — TWEAK (controls, 410 bones), DEFORM (79, Blender-native frames), `root` (88, engine axes) — identified by name
  (`Operators/Append_Mannequin.py:51-94`); the person moves TWEAK controls onto the character; `grt.apply_rig` bakes each
  armature's constraint result into its rest (`Operators/Apply_Rig.py:30-51`, `Utility_Functions.py:50-82`); `grt.switch_parent_armature`
  swaps meshes between DEFORM and `root` (`Switch_Parent_Armature.py:24-38`); `grt.copy_additional_bones_to_root` joins the
  deform rig's extra bones into `root` (`Copy_Additional_Bone_To_Root.py:46-115`). The Mannequin `.blend` assets are Epic
  content and are not used: the template is the project's native skeleton.
- **Titan `tools/rig-axi.py` (port on the captain's word, H.1):** verbs `joints --from-views | --hands | --pose`, `fit`,
  `check`, `slices`, `weights` (docstring `rig-axi.py:10-59`); joints schema `titan.rig-joints/1` (`:94`, `:165-179`);
  required joints (`:95-98`); the views pipeline (`:373-429`) and hands (`:357-370`); the fit by damped Gauss-Newton over GRT's
  controls (`:29-31`, recipe `tools/recipes/rig-blender.py`). The Lampway port writes joints directly (closed form, canon 20
  B.2) and keeps Gauss-Newton only for control-rig templates.

## Contract

```json
{"example": "object | .glb", "joints": "joints.json | 'views' | 'rig:<armature>'", "template": "fit_body package",
 "hands": "views|none", "hidden": ["pelvis", "thigh_l", "thigh_r"], "convention": "blender", "weights": "procedural|none",
 "allow_outside": [], "out": "rig/<example>.rig.blend", "dry_run": false}
```
Steps: joints (measured, or loaded and provenance-checked) -> template copy -> write joint heads -> synthesize unmeasured bones
(template fractions) -> frames (canon 17) -> inside check (six axis rays per joint) -> procedural-body weights transferred to
the example (canon 07) -> receipt.
Refusals: joints file `example_sha256` != the example's sha256; `copied_not_fitted` (every bone length within 0.1 % of the
template's) unless the example IS the template body; a required joint missing; joints outside the example not named in
`allow_outside`; `views` requested without the pose environment (the refusal names it; detector choice is the captain's,
canon 11).
Receipt: `{residual: {rms_m, max_m}, ratios: {bone: r}, synthesized, hidden, outside, inside_rays, weights: {source, unweighted},
sha256: {example, joints, template, out}}`.

## Goldens

R06 (closed-form fit, residual 0; ratios 1.08 / 0.95; `copied_not_fitted` on template joints; missing-joint refusal). The
regression pin on the captain's warrior (rig_axi run3: rms 0.017 cm, max 0.045 cm, 11 finger joints outside before the hand
pass) runs only where the shelf is mounted and skips with a stated reason elsewhere.

## Place in the three-input pipeline

Step one: the example rigged from itself; then the pose solver (canon 08) poses example and native body the same; the pieces
then bind on the native body (ruling 2026-09-30).

## Upgrades

Replaces LT `rig.auto_rig` (`rig.py:131-157`: a T-pose skeleton from height fractions, heat-map weights) for the fitted example;
`auto_rig` remains the generic quick rig for un-measured props and says so in its receipt.

## Decisions owed

1. Port Titan's `rig-axi.py`, `views_joints.py`, `hand_pose.py`, `proc_body.py` into Lampway, or call them externally?
2. Hidden joints under armour (canon 20 H.1).
