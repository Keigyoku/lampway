---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# scripts/lampway — build, launch, sync and the pre-publish gate

Lampway's own operator scripts: `build_linux.sh` (clone to runnable app in the build box), `lampway` (the one command: server plus
app on a copy of a file), `sync_python.sh` (a Python-only change into an installed build), `prepublish_gate.py` with
`pii_allow.txt` (what may never be published), `engine_env.py` (the pinned Hermes engine environment, agent-modes spec E1.1, and
the prebuilt Hermes TUI a Mode 1 pane runs, A1), `herdr_env.py` (the pinned herdr, built from `third_party/herdr` with herdr's own
toolchain pin and `cargo build --release --locked`; agent-modes spec A4). Upstream's build machinery stays in `scripts/unix/` and `scripts/windows/`; these
wrap it. The procedures: the `lampway-coding-guidelines` skill (build and run) and the `lampway-release` skill (the gate).

## Invariants

1. **AXI refusals.** A refusal prints `error: <why>` and a `help[N]:` list of next commands on stdout and exits 1; an unknown flag
   exits 2; `--plan` / `--check-deps` print what a run would do and touch nothing. A new script follows the same shape.
2. **The build runs in the box, never on the host,** and never writes `.env`: a `.env` that contradicts the requested environment
   is refused, because `settings.sh` sources it after the environment and would silently win.
3. **The launcher never takes a secret as an argument and never prints one**; the OpenRouter key comes from the environment or a
   dotenv file the user points at, and the session budget is a hard ceiling. `--copy` opens a copy; the user's file is never
   opened for saving. The profile lives under `LAMPWAY_HOME`.
4. **The pre-publish gate holds no owner value.** The maintainer's patterns come from `PII_OWNER_*_RE` variables (a 0600
   `pii_owner.env` in the shared git directory locally, repository secrets in CI). `pii_allow.txt` holds only known-fake values,
   each with its reason on its line. Secrets are printed as their first four characters only.
5. **The gate proves itself.** `prepublish_gate.py --self-test` plants one offender of each kind and fails if any goes unseen; a
   change to the patterns lands with its plant.
