---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-tool-authoring
description: "Add or change a Lampway agent tool: the contract first, the client api function and its refusal shape, the server Def and the registry, MCP exposure, paid-job receipts, egress routes, the spend gate, the generated tool docs, and the RED-first tests on both sides."
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# Adding a Lampway tool

Load `lampway-coding-guidelines` first. A Lampway tool is proven code first; a model or a studio slots in behind the same
interface later. It is written test-first on both sides of the wire.

## 1. The contract before the code

Every tool starts from a contract with these sections: name and one-line purpose (agent name `lampway_<name>`, api name `<name>`);
source (the decisive line quoted); user story; inputs (a JSON schema with bounds and the refusal for each out-of-range value);
outputs (schema, artefacts, what lands in the scene); engine (the proven algorithm, its licence, the existing tool it extends);
model slot (provider, measured or cited cost, spend-gate behaviour); preconditions and refusals (each refusal names the next step);
side effects (files touched, hosts, undo); tests, RED first, each with its falsifier; acceptance evidence; dependencies; open
questions that only the captain can answer. Mark every unverified claim `[UNVERIFIED]`. When the work is a 3D algorithm, the
canon page is part of the contract: load `lampway-canon` and build to it.

## 2. The client half (runs in Blender)

- Write the function in `src/scripts/mixar/modules/lampway_tools/api.py` (or a module it imports) and decorate it with `@tool`.
  The decorator registers it in `TOOL_FUNCS`, the only door `api.call(name, payload)` opens, and turns an exception into the AXI
  refusal `{"ok": false, "error": ..., "help": [...]}`; add a `_HELP` row when a new exception type needs its own next step.
- JSON in, JSON out. Every path an argument names resolves under the project root (`settings.project_root`); outside it is
  refused (`settings.PathOutsideProject`). Slow work runs as a job (`jobs.py`); only its scene-touching tail runs on the main thread.
- Pure logic goes in a bpy-free module so the standalone suite can test it; Blender behaviour is tested through
  `tests/lampway_tools/blender_run.py` against the real binary (`LAMPWAY_BIN`).
- A tool that spends never confirms: it returns a plan with the price read back, and the Client's own button is the only confirm
  (`human_gate.py` refuses while any script runs).

## 3. The server half (what the model and MCP see)

- Add a `Def(name, description, params, api=...)` to `DEFS` in `server/lampway_server/agent/lampway_tools.py` (or `batch=` for a
  ported batch tool). `build_script` turns a call into one `api.call(...)` whose arguments ride as ONE JSON string literal, so no
  argument value can change the script; a missing required argument is refused before Blender is asked.
- The description is the documentation the model reads and the docs render: say what it does, what it refuses and the next
  step. Name the canon page when there is one.
- A tool family that runs on the server (studio, video, prompts, ledger, assets, compute) has its own `specs()` module under
  `server/lampway_server/agent/` and is concatenated into `TOOLS` in `agent/tools.py`; `script_for` refuses to send a server-run
  tool to Blender.
- MCP offers external apps the scene tools, every `DEFS` tool and the server's read-only tools (`mcp.py` `offered_tools`). Studio
  tools are never offered to them (they spend on the owner's subscription) and the swarm only to a Lampway pane bound to a scene
  tab. Lampway's agent (Mode 1, Hermes in its pane) is offered the whole registry as Capabilities allow through its unit's
  endpoint (`engine/mcp_endpoint.py`). No tool asks the user: Hermes asks with its own `clarify`, and a question tool would be
  offered to no agent (`ask_user` left the registry, 2026-10-07).

## 4. Money, receipts and egress

- A paid provider call writes its receipt first (`server/lampway_server/jobreceipts.py`): `submission_pending` is on disk before
  the first byte leaves; a crash leaves `submission_unknown`, and only the user can acknowledge or link it. Nothing resubmits.
- Call `egress.preflight(route)` before marking a receipt pending, so a route that is off refuses having sent nothing.
- A new outbound host is a new `Route` in `egress.ROUTES` with its retention and training terms (or the explicit "unread"
  value), off until the user opts in. An in-process httpx call is gated at the transport; a call that starts another process
  wraps its launch in `egress.guard(route, ...)`.
- The spend policy (`spendpolicy.py`) decides whether a job waits for a click; an unknown price always waits. It never clicks.

## 5. Tests (RED first, both halves)

- Server: extend `server/tests/test_lampway_tools.py` (the tool is in the agent's list with a schema; its script is one api call;
  arguments cannot break out; a missing argument is refused) and the feature's own test file. `cd server && .venv/bin/python -m pytest -q tests`.
- Client: a standalone test for the pure module, and a `tests/lampway_tools/` test that drives the real binary for anything that
  needs Blender. A test that skips for want of a binary is not evidence; say so in the report.
- Each falsifier from the contract is a test that fails on the old code. Keep it after the fix.

## 6. The generated tool docs

The tool reference is generated from the live registry, never hand-written: `lampway_server.agent_files.generate` renders the
per-area tool skills a user's project receives, and the docs lane's `docs/gen_tools.py` renders `docs/tools.md` with a `--check`
that names added and removed tools. After adding a tool, regenerate and commit the output in the same change; where the
generator is not on your base yet, say so in the report rather than writing the page by hand. **No skill update is owed per
tool** (captain, 2026-10-06): the registry is the documentation. The rail holds the generated pages instead: each generator named
in `rail/catalog.json` `generated` must pass its `--check` in CI (RAIL-018), so a tool added without regenerating its page is red.

## 7. Done means

The contract's acceptance evidence is in hand (a live run where the contract asks for one), both suites pass, the generated
docs are current, and the report names what was not run.

Provenance: Lampway's `specs/CONTRACT_TEMPLATE.md` (the coordinator's spec shelf), the module docstrings cited above, Titan's
`titan-tool-skills` (every tool owns its procedure; the registry is checked, not trusted).

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the procedure for adding a tool existed only across module docstrings and an off-tree contract template | one procedure: contract, client api, server Def and registry, MCP exposure, receipts, egress, spend gate, generated docs, tests on both halves | captain ruling, 2026-10-05 |
| 2026-10-06 | tool docs held by the rail, not by skill rows | captain: "Those recs are fine" (recommendation 3) | binding every registry file to this skill would owe a body change per tool; nothing held the generated page | no per-tool skill row; the generated page's own --check is a rail leg (catalog `generated`, RAIL-018) | captain ruling, 2026-10-06 |
| 2026-10-07 | `ask_user` left the registry; who is offered what | coordinator brief, Mode 1 loose end 5 (spec A2, A5) | §3 said studio tools, the swarm and `ask_user` "need the agent loop", which is gone, and did not say that Mode 1's Hermes reaches the whole registry through its own endpoint | §3: external apps, bound panes and Lampway's agent each named with what they are offered; no question tool, Hermes asks with `clarify` | none |
