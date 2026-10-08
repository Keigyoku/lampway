<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway agent modes: the Lampway Agent Runtime and Bring Your Own Agent

Status: **partly built, re-architected 2026-10-07** (§A governs; the older sections are read through it), first written
2026-10-06 against `lp/wave5` at `fd0f108`; `main` took wave5 on 2026-10-07. Companion to [the MCP wrapper spec](mcp-wrapper-spec.md) (C0–C2, T1–T3), whose
contracts this one depends on. Nothing here is built. Findings F1–F25 come from the stress-test audit of the same day, whose report is not in this repository; each finding a
contract depends on is restated where it is used. Claims not checked on a running app are marked `[UNVERIFIED]`.

**Direction (captain, 2026-10-06).** Lampway has two agent modes.
- **Mode 1, the Lampway Agent Runtime.** Upstream Mixar's hosted-backend architecture becomes Lampway's local Agent API, driven
  by an API key or a bare LLM endpoint. *Superseded by A:* the runtime is Hermes's (Q7), in a herdr pane (A1); Lampway's own
  agent loop is removed (A5).
- **Mode 2, BYOA (Bring Your Own Agent).** The user's own first-party agent CLIs, on the subscriptions they already pay for, run on
  Lampway's persistent herdr server. No third-party piggybacking: everything goes through the vendors' own apps. BYOA gives up the
  Lampway Agent Runtime and inherits the runtime of whichever harness the user runs.

Inputs: the audit of 2026-10-06 (findings F1–F25 of the companion report); three read-only code surveys of the session lifecycle,
the client↔backend protocol and herdr (summarised in §0); the repository's laws (`AGENTS.md`); the contract template
(`.claude/skills/lampway-tool-authoring` §1).

## A. The architecture: two modes, every agent in herdr (captain, 2026-10-07)

**This section governs.** It was written after `main` took wave5, and every older section below is read through it. Where one
disagrees, this one wins, and the older section carries a *Superseded by A* note. The captain's words: "two Agent Modes and the
Runtime on Mode 1 to be Hermes Runtime. Agents/workers run on either of those modes nothing else, no custom architecture for
hosting or managing agents beyond wrappers for those. In either mode, all agents spawn into the herdr server. Remove headless
workers." Then, on the follow-up questions: headless means agents without a pane (workers keep their own headless Blender scene);
the herdr view should keep context and pane switching to a minimum; and Mode 1 runs Hermes's own TUI in its pane, "we should lose
nothing, but gain agent persistence".

### A0. The rules

1. **Two modes, no third.**
   - **Mode 1, Lampway's agent:** the Hermes runtime, pinned (`third_party/hermes-agent`), thinking only through Lampway's model
     gateway (E1.4).
   - **Mode 2, your agent:** a harness the user runs (B1), on its own login.
2. **Every agent is a process in a pane on Lampway's herdr server.** This covers a scene tab's main agent and every swarm
   worker, in either mode. No agent runs inside Lampway's server, and none runs as a hidden child process. **Removed:**
   - the built-in agent loop (`turns.py`'s provider loop) as a runtime;
   - `BuiltinBrain`;
   - `EngineBrain`'s hidden Hermes children;
   - `EngineRuntime`'s hidden ACP children.
3. **Lampway writes wrappers, not agent hosting.** What Lampway's code may do around an agent:
   - start it in a pane (an adapter, A1 or B1);
   - give it a model (the gateway) and Lampway's tools (the MCP endpoints);
   - show it and drive it in the island (A2 for Mode 1, B4 for Mode 2);
   - lay out its pane (A4).

   The agent's conversation, turns, compression, sessions, retries and persistence are the runtime's.
4. **What does not change:**
   - a worker builds in its own headless Blender scene, and the swarm substrate collects the result into the user's scene (S1);
   - the laws: egress opt-in and logged, spend only on the user's click, write-ahead receipts, controlled decoupling.
5. **Worker choices (captain clarification, confirmed 2026-10-08).** `agent.worker_mode` selects Mode 1
   (`local:lampway_hermes`) or Mode 2 (`byoa:<harness>`), independently of the parent's mode/harness. In Mode 1 the separate
   `agent.worker` service follows the parent choice implicitly until the user moves it off that choice. The captain's direct
   initial-service ruling is: "It's tied to the parent choice, until moved off it. Implicit until changed". An explicit saved
   worker service overrides that implicit follow; its resolved service/model/parameters are pinned for a worker's life.
   In Mode 2 the selected native harness uses its own service and login. Lampway neither copies nor transfers credentials.
   This supersedes the older parent-harness proposal and the earlier inference that an initial service must be independent;
   it does not rename either Choices purpose.

### A1. The Hermes pane (Mode 1: main agent and workers)

A Mode 1 agent is a herdr pane that runs Lampway's thin pane wrapper. The wrapper is the `lampway_hermes` adapter in
`herdr/harnesses/`. It is Lampway-owned: its own home, Lampway's gateway, Lampway's tools. It is not the user's own `hermes`
adapter, which stays a Mode 2 harness (E1.10).

**What the wrapper does, in order:**
1. **Starts the backend.** It runs `hermes serve --host 127.0.0.1 --port <P>` as its child. `serve` is always headless and
   never builds a web UI, so `--skip-build` is not needed (`main_dashboard.py:959-960`). The environment:
   - `HERMES_HOME=<state>/agent/hermes/<unit>`: the rendered config (E1.3), with `model.base_url` = the gateway and `mcp_servers` =
     the unit's MCP endpoint (A3);
   - `HERMES_DASHBOARD_SESSION_TOKEN=<lwh_ token>`: issued by Lampway, never on a command line;
   - `HERMES_TUI_WS_ORPHAN_REAP_GRACE_S=0`, so a session with no client attached is parked, not reaped;
   - `HERMES_GATEWAY_LOCK_DIR=<unit home>/locks`. Hermes allows one `serve` per OS user: its rendezvous lives in
     `~/.local/state/hermes/gateway-locks`, and a second serve with a typed port exits 78 (`main_dashboard.py:847-853`). That
     would collide with the next unit and with the user's own Hermes (measured).
   - the egress proxy's variables (E1.5);
   - no key of the user's (B5);
   - never `HERMES_DESKTOP=1`, which together with the token makes serve act as a Desktop child.
2. **Waits** until `/api/ws` accepts.
3. **Runs Hermes's own Ink TUI in the foreground:**
   - `HERMES_TUI_GATEWAY_URL=ws://127.0.0.1:<P>/api/ws?token=<token>`;
   - `HERMES_TUI_CWD=<project root>`;
   - `HERMES_TUI_RESUME=<session id>` when it reopens one.
4. **If the TUI exits,** the backend keeps running. The pane says "Press Enter to reopen Hermes", and the TUI reopens only on that
   keypress (law 5: nothing respawns without a click).

**The rendered config (E1.3) gains** what keeps serve offline. Measured: zero external requests across serve, every turn and
the TUI, against a refusing proxy.
- `updates.check: false`, `model_catalog.enabled: false`, `nous.guest: false`.
- `models_dev.url`: the gateway's tokenless mirror.
- `security.allow_lazy_installs: false`. Without it, serve's free-tier bootstrap runs `uv pip install boto3` into the engine
  environment through the proxy, and building the first session installs `edge-tts`.
- `approvals.mode: manual`. The default, `smart`, asks a guardian model.
- `terminal.cwd`: the project root.
- `model.supports_vision` (R3).

**Measured on the pinned build (spike, 2026-10-07):**
- serve listens in 3.1 s (2.5–3.0 s warm);
- the first session is ready 2.1–4.4 s after `session.create`;
- the TUI shows a resumed transcript in 1.3–1.4 s;
- after SIGKILL, serve is listening again in 2.5 s, and resuming a session by id takes 0.1–0.8 s with its history intact. The live
  id and the replay epoch change. A turn killed mid-stream keeps its user row but loses the partial reply.

**A user's own Hermes can stop Lampway's serve:** `hermes serve --stop` and `hermes update` find serve processes by command line
and SIGTERM them (`subcommands/dashboard.py:39-45`). The pane wrapper says so and reopens only on the user's click.

**Persistence (what Mode 1 gains):**
- The pane, and the backend inside it, survive a crash of Blender or of Lampway's server.
- Hermes keeps the session (`state.db` under the unit's home).
- On restart, Lampway's server re-adopts the pane from its record (port, token, session id; the record is 0600) and re-attaches
  as a client (A2).
- Closing the pane ends the backend. Its session stays in `state.db`, and reopening it is the user's click, which resumes it
  by id.

**Build:** `engine_env.py` also prebuilds the TUI at build time, in the engine's own copy of the source, so the pinned tree is
never written to:
- install: `npm ci --workspace ui-tui --include=dev --no-audit --no-fund` against the root `package-lock.json` (an npm
  workspace): 163 packages, 7.3 s online; `--offline` from a populated cache, 5.0 s;
- build: `npm run build` in `ui-tui` (esbuild, 0.5 s) gives a self-contained `dist/entry.js` of 3.6 MB.

The wrapper then points `HERMES_TUI_DIR` at it, and the prebuilt bundle is used as it is (`main_tui_launch.py:556-560`), so at
run time `hermes --tui` never runs npm (law 2). Node (22 measured) is a run-time dependency of Mode 1, found or refused with help,
and never fetched at run time.

**Built 2026-10-07** (`herdr/harnesses/lampway_hermes.py`, `engine/hermes_pane.py`, `engine/units.py`, `engine/wiring.py`;
`scripts/lampway/engine_env.py`):
- **The adapter** describes only: the argv is the server's interpreter running the stdlib-only wrapper by path, plus
  `--home <unit home>`. No task and no token is on it. It has no egress route (`route` None): Mode 1 is Lampway's own engine, whose
  model traffic is the gateway's on loopback and whose every other host goes through the egress proxy; the wrapper's launches are
  declared `local` in `egress.LAUNCHES`. Decision recorded: no `byoa:` route for Mode 1.
- **The home** is written before herdr is asked (the cockpit's `mode1` hook): `config.yaml` and `serve.token` 0600, `pane.json` with
  no secret, a worker's `task.txt`. The record keeps `home`, `port`, `token_file`, `stored_session_id` and the two tokens' digests.
  The server creates the pane's session (`session.create` in the project root, written to `session.json`) and submits a worker's
  task as its first prompt; the wrapper resumes that session in the TUI. A worker's home is `<unit home>/workers/<swarm>-<worker>`
  and its one MCP server is the pane endpoint (S3).
- **The wrapper** follows the four steps above; Enter reopens the TUI, or restarts a serve the user's own `hermes serve --stop`
  stopped; closing the pane (SIGHUP) ends serve by its process group.
- **Measured while building:**
  - serve folds the TUI surface's `project` toolset (`desktop_project`) into every session after `agent.disabled_toolsets` is
    applied, which the start-up check refused. The wrapper therefore pins the toolsets with `HERMES_TUI_TOOLSETS` (the chosen
    toolsets, `clarify`, and the `lampway` server), which replaces the fold-in.
  - herdr 0.9.3's `pane run` joins its arguments with spaces, unquoted. Every typed command is now one shell-quoted string.
  - Without `HERMES_NODE` and `HERMES_SKIP_NODE_BOOTSTRAP=1`, `hermes --tui` would run Hermes's node bootstrap (a download) when
    node or npm is not on PATH.
- **Persistence, live-tested:** after a server restart, reconcile re-adopts the pane, its gateway and MCP tokens are adopted
  again by their digests, and the egress proxy takes its previous port back when free. The conversation goes on in the same
  Hermes session, with no new pane. Live-tested both on played herdr running real ptys and on a real herdr 0.9.3 server.
- **The prebuild:** `engine_env.py` drops the `acp` extra, prebuilds the TUI in the engine's own copy, and records `hermes` and
  `tui` in `engine.json`, written last. `[UNVERIFIED]`: the script's full run end to end. This worktree has no Hermes checkout;
  its npm steps are the ones measured in the spike and its order is pinned by a played build. The live suite ran on the existing
  build with `LAMPWAY_HERMES_TUI_DIR` pointing at the spike's prebuilt `ui-tui`.
- **Opening a pane is the user's chat.** An ended pane is reopened (resuming its stored session) by the user's next chat in that
  tab. This treats the chat as the click law 5 asks for: a decision for the captain.
- **Lampway's instructions reach Hermes (built 2026-10-07).** With the loop gone, `agent/prompt.py`'s guidance fed only the
  generated agent files. The pinned Hermes offers four channels: a project context file (`HERMES.md`/`AGENTS.md` in the cwd,
  which would write into the user's project), `SOUL.md` in the home (replaces Hermes's identity), a plugin's
  `register_system_prompt_section` (code in the home), and the config's `agent.system_prompt` (hermes_cli/personality.py
  `resolve_ephemeral_system_prompt`, read when serve builds a session, appended after Hermes's own prompt on every model call,
  agent/chat_completion_helpers.py:2175-2177). Lampway uses the last, the least invasive: a main pane's config carries
  `SYSTEM_PROMPT` (rewritten for Mode 1: the `mcp__lampway__` names behind `tool_search`, `clarify`, Capabilities, the spend
  and source-file rules); a worker's pane gets its prompt with its task (S3). Measured: the scripted model's system message
  starts "You are Hermes Agent" and carries the guidance (`test_engine_pane_live.py`). The client's turn policy rides in the
  prompt's "This turn" section (R3): Plan Mode (plan, then `clarify` with Approve/Revise), Auto mode (ask nothing this turn),
  the asset-match threshold. `[UNVERIFIED]`, read in the source only: a user's `/personality` in the pane takes the slot instead
  (Hermes prefers a personality), until Lampway writes the config again.

### A2. The island is a second front end on the same live session

Lampway's server is a JSON-RPC client of the pane's `hermes serve`, beside the TUI. Hermes fans every event out to every attached
client (`tui_gateway/transport.py` `FanoutTransport`), and a question goes to every client that asked for server requests, first
answer wins. So the island and the pane show one conversation, and either one can answer. **Mode 1 loses nothing:**

| The island (client protocol) | `hermes serve` (`/api/ws`) |
|---|---|
| attach a scene tab | `client.capabilities {server_requests: true}`, then `session.resume {session_id}`; catch up with `session.events.since(seq)` |
| `agent.chat` | `image.attach_bytes` per image, then `prompt.submit {session_id, text}`; the text carries R3's context blocks (rules, folders, "This turn") |
| `agent.chat` while a turn runs (R4, joins the turn) | `/steer <text>` through `slash.exec` |
| `agent.cancel` | `session.interrupt` |
| text and reasoning | `message.delta` → `ephemeral.append`; `reasoning.delta` → the reasoning slot |
| steps | `tool.start` / `tool.complete` → `steps` (label = the Lampway tool name without `mcp__lampway__`) |
| turn end | `message.complete` → `content.set` + `turn_end` (`complete` → `completed`, `interrupted` → `cancelled`, `error` → `failed`) |
| a question | server request `clarify {question, choices}` → the island's question (`interrupt_id`, `actions`); the answer is the response frame `{answer}`. Both front ends get the request and the first answer wins, but the other is sent no `request.cancel` (measured), so Lampway closes the island's card when the turn moves on (`tool.complete` for `clarify`) |
| a permission | server request `approval {command, request_id, choices: once/session/always/deny}` → the island's permission card; the choice is the response frame `{choice}`; it closes on the turn moving on, as above |
| history (R2) | `session.list`, `session.resume` |

Further mapping rules:
- **A turn the user types in the pane** is shown in the island too. Hermes sends no event that carries the typed prompt:
  `message.start` has no payload, and `session.events.since` does not hold it either (measured). So when a turn starts that no
  island prompt asked for, Lampway opens a turn for it and reads the user's text from `session.history`.
- **`/new` in the pane** asks the user to confirm, then closes the shared session for every client (the TUI calls
  `session.close`). The island receives `sessions.changed`, and then `4001 session not found` (measured). Lampway follows the pane to its new session
  (Q15), starts a new island chat and files the old one in History.
- **Catching up:** `session.events.since {last_seen}` replays the missed events, `message.complete` included. Its ring holds 512
  events per session (`event_replay.py:28`); past that it answers `truncated`, and `session.history` fills in.
- **A disconnect of the island's socket** detaches nothing in Hermes, since the island is only a client. The next `agent.attach`
  replays from `session.events.since`.

**Built 2026-10-07** (`engine/front.py` `HermesFront`, `engine/serve_client.py`; `EngineRuntime` and `LampwayACPClient` removed):
- The table above, as written. The first `agent.chat` of a scene session opens the unit's pane (`Mode1Units.open`) only from the
  user's own Client socket (an agent's socket is refused, `agent_origin`), and only on a herdr server the user started (refused,
  `herdr_not_running`; Lampway never starts it). The M0 `wrong_mode` refusal still comes first.
- A chat sent while the pane's Hermes waits on the island's question is that question's answer (a permission card takes it as
  deny unless it names a choice).
