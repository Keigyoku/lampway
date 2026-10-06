<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway algorithm canon — INDEX

> **This repository copy, `docs/canon/`, is the source of truth** (coordinator, 2026-10-06, rail row 1: the captain's
> recommendation accepted). It was copied from the spec shelf's `specs/canon/` once the canon and normalization auditors finished;
> the shelf copy is no longer edited. A canon change is made here, by a lane, in a commit that keeps
> `python3 docs/canon/check_canon.py` green (the three self-tests and byte-identical goldens), and cites the ruling or measurement
> it rests on. Large binaries (the MetaTailor FBX and GLB files) stay out of git; `goldens/metatailor/README.md` records their
> SHA-256. `<specs>` in these pages names the off-tree spec shelf the canon was written against.

One canonical specification per core 3D algorithm so no agent re-derives it. Each page carries: the problem (inputs, outputs,
frames, units), the method with its published source, the invariants, the failure modes already hit with their dates and rulings,
golden tests with falsifiers, the current implementation's gap at file:line, and the agent-facing tool contract. Template:
`<specs>/CONTRACT_TEMPLATE.md`, extended. Written 2026-10-05 against Lampway `lp/wave5` at `b806617f`, Titan at `e3d5ebb5`.

**Status words.** CANONICAL = the maths and invariants are settled by measurement and ruling; an implementer builds to it.
DRAFT = the direction is settled but a ruling, a measurement or a parameter is still owed (named on the page). GAP = no
implementation exists that meets the canon.

