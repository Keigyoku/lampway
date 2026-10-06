<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 11 — Joints from views: 2D keypoints on orthographic renders, triangulated, calibrated, centred

Status: **CANONICAL maths (triangulation, calibration, robust drop); DRAFT pipeline** (the 2D detector is a model slot not built
in Lampway; the static rig-from-views tool does not exist there). Implemented by: Titan `tools/views_joints.py` (pure),
`recipes/pose2d.py`, `recipes/hand2d.py`, `hand_pose.py:284 finger_joints`; shelf grt `rig_axi/centre.py`; LT
`pipeline/anim_mv.py` (the video variant: front + side split screen).

## A. Problem

Rig the fitted example (and any humanoid piece set) from ITS OWN geometry (canon 03 INV-03.7): find each UE joint inside the
example. Meshy normalises the character and asks for 13 markers on one front view; MetaTailor auto-maps 24 avatar landmarks and
makes a PERSON click 21 glove keypoints (memory metatailor-study). Ours is automatic and multi-view (memory multiview-2d-joints,
2026-09-29). Inputs: the mesh; orthographic cameras `{res, ortho, center, right, up, look}` (pixels right and DOWN); per-view 2D
keypoints with confidences. Output: per-joint 3D positions (body frame), the views used, residuals, the calibration applied.

## B. Method

1. **Normalise and render.** Centre, face front, height; render orthographic front / back / left / right at 1024 px (textured;
   zoomed views for hands). Each side uses its own side view.
2. **2D keypoints.** RTMW whole-body (COCO-WholeBody's 133 keypoints: body 17, feet 6, face 68, hands 21 + 21; Jin et al. 2020,
   "Whole-Body Human Pose Estimation in the Wild", ECCV; RTMPose/RTMW, Jiang et al. 2023) via rtmlib (Apache-2.0, ONNX, CPU).
   On armour the hand model needs the hand's box (its own detector finds none); the WRIST keypoint reads the cuff — never use it as
   a joint on a gauntlet (Titan `hand_pose.py:7-9`).
3. **Map keypoints to UE joints** (`views_joints.py:20-27 KEYPOINT_OF`: shoulders->upperarm, elbows->lowerarm, wrists->hand,
   hips->thigh, knees->calf, ankles->foot; hand 21 -> thumb/index/middle/ring/pinky 01..03).
4. **Triangulate** (`views_joints.py:46`): each view fixes the point's offsets along its camera's `right` and `up`; weighted least
   squares over views; exact for orthographic cameras. One view, or views all looking one way, leave depth unfixed: REFUSE.
5. **Robust drop** (`views_joints.py:135`): drop the view whose reprojection misses most while the miss exceeds `max_px` and the
   rest still fix the point (a finger read as its neighbour is not averaged in).
6. **Calibrate** (`views_joints.py:77`): run steps 1–5 on the MetaHuman (known joints) with the SAME cameras; per joint the offset
   true - triangulated; apply it to the example. Keypoint-to-joint offsets are a property of the detector, not of the example.
7. **Hidden joints:** keypoints read off a skirt or cloak are not joints (`merge(..., hidden)`).
8. **Centre in the limb cross-section** (grt `rig_axi/centre.py`): in the plane across the bone at the joint, 16 rays out to the
   example's surface (reach 5 cm fingers, 8 cm hand/foot, 15 cm else); move to the hits' mean projected into the plane; 3
   iterations; skip a joint whose ring is not closed (fewer than 12 of 16 hits; 10 for fingers). **Measured 2026-10-06:** the
   hits' mean HALVES an offset per pass on a circular section, so three passes leave 1/8 of it (10 mm -> 1.25 mm); the first-harmonic
   fit of canon 09 B.4 (`canon_geom.harmonic_centre`) is exact on a circle in one pass - which rule centring keeps is H.3.
9. **Video variant** (LT `anim_mv.py`): one split-screen clip, front (x, height) + side (forward, height); height shared
   (confidence-weighted); LEFT/RIGHT legs and arms identified from the FRONT view and propagated to the side by height, ties broken
   by constant-velocity prediction; single-view mode is the control that must FAIL leg identity.

## C. Invariants

