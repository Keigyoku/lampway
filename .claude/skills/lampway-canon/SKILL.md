---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-canon
description: "Load before ANY fit, placement, pose, skin-weight, bind, validation, opening, proportion, joints-from-views, retopology, UV, bake or clearance work in Lampway: find the canon page, build to it or call its tool, and never re-derive the algorithm, a frame or a threshold."
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: judgment
---

# Use the canon; never re-derive

Most re-derivations in this project's history began with a frame, a bone direction or a threshold guessed from memory, and most
of them were wrong in a way a measured page already recorded. The algorithm canon fixes each core 3D algorithm once: the problem
(inputs, outputs, frames, units), the method and its published source, the invariants, the failures already hit with their dates
and rulings, golden tests with falsifiers, the current implementation's gap at file:line, and the agent-facing tool contract.

## Where it is

The canon is written in the coordinator's spec shelf as `specs/canon/` (`INDEX.md`, one page per algorithm, `goldens/` with a
byte-deterministic generator and self-test, `IMPLEMENTATION_PLAN.md`). **It is not in this repository yet.** If your brief names
its path, read it there. If it does not, say so through your status channel and wait; do not reconstruct a page from memory.
`INDEX.md` is the authority for each page's status (CANONICAL, DRAFT, GAP); this skill does not restate statuses, because a
status copied here would go stale silently.

## The pages

| topic | page | the Lampway tools it governs |
|---|---|---|
| frames, units, bones, identities | `01-conventions.md` | every tool that moves points between frames |
| rigid / similarity fit | `02-rigid-similarity.md` | `pipeline/validate.rigid_fit` |
| fit and deform: the order and the laws | `03-fit-and-deform.md` | `fit_place`, `fit_pose`, `fit_openings`, `fit_bind`, `fit_validate`, `fit_export`, `fit_glove` |
| bind at the fit pose, return to rest | `04-bind-and-return.md` | `lampway_fit_bind` |
| fit validation | `05-fit-validation.md` | `lampway_fit_validate`, `rig_armor`, `pose_test` |
| openings: keep, gasket, delete | `06-openings-gasket.md` | `lampway_fit_openings` |
| skin weights: transfer, profiles, seams | `07-skin-weights.md` | `lampway_weight_transfer`, `fit_bind stage=weights`, `weight_audit`, `weight_cleanup` |
| pose the body to the piece | `08-pose-solve.md` | `lampway_fit_pose`, `pose_clearance` |
| placement by enclosure | `09-placement-enclosure.md` | `lampway_fit_place`, `place_piece` |
| proportion scoring, silhouette instruments | `10-proportion-score.md` | `lampway_proportion_ratios`, `lampway_piece_ratios`, `silhouette_compare` |
| joints from views | `11-multiview-joints.md` | `anim_multiview_fit` |
| retopology | `12-retopology.md` | `lampway_retopo` |
| UV unwrap, pack, score | `13-uv-unwrap-pack.md` | `lampway_uv_score`, `uv_unwrap`, `uv_texel_density`, `uv_layout`, `uv_rectify` |
| baking | `14-baking.md` | `lampway_bake_maps` |
| clearance and penetration | `15-clearance-penetration.md` | `lampway_garment_clearance` |

## How to work with it

1. **Find the page first.** Before writing or changing code in any of these areas, read the page and the conventions page it
   cites. Name the page in your plan and in the commit body.
2. **Call the tool; do not improvise in a script.** When a `lampway_*` tool covers the step, use it (load `lampway-agent-tools`).
   A raw `run_blender_python` that sets bone weights, creates vertex groups, bakes, remeshes, unwraps or loops over poses is the
   re-derivation this skill exists to stop.
3. **Build to the page.** An implementation item is RED-first against the page's named goldens: the golden's falsifier must be
   seen failing the OLD code before the new code lands. Copy a golden's case into the Lampway suite; never weaken its tolerance.
4. **A page's open decision is not yours.** Where the page says DRAFT and names a ruling owed (a threshold, a range, a per-type
   table), stub the behaviour as `needs_decision` and route the question; never pick a value.
5. **When the page is wrong,** prove it with a measurement and report it to the canon's author; do not fork the canon in code.

Provenance: `specs/canon/INDEX.md` and `IMPLEMENTATION_PLAN.md` §3 (the agent skill entries), written 2026-10-05 against
`lp/wave5` at `b806617f`.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | the canon's implementation plan §3 asks for a canon skill; captain: "make the DOE x DOX AGENTS rail for Lampway" | agents re-derived frames, weights and thresholds from memory and repeated recorded failures | load the canon page before any fit or geometry work, call its tool, route its open decisions; the canon's location stated honestly while it is off-tree | canon plan §3 |
