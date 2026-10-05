# Lampway: swarm v3, dogfood defects, the online Studios, provider setup (branch lp/studios)

Branch `lp/studios` in `<workspace>/wt-studios`, from `lp/features` plus `lp/subs` (f4691a49, db670330) merged. Own build copy at
`wt-studios/build/Prod` (a copy of the Prod build, python synced with `scripts/lampway/sync_python.sh --bin-dir build/Prod/bin`). Nothing of the
the user's session (wt-harden, 8787, 19881, ~/.local/share/lampway) was touched. My live harness: Xvfb in the lampway-build box, server+bridge on
18790/19880, `LAMPWAY_HOME=scratch/studios-live/home`, OpenRouter on its own spend log (total under $0.10 of the $15 cap).

Tests at the head: **server 351 passed, 3 skipped; client tools (real Prod binary) 324 passed, 11 skipped** (the skips pre-date this pass).
Every commit body carries a RED line. Where a test could not be seen red for the right reason, the section says so.

## 1. Swarm v3 (top priority)

The client already ships Mixar's harness v3; the server now speaks it. Frame shapes and the client code each comes from (the client IS the spec):

| What the server sends / reads | Shape | Client source |
|---|---|---|
| spawn a worker | request `agent.sandbox_control` `{action:"spawn", connection_id:"<parent>-sbx-<n>-<hex>", parent_instance_id, idle_ttl_s}` to the PARENT socket | `bootstrap/sandbox_supervisor.py:251` handle_sandbox_control, `:126` spawn_sandbox; routed at `core/socket_dispatch.py:73` |
| a worker connects | the child opens `/api/agent/ws/<connection_id>` and sends `system.handshake` with `role:"sandbox"`, `parent_instance_id` | `core/socket_connection.py:252` _perform_handshake, `:330` |
| activate a run | request `agent.execution.activate {protocol_version:"v3", run_id, session_id, turn_epoch}`; a newer epoch revokes the prior run; answer `{success, ack, ...}` | `agent_execution/handlers.py:34`, `bindings.py:69` |
| bind a task | `agent.execution.bind_task {run_id, turn_epoch, task_id, generation, attempt, fence_token(int), worker_connection_id, execution_class:"worker"}` | `handlers.py` METHODS `:26`, `bindings.py:209` |
| run a worker script | `blender.execute_script` to the WORKER socket: `session_id = "agent:<connection_id>"`, `agent_ctx.chat_session_id` the same, `params.envelope {protocol_version, run_id, session_id, turn_epoch, task_id, task_generation, attempt(str), fence_token(str), execution_target}`; the worker refuses any other routing session or target | `agent_execution/request.py:34,56` (envelope), `identity.py:44,79`, `headless/headless_main.py:95,112` |
| the only live write | `agent.execution.commit {op:"append_collection", run_id, turn_epoch, task_id, generation, fence_token, operation_id, payload_hash(sha256), artifact_id, content_hash, collection_name, target_collection:"Mixie Agent"}`; answer `{success, state:"applied", receipt}` or a typed refusal (`stale_epoch`, `stale_fence`, `hash_mismatch`, `deferred`...) | `commit.py:117`, fences `bindings.py:244`, target `commit.py:32`, dispatch `handlers.py:41` |
| read receipts | `agent.execution.status {operation_ids}` -> `{operations:{id:{state,receipt}}}` | `handlers.py:38`, `journal.py` ops_status |
| revoke | `agent.execution.revoke {run_id, task_id?}`, then `agent.sandbox_control {action:"shutdown"}` | `bindings.py:174`, `sandbox_supervisor.py:251` |
| the Parallel Agents cards | `agent.turn.event` payload `{bubble_id, todo:[{id, text, status: PENDING\|IN_PROGRESS\|DONE\|FAILED}]}` (the whole list each time) | `core/slot_processor.py:197,478`, projected by `agent_panel/core/cards.py:219,241` |
| run lifecycle | `{type:"run_status", run_id, status:"in_progress"}` first, `{type:"turn_end"}` last (already emitted) | `core/queue_processor.py:79`, `core/turn_events.py:310` |

