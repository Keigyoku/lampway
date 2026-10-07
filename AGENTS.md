---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# Lampway — agent contract

> **MANDATORY — load before your first change.** Every agent working in this repository loads the `lampway-coding-guidelines`
> skill (or reads [`rail/skills/lampway-coding-guidelines/SKILL.md`](rail/skills/lampway-coding-guidelines/SKILL.md) in full on a
> harness without a skill surface) before its first change. This file is the repository-root binding contract: the laws, the map,
> and the index of the contracts below it. `CLAUDE.md` only imports it.

## Purpose

Lampway is an open-source 3D suite on a Blender 5.2 core with an AI agent inside it and a server the user runs. It began as a fork
of the GPL Mixar desktop client and is not affiliated with Mixar or the Blender Foundation; the upstream backend is closed and
hosted, so Lampway's backend (`server/`) is new, single-user and loopback by default. Product description and quick start:
[`README.md`](README.md); contributing: [`CONTRIBUTING.md`](CONTRIBUTING.md); the build: [`BUILD-LAMPWAY.md`](BUILD-LAMPWAY.md).

## Standing rule

Design direction and scope come from the captain. Agents offer craft (structure, options, tradeoffs, measurements), never
direction. Anything genuinely his (scope, providers, spend, thresholds, what ships) is a decision to route, not a value to pick.

## Laws

Each law is the captain's and is held by the gate named beside it. A change that would break one is refused, not negotiated.

1. **Never contact the upstream service.** Nothing Lampway runs calls `api.mixar.app`, `mixar-backend` or the upstream CDN; every
   host goes through configuration (`src/scripts/mixar/config/brand.py`, `config.py`). Gates: `tests/lampway/test_lampway_no_mixar_hosts.py`,
   `tests/lampway/test_site_links.py`.
2. **Egress is opt-in and visible.** Every outbound route is off until the user opts in, and every send is logged before it
   leaves: one choke point at the httpx transport, `guard()` for a spawned process, `preflight()` before a paid receipt
   (`server/lampway_server/egress.py`).
3. **Spend only on the user's click.** Tools plan and price; only the user confirms, from the Client. No agent tool, swarm worker
   or MCP client has a confirm path; studio tools are not offered over MCP (`server/lampway_server/studios/approvals.py`,
   `spendpolicy.py`, `mcp.py`, `src/scripts/mixar/modules/lampway_tools/human_gate.py`).
4. **Paid work is write-ahead.** A paid job's receipt is on disk before the first byte is sent; nothing resubmits an unknown job
   (`server/lampway_server/jobreceipts.py`).
5. **Controlled decoupling.** Lampway's own herdr server and its agent panes survive a crash of Blender or of the server; a restart
   reconciles, never kills an unknown pane, never respawns an ended one without a click (`server/lampway_server/herdr/__init__.py`).
6. **No owner values in tracked files.** No personal email, home path, account id, token, signed URL or media metadata; the
   maintainer's own patterns live outside the repository. Gate: `scripts/lampway/prepublish_gate.py` in the `pre-push` hook and
   `.github/workflows/pii-gate.yml`.
7. **Build the tool, not the output.** Proven code first; a model or studio slots in behind the same interface; decisions are
   typed and logged. The 3D algorithms are specified once in the canon (`lampway-canon`); nobody re-derives them.

## How the rail works here (DOE x DOX)

- **DOX:** each `AGENTS.md` is the binding contract for its subtree. Before editing a file, read every `AGENTS.md` from this one
  down to it; the closer one controls local detail, and no child weakens a law. After a change, update the nearest owning
  `AGENTS.md` when you changed a contract, an invariant, a test command or the owner.
- **DOE:** the canonical skills under `rail/skills/` are the directives, the agent orchestrates, the tools and scripts execute.
- **The anneal rule:** an `AGENTS.md`, a canonical skill or a catalog trigger that changes owes an appended anneal row and a body
  change in the same commit. `python3 rail/rail.py check` holds it for every commit since the rail's baseline; CI runs it in full, and the
  `pre-push` hook runs its quick form on the commits being pushed.
- The long form, for people: [`docs/rail.md`](docs/rail.md). Maintaining the rail: the `lampway-rail` skill.

## Skills

The canonical source of each skill is `rail/skills/<name>/SKILL.md`; `.agents/skills/` and `.claude/skills/` hold generated copies
(`python3 rail/rail.py sync`). This table and that directory must agree; the rail check compares them.

