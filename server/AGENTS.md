---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# server — Lampway's backend

`lampway_server`: login for the single local account, the agent loop that drives Blender over the client's own JSON-RPC
WebSocket protocol, the tool registry, MCP for external AI apps, the job queue, studios, prompts, the ledger, the asset library,
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
   read-only server tools. Studio tools, the swarm and `ask_user` are never offered.
5. **A tool argument cannot change the script.** `agent/lampway_tools.py` `build_script` passes the arguments as one JSON string
   literal into `api.call`; unknown arguments are dropped and a missing required one is refused before Blender is asked.
6. **Isolation and controlled decoupling (herdr).** Every herdr invocation goes through `herdr/launcher.py` with HOME, XDG and
   the HERDR socket and config paths under the Lampway root, refusing otherwise; the server is launched detached and survives a
   Blender or server crash; a start reconciles sessions and paid jobs in one idempotent pass and never kills an unknown pane or
   respawns an ended one without a click.
7. **Secrets never reach a log or a file in the repository.** Keys come from the environment or 0600 files the user owns
   (the state directory, a dotenv file the launcher is pointed at); `logredact.py` redacts query secrets and token-shaped strings in every log record.
8. **Never the upstream service.** No code here calls the upstream backend; the client's stubbed endpoints are answered locally.
9. **Capabilities are the user's switches** (docs/reports/agent-modes-spec.md E2). `capabilities/` holds what an agent may do,
   globally and per project; only a user request changes it (`PUT /app/capabilities/{id}` refuses agent and cross-origin callers),
   and an agent only proposes (`lampway_capabilities`). Lampway's tool families are checked at call time by `capabilities.check_tool`
   for the in-app agent and for MCP clients; a capability that needs an egress route is in force only while that route is on.
10. **The engine has two doors, both on loopback and both Lampway's** (docs/reports/agent-modes-spec.md E1.4, E1.5). `engine/gateway.py`
    is the engine child's only model endpoint: loopback clients, a per-process bearer (`Registry.issue_token`, in memory, redacted by
    `logredact.py`), answered by the current main provider and never by another; a provider's failure is an OpenAI-style error, not a retry.
    `engine/proxy.py` is its only way out: bound to loopback, it decides before it connects (the gateway's port; a host whose route is on
    and whose capability is in force; any host only with `web:any` and `web.browse`), writes a log row for every refusal and sends an allowed
    connection through `Egress.begin`. It is the one module that opens an outbound stream outside the httpx hook
    (`tests/test_engine_proxy.py` holds that in both directions).

## Test

```bash
cd server
python3 -m venv .venv && .venv/bin/pip install -e ".[test]"   # once
.venv/bin/python -m pytest -q tests                            # the whole suite: no Blender, no network, no model
```

The suite drives the real client's frames through a fake client. A behaviour change lands with its failing test first; a paid
or egress path is tested against a fake transport, never a live provider, unless the captain named the spend.

## Owner

The lane whose contract names the change writes it; the integration lane (`lp/wave5`) lands it after the full server suite.
Doctrine (the laws above, provider and spend policy) is the captain's.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the server's invariants lived only in module docstrings | egress, approval, receipt, MCP, script-literal, herdr and secret invariants stated with their modules; the suite command | captain ruling, 2026-10-05 |
| 2026-10-07 | capabilities switchboard | captain: "I want it all behind a single interface you can choose WHAT your agent can do" (agent-modes spec E2, Q8 defaults) | nothing recorded what an agent may do; the swarm and every tool family were always on for every agent | invariant 9: the user's switches, call-time checks for the agent and MCP, proposals only from agents, routes still decide egress | captain ruling, 2026-10-06 |
| 2026-10-07 | the engine's gateway and egress proxy | captain: Hermes Agent's runtime takes Mode 1's engine seat; Hermes holds no key and only Lampway's doors lead out (agent-modes spec E0, E1.4, E1.5, Q7) | the engine child would have reached models and the network on its own: no key held by Lampway, no log row, no capability check, and `web:any` was not a route | invariant 10: the gateway (loopback, per-process token, current main provider, no retry elsewhere), the proxy (decide before connect, a row per refusal, `Egress.begin` for what it allows) and the `web:any` route | captain ruling, 2026-10-06 |