- The island's card closes when the turn moves on without its answer; the rest of the turn is shown as an island turn of the
  same run (a wakeup the current client accepts), whose first event re-sets the card's bubble with "(Answered in Lampway Agent's
  pane.)". A step still running when the turn stopped for a question (a command awaiting approval) is carried into the
  continuation turn.
- A turn typed in the pane is `agent.turn.started {origin: "pane", user_text}` (the text from `session.history`, or the resume
  answer's `inflight.user` after a reconnect).
- `/new` (Q15, as proposed): on `sessions.changed`, `session.status` of the island's session; on `4001`, `session.active_list`,
  the newest other session is resumed and the unit's record and `session.json` follow it, once (serve says `sessions.changed`
  twice), the closed session's question is released (the island's next chat is a prompt, not an answer to it), and the tab's
  current client is told: `agent.pane.new_conversation {session_id, origin: "pane"}` (the tab's session id, the unit, does not
  change, so nothing else would tell it).
- Reconnect: the same replay epoch replays `session.events.since`; a new epoch or `truncated` settles a waited-on turn from
  `session.history`.
- Measured in the live suite: Hermes marks the first `clarify` choice "(Recommended)" and the island shows it as sent; the TUI's
  `/quit` closes only its socket (the session stays live).

**Built 2026-10-07 (client)** (`space_mixie_chat/core/mode1_pane.py`, `turn_events.py`, the script gate in
`main_thread_executor.py` and `connection_manager.py`, `refile` in `chat_history.py` and `checkpoint_store.py`;
`tests/test_mode1_pane_turns.py`; `space_mixie_chat/ARCHITECTURE.md`):
- **A turn typed in the pane is the tab's turn, as an island turn:** the user's bubble from `user_text`, the run, BUSY, the
  executor's undo turn, the cursor, the slots, the end and the History upsert. Only a Mode 1 tab not in a turn of its own takes it;
  a Your agent tab, a BUSY or MODIFYING tab (an island send in flight, an MCP lease) or one with a live turn ignores it with a log
  line. The rest of a turn whose question the pane answered joins the open run as before, without a user bubble. A pane turn takes
  no checkpoint.
- **Its Blender calls** pass the island turn's gates and one more, on the main thread: a script naming a `pane_` turn runs only
  while that turn is live in its own tab (after the tab's queued frames are rendered, since the script can overtake its turn's
  start); an unknown or ended one is refused (`unknown_turn`) and nothing runs. A swarm worker's script, which carries its parent's
  turn id on an `agent:` route, keeps its own gates.
- **`/new`:** on `agent.pane.new_conversation` the old turns are fenced, their queued scripts answered, the old chat filed in
  History under a new id with its media and its checkpoint timeline, the island emptied for the same session id, and one line
  says the pane started a new conversation.
- **`/new` while Lampway was away (built 2026-10-07):** the frame reaches only a connected client. The server names the pane's
  conversation (the Hermes session id) in `agent.turn.started` and `agent.pane.new_conversation` (`conversation_id`) and, per
  Mode 1 tab, in `agent.status`'s new `conversations` map; the client keeps the last one it saw as a scene ID property
  (`mixie_pane_conversation`, saved with the file) and, on the reconnect's status, files the old chat when the pane shows another
  (`mode1_pane.note_conversation`, the same filing as the frame; a turn's start only records). On the server, attaching to a pane
  first asks serve's live sessions (`session.active_list`): a `/new` while Lampway's server was down left the record naming the
  closed session, so the island and the record follow the live one instead of reopening the old conversation, and a connected
  client is sent the frame. `[UNVERIFIED]` in a running app: a reopened `.blend` saved before the `/new`.
- `[UNVERIFIED]` in a running app: the first-hand look of a pane turn in the island, Stop and an island steer during one, an undo
  after one, `/new` with images in the old chat, and a reopened filed chat.
- **Built 2026-10-07 (server, loose ends):** a tool call that overtakes its pane turn (the turn still being opened, `Sink.pending`,
  or serve's `message.start` not yet read) waits for the island turn that shows it, up to 20 s (`front.TURN_WAIT_S`), so its
  script names the turn the client shows; before, it ran under a scratch id the client refused (`unknown_turn`). A question
  nobody can answer any more (Hermes started another turn, or serve restarted and its request died with it) is released, so the
  tab's next chat is a prompt, and its card is closed in the next turn the island shows ("Not answered").

### A3. Tools reach the scene, whoever started the turn

- Each unit's config names one MCP server: `/engine/mcp/<unit>`, with a per-unit bearer (as built).
- A tool call is routed to the scene tab bound to the unit, through that tab's current client socket. It needs no island turn,
  so a turn typed in the pane reaches the scene the same way.
- With no client connected, the call gets a refusal that says Lampway is not open.
- Capabilities gate every call (E2), as today.
- A worker's pane uses the worker endpoint (`/api/v1/mcp/pane`, S3), whatever its mode. Its tools run on the worker's own headless
  scene, and it finishes with `lampway_worker_done`.

**Built 2026-10-07** (`engine/mcp_endpoint.py`, `engine/front.py` `call_tool`, `AgentHub.socket_for`):
- `/engine/mcp/<unit>` takes the unit's bearer (the pane's 0600 config holds it; the server keeps its digest and adopts it again
  after a restart). A call runs through `AgentHub._run_tool` on the socket that last spoke for that scene tab, with the island's
  turn when one runs, else a scratch turn; a call made in a pane-typed turn reaches Blender the same way (live-tested by typing in
  the real TUI).
- With no Lampway window connected the call is refused: "Lampway is not open on this scene".
- Capabilities gate every call at call time (a switched-off family is refused and nothing reaches Blender).
- `ask_user` is not offered: the island's questions are Hermes's own `clarify` (A2). **Decided and built 2026-10-07:** `ask_user`
  left the registry (no agent was offered it, and a question tool has no use beside `clarify`); the hub, the docs, the generated
  agent skills and the two canonical skills that said it "needs the agent loop" were updated.
- Steps come only from serve's `tool.start`/`tool.complete`; the MCP side emits none.
- The client runs a `blender.execute_script` whose `turn_id` names a pane turn only while it shows that turn, and refuses one it
  dropped or that ended (A2, built 2026-10-07, client).

### A4. The herdr view: one unit, one tab, minimal switching

The captain: "A big problem/friction here is context/pane switching. The more we can jam into a single pane without
overwhelming/losing information the better."

**Layout:**
- **Workspace:** one, `lampway`, as today.
- **A unit = one Lampway scene tab's conversation.** Each unit gets one tab, labelled with the scene tab's name. Its root pane is
  the unit's main agent: the Hermes pane in Mode 1, the bound harness pane in Mode 2.
- **Workers split into their unit's tab,** not into tabs of their own:
  - The first worker splits right of the main agent (`pane split <main> --direction right --ratio 0.6`; herdr's ratio is the
    share the split pane keeps).
  - Each further worker splits down inside that column. A swarm passes its worker count, so its workers share the column
    evenly.
  - The main agent keeps the left 60 %, and every worker is visible beside it without switching tabs. `MAX_WORKERS` (6) keeps
    the column readable.
- **Every pane reports what it is,** via `pane.report_metadata`:
  - `display_agent`: "Lampway · <scene>" or "Worker 3 · <task>";
  - `title`: the task;
  - `state_labels`.

  herdr's sidebar then shows every pane's working, blocked and done state at a glance.
- **The island lists the unit's agents and their states** (the Parallel Agents cards). The user rarely needs herdr at all, and
  focusing a pane is one click from a card.
- **A finished worker's pane** stays readable until the unit's next swarm starts. Then Lampway closes the previous run's ended
  worker panes before it splits new ones. It only ever closes a pane it started that has ended, never a live or unknown one
  (law 5). Decided in **Q13**.

**Built 2026-10-07: the next swarm's fresh column (Q13)** (`Cockpit.close_ended_workers`, `SwarmManager._close_ended_panes`):
- **When:** a unit's `swarm_start`, after its run is activated and before any worker pane splits; serialized with the
  placements, so a swarm opening workers at the same moment never splits a pane being closed.
- **What may close:** only a pane whose record says Lampway opened it as a swarm worker (`created_by` swarm, `role` worker, a
  swarm binding) of that unit, and only while herdr still shows it for the terminal the record names (a pane id herdr gave
  another terminal is unknown and stays).
- **"Ended" means one of:**
  - the record is ended (the swarm ended it on cancel, failure or timeout, or reconcile found its harness gone);
  - its binding is not live in this server: `lampway_worker_done` finished it, a failure, cancel or timeout revoked it, or a
    server restart dropped it, so the pane can no longer reach any scene;
  - herdr's process info shows the worker's harness no longer runs (the pane is at a shell prompt).

  A pane herdr cannot inspect is no proof of an end: it stays.
- **Never closed:** the unit's main pane, another unit's panes, an ad-hoc pane, a pane no record names, a worker still working.
- **After:** the record ends with the reason ("closed when its unit's next swarm started"); a Mode 1 worker's gateway key is
  revoked with its pane; `swarm_start` returns what it closed (`closed_panes`), so the agent is told. With the column empty, the
  run's first worker splits right of the main pane, which keeps 60 % again; a worker still working stays, and the new workers go
  on down its column.
- **Tested:** played herdr (`tests/test_herdr_layout.py`, `tests/test_swarm_panes.py`) and the real herdr 0.9.3
  (`tests/test_herdr_layout_live.py`: two finished workers closed, the main pane, another unit's worker and an unknown pane kept,
  the next worker right of the main pane at 60 %).

**Built 2026-10-07 and checked against the real herdr 0.9.3,** built from `herdrdev/herdr`:
- the CLI spellings come from herdr's CLI reference;
- the ratio's meaning comes from its source (`split_node`: the first child is the split pane) and a live server;
- `tests/test_herdr_layout_live.py` drives the real binary.

### A5. What goes, what stays

- **Goes:**
  - `turns.py`'s provider loop (`_agent_loop`, its rounds and its tool dispatch); the hub stays as the client-protocol front end;
  - `agent/swarm_brains.py`'s `BuiltinBrain` and `model_round`;
  - `engine/swarm_brain.py` (`EngineBrain`);
  - `engine/runtime.py`'s ACP children (`EngineRuntime`, `LampwayACPClient`).
- **Stays:**
  - the model gateway, the egress proxy, the config renderer (it gains the TUI settings);
  - Capabilities;
  - the MCP endpoints and the pane endpoint;
  - the harness adapters (B1), the binding (B2) and the island view of a Mode 2 pane (B4);
  - the swarm substrate and `PaneBrain`, which becomes the only worker brain: the adapter decides the mode;
  - the providers, as the gateway's model doors only.
- **Tests:**
  - The hub's protocol tests move off `ScriptedProvider` onto a scripted `/api/ws` peer that speaks the same contract, so they
    run without a built engine.
  - The live suite runs the real pinned Hermes through the same wrapper the pane runs.
  - CI must build the engine (`engine_env.py`), or the live suite skips, and a skip is not a pass.

**Built 2026-10-07** (`agent/turns.py`, `engine/wiring.py`, `engine/front.py`, `engine/units.py`):
- **The loop is gone.** `turns.py` lost `_agent_loop` and everything only it used: its rounds (`MAX_ROUNDS`), `trim_history`, the
  pairing repair (`pair_tool_calls`, `add_tool_results`) and the hub's own message list, `PLAN_MODE_PROMPT`, the empty-reply note,
  the batched `ask_user` wizard, and the Retry-failed-tasks chip with the swarm's retry state. The hub drives only the engine; the
  providers are the gateway's doors only. A source gate (`tests/test_mode1_only_hermes.py`) holds that the hub never streams from a
  provider.
- **No switch.** `LAMPWAY_AGENT_ENGINE` is no longer read: the engine is in Mode 1's seat whenever a finished build is found and the
  server is on loopback. A server that finds the variable set says once that it is ignored.
- **Refused before any turn, with the fix:** no engine build or no prebuilt TUI (`engine_not_built`, help
  `scripts/lampway/engine_env.py`), an engine that could not start or a non-loopback bind (`engine_unavailable`), no Node.js
  (`node_missing`, help Node.js 22 or 24 or `LAMPWAY_NODE`), no herdr (`herdr_not_built`, help `scripts/lampway/herdr_env.py` or
  `LAMPWAY_HERDR_BIN`). The switch to Your agent is named in each, except herdr's: Your agent runs in a herdr pane too. The M0
  `wrong_mode` refusal still comes first. Nothing answers in the engine's place.
- **Kept:** R0a's plan notice (it was shown on engine turns too), `_run_tool` and the registry, Capabilities, the swarm substrate,
  BYOA. `ask_user` was kept in the registry, offered to no agent (Hermes asks with `clarify`); it left the registry on
  2026-10-07 (A3).
- **Fixed on the way:** a swarm the pane's Hermes starts now runs in the island turn that shows its call, so its todo cards and
  progress reach the Parallel Agents panel; the engine path passed no stream, so they never did.
- **Checkpoints:** a mark bookmarks nothing (`has_conversation: false`) and a rewind is refused (`rewind_unsupported`), so the
  client tells the user the agent still remembers the undone turns, where the hub used to claim it forgot them. Rewinding through
  serve's `session.undo` or `session.branch` is proposed, not measured: a decision for the captain. *Superseded, built
  2026-10-07:*
  - **Measured on the pinned serve:** `session.undo {session_id}` drops the last user turn and everything after it, answers
    `{removed: <messages>}`, refuses while a turn runs (`4009`), and is durable: after serve was killed and resumed, the session
    and the next model request lack the undone turns. `session.branch {session_id, count}` copies the visible user and assistant
    rows (tool rows dropped) into a new stored session; it does not change the live one, so it is not a rewind.
  - **Mapped:** the client binds the snapshot before turn N to that turn's command id and marks the tip before a jump. The
    island bookmarks Hermes's point under those ids (before each island turn's prompt, and on `agent.checkpoint.mark`): the user
    turns the session holds and the identity of the last one (its row id and words), in `checkpoints.json` (0600, the unit's
    home). `agent.checkpoint.rewind` calls `session.undo` until the session holds the bookmark's turns, counting again after
    each undo, and answers `{ok: true, has_conversation: true, removed_turns}`.
  - **What differs from the upstream backend's fork:** Hermes's undo is destructive. A rewind forward (to the tip after going
    back, or to a bookmark whose last turn was undone and replaced) cannot bring the turns back and is refused
    (`rewind_forward`); so is a rewind into a conversation the pane left with `/new` (`rewind_other_conversation`, the old one is
    left as it was), one while the agent works (`rewind_busy`) and one with no pane connected (`rewind_unavailable`). The client
    then shows "the conversation could not be rewound" with Lampway's reason; its fixed tail ("may still remember the undone
    turns") is the client's own wording. A turn typed in the pane takes no checkpoint (A2), and an undo is at user-turn
    granularity: a rewind to a checkpoint inside a turn (an answer to a question) keeps that turn. `[UNVERIFIED]`: whether the
    TUI's transcript drops the undone turns at once (Hermes sends no event for another client's undo that Lampway saw).
  - Tests: `test_questions_checkpoints.py` (the scripted serve), the live `test_engine_pane_live.py` rewind on the real serve.
