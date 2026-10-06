# Normalization: the answer (2026-10-06)

The auditor's tool refused this file, so the coordinator wrote it from the auditor's returned text. Details are in
`AUDIT.md` (107 rows), `SCHEMA.md` with `canonical-asset.schema.json`, `DOOR.md`, `IMPLEMENTATION_PLAN.md` and
`contracts/`.

**The question:** "None of our tools or relevant specs skipped normalization right?"

**The answer: no. They did not all normalize, and most of them skipped it.**
- No ingress produces a recorded canonical asset.
- No tool checks frame, real scale, weld or colour space at its door. Four tools refuse one non-canonical fact each:
  `fit_export`, `asset_acceptance`, `side_label_check`, `motion_experiment`.
- No typed schema exists anywhere. The Vault's `unit_scale` has no writer, so `scale_to_unit` never runs.

**Counts:**

| class | rows |
|---|---|
| SKIPS | 41 (20 ingress paths, 14 tools, 7 specs) |
| assumes canonical, unenforced | 34 |
| assumes canonical, one aspect enforced | 4 |
| normalizes | 22 |
| not wired | 2 |
| not applicable | 2 |
| unresolved | 2 |

## Top SKIPS
1. **Raw landings:** `studio_landing.py:16-34` and `asset_place.py:168-187` use importer defaults. A Tripo piece faces +X,
   is 0.98 m long, and has seam-split vertices.
2. **The Vault cannot tell raw from canonical:** `ingest.py:72-100` and `schema.py:27-28`.
3. **`mesh_to_npz`** (`mesh_to_npz.py:23-48`) decides nothing, and it is the fit chain's only entry.
4. **The facing turn has three defaults and is never stored:** `api.fit_place` uses 0 (`api.py:1040`); `place_piece`
   uses -90; the seed audit uses -90 for every piece.
5. **Bone direction from the imported tail:** `weights.py:103`, `fit_bind.py:52`, `rig.py:103`.
6. **No weld before adjacency:**
   - `segment_mesh` finds one part per UV island;
   - `retopo` silently falls back to voxel (`retopo.py:144-151`);
   - the weight fill does not weld;
   - the seam metric treats each UV island as a plate.
7. **Texel density in local coordinates** (`uv.py:61-71`).
8. **`anim_multiview_fit` writes a mirrored frame** (`anim_mv.py:54-55`).
9. **`animation_retarget` drops unit and non-uniform scale** (`animation.py:212-213`).
10. **Colour space and normal convention:**
    - CC0 sets are tagged sRGB wholesale (`cc0.py:260`);
    - `pbr_pack` assumes OpenGL;
    - `bake_maps` attaches DirectX unflipped (`bake.py:112-113`).

**Two findings beyond the brief:**
- The ingress itself skips; it is not only individual tools.
- ue_parity's GEO-17 claims a `fit_export` refusal that does not exist.

## Specified
- **Schema `lampway.canonical-asset/1`:** 8 kinds (mesh, rigged mesh, skeleton, animation clip, texture, material, part,
  set). JSON Schema 2020-12; the self-test reports 0 mismatches.
  - Working frame: metres, right-handed, +Z up, front -Y.
  - Scale is `real` (with evidence), `generator_normalised` or `unknown`; there is no guessed state.
  - Bones go head to next joint, with a named rest pose and a naming map.
  - Colour space is bound to each texture's role, and every normal map declares its convention.
  - Every asset records the sha256 of its raw source.
- **The door:**
  - only `canon_io` may call Blender importers;
  - a `lampway_normalize_<kind>` tool per kind, writing a receipt and refusing what it cannot decide;
  - the Vault keeps raw and canonical, linked by `normalized_from`;
  - `api.tool` gains a required `consumes=`;
  - CI: an AST scan for importer calls, a raw-input red-team test, and a `LEGACY` ratchet.
- **Plan, inside the canon lane before canon item 2:**
  - N0, the schema module;
  - N1, `canon_io`;
  - N2, the door and its CI checks;
  - N3, `lampway_normalize_mesh`, with the 4 landings rewired;
  - N4, Vault migration 0004.

## Risks
1. **Fixing the landings changes measured numbers:** thresholds tuned on raw pieces need re-measuring (D8).
2. **Lineage anchors live in object space:** they must be re-recorded in canonical space.
3. **Owner maps are keyed by polygon index:** a reordering re-import relabels them silently. `lw_source_face` fixes this
   for newly normalized meshes.
4. **The agent's raw-script output is unstamped,** so every door refuses it (D9).
5. **The door hashes every mesh:** the cost must be measured on the full body.
6. **Partial read:** about 16 of roughly 250 spec files.
7. **The audited worktree** was 47 commits ahead of `origin/lp/wave5`.

## Decisions owed
| id | decision | recommendation |
|---|---|---|
| D1 | Two frame layers (working canonical, plus canon 22's interchange via adapters) | yes |
| D2 | The canonical container | `.blend` plus `.canon.json` |
| D3 | When armour becomes real-scale | at intake, which changes the pipeline order |
| D4 | One scale per left/right pair, or per side | no recommendation without a measurement |
| D5 | The weld default for generated meshes | 1e-5 m with a 5 % guard; never authored rigs |
| D6 | Facing | a per-piece recipe turn, checked against the plates, with a refusal margin |
| D7 | Rollout | the `LEGACY` ratchet |
| D8 | Thresholds tuned on raw pieces | re-measure at real scale |
| D9 | Stamp integrity | hash-bound now; signing only if a forgery is seen |
| D10 | Pivot for an unplaced asset | bounding-box bottom-centre |
