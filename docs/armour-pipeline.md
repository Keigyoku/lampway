<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Armour pipeline

The armour pipeline takes one game-armour piece (a helmet, a chest, a waist piece, gauntlets or boots) from reference plates to an engine-ready, rigged, textured export, as **ordered, gated steps**. Every step is an existing tool or a studio action; the pipeline itself is a sequencer and a record, not a doer. It is the first thing the project was built around, and it is the clearest example of "build the tool, not the output".

Code: `src/scripts/mixar/modules/lampway_tools/pipeline/armor_piece.py` (the sequencer), the tools named below, and `server/lampway_server/studios/` (the studio actions). Agent tool: `lampway_armor_piece_pipeline`.

**Status, plainly.** Mesh-paint texturing and the rebuild loop have run live on a real piece. Waves 2 and 3 (plates, seeds, audits, UV scoring, bake, PBR, placement, bind, validation, export) are built and tested on **synthetic shapes**: no real piece has been fitted to a real body with these tools, the studio actions have never run against a live Studio, and every threshold named "proposed" is a placeholder the maintainer owns. The engine editor leg (importing and validating inside the game engine) is not built.

## 1. The laws

These are enforced in the code, not suggested:

- **Proportions trump mesh defects.** Score every seed against the reference body before anything else. Defects can be repaired; proportions are seeded.
- **Studio actions land on a saved copy.** The original stays virgin and regenerable. Edit Mesh and the free rerolls are the only tools used on an original.
- **Every studio setting is set and read back before Generate**; a mismatch refuses the run. Always 4 variants at maximum polycount.
- **Texturing comes last.** Smart UV the piece first and the studio texture then fills its islands. Any geometry or UV step after a texture discards the texture; the run record marks the texture stale.
- **Pose the body to the piece** before clearance, fit or weights.
- **Enclosure, not registration; pose, not push; metal never blended.** Placement centres the piece on its body segment and applies one uniform scale; fitting corrects pose rigidly per segment; metal parts get one rigid transform and are never weight-blended. Cloth, leather and embroidery are the only blended classes.
- **Typed decisions.** Quality review is a log of typed rows (`id, kind, verdict, reason, by, at`). A proposal never writes a ruling; only your tags or typed answers do. In annotations, Red means delete, Green means mislabel, Yellow means hole.
- **Light renders only while you work live.** No Cycles in your live window; bakes run in a niced headless worker.

## 2. The steps

`lampway_armor_piece_pipeline` holds the table below in your order, checks the order laws, keeps an append-only run record with artefact hashes, and returns each step's tool, arguments and state. A step that spends is always `needs_approval`: the pipeline never confirms one and never arms a studio.

