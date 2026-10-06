<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 15 — Clearance and penetration: inside/outside, signed distance, gap, hideable

Status: **CANONICAL**. Implemented by: LT `features/clearance.py` (garment_clearance), LT `features/rig.py:261 _clearance`, LT
`features/validate_pose.py:94-100` (crossings); shelf `proportion/pose_clearance.py` (axis-ray depth); Titan `surface_query.py`
(constrained nearest), Titan `recipes/fit-measure-blender.py` (skin samples through armour: out share, depth, gap, per-view
visible/enclosed). Used by canons 05, 06, 08, 09.

## A. Problem

Three different questions share one word, "clearance": (1) is a point inside the BODY (penetration), and how deep? (2) how far does
the piece FLOAT off the skin (gap / hug)? (3) can a region of skin be hidden because solid armour encloses it from every view?
Inputs: the body at a pose (closed: the FullBody with its head, or declared open), the piece at the same pose. Output per vertex /
region: signed distance, inside flag, gap to the innermost layer, enclosed share per view.

## B. Method

1. **Unsigned distance:** nearest point on the body triangles (BVH; Ericson 2004 closest point on a triangle). Region-constrained
   when the question is per body part (Titan `surface_query.nearest(regions=, normal=, min_normal_dot=)`).
2. **Sign by the generalized winding number** w(p) = Σ signed solid angles / 4π (Jacobson, Kavan, Sorkine-Hornung 2013, "Robust
   Inside-Outside Segmentation using Generalized Winding Numbers", SIGGRAPH): inside when w > 0.5. Not by one face's normal at the
   nearest point: at a vertex or edge the "nearest face" is arbitrary and its normal can give the wrong sign (golden C05 spike);
   if a normal test is used it must be the angle-weighted pseudonormal (Bærentzen & Aanæs 2005, IEEE TVCG). Not by ray parity on a
   mesh that is not watertight.
3. **Open bodies:** the headless `SKM_..._BodyMesh` is open at the neck; w is fractional near the opening (C05: 0.466 inside, near
   the hole). Use the FullBody (body + head, measured identical weights on all 32,334 BodyMesh vertices; memory
   native-body-canonical-for-fit) or declare the body open and refuse signs within a band of the opening.
4. **Penetration DEPTH for a limb region** (the pose solver's instrument): from the posed bone axis, cast to each skin vertex; the
   first armour hit before the vertex gives depth = |vertex - origin| - hit (`pose_clearance.py:80-92`). Topology-independent for the
   piece (works on single-sided shells).
5. **Gap / hug:** the gap of a piece is measured on its INNERMOST layer: a piece point counts only if the segment from it to the
   skin crosses no other piece surface (a clear line through the piece's own BVH) — a medallion on a strap on a plate is not the gap
   (GENERATED-EQUIPMENT §7c). Report median and p90 per material class (metal / leather / cloth).
6. **Hideable:** render the region's skin with the body removed; per standard view the share of the region's pixels the armour
   still covers (`enclosed_pct`); enclosed from every view (>= 98 %) the region is `hideable` and skin through armour there is not a
   defect — the body mesh may be masked (GENERATED-EQUIPMENT §7l).

## C. Invariants

- **INV-15.1** A sign is never inferred from one face normal at a non-face-interior nearest point.
- **INV-15.2** The body for penetration is closed, or declared open with the refusal band.
- **INV-15.3** Gap is measured on the innermost layer; inner-facing alternative kept only as a diagnostic.
- **INV-15.4** Penetration that a hideable region would show nowhere is reported, not fixed by deforming metal.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-23 | The staged body was inside out (0 of 1996 torso normals outward): the stage reversed the fit's triangles | refuse an inward body; check orientation by winding | GENERATED-EQUIPMENT §7c |
| 2026-10-06 | MetaTailor MT-1 left 46 glove vertices inside the hand (min -23.1 mm, mostly the palm) and pushed a penetrating greave apex to +6 mm. Its clearance is a collision push, not a per-material target | clearance per material kind, measured by signed distance after the fit (GMT.3) | `goldens/metatailor` |
| 2026-09-23 | The arm's rays claimed the chest's flank and dragged it out | mutual nearest (the claim holds only if that skin is the hit's nearest) | §7c |
| 2026-09-23 | The fit judged a medallion on a strap on a plate against the skin | innermost layer only | §7c |
| 2026-09-26 | A helmet at 1.0 cm clearance: the crown came through the flat dome panels BETWEEN vertices — no vertex test saw it; a render with and without the body did | vertex tests miss face-interior crossings; use surface crossings and renders | §7k |

## E. Golden tests (`goldens/C05_clearance`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G15.1 sphere | `sphere.obj` (r 0.2, 48x24) + 60 query points | signed distance within 2·sag (0.85 mm max measured); sign exact beyond that | — |
| G15.2 spike | `spike.obj` needle + `spike_point` beside the apex | outside (w = 0) | an apex face's normal says inside (signs -1 and +1 among the apex faces) |
| G15.3 open body | `open_sphere.obj` | w fractional (0.466) -> refuse or declare | a parity ray test returns a confident sign |
| G15.4 face-interior crossing | a 2x2 cm flat panel passing through a sphere between its vertices (to build) | surface crossings > 0 although every panel vertex is outside | vertex-inside counting reads 0 |

## F. Implementation gap (Lampway `b806617f`)

- LT `features/clearance.py:86-89`, `features/rig.py:264-268` and `features/validate_pose.py:97-99` all sign by the nearest face's
  normal (G15.2 falsifier).
- No winding-number sign, no open-body refusal, no innermost-layer gap, no hideable measure in Lampway (the last two exist in
  Titan's fit_measure recipe only, which is uncommitted-edit state in this worktree).

## G. Agent-facing tool contract — `lampway_garment_clearance`

```json
{"piece": "object", "body": "fit_body package dir | skinned body object", "armature": "name", "pose_set": "rest|closest|<poses file>",
 "classes": {"part": "metal|leather|cloth"}, "clearance_target_m": 0.015, "measure": ["signed", "depth_axis", "gap_innermost", "hideable"]}
```
Refusals: body open without `body_open_band_m`; body inside out (winding of a far exterior point != 0); piece more than 0.5 m from
the body (place first). Receipt per pose `{min_signed_m, inside_vertices, surface_crossings, depth_axis: {>10mm count, worst_mm},
gap: {class: {p50_m, p90_m}}, hideable: {region: {enclosed_pct_by_view, hideable}}}`.

## H. Decisions owed by the captain

Clearance targets per class (15 mm exists only for openings; the cuirass judge used gap bars 1.0 leather / 1.5 metal cm, §7h).
