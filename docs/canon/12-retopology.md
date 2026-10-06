<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 12 — Retopology: a game mesh from the generated high-poly

Status: **DRAFT** (no retopology has been accepted on a real armour piece; the method below is the one the measurements point at).
Implemented by: LT `features/retopo.py` (QuadriFlow, voxel fallback, AutoRemesher via a user-built `native/quadremesh` binary);
Tripo Studio Retopo (subscription slot, 10 credits, Quad | Triangle, 500–50,000); astra `authored/final/author_helmet.py`
(procedural authoring, one helmet).

## A. Problem

A generated high-poly (Tripo/Hi3D: 25k–1M+ faces, one shell or welded parts, a UV atlas only after Smart UV) must become a game
mesh: a budget (the captain's bar, Tripo Studio's helmet: 4,578 polygons, 2,792 quads + 1,786 tris, 0 n-gons, a real 4096²
atlas), edge flow on silhouettes and plate edges, separate rigid parts where the fit needs them, then UV (canon 13) and a bake of
the high-poly's detail (canon 14). The claude-2 spike found that "the gap to 'stunning' is entirely the retopology -> unwrap -> bake
stage" (`<astra-shelf>/from-claude-2/REPORT.md` §0, 2026-09-20).

Inputs: the high-poly (body frame or own frame, metres), the part map (`owner_poly`) and roles, a budget per piece, the target
method. Output: a new object `<name>_retopo`, all-quad or quad-dominant, no UVs, with a two-sided deviation report and the part
map carried over.

## B. Method

1. **Segment first, remesh per part.** Remeshing a fused shell erases the part boundaries the fit needs (a metal part must stay one
   part). Remesh each part (or each rigid group) separately with its boundary preserved, then weld along the shared boundary by
   position.
2. **Engines, proven code first:**
   - QuadriFlow (Huang, Zhou, Niessner, Funkhouser, Guibas 2018, "QuadriFlow: A Scalable and Robust Method for Quadrangulation",
     CGF/SGP) — Blender's `quadriflow_remesh`; deterministic with a fixed seed; refuses non-manifold input.
   - Instant Field-Aligned Meshes (Jakob, Tarini, Panozzo, Sorkine-Hornung 2015, SIGGRAPH Asia) — the field-aligned family;
     AutoRemesher (Dust3D author, MIT since 1.0.0) adds curvature adaptivity, anisotropy and sharp-edge preservation
     (`--sharp-edge`, default 90 deg) and projects extracted quads back onto the input.
   - Voxel remesh — closes openings and loses thin plates (measured: "a remesh loses thin open plates", GENERATED-EQUIPMENT §7j):
     a fallback for closed organic solids only, never silent.
   - Procedural functional armour (the captain, 2026-09-29): simple shapes (tube and shell segments, curved plates, bands, domes,
     cloth panels) fitted to each genned segment, projected onto it within a tolerance, detail baked; each shape one rigid part on
     one bone (memory procedural-functional-armour). The authored helmet (4,546 polygons, 4,442 quads) reached mean six-view IoU
     0.852 vs Tripo's 0.848 but failed the crest length (0.393 < 0.408) and finish (`<astra-shelf>/REPORT-AUTHORED-HELMET.md`).
3. **Hard-surface flags:** preserve sharp edges (dihedral > the feature angle) and open boundaries; keep thin plates as surfaces,
   never thickened or closed.
4. **Deviation, two-sided:** sample both surfaces; report max and p95 of (retopo -> source) AND (source -> retopo), relative to the
   source bounding diagonal. One side alone misses geometry the remesher DROPPED (a crest, a strap).
5. **Silhouette check** against the source in the six views (canon 10 B.6, aspect-preserving).

## C. Invariants

