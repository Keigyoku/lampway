---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-canon
description: "Load before ANY fit, placement, pose, skin-weight, bind, validation, opening, proportion, joints-from-views, retopology, UV, bake, clearance, rig, retarget, engine-export or asset-normalization work in Lampway: find the canon page, build to it or call its tool, and never re-derive the algorithm, a frame or a threshold."
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

**[`docs/canon/`](../../../docs/canon/INDEX.md), in this repository, is the source of truth** (2026-10-06). `INDEX.md` is the
table of contents and the authority for each page's status (CANONICAL, DRAFT, GAP); this skill does not restate statuses,
because a status copied here would go stale silently. Beside the pages: `goldens/` (synthetic cases with a byte-deterministic
generator, reference implementations and self-tests), `rig_tools/` (the agent-facing rig-tool rewrites, one spec per tool),
`normalization/` (the canonical asset `lampway.canonical-asset/1`: its schema, examples, self-test, the door and the normalize
contracts), and `IMPLEMENTATION_PLAN.md` (what to build in what order). The spec shelf's `specs/canon/` is no longer edited.

```bash
python3 docs/canon/check_canon.py               # the three self-tests + generators re-run and byte-compared (numpy, jsonschema)
python3 docs/canon/check_canon.py --self-test   # proves the check refuses a hand-edited golden
```

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
| skeleton mapping and rig creation | `16-skeleton-mapping.md` | `animation_retarget` (`build_mapping`), `auto_rig`, `rig_tools/rig_map.md` |
| rest frames and axis conventions | `17-rest-frames-and-axes.md` | `rig.auto_rig`, `rig_tools/rig_conform.md` |
| rig scale and units | `18-rig-scale-and-units.md` | `skeleton_export_check`, `rig_tools/rig_normalize.md` |
| retarget, game rig, bake, root motion, rest change | `19-retarget-bake-root-motion.md` | `animation_retarget`, `rig_tools/rig_retarget.md`, `rig_bake.md` |
| template fit: rig the example from its own mesh | `20-template-fit-example-rig.md` | `rig.auto_rig`, `rig_tools/rig_fit_template.md` |
| engine export (Unreal) | `21-engine-export-ue.md` | `skeleton_export_check`, `engine_import_check`, `fit_export`, `rig_tools/rig_export_ue.md` |
| canonical rig and animation normalization | `22-canonical-rig-normalization.md` | `rig_tools/rig_convert.md` |
| the canonical asset and its door | `normalization/SCHEMA.md`, `DOOR.md`, `contracts/` | every ingress: `normalize_mesh`, `normalize_rig`, `normalize_texture`, `normalize_clip`, `normalize_part_set` |

## How to work with it

1. **Find the page first.** Before writing or changing code in any of these areas, read the page and the conventions page it
   cites. Name the page in your plan and in the commit body.
2. **Call the tool; do not improvise in a script.** When a `lampway_*` tool covers the step, use it (load `lampway-agent-tools`).
   A raw `run_blender_python` that sets bone weights, creates vertex groups, bakes, remeshes, unwraps or loops over poses is the
   re-derivation this skill exists to stop.
3. **Build to the page.** An implementation item is RED-first against the page's named goldens: the golden's falsifier must be
   seen failing the OLD code before the new code lands. Load a golden's case from `docs/canon/goldens/` in the Lampway suite;
   never copy it elsewhere and never weaken its tolerance.
4. **A page's open decision is not yours.** Where the page says DRAFT and names a ruling owed (a threshold, a range, a per-type
   table), stub the behaviour as `needs_decision` and route the question; never pick a value.
5. **When the page is wrong,** prove it with a measurement and change the page here, through your lane, with the ruling or
   measurement it rests on and `check_canon.py` green; never fork the canon in code.

Provenance: `docs/canon/INDEX.md` and `IMPLEMENTATION_PLAN.md` §3 (the agent skill entries), written 2026-10-05/06 against
`lp/wave5` at `b806617f` and copied into this repository on 2026-10-06.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | the canon's implementation plan §3 asks for a canon skill; captain: "make the DOE x DOX AGENTS rail for Lampway" | agents re-derived frames, weights and thresholds from memory and repeated recorded failures | load the canon page before any fit or geometry work, call its tool, route its open decisions; the canon's location stated honestly while it is off-tree | canon plan §3 |
| 2026-10-06 | the canon moved into the repository | coordinator: "GO for rail row 1" (the captain's recommendation 1) | the skill sent agents to an off-tree shelf and covered pages 01-15 only | point at docs/canon as the source of truth; pages 16-22, rig_tools and normalization in the table; check_canon.py named; page fixes land in the repo through a lane | captain ruling, 2026-10-06 |