- **Tests:** the hub's protocol tests run on the scripted serve (`tests/serve_support.py`: `FakeServe`, `stack`/`run` on a real port,
  `ServeThread`/`mode1_turn` under a TestClient); the tests whose subject was the loop itself were deleted.
- `[UNVERIFIED]`: the `mock` provider (written for the loop) has not been run against Hermes, whose tool names it does not use; CI
  does not build the engine yet. *The mock, built 2026-10-07:* it now answers Hermes behind the gateway: Lampway's tools by the
  names Hermes offers (`mcp__lampway__<tool>`, or the `tool_call` bridge when deferred), never one the request did not offer, text
  only for a request with no tools (Hermes's title call). Live-tested on the pinned serve: a question gets the scene's summary
  from Blender, a `py:` message runs its script in the scene. CI still does not build the engine.

## 0. Where the code is today

| Area | Today | Source |
|---|---|---|
| Session identity | `Scene.mixie_session_id` (uuid4, saved in the .blend): one session per scene tab | `space_mixie_chat/core/session.py:276-283` |
| Server chat state | In memory only (`AgentHub.sessions`); lost on restart | `server/.../agent/turns.py:98-99` |
| History curation | Results clipped at 20,000 chars; oldest results swapped for a note past 200,000 chars; no token counts, no summaries | `turns.py:34-36,565-589` |
| Turn payload | Server reads `message`, `session_id`, `plan_required`, `mark_context`; drops images, rules, folders, project context, preferences, auto mode | `turns.py:143-301`; client `chat_payloads.py:241-292` |
| Disconnect | Turn cancelled; journal kept in memory for `agent.attach`; `agent.parked_turn` always `{has_parked:false}` | `ws.py:92-100`, `turns.py:241` |
| History archive | Server advertises `agent_history_v1/v2` but answers `agent.history_sync` with −32601; the client stops syncing | `ws.py:25,122`; `agent_history/core/sync.py:185-186` |
| Tool-call pairing | Assistant tool calls appended before the tools run; results appended after all finish; a cancel in between leaves calls with no results | `turns.py:358-384` |
| Provider selection | `PUT /agent/byok` accepts anthropic/openai keys only; its provider, model and base_url are never read by the provider factory; `provider="local"` gets 422 | `agent_settings.py:42,82-94`; `providers/__init__.py:27-60` |
| CLI "providers" | `claude_cli`, `codex_cli` (transcript flattened into `claude -p` / `codex exec`), `codex_app_server` (Codex app-server as Lampway's model), `codex_image` | `agent/cli_adapters.py`, `providers/codex_app_server.py` |
| Codex token read | BYOK "Codex (ChatGPT sub)" reads `~/.codex/auth.json` and sends it as `api_key` | `byok/ui/operators/byok_ops.py:286-293,370-430` |
| herdr | Lampway's own `herdr server`; panes `claude --session-id/--resume`, `codex [resume]`, `opencode [--session]`; registry `sessions.json`; reconcile never spawns or kills | `herdr/launcher.py`, `herdr/host.py` |
| Panes ↔ MCP | Not wired: no per-pane MCP config; panes see Lampway only if the user added the connector at user scope | `host.py:106-149`; `mcp_bridge/core/app_configs.py` |
| Pane environment | herdr inherits the server's environment minus `HERDR_*` (API keys included); panes get the real HOME, XDG, `CLAUDE_CONFIG_DIR`, `CODEX_HOME` | `launcher.py:42-61` |
| Pane transcripts | `observers/native.py` tails Claude and Codex session files; not wired to anything | `herdr/observers/` |
| MCP scene tools | Never run: the server opens no MCP operation and sends no `mcp_operation_id` (audit F2); the launcher crashes on start (F1) | `server/.../mcp.py:129`; `mcp_bridge/constants.py` |

The in-tree terms note that draws the BYOA line, quoted from `agent/cli_adapters.py:8-18`: Anthropic "does not permit third-party
developers to … route requests through Free, Pro, or Max plan credentials on behalf of their users"; "running the unmodified
`claude` binary yourself, for yourself, is the user using Claude Code". The same file calls the Codex equivalent "a grey area"
and names Sign in with ChatGPT as OpenAI's supported route for third-party apps. Reading of terms is the captain's; this spec only
builds to the line the captain drew.

## M0. One agent mode per scene tab

**Purpose.** Make the mode explicit, per scene tab, so the client, the server and the MCP lease agree on who drives a scene.

**Contract.**
- New saved scene property `Scene.lampway_agent_mode`: `runtime` (default) or `byoa`; with `byoa`, `Scene.lampway_byoa_pane` holds
  the herdr session id bound to the tab.
- The island's mode switch lives beside the existing agent picker (`MIXIE_CHAT_MT_agent_model`): **Lampway Agent** (Mode 1, with
  its provider list) and **Your agent** (Mode 2, with the harnesses found on the machine).
- Switching is refused while the tab is BUSY, MODIFYING or AWAITING_INPUT, or holds an MCP operation (`code: scene_busy`, help:
  finish or stop the turn).
- Exclusivity is enforced by the MCP lease (R7): a Mode 1 turn and a BYOA tool call can never run in the same tab at once.
- Each tab keeps its own history: switching modes does not carry the conversation across (the two runtimes do not share a
  transcript format). The island says so when the user switches.

**Tests.** Switch refused while BUSY; the property survives save and reload; a BYOA call into a tab in `runtime` mode is refused
with `code: wrong_mode` and a help line naming the switch; two tabs can run one mode each at the same time.

---

# Mode 1 — the Lampway Agent Runtime

The client keeps upstream's architecture (thin client, per-tab sessions, numbered event stream, attach/replay, checkpoints, parked
turns, archive sync). The server becomes a complete local implementation of the protocol the client already speaks. Contracts
R0–R8.

## R0. Providers: an API key or a bare endpoint, nothing else

**Purpose.** Mode 1 thinks through a key the user owns or an endpoint the user runs. It never drives a plan through a CLI.

**Contract.**
- Provider kinds in Mode 1: `anthropic` (API key), `openai` (API key), `openrouter` (API key, budget cap kept), and
  `openai_compatible` (any `base_url` serving `/v1/chat/completions`: llama.cpp, Ollama, vLLM, LM Studio; key optional).
  `mock` stays for tests.
- `PUT /api/v1/agent/byok` drives the provider: `provider`, `model` and `base_url` are stored in Connections and Choices and the
  factory (`providers/__init__.py:make_provider`) reads them. `provider="local"` (what the client's `local_models` sends,
  `orchestrator.py:228`) maps to `openai_compatible`.
- A loopback `base_url` is local; any other host, a LAN box included, belongs to the `custom_llm` egress route, which the user
  switches on (law 2). Built 2026-10-07, stricter than this spec's first draft, which counted RFC1918 hosts as local.
- The model list comes from the endpoint (`GET {base_url}/v1/models`) with an ETag, falling back to the configured model.
- **Retired from Mode 1's chains:** `claude_cli`, `codex_cli`, `codex_app_server` and `codex_image` (the CLI-as-endpoint providers
  in `cli_adapters.py` and `providers/codex_app_server.py`), from `agent.main`, `agent.worker`, `agent.vision_judge`,
  `normalize.judge`, the setup wizard step "Where the agent thinks" (`ui/onboarding.py:20-27`) and the Providers dialog. Their
  place is Mode 2.
- **Removed:** the client's BYOK "Codex (ChatGPT sub)" option that reads `~/.codex/auth.json` (`byok/constants.py:72-81`,
  `byok_ops.py:286-293,370-430`). Lampway never reads another app's credentials.
