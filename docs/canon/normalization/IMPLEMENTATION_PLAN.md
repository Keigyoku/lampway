<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Normalization: implementation plan

Owner: the canon lane (`lp/canon`), which owns the shared geometry module (`canon_geom`, `../IMPLEMENTATION_PLAN.md` item 1) and
is the intended implementer. Every item is RED-first: its named falsifier is seen failing the OLD code before the new code lands
(the canon plan's rule, §2). Laws: `<specs>/CONTRACT_TEMPLATE.md`. Placeholders as in AUDIT.md.

## 1. How this slots into the canon plan

The canon plan's first slice is `canon_geom`, validation receipts, weights, bind-and-return, placement (`../IMPLEMENTATION_PLAN.md`
§1, "The first five items"). Three of those five read inputs whose canonical state nobody records today: weights need welded
geometry and bone directions (AUDIT ranks 5, 6), placement needs the piece's facing (rank 4), validation's seam metric needs a
weld (rank 6). So the schema, the importer funnel and the door go **in front of canon item 2**, built alongside `canon_geom` in
the same lane. Canon item 1 is unchanged; canon items 2-14 and R1-R11 each gain one line: "declare `consumes` and read
`along`, `welded`, `scale.state`, colour space from the stamp".

| order | item (contract) | canon plan link | replaces / fixes (AUDIT row) | RED goldens and falsifiers | size |
|---|---|---|---|---|---|
| **N0** | `canon_asset`: the schema module, the JSON Schema shipped in `LT/canon/`, the vendored validator, `lampway_canon_status` (`contracts/canon_asset.md`) | beside canon item 1 (pure, standalone suite) | P1-P2 (the template gains an "Input conventions" section: §3 below) | `selftest_schema.py` cases through both validators; vendored-vs-jsonschema mutation test | S |
| **N1** | `canon_io`: `import_raw` (the only importer), `load_image(role)`, `facts`, `read_npz`/`write_npz` with the `canon` header (`../DOOR.md` §1) | uses canon item 1's `chain_ends` for skeleton facts | rank 1's raw landings become `lw_raw` datablocks | `test_one_importer` (AST) RED with the 20+ call sites | M |
| **N2** | The door: `api.tool(consumes=, produces=)`, `runner.Tool.consumes`, `TOOL_DOORS`, the AST and red-team CI checks, every existing tool marked `LEGACY` and the ratchet file at that count (`contracts/canon_door.md`) | precondition of canon items 2-14 | the gate the captain asked for | `test_every_tool_declares` RED; red-team pass vacuous until N3 | M |
| **N3** | `lampway_normalize_mesh` with plate-registration facing, weld, source face ids, receipts (`contracts/normalize_mesh.md`) | shares the weld with canon item 3 (weights: "weld first") | I1, I14, I24, I26 landings rewired (group 1 of `canon_migration.md`); upstream `model_front_zrot` deleted | `test_studio_import_lands_raw_today` RED; three-containers-one-canonical; weld unsplits islands; facing on an asymmetric fixture | M |
| **N4** | Vault: migration 0004, `put` requires canonical or raw, ingest's tier-1 GLB stats from canonical documents, `asset_place` places canonical by default (`contracts/canon_migration.md` §6) | none | I8-I15, P6-P8; the dead `scale_to_unit` | `test_put_requires_canonical_or_raw` RED | M |

**The first five items are N0-N4.** After them every new asset entering Lampway is canonical or visibly raw, and no tool can be
added without declaring its input.

