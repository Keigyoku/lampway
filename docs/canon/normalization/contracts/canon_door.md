<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: the door decorator (`api.tool(consumes=..., produces=...)`) and its CI check

Status: **extends** `api.tool` (`LT/api.py:51-67`) and `runner.Tool` (`LT/runner.py:36-45`). Priority P0. Placeholders as in
`../AUDIT.md`; design in `../DOOR.md` §2 and §5.

## 1. Name and one-line purpose
The single registry decorator gains a required declaration of what each tool consumes and produces; a CI check proves, from the
code itself, that no tool and no importer call escapes it.

## 2. Source
- The registry is already single and derived: "Every @tool function, in definition order: derived, not listed by hand (a hand-kept list let 26 tools of Waves 2-4 be functions and Defs the agent could not run)" (`LT/api.py:1555`).
- Memory enumeration-is-not-a-gate: "a rule enforced by a list is enforced by whoever last read it carefully; owe a gate, prefer closed-by-construction".
- rail@ `lampway-tool-authoring` §2: "decorate it with `@tool`. The decorator registers it in `TOOL_FUNCS`, the only door".

## 3. User story
A crew adding a tool cannot register it without saying what it reads; a crew adding an importer call anywhere but `canon_io`
fails CI with the file:line; the agent sees each tool's needs in its description.

## 4. Inputs
Decorator: `consumes: dict[str, Need] | NONE(reason) | LEGACY(issue)`, `produces: dict[str, Inherit | Fresh | Raw]` (default `{}`).
CI: none (the scan reads the tree).

## 5. Outputs
`api.TOOL_DOORS` (name -> declaration); the refusal envelope of DOOR.md §2; CI test results naming each offence with file:line.

## 6. Engine (proven code)
Python `functools.wraps` (as today), `inspect.signature` to bind arguments to the declared names, `canon_asset.satisfies`,
`canon_io.facts`; the CI scan is `ast` over `LT/**/*.py` and every `SRV/**/*.py` that imports `bpy` (today
`SRV/library/render_worker.py`), the same technique the rail lane's generated docs use (`docs@ docs/gen_tools.py --check`).

## 7. Model slot
None.

## 8. Preconditions and refusals
Import time: `TypeError("@tool needs consumes=: declare what this tool reads (Need(...)), or NONE('why') if it reads no asset")`.
Call time: DOOR.md §2's three refusals (raw, unstamped, changed since normalization) and the unmet needs.

## 9. Side effects and safety
Stamps outputs (custom properties only). Adds a sha256 over vertex positions per door check: measure it (test 5) before
enabling on million-vertex bodies; a body package is checked by its hash, not re-hashed per call.

## 10. Tests (RED first)
1. `test_every_tool_declares` (AST): RED today, every `@tool` in `LT/api.py` and the lanes lacks `consumes`.
2. `test_one_importer` (AST): RED today with the 20+ call sites listed in DOOR.md §1.
3. `test_runner_tools_declare`: `Tool(...)` without `consumes` is a `TypeError`.
4. `test_red_team_raw_inputs` (Blender): every `TOOL_DOORS` entry naming a kind refuses a raw cube, armature and image; the list is `TOOL_DOORS`, never typed. Falsifier: remove the door from one tool and the test names it.
5. `test_door_cost`: the door's overhead on a 25k-face piece and on the 32k-vertex body mesh, recorded; a budget is the captain's call only if it bites.
6. `test_legacy_ratchet`: the committed count in `LT/canon_legacy_count.txt` equals the scanned `LEGACY(` count and the file's history only decreases (git log of the file in CI).

## 11. Acceptance evidence
CI green with `LEGACY` at zero; one screenshot-free proof: the red-team test's table (tool, refused, message) in the PR.

## 12. Dependencies and order
`canon_asset`, `canon_io` (import_raw, facts). Lands with every tool marked `LEGACY` (count = number of consuming tools), then
the count falls as each group gets real declarations (`canon_migration.md`).

## 13. Open questions
D7 (hard switch vs the ratchet), D9 (signed stamps).
