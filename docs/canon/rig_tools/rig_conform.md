<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# `lampway_rig_conform` — turn a mapped rig into the project's skeleton (names, missing bones, hierarchy, frames)

**Build order 4.** Canon 16 (B.4-B.7), 17. The rewrite of MB's "Create UE5 Rig".

## Purpose

Given a rig, its `map.json` and the reference skeleton, write a copy whose bones carry the UE names, whose missing bones exist at
their measured fractions, whose hierarchy is the reference's, whose frames follow canon 17 in one convention, and whose skin
still deforms identically at rest.

## Upstream

Re-implemented from documented behaviour; nothing ported. MB `CreateRig.py` (`CreatRig_OT_my_op.execute`, one 13,144-line
method) does, in order: remove Subdivision modifiers (`:88-96`), optional root motion and auto scale, delete existing `ik_*`
bones (`:158-218`), finger and spine fixes, clear every parent (`:2016`), add ik bones (`:2035-2317`), rename mapped bones
(`:2353-2793`), synthesize missing twist/neck/spine/metacarpal bones at midpoints (`:2837-7109`), orient chains by constraint
stacks and Apply Pose as Rest (`:7164-10742`), copy rotations from the reference rig (`:10853-11378`), copy ik tails/rolls
(`:11499-11611`), re-parent by a hand-written list (`:11811-12180`), delete helper bones (`:12204-12324`), rename the armature
object `root` (`:12536`), merge DAZ metatarsal weights into the foot (`:12895-13000`). The canon keeps the intent and replaces
every mechanism: synthesis at reference fractions (R01), frames in closed form (R02), hierarchy from the reference, no deletion,
no global parent clear, and the defects listed in canons 16 D and 17 D cannot occur because sides and chains are generated.

## Contract

```json
{"armature": "object", "map": "rig/<name>.map.json", "reference": "source_copy | fit_body package | reference FBX", "convention": "blender|ue_axes",
 "ik_bones": false, "offsets": {"<bone>": {"roll_deg": 0.0}}, "merge_weights": {"<from_group>": "<to_bone>"}, "out_name": "<name>_ue",
 "dry_run": true}
```
Steps: (1) copy; (2) collision-safe rename of colliding names; (3) rename mapped bones; (4) synthesize missing bones (rule from
the map); (5) re-parent to the reference hierarchy, unmapped bones to their mapped ancestor; (6) frames by canon 17 (heads never
move); (7) optional ik bones; (8) vertex groups renamed with their bones; `merge_weights` only when named (MB's DAZ metatarsal
merge becomes an explicit, recorded argument); (9) verify.
Refusals: no map or a map whose source sha differs; `mixed` output convention; a step moving any rest head (> 1e-9 m); any
vertex's rest position changing (> 1e-9 m) after the frame rewrite (the skin is re-bound by the exact rest change of canon 19
B.7, never by re-weighting).
Receipt: `{renamed, synthesized, reparented, frames: {bone: angle_to_reference_deg}, convention, merged_groups,
rest_vertex_drift_m, sha256: {input, map, reference, output}}`.

For the verified native342 topology, an omitted reference refuses instead of
substituting the shipped161-bone Manny profile. `reference="source_copy"` is an
explicit preservation operation: require the complete native graph, identity
mapping and a measured convention matching the requested convention. Refuse
mixed/unknown frames, synthesis, offsets, IK additions and weight merging before
copies. Preserve authored heads, tails, rest frames, parent edges, flags and skin
weights on independent copies, bypassing EditBone reconstruction. Original pose,
actions and data remain unchanged; the result has no animation, as with ordinary
conform. Receipt fields `reference_scope="source_preservation"` and
`engine_bind_acceptance` explicitly retain unverified native UE parity. This mode
does not supply an independent native reference or repair a native pose mismatch.
Generic, non-native conform retains its existing reference-driven construction.

An explicit independent native profile on the exact complete342 graph uses
canon17's reference-bind calibration when its joints already match the source
under0.01cm. Preserve each source head and length; carry the independent engine
frame through the fixed inverse writer bridge for `blender`, or directly for
`ue_axes`. Reject synthesis, offsets, IK, nonidentity maps and invalid reference
rotation/scale before allocation. Verify Blender's stored frame under the
unchanged0.01degree bar and retain the rest/posed-skin checks. A private
`lw_native_reference_bind` receipt binds the independent reference rows and
declared axes to the output rest fingerprint. `reference_scope` is
`independent_native_bind`; actual UE import acceptance remains unverified.
This bounded path calibrates a matching native body; it does not fit different
reference joints or claim a general native reference construction algorithm.

## Goldens

R01 (synthesis), R02 (frames, roll independence); a Blender-side test conforms a Mixamo-named synthetic 22-bone rig and
asserts names, hierarchy, frames and zero rest drift.

## Place in the three-input pipeline

Gives a rigged example (or any animation source) the native bone grammar so the pose solver (canon 08) and the retargeter speak
one language.

## Upgrades

Replaces LT `rig.auto_rig`'s fixed table (`rig.py:52-75`) for rigs that arrive with bones; `auto_rig` stays only as the
no-joints fallback and says so.