- **INV-11.1** Two non-parallel views per joint, or refuse.
- **INV-11.2** Calibration offsets come from the MetaHuman in identical cameras; never hand-tuned.
- **INV-11.3** The example's rig comes from the example: no joint is copied from the MetaHuman.
- **INV-11.4** Every keypoint-derived joint records its views, reprojection residuals and whether it was centred.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-29 | rig-axi joints "all slightly off" (elbow, wrist & fingers, hips, knees, ankles & toes) | multi-view keypoints, calibrated | memory multiview-2d-joints |
| 2026-09-29 | The rig's finger joints came from the whole-body model and sat 0.3–2.6 cm off the hand model's | fingers from the hand model | GENERATED-EQUIPMENT §7m (3) |
| 2026-09-29 | A measurement that never solved hands and feet swung them out of gloves and boots (17 of 55 joints outside) | hands and feet are solved, then centred | §7m |
| 2026-09-28 | Single-view video tracking: legs right 80 % (SAM 3D Body); silhouette fit alone swaps legs | the second view supplies depth and identity | memory animation-from-video, multiview-video-motion |
| 2026-09-29 | YOLO missed the armoured figure | use our masks/boxes | memory animation-from-video |

## E. Golden tests (`goldens/C08_multiview`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G11.1 exact | 15 joints, 4 orthographic cameras | every joint within 1e-9 m | a perspective model applied to orthographic views |
| G11.2 one view | front only | REFUSED (depth unfixed) | a solver that returns y = camera centre |
| G11.3 outlier | lowerarm_l in the left view +40 px | robust: 3 views used, exact; plain least squares off by 43 mm | — |
| G11.3 note (2026-10-06, measured) | the same 40 px in the RIGHT view | the case is NOT identifiable: left and right are the only views fixing y, so they disagree symmetrically; the reference drops the corrupt view only by a floating-point tie (the right-view error leaves the joint 85.9 mm off with "3 views used", and re-projected points flip the choice). Lampway's tool refuses an ambiguous outlier and names both views; an identifiable one (the left view's HEIGHT, fixed by four views) is dropped exactly | a robust rule that picks either view of a tie |
| G11.4 calibration (built in Lampway, `test_canon_item12_joints.py`) | the same cameras on a body with known joints and a constant per-joint keypoint offset (the same pixels in every view, within `max_px` across views) | offsets recovered exactly; applied to a second body the joints are exact | offsets from a different camera framing (refused) |
| G11.5 leg identity (video) | LT `test_wave4_multiview.py` synthetic two-view walk | identity 100 %, bone directions within 5 deg (1.9 deg measured); single view fails | — |

## F. Implementation gap

1. Lampway has no static "joints from views" tool; `anim_mv.py` covers only the two-panel video case.
2. The RTMW detector is not built in Lampway (`anim_multiview_fit stage=detect` answers needs_approval; `<specs>/STATUS.md`).
3. **Axis naming disagrees:** `anim_mv.py:5-11` uses "Y forward" while the body frame's front is -Y (canon 01). A shared adapter
   must convert, not assume.
4. Joint centring (`centre.py`) lives only in a scratch directory.

## G. Agent-facing tool contract — `lampway_joints_from_views`

```json
{"mesh": "object or file", "views": ["front", "back", "left", "right"], "res": 1024, "ortho_m": "auto (fit + margin)",
 "detector": "rtmw_wholebody|rtmpose_hand|keypoints_json", "keypoints": "path (when detector=keypoints_json)",
 "calibration": "calibration.json from the MetaHuman run (REQUIRED for a rig)", "max_px": 4.0, "centre": true,
 "hidden": ["joints under cloth"], "out": "joints.json"}
```
Refusals: fewer than two non-parallel views for a joint; no calibration for a rig run; a detector that is not installed (names
the install step; the detector is a model slot); a keypoint set from a different camera framing than its calibration.
Receipt: `{joints: {name: {pos_m, views_used, residual_px, centred_cm, calibrated: true}}, cameras, detector, calibration_sha256}`.

## H. Decisions owed by the captain

1. May the rtmlib RTMW ONNX detector (CPU, ~small) run locally under the hardware law, or must it go to a subscription?
2. Hand keypoints on a GLOVE: from the body's exact joints (deterministic) or from the hand model on the glove's own renders
   (the piece's implied hand)? He judged RTMPose hand keypoints on the armoured gloves "really good, maybe millimeters off"
   (memory spike-helper-armour-tooling).
3. Joint centring: the hits' mean (B.8 as written, 1/8 of an offset left after three passes) or the first-harmonic centre (exact on a
   circle; canon 09 B.4 already uses it for placement).
4. G11.3's ambiguous outlier: refuse it (Lampway's tool, naming both views) or keep the reference's tie-break (the same error in the
   other view then goes undetected, 85.9 mm off).
