<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 14 — Baking: cage ray cast from the low-poly into the high-poly

Status: **DRAFT** (the method and its cage rules are canonical; no bake has been accepted on a real piece; the engine-side tangent
basis is [UNVERIFIED] until a UE import is read back). Implemented by: LT `features/bake.py` (planner) +
`scripts/bake/bake_maps.py` (headless niced Cycles worker); Titan `equipment_uv.py` + `recipes/equip-blender.py uv_transfer`
(UV transfer by projection, the proportioned set); shelf `texlib/pbr_merge.py` (ORM pack, DX normal by green flip).

## A. Problem

Carry the high-poly's surface detail onto the low-poly's UV layout as engine maps: tangent-space normal (GL and DX), AO,
position/thickness, material/element ID. Inputs: LP (final UVs, no overlap unless declared stacked), HP (one or more objects or
named bake groups), cage (explicit, same topology as the LP, or an extrusion distance), max ray distance, size, margin. Output:
PNGs (16-bit normals), a per-texel HIT mask, `bake.json` with parameters, both meshes' hashes, per-map hit/miss fractions.
Frame: tangent space of the LP (U tangent, V bitangent, normal); GL = +Y green (Blender), DX = -Y green (Unreal).

## B. Method

1. **Per LP texel** inside a UV triangle: surface point p, interpolated normal n, tangent frame (T, B, N) from the SAME tangent
   basis the engine will use — MikkTSpace (Mikkelsen 2008, "Simulation of Wrinkled Surfaces Revisited", MSc thesis) for Blender and
   for UE's import default [UNVERIFIED for every UE import option; read back].