| skill | load it when |
|---|---|
| [`lampway-coding-guidelines`](rail/skills/lampway-coding-guidelines/SKILL.md) | before any change in this repository |
| [`lampway-tool-authoring`](rail/skills/lampway-tool-authoring/SKILL.md) | adding or changing an agent tool, a provider route, a paid job |
| [`lampway-agent-tools`](rail/skills/lampway-agent-tools/SKILL.md) | before driving the app or running a step a tool may already do |
| [`lampway-canon`](rail/skills/lampway-canon/SKILL.md) | before any fit, pose, weight, placement, proportion, retopology, UV, bake, clearance, rig or normalization work (`docs/canon/`) |
| [`lampway-release`](rail/skills/lampway-release/SKILL.md) | before any push, publish, tag or main advance |
| [`lampway-rail`](rail/skills/lampway-rail/SKILL.md) | changing any AGENTS.md, CLAUDE.md, skill or trigger, or repairing a rail finding |

## Repository map

| path | what it is |
|---|---|
| `upstream/` | the pinned Blender source (submodule, tag v5.2.0); read-only |
| `src/` | the overlay: Python in `src/scripts/mixar/modules/<module>`, native code in `src/source/blender/` |
| `source/`, `build/<env>/` | GENERATED by the build (`scripts/unix/overlay.sh` recreates `source/` every build); never edit, never commit |
| `server/` | Lampway's own backend, `lampway_server` |
| `scripts/lampway/` | Lampway's build, launch, Python-sync and pre-publish scripts |
| `scripts/unix/`, `scripts/windows/`, `cmake/` | upstream's build machinery, with Lampway's options (`LAMPWAY`, `MIXAR_CUDA`) |
| `tests/` | the standalone client suites, the brand and fork gates, the binary-driven tool tests, the rail's tests |
| `docs/` | measured reports, the roadmap, the user documentation and the algorithm canon (`docs/canon/`) |
| `specs/motion_graphics/` | motion scene/tool contracts and acceptance; implemented behavior is pinned to PR3, open requirements remain explicit |
| `rail/` | this rail: the canonical skills, the catalog and the check |

## Facts carried from the upstream guide (verified against this tree)

The root `CLAUDE.md` used to be upstream's own guide, naming its closed backend. These facts from it still hold here:

- **The overlay build.** `src/` is rsynced over a fresh copy of `upstream/` into `source/`; CMake builds `source/`. Everything
  under `src/scripts` is installed into the app except `__pycache__`, `mixar/modules/testing` and in-tree `tests/`
  (`src/source/creator/CMakeLists.txt`), so nothing else belongs there.
- **Bootstrap.** `src/scripts/startup/bootstrap/__init__.py` configures the network (trust store, proxy) before any bootstrap
  module, then registers the bootstrap modules, then loads every `modules/**/ui/` file in time-budgeted batches (4 ms per frame by
  default): properties first, then operators, then panels and menus.
- **Tests outside Blender.** `bpy` is a MagicMock (the root `conftest.py`), which also preloads the real numpy, PIL and requests so
  collection order cannot decide whether a test sees a mock. Operator logic is pinned by source-level or `ast` tests.
- **Pinned contracts with their tests:** the network contract (`tests/network/`), atexit cleanups never touch `bpy` data
  (`tests/test_shutdown_hooks_atexit.py`), the per-user config overlay over the read-only bundled `mixar.json`
  (`tests/test_config_persistence.py`), operators dispatched only through a re-verified region
  (`tests/test_mixie_chat_operator_dispatch_guard.py`), `BLI_string_split_name_number` parsing without `std::stoi`
  (`tests/test_name_number_split_overlay.py`). The agent chat architecture: `src/scripts/mixar/modules/space_mixie_chat/ARCHITECTURE.md`.
- **Gotchas the code and tests cite as "the CLAUDE.md rule"** (that file now imports this one, so the citations resolve here):
  - *Handler pattern:* depsgraph handlers set flags and `bpy.app.timers` do the work; never heavy work or a property write in a
    draw callback (`tests/virtual_camera/test_cinema_phone_surface.py`; cited in `space_mixie_chat/ui/operators/scene_render_ops.py`).
  - *DRW offscreen passes reset the region framebuffer viewport and scissor:* capture and restore both, or the region renders
    black (`tests/virtual_camera/test_stream_capture_gpu_context.py`; cited in `virtual_camera/core/stream_capture.py`).
  - *Keyconfig reload:* a C-registered keymap item must also be registered in the add-on keyconfig, because a GUI keyconfig
    preset reload wipes C-registered items (`tests/moodboard/test_frame_selection_consumers.py`).
  - *No viewport render inside a window resize:* timer and modal code that renders defers while
    `WindowManager.mixar_window_resizing` is true (`tests/scribble_mark/test_scribble_resize.py`).
  - *Upstream's 500-line file limit:* a guideline, not a gate (captain, 2026-10-06; `lampway-coding-guidelines` §4b); pinned
    only for the glass-kit family (`tests/test_mixar_liquid_glass_kit.py`).