- `chatgpt_plan` (Lampway's own Sign in with ChatGPT client, `chatgpt_auth.py`) is a bare endpoint with an OAuth bearer instead of
  a key, researched 2026-10-06:
  - **The route:** `POST https://api.openai.com/v1/responses`, with Lampway's loop, instructions, history and function tools.
    No Codex binary or harness is involved (`agent/providers/chatgpt_plan.py`).
  - **OpenAI documents this direct route** as one of two integrations; the other is Codex app-server, which is optional.
  - **Request constraints** (preview limitations page):
    - `store: false` and `stream: true`; the full history goes in `input`.
    - `instructions` or developer messages; system-role items are rejected.
    - Function tools are grouped in a namespace; hosted tools are not available.
    - Rejected fields include `temperature`, `top_p`, `max_output_tokens`, `truncation`, `metadata` and `user`.
    - Usage-limit failures arrive mid-stream as `response.failed`.
  - **Eligibility:** open-source and locally hosted apps; hosted or paid apps go through OpenAI's interest form.
  - **Developer obligations** (cookbook): keep tokens local, never proxy or share them, and tell users when a request uses their
    plan.
  - **Fit:** it therefore fits Mode 1's runtime. R1's durable history is what the route expects (`store: false`, no
    `previous_response_id`), and R3's budgeting matters more because the whole history is re-sent every round.
  - **Decision (captain, 2026-10-06, Q1):** both. Sign in with ChatGPT is a Mode 1 provider, and Codex CLI is a BYOA harness
    (B1). A ChatGPT subscriber picks either Lampway's runtime on their plan or their own Codex, per scene tab (M0).

**Tests.** `make_provider` honours a stored `openai_compatible` base_url and model; `provider="local"` is accepted; a non-local
base_url refuses until its route is on; the four retired options are absent from every Choices purpose and the wizard; a source
test finds no read of `.codex/auth.json` in the client.

## R0a. Sign in with ChatGPT in Mode 1

**Purpose.** Keep `chatgpt_plan` on OpenAI's documented direct route, inside its stated limits, with the disclosure the developer
guidance asks for.

**Contract.**
- **Route:** only `POST https://api.openai.com/v1/responses` with Lampway's own OAuth client (`chatgpt_auth.py`), as today.
  - Never Codex's tokens, never ChatGPT's backend.
  - No Lampway endpoint forwards a request to this route for another tool. A test asserts the route table has no such proxy.
- **Request shape:**
  - `store: false` and `stream: true`; the full history comes from R1 every round; `instructions` carries the system prompt.
  - Tools go in the `lampway` namespace.
  - None of the rejected fields are sent (`temperature`, `top_p`, `max_output_tokens`, `truncation`, `metadata`, `user`,
    `background`, `conversation`, `max_tool_calls`, `moderation`, `multi_agent`, `prompt`, `prompt_cache_retention`,
    `safety_identifier`, `top_logprobs`). A test builds a request and checks for each one.
- **Models:** listed from `GET /v1/models` with the access token; only `visibility: "list"` entries are shown.
- **Images:** R3's image parts are sent only after a live probe shows the route accepts them. Until then the island says images
  are not sent on this provider, and the turn goes ahead with text. Treat this as `[UNVERIFIED]` until the probe has run.
- **Disclosure:** while a tab uses this provider, the island's provider chip reads "Using your ChatGPT plan". The first turn on a
  session shows that once, in the transcript. A usage-limit failure shows its recovery text and the plan usage link (today's
  `_RECOVERY` table), with no fallback to another billing path.
- **No hosted tools:** image generation stays off this provider (GPT Image is unavailable on the route). Image tools ask for
  another configured image backend.
- **Codex goes to BYOA:** `codex_app_server` and `codex_image` leave Mode 1 (R0). Codex users run Codex CLI as a BYOA harness
  (B1), on Codex's own login, which Lampway never reads.
- **Hosting:** if Lampway is ever offered hosted or paid, this provider stays off there until OpenAI's interest-form approval is
  recorded.

**Tests.** The request-shape test; the no-proxy route test; a recorded stream with `response.failed`
(`subscription_sharing_usage_limit_exceeded`) ends the turn with the recovery text and no retry on another provider; the provider
chip and the first-turn notice appear for this provider only; an image attachment is withheld with the notice until
`chatgpt_vision_ok` is recorded by the probe.

## R1. Durable sessions

**Decision (captain, 2026-10-07):** Mode 1 durability is the Hermes runtime's. Its sessions (`state.db`, `load_session`, `resume_session`, `fork_session`, `list_sessions`) are the conversation record; Lampway builds no store of its own and maps the client's calls onto them (E1.7). What stays Lampway's from this section is the pairing invariant (built 2026-10-07, `turns.py`), which the current loop needs until E1 replaces it, and which the E1.8 suite checks on Hermes.

**Purpose.** A conversation survives a server restart, a crash and an app restart, and the agent keeps its memory of the chat.

**Contract.**
- Store under `<state_dir>/agent/sessions/<session_id>/`: `meta.json` (created, updated, provider, model, title, turn count,
  status), `messages.jsonl` (one neutral message per line, append-only), `turns/<turn_id>.jsonl` (the numbered event journal),
  `bookmarks.json` (checkpoint marks). Files 0600, directory 0700 (the same discipline as the Connections store).
- Write-ahead: a message is appended and flushed before the model sees the next round; an event before it is sent.
- Load on first use of a session id after a restart; `agent.attach` and `agent.status` read the journal from disk.
- `checkpoint.rewind` truncates `messages.jsonl` by rewriting to a temp file and renaming, never in place.
- **Pairing invariant (fixes the cancel bug):** every assistant `tool_call` has exactly one `tool_result` before the next model
  round or the end of the turn. On cancel, disconnect, timeout, a new `agent.chat` during an open question, or an `ask_user`
  issued beside other calls, the runtime appends a result for each unanswered call (`{"cancelled": true, "reason": ...}` or the
  question's answer). On load, a repair pass adds the same synthetic results to any older history that lacks them.
- Retention: sessions untouched for `retention_days` are archived to `<state_dir>/agent/archive/<yyyy-mm>.tar.zst` and removed
  from the live store; a cap on live sessions. Captain's values (Q2, approved 2026-10-06): 30 days and 200 sessions.
- In memory, an LRU of live sessions (proposal 32) replaces the unbounded dicts (`sessions`, `turns`, `commands`, the Anthropic
  `_raw_assistant` map, Codex clients).

**Tests (RED first).** Restart the hub between two turns: the second turn's request to a recording provider carries the first
turn's messages. A cancel during a tool call leaves a paired, cancelled result (fails today). An `ask_user` beside another tool
call: both calls end with results (fails today). A new `agent.chat` while a question is pending: the question's call gets a result
and the pending question is cleared (fails today). Retention moves an old session to the archive and `attach` then answers
`unavailable`. A history written by the old code with an orphan call is repaired on load.

## R2. The archive the client already asks for

**Decision (captain, 2026-10-07):** served from Hermes's sessions (E1.7), not from a Lampway journal. Until then the handshake stops advertising what it does not serve.

**Purpose.** Fill the client's agent archive (`common/agent_history`), or stop claiming to.

**Contract.**
- Implement `agent.history_sync` (version 1): manifests and event pages from R1's store, acknowledged by the client after fsync,
  32 sessions per poll as the client expects (`sync.py:149-238`).
- Implement `agent.history_read` on request.
- Advertise `agent_history_v1` only when served. `agent_history_v2` (images fetched over HTTP from
  `/api/v1/agent/history/blob`) is advertised only once that route exists, with blobs content-addressed under
  `<state_dir>/agent/blobs/`.
- Until then the handshake stops advertising what it does not serve (`ws.py:25`).

**Tests.** A recorded client sync against R1's store yields the same events the live stream sent; an unadvertised capability is
never answered with −32601 (the client's silent stop).

**Built 2026-10-07** (`engine/history.py`, `HermesFront.history_sync`, `AgentHub._history_sync`, `ws.server_capabilities`):
- `agent.history_sync` (version 1) is served from the unit's `hermes serve`: the session the pane shows (`session.history` on the
  live session, read again only after a new event) and, first, a previous session of the unit that still has records the client
  never acknowledged (`session.list`; resumed from `state.db`, read, closed again), one packet per unit per poll. A tab with no
  live pane this server is connected to has nothing to send.
- Each message (user, assistant, tool rows, in order; measured row shape: `{role, text, timestamp, row_id}`, a tool row with
  `name`, `context`, `tool_call_id`) is one record `{version: 1, run_id: <Hermes session id>, task_id: "main", kind: "message",
  payload: {id, role, text, ...}}` at its 1-based position, `event_id` the sha256 of the client's canonical JSON.
- Lampway stores no conversation. Its delivery state is the acknowledged prefix's length and digest per Hermes session
  (`archive.json`, 0600 in the unit's home). An epoch is one Hermes session and rewrite: a history that no longer starts with the
  acknowledged prefix (Hermes's undo, a checkpoint rewind) gets a new epoch and is sent again whole, which the client records as
  an epoch change, never a replay conflict. The owner id is one constant (`lampway-local`: one local account).
- The handshake advertises `agent_history_v1` only while the engine runs Mode 1, never `agent_history_v2` (no image route; no
  record carries an image). `agent.history_read` is the client's own answer to a server's request; Lampway sends none (Hermes keeps
  its own memory).
- Tests: `test_engine_history.py` (the scripted serve), the live `test_engine_pane_live.py` archive test on the real serve, and the
  client's `tests/test_agent_history_hermes.py`, which writes the server's packets with the client's own store.
- Found on the way: serve numbers each session's events from 1, so after following the pane's `/new` the island dropped the new
  session's first events as already seen; the count now starts again on a follow, and other sessions' events are ignored before
  their `seq` is counted.

## R3. Context the client sends, read and used

**Purpose.** Everything the user attaches or configures reaches the model.

**Contract.** The runtime reads the fields it ignores today (`chat_payloads.py:241-292`, `turn_transport.py:55-64`):
- `content` images → provider image parts (Anthropic and OpenAI-compatible vision), stored once as blobs (R2).
- `rules` snapshot → a system-prompt section "Project rules" / "Your rules", replacing the legacy prose prefix in `message`.
  The client stops prefixing once the server advertises `rules_snapshot_v1`.
- `folder_context` → a "Context folders" section listing the attached roots, plus server-issued `context_folder.list/read/search/
  view_image` calls (the client already serves them, `socket_dispatch.py:85`) exposed to the model as tools.
- `project_context`, `attachment_names`, `imported_object_names` → a short "This turn" section.
- `auto_mode`, `approval_required`, `execution_required` → turn policy (R4).
- `user_preferences.asset_match_threshold` → passed to the asset tools that take it.
- **Client fix:** the rules header decides "new session" before `turn_checkpoints.capture()` mints the id (today the order is
  reversed, `chat_ops.py:299` before `composer_send.py:93`, so the new-chat header never fires); New Chat resets
  `mixie_chat_rules_sent_hash`.

**Budgeting (captain, 2026-10-06, Q3).** Context management is left to the Hermes runtime's own settings: its context engine,
compression threshold, protected recent turns and summarising model. Lampway does not add a second budget.
- The **Agent Panel** gains a "Context" section that edits those settings.
- The section writes them to the engine's `HERMES_HOME/config.yaml` (E1.3) per project, and reloads the session.
- Lampway shows Hermes's defaults and the model's window. It never overrides them silently.

**Tests.** An attached image reaches a recording provider as an image part; changed rules appear in the next request's system
prompt and not in `message`; a folder attached in the client is listed and readable by the model; the summary replaces old turns
past the budget and the pinned summary survives a restart.

## R4. Turn semantics the client renders

**Purpose.** Produce the events the client already renders, and stop cancelling on interjection.

**Contract.**
- **Interjection joins the running turn:** a second `agent.chat` during a turn is queued and delivered to the model as a user
  message at the next round boundary (today it cancels and restarts, `turns.py:276`). An explicit Stop still cancels.
- Live tool progress: `agent.tool_start`, `agent.tool_end` and the typed `activity` event (step plus images per tool) as the client
  expects (`socket_dispatch.py:88-107`).
- `ephemeral.set` for model reasoning where the provider exposes it, so the client's thinking dropdown shows thinking rather than
  narration.
- Input types the client renders but never receives: `confirm` and `approval` for gated actions (`approval_required`, `auto_mode`
  off), `file_save` and `file_open` with `interrupt_context` for export and import pickers, `question_ref`.
- `agent.command.delivered` on admission.
- `agent.status` reports `abandoned` for a turn whose socket closed while running, so the client's resume prompt fires
  (`turn_resume.py`).
- `agent.feedback` stored with the turn in R1 (a rating and the user's note; never sent anywhere).
- `generation.agent_result` accepted and turned into a message for the session that enqueued the job (today −32601).

**Tests.** An interjection arrives as a user message in the same turn (fails today); `approval_required` produces an `approval`
input and waits; a socket closed mid-turn reports `abandoned`; a finished generation produces a message in the right session.

## R5. Parked turns

*Superseded by A:* the turn lives in the pane's `hermes serve`, so nothing parks. The island re-attaches as a client (A2).

**Decision (captain, 2026-10-07):** the Hermes runtime keeps the ACP session alive across a client disconnect (E1.7); Lampway does not park turns itself.

**Purpose.** A disconnect stops losing the work in progress.

**Contract.**
- On socket close the runtime parks the turn if no script is in flight: the model round is allowed to finish, its tool calls are
  not executed, and the turn is marked `parked` in R1 with the pending calls.
- With a script in flight, the call's result is recorded as `{"interrupted": true}` and the turn is parked after it.
- `agent.parked_turn` returns the parked turn; the client's existing auto-resume sends "continue" once per session per process
  (`parked_resume.py:150-212`), and the runtime resumes from the pending calls.
- A parked turn expires after `park_ttl`: 24 h (Q2, approved 2026-10-06).

**Tests.** Close the socket between rounds: the turn parks; reconnect: `agent.parked_turn` reports it and continue resumes it with
the same history; a script in flight at close is recorded as interrupted, never re-run.

## R6. Swarm and workers under the same rules

- Workers' histories go to R1 under `<session_id>/workers/<worker_id>/` and obey the pairing invariant.
- `agent.worker` chains use only Mode 1 providers (R0). The v3 execution harness is unchanged.

## R7. The MCP lease (audit F2), shared by both modes

**Purpose.** Every script that reaches a scene from outside a Mode 1 turn runs inside an MCP operation; the lease is also what
keeps the two modes from colliding.

**Contract.**
- `McpServer._call` sends `mcp.begin_operation {operation_id, session_id, timeout_seconds}` over the hub before the script.
- It passes `agent_ctx.mcp_operation_id` with every `blender.execute_script`.
- It sends `mcp.end_operation` in `finally`.
- A refusal (`scene_busy`, `scene_offline`, `ui_busy`, `document_changed`) is returned to the MCP client with its help line.
- A BYOA pane may hold one operation across a burst of calls (begin on first call, renew while calls keep arriving, end after an
  idle gap of 10 s), so the agent-working halo does not flicker.

**Tests.** A fake client enforcing the same gate as `connection_manager.on_script_execute` admits scripts only inside an operation
(fails today); a Mode 1 turn running in a tab makes a BYOA call into it answer `scene_busy`; the operation always ends, including
on exception.

## R8. Documentation and capability truth

- `ARCHITECTURE.md` and the module docstrings describe Lampway's runtime (no LangGraph thread, no 7-day hosted retention, `~/.lampway`
  paths, `LAMPWAY_AGENT_HISTORY_DIR`).
- The handshake's `server_capabilities` lists exactly what is served; a test compares it with the method table.

## E0. The engine seat, and where Hermes Agent fits

**Question (captain, 2026-10-06).** Gut the agent backend, build Lampway's own, re-derive what people already like, and pin the
Hermes Agent runtime (`NousResearch/hermes-agent`) upstream in the same seat?

**What "the seat" is.** Mixar's hosted agent backend was never in this tree. What Lampway has is its own reimplementation of the
protocol the Mixar client speaks, in `server/lampway_server/agent/` (about 6,400 lines):
- **Tool definitions, about 3,500 lines:** Lampway's domain; they stay whatever runs the loop.
- **The Blender bridge and v3 swarm protocol (`harness.py`, about 270 lines):** stays.
- **The engine, about 2,000 lines:** `turns.py`, `providers/`, `swarm.py`, `cli_adapters.py`, `prompt.py`, `questions.py`. This is
  the part that can be gutted.

**Hermes Agent, researched 2026-10-06** (read-only clone of `main` at `65bc672`; nothing run):

| Point | Finding | Bearing on the seat |
|---|---|---|
| Licence | MIT (`LICENSE`, `pyproject.toml`) | Can be pinned or partly copied into GPL Lampway with the notice kept |
| Python | "we *only* support 3.14" (`pyproject.toml:11`); no supported wheel; PyPI stale at 0.19.0 | Lampway's server runs 3.12/3.13; pinning means a separate interpreter and environment |
| Size and pace | 245 MB checkout, 328 locked packages; v0.21.5 on 2026-09-24, patch releases every 3–7 days, about 17k non-merge commits in 30 days | Review-before-bump is impractical; pin a release only |
| Stability | `AGENTS.md`: "internal paths are not API"; no re-export shims; protocol changes ship in patch releases | An in-process embed breaks on routine bumps |
| Embedding | `AIAgent(...).run_conversation` with stream, tool start/end, reasoning, `clarify` and event callbacks; `interrupt()`, `steer()`; `HERMES_HOME` isolation; synchronous, one agent per thread, process-global tool registry and environment | Possible, but one blocking thread per tab and shared globals across tabs |
| Built-ins | Shell, files, browser, code execution, self-written skills, memory, cron, 20 messaging gateways | All must be switched off for Lampway's seat (`enabled_toolsets=[lampway]`, skip memory and skills) |
| Providers | API keys, OpenRouter, local endpoints; plus an Anthropic OAuth that "routes as Claude Code", and import of `~/.codex/auth.json` | Conflicts with R0 and B0 (no plan credentials behind Lampway's loop, never read another app's tokens); those providers must be disallowed |
| Egress | `requests.get("https://models.dev/api.json")`, Portal request tags, subprocess tools | Bypasses law 2's httpx choke point unless pre-seeded and disabled |
| Protocol seams | OpenAI-compatible HTTP+SSE server; TUI-gateway JSON-RPC over stdio or WebSocket; ACP; MCP client and server | A child-process seam keeps Lampway's gates in Lampway's process |

**Three ways to use it.**
1. **In-process library in the seat.** Not recommended: an unstable internal API, Python 3.14 only, global state across tabs,
   built-ins to strip and egress outside the choke point.
2. **Pinned child process behind the seat.** Lampway's server keeps the client protocol, the Blender bridge, R1 history, egress,
   spend and receipts, and drives a pinned Hermes release over its TUI-gateway JSON-RPC or ACP, exposing Lampway's tools to it over
   MCP. Feasible; the cost is tracking a protocol that changes in patch releases.
3. **Hermes as a BYOA harness (Mode 2).** The user runs their own `hermes` in a herdr pane on their own keys; it reaches Lampway
   through Lampway's MCP server like Claude Code or Codex. No coupling, no new gates. Hermes's own provider choices are then the
   user's, in the user's own app, outside Lampway's loop.

**Decision (captain, 2026-10-06, Q7).** Hermes Agent's runtime takes Mode 1's engine seat. The parts that do not fit the seat
are switched off. The rest of this section specifies how. Way 2 (a pinned child process over a protocol) is chosen over way 1
(in-process), because it gives the whole runtime while keeping Lampway's laws in Lampway's own process.

## E1. Hermes in the seat, over ACP

*Superseded by A (captain, 2026-10-07).* Hermes runs its own TUI in a herdr pane, and the island is a second client of the pane's
`hermes serve` (A1, A2). ACP and the hidden child go. What carries over unchanged:
- the gateway (E1.4) and the egress proxy (E1.5);
- the config renderer (E1.3);
- the MCP endpoint (E1.6, now per unit, A3);
- the Hermes behaviour measured below.

E1.7's mapping is replaced by A2's table. The ACP build is kept in the history (`engine/runtime.py` up to the A5 removal) as
the record of what was measured.

**Why ACP.** `hermes acp` speaks the Agent Client Protocol, an open editor–agent standard (VS Code, Zed and JetBrains use it). A
published spec is a steadier seam than Hermes's internal Python API, which its own guide says is not API. What Hermes's ACP side
serves (`acp_adapter/server.py` at `65bc672`):
- **Handshake:** `initialize`, `authenticate`.
- **Sessions:** `new_session(cwd, mcp_servers)`, `load_session`, `resume_session`, `fork_session`, `list_sessions`.
- **Turns:** `prompt` and `cancel`.
- **Settings:** `set_session_model`, `set_session_mode`.
- **Permission prompts:** `request_permission`.
- **Steering:** `/steer <text>` while a turn runs (`acp_adapter/commands.py:287`).

**Shape.** Lampway's server is an ACP client. It owns the client protocol, the tools, the gates and the model gateway; Hermes owns
the conversation.

```
Lampway app ⇄ (agent WS, unchanged) ⇄ Lampway server ⇄ (ACP over stdio) ⇄ hermes acp  [pinned release, own Python 3.14]
                                         │  ▲                                  │
                                         │  └── Lampway tools, served as one MCP server per session (passed in new_session)
                                         └──── model gateway on loopback  ◄────┘  (Hermes's only model endpoint)
```

**Contract.**

*E1.1 Pinning and install.*
- `third_party/hermes-agent` is a git submodule pinned to a release tag (today `v2026.9.24` / v0.21.5), like `upstream/` for
  Blender. Its MIT notice goes into `NOTICE.md` and REUSE.
- The build makes a separate environment with `uv` from Hermes's own `uv.lock` and Python 3.14, under
  `<install>/engines/hermes/<tag>/`. It never touches the user's `~/.hermes` or a Hermes the user installed.
- Bumping the pin is a lane of its own. It merges only when the engine-conformance suite (E1.8) passes against the new tag.

*E1.2 Process model.*
- One `hermes acp` child per scene tab that has a live turn, reaped after an idle period (proposal 10 minutes). Each child gets
  `HERMES_HOME=<state_dir>/agent/hermes/<session_id>`.
- One process per tab avoids Hermes's process-global tool registry and environment, which its docs warn about.
- Whether one process can safely serve several sessions is `[UNVERIFIED]`, so start with one per tab.
- Children start through `egress.guard("agent_engine", ...)`, are niced, and are killed on server shutdown. They are Lampway's
  engine, not user agents, so law 5's herdr rules do not apply.

*E1.3 Nothing is removed; everything is chosen (captain, 2026-10-06).* Every Hermes ability stays available. What a given agent
may do is set in one place, Capabilities (E2), the way outbound routes are set today.
- **Config:** Lampway writes each child's `HERMES_HOME/config.yaml` from the user's capability choices before start
  (`platform_toolsets.acp`, memory, skills, cron, gateways and terminal backend). After a change it rebuilds the session with
  `load_session`, so the agent's tool list always matches the switches.
- **Start-up check:** on start, Lampway checks the advertised tool list against the choices and refuses a mismatch.
- **What is not a capability:** where the agent thinks (providers and logins) is set in Choices under R0, not here. Hermes's own
  provider logins are therefore not configured:
  - the Anthropic route that "routes as Claude Code";
  - Codex with the `~/.codex/auth.json` import;
  - Nous Portal, Copilot, xAI and Qwen OAuth.

  This follows the earlier decisions: no plan credentials behind Lampway's loop, never read another app's tokens. The captain
  confirmed it on 2026-10-06 (Q9): Lampway's engine and a user's own Hermes stay separate by design (E1.10).
- **models.dev:** the cache is pre-seeded and its URL pointed at the gateway, so model metadata never needs a capability or a route.

*E1.4 Models go through Lampway's gateway.*
- The server exposes an OpenAI-compatible endpoint on loopback, for the engine only: `/engine/v1/chat/completions` and
  `/engine/v1/models`, with a per-process token.
- Its backends are R0's providers: API keys, bare endpoints, and Sign in with ChatGPT (R0a), which the gateway translates to the
  Responses route with the `lampway` tool namespace.
- So credentials, egress (law 2), budgets and the ChatGPT-plan disclosure stay in Lampway. Hermes holds no key and no token.
- Whether to also expose an Anthropic-native endpoint, to keep prompt caching and thinking blocks, is `[UNVERIFIED]`: it depends on
  Hermes accepting a custom base URL for its `anthropic_messages` mode.

*E1.5 Egress enforced at the process.* Each child runs with `HTTPS_PROXY`/`HTTP_PROXY` pointed at a Lampway loopback proxy that
allows the gateway plus the hosts of the routes the enabled capabilities need (E2), and denies everything else, with a log row per refusal. With `NO_PROXY` unset, a library that ignores
`HTTPS_PROXY` (`requests` honours it by default) still reaches only loopback. Any denied attempt is surfaced in the Privacy panel.

*E1.6 Tools.*
- Lampway serves the engine one MCP endpoint per session (`/engine/mcp/<session_id>`, token-bound to the child). It offers the
  agent's full registry, the same tools Mode 1 has today, not the external-app subset.
- **Replies are TOON** (captain, 2026-10-06): the endpoint uses the companion spec's C1 envelope and C0 encoder, as external apps
  do. The token counts and task success with JSON and with TOON are recorded on the same tasks.
- Every call runs through `ToolRunner` (E0): the Blender bridge, the R7 lease, spend plans, receipts and egress.
- **Questions:** Hermes's ACP mode has no `clarify`, so `ask_user` is a Lampway MCP tool that holds the call open until the user
  answers in the island (the client's existing choice and text inputs).
- **Permissions:** `request_permission` from Hermes maps to the client's `approval` input (R4).
- **Swarm:** Lampway's swarm tools stay MCP tools (Lampway's headless-Blender workers with the v3 harness); Hermes's
  `delegate_task` stays off.

*E1.7 Mapping to the client protocol.* The client is unchanged. `AgentHub` translates in both directions:

| Client | ACP | Notes |
|---|---|---|
| `agent.chat` (new tab) | `new_session(cwd=project root, mcp_servers=[lampway])`, then `prompt` | the ACP session id is stored in R1's `meta.json` |
| `agent.chat` (continuing) | `load_session` / `resume_session` if the child was reaped, then `prompt` | |
| interjection (`agent.chat` mid-turn) | `prompt` with `/steer <text>` | R4's join semantics |
| `agent.cancel` | `cancel` | |
| `agent.input` (answer) | the result of the pending `ask_user` MCP call, or the `request_permission` reply | |
| `agent_message_chunk` | `ephemeral.append`, then `content.set` at the end | |
| `agent_thought_chunk` | `ephemeral.set` (thinking) | |
| `tool_call`, `tool_call_update` | `steps` rows and `agent.tool_start/end` | |
| `plan` | `todo` slot | |
| stop reason | `turn_end` (`completed`, `cancelled`, `max_tokens` with the cut-off note) | |
| `checkpoint.mark` / `rewind` | `fork_session` at the mark / switch to the fork | `[UNVERIFIED]` that fork can target an earlier message; if not, rewind replays the kept prefix into a new session |
| `agent.attach`, `agent.status` | the live turn's events while it runs; afterwards `load_session`, which replays the conversation as `session/update` notifications `[UNVERIFIED for Hermes]` | no Lampway journal (captain, 2026-10-07) |
| `agent.history_sync` (R2) | `list_sessions`, then `load_session` per session | Hermes's `state.db` is the conversation record |
| parked turns (R5) | the ACP session survives a client disconnect; on reconnect the turn resumes or ends `abandoned` | Lampway stops cancelling on socket close. Built 2026-10-07: the hub marks the engine's running turn detached and names it a survivor, so `ws.py` leaves it running; its events journal on; a Blender call in flight fails and the model is told; `agent.attach` replays what was missed and rebinds the turn and the engine's tool calls to the new socket (`test_engine_conformance.py`). Not yet: `abandoned` for a turn no client re-attaches to |

*E1.8 Conformance and pin bumps.*
- An engine-conformance suite drives a real `hermes acp` from the pinned tree against the gateway's `mock` provider, which plays
  scripted model replies. It checks:
  - event order and the R1 pairing invariant;
  - cancel, steer and a question round trip;
  - a permission round trip;
  - tool calls only through the session's MCP endpoint;
  - no network outside loopback (the egress proxy log is empty of allows);
  - reload after a child is killed.
- It runs in CI on every bump. A failing check blocks the bump.
- The same suite runs against Lampway's previous engine until it is removed, so the client sees the same behaviour.

*E1.9 What Lampway removes.*
- **Loop and providers:** `turns.py`'s model loop and history handling, `providers/*` as loop drivers (they become gateway
  backends), `cli_adapters.py`, `providers/codex_app_server.py`, `prompt.py`'s prompt assembly (moved into the session's
  instructions) and `questions.py` (moved into the `ask_user` tool).
- **Kept:** `harness.py`, `swarm.py` (as tools), every `*_tools.py`, `ws.py`'s protocol, `mcp.py`, and every gate.

*E1.10 Two Hermes, never the same (captain, 2026-10-06).* Lampway's engine Hermes (Mode 1) and a user's own Hermes (BYOA) can both
run on one machine. They are deliberately different and share nothing.

| | Lampway's engine Hermes (Mode 1) | The user's own Hermes (BYOA) |
|---|---|---|
| Binary and version | The pinned release under `<install>/engines/hermes/<tag>/` | Whatever the user installed, on their PATH |
| Home | `<state_dir>/agent/hermes/<session_id>` | The user's own `~/.hermes` (or their `HERMES_HOME`) |
| Thinks through | Lampway's gateway only (R0 providers, Sign in with ChatGPT) | The user's own providers and logins, configured in their Hermes |
| Abilities | Lampway's Capabilities (E2) | The user's own Hermes settings; Lampway's Capabilities apply only to the Lampway tools it reaches over MCP |
| Conversation | Lampway's island, journal and archive (E1.7) | The user's pane; the island shows it read-only (B4) |
| Credentials | None; Lampway's gateway holds them | The user's Hermes holds them. Lampway never reads, copies or configures them (B0) |

**Invariant tests.**
- Lampway never reads or writes the user's `~/.hermes` or a user `HERMES_HOME`, checked with a source gate and a run under a
  sentinel home.
- No engine child starts with a `HERMES_HOME` outside `<state_dir>/agent/hermes/`.
- A BYOA Hermes pane's environment carries no Lampway engine path or gateway token.
- The island labels the two differently: "Lampway Agent (Hermes runtime)" and "Your Hermes".

## E2. Capabilities: one switchboard for what the agent can do

**Direction (captain, 2026-10-06).** Nothing in the harness is neutered. Every capability sits behind one interface where the user
chooses what their agent can do, the way they choose outbound routes. If they want their agent to browse the web, it browses the
web.

**Purpose.** One place, one model, one log for every ability an agent has in Lampway: the Hermes runtime's abilities, Lampway's own
tool families, and the MCP servers the user adds.

**The model** (`server/lampway_server/capabilities/`, built like `egress.py`):

```python
@dataclass(frozen=True)
class Capability:
    id: str               # "web.browse"
    label: str            # "Browse the web"
    does: str             # one plain sentence: what the agent can do with it
    risk: str             # reads | writes_project | runs_code | reaches_internet | acts_outside | spends_plan
    hermes: tuple         # Hermes toolsets / settings it turns on, e.g. ("browser",)
    lampway: tuple        # Lampway tool families it turns on, e.g. ("scene.edit",)
    routes: tuple         # egress routes it needs (law 2); enabling offers to turn them on
    approval: str         # default approval: none | ask_each_time | ask_once_per_session
    options: tuple = ()   # e.g. terminal backend: local | docker | ssh
```

- **State:** `<state_dir>/capabilities.json` (0600) holds `{id: {enabled, approval, options, scope}}`, globally and per project.
  The project overrides the global value, as Choices does.
- **Log:** every change and every refused use goes to `capabilities/log.jsonl`, the same shape as the egress log.
- **Who may change it:** only the user's click in the Client. `PUT /app/capabilities/{id}` refuses agent-origin and MCP-origin
  callers, as `PUT /agent/preference` does.
- **What agents may do:** read it and propose a change through `lampway_capabilities` (`list`, `explain`, `propose`). The proposal
  shows in the island as a card the user accepts or declines. An agent never enables its own capability.
- **Routes:** enabling a capability that needs routes shows those routes in the same card with their terms. The capability stays
  off until its routes are on, because law 2 is unchanged. Turning a route off turns its capabilities off.
- **Approval:**
  - `ask_each_time` and `ask_once_per_session` use the island's `approval` input. For Hermes these arrive through ACP
    `request_permission`, which Hermes already sends for terminal and file actions.
  - An unanswered approval times out to deny.
- **Enforcement, in three places:**
  1. the Hermes child's config and toolset (E1.3);
  2. the egress proxy allow-list (E1.5);
  3. `ToolRunner` for Lampway tool families. Each is checked against `capabilities.json` at call time, not only at start.
- **Scope:** Mode 1 (Hermes in the seat) and external MCP clients obey it fully. BYOA harnesses obey it for the Lampway tools they
  reach over MCP; their own built-in abilities are the harness's settings, and the panel says so beside each BYOA pane.

**The catalogue (first version).** Defaults are the captain's (**Q8**). The proposal mirrors routes: Lampway's scene work on;
everything that runs code, leaves the machine or acts outside Lampway off until chosen.

| id | label | from | risk | routes | proposed default |
|---|---|---|---|---|---|
| `scene.read` | See the scene as data (inspect, summaries, renders) | Lampway | reads | – | on |
| `scene.edit` | Change the scene (tools, Python in Lampway's sandbox) | Lampway | writes_project | – | on |
| `ui.control` | See and use Lampway's interface (screenshots, clicks, typing) | Lampway (today's MCP opt-in) | writes_project | – | off |
| `files.project` | Read and write files in the project folder | Hermes `file` | writes_project | – | off |
| `terminal` | Run shell commands (backend: local, docker, ssh, modal, …) | Hermes `terminal` | runs_code | per backend (ssh, modal …) | off |
| `code.execute` | Run code in a sandbox | Hermes `execute_code` | runs_code | – | off |
| `web.search` | Search the web | Hermes `web` | reaches_internet | `web_search:<provider>` | off |
| `web.browse` | Browse the web | Hermes `browser` | reaches_internet | `web:any` (every host, logged) | off |
| `vision` | Look at images | Hermes `vision` | reads | – (model-side) | on |
| `memory` | Remember things about me and this project | Hermes `memory` | reads | – | off |
| `history.search` | Search past conversations | Hermes `session_search` | reads | – | on |
| `skills.use` | Use installed skills | Hermes skills | reads | – | on |
| `skills.write` | Write and improve its own skills | Hermes `skill_manage`, curator | writes_project | – | off |
| `subagents` | Start helper agents | Hermes `delegate_task` | runs_code | – | off |
| `swarm` | Run parallel Lampway workers | Lampway swarm | runs_code | – | off |
| `schedule` | Run tasks on a schedule while the server runs | Hermes `cron` | runs_code | – | off |
| `computer.use` | Control this computer's desktop | Hermes `computer_use` | acts_outside | – | off |
| `messaging.<platform>` | Talk to me on Telegram, Discord, Slack, … | Hermes gateway | acts_outside | `msg:<platform>` | off |
| `mcp.<server>` | Use an MCP server I added | Hermes MCP client / Connections | per server | per server | off |
| `studio.plan` | Plan and price paid generations (never confirms; law 3) | Lampway studio tools | spends_plan | studio routes | on |
| `panes.drive` | Type into my agent panes on Lampway's herdr server | Lampway workbench | acts_outside | – | off |

New Hermes abilities on a pin bump join as catalogue rows, off by default. The E1.8 suite fails a bump that exposes an ability with
no row, so nothing reaches an agent unlisted.

**The interface.**
- A **Capabilities** page in "Choices and privacy", beside Routes. Each capability is grouped by risk and shows its label, its one
  sentence, its routes with their state, its approval setting and its options (e.g. the terminal backend).
- A project switch ("this project only") and a per-tab summary chip in the island ("Agent can: scene, web, terminal").
- The first-run setup gains a step after routes: "What may your agent do?" with the defaults pre-ticked.
- Turning on a `runs_code` or `acts_outside` capability shows one plain warning naming what it allows. For the terminal with the
  local backend: "commands run on this computer as you".

**Tests (RED first).**
- An agent-origin `PUT /app/capabilities/web.browse` is refused.
- A disabled capability's Hermes tool is absent from the child's tool list.
- A browse with `web.browse` on but `web:any` off is refused at the proxy and logged.
- Enabling then disabling `terminal` rebuilds the session and removes the tool.
- An `ask_each_time` capability produces an approval input; a timeout denies.
- A pin bump that adds an unknown Hermes tool fails the suite.
- A BYOA pane's MCP calls into a disabled Lampway family are refused with the capability named.

**Tests (RED first).**
- A source gate shows no Lampway server module calls a model API except the gateway.
- A config gate refuses any Hermes provider but `custom`.
- The E1.8 suite.
- A live run in a built app, with the audit's harness, of one turn per client feature: text, tool, question, permission, steer,
  cancel, rewind, and reconnect mid-turn.

**Measured 2026-10-07** (pinned `v2026.9.24`, `hermes-acp` driven by the ACP SDK `agent-client-protocol==0.9.0` from Lampway's side,
against a fake OpenAI-compatible model on loopback, with every proxy variable pointed at a refusing loopback proxy):
- **Install:** Hermes refuses wheel and sdist builds by design; `uv sync --frozen --extra acp --no-dev` on the source checkout works,
  on Python 3.13 (the project allows 3.11–3.14). The environment is 141 MB.
- **Timing:** `initialize` 1.7 s; the first `new_session` 19 s (cold: agent construction); a one-line `prompt` 0.8 s.
- **MCP over ACP:** Hermes advertises `mcp_capabilities: {http: false, sse: false}`. So Lampway passes its tools as a **stdio** MCP
  server (a small Lampway command that relays to the engine endpoint, E1.6), not as an HTTP one.
- **Default tools:** with no toolset config, the ACP session offered 23 tools, including `terminal`, `execute_code`, `browser_*`,
  `web_search`, `memory`, `delegate_task` and `skill_manage`. E1.3's config from Capabilities is therefore required before
  any real use.
- **Model calls:**
  - `GET /api/v1/models` at the origin of `base_url`, once without the token;
  - the streamed turn;
  - a second, non-streamed call with no tools (a title or summary).
  The gateway (E1.4) serves all three.
- **Egress attempts with nothing configured:** `pypi.org`, `models.dev`, `hermes-agent.nousresearch.com`,
  `raw.githubusercontent.com`. All were refused by the proxy, and the turn still completed. E1.5's deny-and-log is the control;
  E1.3 should also switch these checks off where Hermes allows it.

**Built 2026-10-07: a switch reaches the running pane** (`capabilities.subscribe`, `engine/units.py` `refresh_all`,
`engine/hermes_config.py` `read`/`env_text`, `gateway.Registry.recheck`). Measured on the pinned serve (v2026.9.24, a scripted
model on loopback, one session, its conversation counted at each step):
- rewriting `config.yaml` alone changes nothing in a live session; `reload.mcp {confirm: true}` alone changes nothing either,
  because the session's toolsets come from the `HERMES_TUI_TOOLSETS` pin, read from the process environment;
- serve loads the home's `.env` over its environment at start and again on `reload.env`; with the pin in `.env`, `reload.env`
  then `reload.mcp` gives every live session the new tool list (terminal on, off, on again), the conversation intact (14
  messages after seven turns) and the TUI still attached; `session.close` + `session.resume` also works but closes the session
  under the TUI ("type /resume"), so it is not used;
- Hermes builds the memory store with the session: `memory` switched on mid-session offers its tool, which answers "Memory is
  not available" until the session is next built (a new conversation, or serve restarted). Switched off, the tool is gone at
  once.

So Lampway re-renders each live pane's config with the keys it already holds, writes the pin to `.env` (0600, no secret), asks
its serve for both reloads, and has the gateway check that pane's next tool list against the new board (a refused re-check
refuses that request only, since one built before the reload may carry the old list). A turn about to start waits for the
refresh. A route turned on or off is a change too. The MCP endpoint's call-time check stays the hard gate for Lampway's tools.
Live-tested: `terminal` switched on through `PUT /app/capabilities/terminal` runs a command in the next turn, switched off is gone
from the next request, in the same pane and conversation (`test_engine_pane_live.py`).

**Still open** `[UNVERIFIED]`:
- per-process session isolation;
- `fork_session` targeting an earlier message;
- `load_session` replaying history as notifications;
- whether Hermes's `anthropic_messages` mode accepts a custom base URL;
- memory use per child.

---

# Mode 2 — BYOA, Bring Your Own Agent

The user's own Claude Code, Codex CLI or OpenCode runs, unmodified and on the user's own login, in a persistent herdr pane bound to a
scene tab. It drives Lampway only through Lampway's MCP server. Lampway hosts the pane and serves the tools; the harness owns the
conversation, the model, the memory and the session lifecycle. Contracts B0–B7.

## B0. The boundary (first-party only)

**Contract.** In BYOA, Lampway:
- launches the vendor's own CLI binary, found on the user's PATH, under the user's real HOME and login (`pane_env`), in the
  project root;
- never reads, copies, stores, proxies or forwards the CLI's credentials or session tokens;
- never sends a model request itself, on any plan;
- never wraps the CLI as a model endpoint behind Lampway's loop (that is what R0 retires);
- sends text into a pane only from the user's own input in the Lampway UI (typed or dictated), marked as the user's by the server,
  never by a body field (B6);
- serves tools over MCP with the same gates as every other MCP client (law 3: no spend confirm; studio tools not offered).

**Lampway's agent typing into panes (captain, 2026-10-06, Q4):** allowed only into panes on Lampway's own herdr server.
- It goes through the `panes.drive` capability (E2), which is off until the user enables it.
- It is refused for any terminal, multiplexer or process outside that server. `herdr/launcher.py` already refuses foreign sockets,
  and the check stays.
- The existing guards stay: the screen-read taint, the user-typing quiet window, and the request-word checks for interrupt and
  close.
- The origin comes from the session, never from a body field (B6).

**Tests.** A source gate: no client or server module opens the CLIs' credential files (`~/.claude/.credentials*`,
`~/.codex/auth.json`, OpenCode's auth store); the BYOA pane spawn path calls no provider; `send_input` from an agent origin into a
BYOA pane is refused unless `panes.drive` is on and the pane is on Lampway's herdr server; a send to any
other target is refused.

## B1. The harness adapter interface

**Decision (captain, 2026-10-06, Q5 and Q6).**
- Every harness ships through one adapter interface.
- **Starting adapters:** Claude Code, Codex CLI, Hermes Agent, OpenCode, Pi, Grok and Cursor.
- The old CLI providers are repurposed into this interface:
  - their binary detection, version probing and scrubbed-environment code in `agent/cli_adapters.py` moves into adapters;
  - the CLI-as-model-endpoint paths are deleted: `build_prompt`/`parse_answer`, `claude -p`, `codex exec`,
    `providers/codex_app_server.py` and `codex_image`.

**Purpose.** One interface describes how each first-party harness is detected, launched, resumed, wired to Lampway's tools and
observed. Adding a harness is one adapter and its fixture tests, never a change to herdr or the island.

**Contract.** `server/lampway_server/herdr/harnesses/` holds one module per harness, each implementing:

```python
class HarnessAdapter(Protocol):
    id: str                                   # "claude" | "codex" | "hermes" | "opencode" | "pi" | "grok" | "cursor"
    label: str                                # shown in the island's "Your agent" list
    def detect(self) -> Installed | None      # binary on PATH, version, and how to install it if missing
    def login_state(self) -> LoginState       # signed in / not / unknown, from the harness's own status command; never reads its files
    def launch(self, pane: PaneSpec) -> Argv  # a new session in the project root, bound to a scene tab (B2)
    def resume(self, native_id: str, pane: PaneSpec) -> Argv
    def lampway_tools(self, pane: PaneSpec) -> ToolWiring   # how this pane reaches Lampway: a per-pane MCP config file and flag,
                                                            # or an extension/bridge for a harness without MCP
    def observe(self, record) -> Observer | None            # how the island reads the session (B4): a session file, a store, or the screen
    def bypass_flag(self) -> list[str]        # emitted only when the user ticked bypass for this pane
```

| adapter | binary | resume | Lampway tools for this pane | island view | notes |
|---|---|---|---|---|---|
| Claude Code | `claude` | `--resume <id>` (today) | per-pane `--mcp-config` file `[UNVERIFIED flag]` | `~/.claude/projects/<cwd>/<id>.jsonl` (`observers/native.py`) | |
| Codex CLI | `codex` | `resume <id>` (today) | `-c mcp_servers.lampway…` override `[UNVERIFIED]` | rollout files (`observers/native.py`) | |
| Hermes Agent | `hermes` | `--resume` / session id `[UNVERIFIED]` | Hermes MCP config scoped to the pane `[UNVERIFIED]` | its `state.db` `[UNVERIFIED]` | the user's own Hermes, never Lampway's engine (E1.10) |
| OpenCode | `opencode` | `--session <id>` (today) | project `opencode.json` `[UNVERIFIED]` | the screen | |
| Pi | `pi` | session switch / resume `[UNVERIFIED]` | **Pi has no MCP by design**: a Pi extension that calls the Lampway launcher, shipped with Lampway `[UNVERIFIED]` | its session file `[UNVERIFIED]` | RPC and SDK modes exist |
| Grok (Grok Build) | `grok` | `--resume`, `-c` | `grok mcp add` or `config.toml`, scoped to the pane `[UNVERIFIED]` | `~/.grok/sessions/` `[UNVERIFIED]` | Apache-2.0; also speaks ACP |
| Cursor | `cursor-agent` | `--resume <chatId>` | a project `mcp.json` `[UNVERIFIED]` | the screen | |

Rows marked `[UNVERIFIED]` come from vendor documentation or search summaries, not an installed copy. Each adapter's first task
is a fixture recorded from a real installed version.

- **ACP:** Hermes, Grok and Cursor also speak ACP. A later adapter version may use ACP for the island view instead of a session
  file. The pane stays the interactive surface either way.
- **Permission bypass:** adapters never pass a bypass flag unless the user ticks it in the Lampway UI for that pane (today's
  `by=="user"` rule, `host.py:112-113`).
- **MCP entries:** written per pane, not at user scope, and pointed at the Lampway launcher with the pane's binding (B2). The
  user's own user-scope entries are left alone.
- **New harnesses:** a harness not in the table (Gemini CLI, for instance) joins by adding an adapter and its fixtures.

**Tests.**
- For each adapter: the built argv against a recorded fixture.
- The tool wiring names the launcher and the bound session.
- No adapter emits a bypass flag without the user flag.
- A harness not on PATH is listed as "not installed", with how to install it.
- A source gate shows no adapter opens a harness's credential files.
- A conformance test runs each installed harness's `detect` and `login_state` without starting a model call.

**Built 2026-10-07: every adapter checked against an installed copy** (`herdr/harnesses/`, each adapter's `FACTS`;
`tests/test_byoa_harnesses.py`). Each harness was installed into a scratch prefix and run with a throwaway HOME, no proxy and no
login, only `--help`, `--version` and offline commands; nothing was signed in and no model was called. The table above is
superseded by this one:

| adapter | checked on | new / resume | Lampway's tools in its pane | Stop | images | island view |
|---|---|---|---|---|---|---|
| Claude Code | 2.1.293 (npm) | `--session-id <uuid>` (Lampway's) / `--resume <id>` | `--mcp-config <file>` (variadic: the task goes first) | Esc | path in the prompt | its transcript |
| Codex CLI | 0.161.0 (npm) | `[PROMPT]` / `resume <id>` | `-c mcp_servers.…` overrides: `codex mcp list --json` parsed exactly the pane's entries | Esc | path in the prompt | its rollout (id recorded once found) |
| OpenCode | 1.18.35 (npm) | `--prompt` / `--session <id>` | `OPENCODE_CONFIG`: `opencode mcp list` connected the pane's entry | Esc twice | path in the prompt | the screen (its sessions are in its own database) |
| Pi | 1.0.4 (npm `@earendil-works/pi-coding-agent`) | `--session-id <id>` (Lampway's) / `--session <id>` | Lampway's Pi extension (`-e`): Pi answered `/mcp` with "lampway: connected" | Esc | path in the prompt (its `read` tool reads images) | its session file (`PiMirror`) |
| Your Hermes | v0.21.5 (Lampway's pinned build, run as a user's would be) | — / `--resume <id>` | none per pane: only `config.yaml` in its home (E1.10) | Ctrl+C | a pasted path is attached | the screen |
| Grok | 1.0.46 (x.ai installer) | `--session-id <uuid>` (Lampway's) / `--resume <id>` | none per pane: user and project config only | Ctrl+C (its docs: Esc never cancels) | a pasted path becomes an image | the screen |
| Cursor agent | 2026.10.01-e373342 (cursor.com installer) | `[prompt...]` / `--resume <chatId>` | none per pane: `.cursor/mcp.json` or `~/.cursor/mcp.json` only | Ctrl+C | refused (none documented) | the screen |

- **Pi has MCP.** The spec's "Pi has no MCP by design" was true of the old `@mariozechner/pi-coding-agent`; Pi 1.x has it built
  in, but reads only `~/.pi/agent/mcp.json` and the trust-gated `.pi/mcp.json`. Lampway's Pi extension
  (`harnesses/lampway_pi_extension.js`) is a wrapper only: it reads the pane's own 0600 config (`LAMPWAY_PI_MCP`) and calls
  `pi.registerMcpServer` for that session. `tests/test_byoa_pi_live.py` runs it on a real Pi.
- **herdr starts all seven itself.** herdr 0.9.3 knows every kind (`agent start --kind claude|codex|opencode|pi|hermes|grok|cursor`).
  Found while checking: herdr refuses an agent name that is not `[a-z][a-z0-9_-]{0,31}`, and the cockpit passed the session's
  display name, so every Claude Code, Codex and OpenCode pane failed to start on the real server; the name is now `lw-<record id>`.
  It refuses `ctrl-c` too (the spelling is `ctrl+c`), which the cockpit's interrupt sent.
- **Login checks** read each harness's own answer: Claude Code's JSON `loggedIn`, Codex's exit status, OpenCode's credential count
  (it exits 0 signed out), Cursor's JSON `isAuthenticated`; Pi, Grok and Hermes have no account-wide status command.
- `[UNVERIFIED]`, because a turn needs an account: each interrupt key on a running turn (the keys come from herdr's detection
  manifests and the harnesses' own docs and sources), how each attaches a pasted image path, a rollout written by Codex 0.161.0,
  Pi's records from a real turn, and Grok's `updates.jsonl` (an ACP stream, so Grok is still shown by its screen).

## B2. Binding a pane to a scene tab

**Purpose.** A BYOA agent works in the tab the user started it from, the way an MCP client pins one scene today.

**Contract.**
- BYOA session record (extends `sessions.json`): `{herdr_session_id, harness, native_id, scene_session_id, project_root, created,
  state, mcp_config_path}`.
- The launcher accepts `LAMPWAY_BOUND_SESSION` (set by the pane's MCP config) and starts with `bound_session` set, so every tool call
  carries the tab's `X-Mixar-Session-Id`.
- Closing the scene tab ends the binding but never kills the pane (law 5): the pane is listed as unbound and can be re-bound to a tab.
- Opening a .blend whose tab names a BYOA pane offers to re-attach it if herdr still has it (reconcile), or to resume it with
  `native_id` if not.

**Tests.** A tool call from a bound pane reaches only its tab; closing the tab leaves the pane running and unbound; reopening the
file re-attaches by `scene_session_id`.

**Built 2026-10-07: Resume or Unbind on .blend open** (`agent/byoa.py`, `herdr/host.py` `resume_bound`; client
`core/byoa_view.py`; `tests/test_byoa_island_controls.py`, `tests/test_byoa_island_view.py`):
- A bound pane that is still live is observed again (as before). One that ended is answered `view: ended`, with `resumable` when a
  native session id was recorded. Claude Code, Pi and Grok are given one by Lampway at the start; Codex's is read from its rollout
  once found. OpenCode, Cursor and the user's own Hermes choose their own and Lampway cannot see it, so they are not resumable.
- The island shows one bubble with **Resume** (only when resumable) and **Unbind** buttons. Opening the file only observes:
  nothing resumes by itself (law 5).
- `agent.byoa.resume` is the user's click from the user's own socket. It needs the BYOA switch and the harness's route, like any
  start. A new pane runs the adapter's resume with the stored id, bound to the same tab; the ended record stays in the registry,
  unbound. `agent.byoa.unbind` drops the ended pane's binding, and nothing is closed.

## B3. Lifecycle owned by the harness

**Purpose.** BYOA gives up Lampway's runtime and states plainly what it inherits.

| Concern | Mode 1 (Lampway Agent Runtime) | Mode 2 (BYOA) |
|---|---|---|
| Model and account | API key or endpoint the user configured | The harness's own login and plan |
| Conversation history, compaction, memory | R1, R3 | The harness's (e.g. Claude Code's session files and compaction) |
| Session resume | R1, R5 | `--resume` / `resume` with `native_id` (B1) |
| Instructions | Lampway's system prompt plus rules (R3) | `AGENTS.md`, `CLAUDE.md` and skills generated in the project by `agent_files` |
| Plan mode, `ask_user` choice bubbles | Lampway's | The harness's own prompts, in the pane |
| Swarm workers | Lampway's (R6) | The harness's own subagents, if any |
| Undo per turn | Client groups by turn | Client groups by MCP operation (R7) |
| Document checkpoints | Before each turn | Before each MCP operation that edits, same store and caps |
| Conversation rewind | `checkpoint.rewind` | Not available; the document checkpoint still restores the scene |
| Spend | Plan and price; user confirms in the Client | Same: studio tools not offered over MCP |
| Egress | Per provider route | The harness talks to its vendor directly; Lampway gates the launch (B5) |

## B4. Showing a BYOA session in Lampway

**Purpose.** The island stays the place the user talks to the agent, without Lampway becoming a client of the vendor's API.

**Contract.**
- Wire the existing observers (`herdr/observers/native.py`, `activity.py`): the server tails the harness's own session file for the
  bound pane and streams it to the client as the same `agent.turn.event` slots Mode 1 uses (`content.set`, `steps` for tool calls,
  `run_status`), read-only.
- Where no session file exists (OpenCode today), the island shows the pane's screen text (`pane read`) in a terminal view.
- The island's composer, in BYOA mode, sends the user's text to the pane (`send-text` plus Enter) through an endpoint that marks the
  origin from the session, not from the body (B6).
- The client's chat archive (`chat_history`) stores the observed transcript for reopening; the harness's own file stays the source
  of truth.
- The agent-working halo follows the MCP operation (R7), so the user sees when the harness is editing the scene.
- Typing into a pane the user is also typing into: the existing 2.5 s quiet window (`host.py:181-187`) applies to every send.

**Tests.** A recorded Claude session file renders as bubbles and steps in the island; a pane without a session file shows its screen;
a user message from the island appears in the pane; the halo is on exactly while an operation is held.

**Built 2026-10-07: Stop, images and Pi's view** (`agent/byoa.py`, `herdr/host.py`, `herdr/observers/mirror.py`; client
`core/byoa_view.py`, `ui/operators/session_ops.py`; `tests/test_byoa_island_controls.py`, `tests/test_byoa_island_view.py`):
- **Stop** in a Your agent tab is `agent.byoa.interrupt`; `agent.cancel` for such a tab does the same. The adapter's own interrupt
  keys are typed into the tab's live pane, from the user's own socket only. While an observed turn runs, or herdr reads a
  screen-shown pane as `working` (`pane get` `agent_status`), the island lights running through `mixie_chat_is_busy` and shows
  STOP. The tab's turn state is never touched, so an MCP operation is never blocked. Running goes out when the observed turn ends.
- **Images.** For a harness that takes an image by its path, the island's images (encoded as Mode 1 encodes them) are written into
  `<project root>/.lampway/panes/<id>/images/`:
  - 0600 files in 0700 directories;
  - the type is read from the bytes (PNG, JPEG, GIF, WebP), and the name is Lampway's;
  - every directory is checked against the project root after symlinks are resolved.

  Their paths are typed before the text. Cursor is refused before anything leaves, with its reason, and so is an agent's socket.
- **Pi** is observed from its own session file (`PiMirror`, the installed package's documented record shapes).
- **Settled with installed copies:**
  - Claude Code writes its message's `stop_reason` on every main-chain assistant record, never null (record shapes counted in a
    2.1.292 transcript). The mirror's `end_turn` rule holds.
  - Codex 0.161.0 still writes rollouts by default: its paginated thread history is a feature under development and off.

## B5. Egress, environment and consent

**Contract.**
- One egress route per harness, `byoa:claude`, `byoa:codex`, `byoa:opencode`, off until the user switches it on (law 2). Starting a
  BYOA pane is `egress.guard(route, ...)` around the launch, with a log row; the route's card says the harness talks to its vendor
  directly under the user's account and that Lampway does not see or log that traffic. Today herdr launches are classed "local" and
  pass no gate (`egress.py:85-86`).
- The pane environment is built from a scrubbed base (`connections.env_for([])`, every key removed), then `pane_env()` for the real
  login. API keys reach a pane only if the user opts in for that pane ("bill this pane to my API key"), so a plan session is never
  silently switched to API billing. herdr itself starts from the scrubbed base too (today `launcher.env_for` keeps the full
  environment).
- The first BYOA launch per harness shows a one-time notice naming the account the harness will use (from its login check, B1).

**Tests.** No `*_API_KEY` or Lampway secret in a pane's environment unless opted in; a launch with the route off refuses with the
route named; the guard writes its log row before the process starts.

## B6. Fixes the herdr surface needs first

- `POST /app/workbench/sessions/{sid}/input` decides the origin from the caller (the client's UI session versus an agent call),
  never from `body.by` (`app.py:839`).
- `AgentOps.workbench_open` applies the same `LAMPWAY_LOCAL_CLI` / BYOA enablement check as the route (`ops/registry.py:52-58` versus
  `app.py:814-818`).
- `lampway_workbench` stays off MCP (`mcp.py:40-41`), so one BYOA agent cannot drive another pane.

**Tests.** A body claiming `by:"user"` from an agent token is treated as an agent send; the agent path refuses when BYOA is not
enabled.

## B7. What BYOA depends on in the companion spec

BYOA is only as good as the MCP surface:
- **F1:** the launcher must start outside Blender.
- **F2 / R7:** scene tools must run.
- **C2:** the guide must name real tools.
- **T1 `lampway_inspect`, T2 `lampway_view`:** let a harness see the scene as data and pixels.
- **C1:** TOON replies keep a harness's context small, and Lampway's own engine gets the same envelope (E1.6).

These come before any BYOA UI work.

---

# The swarm on the Mode system (S)

**Direction (captain, 2026-10-07).** "Make the spec and contract to put the Swarm V3 on the same Mode system. Mode 1 or Mode 2", and
build it in the same work.

**Purpose.** A swarm runs in the mode of the scene tab that starts it (M0). Its workers think the way that mode thinks: Lampway's
engine in Mode 1, the user's own harness in Mode 2. The parts that make a swarm safe stay one implementation for both.

## S0. Where the swarm is today

- `agent/swarm.py` (`SwarmManager`, `SWARM_SPECS`): `swarm_start`, `swarm_status`, `swarm_cancel`, `swarm_collect`, at most 6
  workers.
- Each worker is a headless Lampway process spawned through the parent's sandbox supervisor and bound to one task with a v3
  envelope (`agent/harness.py`: `spawn_worker`, `bind_task`, `run_script` on the worker's constant routing session, `revoke`,
  `shutdown_worker`).
- The worker's scene is reset; its input objects are copied in through a staged artifact. Its result is staged, then committed
  into the user's scene with the typed `append_collection` under the client's epoch, fence and document checks. A refused commit
  fails that task only.
- The model loop inside each worker is Lampway's built-in loop (`_run_worker`), on `make_swarm_provider` (Choices `agent.worker`).
- The swarm tools are offered to the in-app agent only, gated by capability `swarm` (E2, off by default). They are not offered to
  external MCP apps (server invariant 4).

## S1. One substrate, three brains

*Superseded by A:* one brain. `PaneBrain` runs every worker in a pane. The user's saved `agent.worker_mode` selects the adapter:
`lampway_hermes` for Mode 1 (A1), the user's selected BYOA harness for Mode 2, independently of the parent (A0.5, S4, Q10).
Mode 1 separately resolves `agent.worker`; Mode 2 keeps that harness's own service/login. `builtin` and `engine` are removed
(A5). The substrate and `WorkerJob.call_tool` stand as written. The protocol and `builtin` paragraph below record the earlier
design, not additional current brains.

**Contract.** `SwarmManager` keeps the substrate and asks a **worker brain** to think:

```python
class WorkerBrain(Protocol):
    kind: str                                             # "builtin" | "engine" | "pane"
    async def run(self, job: WorkerJob) -> str            # returns the worker's summary; raises to fail the task
    async def stop(self, job: WorkerJob) -> None          # cancel: the swarm also revokes and shuts the worker down

@dataclass
class WorkerJob:
    worker: Worker            # id, name, prompt, objects, status, created, calls
    system: str               # worker_system_prompt(worker)
    tools: list               # worker_tools(): Blender and Lampway tools, never the swarm, the studios, ask_user or panes
    call_tool: Callable       # (name, arguments) -> (text, is_error): runs on THIS worker's headless Lampway (harness.run_script)
    progress: Callable        # one line to the parent's turn
```

- **Substrate (both modes):** spawn, bind, reset, seed, stage, collect, commit, revoke, shutdown, the `todo` rows and the
  Parallel Agents cards. These do not change.
- **`builtin` brain:** today's loop. It stays until the E1.8 suite removes the built-in engine.
- **`call_tool` is the only door to a worker's scene.** Every brain's tool calls go through it, so a worker can never reach the
  user's scene or another worker's scene.

## S2. Mode 1: engine workers

*Superseded by A:* a Mode 1 worker is a Hermes pane (A1) with these settings:
- home: `<unit home>/workers/<swarm>-<worker>`;
- model: the gateway, answered by the `agent.worker` choice;
- tools: the worker endpoint (S3), not an engine endpoint;
- its task: submitted as its first prompt.

It finishes with `lampway_worker_done`, exactly as a Mode 2 worker does. The abilities and limits below still apply.

**Historical build description, 2026-10-07: the worker's model is the `agent.worker` choice** (`engine/wiring.py` `provider_getter`,
`engine/gateway.py`). Its implicit follow-main service default is confirmed by A0.5 and S4; this historical receipt does not establish the
current production factory or final-head verification:
- The gateway decides from the token's session. A worker pane's gateway token is keyed by its swarm binding
  (`swarm:<swarm>:<worker>`, `Mode1Units.prepare`), a main pane's by its unit, so the gateway answers a main pane with the current
  main provider and a worker's pane with the worker choice.
- The worker's provider is built by the hub's `swarm_provider_factory` (`make_swarm_provider`: the `agent.worker` chain in
  Choices, its fallback decided at spawn, HC23) at the worker's first call, and kept for the worker's life: a worker never changes
  provider mid-task.
- With no worker choice, the chain is `follow:agent.main` (the registry's and the bridge's default): the worker follows the main
  agent. A worker choice that cannot be built (no key) is an OpenAI-style error for that pane, never the main provider instead.
- One answer for the workers, in this order: the environment (`LAMPWAY_SWARM_PROVIDER` and its swarm models, a session scope),
  then `agent.worker` in Choices, which the Providers dialog's swarm fields and the model picker's worker role both write, then
  the default `follow:agent.main`. The dialog's swarm model is therefore what the gateway answers a worker with.
- Tested with a scripted provider each, and the dialog's swarm model through the gateway (`tests/test_engine_wiring.py`).

**Current Mode 1 service boundary:** the worker's own `agent.worker` resolution is captured when it starts, separately from
`agent.worker_mode`, and its gateway uses that pinned resolution for the worker's life (`agent/swarm.py` `worker_brain`,
`herdr/swarm_brain.py`, `engine/wiring.py` `provider_getter`). Missing resolution, an incompatible provider factory or a service
that cannot be built refuses the call; it never switches to the current main provider. Selecting Mode 2 leaves this Mode 1
service choice saved and does not pass its credentials to the BYOA harness.

**Initial service decision, settled by A0.5:** without an explicit worker service selection, `agent.worker` follows the
parent choice. Parent-only preferences or environment settings must not silently create an independent worker override.
An explicit worker preference, environment override or saved `agent.worker` choice moves it off that follow. The actual
configured app factory must forward the captured resolution, including model and parameters, unchanged.

**Contract.**
- Each worker is one engine session (E1.2) with `HERMES_HOME=<state>/agent/hermes/<session_id>/workers/<worker_id>`. That keeps
  each worker's conversation in Hermes, beside its parent's (R6 under the captain's durability ruling).
- **Model:** the gateway (E1.4), answered by the `agent.worker` choice (Choices), not by the main agent's provider. The gateway
  token says which.
- **Tools:** the worker's own MCP endpoint, `/engine/mcp/<session_id>:<worker_id>`. It lists only `worker_tools()`, as
  `Capabilities` allow, and every call runs through `WorkerJob.call_tool`.
- **Abilities:** the worker's config is the parent's capability choices minus everything that would let a worker act outside its
  task: `subagents`, `swarm`, `schedule`, `messaging.*`, `panes.drive`, `computer.use`. A worker never asks the user a question
  (`ask_user` is not offered); it reports what it could not do in its summary.
- **Instructions:** `worker_system_prompt(worker)` goes in as the first prompt's preamble. ACP has no system-prompt field.
- **Summary:** the worker's last agent message is its summary. A cancelled or failed prompt fails the task (the substrate's rules).
- **Limits:** the same `MAX_WORKERS` (6). A worker's prompt is bounded by the swarm's own timeout; Hermes's own turn limits apply
  inside it.

## S3. Mode 2: pane workers

**Contract.**
- **Where:** each worker is a pane on Lampway's herdr server running the BYOA harness selected by the user's saved
  `agent.worker_mode` choice (**Q10**, A0.5), independently of the parent's mode or harness, through its adapter (B1). It is
  started under that harness's `byoa:<harness>` route (B5), using the harness's own service and login. Lampway never transfers
  its Mode 1 API keys or ChatGPT login into that harness. The older same-harness-as-parent proposal is superseded.
- **Its scene (as built, 2026-10-07):** the worker pane does not go through the client's MCP launcher. It talks straight to
  Lampway's loopback pane endpoint, `POST /api/v1/mcp/pane`. Its config has one server: header
  `X-Mixar-Session-Id: swarm:<swarm_id>:<worker_id>` and a per-worker bearer, kept by the server only as a digest and revoked when
  the worker ends. The endpoint offers that worker's `worker_tools()` and `lampway_worker_done`, every call through
  `WorkerJob.call_tool`, so the tools run on the worker's own headless Lampway.
  - **Why not through the launcher:** the client's relay forwards only a UUID scene-tab session header
    (`mcp_bridge/core/relay.py`). The launcher's tool list carries no session header. And it serves the desktop's UI and scene-tab
    tools, which could rebind a worker onto the user's scene.
  - A `swarm:` header on the external route is refused (**Q11**).
- **Its task:** the adapter's `launch(task=...)` with `worker_system_prompt` plus the task prompt.
- **Done:** the pane's harness calls the worker-only MCP tool `lampway_worker_done(summary)`. That stages the result and finishes
  the brain. A pane that exits without it fails the task.
- **Swarm tools for a BYOA parent:** `swarm_start`, `swarm_status`, `swarm_cancel` and `swarm_collect` are offered over MCP only to
  a **bound BYOA pane** whose tab is in Mode 2 (M0), with capability `swarm` on.
  - **As built:** a bound pane's config gains a `lampway_swarm` entry on the same pane endpoint, with a per-pane key. The cockpit
    keeps only the key's digest.
  - That entry reaches only the swarms its own pane started.
  - Its commits land in the pane's bound tab. External MCP apps that are not Lampway panes still
  never get them (invariant 4). No swarm tool spends.
- **Visibility:** worker panes show in the cockpit like any pane. Closing a worker pane cancels its task; it never kills a pane the
  swarm did not start (law 5).

**Built 2026-10-07: the Parallel Agents cards and Retry for every swarm** (`agent/swarm_island.py`, `SwarmManager.retry`; the
captain: nothing hidden, finish it). Before, the cards came only from a swarm started inside a built-in hub turn; a swarm started
by a bound Mode 2 pane over MCP, or by Lampway Agent's Hermes pane over its engine endpoint, emitted none.
- **Where the cards go:** every swarm reports its workers to the island of its unit's scene tab, in the client's own frames (the
  `todo` slot the Parallel Agents panel mirrors, and the "Retry failed tasks" `actions` chip):
  - a swarm started in a turn that handed it its stream: on that turn, as before;
  - a Mode 1 swarm while Lampway Agent's island turn runs (the front's live sink): on that turn's own bubble;
  - otherwise (a Mode 2 swarm; a Mode 1 swarm between island turns): on a card turn of its own, on the scene tab's current Client
    socket: `agent.turn.started` with `observed: true`, the `swarm` id and the parent `pane`; `run_status`; the rows on one bubble;
    at collect the Retry chip when a task failed, `turn_end` (no `offset`, so the pane's transcript cursor is untouched) and
    `agent.turn.ended`. A Your agent tab renders it as it renders an observed turn. `[UNVERIFIED in the client]` **For the client
    lane:** a Lampway Agent tab takes only its own turns and their wakeups, so it drops a card turn; it needs to accept a `swarm`
    card turn too (the same gap as A2's `origin: pane` turns).
- **Retry, under the same rules:** the chip sends the user's "continue" (`agent.chat` in a Lampway Agent tab, `agent.byoa.send`
  in a Your agent tab). Only from the user's own Client socket, and only while failed tasks are on offer, it is a retry:
  - the failed tasks run once more as one new swarm, in the mode, harness, folder and owner of the swarm they failed in, under
    capability `swarm`, and are collected into the scene; a second click finds nothing left to retry;
  - the unit's agent is told in one line (nothing is hidden from it): Lampway Agent's Hermes gets it with the user's "continue"
    after the retry ran inside the island turn (its steps and cards on that bubble); a Your agent pane is typed the user's
    "continue" with that line, as the user's click; `swarm_status` of the original names the new swarm (`retried_as`), which is
    the pane's own swarm too;
  - an agent's "continue" is never a retry.
- **Tested** with the fake desktop receiving the frames (`tests/test_swarm_cards.py`, `tests/test_engine_front.py`).
- **Egress:** the panes talk to their vendor under the user's account (B5). Lampway gates the start and logs it.

## S4. Choosing the brain

**Current contract (A0.5, Q10; captain clarification confirmed 2026-10-08).** There is one brain, `PaneBrain`, and the user's
worker mode is separate and its Mode 1 service follows the parent until explicitly changed:

- `agent.worker_mode` selects `local:lampway_hermes` for Mode 1 or `byoa:<harness>` for Mode 2. The shipped mode choice is
  `local:lampway_hermes`; a saved user choice persists across restart and is not overwritten by the parent's mode or harness.
- Mode 1 resolves `agent.worker`: implicitly the parent service/model until the user chooses a worker override, including
  an API service/model or Lampway Sign in with ChatGPT. That resolution
  is pinned at worker spawn and reaches the gateway unchanged; it is not reselected from the parent's live provider.
- Mode 2 runs the selected first-party harness in herdr on that harness's own service/login. It does not resolve or consume the
  Mode 1 worker service, and changing worker mode preserves that saved service. No Lampway credential transfer occurs.
- Missing readiness, a disabled BYOA route, an unsupported worker endpoint or unavailable Mode 1 runtime refuses the start
  with help. It never falls back to a different mode, parent harness or hidden worker.
- The initial mode is `local:lampway_hermes`; the initial Mode 1 service follows the parent choice implicitly. An explicit
  saved service or worker-specific setting overrides that follow; parent-only changes do not erase a saved worker choice.

**Historical design, superseded:** the tab or caller previously selected `builtin`, `engine` or `pane`, with Mode 2 workers
following the parent harness. A0/A5 removed those alternate brains; the later worker-selection clarification removes the parent
harness-inheritance rule. The initial Mode 1 service follows the parent as the captain subsequently confirmed. The caller
still supplies the owning unit and scene binding, not the worker's mode or service.

## S5. Tests (RED first)

- The substrate is unchanged: the existing `test_swarm_v3.py` passes on the `builtin` brain.
- A brain's tool call reaches only its worker's headless Lampway (the harness envelope names that worker), never the parent's scene.
- **Mode 1:**
  - with the real pinned engine and a scripted loopback model (as in E1.8), a two-worker swarm runs each worker in its own engine
    session;
  - each worker's tool call lands on its own worker connection;
  - both results are committed by `swarm_collect`;
  - the gateway answered the workers on the `agent.worker` choice.
- **Mode 2:**
  - with fake harness binaries (no vendor binary in tests), `swarm_start` from a bound pane opens one pane per task under the
    harness's route;
  - each pane's MCP config is bound to its worker;
  - `lampway_worker_done` stages and finishes the task;
  - a pane that exits without it fails the task;
  - an external MCP app is still refused the swarm tools.
- `ask_user`, `swarm_*` and `lampway_workbench` are absent from every worker's tool list in both modes.

## S6. What stays out

- A Mode 1 worker never uses Hermes's own `delegate_task`; Lampway's swarm is the one parallel mechanism (E1.6).
- A Mode 2 worker's own subagents are the harness's business; Lampway sees only its MCP calls.

---

## 4. Questions and decisions

1. **Q1 `chatgpt_plan` — decided 2026-10-06: both.** Sign in with ChatGPT in Mode 1 (R0a), and Codex CLI as a BYOA harness (B1).
   Before shipping, still to settle:
   - a reading of OpenAI's Sign in with ChatGPT terms page, which the research could not fetch;
   - the vision probe (R0a).
2. **Q2 retention — approved 2026-10-06, clarified 2026-10-08:** "Soft-hide native ended sessions after 30 days; cap visible ended history at 200; preserve resumable records."
   The visibility cap applies across recorded Lampway-owned native homes, without a second conversation store or destructive
   pruning. Native ended-tip selection is a snapshot; archiving changes visibility and preserves resumability. The older
   24-hour parked-turn value is superseded by R5 under the pane architecture.
3. **Q3 context — decided 2026-10-06:** left to the Hermes runtime's settings, editable in the Agent Panel (R3).
4. **Q4 typing into panes — decided 2026-10-06:** yes, only panes on Lampway's own herdr server, behind `panes.drive` (B0, E2).
5. **Q5 harnesses — decided 2026-10-06:** all through the adapter interface. Starting adapters: Claude Code, Codex CLI, Hermes Agent,
   OpenCode, Pi, Grok and Cursor (B1).
6. **Q6 old CLI providers — decided 2026-10-06:** repurposed into the adapter interface (detection, versions, environment). The
   CLI-as-endpoint paths are deleted (B1).
7. **Q7 the engine seat — decided 2026-10-06:** Hermes Agent's runtime in Mode 1's seat, with what does not fit switched off. E1 specifies
   it over ACP (way 2).
8. **Q8 capability defaults (E2) — approved 2026-10-06 as proposed.** They mirror routes: scene work, vision, history search, installed skills and studio
   planning on; everything that runs code, leaves the machine, writes its own skills or acts outside Lampway off until chosen. The
   earlier per-feature recommendations become defaults in this table:
   - `history.search`: on.
   - `memory`: off by default, per project once on.
   - `skills.write`: off by default, with a review step in the island when on.
9. **Q9 Hermes's own logins — decided 2026-10-06: kept separate, intentionally.** Lampway's engine and a user's own Hermes are
   different products (E1.10):
   - **Lampway's pinned Hermes:** thinks only through Lampway's providers.
   - **A user's own Hermes:** runs under BYOA with whatever the user configured in it.

10. **Q10 worker mode and service — decided; captain clarification confirmed 2026-10-08.** `agent.worker_mode` selects
    Lampway Hermes or the user's BYOA harness independently of the parent's mode/harness (A0.5, S4). Mode 1's service follows
    the parent choice implicitly until the user moves it off that choice; an explicit `agent.worker` overrides and pins the
    service/model for the worker's life. Mode 2 keeps the selected harness's own service/login without Lampway credential
    transfer. These are existing purpose IDs, not an API rename. The captain's initial-service ruling is recorded in A0.5.
    **Historical proposal, superseded:** Mode 2 workers would default to the parent's harness, or the parent could name one per
    task. That proposal is no longer open; the initial Mode 1 service decision is also settled.

11. **Q11 Mode 2 swarm binding (built, open).** The pane bearers go on a direct loopback endpoint instead of the client launcher
    (S3, "as built"). Also open:
    - the worker timeout, 1800 s as a placeholder;
    - finished worker panes stay open for the user to read (until the unit's next swarm closes them, Q13, built 2026-10-07);
    - Codex's pane bearer is visible briefly on the herdr client's command line.

12. **Q12 the architecture — decided 2026-10-07:** two modes, Mode 1 on the Hermes runtime, every agent in a herdr pane, wrappers
    only, no agent without a pane; workers keep their own headless Blender scene (A0).
13. **Q13 the herdr view — decided 2026-10-07: minimal switching.** One tab per unit; workers split beside the main agent;
    pane metadata in herdr's sidebar (A4). Closing a unit's ended worker panes when its next swarm starts: decided as
    recommended, built 2026-10-07; the captain: nothing hidden, finish it (A4).
14. **Q14 Mode 1's pane — decided 2026-10-07:** Hermes's own TUI in the pane, with the island as a second client of the same
    `hermes serve` session. Nothing is lost, and the agent persists (A1, A2). ACP is retired.
15. **Q15 `/new` in a Mode 1 pane (proposed):** the island follows the pane to its new session (A2). The other choice is to
    refuse `/new` in Lampway's pane.

## 5. Build order

*Superseded by A for what is left to build:*
1. A1, the `lampway_hermes` adapter and the TUI prebuild. Built 2026-10-07 (A1).
2. A2, the island as a `hermes serve` client, with the scripted `/api/ws` peer for tests. Built 2026-10-07 (A2).
3. A3, routing tools by unit. Built 2026-10-07 (A3).
4. A5's removals, together with S1's one brain.
5. A4, the layout.

Each lands RED first.

The list below is the original order, for the record.


1. **Shared foundation:** F1, R7 and C2 from the companion spec. Without them neither mode reaches the scene from outside a turn.
2. **Mode 1 correctness:** the R1 pairing invariant, the `ask_user` and pending-question fixes, R0's provider wiring and
   retirements, R0a's request-shape and disclosure checks for Sign in with ChatGPT, the B0 removal of the client's Codex token read.
3. **The engine seat (E1):**
   - the model gateway (E1.4) and the egress proxy (E1.5);
   - the pinned Hermes environment (E1.1–E1.3);
   - the engine MCP endpoint with `ask_user` (E1.6);
   - the ACP mapping (E1.7), with the conformance suite first (E1.8).

   R3 and R4 become mostly mapping work, because Hermes supplies compression, steering and sessions.
4. **Mode 1 durability:** none of Lampway's own: it is the Hermes runtime's (captain, 2026-10-07). R1, R2 and R5 are mapped in E1.7.
5. **Mode 1 context:** R3, then R4.
6. **BYOA:** B6 hardening and B5 egress/env, then B1 adapters and B2 binding, then B4 island view.
7. **M0** mode switch in the island, once both modes run end to end.

Each step lands with its RED tests on both halves, the regenerated `docs/tools.md` where tools change, and a live run in a built
app (the audit's harness works for this: Xvfb, the headless sign-in browser, MCP over the launcher).
