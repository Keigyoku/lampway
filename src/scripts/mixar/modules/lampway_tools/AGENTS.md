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
9. **What an agent may do is the user's click, and the Client holds no default of its own.** A capability is switched, its approval or
   options changed and an agent's proposal accepted only by the user's click (`ui/capabilities.py` through `capabilities_client.py`,
   every write behind `human_gate`; the first-run walk's step in `onboarding.py` writes only what the user ticked differently from the
   server's own defaults). The capability-enabled first-run walk sizes each current step from its actual content, and
   paginates the capability catalog within a fixed content-row budget. Its partition reserves possible warning rows so
   ticking a choice cannot move it between pages; paging refreshes the original native dialog through
   `Window.mixar_refresh_popups`, preserves choices and never opens a second modal or writes settings. Legacy walks retain
   their existing sizing behavior. Turning on one that runs code or acts outside Lampway shows its plain warning first. The page reads a cache
   (`capabilities_state`) filled by a worker thread; a draw never reaches the network, and the page never switches a route.
   Agent preferences exposes the same server-backed native Hermes delegation, cron and background choices. Every enable
   action displays the explicit untested layering warning and requires user confirmation; all default off on the server.
   The warning remains visible when enabled, and scripts cannot confirm it. No client-only copy of these choices is saved.
   Context settings in the Choices/Capabilities surface follow the same rule: the server supplies defaults and explicit project
   overrides; the client draws a cache, performs requests off-thread and publishes replies on the main thread. Publication
   redraws areas and rebuilds open refreshable unanchored popovers through the native window helper; temporary popup
   regions are outside areas, so area redraw alone leaves the original Context page stale. Edits/reset require
   the user's click and a matching project; a stale dialog cannot write another project. The UI shows the pinned runtime's live
   reload and independent summarizer limitations rather than silently restarting a pane or inventing a model window.

   First native-harness launch has its own explicit account notice dialog, separate from route enablement. Its cache-only draw
   displays safe native status or UNKNOWN; slow preparation and launch stay off the app thread. A script cannot confirm,
   a cancelled or failed dialog discards its nonce, and stale scene validation refuses before launch. Failed queue callbacks
   cannot strand later owned responses. Neither notice preparation nor cancellation changes capabilities or login.

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
| 2026-10-07 | the Capabilities page and the walk's step (E2, client half) | coordinator: "the client (Blender UI) half of Capabilities" after the server's switchboard (e837e5c) | invariant 7 named routes only: nothing said who may switch what an agent can do, so a new page could have given a script, or a Client-side default, that say | invariant 9: the user's click through `ui/capabilities.py` behind `human_gate`, the walk writing only the user's differences from the server's defaults, a draw reading a cache that a worker thread fills | none |
| 2026-10-08 | project Context configuration controls | R3/Q3 missing-section RED and stale-popup RED | the client had no Context settings and a dialog could outlive its selected project | invariant 9: cached defaults/overrides, worker requests, main-thread publication, human-gated explicit edits/reset and project identity fencing; runtime limitations displayed | focused client witnesses; native proof pending |

| 2026-10-08 | original Context popout receives async state | actual production-panel loading RED and callback RED | Context response publication redrew areas but never rebuilt temporary popup layout | invariant 9: main-thread publication refreshes owned native popup layouts as well as areas, without networking from draw or altering user confirmation | callback RED/GREEN; matching native original-popout proof required |
| 2026-10-08 | Agent preferences for experimental native Hermes helpers | captain: default-off delegate, cron and background knobs with an explicit untested layering warning | preferences lacked these controls and generic capability warnings did not name experimental layering | invariant 9: cached server-backed switches, persistent warning, explicit human confirmation before each enable, no client defaults | six behavioral RED failures and focused client GREEN; native UI proof required |

| 2026-10-08 | audit first-run capability pagination | supplied PR4 audit A06 | catalog row estimate inflated every page and hid navigation as capability counts grew | invariant 9: current-step content sizing, bounded stable capability pages, preserved ticks and no paging writes | three causal RED controls and 43 focused GREEN checks; matching native visibility proof required |

| 2026-10-08 | capability paging keeps one native dialog | actual matching 84560502 UI Next produced two dialog regions | reinvoking from an inner page button stacked a modal over the original | invariant 9: refresh the original popup layout through the existing native window helper; no extra modal or changed choices | actual native RED and focused callback RED; new matching build proof required |

| 2026-10-10 | first human native-agent disclosure | agent-modes spec B5 | cockpit and scene launch had no independent first-account warning, and failed popup/queue callbacks retained pending requests | invariant 9: explicit human notice, cached draw, off-thread preparation and cancellation/stale-scene cleanup | four causal client dialog REDs; 30 focused client checks pass; matching physical native dialog proof remains required |
