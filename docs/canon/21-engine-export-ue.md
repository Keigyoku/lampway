<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 21 — Engine export (Unreal): the skeleton the engine reads, and the read-back that proves it

Status: **CANONICAL** gate and the measured Titan recipe; **DRAFT** for any engine other than Unreal 5.8. Implemented by: Lampway
LT `features/export_checks.py` (`skeleton_export_check`, `engine_import_check`), LT `features/fit_export.py` (rigged export behind
gates, with a read-back), LT `features/batch_export.py`; Titan `tools/armour_validate.py:414-433` (`bind_mismatch`, the bone-by-bone
bind check); MB `PoseUE.py:4130-4205` (`exportfbxf.m_operator`), MB `MagicBoneTop_Panel.py:32429-32650` (batch export); GRT
Unreal module (export rig = the armature object `root`; no export operator of its own).

## A. Problem

An exported skeleton is right when the ENGINE reads every bone at the reference's position, rotation and scale — not when the
bone names match. Inputs: the armature (deform rig, frames per canon 17), the reference skeleton (the project's native body), the
meshes and actions. Output: an FBX, and a read-back receipt comparing every bone's bind against the reference.

## B. Method

1. **Gate first, settings second.** The export is accepted when a read-back of the written file matches the reference bone by
   bone: position <= 0.01 cm, rotation <= 0.01 deg, scale <= 1e-4 (Titan `armour_validate.py:414-433`, `bind_mismatch`), plus
   names, parents, root, no leaf bones (LT `export_checks.py:65-113`). The FBX settings are whatever passes that gate on the
   reference, recorded with the receipt.
2. **The recipe Titan measured on the native body (2026-09-30, memory native-body-canonical-for-fit):** a centimetre-native FBX
   (`UnitScaleFactor 1`; `FBX_SCALE_NONE` with `apply_unit_scale`), primary bone axis Z, secondary X, passes all 342 bone rows
   and the leader-driven rest of the test rivet. Two failures on the way, both now refusals of the gate: `primary_bone_axis='Y'`
   matched joint POSITIONS to 1e-4 cm while frames rotated up to 90 deg (gear moved up to 28.8 cm); primary Z / secondary X with
   default scaling left scale 100 on every bone.
3. **Hierarchy and root follow the reference.** The native MetaHuman has a real `root` bone; its armature container imports as
   one more top bone (`NewMetaHumanCharacter_FullBody`, parent of `root`, identity, scale 1 — accepted, recorded). GRT and MB
   instead name the ARMATURE OBJECT `root` and have no `root` bone (GRT's Unreal armature: 88 bones, none named `root`, measured;
   MB `CreateRig.py:12536-12538`). The two are different skeletons to the engine: the root check (LT `export_checks.py:93-106`)
   refuses the mismatch; never mix them.
4. **Deform bones only, no leaf bones, no helpers the reference lacks.** `use_armature_deform_only`, `add_leaf_bones` off (MB
   `PoseUE.py:4189-4205` sets both; LT `skeleton_check` reports leaves). IK helper bones (`ik_*`, `center_of_mass`,
   `interaction`) are exported only if the reference has them (canon 16 B.6).
5. **Frames in one convention** (canon 17 B.1): a `mixed` armature is refused before writing. The convention inside Blender and
   the axis settings form a PAIR; the read-back proves the pair.
6. **Animation:** baked keys only (canon 19), no constraints, one action per clip, frame range recorded; root motion per canon 19.
7. **Meshes:** one skinned mesh per piece, vertex groups naming only bones the reference has (LT `fit_export.py` gates it),
   normals preserved and compared corner by corner on read-back (Titan tools rail, wave4-tools-9: canonical corner shading and
   actual FBX normal preservation). MB exports with `mesh_smooth_type='EDGE'` and no normal check (`PoseUE.py:4195`).
8. **The engine import is a receipt, not an assumption.** The import settings (Interchange) are recorded; Titan changed none
   (memory native-body-canonical-for-fit). LT `engine_import_check` records a hand-run import's receipt (`export_checks.py:127-172`).

## C. Invariants

- **INV-21.1** No export without a read-back that compares every bone's position, rotation and scale to the reference.
- **INV-21.2** Root and hierarchy equal the reference's (the container top bone is the one accepted extra, named).
- **INV-21.3** No leaf bones; no bone the reference lacks unless declared.
- **INV-21.4** The convention-and-axes pair is recorded with the file's sha256.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-30 | `primary_bone_axis='Y'`: positions 1e-4 cm, frames up to 90 deg off, gear 28.8 cm off | read back FRAMES | memory native-body-canonical-for-fit |
| 2026-09-30 | primary Z / secondary X: frames right, scale 100 on every bone | read back SCALE; cm-native recipe | same |
| 2026-10-05 (read) | MB export passes no axis or scale arguments and relies on the scene unit 0.01 + object x100 it set earlier | an export recipe is explicit and gated | MB `PoseUE.py:4189-4205`, `AutoScalenew.py:213-216, 290` |
| 2026-10-05 (read) | Lampway's skeleton check holds parent and length per bone, not frames: the 28.8 cm case passes it | add the frame rows | LT `export_checks.py:52-62` |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G21.1 convention gate | R02's mixed set | refused before writing | an exporter that writes it |
| G21.2 read-back (to build, Blender headless) | a synthetic 5-bone chain in `blender` convention exported with each axis pair, re-imported with `automatic_bone_orientation=False` | the passing pair's frames equal the source to 0.01 deg | primary Y on the same chain: frames off by 90 deg while heads match |
| G21.3 scale (to build) | the chain exported with default scaling and with FBX_SCALE_NONE + apply_unit_scale | the second reads scale 1 | the first reads 100 |

## F. Implementation gap

- Lampway (`4e9001c7`): `skeleton_check` compares names, parents, root, leaf bones, unit ratio, posed rest — not frames or
  per-bone scale (`export_checks.py:52-113`); `engine_check` records a receipt; there is no rig export tool that writes the
  measured recipe and gates it.

## G. Agent-facing tool contract — `lampway_rig_export_ue` (spec: `rig_tools/rig_export_ue.md`)

```json
{"armature": "object", "meshes": ["objects"], "actions": ["names"] , "reference": "reference FBX | fit_body package",
 "recipe": "titan_cm_native|<recipe.json>", "out": "export/<name>.fbx", "readback": true}
```
Refusals: `mixed` convention; root/hierarchy differing from the reference; leaf bones; a vertex group naming a bone the
reference lacks; any read-back row over tolerance (rows listed). Receipt: `{recipe, convention, readback: {bones_compared,
worst_position_cm, worst_rotation_deg, worst_scale, over_tolerance}, sha256: {fbx, reference}}`.

## H. Decisions owed by the captain

1. Whether Lampway exports with GRT/MB's `root`-object convention for third-party (non-MetaHuman) targets at all, or only the
   native body's hierarchy.
