---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# server — Lampway's backend

`lampway_server`: login for the single local account, the agent hub that fronts Mode 1's Hermes pane over the client's own
JSON-RPC WebSocket protocol and drives Blender for its tools (Lampway runs no agent loop of its own, spec A5), the tool registry,
the model gateway, MCP for external AI apps, the job queue, studios, prompts, the ledger, the asset library,
compute adapters and the cockpit's herdr host. Loopback by default (`config.py`: `LAMPWAY_HOST` defaults to `127.0.0.1`). How to
run it and its environment: [`README.md`](README.md). The laws are the root [`AGENTS.md`](../AGENTS.md)'s; this file states how
they bind here. Adding a tool: the `lampway-tool-authoring` skill.

## Invariants

1. **One egress choke point.** `egress.install()` wraps the httpx client send once; every in-process provider call passes there.
   A call that starts another process wraps its launch in `egress.guard(route, ...)`. A paid job calls `egress.preflight(route)`
   before its receipt is marked pending. A new host is a new `Route` in `egress.ROUTES`, off until the user opts in. The log row
   is written before the bytes leave and holds no content, query string or header.
2. **No confirm path for anyone but the user.** An approval is created by a plan and confirmed only from the Client's REST route
   (`studios/approvals.py`); `spendpolicy.py` decides whether a job waits and never clicks; an unknown price waits.
3. **Write-ahead receipts.** `jobreceipts.py`: exclusive create, `submission_pending` on disk before the first byte, reconcile
   turns a dead pending into `submission_unknown`, and only the user acknowledges or links it. Files are 0600 in 0700 directories;
   `export_safe` drops signed URLs and secrets before a receipt goes anywhere else.
4. **MCP offers no spend.** `mcp.py` `offered_tools()` is the scene tools, the `DEFS` tools that are one script in Blender, and the
   read-only server tools. Studio tools, the swarm and `ask_user` are never offered to external apps, and a `swarm:` session header
   on their route is refused (a binding is not a credential). The engine's own endpoint
   (`engine/mcp_endpoint.py`, `/engine/mcp/<unit>`, spec E1.6, A3) is not an external app: it is the in-app agent's, the Hermes of
   one unit's Mode 1 pane, loopback only and bound to that unit's bearer (in the pane's own 0600 config; the server keeps its digest),
   and offers the agent's full registry as Capabilities allow less `ask_user` (questions are Hermes's own `clarify`, A2), every call
   through `AgentHub._run_tool` on the scene tab's CURRENT client socket (`AgentHub.socket_for`), whoever started the turn; with no
   Lampway window connected the call is refused, saying so. It has no confirm path either (law 3).
   The pane endpoint (`/api/v1/mcp/pane`, spec S3) is not an external app either: loopback only, it answers only a pane Lampway
   started on its own herdr server, proven by that pane's own bearer, which lives only in the pane's own 0600 config or its
   environment, handed to herdr like a per-pane API key (never the registry, which keeps a hash, and never the harness's command
   line). A swarm worker's pane (session header `swarm:<swarm_id>:<worker_id>`, its `PaneBrain`'s token) is offered
   `worker_tools()` as Capabilities allow plus `lampway_worker_done`, every call through its `WorkerJob.call_tool` on its own
   headless Lampway, never the swarm, the studios, `ask_user` or the workbench. A pane bound to a scene tab (B2; its key) is offered only `swarm_start`, `swarm_status`,
   `swarm_cancel` and `swarm_collect`, only with capability `swarm` in force and the BYOA switch on, for the swarms it started; its
   swarm thinks in panes and lands in its bound tab. No swarm tool spends.
5. **A tool argument cannot change the script.** `agent/lampway_tools.py` `build_script` passes the arguments as one JSON string
   literal into `api.call`; unknown arguments are dropped and a missing required one is refused before Blender is asked.
