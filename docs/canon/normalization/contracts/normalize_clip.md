<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: `lampway_normalize_clip` (kind `animation_clip`)

Status: **new; the working-frame face of canon `rig_convert` (R4, O36)**. Priority P1.

## 1. Name and one-line purpose
`lampway_normalize_clip` / api.tool `normalize_clip`: an action, an animation file, or a multiview `fit.json` into a canonical
`animation_clip` bound to a canonical skeleton.

## 2. Source
- Canon 22 B.4-B.7 (reference-relative quaternions, Hamilton xyzw, sign rule, rational time plus terminal, uniform scale only), INV-22.1-22.5.
- Canon REPORT contradiction 8: "`anim_mv`'s "Y forward" vs the body frame's -Y front: the body frame."
- AUDIT rank 8: `LT/pipeline/anim_mv.py:9`, :48-59 (Y forward); `anim_io.py:137-163` (take quats with no frame or rest).

## 3. User story
Runs on every motion that enters: an imported FBX/BVH clip, a retarget result, an external tool's clip for `motion_experiment`,
the multiview tracker's output before `anim_check` and `anim_loop_export`.

## 4. Inputs
```json
{"input": "action name | project path (fbx, bvh, glb, fit.json, take.json)", "skeleton": "canonical skeleton asset id or armature name",
 "source_frame": "detect | multiview_y_forward | lampway_body (fit.json is multiview_y_forward by its writer)",
 "time_rule": "rational_fps_plus_terminal | source_keys", "fps": {"num": 30, "den": 1}, "root_bone": "pelvis | root", "dry_run": true}
```

## 5. Outputs
`{ok, asset_id, document, receipt}`; the Blender action stamped `lw_canon`; a JSON clip (canon 22 B.7 encoding) in the Vault.

## 6. Engine (proven code)
Titan `tools/animation_canon.py` `normalize` / `adapt` / `sample_times` (canon 22 B; port on the captain's word, canon 22 H.1),
evaluated in the working frame. The multiview frame is a REFLECTION of the body frame: `triangulate` takes X from the front
panel's u (world +X, the character's left) and Y as `side_origin_u - side_u` through a side camera whose image right is world +Y
(`anim_mv.py:54-55`, `anim_ref.py:12-13`), so Y_multiview = -Y_world. Positions map by `diag(1, -1, 1)` (det -1, recorded with
`winding_reversed` irrelevant for joints); rotations are derived from the mapped positions, never mapped as quaternions
[read from the code; test 2 measures it].

## 7. Model slot
None.

## 8. Preconditions and refusals
Canon 22 G's refusals (incomplete profile, non-uniform scale, schedule, bone set). A clip whose skeleton is not canonical ->
"normalize the skeleton first (lampway_normalize_rigged)".

## 9. Side effects and safety
New action or file; the source never edited; no overwrite (canon 22: publication never overwrites).

## 10. Tests (RED first)
1. Canon 22 goldens G22.1-G22.4 (to port from Titan's suite).
2. RED `test_multiview_forward_is_minus_y`: a synthetic walk moving toward -Y in the body frame, rendered through the recorded cameras, tracked by `anim_multiview_fit`, comes back moving +Y today (AUDIT I22); after normalization the root travel is -Y.
3. `test_loop_export_refuses_raw_take`: `anim_loop_export` behind its door refuses a take without a canonical document.

## 11. Acceptance evidence
One multiview take normalized and replayed on the canonical MetaHuman skeleton in a Workbench capture facing the front camera.

## 12. Dependencies and order
`normalize_rigged`, canon R4.

## 13. Open questions
Canon 22 H.1 (port Titan's modules or call them externally).