2. **Cage point** c = p + e n (or the explicit cage vertex interpolated); cast the ray c -> -n up to `max_ray`; take the first HP
   hit (Blender's selected-to-active semantics).
3. **Cage rules** (golden C10): the cage must ENCLOSE the HP (e >= the HP's greatest height above the LP), and the ray must reach
   the HP's greatest depth below the LP (`max_ray >= e + depth`). Measure the LP<->HP distance distribution first (sample LP
   vertices to the HP; the proportioned set's LP lies on its HP within 1–3 mm p50) and derive e and `max_ray` from it; refuse when
   the median exceeds e.
4. **Normal:** transform the HP normal at the hit into (T, B, N); encode GL `(n + 1)/2`; derive DX by flipping green in the pixel
   array — bake ONCE, never re-bake for DX.
5. **AO / thickness:** the scene needs a world (AO reads its distance); the target is invisible to its own rays (a decimated LP
   partly outside the HP otherwise blacks out AO); fixed seed; samples recorded.
6. **Bake groups:** HP parts are assigned to LP parts so a ray cannot hit a neighbouring part (cross-part hits) — the Alpaca3D Bake
   lab's "bake groups" and TexTools' name-keyed bake sets (`low/high/cage` keywords) are the reference behaviours.
7. **Hit mask and margin:** record hit / miss per texel; misses stay flat and are reported; dilate by `margin` px (default
   `size/128`, >= 2) outward from island borders only.
8. **UV transfer by projection** (no bake; when a vendor LP lies on the HP): per HP face the LP triangle nearest its centroid; per
   corner the UV on that triangle's plane, so no face straddles a seam; the turn that lays LP on HP is measured and refused when two
   turns tie (GENERATED-EQUIPMENT §7k: all five proportioned pieces PASS).

## C. Invariants

- **INV-14.1** Bake after the final UV; a UV change invalidates the bake.
- **INV-14.2** Overlapping UVs refuse unless declared stacked (a stacked bake writes both surfaces into one texel).
- **INV-14.3** Never Cycles in the captain's live Blender; a headless niced worker only, and not while he works live (memory
  no-heavy-renders-while-live: headless Cycles beside his live session locked the box) — or the compute offload when he opts in.
- **INV-14.4** The tangent basis of the bake equals the engine's; the export carries the tangents or the engine recomputes with
  the same algorithm.
- **INV-14.5** The look is judged in engine (memory final-look-judged-in-engine); Blender shows defects only.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-05 | Boots1 attempt_2 onto a 20 % decimation: AO 64.5 % black texels at the default cage (2 % of the diagonal, ray 0.5x); 9.5 % after cage 0.08 / ray 0.16 | ray >= cage + depth; derive from measured distances | `<lampway>/docs/reports/wave2.md` "Live verification" |
| 2026-10-05 | The planner's overlap check at 256 px over-counted a dense layout | measure overlap at the bake size | same |
| 2026-10-04 | A 2048 relief bump read as "a pixelation effect on everything" (the captain) | detail normals are a look aid, judged in engine | LT `detail_normals.py` docstring |
| 2026-09-26 | The low-poly's normal map is the high-poly's own detail baked for the low-poly — do not carry it onto the high-poly | material transfer without the normal map | GENERATED-EQUIPMENT §7k |

## E. Golden tests (`goldens/C10_bake`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G14.1 cap normals | `lp_plane.obj`, `hp_bump.obj` (cap radius 0.15, height 0.05; R 0.25), cage 0.06, ray 0.12 | 7 sampled texels' tangent normals within 0.02 of the analytic `(x, y, sqrt(R² - ρ²))/R`; DX = GL with green flipped (0.01) | no HP: all texels flat; flank texels fail |
| G14.2 sunk HP, short ray | HP lowered 1 cm, cage 0.06, ray 0.03 (0.5x) | hit fraction <= 0.03 (only the cap's top, ρ <= 0.07 m) | — |
| G14.3 sunk HP, long ray | same, ray 0.12 (2x) | hit fraction 1.0 | a "black texel" heuristic that cannot see flat misses |
| G14.4 determinism | two bakes, same inputs | byte-identical PNGs | an unseeded AO |

## F. Implementation gap (Lampway `b806617f`)

1. **Ray shorter than the cage by default:** LT `features/bake.py:62-65` sets `cage_extrusion = 2 %` of the LP diagonal and
   `max_ray = 0.5 x cage` — the configuration the Boots1 run had to override (G14.2).
2. **8-bit normals** (`bake_maps.py:39`, `float_buffer=False`) and DX by a second bake with `NEG_Y` (`:51`) instead of one GL bake
   plus a green flip.
3. **No hit mask:** misses are inferred from black texels of a rasterised UV polygon mask (`bake_maps.py:60-74`); a missed normal
   texel is not black.
4. Maps limited to normal / albedo / AO (`bake.py:21`); no bake groups; no tangent-basis statement in `bake.json`.
5. A bake overwrites when `overwrite=true` (`bake.py:74-76`); canon: a new hash directory per run.

## G. Agent-facing tool contract — `lampway_bake_maps`

```json
{"low": "object", "high": ["objects"] , "groups": {"lp_part": ["hp objects"]}, "cage": "object|null", "cage_extrusion": "auto|m",
 "max_ray": "auto|m", "maps": ["normal", "ao", "position", "thickness", "id_material"], "size": 4096, "margin_px": "auto",
 "normal_convention": "both", "samples": 16, "stacked_ok": false, "out_dir": "bakes/<low>"}
```
`auto` derives e and `max_ray` from the measured LP<->HP distances (B.3). Refusals: no UV; overlap above 0.5 % at the bake size;
median LP->HP distance above e; size not a power of two; live session detected (INV-14.3) unless `offload: true`.
Receipt `bake.json`: `{maps: {name: {files, bit_depth, hit_fraction, miss_fraction}}, cage_extrusion_m, max_ray_m, lp_hp_distance:
{p50, p95, max}, tangent_basis, seed, sha256: {lp, hp}}`.

## H. Decisions owed by the captain

1. Bake at all for the five armour pieces, or project (relief/mesh-paint) and transfer UVs as today?
2. GPU Cycles bake when he is not working live, or CPU only / compute offload?
