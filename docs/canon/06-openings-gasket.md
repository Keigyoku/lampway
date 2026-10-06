<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 06 — Openings: keep, gasket or delete a cap, cut from the posed body

Status: **DRAFT** — the decision rule and the cut are canonical; the collar depth (flange length) and lip are the captain's
numbers and unruled (BUILD_ORDER decision 1). Implemented by: LT `features/opening.py` (built, synthetic tests only);
ancestor shelf `partseg/delete_caps.py` (hand-typed footprint).

## A. Problem

A generator often closes a limb, neck or waist opening with a cap (neck bowl, waist fan, arm dome). Each opening gets a typed
decision recorded append-only: **keep** (hidden or intended), **gasket** (open it to the body), **delete** (open hem). A gasket
"make a hole, base on the MetaHuman base body, and manifold it" (the captain, 2026-10-05), read on 2026-10-05 as "an engine
exhaust or intake manifold hole": a formed tubular collar with a rolled lip, not a raw cut (memory fit-and-decisions-rulings-1005).
Inputs: the piece (rebuilt mesh with `orig_poly`, `owner_poly`), the POSED body (canon 08 `pose.json`), the opening's axis
and plane, `clearance_mm` (default 15, PIECE_PIPELINE), `flange_mm` (no default), `lip_mm`. Output: a new mesh `<piece>_openings`,
`orig_poly = -1` for new faces, the decision rows, a manifold report. Frame: body frame (canon 01).

## B. Method

1. **Detect.** For each site of the kind's table (chest: neck, two arms, waist; helmet: neck; waist: top, hem; boots: shaft;
   gauntlets: cuff, fingers), the site axis is the POSED body's bone line through the opening (not a typed axis). A cap is a
   connected set of faces within 35 deg of that axis lying beyond the opening plane, found by rays along the axis through the
   body's own section footprint (the `delete_caps.py:35-39` ray test with the footprint derived, not typed).
2. **Section.** Slice the posed body with the cap plane; take the closed loop that CONTAINS the bone's axis point (never "the
   largest loop": at an arm plane the torso's loop is larger).
3. **Cutter.** Offset the section outward by `clearance_mm` in the plane (mitre-limited); refuse self-intersection.
4. **Gasket.** Delete the cap faces; bridge the cap's boundary loop to the cutter loop with a planar annulus; extrude the cutter
   loop `flange_mm` into the piece (the collar wall); roll the far rim outward over `lip_mm` (a half circle of `lip_rings`).
   Exactly one new boundary loop per gasket (the lip's free rim); no non-manifold edge; winding consistent with the neighbours.
5. **Delete.** Remove the cap faces, keep UVs; the rim stays open.
6. **Keep.** No geometry change (mesh sha equal).
7. New faces are patch faces (`orig_poly = -1`) so the patch-UV puzzle, masks and PBR merge apply unchanged (canon 13).
8. Metal: a cut removes faces and records their original ids (an "approved cut"); no weight or blend operation is allowed.

## C. Invariants

- **INV-06.1** Runs on the posed body, never the rest pose.
- **INV-06.2** A geometry step: it discards a texture made before it (re-run texturing).
- **INV-06.3** The decision log is append-only; the latest answer per opening id wins; a repeated identical answer appends nothing.
- **INV-06.4** The cutter must fit inside the old cap boundary; if the body section plus clearance does not fit, the piece is
  too small there: refuse and ask for a reroll, never scale the piece locally.

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-10-04 | Chest `pose_uv1` (cap present): neck penetration fraction over 2 mm 0.2538, worst 79.4 mm; with the cap deleted 0.0 / 0.0 | caps are real penetration sources; detect them | `<shelf-scratch>/proportion/pose_uv1*/pose_clearance.json` |
| 2026-09-26 | Greave lid read as inner wall, cage pushed the top out 3 cm (the "collar") | a cap is a defect to open, not geometry to conform around | GENERATED-EQUIPMENT §7j |
| 2026-10-06 | MetaTailor MT-4 (synthetic lidded greave, Pants): no opening was detected. The lid apex, 41 mm inside the leg, was pushed out to +6 mm and 14 tube vertices moved; the closed lid survived as a skewed cone (apex 55.6 -> 11.9 mm from the wall) | a fitter that treats a cap as collision keeps the cap; detect and open it first (GMT.6) | `goldens/metatailor` MT-4 |
| 2026-10-05 | Boots1 v1: closed shaft bowl at z 0.38–0.42 of the 1.0 mesh, a second diagonal partition at the ankle | detect per site; more than one cap per piece | `seed_audit/Boots1/audit.json` (cited in `<specs>/shelf/fit_place.md`) |

## E. Golden tests (`goldens/C12_gasket`)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G06.1 detect | `piece_capped.obj` (32-face fan cap at z 1.60), `neck.obj` | 1 capped site, axis +Z, plane z 1.60 | a mesh without the cap: 0 sites |
| G06.2 gasket at 15 mm | + `flange_mm` given | rim radius 0.070 ± 1.5 mm; boundary loops 1 -> 2; non-manifold 0; bad winding 0 | `clearance_mm=0`: rim at 0.055 fails the radius check |
| G06.3 keep | answer keep | mesh sha unchanged; one decision row | — |
| G06.4 too small | neck radius 0.08 | REFUSED: section + clearance does not fit | a tool that scales the cap out |
| G06.5 no flange | gasket without `flange_mm` | `needs_decision` with three rendered depths | a silent default depth |

## F. Implementation gap (LT `features/opening.py`)

1. **Detection only at the piece's extreme along a typed axis** (:77-96: caps within 2 % of the min/max extent along `axis`);
   arm openings on a chest's flank are not at an extreme and the axis is the caller's, not the posed bone's.
2. **The largest section loop is taken** (:127-133); at an arm plane the torso loop wins. Canon: the loop containing the bone's
   axis point.
3. **The cutter is projected by rays from the cap boundary's centroid** (:236-246), which assumes a star-shaped boundary; a
   concave cap boundary refuses or mis-projects [UNVERIFIED on real caps].
4. `propose` returns `ambiguous` for every opening (:361-362): no measured rule (visibility, body-through depth) is applied.
5. Texture-discard gate keys on the object property `lw_studio_textured` only (:410), not on an image texture in the material.
6. `variants` renders one view (`Left`, :389).

## G. Agent-facing tool contract — `lampway_fit_openings`

```json
{"stage": "detect|propose|rule|variants|apply|check", "object": "piece", "piece": "id", "kind": "chest|helmet|waist|boots|gauntlets",
 "body": "fit_body package dir", "pose": "pose.json (REQUIRED for variants/apply)", "answers": {"OP000": "keep|gasket|delete"},
 "captain_words": "verbatim", "clearance_mm": 15, "flange_mm": "REQUIRED for gasket (no default)", "lip_mm": 4,
 "texture_discard_ack": false}
```
Refusals: no pose; gasket without `flange_mm` (returns `needs_decision` + `variants` hint); an answer outside the three words;
an unknown id; an undecided opening at `apply`; a texture present without the ack; cutter does not fit; offset self-intersects.
Receipt: `openings.json` per opening `{answer, removed_orig_ids, rim_radius_mm, flange_faces, min_clearance_mm, manifold}` plus
`decisions.jsonl` rows `{question: opening_decision, descriptor, descriptor_sha256, answer, decider, captain_words}`.

## H. Decisions owed by the captain

1. Collar depth (flange length) — render variants (10 / 20 / 35 mm proposed) and pick.
2. Lip radius and whether the collar is its own UV island or joins the bordering island.
3. Default answer per site (proposal rules are placeholders until ruled).
