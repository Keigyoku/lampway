<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 21 — Engine export (Unreal): the skeleton the engine reads, and the read-back that proves it

Status: **CANONICAL** gate and the measured Titan recipe; **DRAFT** for any engine other than Unreal 5.8. Implemented by: Lampway
LT `features/export_checks.py` (`skeleton_export_check`, `engine_import_check`), LT `features/fit_export.py` and `ue/export.py` (rigged export behind
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
   **Which axis pair is a property of the rig's Blender-side convention, not of the engine (golden R08, 2026-10-06).** The FBX
   writer turns each bone into a node frame `N = R_bone @ M(primary, secondary)` (the node's primary axis is the bone's +Y, its
   secondary the bone's +X); a pair carries a convention exactly when `M` equals that convention's engine frame (canon 17 B.2:
   `ue_axes` bones are the engine frames; a `blender` bone's engine frame is `R_bone @ T`, X <- Y, Y <- -X, Z <- Z). Solved: the
   `blender` convention needs **primary X / secondary -Y**, `ue_axes` needs **primary Y / secondary X**. Primary Z / secondary X
   carries neither: it is 120 deg off a `blender` rig and 90 deg off a `ue_axes` rig (exactly lane orphans' read-back measurement,
   2026-10-06), and it is the pair a rig needs that entered Blender from an engine FBX imported with Z / X - a ROUND TRIP, which is
   how Titan's MetaHuman body was measured. Blender's real FBX writer was driven through all three pairs and wrote `R_bone @ M`
   for every bone (Lampway `tests/lampway_tools/test_canon_r08_export_axes.py`; the transposed map is 180 deg off, so the direction
   is pinned). The explicit recipe `titan_cm_native` (Z / X) is refused by the read-back on canon-17 rigs. Issue2's default-chain requirement supersedes leaving it as the default: `auto` selects X/-Y for measured normalized `blender` frames and Y/X for `ue_axes`, records the choice and keeps every readback bar. Physical engine confirmation is still required (ue_parity MEASUREMENT_PLAN `M-RIG-01`: the R08 recipes on the
   native body in Unreal 5.8). Use the convention's own recipe and let the read-back decide.
   **Unit-carrier correction measured 2026-10-07:** the old metre-coordinate `FBX_SCALE_NONE` recipe writes a Null ancestor scale100 while UnitScaleFactor1 and direct bone scales pass. Actual legacy UE5.8 imports retain this factor in342 component scales; the native-self control passes. The convention recipes now explicitly make centimetre export copies and cancel only the pinned writer scene-unit factor, preserving dimensions, weights, frames and original data. Raw Null ancestry and direct bone scales are checked before publication. Blender's known uniform importer unit carrier is decoded without modifying rest/mesh data or changing the bars; physical native Unreal parity is still required. This corrects the earlier G21.3 assumption that direct LimbNode scale and UnitScaleFactor alone identify engine scale.
3. **Hierarchy and root follow the reference.** The native MetaHuman has a real `root` bone. The earlier accepted extra-container
   description does not match the actual342-bone reference: the candidate's343rd container changes `root`'s parent and refuses.
   Installed UE5.8.2 source verifies that Blender-created top-level Null `Armature` is skipped (case-insensitive name); the
   actual differently named candidate does not meet that predicate. The two convention recipes declare
   `ue_armature_container="Armature"` and name only the disposable export copy accordingly. An existing object occupying
   that exact name or an unverified requested name refuses before copies; originals are never renamed. GRT and MB
   instead name the ARMATURE OBJECT `root` and have no `root` bone (GRT's Unreal armature: 88 bones, none named `root`, measured;
   MB `CreateRig.py:12536-12538`). The two are different skeletons to the engine: the root check (LT `export_checks.py:93-106`)
   refuses the mismatch; never mix them.
4. **Deform bones only, no leaf bones, no helpers the reference lacks.** `use_armature_deform_only`, `add_leaf_bones` off (MB
   `PoseUE.py:4189-4205` sets both; LT `skeleton_check` reports leaves). IK helper bones (`ik_*`, `center_of_mass`,
   `interaction`) are exported only if the reference has them (canon 16 B.6).
5. **Frames in one convention** (canon 17 B.1): a `mixed` armature is refused before writing. The convention inside Blender and
   the axis settings form a PAIR; the read-back proves the pair.
6. **Animation:** baked keys only (canon 19), no constraints, one action per clip, frame range recorded; root motion per canon 19. UE animation uses the same measured axes and disposable centimetre/action copies. Resolve the requested action slot against the original armature before copying, including a non-active requested action; ambiguous slots refuse. Check raw units, identity Armature container, full topology and exact pinned-writer key cadence. Preserve source action/slot, pose, frame and all datablocks. A skeleton-only clip lacks independent skin cluster binds and cannot claim authored skin-bind acceptance or native UE animation parity.
7. **Meshes:** one skinned mesh per piece, vertex groups naming only bones the reference has (LT `fit_export.py` gates it),
   normals preserved and compared corner by corner on read-back (Titan tools rail, wave4-tools-9: canonical corner shading and
   actual FBX normal preservation). MB exports with `mesh_smooth_type='EDGE'` and no normal check (`PoseUE.py:4195`).
8. **The engine import is a receipt, not an assumption.** The import settings (Interchange) are recorded; Titan changed none
   (memory native-body-canonical-for-fit). LT `engine_import_check` records a hand-run import's receipt (`export_checks.py:127-172`).

   **Authored-file readback (2026-10-08):** the actual eight source bones are10–15cm
   and copy rotation passes; the earlier synthetic source-short-bone mechanism
   does not explain their imported readback refusal. A long-source/coincident-child
   synthetic control reproduces tiny inferred display tails and RNA frame drift
   while authored node/BindPose/cluster rotations pass. For admitted centimetre
   exports, the restricted pinned-writer reader verifies all three redundant
   authored binds and hierarchy under unchanged shortest-quaternion bars. It
   refuses unsupported transforms, axes/units, missing clusters and contradictions,
   preserving imported display errors as explicit diagnostics. Source and imported
   rest data remain untouched. Matching the actual eight file/import rows and
   native mesh-versus-Skeleton calibration remain owner-local measurements;
   authored-file verification does not establish native engine parity.

## C. Invariants

- **INV-21.1** No export without a read-back that compares every bone's position, rotation and scale to the reference.
- **INV-21.2** Root and hierarchy equal the reference's. A container is not an accepted extra for the verified342-bone native reference.
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
| G21.2 read-back (to build, Blender headless) | a synthetic 5-bone chain in `blender` convention exported with each axis pair, re-imported with `automatic_bone_orientation=False` | the passing pair's frames equal the source to 0.01 deg - **unreachable for arbitrary frames inside Blender (measured 2026-10-06): an edit bone set to an arbitrary frame reads back up to 0.112 deg off (67 of 400 random frames over 0.01 deg), with no FBX involved; the gate's 0.01 deg is a decision owed (H.3)** | primary Y on the same chain: frames off by 90 deg while heads match |
| G21.4 axis pair (R08) | the three pairs Z/X, X/-Y, Y/X against both canon-17 engine frames | X/-Y carries `blender` (0 deg), Y/X carries `ue_axes` (0 deg); Z/X is 120 / 90 deg off | the transposed map (180 deg off the right pair) |
| G21.3 scale | real writer metre-coordinate legacy recipe versus independent centimetre copies | corrected raw Null1/UnitScaleFactor1; decoded readback retains dimensions and all existing bars | old default returns Blender PASS while raw Null100; scene-only unit changes shrink geometry; importer object-scale application violates the existing drift guard |

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
2. The default export recipe once `M-RIG-01` has run in Unreal: the canon-17 convention's own pair (R08: X / -Y for `blender`,
   Y / X for `ue_axes`) or Titan's Z / X for rigs that entered Blender from an engine FBX. Issue2 supersedes the former refused-default policy: `auto` selects from measured normalized frames now, retains explicit Titan and unchanged readback bars, and records physical `M-RIG-01` acceptance as pending.
3. The read-back's rotation tolerance inside Blender: 0.01 deg (Titan's `bind_mismatch`, measured in UNREAL) is below what a
   Blender edit bone holds for an arbitrary frame (max 0.112 deg, 17 % of 400 random frames over 0.01 deg, 2026-10-06, no FBX
   involved); the cause is not identified (the errors are not clustered at the roll singularity, the bone's Y near -Z). A Blender
   read-back may need a measured bar of its own, or a comparison against frames that went through the same storage. No tolerance change was ruled: the implemented authored node/pose/cluster readback keeps0.01deg, reports imported display errors separately and refuses unsupported layouts.

## Shared public-route contract correction

The fit-chain `fit_export` and UE `skinned_piece` routes use the same measured-convention recipes, disposable centimetre copies and reserved Armature container as rig export. They validate raw unit/ancestry scales before the strict authored node/BindPose/cluster and full-hierarchy gate. The existing diagnostic imported-axis check is retained in addition to the unchanged canon bind bars. Wrong position, quaternion, scale, missing reference rows and hierarchy mutations refuse. Passing these file/Blender checks does not assert native Unreal or original-gear acceptance.