| # | Algorithm | Status | Lampway tool today (LT = `lampway_tools`) | Gap in one line | Goldens |
|---|---|---|---|---|---|
| 01 | [Frames, units, bones, identities](01-conventions.md) | CANONICAL | (every tool) | bone direction from the imported tail in LT `fit_bind`, `weights.plan`, `rig._proximity_weights` | — |
| 02 | [Rigid / similarity fit](02-rigid-similarity.md) | CANONICAL | `pipeline/validate.rigid_fit` | four copies across LT/Titan; whole-mesh rest fidelity | C01 |
| 03 | [Fit and deform (the order and the laws)](03-fit-and-deform.md) | CANONICAL order; DRAFT soft-part deformer | `fit_place`, `fit_pose`, `fit_openings`, `fit_bind`, `fit_validate`, `fit_export`, `fit_glove` | no orchestrator; no rigid per-segment pose correction; no soft-part conform; glove pose/bind stubbed | C03 (+ step goldens) |
| 04 | [Bind at the fit pose, return to rest](04-bind-and-return.md) | CANONICAL maths, GAP | `lampway_fit_bind stage=return` (residual only) | no return in Lampway; Titan returns by the blend of inverses | C02 |
| 05 | [Fit validation](05-fit-validation.md) | CANONICAL receipts; limits PROPOSED | `lampway_fit_validate`, `rig_armor`, `pose_test` | tautological expectation; Euler poses; proximity seams; nearest-normal crossings; uncapped control; no engine leg | C01, C03, C05, C07, C14 |
| 06 | [Openings (keep / gasket / delete)](06-openings-gasket.md) | DRAFT (collar depth owed) | `lampway_fit_openings` | detects only at the extremes of a typed axis; largest-loop section | C12 |
| 07 | [Skin weights: robust transfer, profiles, seams](07-skin-weights.md) | CANONICAL; per-type table DRAFT | `lampway_weight_transfer`, `fit_bind stage=weights`, `weight_audit/cleanup` | no weld; no region constraint; zero rows after restrict; no dress/fade/falloff/seam band | C03, C04 |
| 08 | [Pose the body to the piece](08-pose-solve.md) | CANONICAL chest; DRAFT other kinds | `lampway_fit_pose` (chest route), `pose_clearance` | absolute-height regions; world-axis DOFs; output not replayable; four kinds unruled | C07 |
| 09 | [Placement and registration (enclosure)](09-placement-enclosure.md) | CANONICAL; boots anchor DRAFT | `lampway_fit_place`, `place_piece` | all-vertex section centres (non-chest); rotation not applied; absolute constants | C06 |
| 10 | [Proportion scoring + silhouette instruments](10-proportion-score.md) | CANONICAL chest; DRAFT other kinds | `lampway_proportion_ratios`, `lampway_piece_ratios`, `silhouette_compare` | non-chest kinds unfalsified; silhouette crop-and-stretch | C11 |
| 11 | [Joints from views (2D -> 3D)](11-multiview-joints.md) | CANONICAL maths; DRAFT pipeline | `anim_multiview_fit` (video only) | no static rig-from-views tool; no detector; axis naming differs | C08 |
| 12 | [Retopology](12-retopology.md) | DRAFT | `lampway_retopo` (QuadriFlow / voxel / AutoRemesher) | one-sided deviation; no per-part retopo; sharp edges off | C13 |
| 13 | [UV unwrap, pack, score, Smart-UV facts](13-uv-unwrap-pack.md) | CANONICAL measurements; DRAFT unwrap/pack | `lampway_uv_score`, `uv_unwrap`, `uv_texel_density`, `uv_layout`, `uv_rectify`, `rebuild` (uv_patches) | two island definitions; inclusive raster; row packer | C09 |
| 14 | [Baking (cage ray cast)](14-baking.md) | DRAFT | `lampway_bake_maps` | ray 0.5x cage by default; 8-bit normals; no hit mask | C10 |
| 15 | [Clearance and penetration](15-clearance-penetration.md) | CANONICAL | `lampway_garment_clearance` | nearest-normal sign; no innermost gap; no hideable | C05 |
| 16 | [Skeleton mapping and rig creation](16-skeleton-mapping.md) | CANONICAL; family tables DRAFT | inside `animation_retarget` (`build_mapping`); `auto_rig` fixed table | no family tables, no tie refusal, no synthesis, no map receipt | R01 |
| 17 | [Rest frames and axis conventions](17-rest-frames-and-axes.md) | CANONICAL; finger up-axis table DRAFT | none (heads/tails only in `rig.auto_rig`) | no frame computation, no convention detector; export check has no frames | R02 |
| 18 | [Rig scale and units](18-rig-scale-and-units.md) | CANONICAL | `skeleton_export_check` reads the unit ratio | no apply-scale; GRT's is wrong for non-uniform (measured 0.2236 m) | R03 |
| 19 | [Retarget, game rig, bake, root motion, rest change](19-retarget-bake-root-motion.md) | CANONICAL maths; game-rig scale policy DRAFT | `animation_retarget` (matrix, constraints) | no root bone, no game-rig extraction, no bake tool, no rest change | R04, R05, R07 |
| 20 | [Template fit: rig the example from its own mesh](20-template-fit-example-rig.md) | CANONICAL; hidden joints DRAFT | `rig.auto_rig` (height fractions) | no measured joints, no provenance, no inside check | R06 |
| 21 | [Engine export (Unreal)](21-engine-export-ue.md) | CANONICAL gate; the axis pair per convention derived (R08), its UE confirmation owed (M-RIG-01) | `skeleton_export_check`, `engine_import_check`, `fit_export` | no frame/scale read-back; no recipe writer | R02, R08 (+ G21.2-3 to build) |
| 22 | [Canonical rig and animation normalization (O36)](22-canonical-rig-normalization.md) | CANONICAL animation; skin/morph DRAFT | none (STATUS O36 orphan) | the maths exists only in Titan's pure modules | G22.x (Titan suite to port) |

