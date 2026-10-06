<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: `lampway_normalize_rigged` (kinds `skeleton` and `rigged_mesh`)

Status: **new; the ingress face of canon `rig_inspect` (R1) and `rig_normalize` (R3)**, which it calls. Priority P0 for the
fit chain. Placeholders as in `../AUDIT.md`.

## 1. Name and one-line purpose
`lampway_normalize_rigged` / api.tool `normalize_rigged`: an armature (with or without its skinned meshes) into a canonical
`skeleton` and, per mesh, a canonical `rigged_mesh`.

## 2. Source
- Canon 01 C.1 ("A Blender-imported UE bone's head->tail is NOT its direction ... head -> the head of its continuation child"), C.5 (authored non-uniform scale refused), C.6 (full roster).
- Canon 17 B.1 (detect the convention; `mixed` refused), INV-17.3/17.5; canon 18 B.1 (unit factor from measurement within 5 %), INV-18.2.
- Memory gltf-bone-tail-is-not-direction; memory native-body-canonical-for-fit (the native body is canonical; a GLB copy is degraded to 4 influences).
- AUDIT ranks 5 and 9: tail-as-direction in `weights.plan`, `fit_bind`, `rig._proximity_weights`; retarget drops scale.

## 3. User story
Runs when a body, a rig or a rigged piece arrives (Vault placement, `fit_body build`, `animation_retarget`'s source import).
The fit tools then read `along` from the stamp instead of a tail.

## 4. Inputs
```json
{"armature": "object name | project path (fbx, glb, blend, bvh)", "meshes": ["object names | null = every mesh skinned to it"],
 "reference": "metahuman_fullbody | ue5_manny | mixamo | <fit_body package dir> | <reference FBX>",
 "map": "project path of a reviewed naming map | auto", "rest_pose": "rest (default) | <pose name>",
 "convention": "blender | ue_axes | detect (default detect; a mixed armature needs an explicit target: canon 17 G)",
 "unit": "auto | m | cm | in (default auto: canon 18 B.1)", "dry_run": "true (default) | false"}
```

## 5. Outputs
`{ok, skeleton: {asset_id, document}, rigged: [{object, document}], receipt}`; stamps on the armature and each mesh. The
skeleton document's `bones[].along` and `frame` are computed per canon 17 B.2-B.4 from joints and the reference.

## 6. Engine (proven code)
Canon `rig_tools/rig_inspect.md` and `rig_normalize.md` (R1, R3), `chain_ends` and `finger_axis` ported from Titan
`tools/proc_body.py:84-133` into `canon_geom` (canon plan item 1); naming via `LT/pipeline/anim_labels.py` (`label`) and the
canon R2 family tables; unit factor and apply-scale per canon 18 B.1-B.3.

## 7. Model slot
None.

## 8. Preconditions and refusals
Canon 17 G and 18 G's refusals verbatim (mixed convention without a target; undefined along-axis; unit ratio outside 5 % of a
known factor, printed; non-uniform scale on an animated armature, bones listed; negative scale). Plus: a roster incomplete
against the requested reference -> the missing bones; a mesh whose vertex groups name bones the armature lacks -> the names.

## 9. Side effects and safety
`dry_run` (default) changes nothing and returns the receipt; a real run applies scale and writes rest frames on a COPY
(`<armature>_canon`), never the captain's own rig in place (canon 18 INV-18.4).

## 10. Tests (RED first)
1. RED `test_plan_reads_the_tail_today`: on canon golden R02's three-bone arm imported through glTF, `weights.plan` assigns the forearm's vertices by the tail segment (the bug, AUDIT T5). After: `plan` reads `along` from the stamp and the falsifier fails.
2. Canon goldens R01-R03 through this tool (classification, frames, apply-scale).
3. `test_retarget_refuses_unnormalized_scale`: a source armature at object scale (2, 1, 3) is refused by `animation_retarget`'s door (today `animation.py:212-213` normalizes it away silently).
4. `test_roster_incomplete_refused`: `SKM_Manny_Simple`-sized roster against `metahuman_fullbody` lists the 72 missing profile bones (canon 01 C.6's count, synthetic stand-in).

## 11. Acceptance evidence
The native body package (`fit_body build`) carries a canonical skeleton document whose 342 bones' `along` match Titan
`proc_body.chain_ends` within 1e-6; the receipt names the convention detected.

## 12. Dependencies and order
`canon_asset`, `canon_door`, `canon_geom` (canon item 1), canon R1/R3. Before the fit-chain doors.

## 13. Open questions
Canon 17 H.2 (the convention inside Blender: `blender` recommended); canon 17 H.1 (finger up-axis table source). Not decided here.
