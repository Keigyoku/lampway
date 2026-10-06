<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: migration to the canonical door (existing tools, existing Vault assets, existing shelf data)

Status: **new**. Priority P0 (the order of everything after the module and the door). Placeholders as in `../AUDIT.md`.

## 1. Name and one-line purpose
`lampway_canon_migrate` / api.tool `canon_migrate` (Vault side: `AssetLibrary.migrate_canonical`): give every existing asset a
canonical twin without touching the raw one, and move every tool from `LEGACY` to a real declaration, group by group.

## 2. Source
- `../AUDIT.md` (107 rows; 41 SKIPS), `../DOOR.md` §4-5.
- `SRV/library/store.py:118-136` (numbered migrations with a pre-migration backup: `VACUUM INTO '<db>.pre-NNNN.bak'`).
- Memory measure-the-mesh-not-the-render; memory pipeline-set-hp-lp (per-piece facing, ~0.98 m).

## 3. User story
The captain clicks "Normalize library" once: a preview lists every asset with the decision the normalizer would make and the
ones it cannot make; he answers the undecided facings; the run writes canonical versions. Crews then convert tool groups.

## 4. Inputs
```json
{"action": "plan | run | status", "scope": "vault | shelf_seeds | scene", "kinds": ["mesh", "rig", "animation", "map", "texture_set", "material"],
 "decisions": "project path of a facing/scale decision file (piece -> turn_deg, plate) | null", "by": "captain (run only)"}
```

## 5. Outputs
`plan`: per asset `{id, kind, raw_sha256, would_decide: {frame, scale_state, weld}, undecided: [why]}` and counts; `run`: the
canonical versions written, `normalized_from` relations, receipts, and the undecided list untouched.

## 6. Engine (proven code)
**Vault migration 0004** (`SRV/library/migrations/0004_canonical.sql`): `relation.type` CHECK gains `normalized_from`; table
`canonical(version_id PRIMARY KEY REFERENCES version, schema_version, kind, frame, scale_state, scale_decision, canonical_sha256,
raw_sha256, receipt_sha256, doc_json)`; `version_file` role `canon`. `AssetLibrary.put` for kinds mesh, rig, animation, map,
texture_set, material requires `canonical` (validated by `canon_asset.validate`) or `subtype: raw`; existing rows are marked raw by
the migration. `mesh_stats.dim_*` and `bbox_*` are rewritten from canonical documents only. The batch run uses the normalize tools
in a niced headless worker (the `render_worker` pattern, `SRV/library/render_worker.py`), one asset at a time.

**Tool groups, in order** (each group: replace `LEGACY` with real `Need`s, delete the group's `turn` defaults, read `along`,
`welded`, `scale.state`, colour space from the stamp; the count in `canon_legacy_count.txt` falls by the group's size):
1. Landings: `studio_landing`, `asset_place`, `live_load`, `mesh_to_npz` (npz gains its `canon` header), `catalog_export`, the
   batch scripts' file reads, upstream `model_io` (its `model_front_zrot` table deleted: the facing comes from the normalizer).
2. Fit chain: `fit_body`, `fit_place` (turn from the stamp; it re-stamps `scale.state = real`), `fit_pose`/`pose_clearance`,
   `fit_openings`, `fit_bind`, `weight_*`, `garment_clearance`, `fit_validate`, `pose_test`, `rig_armor`, `fit_export`.
3. Geometry: `segment_mesh`, `retopo`, `mesh_defect_scan`, mesh QA (thresholds re-expressed, decision D8), `scene_cleanup`,
   `mesh_prep`, `asset_acceptance`, `asset_lineage` (anchors re-recorded in canonical space), orphans geometry group.
4. UV and texture: `uv_*`, `bake_maps`, `pbr_pack`, `material_bake_export`, `project_views`/`texture_gen`, `meshpaint`,
   `detail_normals`, `procedural_library`, `layered_material`.
5. Animation: `animation_retarget`, `clip_classify`, `anim_*`, Wave 6 motion tools.
6. Read-only and scale-free tools: `model_compare`, `silhouette_compare`, `seed_audit`, `parts_critique`, proportion tools,
   Vault previews and similarity (declare `scale=any`).

**Shelf seeds and the Parts Library:** the 61 seeds (`<specs>/asset_library/asset_schema.md` §2) and the shelf's part sets get
canonical twins with frame decisions from a decision file the captain approves (canon 01 B's measured facings as the proposal:
greaves and helmet +X, chest -Y, waist wide on Y); scale `generator_normalised` with the measured longest side.

## 7. Model slot
None.

## 8. Preconditions and refusals
`run` by anyone but the captain -> "the migration writes the whole library: the captain's click"; free space under 2x the
batch (the store's own rule, `store.py:220-223`); an asset whose raw file is missing -> listed, skipped, never fabricated.

## 9. Side effects and safety
Never modifies a raw file or a raw row's content; a pre-migration backup (the store's `VACUUM INTO`); rollback = soft-delete
the migration batch (`store.rollback`). The tool-group conversions are ordinary PRs.

## 10. Tests (RED first)
1. `test_migration_0004_applies_and_backs_up` on a copy of a fixture library.
2. `test_put_requires_canonical_or_raw`: RED today (`store.put` accepts any mesh).
3. `test_plan_lists_undecided_facings` on fixtures with no recipe turn and no plate.
4. `test_asset_place_places_canonical_by_default`.
5. Per tool group: the group's RED tests from the normalize contracts (e.g. `fit_place` with the chest at the old default turn 0 now refuses or reads the stamp).

## 11. Acceptance evidence
`status` after the run: assets by kind with canonical twins, undecided count, receipts; the legacy count at zero after group 6.

## 12. Dependencies and order
`canon_asset`, `canon_door`, `normalize_mesh` (group 1), `normalize_rigged` (group 2), `normalize_texture` (group 4),
`normalize_clip` (group 5).

## 13. Open questions
D7 (ratchet vs hard switch), D8 (threshold re-expression).
