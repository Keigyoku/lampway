# Algorithm canon: report (2026-10-05; MetaTailor goldens added 2026-10-06)

The auditor's harness refused this file, so the coordinator wrote it from the auditor's returned text. The page list and
statuses are in `INDEX.md`; the build order is in `IMPLEMENTATION_PLAN.md` (§3a is the rig track).

## Goldens
- **C01-C14:** 35 checks pass.
- **R01-R07:** 22 checks pass.
- Both generators reproduce byte-identical output.

## Rig tools (MBTools, GameRigTools)
- **Licences:**
  - GRT core 4.3.0 and its Unreal module 4.2.0: the LICENSE file is the GPL v3 text, while the manifest says
    GPL-2.0-or-later. That contradiction is internal to the add-on; either reading is compatible with Lampway.
  - MB UE5 Rig Creator Pro 3.1.0: only `__init__.py` carries a header, "GPL version 3 or any later version". There is no
    LICENSE file and no copyright line.
  - Attribution text: `rig_tools/README.md`.
- **GRT defects, run to confirm** (headless Blender 5.2.1, synthetic rigs):
  - With default settings, the game-rig generator puts only the last of 5 deform bones in the "Deform" collection.
  - "Flat Hierarchy" never flattens, and it sets a property that no longer exists.
  - Unlock Bones Transform swaps the Rotation and Scale flags.
  - Apply Armature Scale moves a bone 0.2236 m under non-uniform scale (golden R03).
  - With its post-generation toggle on, GRT executes a scene datablock's text with `exec`. NEVER port that.
- **MB defects, read on the source:**
  - Wrong-side re-parenting guards.
  - A finger list with a duplicate and a missing bone, and a thumb bone tracking itself.
  - Absolute mannequin heights written into the joints.
  - APIs removed in Blender 5.2 (`Action.fcurves`, armature layers).
  - Destructive side effects: it joins skinned meshes, renames UV layers, deletes actions, and its batch export deletes
    the scene.
- **11 rewrite specs** under `rig_tools/`: inspect, map, normalize, conform, export, convert, fit-to-example, game-rig
  extract, bake, retarget, rest pose.
- **O36's first slice:** inspect, map, normalize, convert, and the export read-back.
- **Prior art:** Titan's `tools/rig-axi.py` already drives GRT as an agent tool. Its 2026-09-28 failure came from taking
  the target joints from the MetaHuman. The fit spec now refuses a joints file whose mesh hash does not match the example.

## Findings, most serious first
1. Titan's return to rest uses a blend of inverses where the inverse of the blend is needed: 10.8 mm off on 46 vertices.
   The rest-pose change has the same error: 12.5 mm.
2. Lampway's weight transfer:
   - does not weld first;
   - has no region constraint;
   - leaves zero-weight rows after restricting.
3. Fit validation's expectation is circular, and it uses world-axis Euler poses.
4. Penetration is signed by the nearest face's normal, which gives the wrong side at sharp points.
5. The skeleton export check ignores bone frames and per-bone scale. It would pass the 28.8 cm frame error.
6. Placement centres on all vertices instead of the inner wall: a 12.5 mm bias.
7. Several tools read bone direction from the imported tail.
8. Smaller defects:
   - Bake: the ray is 0.5x the cage; it should be 2x.
   - UV raster: it counts overlaps that do not exist.
   - Retopo: deviation is measured one-sided.
9. Pose controls:
   - The crossing control has no cap.
   - Pose clearance uses absolute heights.
10. GRT apply-scale and MB auto-scale are wrong outside uniform scale.
11. MB's copy-paste guard defects (above).
12. GRT's `exec` of scene text.

## Contradictions, with the winner
1. "Rig the example; pieces ride its weights" (09-29) vs the native body as the canonical fit body (09-30).
   **Recommended:** the native body for bind, weights and validation; the example supplies the pose and the armour-to-body
   relationship. **DECISION OWED.**
2. Metal wrapped at fit time vs "pose, not push" and "metal never blended": the later rulings win, so metal takes one
   rigid transform.
