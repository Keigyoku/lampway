<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Canon 07 — Skin weights: robust transfer, type profiles, seam-aware positional weights

Status: **CANONICAL** (method and invariants), with the per-type profile table **DRAFT** for the types not yet measured
(helmet, boots, waist strips). Implemented by: LT `features/weights.py` (`transfer`, `audit`, `cleanup`), LT
`scripts/rig/robust_weight_transfer.py`, LT `features/fit_bind.py` (`weights` stage); Titan `tools/weight_profile.py`,
`hand_pose.py` (`falloff_weights`, `rigid_blend`, `rigid_blend_strict`), `surface_query.py`, `proc_body.py:84 joint_blends`,
`recipes/piece-weights.json`, `recipes/fit-profiles.json`, `recipes/fit-attach.json`.

## A. Problem

Give every vertex of a fitted piece weights on the native skeleton such that: metal parts move rigidly; cloth and leather follow
the body; the two copies of every seam vertex move together; armpits, crotch and chest-to-arm gaps blend smoothly without hand
painting. Inputs: the piece at the fit pose (body frame, metres), its part labels and roles, the native body at the same pose with
its sidecar weights (all influences, never the 4-influence GLB), the type's profile. Output: per-vertex `{bone: weight}` summing
to 1, plus receipts.

## B. Method

1. **Weld by position** (1e-5 m) — generated pieces only (canon 01 D.1/D.2). Every step below runs on welded vertices; results
   scatter back so duplicates carry bit-identical rows (golden C04: an unwelded fill leaves a whole island unweighted).
2. **Match to the body surface** (Abdrashitov, Raichstat, Monsen, Hill, "Robust Skin Weights Transfer via Weight Inpainting",
   SIGGRAPH Asia 2023 Technical Communications; reference code rin-23/RobustSkinWeightsTransferCode, MIT; add-on
   sentfromspacevr/robust-weight-transfer, GPL): closest point on the body triangles, barycentric interpolation of the native
   weights; accept when distance <= `max_distance` and the normal angle <= 30 deg (or its flip for single-sided shells). The paper's
   distance default is a fraction of the bounding-box diagonal (0.05 of it); state the absolute value in the receipt.
   **Region-constrained:** the query names the profile's body regions and requires normal compatibility, so "a closer incompatible
   surface cannot hide the correct one" (Titan `surface_query.py:131 nearest(regions=, normal=, min_normal_dot=)`): a sleeve
   vertex 1 cm from the torso takes arm bones. Search the allowed region for the nearest normal-compatible triangle within the existing distance bar, even when the nearest triangle fails the normal bar. Equal measured distances use stable triangle identity, without an acceptance tolerance expansion. For a compatible nearest hit, a float32 BVH discovery radius may advance one representable step to avoid an inward-rounded boundary, capped by the declared distance; every discovered hit is then filtered against the original measured nearest distance and unchanged normal bar. A coincident body vertex does not guarantee its authored weights when every incident face fails the normal gate: C02's exact-inverse tool control supplies the golden's authored W explicitly, while a separate transferred-W control proves forward round-trip under the unchanged 1e-6 m bar.
