<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Lampway server

Lampway's own backend for the desktop client (the GPL fork of the Mixar client). The upstream backend is closed and hosted, so this one is new: **single-user, loopback by default**, no accounts, no billing. It does the jobs a hosted backend would, on accounts and machines you own:

1. **Login** for the client (PKCE desktop SSO against a loopback page, refresh tokens that survive restarts).
2. The **agent loop**: the client has no model code. The server receives `agent.chat` over a JSON-RPC WebSocket, calls a model, and runs Python in Blender by sending `blender.execute_script` back over the same socket. It also runs **parallel workers** (headless Blender processes) and the typed, fenced commit that lands their results.
3. The **job queue** and generation catalogue for images and video, the **studio** plan/confirm flow, prompts, the experiment ledger, job receipts, the egress gate, the compute wrapper and the cockpit routes.

Documentation for users is in [`docs/`](../docs/README.md); this page is for running and testing the server.

## Run

```bash
cd server
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements-lock.txt      # the pinned set the suite was verified with
pip install -e .

export LAMPWAY_USER_PASSWORD='choose-a-password'   # optional: the sign-in page asks for it
export LAMPWAY_PROVIDER=mock                        # mock | anthropic | openai | openrouter | chatgpt_plan
python -m lampway_server                            # or: lampway-server
# serving on http://127.0.0.1:8787
```

Normally you do not run it by hand: `scripts/lampway/lampway` starts it, points the app at it and stops it again ([getting started](../docs/getting-started.md)).

Python 3.12 or newer is what the lock was verified with (`pyproject.toml` allows 3.11). The Asset Vault library needs Python 3.14 and numpy today ([asset vault](../docs/asset-vault.md)).

## Configuration (environment)

The full list lives in `lampway_server/config.py`; the ones you will touch:

| Variable | Default | Meaning |
|---|---|---|
| `LAMPWAY_HOST` / `LAMPWAY_PORT` | `127.0.0.1` / `8787` | bind address; a Host guard answers 421 to any other Host |
| `LAMPWAY_STATE_DIR` | `$XDG_STATE_HOME/lampway-server` | the JWT secret, saved provider prefs, egress prefs and log, spend log, the Connections record (no key) (files 0600) |
| `LAMPWAY_SECRETS_DIR` | `$XDG_STATE_HOME/lampway-secrets` | Connections' file store (0600 files, 0700 directory), used only when no OS keyring works; outside the Lampway home, which the agent's script sandbox reaches |
| `LAMPWAY_PROJECT_ROOT` | `~/.local/share/lampway/projects` | the root every tool path is jailed to; receipts, ledger, video and uploads live under it |
| `LAMPWAY_USER_EMAIL` / `LAMPWAY_USER_NAME` / `LAMPWAY_USER_PASSWORD` | `owner@lampway.local` / `Owner` / empty | the one account; empty password means the browser sign-in page approves without asking and the form login is refused |
| `LAMPWAY_JWT_SECRET` | generated once, kept at `<state>/jwt_secret` (0600) | HS256 secret for access tokens |
| `LAMPWAY_PROVIDER` | `mock` | the main provider; see [providers](../docs/providers.md) |
| `LAMPWAY_ANTHROPIC_MODEL`, `OPENAI_BASE_URL`, `LAMPWAY_OPENAI_MODEL`, `OPENAI_API_KEY`, `LAMPWAY_CHATGPT_MODEL` | see `config.py` | per-provider models and endpoints |
| `OPENROUTER_API_KEY` or `LAMPWAY_OPENROUTER_KEY_FILE`, `LAMPWAY_OPENROUTER_BUDGET_USD` | none / `3.0` | the OpenRouter key and the session ceiling |
| `LAMPWAY_LOCAL_CLI` | off | `1` lets the cockpit start your own agent CLIs (Claude Code, Codex, OpenCode) in its panes |
| `LAMPWAY_LOG_LEVEL` | `INFO` | debug logs name methods and ids, never payloads or keys |

