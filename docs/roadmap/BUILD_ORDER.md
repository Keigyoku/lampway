# Lampway build order: merged from the five spec audits (2026-10-05)

Sources: specs/{mixar_docs (34), wiki (76), resources (10), shelf (21), generation (22)}/INDEX.md, plus specs/prompts/PROMPT_LIBRARY.md.
Where several areas specify the same tool, the MERGE column names every contract. Build ONE tool satisfying all of them, and make
its tests cover each contract's acceptance evidence. Laws: CONTRACT_TEMPLATE.md. Work wave by wave; within a wave, follow the
dependencies in the contracts. Each wave ends with a pushed lp/* branch, a report and a build path for the coordinator.

## Wave 0: correctness defects in shipped tools (found by reading the code; fix first, RED-first)
| defect | where | found by |
|---|---|---|
| asset_acceptance identity gate is hard-coded to pass | features/workflows.py:93 | wiki |
| rig_armor rigid-mode stretch check cannot fail; pose set has 4 poses vs the wiki's 8 | features/rig*.py | wiki |
| bind_to_armature transfer takes weights from a GLB copy and ignores roles and seams; rig_armor accepts stretch < 1.35, which passes the captain's measured 7.3 cm cuirass seam tear | features/rig.py, workflows | shelf |
| auto_rig parents and mutates the source mesh (rig_armor copies it) | features/rig.py:143 | mixar_docs, wiki |
| mesh_prep never flags a flipped open shell; its hash ignores UVs | features/mesh_prep* | wiki |
| tripo_regen is bundled server-side with no action row, so the Studios panel cannot reach free rerolls | studios/service.py:27, actions.py | shelf, wiki |
| detail_normals.py is a finished module with no tool, Def or operator | texlib port | shelf |
| (done) imagegen endpoints parse / size passthrough | b0b107b5 lineage | generation |

## Wave 1: infrastructure everything else needs
| tool | merge | notes |
|---|---|---|
| prompt library | specs/prompts | in progress (lp/prompts) |
| job_services registry | mixar_docs/job_services | the Client has 21 job types and the server serves image_gen + video_gen; a registry lets each later tool light up its tab |
| asset_lineage | wiki/asset_lineage | one source-hash record per artefact |
| experiment_ledger | wiki/experiment_ledger + prompt run log | ONE ledger: runs, gates, ratings, costs |
| workflow_graph | wiki/workflow_graph | composites run as typed step graphs over the tools |

## Wave 2: armour pipeline to the engine set (the captain's piece runbook, in order)
| tool | merge |
|---|---|
| plate_pick / plate_prep | shelf/plate_pick, wiki/plate_prep |
| seed_catalog | shelf/seed_catalog, wiki/seed_catalog |
| seed_audit (+ lineup) | shelf/seed_audit, wiki/seed_audit_brief |
| tripo.regen actions | Wave 0 row + shelf INDEX |
| proportion_score (piece_ratios) | shelf/piece_ratios, wiki/proportion_score; carry the auditors' scorer fixes: plume-tail depth, wrist mid-palm, a pair split per boot |
| uv_score | shelf/uv_score, resources/uv_score, wiki/uv_score |
| uv_texel_density | resources/uv_texel_density |
| mesh_defect_scan | wiki/mesh_defect_scan (on meshqa) + qa_propose (built) |
| silhouette_compare | wiki/silhouette_compare |
| parts_critique | shelf/parts_critique |
| fit_place, fit_pose, fit_openings | shelf/fit_*, wiki/opening_gasket; these run BEFORE mesh-paint and texture (a geometry change discards texture) |
| palette_fit | shelf/palette_fit, wiki/palette_match |
| studio_texture_flow | shelf/studio_texture_flow |
| bake_maps | mixar_docs/bake_maps, resources/bake_maps, wiki/bake_maps (headless niced Cycles subprocess, never in his live Blender) |
| pbr_pack | wiki/pbr_pack, mixar_docs/pbr_gen |
| armor_piece_pipeline (composite) | wiki/armor_piece_pipeline, keeping the CAPTAIN's order |

## Wave 3: fit, bind and export to UE
| tool | merge |
|---|---|
| fit_body | shelf/fit_body |
| garment_clearance | wiki/garment_clearance |
| weight_transfer | resources/weight_transfer (needs libigl + robust-laplacian, which waits on the captain) |
| weight_audit, weight_cleanup | wiki |
| fit_bind | shelf/fit_bind, wiki/rig_armor |
| fit_validate | shelf/fit_validate |
| fit_export, skeleton_export_check, engine_import_check | shelf/fit_export, wiki/* |
| fit_glove, fit_state | shelf |

## Wave 4: animation
| tool | merge |
|---|---|
| anim_reference_render | generation |
| anim_clip | generation/anim_clip, with the prompt-library templates (side-track walk with a grid floor, in place, split, loop, motion transfer) |
| anim_check | generation/anim_check, wiki/motion_clip_audit (+ root speed from the grid parallax) |
| animation_retarget | mixar_docs/animation_retarget, resources/animation_retarget, wiki/motion_retarget |
| anim_loop_export | generation |
| **anim_multiview_fit (PRIMARY tracker)** | generation/anim_multiview_fit.md: a split-screen front+side clip, per-panel 2D joints, orthographic triangulation, two-view silhouette analysis-by-synthesis. Depth and leg identity come from the second view; no heavy model |
| anim_track (model slots) | generation/anim_track + anim_track_research.md: GEM-X, hosted SAM 3D Body (Higgsfield/fal), Uthana as initialisers and comparisons |
| anim_from_video (composite) | generation, wiki/animation_pipeline |
| video presets (bulk/loop/motion transfer/edit/upscale) | generation/video_* |

## Wave 5: Mixar parity, the rest
retopo (+ AutoRemesher method), uv_unwrap extensions, uv_rectify (Mio3), uv_layout, segment_mesh (island_labels), image_to_3d +
segment_image, texture_gen, scene_cleanup (9 checks), batch_export (the Client's export_package), procedural_library (~40 metals
first), layered_material, material_bake_export, camera_shot, asset_search, mcp_connect, Meshy and Hi3D drivers
(studio_meshy_driver, studio_hi3d_driver; needs the captain's logins).

## Wave 6: waits on the captain's scope word (do not start)
character_pipeline, modular_character, cloth_garment_sim, secondary_chain_rig, face_rig_validate, cinematic_shot_plan,
playblast_capture, level_blockout, traversal_check, splat_*, print_*, lod_chain, glb_optimize, vehicle_wheel_rig, profile_revolve,
material_experiment, motion_experiment, motion_generate (text-to-motion; needs a provider), and the remaining P3 rows.

## Decisions owed by the captain (block the rows named)
1. Fit: gasket flange length; what "manifold it" means; the boots scale anchor; whether the fitted example is still an input
   (09-29 law vs 09-30 native-body ruling); Laya / fit model for fit_state; the material role per part. (Wave 2-3 fit rows)
2. Body tracking: MHA is Windows-only. Choose a Windows box for MHA, a paid tracking service, or a local SAM 3D Body exception
   (80 % legs, below the 85 % gate). (anim_track)
3. OpenRouter dollar spend: a per-call click, or the session and job caps are enough? (all OpenRouter generation)
4. Installs: libigl + robust-laplacian in the science python (weight_transfer); an AutoRemesher Qt-free CLI build vs the AppImage
   download. (Waves 3, 5)
5. Providers: a text-to-motion host; MetaTailor / Rodin / Modddif / 3D AI Studio in scope?; Meshy and Hi3D logins. (Waves 5, 6)
6. Scope: does game armour need outfits/cloth, splats, printing or cinematics? (Wave 6)
7. Thresholds only he owns: thin-wall, the silhouette IoU floor, clearance targets, budget table. (Waves 2-3 gates)
