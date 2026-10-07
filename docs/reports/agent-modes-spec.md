<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway agent modes: the Lampway Agent Runtime and Bring Your Own Agent

Status: **planned** (a proposal with the captain's decisions recorded), 2026-10-06, written against `lp/wave5` at `fd0f108`. Companion to [the MCP wrapper spec](mcp-wrapper-spec.md) (C0–C2, T1–T3), whose
contracts this one depends on. Nothing here is built. Findings F1–F25 come from the stress-test audit of the same day, whose report is not in this repository; each finding a
contract depends on is restated where it is used. Claims not checked on a running app are marked `[UNVERIFIED]`.

**Direction (captain, 2026-10-06).** Lampway has two agent modes.
- **Mode 1, the Lampway Agent Runtime.** Upstream Mixar's hosted-backend architecture becomes Lampway's local Agent API: Lampway's
  own agent loop, driven by an API key or a bare LLM endpoint.
- **Mode 2, BYOA (Bring Your Own Agent).** The user's own first-party agent CLIs, on the subscriptions they already pay for, run on
  Lampway's persistent herdr server. No third-party piggybacking: everything goes through the vendors' own apps. BYOA gives up the
  Lampway Agent Runtime and inherits the runtime of whichever harness the user runs.

Inputs: the audit of 2026-10-06 (findings F1–F25 of the companion report); three read-only code surveys of the session lifecycle,
the client↔backend protocol and herdr (summarised in §0); the repository's laws (`AGENTS.md`); the contract template
(`.claude/skills/lampway-tool-authoring` §1).

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
| parked turns (R5) | the ACP session survives a client disconnect; on reconnect the turn resumes or ends `abandoned` | Lampway stops cancelling on socket close |

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

## 4. Questions and decisions

1. **Q1 `chatgpt_plan` — decided 2026-10-06: both.** Sign in with ChatGPT in Mode 1 (R0a), and Codex CLI as a BYOA harness (B1).
   Before shipping, still to settle:
   - a reading of OpenAI's Sign in with ChatGPT terms page, which the research could not fetch;
   - the vision probe (R0a).
2. **Q2 retention — approved 2026-10-06:** 30 days, 200 live sessions, older ones archived; parked turns expire after 24 h.
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

## 5. Build order

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
