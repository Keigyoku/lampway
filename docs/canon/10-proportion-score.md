<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 10 — Proportion scoring against the MetaHuman (and the silhouette instruments beside it)

Status: **CANONICAL for the chest** (auditor-validated 2026-10-04); **DRAFT for helmet, waist, boots, gauntlets** (new 2026-10-05,
self-tested, auditor falsification owed). Implemented by: shelf `proportion/proportion_ratios.py` (PRIMARY, chest) and
`piece_ratios.py` (other kinds), ported to LT `scripts/proportion/`; `proportion_fit.py` (overlay only, FRAGILE); LT
`features/silhouette.py`, `pipeline/plates.py` (fidelity); astra/claude-2 `spike/measure.py` (the reconstruction rubric).

## A. Problem

Rank seeds of one piece by how well their shape fits the MetaHuman body BEFORE any repair, because "a mesh can be repaired,
proportions are in the seed generation" (memory proportions-trump-mesh-defects, 2026-10-04). Inputs: `body.npz` (vertices,
triangles, joint heads; the FullBody GLB for geometry and joints only), `piece.npz` + `turn_deg`, kind, clearance C (15 mm).
Output: per seed the ratios, the body's ratios, deviations (%), `rms_logdev` (0 = the body's proportions plus C), info, ranking,
and `validated` (false until an independent landmark method reproduces the order).

## B. Method

1. **Scale-free:** the piece is normalised (z 0..1, centred) — absolute size is meaningless (canon 01).
2. **Sections:** per height, slice the triangles; from the section's front/back centre cast 36 rays (10 deg); the FIRST hits give
   W (left + right, medians of 3 azimuths about ±X) and D (front + back, medians of 5 azimuths about ±Y)
   (`proportion_ratios.py:21-59`). Limb kinds slice perpendicular to the piece's principal axis and use roll-free PCA extents of
   the section outline (`piece_ratios.py:35-52`).
3. **Landmarks and ratios per kind:**
   - chest: axilla (W first exceeds a threshold above the waist), chest window just below it, neck band, collar rim (W falls
     halfway from chest to neck width), arm span just above the axilla; ratios D/W, neck W/chest W, axilla-to-collar/chest W,
     arm span/chest W. `tight_front` flags chest depth excess < 20 mm (the bare-body depth comparison lets a too-shallow piece
     score well).
   - helmet: D/W at the widest level; H/W with H = shell height to the crest's base (first level narrower than 45 % of max, scanning UP).
   - waist: band D/W vs waist at `spine_01` + 3 cm; hip flare vs body hip/waist; report hem fraction waist->knee.
   - boots: shaft D/W at 60 % height; foot/shaft; height/foot — per side, the worse side counts.
   - gauntlets: bracer minor/major at 35 %; hand/bracer; length/bracer (cuff up; wrist = where the section first flattens).
4. **Score** = RMS of log(piece ratio / body ratio) over the kind's ratios; 0 = the body's proportions plus C.
5. **Self-test** (the falsifier the method owes): the MetaHuman's own region offset 15 mm along its normals must score ~0 —
   measured helmet 0.032, waist 0.022, boots 0.030, gauntlets 0.055 (`piece_ratios.py:23-26`).
6. **Silhouette/fidelity instruments are a different question** (appearance vs V3 plates) and must preserve aspect: compare masks
   in ONE frame at one scale (the piece rendered with the plate's framing), never each mask cropped to its own box and resized to a
   square (golden C11: a 2:1 rectangle vs a square reads IoU 1.0 under crop-and-stretch, 0.5 correctly). Plates are keyed by the
   colour of their own border ring (median of an 8 px ring; tolerance from its p99), never a literal #FF00FF (measured ring
   ≈ (249, 3, 251), corners to (237, 11, 240); `<astra-shelf>/from-claude-2/ENVIRONMENT-FINDINGS.md`).

## C. Invariants

- **INV-10.1** Proportion first, defects second, in every seed pick and every auditor brief.
- **INV-10.2** The ranking is advice until `validated: true` (an independent landmark method reproduces at least the top and
  bottom of the order); "proportions did not separate any piece's 4 seeds — the audit did" (`piece_ratios.py:22`).
- **INV-10.3** `proportion_fit.py` (one scale + translation by trimmed clearance variance) is an overlay renderer only: single
  switches flip its winner (`proportion_fit.py:1-4`, audit 2026-10-04).
