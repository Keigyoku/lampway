# Lampway server v0 — implementation report

Worktree `<workspace>/wt-server`, branch `lp/server`, code under `server/`.
Pushed to `origin lp/server` (github.com/Keigyoku/lampway) as a new branch.

## Commits (author Keigyoku, no trailers)

| sha | slice |
|---|---|
| `e5e26a67` | single-user form login, HS256 access tokens, `/auth/me` top-level profile; the fake client |
| `66f446b6` | PKCE desktop SSO page + exchange, idempotent refresh rotation |
| `0fc66a91` | the `{status,message,data}` envelope, ETag/304, quiet-keeping stubs, local agent settings store |
| `200450ba` | agent WebSocket system layer (4001 close, handshake, ping, reauth, sync stubs, -32601) |
| `419a88c4` | the agent loop: chat turns, slot event stream, execute_script round trips, three providers |
| `0265343e` | `python -m lampway_server` entrypoint, README, config tests, real-socket run |

## Environment — a deviation to read first

The dispatch named distrobox `lampway-dev` for the venv and tests. The box was found broken: its
first-run entrypoint fails with `E: dpkg was interrupted` → `Exited (100)` (two concurrent first
entries — it is shared with the fork-patches implementer). I tried a repair (`dpkg --configure -a`
inside the stopped container through `podman unshare` + a nested user namespace reproducing the
container's idmap, see `scratchpad/box-dpkg-repair.sh`); each attempt met `dpkg frontend lock was
locked by another process with pid …` — a live pid, i.e. the other agent entering the box at the same
moment. I stopped touching the box rather than race another agent on a shared resource.

**All tests and the live run therefore ran on the host**, in a venv OUTSIDE the worktree
(`<scratchpad>/hostvenv`, Python 3.14.7, anthropic 1.11.0, starlette 1.7.0, uvicorn 0.54.0, httpx
0.28.1 + httpx2 2.13.1, pytest 9.1.1, websockets 17.2). `server/.venv` was NOT created (it would have
been a 3.14 venv unusable from the 3.12 box). The code targets `>=3.11` and uses nothing 3.14-specific,
but **it has not been executed on 3.12 in the box** — the first thing to do when the box is back is
`distrobox enter lampway-dev -- bash -lc 'cd server && python3 -m venv .venv && .venv/bin/pip install -e .[test] && .venv/bin/pytest'`.
The box is still in its broken state as of this report (`podman ps -a`: `Exited (100)`); `dpkg --audit`
inside it lists `libncursesw6` unpacked-not-configured and `libc-bin` triggers pending.

## Endpoints implemented vs protocol.json

Legend: **done** = implemented and tested against the shape the client reads; **stub** = answers the
documented shape with inert content; **—** = not implemented (client either hides the feature or
catches the failure); **n/a** = no production caller per the audit.

| protocol.json id | method/path | status | notes |
|---|---|---|---|
| auth.desktop_token | POST /api/v1/auth/desktop/token | done | S256 verifier check, single-use 5-min code, 400 `{detail}` on failure |
| (SSO page) | GET/POST /app/desktop-login | done | password form (or immediate approve when no password), 302 to `http://127.0.0.1:<port>/?code&state` echoing state; 400 without challenge |
| auth.login | POST /api/v1/auth/login (form) | done | 200 `{access_token, refresh_token}`; 401 `{detail}` |
| auth.refresh | POST /api/v1/auth/refresh | done | rotation; same Idempotency-Key + same refresh token replays the same pair; 401 otherwise |
| auth.me | GET /api/v1/auth/me | done | top-level `{email, name, credits}`; 401 without/forged bearer |
| auth.handoff_create | POST /api/v1/auth/handoff/create | — | billing/upgrade handoff; failure is user-visible but not blocking |
| notifications.client_version | PUT …/notifications/me/client-version | stub | `status: success` |
| notifications.sounds | GET …/notifications/sounds | stub | `data.sounds: []` + ETag, 304 |
| updates.check | GET …/updates/check | stub | `update_available: false` |
| telemetry.events | POST …/telemetry/events | stub | accepted, discarded |
| subscriptions.status | GET …/subscriptions/status | stub | all meter fields, generous `credits_per_month` |
| generation_catalog | GET …/generation-catalog | stub | **empty** capabilities (kill switch), ETag/304 |
| generation_catalog.chat_options | GET …/generation-catalog/chat-options | stub | empty options, ETag/304 |
| job_queue.* (enqueue/stage/get/cancel/info) | /api/v1/job-queue/… | — | next step (owner's Tripo/Meshy/Hi3D drivers) |
| agent.models | GET …/agent/models | done | our list: anthropic (sonnet-5-5, opus-5-5, haiku-4-5), openai-compat (configured model), mock; ETag/304 |
| agent.credentials_get / byok_put / credentials_delete_all | …/agent/credentials, /byok, /credentials/all | done | stored in `<state>/agent_settings.json` (0600); key never echoed past `key_preview`; **stored key not yet used for model calls** |
| agent.model_preference_get/put/delete | …/agent/model-preference[/{role}] | done | 400 `Model not available: …` for unknown models; DELETE role 404 when unset; DELETE all |
| agent.history_blob, agent.images | GET …/agent/history/blob, /agent/images/… | — | no history archive in v0 |
| prompt_refine, handwriting, model_3d.detect_views, scene_segment.*, scene_gen.*, asset_search.*, referrals.invite_emails, mcp.*, dictation.ws | | — | referrals.dashboard is a zeros stub; the rest are hidden/caught per the audit |

WebSocket `/api/agent/ws/{instance_id}`:

| method | status | notes |
|---|---|---|
| upgrade auth | done | bad/missing bearer → accept then close **4001** (verified over real TCP too) |
| system.handshake | done | `{success:true, agent_ws_v1:true, server_capabilities:[agent_history_v1, agent_history_v2]}` |
| system.ping / system.reauth / system.set_context | done | ping answers `{}` with the same id; reauth `{authenticated: bool}` |
| notifications.sync / mark_read / get_unread; notifications.push | stub | empty lists; push never sent |
| job.sync / job.get / job.update | stub | `{jobs: []}`, `{job: null}`; update never sent |
| agent.chat | done | receipt `{state: pending}`; -32602 without session_id/message |
| agent.input | done | answer text becomes the next user message of the session |
| agent.cancel | done | cancels the running turn → `turn_end status: cancelled` |
| agent.status | done | `{turns: {sid: {turn_id, run_id, replay_available, status, active, last_seq}}}` |
| agent.attach | done | replays `agent.turn.event` with seq > after_seq from the journal, re-sends `agent.turn.ended`; unknown → `{status: unavailable}` |
| agent.request_status | done | `{state, result}` |
| agent.parked_turn / feedback / checkpoint.mark / checkpoint.rewind | stub | benign constants |
| agent.history_sync, generation.agent_result (notification), anything else | — | -32601 / ignored (the client treats -32601 as an older backend and stops syncing) |
| agent.turn.started / turn.event / turn.ended / command.result | done | started carries turn_id == command_id and precedes command.result; seq 0..N contiguous; first `run_status in_progress`, last `turn_end` |
| blender.execute_script (server→client) | done | `{script, tool_name, session_id, agent_ctx:{chat_session_id, turn_id, call_id}}`, correlated by id, 600 s timeout, errors fed to the model |
| blender.liveness, agent.sandbox_control, llm.request, addon_project.*, agent.execution.*, context_folder.*, mcp.*_operation, agent.history_read | — | never sent |

Agent loop: `AgentHub` (server/lampway_server/agent/turns.py) — provider interface `stream(ModelRequest) → Text | ToolCall`
(providers/base.py); `MockProvider`/`ScriptedProvider` (tests, no model), `AnthropicProvider` (official SDK,
`messages.stream`, model from `LAMPWAY_ANTHROPIC_MODEL` default `claude-sonnet-5-5`, no forced tool_choice,
thinking blocks echoed back through a per-tool-call cache), `OpenAICompatProvider` (chat/completions SSE over httpx).
Tools: `run_blender_python`, `scene_summary` (fixed script; `__RESULT__` dict). Keys: never read by our code
except `OPENAI_API_KEY` → Authorization header; Anthropic's is read by the SDK; nothing logs payloads or keys
(debug logs carry method names and ids only).

## Tests and results

`server/tests` — 60 tests, all pass on the host venv (`pytest`, 1.3 s). Final run: `60 passed in 1.31s`.

| file | what | red-first? |
|---|---|---|
| test_auth.py (4) | form login, JWT exp, /auth/me top-level, 401s | RED observed (ModuleNotFoundError), then GREEN |
| test_sso_refresh.py (7) | PKCE page/redirect/state, wrong password, no challenge, wrong verifier + reused code, refresh rotation, idempotent replay, unknown token | RED (7 × 404), then GREEN |
| test_stubs.py (22) | bearer-required table, every stub's exact reader shape, ETag/304, BYOK round trip (key not echoed, file 0600 contents), preference round trip + `Model not available:` | RED (22), then GREEN |
| test_ws.py (8) | handshake shape, 4001 on bad/missing bearer, ping, reauth, -32601, sync stubs, id-less notification ignored | RED (8), then GREEN |
| test_agent_turn.py (7) | the full ordering contract (see table above), failed script reported `is_error`, scene_summary script, provider request contents, attach replay + status + request_status, history across turns | RED at import, then GREEN; **attach replay test found a real bug** (journal shared mutable step dicts → replay differed from original) fixed by deep-copying at emit |
| test_agent_control.py (3) | cancel mid-script, input as user message, -32602 | written alongside the chat implementation; never RED for their own reason → **mutation-verified**: three mutants (status `completed`, text `MUTANT`, check removed) each killed by its own test |
| test_providers.py (4) | Anthropic wire translation + SSE stream (httpx2.MockTransport), OpenAI-compatible translation + SSE (httpx.MockTransport), no-key → no Authorization, make_provider | RED at import, then GREEN |
| test_config.py (4) | env mapping, defaults, secret persistence 0600, configured secret wins | written after the code → mutation-verified (default port 8788 killed it) |
| test_live_socket.py (1) | uvicorn on a loopback port; `websockets` client with Bearer on the upgrade; login → handshake → chat → execute_script → turn.ended; 4001 refusal | written after → mutation-verified (close code 4000 killed it) |

Two test-side defects I made and fixed (both collector errors, not spec changes): the attach test counted the
re-sent `agent.turn.ended` as an event (now asserted explicitly), and the cancel test waited for a reply whose
id equalled the *command* uuid instead of the JSON-RPC *request* id (fake now records `last_request_id`).
Diagnosing the second one added permanent debug logging of dispatched methods and a `_guarded` wrapper so a
handler that raises answers `-32603` instead of leaving the client waiting.

Live run of the real entrypoint (`scratchpad/live-run.sh`, `python -m lampway_server`, port 18787, mock
provider): login 200 → `/auth/me` `{"email":"owner@lampway.local","name":"Owner","credits":100000}`; 401 without
token; enveloped empty catalogue; `/app/desktop-login` 200 with a form; wrong password 401; right password
`302 http://127.0.0.1:51731/?code=…&state=xyz`; stopped by exact PID (exit 143). Server log carries no token/key.

## What needs a real client to verify

1. The whole thing against the real forked Blender client: the slot rendering (`ephemeral` streaming then
   `content.set`, `steps` rows via `steps_format.normalize_step_item`, loader on/off), the C++ profile card
   reading `/auth/me`, the keyring storage of our pair, and the SSO browser hop (I only followed the redirect
   by hand).
2. `blender.execute_script` against the real sandbox: `connection_manager.on_script_execute` requires an active
   session — I send `session_id`/`agent_ctx.chat_session_id` = chat session and only after `turn.started`, per
   the code, but the scene routing (`main_thread_routing`) was not read.
3. Reconnect behaviour: `agent.attach`/`agent.status` were tested with a fake; the client's gap/overflow paths
   and `turn_cursor` persistence were not driven.
4. **The Anthropic and OpenAI-compatible providers were never run against a live model** (no real LLM calls
   in tests, by rule). In particular: SDK 1.x `messages.stream` event shapes were taken from the skill docs and
   a hand-built SSE fixture; the thinking-block echo on tool-result continuation is implemented but unverified
   against the API; `max_tokens=32000` and no `thinking` parameter (adaptive by default on Sonnet 5.5).
5. Python 3.12 in the box (see Environment).

## Known gaps / concerns (honest list)

- Refresh tokens and PKCE codes are in memory: a restart invalidates refresh → the client re-logs in (access
  tokens survive via the persisted secret). Sessions/turn journals are in memory too.
- Chat image attachments (`payload.content` image_url parts) are ignored; only `message` text is used.
- `agent.input` with `answers`/`interrupt_id` is treated as plain text; the server never asks questions in v0,
  so the client's AWAITING_INPUT path is untouched.
- The stored BYOK key is not used for calls (keys come from the environment) — flagged in README.
- `agent.cancel` replies `{state: complete, result: {ok}}`; the client's handling of that reply
  (session_ops.py) was not read.
- `generation.agent_result` requests (not notifications) would get -32601; the client retries them 20× over
  an hour — harmless noise, only reachable once job-queue work exists.
- The nested-userns box repair script left the container untouched in the end (every run hit the live lock);
  no state outside my worktree, the scratchpad, and `~/.claude/agent-memory` was written.

## Next steps

1. Run the suite inside `lampway-dev` (Python 3.12) and create `server/.venv` there.
2. Drive the real client once (login → handshake → "add a cube") with `LAMPWAY_PROVIDER=mock`, then with
   `anthropic`; fix whatever the slot renderer disagrees with.
3. Job queue: `POST /api/v1/job-queue/jobs` → the owner's Tripo/Meshy/Hi3D drivers; publish a real
   `generation-catalog` (capabilities → services → models → params) so the client shows the tabs; push
   `job.update`/answer `job.sync`/`job.get`; serve result files from a local asset host and add it to
   `MIXAR_ASSET_HOSTS`.
4. Subscription-based providers: DROPPED the `~/.codex/auth.json` idea (2026-10-05, by the captain's ruling after the terms audit):
   Codex's tokens belong to Codex's own client id and the Sign in with ChatGPT terms require OpenAI's supported flow. The `chatgpt_plan`
   provider (lp/tools) implements that flow from the documented protocol; Claude subscriptions are not usable by third-party apps
   (Anthropic's terms) and stay API-key only. Use the stored BYOK provider/model/key to pick the provider per account.
5. Persist refresh tokens and sessions to the state dir; add `agent.history_sync` (v1) so transcripts survive.
6. Images in chat (vision) and `request_user_input`-style questions (`input_type`/`actions` slots).
