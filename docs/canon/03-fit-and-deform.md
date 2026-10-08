<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 03 — Fit and deform: one genned armour piece onto the MetaHuman

Status: **CANONICAL for the order, the laws and the rigid path; DRAFT for soft-part deformation** (no soft-part deformer has
passed the captain's eye on a real piece; every one tried so far is listed in D).
Implemented by (today, in pieces): LT `pipeline/fit_place.py`, `posing.py`, `features/opening.py`, `features/fit_bind.py`,
`pipeline/validate.py` + `features/validate_pose.py`, `features/fit_export.py`, `pipeline/fit_glove.py`; Titan
`tools/equipment_fitpose.py`, `equipment_cage.py`, `equipment_match.py`, `weight_profile.py`, `hand_pose.py`,
`armour_validate.py`; shelf `proportion/place_piece.py`, `pose_clearance.py`. **No single tool runs the order below.**

This page is the spine; each step's maths lives in its own canon (02 similarity, 04 bind-and-return, 05 validation,
06 openings, 07 weights, 08 pose, 09 placement, 10 proportion, 15 clearance).

## A. Problem

**Inputs (the captain's three, 2026-09-29):** (1) a fitted example — the whole armour on a humanoid, rigged from ITS OWN mesh;
(2) the MetaHuman base — the project-native `/Game/MetaHumans/NewMetaHumanCharacter_FullBody` (body + head, 342 bones, up to
12 influences per vertex), packaged once (`lampway_fit_body`); (3) the individually genned pieces, segmented into parts, each
part carrying a material ROLE (metal | leather | cloth | embroidery) from the captain or the recipe.

**Output:** each piece in the body frame (canon 01), skinned to the native skeleton in the native REST pose, with its own bind
equal to the native reference bone by bone, plus receipts that a number can stand on (canon 05). "Positions come out of it for
free" (memory three-input-fit-pipeline): placement, scale and pose are consequences of ref-posing, not hand guesses.

## B. Method — the canonical order (each arrow is a refusal if skipped)

```
0 body package ─► 1 intake + roles ─► 2 proportion gate ─► 3 match by eye in Blender ─► 4 place by enclosure
   ─► 5 rigid pose correction per segment ─► 6 pose the body to the piece ─► 7 openings on the posed body
   ─► 8 soft-part conform (cloth/leather only) ─► 9 bind at the fit pose, return to rest ─► 10 weights by position
   ─► 11 validate (poses + controls) ─► 12 export (Z/X bone axes, cm) ─► 13 motion acceptance filmed in UE
```

The native body may contain authored facial openings. Body-package topology is
measured using analytical position identities at 1e-5 m, reporting raw and welded
boundary/non-manifold counts. This does not weld or publish the authored geometry,
and native weight vertex ids stay unchanged. Generalized winding (canon 15) tests
head inclusion on the original triangles regardless of watertightness; a measured
head winding >0.5 permits native openings at intake. `closed=false` remains true
in the receipt, rather than being mislabeled. Headless/unverified packages still
refuse. Signed measurements near openings retain canon 15's declared-band rule.

1. **Intake.** Turn to the body frame (`turn_deg` recorded), keep every salvageable part (memory salvage-parts-piece-by-piece),
   record each part's role. Material comes from the captain's word or the recipe, never from a render's colour (memory
   gauntlet-upper-arm-is-cloth). Pieces are generated per item; a paired piece (gauntlets, boots) from front+back views only
   (memory paired-pieces-front-back-only).
2. **Proportion gate.** Score against the MetaHuman before anything else (canon 10). "Best proportions trump bad meshes"
   (memory proportions-trump-mesh-defects): a seed that fails proportion is rerolled, not fitted.
3. **Match by eye.** Place, scale and shape the piece on the body in Blender; render front/side/back after each change beside the
   V3 turnarounds (THE appearance authority, memory v3-turnarounds-are-the-appearance-source); the captain reviews the render
   before fit (memory blender-match-before-fit). Numbers never overrule a distorted render.
