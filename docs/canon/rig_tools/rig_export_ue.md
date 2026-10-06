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
 "recipe": "titan_cm_native | <recipe.json>", "out": "export/<name>.fbx", "readback": true, "allow_container_top_bone": true}
```
`titan_cm_native` = cm-native FBX (`UnitScaleFactor 1`, `FBX_SCALE_NONE` + `apply_unit_scale`), primary bone axis Z, secondary
X, deform only, no leaf bones, baked actions only. It is the DEFAULT and it refuses every canon-17 rig at the read-back (120 deg
off `blender`, 90 deg off `ue_axes`; golden R08): Z / X is the round trip of a rig imported from the engine with Z / X. The
convention's own pairs are X / -Y (`blender`) and Y / X (`ue_axes`), same cm-native scaling; the default changes only after
ue_parity `M-RIG-01` confirms them in Unreal (canon 21 H.2). A recipe file states every exporter argument; nothing is left to defaults.
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
