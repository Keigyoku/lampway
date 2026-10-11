<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Privacy and egress consent

The rule: **every outbound route is off until you switch it on, and you can always see when data is going over the wire.** There is no hosted Lampway service, no account and no telemetry by default. This page says exactly what the code does, where it stops, and what it cannot promise.

Implementation: `server/lampway_server/egress.py`. Tests: `server/tests/` (egress, receipts, compute). The Blender side is the **Privacy (what leaves this machine)** panel in the Lampway tab of the 3D viewport sidebar.

## 1. Routes

A route is one place data can go. The server knows these routes and their hosts; each carries a retention and a training statement and a privacy class:

| Route | What it is | Hosts | Privacy class |
|---|---|---|---|
| `openrouter` | OpenRouter chat, images, video, embeddings | openrouter.ai | conditional: needs `zdr: true` and `data_collection: deny` for private content |
| `chatgpt_plan` | your ChatGPT plan | chatgpt.com, auth.openai.com, api.openai.com | unknown |
| `claude_plan` | the Anthropic API-key provider (the label says "plan") | api.anthropic.com, claude.ai | unknown |
| `custom_llm` | an OpenAI-compatible endpoint that is not on loopback | the host in `OPENAI_BASE_URL` | unknown |
| `mcp_probe` | the MCP connection check (initialize and tools/list only, no credential, none of your content) | the server you configured | ok |
| `studio:tripo`, `studio:meshy`, `studio:hi3d`, `studio:hyper3d` | the 3D studios | their own hosts | unknown |
| `higgsfield`, `heygen`, `fal` | generation services | their own hosts | unknown |
| `model_download` | a plain GET of public model weights (Hugging Face) | huggingface.co and its CDNs | ok: no content is sent, the host sees your IP address and the file you asked for |
| `compute:boat` | Boat cloud CPU boxes | boat.dev | conditional: snapshots off and no environment passed |
| `compute:modal`, `compute:runpod` | serverless GPU endpoints | their own hosts | unknown |
| `web:any` | the agent's own browser, for the engine's `web.browse` capability: any host, each one logged (built and tested as the engine's egress proxy; no engine starts it yet) | any website | unknown |
| `byoa:claude`, `byoa:codex`, `byoa:hermes`, `byoa:opencode`, `byoa:pi`, `byoa:grok`, `byoa:cursor` | starting your own agent CLI in a pane of Lampway's herdr server (Bring Your Own Agent): the harness talks to its vendor directly under your account, and Lampway does not see or log that traffic; the route gates the start and logs it | none from Lampway (the harness reaches its own vendor) | unknown |

"Unknown" is stated honestly: the providers' terms (retention, training) have not been read or recorded for these routes, so Lampway does not claim a policy it has not verified. The panel shows each route's retention and training line as the code has it.

## 2. How a route is enforced

- **One choke point.** `egress.install()` wraps `httpx.Client.send` and `httpx.AsyncClient.send` once. Every in-process provider (the Anthropic SDK included) uses httpx, so every call passes the same gate. A call that starts another process (a studio browser driver, a local CLI, a URL downloader, a cloud box CLI) cannot be seen at the transport, so it calls `guard(route, ...)` at the place it launches.
- **Off by default.** In production the server creates a strict `Egress` over its state directory, with every route off. A call to a route that is off, or to a host that maps to no route, raises `EgressRefused` and **nothing is sent**: `openrouter is off: switch it on in Privacy to let data leave`.
- **Loopback is exempt.** `127.0.0.1`, `localhost` and `::1` are never gated, so the mock provider and a local Ollama need no opt-in.
- **Your click, not a script's.** Switching a route on or off is a button in the panel. The Client refuses it while any script is running (the agent's, a swarm worker's, the live bridge's), so no script can opt you in.
- **Before a receipt.** A paid job whose route is off is refused before its write-ahead receipt is created, so it never reads as "submission unknown" ([spend](spend.md)).

Preferences live in `<state>/egress.json` (mode 0600).

## 3. The wire indicator