Server code: `server/lampway_server/agent/harness.py` (protocol), `swarm.py` (rewritten), `ws.py` (handshake records role and parent; a socket that is not a
`sandbox` of THIS parent is never driven, mutation-checked), `turns.py` (todo emission, run id). A task may list `objects`: the parent copies them to a staged
artifact (`staging.export_copies`, a Lampway addition) and the worker loads them (`import_artifact`), so a worker works ON a piece; a worker starts by clearing
Blender's default scene (`reset_worker_scene`, found live: Camera/Cube/Light were staged back as its work); it stages everything it made with
`staging.stage_scene` (a Lampway addition that keeps the worker's own collections, found live: `QA_markers` was flattened away). A model call is bounded
(300 s) so a wedged `claude` CLI fails one worker only.

**The lane-scene path is gone.** The in-process `agentlane:` scenes, `lane_guard.py`, `swarm_lanes`/`swarm_merge` scripts and their tests are deleted; the
client still has lane support for its own foreground fan-out, but nothing on this server needs it.

### Tests (RED, GREEN, what they prove)
- `server/tests/test_swarm_v3.py` (13): RED on the lane swarm = no todo slot ever emitted (cards absent), no `agent.execution.activate`, 0 of 3 collections landed.
  Now: cards per task with live status, v3 conversation order and envelope shape, 3 same-named collections all land, failed worker = FAILED card and no commit,
  refused commit fails that task with the client's reason, unspawnable worker fails not hangs, rogue socket never driven, default scene cleared first, model timeout.
- `tests/lampway_tools/test_agent_execution.py` (6, REAL binary): the shared-`bpy.data` collision reproduced (three by-name draws in one process leave ONE collection);
  three worker PROCESSES stage and all three commit; stale fence / wrong epoch / revoked task / older-epoch activate refused; replay by payload hash applied once,
  different payload refused; journal state `applied`; export/import round trip; `stage_scene` keeps `QA_<piece>`. (The client's own commit/bindings code passed on first run: these are characterisation tests of Mixar's code, not RED-then-fix.)
- `server/tests/fake_harness.py` models the client's activate/bind/commit semantics; it is a model, the real code is the previous bullet.

### Live (Xvfb, three workers, real Blender processes)
`reports/studios-swarm-cards.png`: the Parallel Agents panel bottom-left with three cat-avatar cards (boots / waist / helmet) while the workers run.
Landed tree (read through the bridge): `Mixie Agent / boots / QA_markers [boots_marker]`, `waist / QA_markers.001 [waist_marker]`, `helmet / QA_markers.002 [helmet_marker]`:
three workers each created a collection by the SAME name in their own process, and all three survived. Positions were 1 m above each input piece (inputs were seeded).
Model: deepseek/deepseek-v4.1-flash for main and workers (OpenRouter).

Not run live: workers on `claude_cli` (the user's setup); the swarm is built on `make_swarm_provider`, concurrency is bounded by MAX_WORKERS=6 per swarm,
and a model round times out. A separate swarm in the same turn is not globally bounded.

## 2. Dogfood defects A1-A8

| # | RED (first failure) | Fix | Test |
|---|---|---|---|
| A1 turn ignored | `side` was `left` for a +x piece with turn -90 | `meshqa/live.py` `analysis_matrix`/`live_matrix`: offset removed, then turn about Z; draw and read_tags use the inverse; `candidates.prepare` recomputes normals after the turn; after a rebuild load the config turn is 0 (the object already has it baked in; the rebuild keeps its own turn) | `test_qa_dogfood.py::test_the_turn_puts...` |
| A2 one collection | `QA_a` did not exist; one `QA_candidates` for all | `draw_candidates(cfg, collection=None, prefix=None)` -> `QA_<piece>` / `<piece>_`; a re-run replaces only its own; tools + server defs take `piece`, `collection`, `prefix` | `test_two_pieces_in_one_scene...` |
| A3 one config per scene | (same test) | config per piece (`scene['lampway_qa_pieces']`), an active piece; the old single key is still read | same |
| A4 verdict markers | `qa_propose` missing | proposals file, red/yellow/green/grey materials, label `<id> <VERDICT>`, panel + refresh operator; a proposal never writes a ruling | `test_proposals_recolour...`, `test_ui.py` |
| A5 transcript | `.content` is '' for USER (text is in `.text`) and for a running AGENT bubble (narration in `.ephemeral`/`.thinking_text`, tools in `step_items`) - reproduced in the binary | `api.chat_transcript(last, include_steps)` + server tool `lampway_chat_transcript` | `test_chat_transcript.py` |
| A6 path printed 10x | live boot log: `workflow/ui/headers/zen_scene_controls.py:165` x10 and `:206` x5 (operators `mixar.zen_toggle_guides`, `mixar.director_enter` drawn before they register); the topbar login fallback is the same class | `common/ui_guard.operator_exists`; the draws add an operator only when registered; `topbar.draw_login_entry` | `test_boot_prints.py`, `test_topbar_login.py`. Note: your `topbar.py:241` print was not reproduced in my build (mine printed the zen lines); the topbar fix is inferred from the code |
| A7 silent turn | a 1.6 MB tool result pushed the request over the model's limit, the model answered nothing, the bubble's content was `''` (reproduced with a context-limited fake). Actual live cause is still unverified: the provider's stop reason was never read | `clip_result` (20k chars per result), `trim_history` (oldest results dropped past 200k), `Stop` event (openai-compatible: abnormal finish reasons), an explicit note with tool-call count + stop reason on an empty reply (logged WARNING), the round cap named | `test_turn_limits.py` (6) |
| A8 qa_propose | proposals were a dict and there were no rules | `meshqa/rules.py` (float / see_through / rim decide; float_threshold / backfacing_hit / large_rim / flood_guard leave it to the model), every reason names its rule, `qa_descriptors` compact batches (20 max, never `segments_m`), KEEP markers hidden, a rules re-run never replaces an agent row; the file is a list `{id,kind,verdict,reason,by,at}` like your script's | `test_qa_propose_rules.py` (4) |

A7 for the providers: only `openai_compat` (so OpenRouter) emits `Stop`; chatgpt_plan raises on `response.incomplete` already; the Anthropic and CLI providers do not report a stop reason yet.

## 3. The online Studios inside the Client

**Engine = the owner's shelf drivers, run as they are** (`LAMPWAY_STUDIO_SHELF=<shelf>/tools`; the bundled ports of the older drivers otherwise; `tripo_uv` and `--views` need the shelf). Meshy and Hi3D: the driver folders are empty. Read-only check of the tool browser (`/json/list`, no page evaluated): **tabs exist for both** (`www.meshy.ai/workspace?sidebar=image`, `www.hi3d.ai/workspace?panel=text-to-image`; a workspace URL suggests a signed-in session, which I did not verify by reading the pages). Nothing the user must log into on that evidence; what is missing is the DRIVERS (someone has to drive those tabs once to author them). The service resolves `studios/<studio>/<driver>.py`, so they drop in.

Flow (server `studios/`: `toon.py` reader, `actions.py` catalog + laws, `approvals.py`, `service.py`; routes `/app/studio/...`; agent tools `studio_plan` / `studio_job` / `studio_actions`):
1. **plan** (Client button or agent tool): the driver runs its read-back / dry run, env NOT armed, nothing clicked; the price read back must equal the expected one (mesh 100, texture 30, pbr 5, unwrap 20, image free) or the plan is refused with the driver's own words; a spend becomes an **approval** carrying the price. Free steps (state, clone, retry, pick, save, fetch...) run at once as server jobs.
2. **confirm**: only the user, from the Client: `POST /app/studio/approvals/<id>/confirm {price}`; the price must equal the one shown; one-shot; expires (600 s); `by != "captain"` refused. The confirmed run is the only thing that sets `LAMPWAY_STUDIO_ARMED=1`, for that process. **No agent tool confirms** (asserted), and the old `dry_run:false` of `studio_tripo_*` is closed for the agent (`imagegen`'s free-quota tripo path keeps an internal `allow_live`).
3. **the human gate** (`lampway_tools/human_gate.py`): `lampway.studio_confirm` refuses while ANY script runs: the GUI agent executor, a headless worker (same executor) and the bridge's `exec_code`. Mutation-checked on both doors. Residual: the MCP bridge's own exec path is not gated (owner tooling), and a person can still run `bpy.ops.lampway.studio_confirm` by hand.
4. **job -> scene**: the job runs the driver in the server (fresh out dir; drivers never overwrite a record), the panel's Import button downloads a file by name and `studio_landing.import_file` puts it in the `Studio` collection with the job prefix.

Laws enforced before any driver runs: read back every setting; 4 variants at maximum polycount (a lower polycount/count is refused); a saved COPY only (unwrap is planned from `state`, refused when the History has dated cards); texturing last (the driver's guard surfaces as the plan's refusal); paired = front+back only via `--views`; a hung job is never re-clicked until the user acknowledges it; nothing can change privacy (no action exists for it); paths jailed to the project root. The quirks the drivers already handle (newest-first thumbnails, scroll-into-view, transition clicks, one-shot mesh URLs) stay in the drivers.

**What the Client shows** (Lampway tab > Studios panel): the engine, a `Providers` button, **Waiting for YOUR confirmation** boxes (action, "N credits, read back from Studio", Confirm and spend / Reject), a plan form, recent jobs with state and Import buttons. A poll timer runs only while something is pending or running.

Tests: `server/tests/test_studio_service.py` (23), `test_studio_routes.py` (4), `tests/lampway_tools/test_studio_client.py` (6). Mutation checks: confirm-by-anyone, armed plan, price not compared (server); gate removed on executor and on bridge (client). **The driver output shapes in the fakes were read from the shelf sources, not recorded from a live run.**

### What I need run live by you (I touched no Studio)
1. Set `LAMPWAY_STUDIO_SHELF` to the shelf `tools` dir, start the server, open the Studios panel.
2. `tripo.state` (read-only) and a **plan** of `tripo.mesh` with the four plates (dry run only): check the read-back price parses (`generate_button: Generate 100`), and that `tripo.texture` / `tripo.pbr` / `tripo.image` plans parse (`settings`+`verified`, `button`, `price` shapes are from the sources).
3. `tripo.uv.clone` then `tripo.uv.unwrap` plan (it reads `tripo_uv state`'s `smart_uv_buttons` and `history`), then the first real confirm of an unwrap at 20.
4. Meshy / Hi3D drivers: none exist; the actions go in `studios/actions.py` and the drivers under `<shelf>/studios/<studio>/`.

## 4. Provider setup, no longer env-only (lp/subs request)
`GET/PUT /app/provider-settings` (`provider_prefs.py`): main provider/model/effort, swarm provider/models, image backend/model/size/quality, saved 0600 in the state dir, applied live (the main provider is swapped for new turns), reloaded at start; env is the default, a saved value wins, `source` says which. Refusals name the reason and change nothing: unknown provider, `size: "4K"`, 3840x3840, a provider that cannot be built (no key, local CLI switch off). No credential field exists. Client: `lampway.providers_open` / `providers_save` (Providers button in the Studios panel; only changed fields are sent).

**Image model per purpose** (your bake-off): `image_purposes` = plates / mask / concept / tile, each with model, size, resolution, quality; defaults plates gpt-image-2.5-flare 2880x2880, mask gemini-3.1-flash-image, concept flux-3-image at 2K, tile flare 2048x2048. Budget about 8.3 MP and at most 3840 per edge (2160x3840 passes). A request reads `GET /images/models/<id>/endpoints` (cached; model-family fallback) and refuses a parameter the model does not list (GPT Image takes `size`; FLUX/Seedream/Gemini/Riverflow take `resolution` + `aspect_ratio`). Per call: `size` or `aspect_ratio` on `studio_image_generate` and on the job payload (`aspect_ratio` -> the largest budget-fitting size on size-models, passed through on aspect-models), plus `purpose` (default plates). The plates default replaced the old Gemini default (two test expectations updated). Tests: `test_provider_prefs.py`, `test_image_purposes.py`, and the dialog test.
Unverified: the endpoints response shape (`data.endpoints[].supported_parameters`) is as you described it, not recorded; a lookup failure falls back to the family table.

## 5. Features (C)
Closed this pass: the studio slot of the features now names its Studio action (`tripo.uv.unwrap`, `tripo.mesh`, `tripo.texture`) and says plainly where the shelf has no driver (retopology, segmentation, auto-rig); `chat_transcript`, `qa_propose`/`qa_descriptors`; the sandbox/transcript/log defects above. Not done: AutoRemesher as a retopo engine (native build needs your approval), the splat view render check, per-feature panels, deeper wiki workflows beyond the three already built.

## 6. Open / honest list
- A7's real live cause (stop reason, limit, budget) is unverified; the reproduction is a context-limited fake. The fix removes the two causes I could reproduce and never ends silent.
- A6 on your build (`topbar.py:241`) not reproduced; the guard exists for both sites.
- Swarm on `claude_cli`, the ChatGPT-plan main agent and a real Studio were not exercised here.
- Residual gate gaps: MCP bridge exec path; a user running the operator by hand.
- Build ready to swap: `wt-studios/build/Prod` (python synced at `b691b0b1`). Launch it the way you launch his session with `--env Prod` from `wt-studios`; the server code is in `wt-studios/server`.