4. **Place by enclosure** with ONE uniform scale per piece (per rigid group): canon 09.
5. **Rigid pose correction per segment.** Measure each segment's axis against its bone — shin vs calf, boot vs foot, bracer vs
   forearm, glove vs hand, cuff vs upper arm — and correct with a RIGID turn about the joint (memory pose-not-push: the greaves
   were 3–4 deg off the calf, the gauntlets 14–23 deg off the forearm). Bone directions per canon 01 C.1.
6. **Pose the body to the piece** (canon 08): the body's closest pose (arm abduction/swing, neck:chest and back:hips pitch,
   wrist and fingers for gloves). Only clipping that survives this pose is a mesh defect; report A-pose and posed numbers
   (memory pose-body-to-the-piece).
7. **Openings** (canon 06): keep | gasket | delete per capped opening, cut from the POSED body's section, before any texture.
8. **Soft-part conform** — cloth and leather only, rest pose or fit pose, judged by eye first. Metal parts and ornaments are
   carried by ONE similarity per part (canon 02); ornaments ride the deformed shell unchanged (shell vs ornament segmentation
   first; GENERATED-EQUIPMENT §7j item 4). Where the body pokes through SOLID armour that hides it from every view, the canon
   answer is to hide the body there (`hideable`: enclosed in >= 98 % of every view, GENERATED-EQUIPMENT §7l), not to bend the
   armour (memory pose-not-push).
9. **Bind at the fit pose, return to rest** (canon 04): the exact inverse of the blended transform, never the blend of inverses.
10. **Weights by position** (canon 07): restrict / dress / rigid / plate per the type's profile; one shell → positional weights;
    seams cannot open.
11. **Validate** (canon 05) in authored, closest and captured poses with the positive controls; verdicts never stronger than the
    declared limits.
12. **Export** with the measured FBX settings and a bone-frame read-back (canon 01 C.3); textures re-made if any geometry step
    ran after them (texturing comes last, memory tripo-studio-invariants).
13. **Motion acceptance** in UE: poses + arm raise, reach, elbow bend, twist, squat, knee bend, walk, filmed (memory
    fitting-workflow-revised). Final look is judged in engine (memory final-look-judged-in-engine).

### Soft-part conform: the measured candidates (DRAFT)