Every outbound route is **off** until it is switched on in the Privacy panel ([privacy](../docs/privacy.md)), so a real provider is refused until you do.

## Connections (`lampway_server/connections/`)

The one place that knows every credential: `GET /app/connections` lists every service of `specs/connections/CATALOGUE.md`
with its state (`connected`, `signed_out`, `expired`, `missing`, `error`, `not_checked`), where its credential comes from and
whether its route is on. Every route needs the bearer and no route returns a secret. A key is pasted once
(`PUT /app/connections/{id}/secret`) into the OS keyring (service `lampway`), else into `LAMPWAY_SECRETS_DIR`; or it is
read where it already is (an environment variable, which wins over a saved key, or an owner-only key file). A Test runs
only the service's free check and only with its route on; the server re-checks every 30 minutes the connections whose route
is on and that were used in the last day. Consumers call `connections.require(id)`; a child process gets
`connections.env_for([...])` (the server's environment with every key removed, plus that one connection). The agent reads
status only, through `lampway_connections`. Hyper3D's MCP signs in from Connections (`mcp:hyper3d`); its tokens live in
the store.

## Choices (`lampway_server/choices/`)

What Lampway uses for each purpose (56 of them: the main agent, plates, retopology, dictation, ...), what that falls back to, and why a
job ran the way it did. `GET /app/choices` lists them; a choice is set per purpose (`PUT /app/choices/{purpose}`: a preferred option,
fallbacks, params) globally or for one project. Precedence: the `LAMPWAY_*` environment for the session, then the project, then your
choice, then the Providers dialog's saved values, then the shipped default. Every option is checked, in order, for: it exists, it can do
the job, private content may go there, its connection works, its route is on, its cost fits, and its local engine is ready; the first
failure is shown with its fix. A job receipt carries the `choice` (option, reason, why). The agent reads and proposes through
`lampway_choices`; only your click changes a choice. Private content to an option whose terms are unread is recorded
(`would_refuse_private`), not yet refused (decision CH1, first release).

## What is served

| Area | Endpoints |
|---|---|
| auth | `POST /api/v1/auth/login`, `/auth/desktop/token`, `/auth/refresh`, `GET /auth/me`, the sign-in page `/app/desktop-login` |
| agent | WebSocket `/api/agent/ws/{instance_id}`: handshake, chat, input, cancel, status, attach (journal replay), the v3 swarm harness, `blender.execute_script` |
| generation | `/api/v1/job-queue/jobs`, `/api/v1/generation-catalog`, `/api/v1/uploads/{kind}`, `/api/v1/jobs/files/...` |
| local routes | `/app/provider-settings`, `/app/studio/*`, `/app/prompts*`, `/app/ledger*`, `/app/egress*`, `/app/workbench*`, `/app/mcp/*`, `/app/swarm*`, the sign-in pages `/app/chatgpt` and `/app/higgsfield` |
| other | `/api/v1/mcp` (MCP over JSON-RPC), `/api/v1/asset-search/*`, `/api/v1/matgen`, WebSocket `/api/v1/dictation/ws` |
| compute | not a route: the CLI `python -m lampway_server.compute` ([compute](../docs/compute.md)) |

## What is stubbed (keeps the client quiet)

Account, billing and growth endpoints answer with local constants: telemetry events are accepted and discarded, the update check says "no update", the subscription is a generous fake, referrals are zeros, notifications are empty, and `agent.history_sync` (and anything unknown) answers `-32601`, which the client reads as an older backend. The profile card shows a local identity and a large fake credit number. Tool and generation features that the server does not back are hidden by an empty catalogue rather than offered and failed.

## Tests

```bash
pytest                        # no Blender, no network, no model; uses a fake client that speaks the real client's frames
```

The suite covers auth, the WebSocket system layer, the agent turn contract, providers on fake transports, the swarm harness, studios, video, prompts, ledger, receipts, egress, compute, cockpit and the Asset Vault library. Keep `TMPDIR` and `--basetemp` on a filesystem with space for a full run.