| order | item | canon plan link | fixes | RED | size |
|---|---|---|---|---|---|
| N5 | `lampway_normalize_rigged` (`contracts/normalize_rig.md`) = canon R1 inspect + R3 normalize behind the ingress door; `fit_body build` stamps the body | canon R1, R3 (pulled forward) | ranks 5, 9 (tail direction; retarget scale) | `test_plan_reads_the_tail_today` RED; canon R01-R03 | M |
| N6 | Fit chain doors (migration group 2), in the canon's own order: placement (canon item 5) re-stamps `scale.state = real` with the enclosure as evidence; weights (canon 3) read `welded` and `along`; validation (canon 2) reads the weld | canon items 2, 3, 5, 7, 11 | ranks 4 (the chest's default turn), 5, 6, 11 | each canon item's goldens plus "refuses a raw piece" | L (spread across the canon items) |
| N7 | `lampway_normalize_texture` / `_material` (`contracts/normalize_texture.md`); group 4 doors | canon item 9 (bake: "tangent basis in bake.json") | rank 10 (CC0 sRGB set, `pbr_pack` GL assumption, bake attach DX) | `test_cc0_set_is_not_all_srgb`, `test_bake_attach_dx` RED | M |
| N8 | Geometry doors (group 3): `segment_mesh`, `retopo`, defect scan, mesh QA thresholds (decision D8), lineage anchors re-recorded | canon items 10, 12 | ranks 6, 11 | segment on the seam-split sphere: 1 shell after; QuadriFlow no longer falls back silently | M |
| N9 | `lampway_normalize_clip` (`contracts/normalize_clip.md`); animation doors (group 5) | canon R4 (O36), R8 | rank 8 (multiview reflection) | `test_multiview_forward_is_minus_y` RED; canon G22.1-G22.4 | M |
| N10 | `lampway_normalize_parts` (`contracts/normalize_part_set.md`) | canon item 13 (the orchestrator's `fit.json` names the set) | T45 (owner maps by index) | `test_owner_by_index_breaks_on_reorder` RED | S |
| N11 | Library migration run (the captain's click) and the shelf seeds' canonical twins | none | the existing 61 seeds and part sets | `test_plan_lists_undecided_facings` | M |
| N12 | Scale-free and read-only doors (group 6); the ratchet reaches zero and `LEGACY` is deleted | none | AUDIT A- rows | `test_legacy_ratchet` at 0 | S |

## 2. Test discipline (inherits the canon plan's §2)

- The schema's self-test and the AST checks run in the standalone suite (no Blender); the red-team pass and every normalize test
  run against the real binary, headless and niced, in a factory-empty scene; never in the captain's live window; Workbench only
  for the facing renders.
- Fixtures are synthetic (generated boxes, spheres, L-shapes, a three-bone arm) plus the shelf's own files where the shelf is
  mounted (`LAMPWAY_SHELF_SCRATCH`), skipped with a stated reason elsewhere, never counted as a pass.
- A normalize receipt is a golden: the same raw bytes and decisions give byte-identical `.canon.json`.

## 3. Agent and spec entries (so agents and crews use the door)

1. **`CONTRACT_TEMPLATE.md` gains section 4a "Input conventions"**: the kinds, scale states, bone convention and colour roles
   the tool consumes (the `Need`s of its door), and section 5 gains "the canonical document it produces". Every contract written
   after N2 fills them.
2. **rail@ `lampway-tool-authoring` §2** gains: "declare `consumes=` (a `Need` per asset argument) and `produces=`; never call an
   importer: use `canon_io`". **`lampway-canon`'s table** gains a row: "an asset arrives -> `lampway_normalize_<kind>`; a tool
   refuses 'normalize first' -> run the named normalizer, never strip the stamp".
3. **The pre-tool reminder** (canon plan §3.3) adds `import_scene`, `wm.*_import`, `transform_apply`, `images.load` and
   `colorspace_settings` to its list.
4. **Tool descriptions** (the server Defs) gain the door's needs, generated from `TOOL_DOORS` (rail's generated docs, `docs@
   docs/gen_tools.py`).

## 4. What is not in this plan

No model is trained or downloaded; no Studio credit is spent (the vendor real-scale flags, Tripo `auto_size` and Hyper3D
`bbox_condition`, are measured only when the captain runs a generation he wanted anyway); the Titan repository is not edited
(Titan's `canon.py` and `animation_canon.py` are read as the interchange reference; the port is canon 22 H.1's decision).
