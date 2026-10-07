<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 08 — Pose the body to the piece (the closest pose)

Status: **CANONICAL for the chest** (measured, regression-pinned numbers); **ACCEPTED TABLE for helmet** (captain issue-2 instruction); **DRAFT for waist, boots and gauntlets** (their
degrees of freedom and ranges are the captain's to rule; BUILD_ORDER decision 1). Implemented by: shelf
`proportion/pose_clearance.py` (ported byte-for-byte to LT `scripts/proportion/pose_clearance.py`, routed by LT `posing.py`);
Titan `tools/equipment_fitpose.py` (`swing`, `pose_chain`, `fit_chain`), Titan `armour_validate.py` (`pose_cs`, `resolve_axis`,
`expand_pose`, `check_expect`), Titan `proc_body.py` (`finger_axis`, `curl_delta`).

## A. Problem

A generated piece carries its own implied pose (sleeves hang at some angle, the torso arches). Measured on the MetaHuman's A-pose
(arms ~40 deg down), that difference reads as clipping, and "fixing" it damages a good piece (memory pose-body-to-the-piece,
2026-10-04). Find the body pose closest to the piece BEFORE clearance, openings, fit, skinning or weighting; report both numbers.
Inputs: the placed piece (canon 09, body frame) with its placement meta; the native body package (skinned by its own skeleton);
the kind's DOF table. Output: `pose.json` — entries in the joint-named axis grammar, replayable by validation and the UE leg —
with A-pose and posed penetration, pose cost, and the residual blocking surfaces mapped back into the piece's own frame.

## B. Method

1. **Sign check first.** Rotate the first DOF by +20 deg and require the expected joint to move the expected way (shelf: elbow_l z
   must drop by > 2 cm; `pose_clearance.py:63-65`). A failing check REFUSES the run ("the sweep would be meaningless").
2. **Rotate about axes named from the body's joints** through the bone's head (`armour-poses.json` grammar: `up`, `forward`
   = foot_l->ball_l levelled, `lateral`, `{line:[a,b]}`, `{perp:[a,b],to:axis}`), composed in pose space, children carried
   (`pose_cs`, Titan `armour_validate.py:384`). Never Euler angles on the bone's local axes.
3. **Penetration metric** per body region: for each sampled skin vertex, cast from its posed bone's axis (the projection of the
   vertex onto the bone line) outward to the vertex; the first armour hit BEFORE the vertex gives depth = |vertex - origin| - hit
   (`pose_clearance.py:80-92`). Count depths > 10 mm (arms) and the fraction > 2 mm (torso, neck). Body regions are selected from
   the body's own joints (bone segment + radius), never absolute heights.
4. **Search** (deterministic): a grid over the first-order DOFs (chest: arms lowered 0..40 step 5 x swung -10..10 step 5), then
   each chain link in turn (hips `spine_01`, chest `spine_03`, neck `neck_01`, pitch -8..+8 step 4) holding the earlier links'
   best (coordinate descent, `pose_clearance.py:134-145`). Selection: fewest penetrations over the threshold, then smallest worst
   depth, then smallest |angle| (prefer the natural pose).
5. **Hands** (gauntlets): wrist ±30, then each finger joint curled TO an angle (80/95/60 deg for 01/02/03 at fraction 1) about the
   knuckle line (`proc_body.py:124 finger_axis`, `:112 curl_delta`), thumb included; fractions 0, 1/3, 1/2, 2/3, 1.
6. **Report** A-pose and posed numbers, `pose_cost_deg = Σ|deg|`, and the residual blockers' bounding box in the piece's own
   frame (undo turn, scale and shift with the placement meta) — the exact box for a region regeneration.
7. **Optional limb initialiser (DRAFT):** lay each limb bone along the centreline of the armour tube round it by damped
   Gauss-Newton over swings (`equipment_fitpose.py:180 fit_chain`) — not yet measured against the sweep.

## C. Invariants

- **INV-08.1** Only clipping that survives the closest pose is a mesh defect; both numbers are reported.
- **INV-08.2** A natural fit is preferred: the selection never trades a penetration for a larger pose than needed.
- **INV-08.3** The pose is RECORDED in the replayable grammar; validation and the UE leg replay the identical pose (two engines
  agree on joint positions within 0.01 cm).
