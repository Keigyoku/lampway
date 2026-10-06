<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 19 — Retargeting, game-rig extraction and baking, root motion, rest-pose change

Status: **CANONICAL** retarget, bake and root-motion maths; **DRAFT** game-rig scale policy (H.1). Implemented by: Lampway LT
`features/animation.py` (`animation_retarget`, method `matrix` and `constraints`); GRT `Deform_Rig_Generator.py`
(`gamerigtool.generate_game_rig`), GRT `GRT_Action_Bakery.py` (`gamerigtool.bake_action_bakery`), GRT
`GRT_Extra_Operators/*`; MB `GetAnimInRigCrea.py`, `GetAnimInWPose.py` (animation onto the converted rig), MB `rootmake.py`
(root bone for animation), MB `helperT.py`, `PoseUE.py` (rest change with mesh bake, UE pose), MB `MBRigfy.py` (Rigify deform
rig link/unlink).

## A. Problem

Four operations that every pipeline here runs and that are easy to get subtly wrong:

1. **Retarget** — play skeleton S's animation on skeleton T (different rests, different proportions).
2. **Game-rig extraction and bake** — from a control rig (Rigify, a tweak rig, a constraint stack) produce an engine-clean deform
   rig whose keys reproduce the control rig's motion, with no constraints left.
3. **Root motion** — derive a `root` bone's travel from the pelvis so the engine can move the capsule.
4. **Rest-pose change** — make a pose the new rest (e.g. the engine's reference A-pose) while the mesh keeps its shape.

## B. Method

1. **Retarget, rotations.** Per mapped pair the target's world rotation is `W_t = W_s R_s^-1 R_t` (the source bone's world
   change applied to the target's rest), solved parent-first into local keys (LT `animation.py:7-8, 212-262`; golden R04: along
   axes agree to 1e-4 deg, keys reproduce W within storage precision). Published basis: Gleicher 1998, "Retargetting Motion to New
   Characters" (SIGGRAPH); Monzani, Baerlocher, Boulic, Thalmann 2000, "Using an Intermediate Skeleton and Inverse Kinematics for
   Motion Retargeting" (Computer Graphics Forum 19(3)). Non-root bones key ROTATION only: the target keeps its own bone lengths.
2. **Retarget, root travel.** The pelvis (mode `transform`) moves by the source pelvis displacement times the pelvis-height ratio
   (LT `animation.py:216-244`); `in_place` zeroes the ground components. A separate `root` bone, when the profile has one, takes
   the travel by B.5.
3. **Two retarget falsifiers.** (a) Copying the source's LOCAL rotation onto a target with a different rest (a local Copy
   Rotation, a key copy): 55.7 deg wrong in R04; Lampway's `constraints` method copies WORLD rotation without rest compensation
   and warns above 5 deg (`animation.py:285-296`, `:348-349`). (b) Copy Transforms in POSE space (MB `GetAnimInRigCrea.py:168-172`,
   `:768-770`, after parenting every UE bone under its mapped SOURCE bone, `:244-717`): exact only when the target was built from
   the source's own rest (MB's case); onto another body it drags the target's joints to the source's geometry — R04: a 0.30 m
   bone driven by a 0.27 m one changes length by 30 mm.
4. **Game-rig extraction** (GRT's method, kept): copy the control rig; keep deform bones (`Extract_Mode` DEFORM / SELECTED /
   SELECTED_DEFORM / DEFORM_AND_SELECTED, `Deform_Rig_Generator.py:518-534`); reconcile the hierarchy — a deform bone whose parent
   is not deform takes its nearest deform ancestor, or the `ORG-` -> `DEF-` twin (`:421-438`, Rigify) — or keep / flatten it;
   disconnect; inherit rotation, scale FULL, local location; drop B-Bones, shapes, custom properties, animation data and every
   constraint; then constrain each game bone to its control twin (`LOTROT` default = Copy Location + Copy Rotation, optional Copy
   Scale from the root; `TRANSFORM` = Copy Transforms; `:581-606`) and re-point every Armature modifier from control to game rig,
   world matrix kept (`:612-624`). B-Bones are either refused or converted to one bone per segment (GRT `GRT_Convert_Bendy_Bones_To_Bones.py:136-291`:
   segment matrices from `bbone_segment_matrix(i, rest=True)`, an Armature constraint to the bendy bone, Damped Track to the
   next segment, Limit Scale 1 unless stretch).