The panel's first line is a badge: `nothing is leaving this machine`, or `DATA LEAVING: <route, route>` while a call is in flight. It is driven by `Egress.indicator()` (`over_the_wire`, the active routes, the last route and time), which counts calls in flight per route. The panel reads that state from the server on a 1.5 second timer and on the **Refresh** button, so the badge comes from a refreshed cache, not a live push: a very short call can start and finish between two polls. The egress **log** is the authoritative record. (The facelift lane is restyling the badge with a dedicated "wire" colour; the information stays the same.)

## 4. The egress log

`<state>/egress/log.jsonl` (0600), append-only, one JSON row per decision, written **before the bytes leave**. A row holds the event (`send`, `refused` or `override`), the route, the host, the method, the kind (`image`, `video`, `mesh`, `text`, `file`, `request`), the byte count, any asset ids, the content class, the retention and training statements and whether an override applied. It never holds content, a query string or a header. The panel shows the last 20 rows; **Export** downloads the file.

Server routes (all need your bearer token): `GET /app/egress` (routes, indicator, overrides), `POST /app/egress/route` `{route, enabled}`, `POST` and `DELETE /app/egress/override`, `GET /app/egress/log?limit=`, `GET /app/egress/export`.

## 5. Opting a route in

- **In Blender:** Lampway tab, Privacy panel, **Switch on** beside the route.
- **From a shell** (no Blender), using the compute CLI, which shares the same `egress.json` when you point it at the server's state directory:

  ```bash
  LAMPWAY_STATE_DIR=~/.local/share/lampway/server-state \
    python -m lampway_server.compute egress openrouter on
  ```

  (run with the server package on `PYTHONPATH`, for example from `server/`). Without `LAMPWAY_STATE_DIR` the CLI uses its own default directory and will not change the server's routes. `compute egress` with no arguments lists the compute routes and fal.

## 6. Private assets

Content can carry a class: `public`, `synthetic` or `private`. Anything unclassified is not treated as private by the transport, so callers that handle your own designs (the compute wrapper and the embedding service; the closed-choice decision judge in `decisions_model.py` follows the same routing law but nothing calls it in production yet) classify what they send:

- A **private** request passes only a route whose class is `ok`, or `conditional` with every required constraint declared on the call (OpenRouter: `zdr: true` and `data_collection: deny`; Boat: `snapshots: false` and `noEnv: true`). Everything else is refused with the reason and what the route requires.
- A **per-asset override** (`POST /app/egress/override`) lets one asset through one route. It is scoped to that asset and that route, is logged as its own row when set and when cleared, and applies only when every asset id on the call has one.
- **Compute inputs** are private unless you tag them: `--input path:public`, `path:synthetic` or `path:private`; no tag means private. A backend you have not marked as allowed for private inputs refuses them.
- **Embeddings and judges.** Private content may go only to a model on OpenRouter's live ZDR endpoint list, with `provider: {"zdr": true, "data_collection": "deny"}`, never to a `:free` endpoint; the eligible list is computed live and never hard-coded. With none eligible the call is refused and nothing is sent. Free embedding models are treated as non-private. The default for the Asset Vault is deterministic, local descriptors with nothing uploaded ([asset vault](asset-vault.md)).

## 7. What this does not cover

- The gate lives in the **server** process and the compute CLI. The Blender client has its own network surface: telemetry is off by default and only ever goes to the configured backend, the sandbox's default allowed hosts are your local server only, and the brand and host gates in `tests/lampway` pin the hosts the client may name. The pre-publish gate is a separate thing (it keeps personal data out of the repository, see [`CONTRIBUTING.md`](../CONTRIBUTING.md)).
- Local CLI adapters and the cockpit start your own `codex`, `claude` or `opencode` binaries; those binaries use their own networking. Lampway starts them only on your click (cockpit) or with the local-CLI switch on, and never reads their credential files.
- Studio browser drivers drive a browser you signed in to; the page itself talks to the studio. The route gates and logs the launch, not each request the page makes.
- A provider's behaviour once it has your data (retention, training) is the provider's. Where the table says "unknown", Lampway does not know either.
- Keys never go into the egress log, the saved provider settings, a receipt export or a log line; secrets in log records are redacted (`logredact.py`).

## 8. Telemetry and accounts

There are no accounts and no billing. The client's telemetry is off by default and sends only to the configured backend. The server answers the client's account, subscription and telemetry endpoints with local stubs ("quiet-keeping"), which is why the profile card shows a local identity and a large fake credit number.