- **INV-10.4** Known biases are part of the output: helmet D includes a crest swept down the back (+~39 % D/W on every Helmet1
  seed), waist scores the design flare, boots score knee height and the lion relief, gauntlets cannot see collapsed or slotted plates.
- **INV-10.5** Top/bottom silhouette IoU rewards wrong crests; face count says nothing about quality (`<astra-shelf>/from-claude-2/REPORT.md` §3).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-04 | `proportion_fit` ranking flipped by single switches (A-pose arm rays, neck rays, 20 mm target, the cape's back sector, free vertical placement, first-hit inner lining), each worth up to 10 mm against a 3.7 mm spread | landmark ratios at axilla-aligned placement are primary | `proportion_fit.py:1-4` |
| 2026-10-04 | Every quad chest seed had a collar 30–37 % too high | proportions are in the seed: reroll | memory proportions-trump-mesh-defects |
| 2026-10-05 | Gauntlet axis flipped twice before "cuff = upper end"; wrist detector sat mid-forearm (+47 % hand) | orientation measured and refused; wrist = flattening | `piece_ratios.py:24-26`, `:132-139` |
| 2026-09-21 | The helmet rubric's `measure.py` crops and resizes each silhouette to the max width/height (aspect not preserved); its crest "width" is column occupancy (83 px row width vs 150 px column height on the selected mesh) | aspect-preserving masks; name what a metric measures | `<astra-shelf>/REPORT-AUTHORED-HELMET.md` "Instrument observation" |
| 2026-09-20 | Plate background not #FF00FF; a literal key left fringe opaque at the frame edges | key from the border ring | `<astra-shelf>/from-claude-2/ENVIRONMENT-FINDINGS.md` |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G10.1 section extents | `goldens/C11_proportion` ellipse levels + C | W = 2(a+C), D = 2(b+C) to 1e-6 | an all-points extent on a cut with an inner lining |
| G10.2 scale-free | piece x 1.37 | ratio deviations 0 | a ratio using an absolute length |
| G10.3 sensitivity | depth x 1.10 | D/W dev +10.0 % exactly | — |
| G10.4 aspect | C11 rectangle vs square masks | IoU 0.5 | crop-and-stretch: 1.0 |
| G10.6 native cardinal facing | `test_canon_normalize_facing.py`, L-profile Front on a rectangular alpha canvas, raw +90° | measured -90° applied; best IoU >0.99; best-second exceeds explicit margin; +X raw front recorded | symmetric cube ties and refuses without geometry/ID changes |
| G10.5 body self-test | the MetaHuman region offset 15 mm (built from the body GLB by the implementer; not committed: private-free but large) | helmet < 0.04, waist < 0.03, boots < 0.04, gauntlets < 0.06 | a scorer whose self-test exceeds 0.06 is not shipped |

## F. Implementation gap

1. `piece_ratios` kinds are unfalsified (`validated: false`), as they should be; the auditor's independent method is owed.
2. The shared silhouette loader supports native dimensions and keys non-alpha plates from the median 8px border ring with its p99 distance tolerance. Normalization uses native dimensions followed by the common aspect-preserving fit. Existing silhouette_compare calls retain their explicit square-size interface.
3. Lampway's `CUFF_UP_MARGIN` comment (`scripts/proportion/piece_ratios.py` header) says real seeds read 0.55–0.6 right-way-up
   while the in-code comment says the cuff end measured 0.90–0.95: one of them is stale [UNVERIFIED which].

## G. Agent-facing tool contract — `lampway_proportion_score`

```json
{"kind": "chest|helmet|waist|boots|gauntlets", "body": "body.npz (with joints)", "pieces": ["name=piece.npz:turn_deg"],
 "clear_mm": 15, "out": "scores.json"}
```
Refusals: body without joints; a piece file missing (`mesh_to_npz` hint); a pair side with < 50 triangles; a gauntlet finger-end up;
`clear_mm` outside 0..40. Receipt: the shelf JSON shape `{kind, clearance_mm, method, validated, ranking, pieces: {name: {ratios,
body, dev_pct, rms_logdev, info}}, known_biases}`; `validated` is set only by an attached auditor report hash.

## H. Decisions owed by the captain

Who falsifies each non-chest kind, and when `validated` may flip (PIECE_PIPELINE known gap).