6. **The engine build is finished or absent.** `engine_env.py` builds in a copy of the pinned source (never in `third_party/`):
   `uv sync --frozen --extra mcp`, then the TUI (`npm ci --workspace ui-tui` at the copy's root, `npm run build` in its `ui-tui`),
   and writes `engine.json` (naming `hermes` and `tui`) LAST, so a directory without it is an unfinished build the server ignores.
   `--plan` lists the npm steps; `--check-deps` names missing tools and verifies installed npm against the pinned
   package manifest before any build writes. Unknown versions or constraint syntax refuse with help. Before npm builds,
   `engine_tui_compat.py` validates the three exact pinned source hashes and every replacement anchor, then installs the owned
   history-display helper in the build copy only. `engine.json` records original/patched source, helper and patcher hashes.
   Frontend notice provenance survives native timestamp cloning, stays outside serialized history, and an authoritative
   functional replacement retains native transcript caps and resets its native display generation. After the first native
   info baseline, a revision advancing beyond both the desired and applied revisions refreshes only while idle. Initial,
   same-revision and intermediate info keep native rendering. Unsupported source
   refuses without a completed manifest; the pin and generated bundles are never edited directly.
   Nothing at run time fetches or builds.
7. **herdr identity comes from the pin.** Resolve its stable package version from the verified commit's `Cargo.toml`, refusing
   local manifest drift. A shallow checkout needs no release tag or broad history fetch; unrelated tags cannot set identity.
   Require the exact binary version and write `herdr.json` last.

## Test

```bash
python -m pytest -q tests/lampway/test_build_linux.py tests/lampway/test_prepublish_gate.py tests/lampway/test_engine_env.py tests/lampway/test_herdr_env.py
python -m pytest -q tests/lampway_tools/test_launcher.py tests/lampway_tools/test_linux_scripts.py
LAMPWAY_TEST_ENGINE_TUI_COMPAT=1 python -m pytest -q tests/lampway/test_engine_tui_compat.py
python3 scripts/lampway/prepublish_gate.py --self-test
scripts/lampway/build_linux.sh --plan
```

## Owner

The build script and the build box belong to the native-build lane (`lp/facelift` at the time of writing). The pre-publish gate is
the coordinator's final gate; widening what it allows is the captain's call. Changes to `prepublish_gate.py`, `build_linux.sh`,
`sync_python.sh` and `lampway` owe their skill an anneal row and a body change in the same commit (`rail/catalog.json` triggers).

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the scripts' refusal shape, secret handling and the gate's outside-the-tree patterns were known only from their headers | the five invariants, the test commands, and the scripts bound to their skills as rail triggers | captain ruling, 2026-10-05 |
| 2026-10-07 | the engine environment script | captain: Hermes Agent's runtime in Mode 1's seat (agent-modes spec Q7, E1.1) | the pinned engine had no build step, and Hermes refuses wheel builds | `engine_env.py` in the scripts list, in the AXI shape, with its test in the test command | captain ruling, 2026-10-06 |
| 2026-10-07 | the herdr build script | captain: "Pin the current herdr and Hermes releases the same way the Blender pin is done" | herdr had no pin and no build step: the cockpit ran whatever herdr was on PATH | `herdr_env.py` in the scripts list, in the AXI shape (`--plan`, `--check-deps` naming cargo and Zig 0.16.0), `herdr.json` written last, its test in the test command | captain ruling, 2026-10-07 |
| 2026-10-07 | the TUI prebuild and the end of ACP (agent-modes spec A1, A5) | captain, 2026-10-07: Mode 1 runs Hermes's own TUI in its pane; coordinator brief for the A1-A3 lane | the engine build had the `acp` extra and an `hermes-acp` entry nothing will use, and no TUI: `hermes --tui` would have run npm at run time | invariant 6: `--extra mcp` only, the TUI prebuilt in the engine's own copy, `engine.json` naming `hermes` and `tui` written last, `--plan` and `--check-deps` naming the npm steps and Node | captain ruling, 2026-10-07 |
| 2026-10-07 | merge: the TUI prebuild beside the herdr build script | coordinator integration of the A1-A3 lane | both sides rewrote the scripts list | the list names engine_env.py with the prebuilt TUI and herdr_env.py; both anneal rows kept | none |

| 2026-10-08 | audit npm preflight and shallow herdr identity | supplied PR4 audit A04-A05 | dependency check accepted incompatible npm and missing release tag substituted a commit prefix for binary version | invariants 6-7: pinned manifest npm constraints before writes and verified Cargo version with exact binary check | causal RED/GREEN including real shallow no-tags fixture; compiler fixture is controlled |
| 2026-10-10 | controlled native history display prebuild | actual pinned terminal Undo retained removed messages | runtime injection or direct vendor/generated edits would obscure the pin and rebuild provenance | invariant 6: validate exact native hashes and unique anchors, apply owned helper in normal copy, record provenance and manifest last; explicit compiler qualification command | 113 focused controls pass with native build/runtime still NOT RUN; changed native source plant refuses before any patch |
| 2026-10-10 | preserve frontend notice provenance in normal engine copy | compressed display and ordinary-info repaint regression | native timestamp clones lost object identity and replacement could lose command output | invariant 6: three hash-checked sources, enumerable Symbol provenance, native generation/caps and final manifest provenance | nine scratch controls and no-emission typecheck pass; normal rebuilt engine and terminal acceptance remain required |
| 2026-10-10 | later external USER rows reach native display | actual 9af pinned TUI retained stale rows despite correct native public history | Undo-only refresh ignored later externally originated turns | invariant 6: first info baseline stays quiet; only revisions beyond desired and applied refresh while idle, preserving native DISPLAY and frontend notices | causal controller RED one failure/one pass; six copy/refusal/compiler/controller checks pass; rebuilt native acceptance remains required |