- **INV-08.4** The body is skinned by its own skeleton; poses never move the body by hand.
- **INV-08.5** A cap or bowl inside a collar is a mesh defect counted by the neck metric (canon 06), not a pose problem.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-04 | Chest audits counted A-pose arm clipping as defects; neck:chest / back:hips pitch "can vastly change the chest fit" | pose first; report both | memory pose-body-to-the-piece |
| 2026-10-04 | A first version without view-layer updates left the elbow fixed for every pose | update the evaluated pose before every read | `pose_clearance.py:50-51` comment |
| 2026-09-29 | The fist test added 70 deg per joint to a hand the example rests half-curled and never moved the thumb | curl TO an angle about the knuckle line, thumb included | GENERATED-EQUIPMENT §7m (4) |
| 2026-09-30 | Curl axis pinky->index bent the fingers back; every curl REFUSED on its expect | sign by expectation, axis index->pinky | `recipes/armour-poses.json` |
| 2026-10-07 | Captain: implement issue-2 typed stubs with canon recommended values | Helmet H.1 is a complete table: neck_01/neck_02/head pitch and roll -8..8 step4; sign probe carries head forward; retain the existing 2mm neck metric and the reversed-axis refusal | issue 2 ruling, coordinator |
| 2026-10-04 | Chest seed 9c052d49 measured: A-pose arm vertices > 10 mm: 166 (l) / 207 (r) -> 90 / 103 at lower 0, swing +10; neck fraction > 2 mm 0.2538 -> 0.0639 at neck_01 -4 deg, spine_01 -4, spine_03 0 | the regression pin of the chest sweep | `<shelf-scratch>/proportion/pose_9c052d49/pose_clearance.json` (cited in `<specs>/shelf/fit_pose_solve.md`) |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G08.1 authored arm angle | `goldens/C07_pose_solve` | best lower = 30 deg exactly; 0 penetrations > 10 mm; A-pose > 0 (37 measured by the reference) | a sweep that ranks by mean clearance picks a different angle |
| G08.2 sign check | same rig, axis negated | REFUSED before any sweep | — |
| G08.3 replay | the produced `pose.json` replayed through `pose_cs` | joint positions agree with the sweep's within 0.01 cm | Euler-on-local-axes replay on another rig |
| G08.5 curled hand | `tests/lampway_tools/test_canon_finger_targets.py`, authored20°/30° relative curl and all five digits | targets80/95/60 produce deltas60/65/60; native API fifteen entries and unchanged pose matrices; all three bounded candidate tables execute with positive sign probes | additive expansion gives80/95/60 and omits thumb |
| G08.4 chest regression | the recorded chest inputs (`pose_9c052d49`) | 166/207 -> 90/103; neck 0.2538 -> 0.0639 | — |

## F. Implementation gap

1. LT `posing.py` supplies chest and the accepted complete helmet table. `fit_pose` uses the helmet table by name or by default with scene inputs. Waist, boots and gauntlets still require the missing numerical rows; supplied DOFs run the shared engine. `pipeline/decision_tables.py` supplies complete bounded measurement candidates with an explicit caller sign expectation and positive region threshold, never canonical defaults. `curl_side` adds the B.5 coupled curl-TO sweep including thumb using shared `finger_axis`/`flex_axis` and `curl_delta`; authored existing curl is subtracted, rather than adding the target.
2. LT/shelf `pose_clearance.py:73` and `:119` select torso and neck vertices by ABSOLUTE heights (z 1.15–1.52, 1.50–1.62 m) and
   |x| bands: body-specific constants that break on any other body or placement. Canon: regions from the body's joints.
3. World axes `(0,1,0)` and `(1,0,0)` (`pose_clearance.py:111-113`) assume the body faces -Y in A-pose; the canon names axes from
   joints.
4. `pose_clearance.json` is not in the replayable `pose_cs` grammar; `fit_validate`/UE cannot replay it.
5. The body is skinned from the GLB (4 influences) in Blender, an approximation the report does not state.

## G. Agent-facing tool contract — `lampway_fit_pose`

```json
{"kind": "chest|helmet|waist|boots|gauntlets", "placed": "placed.npz (+ .json meta)", "body": "fit_body package dir",
 "dofs": [{"bone": "upperarm_l", "axis": "<joint grammar>", "range": [0, 40], "step": 5, "mirror": true}],
 "chain": [{"bone": "spine_01", "axis": "lateral", "range": [-8, 8], "step": 4}], "classes": "labels per placed triangle (optional)",
 "out_dir": "dir"}
```
Refusals: sign check fails; an `expect` fails; a range wider than 90 deg ("not 'closest': split the piece or ask"); no DOF table for
the kind and none passed (`needs_decision` with the proposal); placed meta missing (blockers cannot map back).
Receipt `pose.json` (`lampway.fit-pose/1`): `{body_sha256, placed_sha256, kind, entries: [{bone, axis, deg}], a_pose: {...}, posed:
{...}, pose_cost_deg, blocking: {side: {points, bbox_piece_frame, by_class}}, sweeps: [...]}`.

## H. Decisions owed by the captain

1. Remaining DOF ranges for waist, boots and gauntlets (helmet neck_01/neck_02/head pitch & roll -8..8 step4 accepted on 2026-10-07; waist
   spine_01/pelvis pitch -8..8 + thigh flexion/abduction; boots ankle pitch/roll + small knee; gauntlets forearm twist, wrist ±30,
   finger curl fractions).
2. Is a large required pose (pose_cost above some degrees) a REJECT signal for the seed?
