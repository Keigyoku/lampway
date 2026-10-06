<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 16 — Skeleton mapping and rig creation: slots, naming families, missing joints, hierarchy

Status: **CANONICAL** mapping and synthesis rules; **DRAFT** family tables beyond Mixamo / Rigify (tables owed, see H).
Implemented by: Lampway LT `features/animation.py:44-68` (`build_mapping`: exact names, then label/side/number, spine and neck
by rank), LT `features/rig.py:52-75` (`_bone_table`, a fixed UE-named humanoid from height fractions); MB `CreateRig.py` (the
slot rename + synthesis + re-hierarchy), MB `MagicBoneTop_Panel.py:19258-30067` (`rigs_liss_my_op`, the per-family name tables);
Titan `tools/rig-axi.py:95-108` (`REQUIRED_JOINTS`, `PARENT_OF`). Sources and placeholders: `rig_tools/README.md` §Sources.

## A. Problem

Turn an arbitrary humanoid skeleton (a Mixamo export, a Rigify rig, a CC / DAZ / VRoid / AccuRIG rig, a hand-built armature, or
joints measured on a mesh) into the project's ONE bone grammar — the UE5 mannequin / MetaHuman body names (canon 01) — without
losing a joint and without inventing one silently. Inputs: the source bone names, their rest heads, their parents. Output: a
slot map `{ue_slot: source_bone}`, the list of synthesized slots with how each was placed, the target hierarchy, the unmapped
source bones (kept, never deleted), a `map.json` receipt.

## B. Method

1. **Slots are the UE5 mannequin bone names.** The 79 deform bones of GRT's Manny DEFORM armature (measured: 79 bones, all
   deform; plus 9 non-deform helpers in the Unreal armature: `ik_foot_root`, `ik_foot_l/r`, `ik_hand_root`, `ik_hand_gun`,
   `ik_hand_l/r`, `interaction`, `center_of_mass` = 88; headless probe 2026-10-05) and MB's slots (`bone_target1..78` +
   `bone_targetHip` = 79 bones; `bone_target79` is the root-motion source, `bone_target90` a rename suffix; MB
   `CreateRig.py:2353-2793` renames each mapped source bone to its UE name) are the same set. The REQUIRED set (refuse without them): `pelvis, spine_01, head, clavicle, upperarm, lowerarm, hand, thigh, calf,
   foot` per side — MB's create gate requires 17 slots (`CreateRig.py:82`), Lampway's retarget requires 15 (`animation.py:23`),
   Titan's fit requires 55 with fingers (`rig-axi.py:95-98`): the tool states which set it ran against.
2. **Family by table, never by substring.** Detect the naming family as the table naming the most source bones; a tie refuses
   and asks for `family=` (golden R01: a mixed Mixamo/Rigify list refuses). Map by the family table; a slot whose table name is
   absent is MISSING (reported), never filled by a substring guess (R01 falsifier: words `left`+`hand` take
   `mixamorig:LeftHandIndex1` for `hand_l`). After the table, Lampway's label/side/number parse (`animation.py:44-68`) is the
   fallback for families with no table, and its proposals are marked `by: label`, not `by: table`.
3. **Anatomical role, not index.** Rigify's `DEF-spine.003` is the CHEST and maps to `spine_05`, not `spine_03` (MB's table
   `MagicBoneTop_Panel.py:19324-19330`: Hip `DEF-spine`, spine_01 `.001`, spine_02 `.002`, spine_05 `.003`, neck_01 `.004`,
   neck_02 `.005`, head `.006`). The top of a source torso chain is always `spine_05`; the top of a neck chain `neck_02` /
   `head`.
4. **Missing joints are synthesized at the reference skeleton's arc-length fractions** along the source chain polyline (golden
   R01: `spine_03`, `spine_04` placed at fractions 0.500 / 0.722 of the reference chain). The reference is the project's native
   skeleton (canon 01: `NewMetaHumanCharacter_FullBody`), its fractions measured once and recorded in the map receipt. MB places a
   missing bone at the midpoint of two selected bones (`snap_cursor_to_selected`, e.g. `CreateRig.py:2852-2877`): off the
   reference by 65 mm in R01 — a falsifier, not a method. Missing twist bones: same rule on the limb segment (UE twist_01 /
   twist_02 fractions from the reference). Missing metacarpals: same rule between `hand` and the finger's `_01`.
5. **Hierarchy from the reference, applied after renaming.** Parents are the reference skeleton's (Titan `rig-axi.py:100-108`
   writes the UE layout); unmapped source bones keep their original parent re-pointed to the mapped ancestor (canon 07's
   ancestor remap). MB clears ALL parents (`CreateRig.py:2016`, `parent_clear CLEAR`) and re-parents by a hand-written list
   (`CreateRig.py:11811-12180`) whose existence guards are wrong in places (H.2).