5. **Root motion.** `root = T(x_pelvis, y_pelvis, 0) * R_z(yaw)` with `yaw = none` (default) or the heading of the pelvis's
   forward axis projected on the ground; `pelvis_local = root^-1 * pelvis` (R05: recomposition exact, root never tilted; copying
   the pelvis's whole rotation tilts the root 5.96 deg). MB builds the same with helper objects and constraints whose rotation
   toggles default OFF (`MagicBoneTop_Panel.py:5783-5785`; applied `GetAnimInRigCrea.py:869-895`, `rootmake.py:903-937`), i.e. yaw
   `none` by default — consistent with this canon.
6. **Bake** (control or retarget -> keys): sample the evaluated world matrices per frame and write parent-first local keys (the
   same solve as B.1 with an identity map); receipt = per-frame max world error between the baked rig and its driver (expected
   ~0). GRT bakes through `anim_utils.bake_action_objects` with visual keying, frame ranges ACTION / SET / TRIM with an inclusive
   end (`GRT_Action_Bakery.py:1221-1278`), naming by prefix / suffix / replace, overwrite by rename-remap-remove (`:1246-1252`),
   offset to frame one (`:1300-1306`), push to NLA (`:1310-1345`).
7. **Rest-pose change is one-way.** New rest mesh `v1 = LBS_P(v0)`, new bind = P, animation re-expressed per bone by
   `basis' = (rest'_local)^-1 rest_local basis`. Going BACK through the new bind is the blend of inverses (canon 04): R07, on
   C02's tube, 12.5 mm on 46 vertices; the exact inverse returns 0.0. So the original rest and its sha256 are kept, rest changes
   never chain, and a return uses `lbs_inverse` against the ORIGINAL bind. MB's rest change (`helperT.py:202-312`, `PoseUE.py:3076-3138`)
   joins every skinned mesh into one (`PoseUE.py:2950`), renames every UV layer `UVMap` (`:2910-2911`), applies the armature as a
   shape key and blends it into the basis: the joins and renames are refused side effects in the canon.
8. **A reference pose is data.** The engine's reference pose for an IK retargeter is written as `pose.json` (per-bone local
   rotations, the reference sha256); MB bakes it into a 2-frame action `UE5_Pose_For_IKRetar` and deletes every action without a
   fake user (`PoseUE.py:4030-4083`) — never delete actions.

## C. Invariants

- **INV-19.1** A retarget changes no target bone length (non-root channels are rotations).
- **INV-19.2** A bake's per-frame world error against its driver is reported; above 1e-4 m or 0.01 deg it fails.
- **INV-19.3** Root never pitches or rolls; `root * pelvis_local == pelvis` exactly.
- **INV-19.4** A rest change keeps the original rest (sha256) and is never chained; returning uses the exact inverse.
- **INV-19.5** No tool deletes actions, joins meshes, renames UV layers or touches preferences as a side effect.
- **INV-19.6** Every mesh still deforms after game-rig extraction (each Armature modifier points at the game rig; parent world
  matrix unchanged).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-05 (measured) | GRT game rig, default settings: of 5 deform bones only the LAST lands in the "Deform" collection (the clear-collections step runs inside the per-bone loop) | a per-bone loop must not reset shared state | headless probe; GRT `Deform_Rig_Generator.py:493-510` |
| 2026-10-05 (measured) | GRT preset "Flat Hierarchy with full Squash/Stretch" does not flatten: `execute` derives `Flat_Hierarchy` from `Hierarchy_Mode`, which the preset never sets; the preset also sets a property that no longer exists | presets are tested like code | probe; GRT `Deform_Rig_Generator.py:354-362`, `presets/.../Flat_Hierarchy_with_full_Squah_slash_Stretch.py:5,13` |
| 2026-10-05 (read) | GRT runs the text of a Text datablock with `exec` after generation when its toggle is on | a .blend can carry code; never exec scene data | GRT `Deform_Rig_Generator.py:630-633` |
| 2026-10-05 (read) | GRT's bake operator declares `bl_info` instead of `bl_options` (no undo), and skips every action silently when the control rig has no animation data | refusals must be loud | GRT `GRT_Action_Bakery.py:1079`, `:1153` |
| 2026-10-05 (read) | MB's batch export deletes every object in the scene after each file | a batch tool works in its own scene | MB `MagicBoneTop_Panel.py:32537-32538` |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G19.1 retarget (`R04_retarget`) | two 2-bone chains, rests differing by roll 90 / -30 deg, 5 frames | along axes agree (< 1e-4 deg); parent-first keys reproduce W | local copy 55.7 deg; pose-space copy 30 mm length change |
| G19.2 root motion (`R05_root_motion`) | 9 pelvis frames with yaw, pitch, roll | root z 0, tilt 0, exact recomposition, both yaw modes | full-rotation copy tilts 5.96 deg |
| G19.3 rest change (`R07_rest_change`) | C02's two-bone tube, 60 deg pose baked as rest | exact inverse returns 0.0 | return through the new bind 12.5 mm on 46 vertices |
| G19.4 game rig (to build, Blender) | the 9-bone probe rig (5 deform, 4 control) | 5 bones, all in the collection, hierarchy per mode, meshes re-pointed | GRT 4.3.0: 1 of 5 in the collection |

## F. Implementation gap

- Lampway (`4e9001c7`): retarget is close to canonical (B.1-B.3) but has no root-bone extraction (`root_motion` is `keep` |
  `in_place` on the pelvis, `animation.py:136-137, 240-244`), no game-rig extraction, no bake-to-keys tool beyond retarget, no
  rest-change tool, and writes `anim/presets/<src>__<tgt>.json` on every run (`animation.py:350-356`).

## G. Agent-facing tool contracts (specs in `rig_tools/`)

`lampway_rig_game_extract` (`rig_game_extract.md`), `lampway_rig_retarget` (`rig_retarget.md`, upgrades `animation_retarget`),
`lampway_rig_bake` (`rig_bake.md`), `lampway_rig_rest_pose` (`rig_rest_pose.md`).

## H. Decisions owed by the captain

1. Squash and stretch on game rigs: keep per-bone scale channels (GRT `TRANSFORM`) or drop them (`LOTROT`, GRT's default)?
   Unreal skeletons accept bone scale; the gameplay rig may not want it.
2. Root yaw: `none` (MB default, this canon's default) or `heading` for turn-in-place root motion.
