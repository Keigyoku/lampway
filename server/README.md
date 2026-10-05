# Lampway server (v0)

Our own backend for the Lampway desktop client (the GPL fork of the Mixar
client). It replaces the closed hosted backend for exactly two jobs:

1. letting the client **log in** (and stay logged in), and
2. running the **agent loop** that drives Blender: the client has no LLM code
   of its own — the server receives `agent.chat` over a JSON-RPC WebSocket,
   calls a model, and executes Python in Blender by sending
   `blender.execute_script` back over the same socket.

Everything else the client calls is stubbed just enough to keep it quiet (see
"What is stubbed").

## Run

```bash
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[test]"

export LAMPWAY_USER_PASSWORD='choose-a-password'   # login password for the single local account
export LAMPWAY_PROVIDER=anthropic                   # mock | anthropic | openai
export ANTHROPIC_API_KEY=...                        # read by the Anthropic SDK, never logged

python -m lampway_server          # or: lampway-server
# serving on http://127.0.0.1:8787
```

Run the tests with `pytest` (they use a fake client that speaks the real
client's frames; no Blender, no network, no model).

## Configuration (environment)

| Variable | Default | Meaning |
|---|---|---|
| `LAMPWAY_HOST` / `LAMPWAY_PORT` | `127.0.0.1` / `8787` | Bind address. |
| `LAMPWAY_USER_EMAIL` / `LAMPWAY_USER_NAME` | `owner@lampway.local` / `Owner` | The one account. The email is the login username and what the client shows. |
| `LAMPWAY_USER_PASSWORD` | *(empty)* | Password for `POST /api/v1/auth/login` and the browser sign-in page. Empty means the browser page approves without asking (loopback-only convenience) and the form login is refused. |
| `LAMPWAY_JWT_SECRET` | generated | HS256 secret for access tokens. When unset, one is generated once and kept at `<state>/jwt_secret` (0600) so tokens survive restarts. |
| `LAMPWAY_ACCESS_TTL_S` | `3600` | Access-token lifetime. Keep it well above 120 s: the client refreshes whenever `exp` is nearer than that. |
| `LAMPWAY_STATE_DIR` | `$XDG_STATE_HOME/lampway-server` | Where the secret and the agent settings (`agent_settings.json`, 0600) live. |
| `LAMPWAY_FAKE_CREDITS` | `100000` | Credits shown in the profile card and the usage meter. |
| `LAMPWAY_PROVIDER` | `mock` | `mock` (no model: lists the scene and echoes it; a chat message starting `py:` runs the rest as a Blender script), `anthropic`, `openai`, `chatgpt_plan` (your ChatGPT Plus/Pro plan, see below), `codex_cli` / `claude_cli` (local CLI adapters, off unless enabled, see below). |
| `LAMPWAY_CHATGPT_MODEL` | `gpt-6.1-sol` | Model for `chatgpt_plan` (the account's own list is what `GET /v1/models` returns). |
| `LAMPWAY_ANTHROPIC_MODEL` | `claude-sonnet-5-5` | Model for the Anthropic provider. `ANTHROPIC_API_KEY` comes from the environment (or an `ant auth login` profile). |
| `OPENAI_BASE_URL` / `LAMPWAY_OPENAI_MODEL` / `OPENAI_API_KEY` | `http://127.0.0.1:11434/v1` / *(required)* / *(optional)* | OpenAI-compatible `chat/completions` endpoint (Ollama, LM Studio, llama.cpp, vLLM, OpenAI). |
| `LAMPWAY_LOG_LEVEL` | `INFO` | Python logging level. Debug logs name methods and ids, never payloads or keys. |

Refresh tokens live in memory: a server restart invalidates them and the client
re-runs its login (the access token itself stays valid until `exp`).

## Point the client at it

The client reads `backend_url` from `mixar.json`. Either build with
`MIXAR_BACKEND_URL=http://127.0.0.1:8787` (and `MIXAR_FRONTEND_URL` the same —
the sign-in page is served by this server at `/app/desktop-login`), or drop a
per-user overlay that is merged over the bundled file:

```json
{ "backend_url": "http://127.0.0.1:8787", "frontend_url": "http://127.0.0.1:8787" }
```

at `<user config>/mixar/mixar.json`. On this branch `scripts/generate_config.py:82`
still reads the stock `MIXAR_BACKEND_URL`; the fork-patches branch renames it to
`LAMPWAY_BACKEND_URL` — use whichever name your checkout's build script reads.
Plain `http://` and `ws://` are fine for the Python side; the stock C++ startup
gate refuses `http://` and is patched out in the fork (see the audit, blockers
B1/B2).

Login paths the server supports:

* **Browser SSO (the normal client path):** the client opens
  `{frontend}/app/desktop-login?port=&code_challenge=&code_challenge_method=S256&state=&source=desktop`;
  this server shows a password form (or approves immediately when no password is
  set) and redirects the browser to `http://127.0.0.1:<port>/?code=…&state=…`;
  the client posts the code to `/api/v1/auth/desktop/token` with its PKCE
  verifier.
* **Form login (Dev-build bypass):** `POST /api/v1/auth/login` with
  `username=<LAMPWAY_USER_EMAIL>&password=<LAMPWAY_USER_PASSWORD>`.

## What the agent can do (tools v0)

* `run_blender_python(script)` — the model's Python runs in the client's
  sandbox; stdout comes back as `output`, a dict assigned to `__RESULT__` comes
  back flattened, errors come back with tracebacks.
* `scene_summary()` — a fixed script listing objects (name, type, location,
  dimensions, parent, materials), materials, selection and active object.

Turns stream to the client as it renders them: a `run_status`, a loader, live
narration in the `ephemeral` slot, tool calls as `steps` rows, the final answer
in the `content` slot, `turn_end`; the journal supports `agent.attach` replay.

## What is stubbed (keeps the client quiet, does nothing)

| Endpoint | Answer |
|---|---|
| `POST /api/v1/telemetry/events` | accepted and discarded |
| `GET /api/v1/updates/check` | `update_available: false` |
| `GET /api/v1/subscriptions/status` | a generous fake plan |
| `GET /api/v1/notifications/sounds` | empty catalogue (ETag/304) |
| `PUT /api/v1/notifications/me/client-version` | `status: success` |
| `GET /api/v1/generation-catalog`, `…/chat-options` | **empty** catalogues (ETag/304) — every generation tab stays hidden in v0 |
| `GET /api/v1/agent/models` | our provider list (Anthropic, OpenAI-compatible, mock) |
| `GET/PUT/DELETE /api/v1/agent/credentials`, `/byok`, `/model-preference` | stored locally in `agent_settings.json`; the stored BYOK key is **not yet used** for model calls (keys come from the environment) |
| `GET /api/v1/referrals/dashboard` | zeros |
| WS `notifications.sync` / `job.sync` / `job.get` | empty |
| WS `agent.parked_turn`, `agent.feedback`, `agent.checkpoint.*` | benign constants |
| WS `agent.history_sync` and anything unknown | `-32601` (the client treats it as an older backend and stops) |

Not implemented at all: the job queue (3D/image/video generation), asset
search, prompt refine, turnaround detection, segmentation, handwriting,
dictation, MCP, auth handoff, history blobs/images. The client either hides
those features (empty catalogue) or logs a caught failure.


## ChatGPT plan usage (`LAMPWAY_PROVIDER=chatgpt_plan`)

Runs the agent on your own ChatGPT Plus or Pro plan through OpenAI's "Sign in with ChatGPT" plan-usage route (open-source and
local apps), implemented from the documented flow (developers.openai.com/siwc/token-sharing-open-source): OAuth authorization code
+ PKCE with a loopback redirect, the Responses API (`store:false`, `stream:true`). One-time consent: open
`http://127.0.0.1:8787/app/chatgpt`, choose **Continue with ChatGPT**, approve in the browser. Then `LAMPWAY_PROVIDER=chatgpt_plan`.

* Tokens live only in `<state>/chatgpt_auth.json` (0600) on this machine; nothing is logged; sign out revokes them.
* Requests come only from this local server, only from the agent loop answering your chat turns. There is no endpoint that lets any
  other tool use your plan, and the server is single-user and binds 127.0.0.1 (the terms forbid general-purpose access, pooling,
  hosted use for other people, and background use without express consent: Lampway has no background agent runs).
* Limits (OpenAI's): GPT Image and the other hosted tools are not available on this route; the Plus five-hour limit is shared across
  all apps; you set this app's weekly cap in ChatGPT Settings > Usage; nothing falls back to another billing path.
* It does NOT use Codex's login or `~/.codex/auth.json` (those tokens belong to Codex's own client id).
* `server/tests/test_chatgpt_live.py` runs the real checks once a consented token exists.
