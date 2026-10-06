<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_inspect` — read any skeleton and say what it is

**Build order 1.** Canon 16 (family, slots), 17 (convention), 18 (units). Read-only.

## Purpose

Before an agent maps, scales, conforms, retargets or exports anything, it asks this tool what the skeleton IS: naming family,
mapped and missing slots, the frame convention, the unit factor, scale, animation, constraints, B-Bones, leaf bones and helper
bones. Every other rig tool refuses on input it did not inspect (the receipt sha256 is their precondition).

## Upstream

Re-implemented from documented behaviour. MB's `Button_Checkbones` (`MagicBoneTop_Panel.py:16533-18904`) warns slot by slot
when a required bone is missing; MB's `SetTargetName_OT_my_op` (`:15933-16117`) also renames the armature and sets the UI
language — refused side effects here. Nothing is ported.

## Contract

```json
{"armature": "object | .fbx | .glb | .blend", "reference": "fit_body package | reference FBX (optional)", "family": "auto|<name>", "profile": "ue5_body|ue5_body_fingers|metahuman"}
```
Receipt:
```json
{"ok": true, "bones": 0, "deform": 0, "roots": [], "family": {"name": "", "hits": {}}, "slots": {"mapped": {}, "missing_required": []},
 "convention": {"class": "blender|ue_axes|mixed", "angles_deg": {"median": 0, "min": 0, "max": 0}},
 "units": {"scene_scale_length": 1.0, "object_scale": [1, 1, 1], "height_m": 0, "ratio_to_reference": 1.0, "factor": "1|0.01|100|..."},
 "animation": {"actions": [], "frame_ranges": {}, "rotation_keys": 0, "location_keys": 0, "scale_keys": 0},
 "constraints": 0, "bbones": [], "leaf_bones": [], "helpers": [], "sha256": {"input": "", "reference": ""}}
```
Refusals: no armature in the input; more than one armature without `armature=` naming one; an unreadable reference.
Never refuses on a defect of the rig — it reports it (that is its job).

## Goldens

R01 (family + slots + tie), R02 (convention classes on the stored frames). Tests import the cases and build the armature in a
factory-empty headless scene.

## Place in the three-input pipeline

The example arriving rigged (canon 20 B.1c) and every animation source start here; the pieces' armature (the native body's) is
inspected against the reference before export.

## Upgrades

New. It reads what LT `export_checks.skeleton_check` reads (`export_checks.py:52-113`) plus frames, slots, units and
animation; `skeleton_check` keeps its role as the export gate (canon 21).
