<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: `lampway_normalize_mesh`

Status: **new** (replaces the landing logic of `studio_landing.import_file`, `asset_place._import`, `live_load.load_rebuild`,
`mesh_to_npz`, and upstream `model_io.rename_generated_model`). Priority P0.

## 1. Name and one-line purpose
`lampway_normalize_mesh` / api.tool `normalize_mesh`: a raw mesh (a file or an object) into a canonical `mesh` with its receipt,
or a refusal that names what could not be decided.

## 2. Source
- Canon 01 B (frames, Tripo's +X front after import, ~0.98 m generator normalization, "A tool never assumes the turn"), D.1 (weld by position before adjacency).
- Memory pipeline-set-hp-lp: "Every file is normalised to ~0.98 m on its longest side, so absolute scale never survives Tripo. The scale comes from the body at intake."
- Memory smart-mesh-seams-split-vertices: "Weld by position before any adjacency-based segmentation or measurement."
- Upstream prior art: `MX/common/job_queue/core/model_io.py` `_set_origin_bottom_and_center` (apply transforms, ground the origin) and `MX/moodboard/core/generation_enqueue.py` `model_front_zrot` (one turn per engine: the rule this contract replaces with a per-piece decision).

## 3. User story
Runs at every ingress without being asked: the Studios panel Import, Vault placement, the rebuild landing, the batch scripts'
file reads. The agent calls it on a mesh the captain dragged in. The captain sees one receipt per piece. A multipart file is one imported assembly: its meshes retain their relative world geometry under one shared turn and origin.

## 4. Inputs
```json
{"input": "object name | project path (glb, gltf, fbx, obj, usd, blend)",
 "turn_deg": "number | null (the piece's facing: -90 for a +X-facing import; null = decide by plate or recipe)",
 "plate": "project path of the approved Front plate | null (enables measured facing)",
 "facing_margin": "number 0..1 | null (explicit minimum best-minus-second silhouette IoU; null uses judgment default0.05, physically untested)",
 "recipe": "project path | null (a recipe's per-piece turn_deg wins over a guess, never over an explicit turn_deg)",
 "generator": "tripo_studio | tripo_api | meshy | hi3d | hyper3d | hunyuan | trellis | captain_authored | lampway_tool | unknown (default: from the Vault record)",
 "want_scale": "real | any (default any)", "scale_evidence": "{method, value, reference} | null",
 "weld": "auto | never (default auto: weld generated meshes, never authored rigs)", "weld_distance_m": "1e-7..1e-3 (default 1e-5)",
 "store": "true | false (default true: the canonical version goes into the Vault)"}
```
Bounds and refusals in section 8.

## 5. Outputs
`{ok, object, asset_id, version, document, receipt, receipt_path}`; the datablock stamped `lw_canon`; in the Vault, a new
version with files `main` + `canon` and relation `normalized_from` to the raw version; the receipt
(`lampway.normalize-receipt/1`, DOOR.md §3.2) under `<root>/canon/receipts/<canonical_sha256[:12]>.json`.

## 6. Engine (proven code)
Blender importers through `canon_io.import_raw` (DOOR.md §1); transform apply with winding reversal as `batch_export._apply_transforms`
(`LT/features/batch_export.py:102-113`); weld by `bmesh.ops.remove_doubles` with the 5 % guard of `scene_cleanup`
(`LT/features/scene_cleanup.py:189-197`); topology and UV measurement from `common.mesh_report` (`LT/features/common.py:77-117`)
and `uv_islands.measure_object` (`LT/features/uv_islands.py:85-121`); geometry hash as `workflows.mesh_hash`
(`LT/features/workflows.py:37-46`) over canonical positions. **Plate registration** (measured facing): `render.render_view`
silhouettes at four cardinal yaws (0, -90, 90, 180) against the approved Front plate, using the shared `silhouette._render_mask` engine and `canon_geom.fit_masks_true_aspect`/`mask_iou`. The plate loader retains native dimensions, keys alpha or the canon-10 border ring, and never stretches a rectangular plate square before fitting. A unique winner must beat the second by the explicitly supplied or ruled margin; a tie always refuses. Measurement uses a disposable object, scene and image files; the input stays untouched until the frame is accepted. For multipart files, capture every source world matrix before changing any mesh and normalize parents before children. Compute one bottom-centre offset from the union of all source vertices after the shared turn. Bake that same turn and offset into every member, including shape keys, without resizing pieces. Each member records `pivot.rule=source_origin` relative to the rebased assembly origin; every receipt records the assembly member count, turned union bounds, shared offset and turn. A single-object input retains its own bottom-centre pivot. Multipart plate-only facing refuses until the caller provides a shared turn or recipe turn; per-member silhouette choices cannot establish one assembly frame. Animated or constrained assembly transforms require an explicit static copy. Licence: Blender GPL; nothing new.

## 7. Model slot
None. A vision judge never decides a frame.

## 8. Preconditions and refusals
| refused when | message (names the fix) |
|---|---|
| the frame is undecided: no `turn_deg`, no recipe entry, no plate | "frame undecided: pass turn_deg (the piece's facing) or plate=<approved Front plate>" |
| plate registration's best yaw beats the second by less than the margin (decision D6) | "facing ambiguous: yaw A IoU x, yaw B IoU y; pass turn_deg" |
| `want_scale=real` with no evidence | "scale unknown: real scale comes from fit_place (armour) or scale_to_measure; normalize with want_scale=any to keep generator scale" |
| a weld would merge more than 5 % of the vertices | "the weld distance is wrong for this mesh: pass weld_distance_m" |
| multipart facing has no shared declared/recipe turn | "assembly facing needs one shared turn_deg or a recipe turn" |
| multipart transforms are animated or constrained | "animated or constrained assembly transforms need an explicit static copy" |
| the input is skinned (an Armature modifier, a parent armature) | "a skinned mesh is normalized with lampway_normalize_rigged" |
| the input already carries `lw_canon` whose hash matches | not a refusal: `{ok, unchanged: true}` (idempotent) |

## 9. Side effects and safety
Imports into the open scene (main thread) or a headless worker for a path with `store=true, place=false`; never edits the raw
file; writes the receipt and the Vault version; one undo step. Never in the captain's live window when called by a worker.

## 10. Tests (RED first)
Fixtures: a synthetic box exported three ways (GLB with +X front, FBX at cm, FBX with a parent empty and a 90-degree node
rotation), a seam-split UV sphere (each island its own shell), the Boots1 Smart UV attempt (`<shelf-scratch>/tripo_uv/Boots1/attempt_2.fbx`, 27,753 faces, 706 islands per its `uv_score.json`) where the shelf is mounted.
1. RED `test_studio_import_lands_raw_today`: `studio_landing.import_file` of the +X GLB leaves the box facing +X with no stamp (the bug, AUDIT I1). Kept as the falsifier after the fix: the landing must now return a stamped -Y object.
2. `test_three_containers_one_canonical`: the three exports normalize to the same `geometry_sha256` (the box faces -Y, metres, identity matrix).
3. `test_weld_unsplits_islands`: the seam-split sphere's `shells` goes from the island count to 1; UV islands unchanged; the receipt counts the merged vertices.
4. `test_turn_is_recorded_and_reversible`: `axis_map` applied inverse returns the raw positions within 1e-6.
5. `test_unknown_scale_refused_when_real_wanted` and `test_generator_scale_recorded` (Tripo source -> `generator_normalised`, `longest_side_m` measured).
6. `tests/lampway_tools/test_canon_normalize_facing.py` pins the native plate-registration golden: a synthetic L profile rendered as the approved Front on a rectangular alpha canvas, raw geometry baked +90°, winning turn -90° with best/second IoU and explicit margin in the document and receipt. Falsifier: a symmetric cube ties and yields "facing ambiguous", preserving geometry and all IDs. Unset/out-of-range margins refuse; the nonliteral background uses the shared border-ring key.
7. `test_idempotent`: normalizing a canonical object changes nothing and returns `unchanged`.
8. `test_reproducible`: the same raw bytes and decisions give byte-identical `.canon.json` and canonical `.blend` content hash [UNVERIFIED whether .blend writes are byte-stable; if not, the canonical hash covers the payload, SCHEMA.md §3].

9. Multipart hierarchical GLB regression checks every vertex against one shared turn/union-origin transform under the existing 1e-6 m bar, canonical checks and assembly receipt scope. Plate-only multipart refusal restores all scene IDs.

## 11. Acceptance evidence
The four Tripo pieces of the "proportioned" set and one Hi3D and one Meshy file normalized: receipts with each frame decision,
the chest's `turn_deg` differing from the greaves' (canon 01 B), Workbench front views showing every piece facing -Y.

## 12. Dependencies and order
`canon_asset`, `canon_door` (the decorator). Before every landing rewire (`canon_migration.md`).

## 13. Open questions
D6 judgment margin0.05 is adopted, physically untested; approved original-plate calibration remains open. D5/D10 retain their recorded rulings.