6. **IK and helper bones** (`ik_foot_root`, `ik_foot_l/r`, `ik_hand_root`, `ik_hand_gun`, `ik_hand_l/r`, `center_of_mass`,
   `interaction`) are created only when the target profile asks for them: heads at the matching hand/foot heads, tails and rolls
   from the reference (MB copies tail/roll/length from its reference rig, `CreateRig.py:11499-11611`; parents `ik_hand_l/r ->
   ik_hand_gun -> ik_hand_root`, `ik_foot_l/r -> ik_foot_root`, `CreateRig.py:12176-12180`). They are non-deform.
7. **Collision-safe rename.** Before renaming into UE names, any source bone already carrying a UE slot name that is NOT the
   bone mapped to that slot is renamed out of the way with a recorded suffix (MB appends `bone_target90` to EVERY bone,
   `naming.py:20-24`; the canon renames only the colliding ones and records it).

## C. Invariants

- **INV-16.1** Every REQUIRED slot is mapped or the tool refuses; a refusal lists the missing slots by name.
- **INV-16.2** No source bone is deleted by mapping; unmapped bones are listed and kept (they may carry weights).
- **INV-16.3** A synthesized joint records its rule (`fraction f of chain c, reference sha256`) in `map.json`.
- **INV-16.4** The map is a receipt: `map.json` + the source rest sha256 + the reference rest sha256; re-running on the same
  inputs reproduces it byte for byte.
- **INV-16.5** Family detection never guesses on a tie.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-28 | A UE5 rig placed on the fitted warrior took the MetaHuman's joints, not the warrior's | joints come from the mesh being rigged (canon 20) | memory three-input-fit-pipeline; shelf `grt/rigfit.py:19-20` |
| 2026-10-05 (read) | MB right-hand re-parenting guarded by LEFT bone names: `bones.get("middle_metacarpal_l")` guards `middle_metacarpal_r` | one table drives both sides; never hand-written per side | MB `CreateRig.py:12097-12170` |
| 2026-10-05 (read) | MB `foot_l -> calf_l` guarded by `ball_l` existing | guard the bone you edit | MB `CreateRig.py:11816-11818` |
| 2026-10-05 (read) | MB writes the mannequin's ABSOLUTE heights into the source joints: ankle 8.2376 cm, ball 0.7508, toe 0.2213 (`footuezz`), clavicle tail Z and head X ±1.4279 (`ShoulderFix`); one guard compares a bone name to `False` (always true) | joints are measured, never overwritten by another body's numbers (canon 20 B.1) | MB `MagicBoneTop_Panel.py:13995-14044`, `:14020`; `ShoulderFix.py:656-698` |
| 2026-10-05 (read) | MB `SetTargetName` renames the user's armature object to `MB_RFRig` and sets the UI language to en_US | a mapping tool never renames inputs or touches preferences | MB `MagicBoneTop_Panel.py:15955, 15980, 16103` |

## E. Golden tests (`goldens/R01_mapping`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G16.1 family | 18 Mixamo-convention names | `mixamo`, 14 hits; 14 slots; no required missing | — |
| G16.2 tie | 6 Mixamo + 6 Rigify names | refused | a first-match detector picks one |
| G16.3 substring | words `left hand` | — | `hand_l` -> `mixamorig:LeftHandIndex1` |
| G16.4 synthesis | Rigify-like torso missing spine_03/04 | positions at reference fractions (0.500, 0.722) | midpoint 65.3 mm off |

## F. Implementation gap

- Lampway (wt-wave5 `4e9001c7`): mapping exists only inside retarget (`animation.py:44-68`), with no family tables, no tie
  refusal, no synthesis of missing joints, no map receipt; `rig.py:52-75` builds the skeleton from fixed height fractions
  (pelvis at 0.53 h, spine at 0.60/0.66/0.72, arms at 0.72 h), i.e. a T-pose template, not a mapped or measured skeleton.
- MB: correct intent, untestable form (one 13,144-line `execute`, `bpy.ops` with selection, state in 167 scene string
  properties); defects in D.
- GRT: no mapping (it duplicates an existing control rig; canon 19).

## G. Agent-facing tool contract — `lampway_rig_map` (spec: `rig_tools/rig_map.md`)

```json
{"armature": "object | file", "family": "auto|mixamo|rigify|cc|daz_g8|daz_g9|vroid|ue|accurig|<map.json>", "profile": "ue5_body|ue5_body_fingers|metahuman",
 "reference": "fit_body package | reference FBX", "synthesize": true, "out": "rig/<name>.map.json"}
```
Refusals: tie between families; a REQUIRED slot missing (named); reference unreadable; a synthesized slot whose chain has fewer
than two mapped joints. Receipt: `{family, hits, map, synthesized: {slot: {chain, fraction}}, unmapped, required_set,
sha256: {source_rest, reference_rest}}`.

## H. Decisions owed by the captain

1. Which families get shipped tables first (MB carries Rigify, ActorCore AccuRIG, Mixamo, UE4, Auto-Rig UE4, CC3/4, Human
   Generator, DAZ G8/G9 in five variants, VRoid VRM 0/1: `MagicBoneTop_Panel.py:5483-5535`).
2. Whether the REQUIRED set for armour work includes the 30 finger joints (Titan's fit requires them; MB and Lampway do not).