| # | Step | Tool or action | Credits | Notes |
|---|---|---|---|---|
| 1 | Plates (4 views, 4K) | `tripo.image`, `lampway_plate_pick` | 0 (free quota, still confirmed) | `plate_pick` ranks regenerated plates against the approved reference by silhouette IoU, structure and colour, and cuts the alpha deterministically; it ranks, you pick |
| 2 | Seed meshes | `tripo.mesh`, `tripo.fetch`, `lampway_seed_catalog` | 100 | one paid generation, 4 variants at maximum polycount, then catalogued with stage, model and settings |
| 3 | Fetch and catalogue the seeds | `tripo.fetch` plus the catalogue | 0 | scores matched by `<dir>/<stem>`, verdicts logged |
| 4 | Seed audit (proportions first) | `lampway_seed_audit` | 0 | measures every seed (fold and topology counts, a closed-bowl detector, boundary and non-manifold edges) and ranks by proportions, then defects, then fidelity. A lineup renders every seed the same way. Only your `record` writes a verdict |
| 5 | Proportion score | `lampway_proportion_ratios` (chest), `lampway_piece_ratios` (helmet, waist, boots, gauntlets) | 0 | scale-free landmark ratios against the body. `piece_ratios` is not yet falsified by an independent audit |
| 6 | Provisional fit and closest pose | `lampway_fit_place`, `lampway_pose_clearance`, `lampway_fit_pose` | 0 | placement by enclosure with one uniform scale. Pose solving is built for the chest only; the other kinds answer `needs_decision` because the degrees of freedom are yours to rule |
| 7 | Region fixes and matched-view audit | `lampway_mesh_defect_scan`, `lampway_silhouette_compare`, `lampway_qa_*` | 0 | typed defect candidates (open loops, floating shells, self-intersections, thin features, flipped shells, degenerate faces); never an edit. The exact-box Edit Mesh retry is not an action (it needs your approval flag) |
| 8 | Clone, then Smart UV | `tripo.uv.*` (select, clone, unwrap, retry, collect, score, pick, save) | 20 | a geometry step; unwrap needs a fresh clone and a price of 20 read back; a hung job is never re-clicked |
| 9 | UV score and mesh-QA patches | `lampway_uv_score`, `lampway_rebuild` | 0 | utilisation, overlap, stretch, flipped faces, seam length, a composite and per-gate results |
| 10 | Parts | `lampway_transfer_parts`, `lampway_parts_critique`, `lampway_apply_part_fixes`, `lampway_split_relief` | 0 | carry an approved part set onto a new seed; a critique flags weak islands before you see them |
| 11 | Openings (a geometry step) | `lampway_fit_openings` | 0 | per cap a typed decision: keep, delete, or **gasket** (cut the posed limb's cross-section plus clearance, delete the inside, form a short rolled collar). The collar depth is your number: without it, `needs_decision`. Runs on the posed body only |
| 12 | Mesh-paint | `lampway_meshpaint` | 0 (free quota) | four clay views, the image model paints your design over **your** mesh, ranked by silhouette IoU, then projected |
| 13 | Studio texture | `tripo.texture` (8K, Remove Lighting) | 30 | keeps the UV layout and the face count. State, refs and restore are free actions |
| 14 | PBR, palette and engine set | `tripo.pbr`, `lampway_palette_fit`, `lampway_pbr_pack`, `lampway_pbr_merge` | 5 | fit the per-class hue, saturation and value to the mesh-paint albedo (median in sRGB), then ORM, Normal DX and GL, BaseColor |
| 15 | Export | `lampway_export_piece`, `lampway_asset_acceptance` | 0 | FBX plus `Textures/` plus a README naming each file, its role and its sha256 |

Cost per piece: **about 155 credits** (100 + 20 + 30 + 5). Image work uses the free quota; rerolls, Edit Mesh retries and History restores are free. These are read-back prices from the studio, not bills: no studio generation has been run by the project's builds.

Step 6 and 11 sit before texturing on purpose: placement, pose and openings change geometry, and a geometry change discards a texture.

## 3. The fit phase

After the piece exists, it is fitted to the character body and bound to the skeleton:

| Tool | What it does | Honest gaps |
|---|---|---|
| `lampway_fit_body` | the body as one hashed package (joints parents-first, vertices, optional weights) | weights need a sidecar file; no engine-editor leg |
| `lampway_weight_audit`, `lampway_weight_cleanup`, `lampway_weight_transfer` | audit weights (unweighted, over-influenced, side checks), clean a copy (normalise, limit to 4, with a refusal when 40 % of mass would be zeroed), transfer weights with an algorithmic and a robust (biharmonic) engine | the robust engine runs in the science Python (libigl, robust_laplacian); `mirror_from` is refused |
| `lampway_garment_clearance` | signed distance from the piece to the posed body, per pose, with class tolerances | |
| `lampway_fit_bind` | bind by your weight laws: roles required, metal rigid on one bone, blends refused for metal, seams and rigid groups, a seam-opens gate at apply | the fit-pose bind-and-return deformation and the profile data files are not built |
| `lampway_fit_validate` | measure a bound piece through poses against its **original** shell, then judge: rigid residual with the scale fixed, strain, seam gap, crossings with a crossing control; verdicts PASS, FAIL, UNVERIFIED, REFUSED or UNPROVEN | the receipt is `lampway.armour-validation/1`; the engine leg and captured poses are not built; limits are **proposed**; cloth, leather and embroidery have none, so they read UNVERIFIED, never PASS |
| `lampway_fit_export` | the rigged export behind gates (a validation, roles, texture hash chain, unknown bones) with a read-back of every joint's position **and axes** | the UE-frame bind comparison is not built |
| `lampway_skeleton_export_check`, `lampway_engine_import_check` | an FBX written by the real binary and read back: leaf bones, missing and extra bones, 100x scale, posed rest, header version, collision names, missing textures | `engine_import_check` does not yet consume the engine-project adapter |
| `lampway_fit_glove`, `lampway_fit_state` | the glove's plate labels as a typed decision; the fit-state loop | pose and bind for the glove, and fit-state, answer `needs_decision` (open questions for the maintainer) |

Fit rules worth knowing: the 7.3 cm seam tear a plate used to hide is now caught (`rig_armor` fails above a 1 cm seam gap, measured between shells that were within 2 cm at rest), and a rigid plate is also judged against the **posed** body, which is the only check a rigid plate can fail.

## 4. Running it

Use the agent: ask it to plan a piece with `lampway_armor_piece_pipeline` and it returns the 15 steps, their order laws, the credit plan and what each step needs. Each paid step then waits for your click in the Studios panel ([spend](spend.md)). Every step also works on its own from the Lampway tab (Mesh QA, Rebuild, Mesh-paint texturing, Parts and proportion tools, Studios, Features) or from an external AI app over MCP ([tools](tools.md)). The generated tool pages in [tools](tools.md) quote every tool's inputs and refusals.

## 5. Known gaps

- No real piece has been fitted end to end with the wave 2-3 tools; the tests use synthetic shapes.
- Studio actions (Tripo browser and REST, Meshy, Hi3D, Hyper3D) have never run live.
- One material per piece: parts are not yet material slots. The QA candidate renders need a thicker highlight and cameras past occluders.
- The engine editor leg: import into the engine, validate the skeleton there, publish.
- Thresholds (seam, clearance, thin-wall, silhouette IoU floor, asymmetry) are proposed placeholders.