3. **Inpaint the unmatched** by the biharmonic energy with matched rows fixed:
   `min tr(Wᵀ Q W), Q = -L + L M⁻¹ L`, L, M the robust Laplacian and mass of Sharp & Crane 2020 ("A Laplacian for Nonmanifold
   Triangle Meshes", SGP; `robust_laplacian`), point-cloud or mesh mode; clamp >= 0, renormalise. Optional smoothing near the
   matched/unmatched boundary (the add-on's `smooth` pass).
4. **Apply the type's profile** (CC5's per-type templates, by rule; the captain 2026-09-28):
   - `rigid` — every vertex on one bone (helmet: `head`).
   - `restrict` — transferred weights kept to the type's bones; a weight on any other bone moves to its nearest ALLOWED ANCESTOR,
     else to the named fallback (Titan `weight_profile.py:38 remap_table`); never renormalise a zero row silently — refuse it.
   - `dress` — pelvis alone at and above the hips; the thighs' share `f = follow · smoothstep((top - z)/(top - hem))`, split
     between the thighs by the point's place between them (`weight_profile.py:70 dress`; skirt follow 0.6).
   - `plate` — a hard part of a separate piece on ONE bone: the allowed bone nearest the part's AREA centroid (by transferred weight
     the cuirass shell rode `upperarm_r`, pulled by ornament-dense shoulders); a plate within the first 25 % of its bone sits over the
     joint and rides the parent (`weight_profile.py:177 nearest_bone`); a carried label (the glove's typed plate decision) wins.
   - Glove leather: **continuous falloff** — every bone within `margin` (6 mm) of the nearest segment takes `(1 - excess/margin)²`,
     normalised (`hand_pose.py:216`); the two-nearest inverse-distance rule jumps where the second-nearest bone changes and cracked
     the leather (2026-09-29).
5. **Rigid parts fused to cloth/leather:** each hard part's rigidity `r = smoothstep(1 - d/fade)` (fade 5 mm) takes its bone; the
   field keeps what remains (`hand_pose.py:226 rigid_blend`); strict form refuses two different rigid anchors at one point
   (`rigid_blend_strict`, :244). Only the source-bound articulated contacts ruled below may separate contact domains; the retained third pairing at a three-way contact remains strict.
6. **Seam band** (one shell cut into parts): the blend across a cut is a function of POSITION only (a band about the cut line);
   measured on the rigged warrior: a 5 cm band cut seam drift p95 2.47 -> 0.27 cm in the walk, pairs over 2 cm 5.62 % -> 1.24 %
   (`<shelf-scratch>/grt/gap_seam0.log` vs `gap_seam5all.log`, 2026-09-29).
7. **Per-joint blend widths** on a procedural / example body: a quarter of the shorter bone at each joint (0.4–7.0 cm) took the
   elbow bend's cuirass from 1121 stretched edges to 1 (`proc_body.py:84 joint_blends`; GENERATED-EQUIPMENT §7m).
8. **Rigid groups.** Parts sharing a seam and one bone form a rigid group; two rigid parts of ONE shell on different bones open the
   seam: refused at apply unless the captain accepts a gap (LT `fit_bind.py:94-127`, correct).
9. **Influences.** No cap beyond the engine's (MetaHuman FullBody keeps up to 12); record the histogram. Bone directions for every
   segment distance use head -> continuation child (canon 01 C.1), never the imported tail.

## C. Invariants

- **INV-07.1** Weights depend on position alone within each closed contact domain of a genned piece; duplicates are bit-identical. The narrowly source-bound articulated-contact exception below separates only explicitly authorized contact pairs on a derived copy. Undeclared pairs remain in the same domain.
- **INV-07.2** Metal parts: one bone at weight 1.0 per part (per rigid group).
- **INV-07.3** Weights come from the native body (sidecar), never a GLB copy (4 influences).
- **INV-07.4** Never "transfer then hope": every vertex is matched or inpainted; zero rows refuse.
- **INV-07.5** Profiles belong on separate genned pieces, not on a fused example (a profile switch inside one connected shell tears
  along its seam: arms up chest 3137 -> 3160 torn edges, 2026-09-29, GENERATED-EQUIPMENT §7m).
- **INV-07.6** The pauldron's bone is chosen by measured motion against the reference (C-ARM-LIFT), never by habit
  (memory chest-parts-motion-rulings). Never by a default either: MetaTailor's Accessory route parented a shoulder plate to
  `hand_r`, and "Parent to Closest" kept that (`goldens/metatailor` MT-2).

## D. Failure modes already hit

| Date | What | Lesson | Source |
|---|---|---|---|
| 2026-09-23 | UE `PruneBoneWeights` left 3,263 of 4,152 vertices weighted to a bone named None | restriction is our code (remap to allowed ancestor) | GENERATED-EQUIPMENT §7 |
| 2026-09-29 | Nearest transfer: cuirass took the pauldrons' forearm weights; skirt stretched between the legs; helmet bent at the neck | type profiles (rigid / restrict / dress) | `titan/tools/weight_profile.py` docstring |
| 2026-09-29 | Blender heat weights left all 2.55 M warrior vertices unweighted | heat weights are not a fallback for genned meshes | GENERATED-EQUIPMENT §7m |
| 2026-09-29 | One bone per part opened the gloves' seams 8.7 cm at rest, the cuirass 7.3 cm in a twist | positional weights | memory seams-need-positional-weights |
| 2026-09-29 | Two-nearest inverse-distance weights cracked the glove leather at rest | continuous falloff | GENERATED-EQUIPMENT §7m (1) |
| 2026-09-29 | MetaTailor's export: 5–14 bones per vertex incl. MetaHuman correctives; the sleeve above the elbow weighted to `upperarm_twistCor_02` and stretched 17 % | record influences; correctives are not fit bones | memory metatailor-study |
| 2026-10-06 | MetaTailor MT-1..MT-4 (synthetic). Glove: 94 bones, up to 29 influences, rigid caps on 8–21 influences that strain up to 70 %. Plate (Shirts): 10 bones (upperarm_out 0.46, clavicle 0.25); bends 22 % (p95) at a 60° arm lift. Skirt: thigh share 0.63 at the strip tops -> 1.0 by 0.68 m; strips stretch 36 % (p95) in a 60° hip flexion. Greave: calf twist bones 0.88, rigid (0.18 mm) through a 90° knee bend | a template's cloth skinning is the counter-example for INV-07.2 and the pteruges ruling; the skirt ramp is a measured reference shape for `dress`; a twist-bone pair keeps a shin tube rigid | `goldens/metatailor` |
| 2026-10-03 | PartField's "island respect" was the UV-seam split | weld before adjacency | memory smart-mesh-seams-split-vertices |

## E. Golden tests

| Test | Fixture | Expected | Falsifier |
|---|---|---|---|
| G07.1 weld before fill | `C04_weld_inpaint` | welded: 0 unweighted, 5 duplicate pairs bit-identical, sums 1 | index-graph fill: 30 unweighted |
| G07.2 positional seams | `C03_seam_tube` | positional band: ledger gap 0 in the 40 deg twist | one bone per part: 8.208 cm |
| G07.3 dress rule (analytic) | `dress(top=1.0, hem=0.5, left_x=0.1, right_x=-0.1, follow=0.6)` | (0.1,0,0.5) -> {pelvis 0.4, thigh_l 0.6}; (0,0,0.75) -> {pelvis 0.7, thigh_l 0.15, thigh_r 0.15}; (0,0,1.2) -> {pelvis 1} | a linear (not smoothstep) ramp gives 0.7 / 0.15 too but fails at z 0.6 (expected f = 0.6·0.896 = 0.5376) |
| G07.4 restrict remap | parents `{pelvis: None, spine_01: pelvis, spine_03: spine_01, upperarm_l: spine_03, lowerarm_l: upperarm_l}`, allowed `[spine_0*, upperarm_*]`, fallback `spine_01` | `lowerarm_l -> upperarm_l`, `pelvis -> spine_01` (fallback) | a bone with no allowed ancestor and no fallback must REFUSE |
| G07.5 region constraint | a sleeve vertex 1 cm from the torso, 3 cm from the upper arm | arm bones only | whole-body nearest gives spine |
| G07.6 continuity | a point moving across the boundary where the 2nd-nearest bone changes | weights continuous (max jump < 1e-6 for a 1e-6 m step) | the two-nearest rule jumps |

## F. Implementation gap (Lampway `b806617f`)

1. **No weld.** LT `features/weights.py:283-308` matches per vertex index; split duplicates get different vertex normals per island
   (`v.normal`, :287) so the 30 deg gate can accept one copy and reject the other; the harmonic fill (:335-355) walks mesh edges, so
   an unmatched island stays zero (golden C04). The robust fill (`scripts/rig/robust_weight_transfer.py:20-23`) builds its Laplacian
   on unwelded points.
2. **No region constraint; nearest over the whole body.** LT `features/fit_bind.py:155` calls `transfer(max_distance=0.5,
   max_normal_angle=180)`: any surface within 50 cm, any normal.
3. **Restrict leaves zero rows.** `fit_bind.py:162-168` zeroes non-allowed bones then normalises; a vertex whose allowed bones carry
   no transferred weight stays unweighted (no ancestor remap, no fallback).
4. **Bone segments use the imported tail** (`fit_bind.py:49-54` `_hist`, `weights.py:89-114` `plan`, `rig.py:100-118`
   `_proximity_weights`): wrong for any glTF-imported UE rig (canon 01 C.1).
5. **Rigid part bone by vertex-count majority of nearest segment** (`fit_bind.py:84-88`), not the part's area centroid.
6. **No dress, no plate fade, no continuous falloff, no seam band**; `cleanup mirror_from` refused (not built).
7. **Influence cap 4 by default** (`weights.py:260`, `audit` max_influences 4) against a 12-influence native body.
8. Weights come from a scene body object, "an approximation" (`fit_bind.py:146,185`), not the sidecar.

## G. Agent-facing tool contract — `lampway_weight_transfer` (engine of `lampway_fit_bind stage=weights`)

```json
{"object": "piece", "body": "fit_body package dir (sidecar REQUIRED)", "pose": "pose.json (the fit pose)",
 "profile": "chest|helmet|waist|greave_l|greave_r|gauntlet_l|gauntlet_r|<recipe profile>", "parts_roles": {"part": "role"},
 "weld_m": 1e-5, "max_distance": "number m | 'diag:0.05'", "max_normal_angle": 30, "flip_normals": true,
 "inpaint": "biharmonic_point|biharmonic_mesh", "seam_band_m": 0.05, "plate_fade_m": 0.005, "falloff_margin_m": 0.006}
```
Refusals: no sidecar ("weights come from the native asset: run lampway_fit_body build"); a profile bone not in the skeleton (nearest
names); a bone with no allowed ancestor and no fallback; zero rows after restriction (names the vertices' region); a metal part
assigned `blend`; two rigid anchors at one point; the science python lacking `robust_laplacian`/`scipy` (names the interpreter).
Receipt `weights.json`: `{matched_fraction, inpainted, duplicates_identical: true, influence_histogram, max_influences, per_part:
{role, mode, bones, reason}, seam_pairs_checked, sha256: {piece, body_package, pose}}`.

## Current public planar seam interface (2026-10-09)

The historical gaps above describe `b806617f`. `fit_bind` now composes the existing `band_weights` primitive through an optional `bind_overrides._seam_bands` list at `stage=plan`. Each recipe names `parts` and `bones` in behind/ahead order, `generated_same_shell: true`, the working `workflows.mesh_hash(piece)` as `source_sha256`, complete `source_seam_pairs` as working source vertex ID pairs, world-metre `cut_point`, `axis`, and positive finite `width_m` (default 0.05 m). The declaration must come from actual source authority; coincident points alone do not establish same-shell provenance.

The bounded interface admits explicit flexible planar cuts with disjoint ownership and compatible endpoint fields. Complete contact pairs must match the source within the unchanged weld bar and lie on the declared plane. Rigid/metal ownership, ambiguous or overlapping bands, invalid endpoints, and changed source/frame/membership/recipe refuse before publication. Plan and weights retain the input identities and pair count; band composition precedes the unchanged strict rigid fade. It does not authorize any seam opening or certify physical quality. The source remains intact and physical review remains separate.

`weight_transfer` now uses `limit_groups=0` by default, preserving native influences. A positive caller-requested cap is still applied and recorded; it is never selected implicitly as four. This does not change the engine's own export constraints or the explicit cleanup limit operation.

## Authorized articulated shoulder contacts (2026-10-10)

The captain authorized the proposed bounded shoulder-contact exception: “If this is what it takes to match the movement in the ref videos, do it.” The proposal keeps the torso plates and roundels rigid together, releases only the identified off-axis pauldron bridge contacts on derived copies, and retains the sleeve-to-torso pairing at the left three-way contact. The reviewed inventory identifies thirteen source vertices and fourteen released pair rows. This ruling authorizes implementation and candidate measurement; it does not select a physically verified carrier, hinge, final fit or acceptable gap.

The optional `bind_overrides._articulated_contacts` declaration uses schema `lampway.articulated-contacts/1`. It pins the authored `source_sha256`, working `prepared_sha256` and complete `prepared_identity`; its `contacts` rows name `parts: [a,b]`, released `source_vertices` and `retained_source_vertices`. Their disjoint union must equal the complete contact closure for that part pairing. The `authorization` object records `decision: release_derived_contacts`, `scope: contact_pairs_only` and the actual approving declaration. Original-file provenance and the source-bound inventory are retained in the private candidate package; source geometry and owner assets do not enter this repository.

Admission requires the existing authored FACE-part copy and its validated original identity/ownership/seam ledger. Every declared part pairing must partition its complete measured and original contact closure into released and retained original IDs. Retained IDs remain strict; a partially released rigid pairing cannot bypass the remaining seam-open refusal. Reject omitted or extra IDs, repeated pair rows, stale geometry/frame/part membership, unknown fields and unsupported endpoint ownership before publication. Recheck the declaration at weights, return and apply. Rigid endpoints require explicit one-bone choices; implicit proximity defaults cannot select an articulated carrier. A flexible endpoint may ignore only the explicitly released rigid surface at the named source vertices; undeclared rigid anchors, nearby vertices and retained three-way pairings keep the existing strict fade and weight rules. Keep released contacts visible in diagnostic receipts, separately from closed seam metrics.

This interface changes weight-domain coupling on copied ownership boundaries. It preserves source faces, corner identities, UVs, material assignments and original scene data. It introduces no global seam waiver, substitute geometry, numerical tolerance or automatic full-fit approval. Canon05 deformation/clearance checks, bind/return, output review and physical motion acceptance remain required. A reference-video semantic review establishes the intended movement, not a measured three-dimensional hinge or bone choice.

## H. Decisions owed by the captain

1. Influence cap for armour pieces in UE (none / 8 / 12)?
2. Profiles for helmet (rigid head), boots (restrict calf/foot/ball), waist (dress) — accept as drafted, or measure first?
