<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 09 — Placement and registration: one uniform scale, centred by enclosure of the inner wall

Status: **CANONICAL for the rule; DRAFT for the boots' scale anchor** (unruled). Implemented by: shelf
`proportion/place_piece.py` (chest; LT `scripts/proportion/place_piece.py`, byte-identical), LT `pipeline/fit_place.py`
(all five kinds), LT `pipeline/sections.py`, shelf grt `enclose.py`, Titan `equipment_match.py`, `equipment_reference.py`.

## A. Problem

A genned piece arrives at the generator's scale (~0.98 m longest side) and frame (canon 01). Put it on the body: one uniform
scale (per piece; per side for pairs — open), a rotation that lays its axis on its bone, and a translation that centres it on the
body segment it covers. Output: `placed.npz` + meta `{kind, scale, translation, turn_deg, norm_lo, norm_hi, anchor, sides}` that maps
every later point back to the piece's own frame (canon 08 blockers, region regeneration boxes).

## B. Method

1. **Frame.** `turn_deg` to the body frame (input, recorded). Forward is LEVEL and square to the hips (`forward_from: {across:
   [thigh_l, thigh_r], toward: foot_l -> ball_l}`), never foot->ball alone (6.5 deg toe-out, GENERATED-EQUIPMENT §7e).
2. **Axis.** Limb pieces lay their principal axis along their bone (head -> continuation child, canon 01 C.1); orientation of the
   axis is a measured fact of the piece (gauntlets stand cuff-up in V3/Tripo; the cuff end is the upper end — `piece_ratios.py`
   comment and the Lampway refusal when the finger end is up). Footwear lies LEVEL along the foot's heading. A residual angle
   between the piece axis and the bone is corrected rigidly (canon 03 step 5), never left (LT refuses > 25 deg and leaves < 25 deg).
3. **Scale — one number, from a landmark span** + the wear clearance C (15 mm; chest uses +40 mm on width, i.e. C = 20 mm):

   | Kind | Piece measure | Body measure | Source |
   |---|---|---|---|
   | chest | median section width just below the axilla (W crosses 0.60 of normalised width) | chest width just below the axilla (W crosses 0.42 m) + 40 mm, axilla heights aligned | `place_piece.py:12-21` |
   | helmet | shell width at its widest level (crest excluded) | head width at its widest level above `neck_02` + 2C | `fit_place.py:54-66` |
   | waist | band width (top 6 % of the piece) | waist width at `spine_01` + 3 cm (arms excluded) + 2C | `fit_place.py:69-85` |
   | gauntlets | bracer major axis at 35 % of the length (cuff up) | forearm major at mid-forearm + 2C | `fit_place.py:122-168` |
   | boots | **unruled**: shaft width at 60 % height / knee height / foot length | same at the leg | `fit_place.py:88-119`; Boots1 audit: height anchor s 0.52 leaves the foot 8 % short, foot anchor s 0.624 puts the top 118 mm above the knee |

   A girth-matched scale is an alternative when a span-matched scale lets the torso through (cuirass: collar-to-hem span 0.98 vs
   girth 1.29 at 1.5 cm median column clearance; GENERATED-EQUIPMENT §7k): the canon records which anchor drove the scale.
4. **Translation — enclosure of the INNER wall.** At several heights over the piece's band, slice body and piece; from the body
   section's centre cast rays (±side, ±front) and take the FIRST piece hit — the inner wall; translate so the inner wall's centre
   equals the body section's centre; median over the slices. Iterate twice from the new centre (`place_piece.py:23-26`). A section
   centre is the fitted first harmonic of the ring's radii (`r(θ) ≈ r0 + a cos θ + b sin θ` -> offset (a, b)); the plain mean of the
   ring's points finds about half the offset (GENERATED-EQUIPMENT §7k). Helmet: the skull without the crest.
5. **Registration between BODIES** (an example to the MetaHuman): Horn similarity over shared joints, joints whose rigs disagree
   excluded (spine_03, hands: 17 / 13 cm off), per-joint residuals reported (GENERATED-EQUIPMENT §7h). **Never surface ICP of an
   armoured body to a bare one** (memory armour-registration-bias: 3–5 cm forward bias, 2–6 cm back at the head).
6. **Pairs.** Split at x = 0 (refuse when a side has < 50 triangles: "centre the pair on x = 0 or run sides=l and r").
7. **Source-part check first.** Before placing, each piece is compared with its source part by part (one similarity per rigid
   group, residual ~0); a piece moved in parts by an earlier experiment is refused (memory gauntlet-glove-detached).

## C. Invariants

