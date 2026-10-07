<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_export_ue` — write the FBX the engine reads, and prove it bone by bone

**Build order 5** (the read-back half belongs to O36's first slice). Canon 21.

## Purpose

Export an armature with its meshes and actions using the recipe that passed the reference, then read the file back and compare
every bone's position, rotation and scale to the reference; refuse to publish otherwise.

## Upstream

Re-implemented. MB's export (`PoseUE.py:4189-4205`: selection, deform-only, no leaf bones, `mesh_smooth_type='EDGE'`, no axis
or scale arguments) and batch export (`MagicBoneTop_Panel.py:32429-32650`, which deletes the scene after each file) are not
ported; GRT has no exporter (its export rig is the armature object named `root`, measured). The recipe is Titan's measured one
(memory native-body-canonical-for-fit, 2026-09-30); the bone comparison is Titan's `bind_mismatch` (`armour_validate.py:414-433`:
0.01 cm, 0.01 deg, 1e-4 scale).

## Contract

```json
{"armature": "object", "meshes": ["objects"], "actions": ["names"], "reference": "reference FBX | fit_body package",
 "recipe": "auto | titan_cm_native | cm_native_blender_convention | cm_native_ue_axes | <recipe.json>", "out": "export/<name>.fbx", "readback": true, "allow_container_top_bone": true}
```
`auto` is the default: select from the armature's measured normalized convention, never its name. A `blender` rig uses X / -Y; a `ue_axes` rig uses Y / X, both with explicit centimetre export copies (`export_coordinates=cm`), raw identity Null scale, `UnitScaleFactor1`, `FBX_SCALE_NONE` + `apply_unit_scale`. Effective global_scale cancels the pinned writer scene-unit factor on copies only. Temporary readback decodes the pinned importer unit carrier after raw ancestor/bone admission; no authored rest or geometry mutation is needed. The receipt records requested recipe, measured convention, selected recipe and source. Explicit `titan_cm_native` retains legacy engine-native Z / X; on canon-17 rigs its raw-frame readback still refuses120°/90° mismatches.

Issue2's actual default-chain failure requirement supersedes the earlier policy of leaving an inevitably refused recipe as default. This changes recipe selection, not acceptance bars: every bone still meets0.01cm /0.01° /1e-4 scale. Physical Unreal `M-RIG-01` confirmation remains mandatory and pending; a Blender PASS does not claim it. Mixed frames still refuse and must be conformed. Shipped recipe names resolve directly; explicit recipe files state every exporter argument.
Refusals: `mixed` convention (canon 17); root or hierarchy differing from the reference (the container top bone accepted and
named); leaf bones; a vertex group naming a bone the reference lacks; constraints present; a read-back row over tolerance
(rows listed, the file moved to `export/rejected/`); an existing different `out`.
Receipt: `{recipe, convention, readback: {bones_compared, worst_position_cm, worst_rotation_deg, worst_scale, over_tolerance},
normals: {corner_max_deg}, sha256: {fbx, reference, armature_rest}}`.

## Goldens

G21.1 (refuses R02's mixed set); G21.2/G21.3 to build headless: a synthetic 5-bone chain exported with each axis pair and each
scaling mode, re-imported with `automatic_bone_orientation=False`; the falsifiers are the 90 deg frames of primary Y and the
x100 scale of default scaling — Titan's two measured failures reproduced on synthetic data.

## Place in the three-input pipeline

The last step for the pieces (bound to the native body) and for any rig going to the engine; the read-back is the evidence the
REPORT and the captain read.

## Upgrades

Adds frames and per-bone scale to LT `skeleton_export_check` (`export_checks.py:52-113` keeps parent and length only) and makes
LT `fit_export` (`fit_export.py`) call it as its read-back.
