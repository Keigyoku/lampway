---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# lampway_tools — the client-side tools

The tools the agent, the panel's buttons, the operators, MCP clients and the live bridge all call inside the running app:
`api.py` is the one door; `features/` and `pipeline/` hold the tool engines (`features/` touches Blender, `pipeline/` is mostly
pure); `meshqa/`, `rebuild.py`, `meshpaint.py`, `jobs.py`, `runner.py` and the `*_client.py` / `*_state.py` pairs talk to the
server. This directory ships inside the app (everything under `src/scripts` is installed), so nothing here may be a scratch file,
a sample asset or a test. Adding a tool: the `lampway-tool-authoring` skill; the algorithms: the `lampway-canon` skill.

## Invariants

1. **One door.** The agent's scripts reach a tool only through `api.call(name, payload)`, and only names registered by `@tool`
   (`TOOL_FUNCS`) are callable; the payload is one JSON object.
2. **Refusals name the next step.** A failure is `{"ok": false, "error": ..., "help": [...]}`, never a traceback into the model
   (the `@tool` wrapper and its `_HELP` table).
3. **The project-root jail.** Every path an argument names resolves under `settings.project_root` (`settings.resolve_in_root`);
   outside it is refused with `PathOutsideProject`. Tools write new files and never overwrite the user's sources; a rebuild tag is
   never overwritten.
4. **Only the user's click confirms a spend.** Anything that runs Python for someone else (the agent's executor, a headless
   worker, the live bridge) runs inside `human_gate.scripting()`, and the confirm operator refuses while one is on the stack.
5. **The scene is touched on the main thread only.** Slow work is a job (`jobs.py`); only its scene-touching tail runs from the
   app's timer. Background threads never touch `bpy`.
6. **The live bridge serves only its own user.** It runs unsandboxed Python, so each connection's peer uid is read from the
   kernel's socket table and only the app's own uid is served; an unattributable connection or an oversize request is refused
   (`bridge.py`).
7. **Egress is the server's.** A route is switched on only by the user's click (`ui/operators/egress_ops.py` through
   `egress_client.py`); no tool here opens an outbound connection of its own to a provider.
8. **Settings resolve environment, then `<lampway home>/settings.json`, then the default** (`settings.py`); the profile lives under
   `LAMPWAY_HOME` and never in the user's stock Blender profile.

## Test

```bash
python -m pytest -q tests/lampway_tools                     # without a binary, the binary-driven tests SKIP: not a pass
LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools   # against a built app (syncs Python first)
python -m pytest -q tests                                   # the standalone suites, bpy mocked
```

`tests/lampway_tools/blender_run.py` runs a script inside the real binary and reads `RESULT {json}` lines; it calls
`scripts/lampway/sync_python.sh` before every run, so a Python change needs no rebuild. The server half of each tool is tested in
`server/tests/test_lampway_tools.py`.

## Owner

The lane whose contract names the tool writes it and its tests; the integration lane lands it. A tool's engine follows its canon
page; the canon's open decisions are the captain's.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the client tools' door, jail, refusal shape and human gate were known only from docstrings | the invariants with their modules, the binary-driven suite and its skip rule | captain ruling, 2026-10-05 |