- Upstream's guide pointed at a private module-document map (`docs/modules/`); it is not in this repository.

## Child DOX Index

A rule lives in the `AGENTS.md` closest to the code it binds: one subtree owns it, that subtree's file; two, their common parent;
a law, this file. Each child states its invariants, its test commands and its owner.

| path | owns | touch carries |
|---|---|---|
| [`server/AGENTS.md`](server/AGENTS.md) | Lampway's backend: agent loop, tools registry, MCP, egress, receipts, spend, studios, herdr | the egress, spend, receipt and decoupling invariants; the server suite |
| [`src/scripts/mixar/modules/lampway_tools/AGENTS.md`](src/scripts/mixar/modules/lampway_tools/AGENTS.md) | the client-side tools the agent calls inside Blender | the api door, the refusal shape, the project-root jail, the human gate; the binary-driven suite |
| [`src/source/AGENTS.md`](src/source/AGENTS.md) | Lampway's patches to the native (C/C++) overlay | the `LAMPWAY` guard, upstream compatibility, the native build owner |
| [`scripts/lampway/AGENTS.md`](scripts/lampway/AGENTS.md) | the build, launcher, Python sync and pre-publish gate scripts | AXI refusals, the box, the gate's outside-the-tree owner patterns |
| [`docs/AGENTS.md`](docs/AGENTS.md) | the reports, the roadmap and the user docs | measured claims only, generated pages never hand-edited, public paths only |
| [`docs/canon/AGENTS.md`](docs/canon/AGENTS.md) | the algorithm canon: pages 01-22, rig tools, the canonical asset schema, goldens | the repo copy is the source of truth; goldens generated and byte-checked; falsifiers kept; `check_canon.py` |
| [`tests/AGENTS.md`](tests/AGENTS.md) | every client-side suite and gate | RED first, plants for every gate, a skip is not a pass |
| [`rail/AGENTS.md`](rail/AGENTS.md) | the rail: canonical skills, catalog, check, self-test | the anneal rule, the finding codes, the baseline policy |

## Maintaining this file

Motion contracts live in [`specs/motion_graphics/motion_graphics.md`](specs/motion_graphics/motion_graphics.md). Updating a specification does not certify its implementation; retain the distinction between observed behavior, open requirements and captain decisions, and carry exact-head evidence.

Keep it for what almost every session needs; point at the file or command that owns a detail. Prefer rewriting an entry to
appending a sibling. A change here owes an anneal row in the same commit, like every rail.

## DOX closeout

One row per tag, added before the tag is cut: the tag, what annealed in the increment, and the evidence. `python3 rail/rail.py
closeout --tag <tag>` reads it. No tag has been cut under the rail yet.

| tag | what annealed | evidence |
|---|---|---|

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption: this file replaces the upstream guide | captain: "make the DOE x DOX AGENTS rail for Lampway, examples of it are in Vellum and Titan" | the root guide was upstream's, named its closed backend and a private doc map, and no file carried Lampway's laws | the laws with their gates, the DOX chain, the skill and child indexes (both checked against the tree), the verified facts kept from the upstream guide | captain ruling, 2026-10-05 |
| 2026-10-06 | the 500-line rule settled; the rail in the hook | captain: "Those recs are fine" | the file limit was recorded as an open decision; the rail's place in the push was CI only | the limit is a guideline (the coding skill §4b); the laws' rail line names the pre-push quick check | captain ruling, 2026-10-06 |
| 2026-10-06 | the canon indexed | coordinator: "GO for rail row 1" | the canon lived off-tree, outside every index | docs/canon in the repository map, the Child DOX Index and the canon skill's row | captain ruling, 2026-10-06 |
| 2026-10-07 | formal motion contracts indexed | captain authorizes writing the previously unwritten specs | implementation citations had no repository specification and could overstate acceptance | index the new contracts and require explicit behavior, gap and decision status with exact-head evidence | captain ruling, 2026-10-07 |
