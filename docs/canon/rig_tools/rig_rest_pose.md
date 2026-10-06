<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_rest_pose` — make a pose the rest, once, and say what it cost

**Build order 11.** Canon 19 B.7-B.8, canon 04 (the exact inverse).

## Purpose

Change a skinned character's rest pose to a given pose (the engine's reference A-pose for an IK retargeter, a fit pose) with the
mesh keeping its shape and every action re-expressed, as a declared one-way step whose receipt keeps the original rest and
reports what returning would cost.

## Upstream

Re-implemented from documented behaviour; nothing ported. MB `helperT.py` (`helper_OT_op`, `:14-416`): duplicate rig as a
helper, join all skinned meshes (`:137`), apply the armature modifier as a shape key and blend it into the basis (`:202-288`),
Apply Pose as Rest (`:312`), re-drive the rig from the helper by Copy Rotation / Location / Scale and bake (`:322-370`). MB
`PoseUE.py` `posemake_op` (`:2589-3782`): the same against the mannequin reference rig, plus renaming every UV layer to
`UVMap` (`:2910-2911`), joining meshes (`:2950`), and `animpose_only_op` storing the reference pose as a 2-frame action while
deleting every action without a fake user (`:4030-4083`). The joins, renames and deletions are refused side effects.

## Contract

```json
{"armature": "object", "meshes": ["objects"], "pose": "pose.json | action:frame | reference", "actions": "all|[names]",
 "keep_original": true, "out_suffix": "_rest2", "dry_run": true}
```
Method: per mesh `v1 = LBS_P(v0)` (no join, UV layers untouched); per bone the new rest = the pose; per action
`basis' = (rest'_local)^-1 rest_local basis`; the original rest, its mesh and its sha256 are kept on the receipt (and, with
`keep_original`, as a hidden copy).
Refusals: a rig whose rest was already changed by this tool (no chaining: return through the original first); shape keys on a
mesh (each key must be re-baked through the same LBS — refused until requested explicitly); non-uniform scale (canon 18).
Receipt: `{pose_sha256, original_rest_sha256, new_rest_sha256, meshes: {name: {moved_max_m}}, actions_rewritten,
return_cost: {blend_of_inverses_max_m, vertices_over_1mm}}` — `return_cost` computed from canon 04 (exact inverse vs blend of
inverses) so the person sees what a naive return would do.

## Goldens

R07 (C02's tube: the exact inverse returns 0.0; returning through the new bind 12.5 mm on 46 vertices).

## Place in the three-input pipeline

Used when the engine's IK retargeter needs a rest that matches the reference pose; never on the pieces' bind (the pieces bind at
the native body's reference, canon 04/05).

## Upgrades

New.
