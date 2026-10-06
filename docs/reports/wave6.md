# Wave 6 (the captain's "let's walk the talk"): the WAITING contracts of Wave 6 and the remaining P3 rows, on branch lp/wave6

Base: `lp/wave5` at 00d907d4. Build path: the lane's own native binary `blender-lanes/wave6/Prod/bin/mixar` (`LAMPWAY_BIN`) for the client tests;
the server suite with `venv-tools`. Exploration: the code graph refused to index this worktree ("a pre-coordination or unverified CBM generation is
active", three attempts, full and fast); the `lampway-harden` snapshot in the graph was used for orientation and `git grep` / reading for the current tree.

## Scope: what STATUS classes WAITING for Wave 6 or "remaining P3 rows"

29 contracts. Four more WAITING rows are NOT Wave 6 (each waits on another captain decision) and are left alone: `fit_glove`, `fit_state`
(decision 1), `anim_track` (decision 2), `model_serving_recipes` (cloud D4).

Rules applied to every contract: a UE editor leg is stubbed `needs_decision` (the Blender-to-UE render parity exploration comes first); a paid or keyed
service gets a fake transport and a `needs_key` / `needs_approval` stub for the live leg; network goes through `egress_consent`.

## Ordered list (kept updated; state per row)

| # | contract | pri | side | state |
|---|---|---|---|---|
| 1 | wiki/modular_character | P1 | Blender | done |
| 2 | wiki/character_pipeline | P1 | Blender (plan) | done |
| 3 | wiki/playblast_capture | P2 | Blender | done |
| 4 | wiki/cinematic_shot_plan | P2 | server | done |
| 5 | wiki/lod_chain | P2 | Blender | done |
| 6 | wiki/material_experiment | P2 | server | done |
| 7 | wiki/motion_experiment | P2 | Blender | done |
| 8 | wiki/secondary_chain_rig | P2 | Blender | done |
| 9 | wiki/cloth_garment_sim | P3 | Blender || done |
| 10 | wiki/face_rig_validate | P3 | Blender || done |
| 11 | wiki/glb_optimize | P3 | Blender || done |
| 12 | wiki/traversal_check | P3 | Blender || done |
| 13 | wiki/level_blockout | P3 | Blender || done |
| 14 | wiki/part_budget_plan | P3 | Blender || done |
| 15 | wiki/platform_budget_check | P3 | Blender || done |
| 16 | wiki/print_check | P3 | Blender || done |
| 17 | wiki/print_prep | P3 | Blender || done |
| 18 | wiki/profile_revolve | P3 | Blender || done |
| 19 | wiki/prototype_gates | P3 | server | done |
| 20 | mixar_docs/scene_from_image | P3 | Blender || done |
| 21 | mixar_docs/terrain | P3 | Blender || done |
| 22 | mixar_docs/addon_project | P3 | Blender + server || done |
| 23 | wiki/editor_connection_receipt | P3 | Blender || done |
| 24 | wiki/vehicle_wheel_rig | P3 | Blender || done |
| 25 | mixar_docs/splat_world (generate half) | P3 | server || done |
| 26 | wiki/splat_collision_proxy | P3 | Blender || done |
| 27 | wiki/texture_route_select | P3 | server | done |
| 28 | resources/material_palette | P3 | Blender || done |
| 29 | resources/motion_generate | P3 | Blender || done |

traversal_check moved ahead of level_blockout (the blockout calls it).

## Contracts

### 1. modular_character (P1): done
- Where: `features/modular_character.py`, api `modular_character` (via `api_wave6.py`), Def `lampway_modular_character` (`agent/wave6_tools.py`).
- Actions: manifest (the template's eleven fields), validate (one armature, rest pose unchanged, equal scales, measured vs declared side, weight_audit on
  deforming parts), outfit_matrix (rays from body faces along normals; the region = what any outfit covers; poke-through within 2 cm on a garment's outer
  side), hidden_body (a copy; refused with no matrix, a failing one, or a stale one), export_parts (one FBX per part with the armature).
- Tests: `tests/lampway_tools/test_wave6_modular_character.py` (9, real binary). RED observed: "no tool function 'modular_character'". The contract's
  three tests plus its falsifier (the gap covered gives zero). Mutants killed: poke-through sign, the stale-matrix stamp, the union region, the side
  check, the side axis.
- Shared seams added: `api_wave6.py` (plain functions wrapped by api.py's `@tool` loop, so they pass the one door), `agent/wave6_tools.py` (appended to
  DEFS), `P.items` (an array's item schema; `parts` is a list of objects). Pinned by `tests/lampway_tools/test_wave6_door.py` and
  `server/tests/test_wave6_tools.py` (both mutated RED: the registration loop removed, the items branch disabled).
- [UNVERIFIED] the cover range (0.3 m) and poke-through range (2 cm) are mine; the contract gives none. Open (the contract's): whether Titan needs
  swappable outfits at all.

### 2. character_pipeline (P1): done
- Where: `pipeline/character_pipeline.py` (pure python), api `character_pipeline`, Def `lampway_character_pipeline`.
- Thirteen stages with their tools; `missing_tools` is read from the live door (`api.TOOL_FUNCS`), so stage 4 (mirror_pair, mesh_join_boolean: STATUS
  orphans) reads `no_tool` until those exist. Spend stages 2 (tripo.mesh, 100 per part) and 8 (tripo.texture, 30 + 5 PBR) are `needs_approval`.
  record: a stage needs the stage before it passed; rigging (9-11) needs the assembly passed ("fit before rigging"). run: executes the given calls per
  stage through `api.call`, stops at a failed gate, a spend stage (never called) or a missing tool; a call naming another stage's tool is refused.
- UE leg: target `metahuman` returns the MetaHuman conform as `needs_decision` (a UE editor action; the UE leg waits on the parity exploration).
- Tests: `test_wave6_character_pipeline.py` (8 pure python + 1 real binary). RED observed: ImportError (module absent). The contract's three tests
  plus the falsifier (the same run passes when the gate passes). Mutants killed: the rig-before-assembly law, the gate reader, the spend stop, the
  previous-stage law, credits per part.
- Open (the contract's): is the MetaHuman conform in scope for the Lampway hand-off or only the captain's UE side.

### 3. playblast_capture (P2): done
- Where: `features/playblast.py` (beside `features/video.py`, reusing its engines and frame cap), api `playblast_capture`, Def `lampway_playblast_capture`.
- Per shot: frames [a, b] from a named camera or waypoints (look_at an object or a point), PNG per frame, H.264 mp4 encoded by a throw-away scene's
  sequencer, first/last stills copied from the very frames encoded, `shot_list.json` with sha256. Refusals: length vs planned duration beyond one frame,
  Cycles, unknown camera, a hidden `scene_objects` entry, duplicate names, > 1200 frames.
- Finding (measured): a throw-away scene that links the user's collection does NOT evaluate the user's animation at its own frame (`render_video`'s
  approach): a ball keyed from x = -1.5 to 1.5 rendered at its current position on every frame of the temp scene (centroid 0.757 at frames 1 and 12;
  the home scene gives 0.224 and 0.753). So each frame is reached with the user's scene `frame_set` (restored afterwards). `render_video` itself is
  not affected for its own use (it animates only its own camera), but it cannot playblast a posed, animated blockout.
- Tests: `test_wave6_playblast.py` (4, real binary). RED observed: "no tool function 'playblast_capture'". Then a real RED on the first build: the
  stills were identical (the finding above). `test_feature_video.py` stays green. Mutants killed: the user-scene frame_set, the one-frame slack, the
  last still taken from the first frame.

### 4. cinematic_shot_plan (P2): done
- Where: `server/lampway_server/cinematic.py` (pure), agent tool `lampway_cinematic_shot_plan` in the new server-run module `agent/plan_tools.py`
  (dispatched by `turns._run_tool`; `script_for` refuses it as server-run, like the ledger and asset tools; not offered over MCP: it needs the
  server's video catalogue).
- plan: one action and one camera move per shot (a second clause joined by and / then / while / before / after or , ; & + is refused), character
  references must name both wearer sides, the wiki's prompt template per shot, five stages with image_edit and video_generate `needs_approval`, the
  video price from the model's own `pricing_skus` through `videogen.estimate` (unknown stays unknown; a Higgsfield model is read back at the confirm;
  no OpenRouter catalogue = `needs_key`), the total, the shortest shot first. split: two actions, durations summing to the shot's, the second starts
  from the first's end frame. review: typed pass/fail on identity, doubling, action_order, camera -> chain | split | redo.
- Tests: `server/tests/test_wave6_cinematic.py` (7). RED observed: ImportError, then "lampway_cinematic_shot_plan not in TOOL_NAMES" for the
  dispatch test. Mutants killed: the one-clause rule, the right-side check (a survivor first; a "left only" case added), the price sum, shortest
  first, the split's second action.
- Not run: no live plan against the OpenRouter catalogue (no key on this box; the fake catalogue row carries a `duration_seconds` SKU).

### 5. lod_chain (P2): done
- Where: `features/lod_chain.py`, api `lod_chain`, Def `lampway_lod_chain`.
- Collapse Decimate on copies (`<name>_LOD<n>`, tagged; a re-run replaces only this tool's own LODs), the protect group plus every UV-split vertex as the
  inverted vertex group (zero weight is never collapsed). Per LOD: faces, `max_deviation_rel` (symmetric vertex-to-surface over the source diagonal),
  `silhouette_iou` (front and left from the source's cameras, the smaller; `silhouette._render_mask`), `weight_audit_pass` when skinned, textures
  downsized per LOD (materials not rewired). Refusals: ratios not strictly decreasing or outside 0.05..0.9, texture_scale length, a skinned mesh
  without `protect` (the contract's sentence).
- Tests: `test_wave6_lod_chain.py` (6, real binary). RED observed: "no tool function 'lod_chain'". The contract's three tests and its falsifier
  (protect everything: the count stays above the ratio). Mutants killed: the inverted protect group, the seam set, the skinned refusal, the texture
  scale; the deviation's lost-detail direction SURVIVED the first suite (both directions grow on a sphere) and was killed by a spike test.
- [UNVERIFIED] engine LOD naming (the contract's open question); the engine import is the captain's.

### 6. material_experiment (P2): done
- Where: `server/lampway_server/material_experiment.py`, agent tool `lampway_material_experiment` (`agent/plan_tools.py`, server-run).
- plan: rows T1..L1 with the Studio action and expected credits from `studios.actions` (tripo.texture 30); meshy.retexture and hi3d.texture_only exist
  as REST drivers (fake transport only, never live) with unpublished prices read back by their plan; 3dai_prism and Material AI have no driver: the
  wiki's documentation prices (20, 10) marked [UNVERIFIED], plan-only. Rows an engine cannot express (T3 needs a seed control, T4 an alignment
  control; only Prism has either, per the wiki) are refused when asked and listed as skipped from the default set. run: never spends; a
  needs_approval card for `lampway_studio_plan`; refused without a driver, without a passing asset_acceptance, T2/T3/T4 before T1, and after any
  identity or fit failure (the stop rule). record: one experiment-ledger row (stage texture, seed not_exposed unless the engine has one, the
  read-back price with its source, by agent). compare: texel RMS T1 vs T2 / T3 with verdicts.
- Tests: `server/tests/test_wave6_material_experiment.py` (9). RED observed: ImportError. The contract's four tests and its falsifier (T1 passes,
  the run continues). Mutants killed: the dispatch name, the stop rule, the T1-first law, the acceptance gate, the RMS, the explicit-row refusal.
- Limit: the server cannot re-run asset_acceptance (a Blender tool); `run` trusts the posted result and copies its object and mesh hash into the card.
- Not run: no live Tripo texture (spend; the captain's click). Open (the contract's): whether T2 (an exact 30-credit repeat) is wanted at all.

### 7. motion_experiment (P2): done
- Where: `features/motion_experiment.py`, api `motion_experiment`, Def `lampway_motion_experiment`.
- A is keyed from the brief (start at frame 1, an optional contact pose, end at the duration; the contact landmark is a pose marker), in each bone's
  OWN rotation mode; B and C (imported actions) must reproduce the start and end poses within 0.5 deg [UNVERIFIED tolerance] or the call is refused.
  Per variant: frames, duration, start/end/contact pose error, the largest angular speed and acceleration; the comparison table; `grade.smoothest`
  (a measurement, a person picks); `seed: not_exposed`. No generative-motion driver (the contract's model slot needs a service the captain names).
- Real RED on the first build: A was keyed on `rotation_euler` of bones whose mode is QUATERNION (the default), so the action drove nothing (frame 1
  read 45 deg). Fixed by keying in the bone's own mode. A "frame_set to the current frame does not re-evaluate" guess I wrote into a comment was
  falsified (the suite passes without it) and removed.
- Tests: `test_wave6_motion_experiment.py` (4, real binary). RED observed: "no tool function 'motion_experiment'". The contract's three tests and its
  falsifier (B with a shifted end is refused; the same B ending on the pose is compared). Mutants killed: the pose tolerance, the foot-contact
  refusal, the end key, the contact marker frame, the speed metric.
- Not written: ledger rows per variant (the contract lists experiment_ledger as a dependency, its outputs do not); the motion_clip_audit is
  replaced by the per-frame measurements above because anim_check (where motion_clip_audit folded) measures tracked video, not actions.

### 8. secondary_chain_rig (P2): done
- Where: `features/secondary_chain.py`, api `secondary_chain_rig`, Def `lampway_secondary_chain_rig`.
- On copies (`<armature>_chain`, `<object>_chain`): a connected chain along the region's principal axis (PCA) from the end nearer parent_bone; region
  weights interpolate between control points (the parent at the root, each chain bone at its middle), every other influence removed and counted;
  DAMPED_TRACK preview constraints; capsule colliders per body bone (radius = its farthest dominated vertex from the segment, parented to the bone);
  "numeric presets are not provided". Refusals: > 24 bones, unknown parent bone (lists them), a region under 4 vertices, a base rig failing
  weight_audit (the contract's precondition).
- Tests: `test_wave6_secondary_chain.py` (5, real binary). RED observed: "no tool function 'secondary_chain_rig'". A fixture bug (the torso's back
  face at y = -0.15 fell on the region boundary) was fixed in the test, not the tool. Mutants killed: competing-influence removal, chain direction,
  connection, collider radius; the audit precondition SURVIVED the first suite and got its own test.
- [UNVERIFIED] engine naming for physics chains (the contract's open question).

### 19. prototype_gates (P3): done
- Where: `server/lampway_server/prototype_gates.py`, agent tool `lampway_prototype_gates` (`agent/plan_tools.py`), and a public `Ledger.record_event`
  (a row of another kind, secrets refused; experiment/job/run kinds keep their own recorders).
- Passes Core, Look, Feedback, Export in order with allowances and gate texts; may_spend refused until every earlier pass passed ("Core has not
  passed: <gate>"), when the pass allows no generation, or when the allowance is used; an allowed answer uses one generation. An agent's pass on a
  captain-owned gate is `proposed` (with evidence; refused without) and passes nothing; the agent tool forces `by: agent` whatever the call says.
- Tests: `server/tests/test_wave6_prototype_gates.py` (6). RED observed: ImportError. Mutants killed: the earlier-pass law, the allowance, the
  proposed state, the forced agent identity.
- Gap: the captain's own door for a captain-owned gate (a Client button or REST route) is not built; the module accepts `by: captain` for it.

### 27. texture_route_select (P3): done
- Where: `server/lampway_server/texture_routes.py`, agent tool `lampway_texture_route_select` (`agent/plan_tools.py`).
- The wiki's five rows as data; `driver_exists` read from `studios/actions.py` and `tool_exists` from the agent's Lampway Defs at every call; shape_fix
  never carries a texture route; engine_available marks what can be used.
- Disagreement with the contract, recorded: its test is named `test_keep_uv_marks_meshy_as_no_driver`, written when Meshy had no driver. Wave 5 added
  the Meshy REST driver (`meshy.retexture`, fake transport only), and the contract's own acceptance says the flags must match `studios/actions.py`, so
  the test asserts the registry (True today) and its falsifier deletes the action (False).
- Tests: `server/tests/test_wave6_texture_route.py` (6). RED observed: ImportError. Mutants killed: a texture route in shape_fix, a hand-set driver
  flag, a hand-set tool flag.

### Shared changes in this batch
- `agent/tool_defs.py`: `Def` and `P` moved out of `lampway_tools.py` (re-exported there), because importing `wave6_tools` first hit a circular import
  (`cannot import name 'DEFS' from partially initialized module`, found by the docstring pin test).
- `agent/wave6_tools.py` is now GENERATED from `api_wave6.py`'s docstrings (`scripts/lampway/gen_wave6_defs.py`) and pinned by
  `test_wave6_door.py::test_every_def_description_is_its_functions_docstring_word_for_word` (mutated RED: one word changed in a docstring).
- `features/common.need_object`: a Gaussian splat (a point object with `splat_opacity` and no faces) is refused by every mesh tool that asks for a mesh
  ("a splat has no faces: mesh tools refuse it"), per splat_world section 4. `splat_collision_proxy` looks the splat up itself.
- Mutation runs use a helper that restores the original bytes from memory and checks them, after a cleanup bug of mine deleted the scratch directory
  (see "Incidents").

### 9. cloth_garment_sim (P3): done
- `features/cloth_garment.py`; a copy `<garment>_draped`, Blender cloth with the pin group as the mass group, the body's Collision modifier for the bake
  only, frames 10..250 plus a 120 s wall-clock budget, the last frame baked to a static mesh, `max_distance` group (0 at the pins, linear to 1 at
  max_distance_m). Refusals: metal (param or `lw_material_class`), an armature-bound garment, an empty/missing pin group, ranges.
- Tests `test_wave6_cloth_garment.py` (4). RED: "no tool function". Mutants killed: pins off, metal check, penetration sign, the collision modifier
  left on the body. The fixture's pin strip was too narrow (3 vertices) and was widened. Numeric defaults are [UNVERIFIED] placeholders, as the
  contract says.

### 10. face_rig_validate (P3): done
- `features/face_rig.py`; the ARKit 52 and 15 viseme names written from the public specifications (viseme_I/O/U for Oculus's ih/oh/ou) [UNVERIFIED
  against the resources: no copy in the tree]; landmarks are the vertex groups lip_upper, lip_lower, brow_l, brow_r; six expressions measured on the
  evaluated mesh, every shape value restored (pinned against values the user left set). VRM bindings: `not_checked` without the VRM add-on.
- Tests `test_wave6_face_rig.py` (4). RED: "no tool function". Mutants killed: the teeth sign, the ARKit list, the restore, the closed-mouth refusal.
  Thresholds (1 mm closed, 1.5 x neutral wide, 2 mm brow) are mine [UNVERIFIED].

### 11. glb_optimize (P3): done
- `features/glb_optimize.py`; Blender's glTF add-on in a throw-away scene: images downsized and re-packed, Draco, WebP at a quality; the output is
  re-imported and compared (deviation, SSIM, animation count/ranges/positions); everything imported is removed. meshopt refused (glTF Transform).
- Tests `test_wave6_glb_optimize.py` (3). RED: "no tool function". Mutants killed: no downsize, the animation flag, in-place.

### 12. traversal_check (P3): done
- `features/traversal.py`; BVH rays: ceiling, ground (gap edges bisected), slope, step rise, wall probes at knee and mid height plus sideways (a wall
  hit is reported as a step when something stands within capsule height). Player values required (none built in).
- Tests `test_wave6_traversal.py` (7). RED: "no tool function" (the first assertion read KeyError 'sightlines' from the error dict). The step-rise
  check SURVIVED the first suite (the knee probe also catches steps) and was killed by a 0.33 m kerb under the probe height. Mutants killed: ceiling,
  gap width, slope, step rise.

### 13. level_blockout (P3): done
- `features/level_blockout.py`; named sets as collections, box/ramp/stair primitives (riser under 0.9 x max_step), the route polyline (edges only),
  three cameras, traversal_check on the result; the scale anchor is a named primitive's longest side.
- Tests `test_wave6_level_blockout.py` (3). RED: "no tool function". Mutants killed: the anchor factor, the metres refusal.

### 14. part_budget_plan and 15. platform_budget_check (P3): done
- `features/budgets.py`; no built-in budget table; triangles count n-gons as n - 2; the largest image texture per object. Platform table dated
  2026-10-05 (Roblox rigid and layered from the two resources; ue_static has no documented limit in the sources: use custom); stale after 90 days
  [UNVERIFIED policy]; Roblox cage names `_InnerCage`/`_OuterCage` [UNVERIFIED].
- Tests `test_wave6_budgets.py` (4). RED: "no tool function". My fixture assumed icosphere subdiv 5 = 20480 faces; Blender's is 5120 (the test was
  wrong, fixed). Mutants killed: over_by, stale, the texture budget.

### 16. print_check and 17. print_prep (P3): done
- `features/printing.py`; print_check in millimetres (manifold, BVH self-overlap excluding neighbours, isolated faces, inward-ray wall thickness,
  overhang excluding the plate, shells, printer volume). print_prep: a copy, optional exact-boolean base, merge/normals, decimate to max_faces, scaled
  to the target height in mm, STL per part, gated by print_check (thin walls or an open shell: nothing written), copies removed.
- Tests `test_wave6_print.py` (7). RED: "no tool function". Mutants killed: intersections, thin walls, the plate exclusion, the thin refusal, the
  millimetre scale. The 3D-Print Toolbox cross-check (the acceptance evidence) was not run: the extension is not installed here.

### 18. profile_revolve (P3): done
- `features/profile_revolve.py`; bmesh spin, seam merged, poles welded, optional vertex bevel, outward normals, manifold and open edges reported.
- Tests `test_wave6_profile_revolve.py` (4). RED: "no tool function". Mutants killed: pole weld, normals, the negative-radius refusal.

### 21. terrain (P3): done
- `features/terrain.py`; a per-terrain copy of the geometry-nodes group (4D noise, Attribute Statistic min/max mapped to 0..height), carve commits
  and lowers with a smooth bank, water plane, vegetation by deterministic ray samples above water and under 35 degrees, capped, instanced through a
  collection; from_image with a blur and a ground-photo heuristic [UNVERIFIED].
- Finding (measured): the geometry-nodes modifier copies its group's input defaults when the group is assigned; defaults set afterwards gave 0 m of
  relief, and `mod[socket_identifier] = value` raises "id properties not supported for this type" in this build. So the defaults are set first.
- Tests `test_wave6_terrain.py` (5). RED: "no tool function". Mutants killed: the falloff, the water level, the instance budget. Biome densities are
  mine [UNVERIFIED].

### 22. addon_project (P3): done
- `features/addon_tools.py` wraps the Client's AddonProjectService (read, stage with the read revision, commit, checks + install, rollback);
  `ui/operators/addon_ops.py` adds `lampway.addon_approve`, the user's click (refused while any script runs, human_gate), the only way a proposal is
  approved; addon_commit refuses anything else. Projects outside the Client's linked registry are refused, listing the linked ones.
- Tests `test_wave6_addon_project.py` (2, real binary, the UI auto-discovery run as the app does). RED: "no tool function". Mutants killed: the
  approval check, the project match. The operator's own gate SURVIVES: `approve()` checks human_gate too (a deliberate double guard).
- Not built: the logredact change the contract asks for. Measured instead: the server never logs tool arguments (`turns._detail` returns "" for
  anything but run_blender_python's first line); no test pins it yet. The approval store is in-process memory; `approve()` refuses while any script
  runs (agent scripts, workers and the bridge run under human_gate), so a script cannot set it.

### 23. editor_connection_receipt (P3): done
- `features/editor_receipt.py`; Blender native (saved copy under the root, else nothing changes; the cube made, seen, removed with its mesh; lists
  compared); unity/godot facts validated and stored; unreal = `needs_decision` (the UE leg waits on the parity exploration).
- Tests `test_wave6_editor_receipt.py` (3). RED: "no tool function". Mutants killed: disposable, identity, the mesh removal. Removing only the
  OBJECT removal is an equivalent mutant: removing the mesh also removes the cube object (measured, the object list still matched).

### 24. vehicle_wheel_rig (P3): done
- `features/vehicle.py`; PCA axle, rim ring (85 % of the farthest distance) that must cover six of eight sectors (a rectangle's corners are
  concyclic: an 8-vertex box first passed the circle fit with zero residual), Kasa circle fit, residual over 5 % refused; copies named per wheel with
  the origin at the centre, parented to bones; axles parallel within 2 deg [UNVERIFIED thresholds and bone naming].
- Tests `test_wave6_vehicle.py` (4). RED: "no tool function". Mutants killed: the sector rule, the residual (after the oval test was made 1.2 x so
  the sector rule does not pre-empt it), the parallel check, the origin shift (after a geometry-did-not-move assertion was added).

### 25. splat_world (P3): done
- Import half: `features/splat_proxy.splat_world_import` (SPZ through the Client's own `world_labs_spz.spz_to_ply`, PLY as is), api tool
  `splat_world`, Def `lampway_splat_world_import`. Generate half: `server/lampway_server/world_gen.py` and the server tool `lampway_splat_world`
  (plan only; `needs_key` without `LAMPWAY_WORLD_LABS_KEY`; with one a `needs_approval` card; only `confirmed_by="user"` runs; bounded polling; files
  under worlds/<job>/; a new egress route `world_labs`, off until opted in). The provider endpoints are [UNVERIFIED] and met only a fake transport.
- Naming deviation from the contract (`lampway_splat_world` for both halves): the generate half is server-run and the import half runs in Blender, so
  they are two tools; the import one is `lampway_splat_world_import`.
- The Client's World Labs tab stays hidden: no world_labs job service is registered (tests/test_job_queue.py already pins the 422).
- Tests: `server/tests/test_wave6_world_gen.py` (5; RED: ImportError), `tests/lampway_tools/test_wave6_splat.py` (SPZ round trip with the Client's own
  SPZ test encoder, run outside Blender because it imports pytest). Mutants killed: the dispatch name, the user-only confirm, the image requirement,
  the egress route, the mesh-tool splat refusal.

### 26. splat_collision_proxy (P3): done
- `features/splat_proxy.splat_collision_proxy`; opacity filter, density per voxel, the faces between solid and empty voxels voxel-remeshed at half a
  voxel (closed, manifold), `UCX_` naming for Unreal, its own collection, mass coverage.
- Tests in `test_wave6_splat.py` (sphere radius, low opacity ignored, slab stays a slab, refusals). Mutants killed: the opacity filter, and the
  density threshold after lone specks were added to the fixture (it SURVIVED the first suite).

### 28. material_palette (P3): done
- `features/palette.py` (numpy + Pillow; bpy only for materials): notable (area bins + hue-family accents, an 8-unit CIELAB floor) and seeded k-means,
  locked colours, coverage summing to 1, CIELAB distance, JSON + swatch, PAL_ materials never overwriting, Pantone refused.
- NOT a port: Img2Mat_Pro's source is not in this tree, so this implements the contract's description of it, and the contract's parity test against
  the add-on was NOT run. The V3 Helmet1 fixture test was not written (the turnarounds sit outside any project root on this box).
- Tests `test_wave6_palette.py` (6). RED: ImportError. The hue-shift test needed a saturated image (a mostly grey one barely moves: measured 5.9).
  The accent pool SURVIVED at first (the area score already favours chroma) and was killed once the accent was speckled across many bins, as a real
  plate's accent is. Mutants killed: the accent pool, the alpha mask, the locked colours.

## Incidents
- My suite runner's cleanup line `find $T -maxdepth 1 -newer ... \( -name 'tmp*' ... \) -exec rm -rf {} +` matched its own start directory
  (`tmp-wave6` matches `tmp*`) and deleted the whole lane scratch directory: the baseline logs, a finished server run's log and my mutation backup
  files. No worktree file was lost (one source file left mutated by the failed restore was put back by an inverse edit and checked). The runner now
  gives every run its own temp root and removes exactly that; mutants restore from memory. The baseline failure list was rebuilt from the run's
  printed output (file-level where a file failed per parameter).
- The coordinator's disk rule (2026-10-06): each run's basetemp is removed when the run ends; the suites also leak lw_* and tmp* directories into
  TMPDIR, now contained in the per-run root.

### 20. scene_from_image (P3): done
- `features/scene_from_image.py`, api `scene_from_image`: masks given or found by segment_image (colour or alpha), each part extruded from its own
  silhouette by image_to_3d, placed under an ASSUMED straight-on camera (image width = scene_width_m, lower = nearer over scene_depth_m, standing on
  z = 0) [UNVERIFIED accuracy], in `<name>_scene`, left to right. studio:tripo: N x 100 credits, one plan, nothing created; model engines refused.
- Tests `test_wave6_scene_from_image.py` (3). RED: "no tool function". The height mutant SURVIVED a strict-order assertion (equal heights differed
  by voxel noise: 0.9618 vs 0.9617) and was killed once each height was pinned to its pixel height. Mutants killed: x placement, height, max
  objects, the plan total. Masks land in scenes/<name>/masks (segment_image never overwrites a different record).

### 29. motion_generate (P3): done
- `pipeline/motion_library.py` (pure: ranker, refusal, model slots, decision rows in the meshqa shape) and `features/motion_generate.py` (index a
  folder, import the pick as `motion_src`, frames/fps read back, a row in motion/decisions.jsonl). Model engines answer needs_provider and open no
  socket (patched to raise in the test).
- Tests `test_wave6_motion_generate.py` (6; the import test builds its own FBX clips in the binary). RED: ImportError. Mutants killed: the
  no-match refusal, the abbreviations (fwd), the decision row, the frames read-back. Not run: the six real shelf clips (the contract's fixture 5):
  they are not on this lane's paths; the rank test uses their names.

### Canonical input (the coordinator's rule, 2026-10-06)
Every Wave 6 tool works in SCHEMA.md's frame: metres, right-handed, +Z up, the body faces -Y, the wearer's left +X (modular_character's side check
and secondary_chain's bone direction head -> next joint already did). The importer calls I added are marked `# LEGACY(normalize): <reason>` until
`canon_io` lands on origin/lp/wave5: glb_optimize's re-import, splat_world's SPZ/PLY import, motion_generate's clip import, lod_chain's texture load
and terrain's heightmap load.