3. Titan's return formula vs the exact inverse: the exact inverse.
4. Validation limits, Lampway 1 mm vs Titan's proposed 0.5 mm with 1 % strain: Titan's proposal. **The captain decides.**
5. Seam limit, 1 cm vs the 2 mm ledger threshold: 2 mm.
6. Bake ray, 2x the cage vs 0.5x: 2x (black texels 64.5 % → 9.5 %).
7. Enclosure by all vertices vs the inner wall: the inner wall (golden C06).
8. `anim_mv`'s "Y forward" vs the body frame's -Y front: the body frame.
9. The `piece_ratios` cuff end: **owed** a measurement.
10. Chest clearance, +40 mm vs 30 mm: **owed**.
11. "Never Cycles" vs the bake worker: bake only headless and niced, never while the captain works live, or offload it.
12. Two UV island definitions and two rasters: one definition, with a half-open raster.
13. Welding: only for generated-armour adjacency, never for authored rigs.
14. Silhouette comparison: at the true aspect, never cropped and stretched.
15. Openings: before texture.
16. Bone axes inside Blender: Blender-native per armature (Titan's export recipe passes 342 of 342 bones). A mixed
    armature is refused.
17. Hierarchy: the reference skeleton's hierarchy, not GRT/MB's "root" object without a root bone.
18. The Lampway working frame (right-handed, metres) vs ADR 0012's interchange frame (UE-style, cm): both, at different
    layers, mapped by an adapter. **The captain confirms.**
19. GRT's licence statement contradicts itself; compatible either way.

## MetaTailor goldens MT-1..MT-4 (run 2026-10-06)
- **Exports:** 1 used for all four cases (one "Export Full Model" FBX). This month: **3 of 5 used, 2 remaining**; MT-5 is in
  reserve with one spare. MetaTailor's UI shows no counter; the count comes from its log (`Found 2 recent exports` before
  this one).
- **Method:** synthetic inputs, black box, measured by UV-grid correspondence.
  - The generator and analyser in `goldens/metatailor/` reproduce the inputs and `results.json` byte-identical.
  - The binaries are kept in scratch, with their hashes recorded.
  - The FBX must be imported at `global_scale` 100: at the default it reads 0.01x. At 100 the frame matches the native
    joints within 0.014 mm.
- **MT-1, rigid-cap glove** (Gloves, 21 keypoints): the warp is non-rigid.
  - Whole-piece residual 18.1 mm RMS.
  - Caps scale 0.94–1.71, 0.44–5.32 mm RMS; distal segments stretched up to 1.83x.
  - The 4.0 mm cap gap closed to 0.03 mm.
  - 46 vertices ended up inside the hand (min -23.1 mm).
  - Up to 29 influences on 94 bones.
  - In a fist: strain p95 32 %, 93 vertices inside.
- **MT-2, shoulder plate:**
  - **Accessory:** defaulted to `hand_r` and moved off the shoulder; "Parent to Closest" kept `hand_r`. Not exported.
  - **Shirts (exported):** geometry unchanged; 10 bones (upperarm_out 0.46, clavicle 0.25); bends 22 % (p95) at a 60° arm
    lift.
- **MT-3, 16-strip skirt** (Skirts):
  - Geometry unchanged.
  - Thigh share 0.63 at the strip tops, 1.0 by z 0.68.
  - In a 60° hip flexion the strips stretch 36 % (p95); the front and back strips deform non-rigidly by 18–22 mm.
  - Strip gaps stay open.
- **MT-4, lidded greave** (Pants):
  - No opening detected. The lid apex was pushed from -41 mm to +6 mm, and the lid was kept as a skewed cone.
  - The tube stays rigid through a 90° knee bend (0.18 mm).
- **What the canon takes from it:** the contrasts GMT.1–GMT.8 (`goldens/metatailor` §6), cited from canons 03, 05, 06, 07,
  09 and 15.
- **Still open:** "Keep Source Dimensions" off (the rescale). Every case kept the source scale. This is a candidate for MT-5.

## Decisions owed
**Fit and pieces:**
- Contradiction 1 (the example's weights).
- The soft-part deformer.
- Glove girth.
- The boots anchor.
- A shared scale for a pair.
- Clearance per material kind.
- The metal, non-metal and seam limits.
- Collar depth.
- Pose ranges for 4 piece kinds.
- The pose-cost threshold.
- The influence cap.
- The per-type weight profiles.
- The joint detector.
- Glove keypoints.

**Mesh and texture:**
- Retopo budgets.
- UV gates.
- Whether to bake at all, and on GPU.
- Clearance targets.
- Who checks `piece_ratios`.

**Rig tools:**
- Which naming families ship first.
- Whether fingers are required.
- Where the finger axis table comes from.
- The convention inside Blender.
- Squash/stretch.
- Root yaw.
- Hidden joints under armour.
- Port Titan's `animation_canon`, `canon`, `skin_bind` and `rig-axi`, or call them externally.
- Shipping skin/morph before Titan Task 131 closes.

## Limits
- Alpaca3D was not installed or run.
- The code graph did not index these trees, so every file:line comes from reading the file.
- Lampway's HEAD moved from `b806617f` to `4e9001c7` during the work; canons 16-22 cite `4e9001c7`.

## The captain's rulings (2026-10-06)
- **Contradiction 1:** the native body is canonical for bind, weights and validation. The fitted example with its
  generated motion is one fitted example of a set (pose and relationship only).
- **Contradiction 4:** Titan's limits, 0.5 mm and 1 % strain.
- **Chest clearance:** owed ("not sure"); a `needs_decision` pref at the default.
- **MetaTailor MT-1..MT-4:** approved, when exports allow. **Done 2026-10-06** (one export; 2 remain).
