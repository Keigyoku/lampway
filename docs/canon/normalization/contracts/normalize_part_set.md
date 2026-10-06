<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: `lampway_normalize_parts` (kinds `part` and `set`)

Status: **new**. Priority P1. Placeholders as in `../AUDIT.md`.

## 1. Name and one-line purpose
`lampway_normalize_parts` / api.tool `normalize_parts`: a canonical mesh's part labels into canonical `part` documents, and a
group of canonical pieces into a canonical `set` (one frame, one body, a declared scale group).

## 2. Source
- Canon 01 D.3: "Render vertices map to source vertices by rest position, never by index."
- AUDIT T45: owner maps are keyed by polygon index across the partseg tools (`patch_holes.py:49`, `render_owner.py:28`, `apply_part_fixes.py:39`).
- Memory metal-never-blended; memory gauntlet-glove-detached (a part off its neighbour by 22 degrees went unseen until measured).
- Canon REPORT decisions owed: "A shared scale for a pair".

## 3. User story
After a part map is approved (transfer, critique, fixes), the piece's parts become documents the fit tools read by source face
id; a piece set (helmet, chest, waist, gauntlets, boots) becomes one document the fit chain and the exporters check.

## 4. Inputs
```json
{"mesh": "canonical mesh asset id or object", "owner": "project path .npy (one part per polygon) | face attribute part",
 "recipe": "project path (part names, classes, binds)",
 "set": {"members": [{"asset": "id", "role": "chest", "side": "center"}], "body": "fit_body package dir", "scale_group": "per_piece | pair_shared | set_shared"}}
```

## 5. Outputs
`{ok, parts: [document], set: document | null, receipt}`; parts stored as `part` assets `part_of` the mesh; the set as a `set` asset.

## 6. Engine (proven code)
Owner map to source ids through the mesh's `lw_source_face` attribute (normalize_mesh step 6); for a re-import that reorders
faces, the shelf's position-based remap (`transfer_parts.py:39-41` nearest-centroid, distance kept) with the distance recorded.

## 7. Model slot
None.

## 8. Preconditions and refusals
"part map length N does not match the mesh's M faces"; "a metal part with a blend bind: metal is one rigid bone"; set: "members
are not in one frame (<ids>)", "scale_group undecided for the pair <a>, <b>: the captain's decision D4".

## 9. Side effects and safety
Documents and Vault rows only; geometry untouched.

## 10. Tests (RED first)
1. RED `test_owner_by_index_breaks_on_reorder`: export and re-import the chest fixture with a different face order; today's owner map labels the wrong faces (AUDIT T45); with `lw_source_face`, the labels follow the faces.
2. `test_metal_bind_rigid_only` (schema rule; falsifier: a metal part with two bones).
3. `test_set_refuses_mixed_frames`: a set with one member still `raw`.

## 11. Acceptance evidence
The chest's approved part set (its recipe's parts) as documents; the `set` for the five pieces with the body package hash.

## 12. Dependencies and order
`normalize_mesh`.

## 13. Open questions
D4 (pair scale group).