| Engine | Maths | Status on real pieces | Source |
|---|---|---|---|
| Per-piece closed **cage** (sleeve round the slot axis, `rows x columns` cells, inner/outer walls from the piece's own radii, shifted per cell to body + clearance, Gaussian-smoothed, bounded) + Blender **Mesh Deform** (harmonic coordinates, Joshi et al. 2007, "Harmonic Coordinates for Character Articulation", SIGGRAPH) | cage vertices move; piece = harmonic interpolation | cuirass: metal gap 1.12 / 2.02 cm (p50/p90), no edge past 2x, ornaments intact (09-25); **rejected on sight on the boot** (68 plates moved, seams opened, 09-26); collar artefact from a lidded top until the inner wall read only across-axis normals | Titan `equipment_cage.py`; GENERATED-EQUIPMENT §7j |
| **Wrap** (mutual-nearest skin claims, Gaussian field, guard push) | per-vertex displacement field | 287 edges past 2x on the cuirass vs the cage's 0; rim peeled until `guard_spread`; superseded by the cage | GENERATED-EQUIPMENT §7c |
| **Outward radial push** (`equipment_cage.shift_field`, outward only) | per-vertex push | **REFUSED by the captain**: "pretty much every spot got worse and exponentially more distorted" (2026-09-28) | memory pose-not-push |
| Surface Deform to a body cage | barycentric binding | sheared up to 45x | GENERATED-EQUIPMENT §7c |
| **ARAP with clearance constraints** (Sorkine & Alexa 2007, "As-Rigid-As-Possible Surface Modeling", SGP) | local rotations, global Laplace solve; handles = clearance targets | **not yet measured** — the canonical next candidate for cloth/leather: keeps local shape (what the eye judges) where a smooth field shears | proposal |
| **Collision-aware relaxation** (incremental potential contact, Li et al. 2020, "Incremental Potential Contact", SIGGRAPH; garment self-collision, Santesteban et al. 2021, CVPR) | barrier energy, intersection-free | not measured; the Chaos Cloth path in UE already does this for the cloak | reference |

Canon rule for the draft: **a soft-part deformer is admitted per piece only after (a) its receipt shows no metal vertex moved
non-rigidly, (b) seams per the source ledger stay within the seam limit, (c) a render beside V3 passes the captain's eye.**

## C. Invariants

- **INV-03.1 The body is fixed and native.** Fit to the stock MetaHuman FullBody; never reshape the body to suit a set (the
  GreekWarriorBody loop is retired, 2026-09-25); never fit weights against a GLB-imported body (UE's glTF parser reads only
  JOINTS_0/WEIGHTS_0) (memories fitting-workflow-revised, native-body-canonical-for-fit).
- **INV-03.2 Metal moves by ONE similarity per part** (or per region after an approved cut recorded as original vertex ids).
  Pteruges (waist strips) are metal; finger caps and the bracer are metal; the gauntlet above the bracer is cloth
  (memories metal-never-blended, chest-parts-motion-rulings, gauntlet-upper-arm-is-cloth).
- **INV-03.3 Pose, not push.** A pose error is corrected rigidly per segment; a deformation never hides it.
- **INV-03.4 Only clipping that survives the closest pose is a defect** (canon 08).
- **INV-03.5 Match by eye before fit; the captain reviews the render.**
- **INV-03.6 The oracle body must match.** Any model or rule trained or tuned on the fitted example uses the body UNDER the
  example's armour, never the stock body rigidly aligned (memory oracle-body-must-match: the stock-aligned oracle taught the
  warrior's wider stance and small head: greaves pushed 2–3 cm out, helmet thrown 26 deg back at 0.89 size).
- **INV-03.7 The example is rigged from its own mesh.** Its joints come from its own geometry (multi-view joints canon 11, GRT /
  MB UE5 Rig Creator), never fitted onto the MetaHuman's joints (memory three-input-fit-pipeline).
- **INV-03.8 A genned piece is one shell cut into parts:** weights by position, seams judged against the source ledger
  (canon 07, 05).
- **INV-03.9 A gauntlet has two anchors:** the bracer stays on the forearm; the hand goes into the (example's) hand by a palm fit
  (thumb base + knuckles; the wrist keypoint reads the cuff); the cuff blends along the forearm (Titan `hand_pose.py`).
- **INV-03.10 Chest-set rulings (2026-10-03):** the roundels are the stationary fulcrum, rigid with the torso; pauldrons pivot
  on the axis through the front and back roundel centres; the pauldron's bone is chosen by measured motion against C-ARM-LIFT,
  never by habit; the neck cowl is taut cloak cloth; black undersuit sleeves are kept for fit and alignment.
- **INV-03.11 Skirt = rigged strips** (one physics bone per strip at the belt, RigidBody, colliding with thigh capsules); **cloak
  = Chaos Cloth on its own fitted mesh** (memory fitting-workflow-revised; GENERATED-EQUIPMENT §7j).
- **INV-03.12 Measure the mesh, not the render or your own labels.** Before the word "missing", list every part with vertices
  in the region with counts (memory measure-the-mesh-not-the-render: the cuirass back plate is in part 25).
- **INV-03.13 A fit failure goes back to the step that produced the input** before any workaround is built (memory
  three-input-fit-pipeline "How to apply").
- **INV-03.14 Any geometry step after texturing discards the texture**; openings and conform run before texture or texture is re-run.

## D. Failure modes already hit

| Date | What went wrong | Ruling it produced | Source |
|---|---|---|---|
| 2026-09-23 | Every piece "goofy": rigid rescaled sculpts floated 3.8 / 9.2 cm (cuirass p50/p90), sandals 4.44x distortion | judge HUG (inner gap) and DESIGNED SHAPE (axis distortion), not just clipping | GENERATED-EQUIPMENT "State of the fitting slice" |
| 2026-09-23 | Forward taken from foot->ball (6.5 deg toe-out) turned every upright piece | forward = level, square to the hips (`forward_from {across: thighs, toward: foot->ball}`) | §7e |
| 2026-09-24 | Sandal laid along foot->ball dips 26.5 deg: heel 6.7 cm up, toe under the floor | `level: true`; sole span = the body's own foot | §7h |
| 2026-09-25 | Skirt passed on gap/stretch numbers while tilted 29 deg with strips bent by the cage | match by eye first; captain ruled "regenerate it" | memory blender-match-before-fit; §7j |
| 2026-09-25 | Fitting body was the armour-refitted GreekWarriorBody | stock body only; body loop retired | memory fitting-workflow-revised |
| 2026-09-26 | Greave "collar": the cage read Tripo's lid as the inner wall and pushed the top out 3 cm | inner wall from across-axis normals only | §7j |
| 2026-09-26 | Cage on the matched boot moved 68 plates rigidly each and opened seams | cage rejected for multi-plate metal pieces | §7k |
| 2026-09-28 | Outward push "fit" distorted every piece along the wrong pose | pose, not push | memory pose-not-push |
| 2026-09-28 | Registration paired each gauntlet with the OPPOSITE arm | side is checked before any seat; `left`/`right` refusal | §7l |
| 2026-09-28 | Own fit model trained on a stock-aligned oracle reproduced the warrior's stance | oracle body must match | memory oracle-body-must-match |
| 2026-09-29 | Example rig's joints were fitted to the MetaHuman's (0.1 cm agreement): ref-posing did nothing | rig the example from its own mesh | memory three-input-fit-pipeline |
| 2026-09-29 | Glove moved 22 deg off its bracer by an experiment became every later stage's input | check each piece against its source part by part (one similarity per rigid group, residual ~0) before fitting | memory gauntlet-glove-detached |
| 2026-09-29 | One bone per part opened glove seams 8.7 cm at rest, cuirass 7.3 cm in a twist | weights by position | memory seams-need-positional-weights |
| 2026-09-30 | Metal shell baked non-rigidly (19.3 mm RMS) while the tear rule read 0 | two metal receipts; per-part role first | memory metal-never-blended |
| 2026-09-30 | Gold embroidery read as metal; a cut recommended | material from the captain, never the shader | memory gauntlet-upper-arm-is-cloth |
| 2026-10-01 | "No back plate" claimed for the fifth time from part labels | list parts by geometry before "missing" | memory measure-the-mesh-not-the-render |
| 2026-10-06 | MetaTailor MT-1 (synthetic glove, known geometry): its 21-keypoint warp moved the glove non-rigidly. Whole-piece residual was 18.1 mm RMS; caps scaled 0.94–1.71; 46 garment vertices ended up inside the hand (min -23.1 mm) | a landmark warp is not a fit for hard parts; metal moves by one similarity per part (INV-03.2), soft parts after it | `goldens/metatailor` MT-1 |
| 2026-10-04 | Chest audit clipping inflated by A-pose vs the piece's implied pose | pose the body to the piece | memory pose-body-to-the-piece |
| 2026-09-25..29 | Every automatic glove sizing failed (skin-to-shell shrink, caps too wide, PCA off-axis, angle clustering mixed fingers); per-finger girth needed 1.5–2.25 and bloated the glove | plate labels are a TYPED decision; girth is an open captain decision | memory fit-tool-direction; §7k |

## E. Golden tests (pipeline level; the step goldens live in their canons)

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G03.1 metal survives the whole chain | `goldens/C03_seam_tube`, lower part declared metal, upper cloth; run place -> bind -> return -> validate | metal part: rest fidelity similarity residual < 1e-6 m, pose rigid residual < 1e-6 m in the twist; seam gap 0 | a per-vertex conform over the metal part makes its similarity residual > 0 |
| G03.2 order gate | call `bind` before `pose` | REFUSED naming `lampway_fit_pose` | an orchestrator that accepts it |
| G03.3 role gate | a part without a role | REFUSED: "the captain or the recipe says metal/leather/cloth/embroidery, never the render's colour" | default role 'metal' |
| G03.4 the push trap | C07 sleeve: instead of the pose sweep, push sleeve vertices outward until no penetration | the pushed sleeve's similarity residual to its source > 10 mm; the posed solution's is 0 | a judge that only counts penetration PASSes the push |

MetaTailor reference observations (black box, 2026-10-06) are in `goldens/metatailor/` §6. GMT.1 is the measured
counter-example for INV-03.2: a landmark warp left rigid caps at 0.44–5.32 mm RMS, scale 0.94–1.71. GMT.8: an already
placed, clear piece passed through unchanged.

## F. Current implementation and remaining gaps (2026-10-07)

1. `api.fit` delegates the canonical order through `pipeline/fit_order.py`, records
   receipts, checks predecessor stages and uses the package's native sidecar.
   `test_canon_item13_fit.py` pins the gates; `test_canon_item13_fit_e2e.py` runs
   the real stages on synthetic and seam-split body packages. This is distinct
   from the older planning-only `armor_piece` runbook.
2. `pipeline/fit_place.py` applies rigid gauntlet axis correction, pinned by
   `test_canon_item5_place.py`. General per-segment `pose_correct` remains a
   measured caller-supplied receipt, rather than a separate correction engine.
3. Soft-part conform remains unbuilt. The composite skips it for all-rigid
   roles; soft parts require the still-open deformer decision.
4. `posing.py` has complete chest and accepted helmet tables. Waist, boots and
   gauntlets execute the complete bounded judgment defaults (canon08),
   explicitly physically untested; supplied DOFs remain available.
5. Independent labelled gloves use the shared pose and bind engines through
   `pipeline/fit_glove.py`, pinned by `test_wave3_glove_state.py`. Default
   gauntlet DOFs and coupled curl targets execute with independent side labels; automatic mirror relabelling is separate and
   does not prevent an independently labelled glove from running.
6. `features/fit_bind.py` samples the native sidecar at the fit pose when a body
   package is supplied. Its explicit scene-body alternative is reported as such;
   the composite requires the native package path.
7. Bind-and-return uses the exact inverse of each vertex's blended transform,
   checks the sampled pose hash and refuses singular blends. Canon04 and
   `test_canon_item4_tools.py` retain the blend-of-inverses falsifier.

## G. Agent-facing tool contract — `lampway_fit` (composite)

```json
{"stage": "status|intake|proportion|match|place|pose_correct|pose|openings|conform|bind|weights|validate|export",
 "piece": "string", "body": "fit_body package dir", "roles": {"<part>": "metal|leather|cloth|embroidery"},
 "kind": "chest|helmet|waist|boots|gauntlets|cloak|skirt", "args": {"...": "the stage tool's own arguments"}}
```
- `status` (no-args view): the piece's fit record — stages done with their receipt hashes, the next allowed stage, and why the
  others are refused.
- Each stage delegates to its canon tool and appends to `<piece>/fit/fit.json` (stage, inputs' sha256, receipt sha256, decider).
- **Refusals (each names the next command):** a stage before its predecessors; a geometry stage after a texture without
  `texture_discard_ack`; any part without a role; a metal part routed to `conform`; a body package that is not native, not
  missing its head (generalized winding ≤0.5), has unverified openings or lacks the weight sidecar; a piece whose source-part check (one similarity per rigid group, residual
  < 0.5 mm) fails (the detached-glove guard); `match` not signed off (`captain_seen: true` with the render hash) before `place`
  results are used by `bind`.
- Receipt: `{piece, stage, ok, receipt_path, sha256, next: ["lampway_fit stage=..."], limits_status}`.

## H. Decisions owed by the captain

1. Is the fitted example still an input after the native-body ruling? **Recommendation:** yes, as the source of the
   armour-to-body RELATIONSHIP (placement, closest pose, plate labels) under INV-03.6, with weights always from the native body;
   no row of this canon needs the example's own weights.
2. Soft-part deformer for cloth/leather: admit ARAP-with-clearance as the next measured candidate (B table)?
3. Glove girth (the genned glove is thinner than the stock hand; 1.5–2.25 to envelope): regenerate in proportion, or accept a
   scaled glove leather?
4. The boots' scale anchor (width | knee height | foot length) — still unruled (LT `fit_place.py:192-193` refuses without it).
