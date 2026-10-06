<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 13 — UV: unwrap, pack, score, and the Smart-UV island facts

Status: **CANONICAL for the measurements (one definition) and the Smart-UV facts; DRAFT for unwrap/pack** (Lampway's own unwrap
has not been compared against Tripo Smart UV on a real piece). Implemented by: shelf `texlib/uv_score.py`; LT
`features/uv_islands.py` (the "one definition"), `features/uv_score.py`, `features/uv.py` (unwrap, `uv_report`, `worst_stretch`,
seam rule), `features/uv_texel.py`, `features/uv_layout.py`, `features/uv_rectify.py`; shelf `partseg/uv_patches.py` (ported,
inside `rebuild`); Tripo Smart UV (subscription slot, 20 credits + 3 free retries).

## A. Problem

Give a mesh a UV layout that textures and bakes cleanly, and pick among candidates (Tripo's four Smart UV attempts, our unwraps) by
numbers, not by eye. Inputs: mesh + UV layer(s), texture size. Outputs: per candidate `{utilization, overlap, islands,
stretch_p90_p10, off_density_2x, flipped, seam_m, score}` and, for our unwrap, a new `<name>_uv` object.

## B. Method

1. **Islands** = connected faces sharing a corner with the same (vertex identity, UV) — vertex identity is the position-welded
   vertex on smart meshes (canon 01 D.1): on a Tripo smart mesh index adjacency and UV adjacency coincide by construction.
2. **Utilization and overlap** by rasterising every UV triangle at `res` (1024; the number Tripo's panel shows within ~1 point) with
   a **half-open (top-left) edge rule**: a texel centre on a shared edge belongs to exactly one triangle. Overlap = texels covered
   twice or more / covered texels. (An inclusive rule double-counts an island's own diagonals: golden C09 reads 0.00167 overlap on
   a layout with none — reproduced with Lampway's formula.)
3. **Density/stretch:** per face `s = sqrt(A_uv / A_3d)`, normalised by the median; area-weighted p90/p10; `off_density_2x` = share
   of 3D area with s > 2 or < 0.5. Worst conformal distortion from the singular values of the UV Jacobian (`uv.py:176 worst_stretch`).
4. **Flipped:** signed UV area per face against the majority sign (a deliberately stacked mirrored pair is reported as stacked, not
   flipped).
5. **Seam length:** 3D length of edges whose two faces disagree in UV.
6. **Score** (shelf, untuned weights): `utilization · (1 - overlap) · (1 - off_density_2x) - 0.5 · flipped`; advice, the captain picks.
7. **Unwrap engines:** Tripo Smart UV for armour (it segments into clean texture regions; utilization typically 70–80 %, seen 90 %);
   Blender angle-based (ABF++, Sheffer, Lévy, Mogilnitsky, Bogomyakov 2005) or conformal (LSCM, Lévy, Petitjean, Ray, Maillot
   2002); low-distortion option SLIM (Rabinovich, Poranne, Panozzo, Sorkine-Hornung 2017). Seams by dihedral angle or hidden from a
   viewer (`uv.py:124 _seams_by_rule`: a minimum spanning cut through the least visible edges).
8. **Pack:** islands into 0..1 with margin `px/size` (1 px per 256 px of map); rotation allowed; a texel-density pass scales each
   island to `target · weight / density` about its centroid then ONE uniform fit (`uv_texel.py`; TexTools' rule); the class target
   is rasterised chart packing with rotation (xatlas, MIT, after Thekla Atlas) — [UNVERIFIED gain over Blender's packer here].
9. **Patches** (faces added by hole repair, `orig_poly = -1`): the island puzzle first — a patch inside one island fills that
   island's UV hole harmonically, rim pinned; a patch on an island's OUTER border gets its own island; pack with every original
   island LOCKED, and prove the original UVs moved by 0 (`uv_patches.py:122-126`).

## C. Invariants

- **INV-13.1 One definition** of islands/coverage/overlap/density for every tool (scores comparable across engines).
- **INV-13.2 Texturing comes LAST**: Smart UV before any studio texture; any UV/geometry step after a texture discards it.
- **INV-13.3 Smart UV ends free Edit-Mesh edits**: run it on a saved copy; the original stays virgin and regenerable.
- **INV-13.4 Pick by measurement** (`uv_score`), not by utilization alone.
- **INV-13.5 Smart-UV islands are relief parts:** a raised relief is the part's DENSE islands — mean polygon area < 70 mm²
  (lion face + mane 64–66, beard 58; scrolls 79–125; plates 160–740; at 60 the lion is missed) (memory
  smart-uv-islands-are-relief-parts; shelf `partseg/split_relief.py`). Height, curvature and normal-spread signals all failed.
- **INV-13.6** Never credit a method with "respecting islands" before checking that its graph could cross a seam at all.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-03 | PartField's clusters matched UV islands 99.8 % — an artefact of the seam split | weld before adjacency | memory smart-mesh-seams-split-vertices |
| 2026-10-04 | 20 of 23 chest patches sat on an island's outer border; a harmonic/affine fill folded ~100 % of their faces | own islands, originals locked | memory smart-uv-islands-are-relief-parts |
| 2026-10-04 | Patch faces took their nearest rim vertex's UVs: a smear across every patch | patch UVs before texturing | `uv_patches.py:1-4` |
| 2026-10-05 | Texture before Smart UV was discarded by the UV step ("I learned that the hard way") | texturing last | memory tripo-studio-invariants |
| 2026-10-05 | Helmet1 Smart UV: 35.4 % utilization, ~6,000 islands from the plume strands, all four attempts equal | strands need their own treatment (cards / atlas strip), not a better unwrap | PIECE_PIPELINE step 8 |
| 2026-10-04 | Measured Smart UV utilizations: Chest1 74.9–75.6 %, Boots1 78.3 %, Waist1 76.9 %, Gauntlets1 77.9 % (attempt 3 at 77.2 % had a tenth of the flipped faces) | the score, not utilization, picks | PIECE_PIPELINE; memory tripo-studio-invariants |

## E. Golden tests (`goldens/C09_uv`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G13.1 metrics | `three_islands.obj` | utilization 0.4375 exact; overlap 0; islands 3; flipped 1/3 | inclusive raster: overlap 0.00167 |
| G13.2 overlap | `overlap.obj` | overlap 0.400 (0.125 / 0.3125); utilization 0.3125 | — |
| G13.3 seam split | `split_seam.obj` | index components 2, welded 1, UV islands 2 | an index-adjacency segmenter reports two parts |
| G13.4 relief rule | `relief_islands.json` | islands 0 and 2 are relief at 70 mm² | a threshold of 60 misses island 0 |
| G13.5 shelf parity | `<shelf-scratch>/tripo_uv/Boots1/attempt_2.fbx` (private asset, not committed) | utilization 0.7824, overlap 0.0002, islands 706, stretch 1.252, flipped 0.0005, seam 23.09 m, score 0.7813 (±0.5 %) | — |

## F. Implementation gap (Lampway `b806617f`)

1. **Two island definitions:** LT `features/uv_islands.py:34` (vertex index + UV rounded to 6 decimals) and LT `features/uv.py:213`
   `_island_ids` (edge-based, UV rounded to 5) — `uv_report` and `uv_score` can disagree.
2. **Two rasters:** `uv.py:18` GRID 512 vs `uv_islands` `res` (1024); both inclusive (`uv.py:112`, `uv_islands.py:80`).
3. **Pack:** `uv_texel.py:107-136` packs rows of upright islands (no rotation); `uv_unwrap` uses Blender's packer then one global
   scale for texel density (`uv.py:297-308`).
4. **No xatlas** or SLIM option.

## G. Agent-facing tool contract — `lampway_uv_score` / `lampway_uv_unwrap`

`lampway_uv_score {objects|files, res: 1024, gates: {max_overlap: 0.005, max_flipped: 0.02, max_off_density_2x: 0.05}}` — refusals:
no UV layer (row error, others continue); file outside the project. Receipt rows as B; `best` is advice.
`lampway_uv_unwrap {object, method: smart|angle|conformal|tripo_smart_uv, seam_rule, margin_px, texel_density, lock_islands}` —
refusals: a textured object without `discard_texture`; an unapplied non-uniform scale; Tripo route on an original (copy first).

## H. Decisions owed by the captain

1. The gate defaults (overlap 0.5 %, flipped 2 %, off-density 5 %) — placeholders until he sees them on real pieces.
2. House texel density (equalise only, or a fixed px/m).
