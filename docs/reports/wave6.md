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
| 5 | wiki/lod_chain | P2 | Blender | |
| 6 | wiki/material_experiment | P2 | server | |
| 7 | wiki/motion_experiment | P2 | Blender | |
| 8 | wiki/secondary_chain_rig | P2 | Blender | |
| 9 | wiki/cloth_garment_sim | P3 | Blender | |
| 10 | wiki/face_rig_validate | P3 | Blender | |
| 11 | wiki/glb_optimize | P3 | Blender | |
| 12 | wiki/traversal_check | P3 | Blender | |
| 13 | wiki/level_blockout | P3 | Blender | |
| 14 | wiki/part_budget_plan | P3 | Blender | |
| 15 | wiki/platform_budget_check | P3 | Blender | |
| 16 | wiki/print_check | P3 | Blender | |
| 17 | wiki/print_prep | P3 | Blender | |
| 18 | wiki/profile_revolve | P3 | Blender | |
| 19 | wiki/prototype_gates | P3 | server | |
| 20 | mixar_docs/scene_from_image | P3 | Blender | |
| 21 | mixar_docs/terrain | P3 | Blender | |
| 22 | mixar_docs/addon_project | P3 | Blender + server | |
| 23 | wiki/editor_connection_receipt | P3 | Blender | |
| 24 | wiki/vehicle_wheel_rig | P3 | Blender | |
| 25 | mixar_docs/splat_world (generate half) | P3 | server | |
| 26 | wiki/splat_collision_proxy | P3 | Blender | |
| 27 | wiki/texture_route_select | P3 | server | |
| 28 | resources/material_palette | P3 | Blender | |
| 29 | resources/motion_generate | P3 | Blender | |

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