- **INV-12.1** The source is never modified; the result is a new object.
- **INV-12.2** Retopo runs before UV and texture (texturing comes last); a retopo after a texture discards it.
- **INV-12.3** Part boundaries and metal parts survive: no remesh crosses a part boundary.
- **INV-12.4** A fallback engine is named in the receipt (`requested_method` vs `method`); never silent.
- **INV-12.5** Budgets are per piece and the captain's; a target above 3x the source refuses ("a remesher cannot invent detail").
- **INV-12.6** Tripo constraints (2026-10-04): a Quad Smart Mesh cannot be segmented; the segmented-quad route is Tri Smart Mesh ->
  Segment -> Quad Retopo (<= ~50k); a Smart Mesh cannot be retopologised into a Smart Mesh; every Studio action on a SAVED COPY
  (memory tripo-studio-invariants).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-20 | Best local reconstruction = a 1 M-triangle marching-cubes shell decimated to 40k with a projected bake; face count said nothing (InstantMesh's 15k was the worst mesh) | retopo -> unwrap -> bake is the missing stage; judge by two-sided deviation + silhouette | `<astra-shelf>/from-claude-2/REPORT.md` |
| 2026-09-21 | Authored procedural helmet: IoU parity at budget, crest and finish failed | procedural shapes for function, genned HP for detail (baked) | `<astra-shelf>/REPORT-AUTHORED-HELMET.md` |
| 2026-09-25 | Voxel-remesh cage lost thin open plates | no voxel remesh on plate armour | GENERATED-EQUIPMENT §7j |
| 2026-09-26 | The proportioned set's LP lies on its HP within 1–3 mm (p50) | a vendor LP is a valid retopo; transfer its UVs by projection | memory pipeline-set-hp-lp; §7k |

## E. Golden tests (`goldens/C13_retopo`, property goldens)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G12.1 sphere | `sphere_dense.obj` (r 0.5), target 600 | faces within ±35 % of 600; quad fraction >= 0.90; two-sided max deviation <= 0.05 of the diagonal; 0 non-manifold; repeat byte-identical | a stub that echoes the input fails the quad fraction |
| G12.2 dropped part | sphere + a 2 cm fin (to build) remeshed so the fin vanishes | source->retopo deviation >= the fin height; refused | one-sided deviation passes it |
| G12.3 part boundary | C03 tube (two parts) | the cut ring survives; no face spans both parts | a whole-shell remesh |

## F. Implementation gap (Lampway `b806617f`)

1. Deviation is ONE-sided: LT `features/common.py:77-117 mesh_report` measures only the result's vertices to the reference surface
   (G12.2 falsifier).
2. QuadriFlow runs with `use_preserve_sharp=False` (LT `features/retopo.py:146-147`) and falls back to voxel on a RuntimeError,
   reported only via `method` (:148-151); no `fallback` opt-in for QuadriFlow (AutoRemesher has one).
3. No per-part retopology; no part map carried over; no UV/part transfer from source to result.
4. AutoRemesher requires `settings autoremesher_bin` (user-built `native/quadremesh`), not measured on a hard-surface piece.

## G. Agent-facing tool contract — `lampway_retopo`

```json
{"object": "high-poly", "method": "quadriflow|autoremesher|voxel|procedural", "target_faces": 2000, "per_part": true,
 "owner_poly": "npy (REQUIRED with per_part)", "preserve_sharp_deg": 90, "fallback": false, "seed": 0}
```
Refusals: target > 3x source; per_part without a part map; a textured source without `discard_texture`; voxel on a piece with
thin open parts unless forced; engine not configured (names the setting). Receipt `{object, method, requested_method, faces,
quads, tris, ngons, deviation: {to_source_max, from_source_max, p95, relative}, parts_preserved, seconds, engine_version}`.

## H. Decisions owed by the captain

1. Per-piece budgets (the bar is ~4.6k polygons for the helmet).
2. Default engine for hard plates (QuadriFlow vs AutoRemesher) after the side-by-side; procedural functional armour as the
   primary route for metal parts?