Also: [goldens/](goldens/README.md) (two generators + self-tests: C01-C14 35 checks, R01-R08 32 checks, both byte-deterministic),
[rig_tools/](rig_tools/README.md) (the agent-facing rewrite specs of MB UE5 Rig Creator Pro and Game Rig Tools, 11 tools, O36)
and [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md). Canons 16-22 were added the same day (the captain's rig-tools scope) and
cite Lampway at `4e9001c7`.

## Sources read

- Memory notes (captain rulings and lessons), every one the brief named plus pipeline-set-hp-lp, salvage-parts-piece-by-piece,
  tripo-studio-invariants, v3-turnarounds-are-the-appearance-source, final-look-judged-in-engine, no-heavy-renders-while-live,
  codex-imagegen-textures, animation-from-video, model-licences-not-a-blocker, tools-follow-axi.
- Shelf `tools/` (TOOLS.md, PIECE_PIPELINE.md, all of `proportion/`, the partseg tools used by the pipeline, `meshqa` headers,
  `texlib/uv_score.py`, `relief_project.py`/`pbr_merge.py` headers), shelf scratch `grt/` (enclose.py, rig_axi/centre.py, the seam and
  strain logs, the MetaTailor export study).
- Titan `docs/design/GENERATED-EQUIPMENT.md` §7–7m; Titan `tools/armour_validate.py`, `equipment_fitpose.py`, `seam_ledger.py`,
  `surface_query.py`, `weight_profile.py`, `hand_pose.py`, `proc_body.py`, `views_joints.py`, `recipes/armour-*.json`,
  `fit-profiles.json`, `piece-weights.json`, `fit-attach.json`.
- `<codex-shelf>`: weld, winding, affine, scale, bind-preservation, influence-order, correspondence, skin-reference, hand-frame,
  pose, body-profile designs and their review verdicts; the captain-equipment assessment; the reference audit.
- `<astra-shelf>`: the authored-helmet report, deliveries, the claude-2 reconstruction spike report and environment findings.
- Rig tools (canons 16-22): Game Rig Tools core 4.3.0 and Unreal module 4.2.0, MB UE5 Rig Creator Pro 3.1.0 (reading depth in
  `rig_tools/README.md`), headless Blender 5.2.1 probes of GRT on synthetic rigs and of GRT's bundled mannequin asset (counts
  and angles only); Titan `adr/0012-normalize-first.md`, `tools/animation_canon.py`, `canon.py`, `skin_bind.py`, `rig-axi.py`;
  `<codex-shelf>` Task 130/131/37 records; shelf `grt/rigfit.py`, `grt/rig_axi/run*.log`, `grt/rig_own/rig_own.json`.
- Lampway `wt-wave5`: the fit/bind/validate/export/opening/weights/clearance/rig/retopo/UV/bake/anim_mv modules and their wave
  2–5 reports and the fit tests; `<specs>` shelf/, wiki/, resources/, generation/ contracts, BUILD_ORDER.md, STATUS.md.

**Graph reach (disclosed).** The code graph has no index of `wt-wave5`, of this Titan worktree (`/6`), or of the codex/astra
shelves; the two indexed Titan crew worktrees (claude-1 and codex-1) do not contain `equipment_fitpose.py` (searched by
name: 0 nodes). Every file:line in this canon is from reading the file. No claim here says a symbol has or lacks callers.
Re-checked for canons 16-22 (`list_projects`, 2026-10-05): still no index of `wt-wave5` or worktree `/6`; the add-ons and the
shelves are not indexed. A Lampway absence claim in 16-22 ("no apply-scale tool", "no root bone") means: not present in the
`LT/features` and `LT` module lists read on 2026-10-05 and not in the modules named.

## Black-box references

- **MetaTailor** (studied 2026-09-29, memory metatailor-study). On the captain's approval, MT-1..MT-4 ran on 2026-10-06 in one
  FBX export (3 of 5 this month used, 2 remaining). Synthetic inputs only; black box (inputs and outputs measured). The record
  is in `goldens/metatailor/` and the summary in `IMPLEMENTATION_PLAN.md` §5. It informs canons 03, 05, 06, 07, 09 and 15.
- **Alpaca3D** (alpaca3d.app, v0.12.32, Windows x64, not publisher-signed): **not installed or run.** It is an interactive tool
  (manual Retopo lab, Auto Seams + pack, a Bake lab with bake groups and cage offset); measuring it needs GUI automation under
  Proton on a headless display. Its published capability list is used as reference behaviour only (canon 13, 14). Running it is
  listed as an optional item in the plan, on public meshes only.