6. **Isolation and controlled decoupling (herdr).** Every herdr invocation goes through `herdr/launcher.py` with HOME, XDG and
   the HERDR socket and config paths under the Lampway root, refusing otherwise; the server is launched detached and survives a
   Blender or server crash; a start reconciles sessions and paid jobs in one idempotent pass and never kills an unknown pane or
   respawns an ended one without a click. Who types into a pane is decided from the caller, never from a body field: the workbench
   input route treats an agent-declared, cross-origin or agent/MCP-token request as an agent send; the agent's open path checks the
   same BYOA switch as the create route; `lampway_workbench` is never offered over MCP (agent-modes spec B6).
   herdr, and so every pane, starts from the scrubbed base (`connections.env_for([])`); a pane adds only the real login variables
   (`pane_env`) and, when the user ticked it for that pane, its own vendor's API key. Starting a harness runs inside
   `egress.guard("byoa:<harness>")`: refused with the route off, logged before herdr is asked (spec B5).
   Every harness pane starts through its adapter in `herdr/harnesses/` (spec B1): an adapter only describes (binary, argv, wiring,
   observation), never opens a harness's credential files, reads or writes a file or starts a process; its version probe and login
   check run through the launcher, the login check inside the harness's route; no adapter emits a bypass flag without the user's tick.
   A harness pane bound to a scene tab (spec B2) gets its own MCP config, 0600 under `<herdr root>/panes/<id>/`, pointing at Lampway's
   launcher with `LAMPWAY_BOUND_SESSION`; nothing is written outside the Lampway root. Binding and unbinding change only that file and
   the record, never the pane; only the user's Client binds (`POST /app/workbench/sessions/{id}/binding` refuses agent callers).
   Every swarm worker, in either mode, is a pane: `PaneBrain` (`herdr/swarm_brain.py`) is the one worker brain (spec S1, A5;
   no worker thinks inside this server or as a hidden child), and the unit's mode picks the adapter its pane starts through
   (`harnesses.worker_adapter`, decided in `SwarmManager.worker_brain` before any run is activated): Mode 2 (a bound pane, or a tab
   in Your agent mode) the parent pane's harness under its route; Mode 1 `lampway_hermes` (`harnesses.LAMPWAY_ADAPTERS`, Lampway's
   own, never in the user's list), whose pane starts only on a server running the engine (the cockpit's `mode1` hook), so
   elsewhere a Mode 1 `swarm_start` is refused with that help and nothing runs another way. A Mode 2 worker's pane has its task on
   the harness's own command line (only where herdr starts the harness itself, never typed into a shell); a Mode 1 worker's task is
   in its home (0600) and the server submits it as its session's first prompt (S2). No worker pane has a desktop launcher (its UI
   and scene-tab tools reach the user's scene); it cannot be bound to a tab.
   **Mode 1's pane (spec A1, `engine/units.py`, `engine/hermes_pane.py`, `herdr/harnesses/lampway_hermes.py`).** A unit's main
   agent and every Mode 1 worker is a `lampway_hermes` pane running Lampway's stdlib-only wrapper by path with the server's own
   interpreter; the wrapper starts the pinned `hermes serve` (its own session, a per-unit lock dir, orphan grace 0, the pinned
   toolset list, never `HERMES_DESKTOP`) and Hermes's own prebuilt TUI in the foreground (`HERMES_NODE`,
   `HERMES_SKIP_NODE_BOOTSTRAP=1`: Node is found, never fetched), and reopens the TUI or restarts a stopped serve only on the user's
   Enter. Before herdr is asked, `Mode1Units.prepare` writes the home `<state>/agent/hermes/<unit>` (a worker's under
   `workers/`): `config.yaml` and `serve.token` (0600) and a `pane.json` with no secret. The argv is the wrapper and the home only,
   one shell-quoted string for `pane run` (herdr joins its arguments unquoted); no token is ever on a command line, in herdr's argv
   or in a record. The record keeps `home`, `port`, `token_file`, `stored_session_id` and the two tokens' digests (`MODE1_FIELDS`;
   only `Cockpit.update_mode1` changes them), never `scene_session_id` (binding is Mode 2's; `ByoaView.bound` counts only a user's
   harness). It has no egress route of its own (`route` None; the launch is `local` in `egress.LAUNCHES`): its model is the
   gateway on loopback and every other host goes through the egress proxy. Opening a unit's pane is the user's own chat
   (`HermesFront.precheck` refuses an agent's socket and never starts herdr); a restart re-adopts every live Lampway pane, its
   tokens by their digests (`Mode1Units.adopt`), and the server's shutdown ends no pane. The swarm ends only a pane whose record names it and that worker (`Cockpit.end_swarm_pane`): on cancel, failure or
   timeout; a finished worker's pane stays open (closing ended ones at the next swarm, Q13, is not decided).
   The herdr view (spec A4, `herdr/layout.py`): a unit is one scene tab's conversation (its scene session id). A pane bound to a
   tab (created bound, or bound later) is its unit's `main` agent and opens in a tab of its own labelled with the scene's name
   (the Client's `name` on the mode route), else a short id; a worker pane splits into its unit's tab, the first right of the
   main pane, which keeps 60 % (herdr's split ratio is the share the split pane keeps), each further one down from the last
   worker pane still in herdr; a swarm passes its worker count (`planned`), so its own workers share the column evenly (each
   split keeps 1/(its workers still to come)), and a worker of another swarm halves the last pane; placements serialized in the
   host so workers opened at once still form one column; a unit with no main pane gets one tab for its workers; an ad-hoc pane keeps a
   tab of its own; a herdr that refuses the split gets the pane in a tab. Every pane reports `display_agent`, `title` and
   `state_labels` (`pane.report_metadata`), best effort: a failure is logged, never a failed start. Each record carries `unit`,
   `role` (`main` | `worker`) and `unit_label`; reconcile re-adopts them with herdr's current pane and tab ids, lists `units`,
   and never closes an unknown pane. The herdr CLI argv shapes live only in `herdr/layout.py`, checked against herdr 0.9.3
   (its CLI reference and a live server): `pane split <pane> --direction … --ratio …` answers `result.pane` with its `tab_id`;
   `pane report-metadata` takes one `--state-label STATUS=TEXT` per status and refuses any option it does not know.
   A scene tab's agent mode (spec M0) is known from the chat payload's `agent_mode` and from that binding table (`agent/byoa.py`):
   a Mode 1 `agent.chat` or `agent.input` into a tab in Your agent mode is refused with `code: wrong_mode` before any turn starts.
   Only the user's Client switches a tab (`POST /app/workbench/mode` binds or unbinds, never touching a pane; agent callers refused).
   The island view (spec B4) tails a bound pane's own session file read-only (Claude Code, Codex: `herdr/observers/mirror.py`) and
   streams it as observed turns in Mode 1's frames; history before the first observation is never replayed unless the client names
   its offset; a harness without a readable file is shown by its screen, and the user's own Hermes home is never read (E1.10).
   `agent.byoa.send` finds the pane from the binding, decides who typed from the socket, and holds an agent's send in the 2.5 s
   quiet window after the user's own.
7. **Secrets never reach a log or a file in the repository.** Keys come from the environment or 0600 files the user owns
   (the state directory, a dotenv file the launcher is pointed at); `logredact.py` redacts query secrets and token-shaped strings in every log record.
8. **Never the upstream service.** No code here calls the upstream backend; the client's stubbed endpoints are answered locally.
9. **Capabilities are the user's switches** (docs/reports/agent-modes-spec.md E2). `capabilities/` holds what an agent may do,
   globally and per project; only a user request changes it (`PUT /app/capabilities/{id}`, `DELETE` of a project override and
   `POST /app/capabilities/proposals/{pid}` refuse agent and cross-origin callers), and an agent only proposes (`lampway_capabilities`),
   which the user accepts or declines. A family row (`messaging.*`, `mcp.*`) is the default for each member with no setting of its
   own, scope by scope (`Store.setting`). Lampway's tool families are checked at call time by `capabilities.check_tool`
   for the in-app agent and for MCP clients; a capability that needs an egress route is in force only while that route is on.
   The engine's Hermes config is rendered from the same board (`engine/hermes_config.py`, spec E1.3): the model is the loopback
   gateway only (`provider: custom`, no other provider, no adopted logins), the serve platform's toolsets (`platform_toolsets.cli`,
   pinned again by `HERMES_TUI_TOOLSETS`) are exactly those of the capabilities in force plus `clarify` for a main agent (never a
   worker's), Lampway's one MCP server is declared with its bearer, every outbound check Hermes lets config switch off is off
   (the Nous guest bootstrap and lazy installs included), approvals are `manual` (the user's, never a guardian model's), context
   stays Hermes's unless given, and it is never written into the user's own `~/.hermes` (E1.10). `check_advertised` compares the
   tools the model is sent (visible and deferred behind tool_search) with the choices; an unexpected or unlistable tool refuses
   the session.
10. **The engine has two doors, both on loopback and both Lampway's** (docs/reports/agent-modes-spec.md E1.4, E1.5, A1). `engine/gateway.py`
    is the Mode 1 panes' only model endpoint: loopback clients, a per-pane bearer (`Registry.issue_token`, in memory as a digest,
    adopted again by its digest after a restart, redacted by `logredact.py`), answered by the current main provider and never by
    another; a provider's failure is an OpenAI-style error, not a retry; serve's Ollama probe (`POST /api/show`) gets a harmless 404.
    `engine/proxy.py` is its only way out: bound to loopback, it decides before it connects (the gateway's port; a host whose route is on
    and whose capability is in force; any host only with `web:any` and `web.browse`), writes a log row for every refusal and sends an allowed
    connection through `Egress.begin`. It is the one module that opens an outbound stream outside the httpx hook
    (`tests/test_engine_proxy.py` holds that in both directions). The gateway's one tokenless path is the models.dev mirror
    (`/engine/v1/models-dev.json`, loopback only, the model's name and window, no secret), because Hermes fetches it with no key.
    `engine/wiring.py` puts the engine in the seat whenever a finished build is found (`$LAMPWAY_ENGINES_DIR`, else
    `<repo>/build/engines`, else `<state_dir>/engines`) and the server is on loopback; there is no switch (spec A5: nothing else runs
    Mode 1, and `LAMPWAY_AGENT_ENGINE` is no longer read, a server that finds it set says so). Otherwise one log line says why and
    the hub keeps that reason with its fix (`AgentHub.engine_problem`: `engine_not_built` with the build command, or
    `engine_unavailable` for a non-loopback bind or an engine that could not start) for its Mode 1 refusals. Then the lifespan starts the proxy (on its previous port when free, so panes that outlived the server still
    reach it), makes `units.Mode1Units` the cockpit's `mode1` hook and `front.HermesFront` the hub's engine, and re-adopts the live
    Lampway panes. Each pane gets a fresh gateway token (an older one for the same pane revoked), its config from
    `hermes_config.write` and the active board (`worker=True`, the board less `WORKER_NEVER` and without clarify, for a Mode 1
    worker's pane; the gateway answers every pane with the main provider), and one environment from the wrapper (`proxy.proxy_vars`
    through `pane.json`: `NO_PROXY` the gateway's loopback host only, `HERMES_MANAGED_DIR` an empty directory in its home so no
    system `/etc/hermes` overrides the config); `check_advertised` runs on each token's first request with tools and a mismatch
    refuses that pane's requests. Shutdown closes this server's connections to the panes and stops the proxy; it ends no pane.
11. **The island is a client of the pane, never its host** (spec A2, `engine/front.py`, `engine/serve_client.py`). Mode 1's front
    end speaks serve's JSON-RPC on `ws://127.0.0.1:<port>/api/ws` (loopback only, never through a proxy) beside the TUI: `agent.chat`
    is `image.attach_bytes` per image then `prompt.submit` with R3's blocks; a chat while a turn runs is `session.steer`;
    `agent.cancel` is `session.interrupt`; serve's events are the turn's slots; `clarify` and `approval` server requests are the
    island's question and permission cards, closed by the island itself when the pane answers first (no `request.cancel` comes); a
    turn typed in the pane is an island turn (`agent.turn.started` with `origin: pane`); `/new` in the pane is followed, once, its
    closed session's question released, and the tab's current client told (`agent.pane.new_conversation {session_id, origin:
    pane}`; the tab's session id stays the unit's); a dropped connection catches up from `session.events.since` (else the
    history); the island's socket closing stops nothing in Hermes. A tool call that overtakes its turn (the pane turn still being
    opened, the island's answer not yet admitted) waits for the island turn that shows it, up to `TURN_WAIT_S`, so its script
    names the turn the client shows; a question nobody can answer any more (Hermes started another turn, or serve restarted and
    its request died) is released and its card closed in the next turn the island shows.
    The M0 `wrong_mode` refusal comes first, before any of it.
    **Mode 1 runs only on Hermes (spec A0, A5).** The hub has no provider loop, no transcript of its own and no rounds: the
    providers are the gateway's doors only (it is their one caller for Mode 1), and Hermes keeps the conversation. With no engine on
    this server (`AgentHub.engine` None) a Mode 1 `agent.chat` or `agent.input` is refused before any turn starts with the reason
    `wiring.py` found, its fix and the switch to Your agent (`AgentHub.engine_refusal`); `HermesFront.precheck` refuses a missing
    hermes binary or prebuilt TUI (`engine_not_built`), Node.js (`node_missing`) and herdr (`herdr_not_built`, its build command)
    before a pane is asked for. Nothing answers in the engine's place. A swarm the pane's Hermes starts runs in the island turn that
    shows its call, so its todo cards and progress reach the Parallel Agents panel. A checkpoint mark bookmarks nothing
    (`has_conversation: false`) and a rewind is refused (`rewind_unsupported`): Lampway does not rewind Hermes's conversation.

## Test

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"   # once
.venv/bin/python -m pytest -q tests                            # the whole suite: no Blender, no network, no model
```

Mode 1 without an engine: the hub's client-protocol tests (`test_engine_front.py`, `test_agent_turn.py`, `test_agent_control.py`,
`test_questions_checkpoints.py`, `test_modes_m0.py`, the swarm's and the tools' turns) drive Mode 1 against `tests/serve_support.py`
`FakeServe`, a scripted `/api/ws` peer speaking the contract measured on the pinned serve, with the client's own frames: the real
server on a real port (`stack`, `run`), or under a TestClient (`ServeThread`, `mode1_turn`, the pane's MCP calls through it). No
test drives a turn through a provider: `ScriptedProvider` is the gateway's door (`test_engine_gateway.py`, the live suite).
`tests/test_mode1_only_hermes.py` holds the refusals with no engine, no herdr and no Node, and that the loop is gone. The suite's
conftest keeps engine discovery off (`LAMPWAY_ENGINES_DIR`, the repository's build) unless a test names its build.
`tests/test_engine_pane.py` holds the adapter, the wrapper (against a stand-in `hermes`), `Mode1Units` and the unit's
endpoint. Live: `tests/test_engine_hermes_config.py` runs the built engine's `hermes serve` (`build/engines/hermes/<tag>/env/bin/hermes`,
or `$LAMPWAY_HERMES_ENGINE`) against a fake loopback model behind a refusing proxy; `tests/test_engine_pane_live.py` runs the real
server with a finished build in `LAMPWAY_ENGINES_DIR` (found, so in the seat), the real wrapper, serve and TUI in a pty (herdr played but running its panes for real,
`tests/live_support.py`) and once on a real herdr server; it needs the build (`LAMPWAY_ENGINES_DIR`), its prebuilt TUI
(`engine.json` `tui` or `LAMPWAY_HERMES_TUI_DIR`) and Node (`LAMPWAY_NODE` or PATH). Without them those tests SKIP, which is not a
pass. The suite drives the real client's frames through a fake client. A behaviour change lands with its failing test first; a
paid or egress path is tested against a fake transport, never a live provider, unless the captain named the spend.
herdr is played by `tests/herdr_support.py` `PaneHerdr` (tabs, splits, reported metadata; like herdr 0.9.3 it refuses a metadata
option it does not know), and driven for real, where a herdr is found (`launcher.bin_path`: `LAMPWAY_HERDR_BIN`, then the pinned
build from `scripts/lampway/herdr_env.py`, then PATH or `~/.local/bin/herdr`), by `tests/test_herdr_cockpit.py`,
`test_herdr_launcher.py`, `test_herdr_layout_live.py` and the real-herdr case of `test_engine_pane_live.py`; without it those SKIP,
and a skip is not a pass. The swarm's substrate tests (`tests/test_swarm_v3.py`) start the swarm in Mode 1 on the real
`lampway_hermes` adapter and `Mode1Units` over a stand-in engine build (`tests/mode1_support.py`), and play each worker pane over
the pane endpoint its rendered config names.

## Owner

The lane whose contract names the change writes it; the integration lane (`lp/wave5`) lands it after the full server suite.
Doctrine (the laws above, provider and spend policy) is the captain's.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the server's invariants lived only in module docstrings | egress, approval, receipt, MCP, script-literal, herdr and secret invariants stated with their modules; the suite command | captain ruling, 2026-10-05 |
| 2026-10-07 | capabilities switchboard | captain: "I want it all behind a single interface you can choose WHAT your agent can do" (agent-modes spec E2, Q8 defaults) | nothing recorded what an agent may do; the swarm and every tool family were always on for every agent | invariant 9: the user's switches, call-time checks for the agent and MCP, proposals only from agents, routes still decide egress | captain ruling, 2026-10-06 |
| 2026-10-07 | the engine's MCP endpoint | captain: Hermes Agent's runtime in Mode 1's seat (agent-modes spec Q7, E1.6) | invariant 4 read as if every MCP surface were an external app, which would keep `ask_user` and the user's swarm from the in-app engine | invariant 4 scoped to external apps; the engine endpoint named with its gates | captain ruling, 2026-10-06 |
| 2026-10-07 | the engine's gateway and egress proxy | captain: Hermes Agent's runtime takes Mode 1's engine seat; Hermes holds no key and only Lampway's doors lead out (agent-modes spec E0, E1.4, E1.5, Q7) | the engine child would have reached models and the network on its own: no key held by Lampway, no log row, no capability check, and `web:any` was not a route | invariant 10: the gateway (loopback, per-process token, current main provider, no retry elsewhere), the proxy (decide before connect, a row per refusal, `Egress.begin` for what it allows) and the `web:any` route | captain ruling, 2026-10-06 |
| 2026-10-07 | engine config from capabilities | coordinator brief: agent-modes spec E1.3 "Nothing is removed; everything is chosen" (captain, 2026-10-06), E1.10, Q3 | with no config the engine offered 23 tools (terminal, browser, execute_code, memory, delegate_task ...), would adopt other apps' logins and tried pypi.org, models.dev, hermes-agent.nousresearch.com and raw.githubusercontent.com | invariant 9 names the rendered Hermes config, its loopback-only model, the never-~/.hermes rule and the start-up check; the Test section names the live engine tests and that their skip is not a pass | none |
| 2026-10-07 | merge of the E1.3 lane into the agent-modes branch | the coordinator's merge: the E1.3 lane extended invariant 9 while the gateway lane added invariant 10 at the same place | two lanes appended to the same list; the merged list keeps invariant 9's new paragraph under 9 and invariant 10 after it | invariants 9 and 10 as both lanes wrote them | none |
| 2026-10-07 | herdr surface hardening (BYOA B6) | agent-modes spec B6, captain's Q4 (2026-10-06): Lampway's agent types only into its own panes, the origin from the session | the input route took `body.by` at its word, so any bearer holder could type as the user; the agent's open path skipped the BYOA switch | invariant 6 names the caller-decided origin, the shared switch and the MCP exclusion | captain ruling, 2026-10-06 |
| 2026-10-07 | BYOA egress and pane environment (B5) | agent-modes spec B5, law 2 | herdr launches were classed "local" and passed no gate; herdr and its panes inherited the server's full environment, API keys included | one `byoa:<harness>` route per harness, off by default, guarding each start; herdr from the scrubbed base; keys only by the user's per-pane opt-in; invariant 6 says so | captain ruling, 2026-10-06 |
| 2026-10-07 | harness adapter interface (BYOA B1) | agent-modes spec B1, captain's Q5 and Q6 (2026-10-06): seven starting adapters, the old CLI switch repurposed | each harness was a branch in `host.agent_args`, the BYOA switch lived in the retired `agent/cli_adapters.py`, and nothing described how a harness is detected, wired or observed | `herdr/harnesses/` with the Protocol and seven adapters, the switch moved there, the host starts panes through them; invariant 6 states what an adapter may not do, held by a source gate | captain ruling, 2026-10-06 |
| 2026-10-07 | a pane bound to a scene tab (BYOA B2, server side) | agent-modes spec B2, law 5 | panes reached Lampway only through a user-scope connector, with no tab binding, and the session record had no harness, scene or config fields | the record carries harness, native id, scene session, project root and config path; a per-pane MCP config pinned by LAMPWAY_BOUND_SESSION; bind and unbind never touch the pane; invariant 6 says so | captain ruling, 2026-10-06 |
| 2026-10-07 | capabilities: proposals decided, overrides cleared, family rows | coordinator brief: the client crew needs E2's accept/decline card, "this project only" undone and the family switches (agent-modes spec E2) | a proposal could be made but never answered, a project override could not be dropped, and switching `messaging.*` or `mcp.*` changed no member | invariant 9 names the decide and clear routes (user only) and the member -> family -> default fallback | none |
| 2026-10-07 | the engine in production (E1 wiring) | coordinator brief: Hermes runs Mode 1 when `LAMPWAY_AGENT_ENGINE=hermes` and a build is found (agent-modes spec E1.2-E1.5, E1.3's start-up check) | the gateway, proxy, config renderer and runtime existed but nothing in `create_app` joined them; two `child_env` helpers disagreed on `NO_PROXY`; a system `/etc/hermes` could override the written config; models.dev pointed at a path the gateway did not serve | invariant 10 names the wiring, its selection and its one log line, the per-child token's life, the one environment, the tokenless models.dev mirror and the start-up check; the Test section names the live wiring test | none |
| 2026-10-07 | the swarm in Mode 2: pane workers and the pane endpoint (S3) | coordinator brief: agent-modes spec S3, S4, S5 (captain, 2026-10-07: "put the Swarm V3 on the same Mode system") | invariant 4 kept the swarm from every MCP caller, a bound BYOA pane included; the client's launcher would hand a worker pane the desktop's UI and scene-tab tools, and the relay forwards only a UUID session header, so a `swarm:` binding could neither reach the server nor be told apart | invariant 4 names the pane endpoint, its two callers and their bearers, and the refused `swarm:` header on the external route; invariant 6 names how a worker pane starts and that the swarm ends only its own panes | none |
| 2026-10-07 | one agent mode per scene tab and the BYOA island view (M0, B4, server side) | coordinator brief: agent-modes spec M0, B4, captain's E1.10 rule | nothing told the server a tab was in Your agent mode, so a Mode 1 turn could run in a tab a pane drives; the observers were wired to nothing and the island could not show or type into a bound pane | invariant 6 names the two sources of a tab's mode and the `wrong_mode` refusal, the user-only mode route, the read-only observed stream with its replay rule and screen fallback, and the socket-decided origin of the island's sends | none |
| 2026-10-07 | merge: M0/B4 beside the swarm's pane workers (S3) | coordinator integration of the M0/B4 crew's branch | both branches extended invariant 6 (how a worker pane starts; how a tab's mode is known and observed) and the conflict could have dropped one | invariant 6 keeps both paragraphs; a Your agent tab's refusal comes before the engine's join-the-turn | none |
| 2026-10-07 | one worker brain and the herdr view (S1, A4, A5) | captain, 2026-10-07: two modes only, every agent a process in a pane on Lampway's herdr server, wrappers only; coordinator brief for the lane (agent-modes spec A0, A4, A5, S1) | swarm workers could think inside the server (`BuiltinBrain`) or as hidden Hermes children (`EngineBrain`, `EngineRuntime.run_worker`); herdr opened one tab per pane, so a swarm meant one tab per worker; nothing reported what a pane is, and a record did not know its unit; concurrent worker starts each saw an empty column | invariant 6: `PaneBrain` the one brain, the mode picks the adapter, Mode 1's `lampway_hermes` a stub refused with the A1 help; the unit/tab/split layout, metadata best effort, `unit`/`role` re-adopted by reconcile, the argv shapes in `herdr/layout.py` with split and report-metadata `[UNVERIFIED]`; invariant 10 drops the hidden workers; the Test section names the played herdr and the played Mode 1 adapter | captain ruling, 2026-10-07 |
| 2026-10-07 | the herdr view checked against the real herdr | captain: "You can download the herdr binary" (herdr 0.9.3 built from herdrdev/herdr) | the layout's argv shapes were unverified: `pane report-metadata --state-labels <json>` is refused by herdr ("unknown option"), so every pane's metadata report failed; herdr's split ratio is the share the split pane keeps, so 0.4 left the main agent 40 %, not 60 %; each further worker halved the last pane, so six workers ended at 1/32 of the column | invariant 6: the verified shapes, the main agent's 60 %, the even column from the swarm's worker count; the Test section names the live herdr tests and the strict played herdr | none |
| 2026-10-07 | Lampway runs its pinned herdr | captain: "Pin the current herdr and Hermes releases the same way the Blender pin is done" | `launcher.bin_path` took the first herdr on PATH, so the server ran whichever version the user had | `bin_path` order (LAMPWAY_HERDR_BIN, the finished pinned build, PATH, ~/.local/bin) in the Test section's lookup; `tests/test_herdr_pin.py`; the live herdr tests use the same lookup | captain ruling, 2026-10-07 |
| 2026-10-07 | Mode 1 in a pane: the Hermes pane, the island as its client, tools by unit (A1, A2, A3) | captain, 2026-10-07: Mode 1 runs Hermes's own TUI in its pane, the island loses nothing and gains persistence; coordinator brief for the lane (agent-modes spec A1-A3, E1.3-E1.6, S3) | Mode 1 ran as a hidden `hermes acp` child per tab (`EngineRuntime`, `LampwayACPClient`), killed with the server; `lampway_hermes` was a stub; the engine endpoint needed an island turn, so nothing typed in a pane could reach the scene; the config named the ACP platform and `no_mcp` | invariant 4: `/engine/mcp/<unit>` on the tab's current socket, no `ask_user`, refused with no window open; invariant 6: Mode 1's pane, its home, its record fields, no route, the user's chat as the only opener, re-adoption; invariant 9: the `cli` platform, clarify, the pinned toolsets, manual approvals; invariant 10: per-pane tokens adopted by digest, `/api/show`, the proxy's kept port, a shutdown that ends no pane; invariant 11 new: the island as serve's client; the Test section names the fake serve and the live pane suite | captain ruling, 2026-10-07 |
| 2026-10-07 | merge: Mode 1 in a pane (A1-A3) beside the verified herdr layout and the herdr pin | coordinator integration of the A1-A3 lane | both sides rewrote the Test section's herdr sentence and the host's placement; the lane's still called the layout's shapes `[UNVERIFIED]` | the Test section keeps the lane's Mode 1 tests and the verified, pinned herdr sentence (the real-herdr case of `test_engine_pane_live.py` named); the host keeps the lane's Mode 1 unit with the swarm's `planned` column | none |
| 2026-10-07 | Mode 1 only on Hermes: Lampway's built-in agent loop removed (A5) | captain, 2026-10-07: "two Agent Modes and the Runtime on Mode 1 to be Hermes Runtime. Agents/workers run on either of those modes nothing else"; coordinator brief for the last server lane (agent-modes spec A5) | `turns.py` still ran its own provider loop (rounds, history trimming, the pairing repair, Plan Mode's prompt, the Retry chip) whenever `LAMPWAY_AGENT_ENGINE` was unset or no engine was built, so Mode 1 silently ran a third runtime; the swarm's todo cards never reached the island on the engine path; a checkpoint rewind claimed to forget turns Hermes still had | invariant 10: the engine is in the seat whenever it is built, no switch; invariant 11: Mode 1 only on Hermes, the refusals with no engine, Node or herdr, the swarm in the island turn, checkpoints say Hermes keeps the conversation; the intro and the Test section: the hub's protocol tests on the scripted serve, no turn through a provider, `test_mode1_only_hermes.py`, the conftest's engine discovery | captain ruling, 2026-10-07 |
| 2026-10-07 | the island told of the pane's `/new` (A2, Q15) | coordinator brief for the client lane: the island starts a new chat when the pane's `/new` moves it | the server followed the pane silently: with no island turn running the client got no frame at all (the tab's session id, the unit, does not change), serve's two `sessions.changed` could follow twice, and a question of the closed session stayed open, so the island's next chat was sent to it as an answer | invariant 11: one `agent.pane.new_conversation` to the tab's current socket after the follow, which releases the closed session's question; a second follow that finds the link already moved does nothing | none |
| 2026-10-07 | a tool call waits for its turn; a dead question is closed (A2) | coordinator brief, Mode 1 loose ends 6 and 8 | a tool call made while its pane turn was still being opened ran under a scratch turn id, which the client refuses (`unknown_turn`); a question left open when serve restarted or Hermes started another turn stayed open, so the tab's next chat was sent to a dead request and its card never closed | invariant 11: the bounded wait for the shown turn, the stale question released and its card closed | none |