- **INV-09.1** One uniform scale (per piece / per pair side); the singular values of the applied linear map are equal.
- **INV-09.2** Never a per-region push to place (canon 03 INV-03.3).
- **INV-09.3** Enclosure by the inner wall, not by all vertices, not by the centroid, not by surface ICP.
- **INV-09.4** Every constant is relative to the body's joints, never an absolute height.
- **INV-09.5** The meta maps any placed point back to the piece frame exactly (round trip < 1e-9 m).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-28 | Trimmed-ICP surface registration of the fitted warrior sat 3–5 cm forward of the body, 2–6 cm back at the head; every piece registered onto it inherited it (back plates buried) | enclosure | memory armour-registration-bias |
| 2026-09-24 | A coarse target biased symmetric ICP to its sample lattice; a round tube converged 1–2 cm off | ICP from every reference point to the dense piece if ICP at all | GENERATED-EQUIPMENT §7h |
| 2026-09-23 | The placement search slid a symmetric chest 2 cm sideways; one flank floated ~10 cm | lock the sideways offset of a symmetric piece | §7c |
| 2026-09-25 | Pauldrons skewed a bounding-box centre | centre on the chest slice's front/back first hits | `place_piece.py:3-4` |
| 2026-10-06 | MetaTailor's Accessory route moved a shoulder plate placed 2 cm off the deltoid to its default parent `hand_r`, even with Keep Source Dimensions on. Its cloth route kept plate and skirt placements exactly (0.00 mm) | placement is ours and is kept; an attach step never re-places a placed piece (GMT.8) | `goldens/metatailor` MT-2, MT-3 |
| 2026-10-05 | Gauntlets "first scored 0.28: axis flipped ('wider end', then 'rounder end' both wrong)"; cuff = upper end | orientation is measured, refused when wrong | shelf `piece_ratios.py:24-26` |

## E. Golden tests (`goldens/C06_enclosure`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G09.1 inner-wall enclosure | elliptic body; piece inner wall = body + 15 mm, front wall 30 mm thick, back 5 mm; displaced (0.012, 0.040) m | translation (-0.012, -0.040) within 1 mm | all-vertex extents midpoint: 12.5 mm error in y (= (tf - tb)/2) |
| G09.2 chest regression | `place_piece.build` on the recorded chest inputs | byte-identical to the shelf output (1e-9) | — |
| G09.3 self-test | the body's own region offset 15 mm | scale 1.000 ± 0.02, translation < 3 mm | — |
| G09.4 uniform | any kind | singular values of the linear map equal within 1e-6 | per-axis scaling |
| G09.6 asymmetric pair | `tests/lampway_tools/test_canon_pair_scale.py`, actual tubes with one side uniformly1.5× larger | measured scales differ >0.1; triangle/vertex identities retained; inverse error <1e-9m; native scene matches output <1e-6m | unconditional averaging cannot express independent scales |
| G09.5 boots | no `scale_anchor` | REFUSED naming the three anchors | a default anchor |

## F. Implementation gap (Lampway `b806617f`)

1. LT `pipeline/sections.py:36-39` `centre` (percentile extents of ALL section points) drives helmet/waist/boots placement
   (`fit_place.py:64,82,111`); the gauntlet uses the mean of the section points (`fit_place.py:164`). Both are all-vertex measures
   (G09.1 falsifier). The chest path (`place_piece.py`) uses first hits from the centre — the inner wall — and is correct.
2. Rotation not applied for gauntlets (0–25 deg left; `fit_place.py:161-168`, `_similarity` :50-51).
3. Absolute constants: waist torso filter `|x| < 0.27` (`fit_place.py:71`), boots foot `z < 0.04` (`:98`), gauntlet arm `|x| > 0.25`
   (`:132`).
4. Pairs: explicit `pair_scale_group=common|per_side` paths are implemented. Per-side placement records vertex ids and one proper similarity per separated side, with an exact inverse; cross-centre triangles refuse. The native scene API validates all groups before writing any vertex. Omitted mode preserves the historical calculation and records `pair_scale_needs_decision=true`; D4 has no canonical default.
5. No source-part check before placement.

## G. Agent-facing tool contract — `lampway_fit_place`

```json
{"kind": "chest|helmet|waist|boots|gauntlets", "piece": "piece.npz", "body": "fit_body package dir", "turn": -90,
 "clear_mm": 15, "pair_scale_group": "common|per_side (explicit; default unruled)", "scale_anchor": "width|height|foot|girth (boots: REQUIRED)", "sides": "both|l|r", "out": "placed.npz"}
```
Refusals: boots without an anchor; a side with < 50 triangles; axis more than 25 deg off its bone without `rotate: true`; a gauntlet
whose finger end is up; a piece failing the source-part check; body package without joints. Receipt: meta above +
`{anchor, scale, inner_wall_shift_m, slices, axis_error_deg, round_trip_m}`.

## H. Decisions owed by the captain

1. The boots' scale anchor.
2. Does a pair share one scale, or each side its own (the reference's shins differ: 0.887 vs 0.853)?
3. Is C = 15 mm the wear clearance for every kind (the chest's legacy is 20 mm)?
