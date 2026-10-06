---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-coding-guidelines
description: "Load before ANY change in the Lampway repository: the overlay build model, the build box, the test suites and the test-first contract, the lanes and the merge-only integration flow, the gates, and the laws no change may break (never contact the upstream service, egress opt-in, spend only on the user's click, no owner values in tracked files)."
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: mixed
---

# Lampway coding guidelines

**Every agent reads this skill in full before its first change in this repository.** It is the one full copy of the crew
operating guide; the root `AGENTS.md` and the nested ones point here and add only their subsystem's rules. Product docs:
[`README.md`](../../../README.md), [`CONTRIBUTING.md`](../../../CONTRIBUTING.md), [`BUILD-LAMPWAY.md`](../../../BUILD-LAMPWAY.md).
Do not restate them; link them.

## 0. The laws

The laws are in the root [`AGENTS.md`](../../../AGENTS.md) §Laws, once, with the gate that holds each one: never contact the
upstream service; egress opt-in and visible; spend only on the user's click; paid work write-ahead; controlled decoupling; no
owner values in tracked files; build the tool, not the output. Every procedure below works inside them.

## 1. Repository layout and the overlay build

- `upstream/` is the pinned Blender source (a submodule; tag v5.2.0). `src/` is the overlay: Python under
  `src/scripts/mixar/modules/<module>`, native code under `src/source/blender/`. `source/` is GENERATED: `scripts/unix/overlay.sh`
  deletes it, copies `upstream/` in, then rsyncs `src/` on top. Never edit `source/` and never run CMake inside it.
- Everything under `src/scripts` is installed into the app; the install rule filters `__pycache__`, `mixar/modules/testing` and
  in-tree `tests/` directories (`src/source/creator/CMakeLists.txt`). Do not put sample assets or scratch files there.
- `server/` is Lampway's own backend (`lampway_server`, Python >= 3.11, Starlette); the app talks to it over JSON-RPC on a
  WebSocket at `127.0.0.1:8787`. The Lampway tools are Python the app's sandbox runs (`mixar.modules.lampway_tools.api`).
- `scripts/lampway/` holds Lampway's own build, launch, sync and pre-publish scripts. `rail/` holds this rail.
- Upstream's own names survive where renaming would break a lookup (`mixar` package, `MIXAR_*` build variables, the
  `build/<env>/bin/mixar` binary). User-visible strings use the brand constants; the brand gates in `tests/lampway` hold that.

## 2. Build and run (inside the build box, never on the host)

```bash
scripts/lampway/build_linux.sh --plan         # every resolved setting; touches nothing
scripts/lampway/build_linux.sh --check-deps   # names what is missing (exit 2)
MIXAR_ENV=Prod scripts/lampway/build_linux.sh # overlay -> CMake -> compile -> install -> embedded Python packages
scripts/lampway/sync_python.sh --bin-dir build/Prod/bin   # a Python-only change, without a compile
scripts/lampway/lampway --env Prod --copy --provider mock scene.blend   # server + app, on a COPY of the file
```

- The build runs in an Ubuntu 24.04 box with GCC 14 (the box is named in your brief; one crew per box). `MIXAR_CUDA=0` skips the
  Cycles GPU kernels; never a release choice. A clean build is long and an unchanged rebuild short (BUILD-LAMPWAY.md §3).
- If `distrobox enter` answers `unable to find user`, the numeric `podman exec --user 1000:1000 -w "$PWD" <box> ...` works.
- Blender returns 0 when a `--python-expr` raises: always pass `--python-exit-code 1`.
- The installed app never carries the repository's agent contracts (AGENTS.md, CLAUDE.md, SKILL.md, `.agents`, `.claude`): the
  scripts install excludes them and removes ones an older install kept, and `sync_python.sh` excludes and deletes them too
  (`tests/lampway_tools/test_install_has_no_agent_contracts.py` walks the installed tree).
- The launcher hands the server three more things: `LAMPWAY_MODELS_DIR` (the bundled local models, when the build bundled them),
  `LAMPWAY_BLENDER` (the binary the server's headless jobs run; defaults to the app's own) and `LAMPWAY_SECRETS_DIR` (below).
- The launcher's start banner prints the models directory and, when UE Look is on, the UE look state (`ue_look:` and its OCIO config).
- Long jobs run as a transient unit or a detached exec polled in the foreground, never a shell `&`. Kill recorded exact PIDs only;
  never a pattern kill. Never launch a window on the captain's desktop unless he asked; offscreen in the box is the default.
- No secret lives in `$LAMPWAY_HOME` (the agent's script sandbox reaches it): the launcher keeps the client's login keyring at
  `$XDG_STATE_HOME/lampway/keyring.json` (an older `$LAMPWAY_HOME/keyring.json` is moved there once, verified) and points the server
  at Connections' file store, `LAMPWAY_SECRETS_DIR` (default `$XDG_STATE_HOME/lampway-secrets`). A test never uses the real ones.

## 3. Test suites

| suite | command | needs |
|---|---|---|
| server | `cd server && .venv/bin/python -m pytest -q tests` | the server venv (`pip install -e ".[test]"`); no Blender, network or model |
| standalone client | `python -m pytest -q` (root `pytest.ini`; the root `conftest.py` stubs `bpy` and preloads real numpy/PIL) | Python with numpy, PIL, requests |
| brand and fork gates | `python -m pytest -q tests/lampway` | as above |
| client tools on the real binary | `LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools` | a built binary; without one they SKIP, which is not a pass |
| rail | `python3 rail/rail.py selftest && python3 rail/rail.py check` and `python -m pytest -q tests/rail` | git with the history back to the rail's baseline |
| pre-publish | `python3 scripts/lampway/prepublish_gate.py --self-test` then `--tree .` | Pillow (and ffprobe for `--media`) |
| algorithm canon | `python3 docs/canon/check_canon.py --self-test && python3 docs/canon/check_canon.py` | numpy, jsonschema |

`bpy` is a MagicMock outside Blender, so operator logic is pinned through source-level or `ast` tests, and behaviour that needs
Blender runs through `tests/lampway_tools/blender_run.py` against the real binary.

Temp files: nothing a test makes may outlive the run in the shared `/tmp` (a quota'd tmpfs). `run_script` points the binary's TMPDIR
into the run's own temp dir (removed after the run), resolves `@RUN_TMP@` in env values (`LAMPWAY_HOME="@RUN_TMP@/home"`) and points
`LAMPWAY_LEGACY_HOME` at an empty place, so a test home never copies the person's real `~/.mixar`; a test that reads a run's files
afterwards passes its own `tmp_path` in (for example `LW_KEEP_ROOT`). In-process tests use `tmp_path`; `tempfile.mkdtemp`/`mkstemp`
need `dir=` (`tests/lampway/test_tmp_hygiene.py` holds that). Both suites keep only a failed test's tmp_path
(`tmp_path_retention_policy = failed`).

The reference test environment is `scripts/lampway/test_env.sh` (upstream/ at its pin without LFS, `tests/requirements-test.txt`
and the server's declared dependency ranges into `LAMPWAY_TEST_PYTHON`); `scripts/lampway/test_all.sh` verifies it first and refuses
("run test_env.sh") when anything is missing, and refuses a binary whose `BUILT_FROM` native sources differ from HEAD. Outside test_all,
tests that need that environment SKIP with the reason and the conftest prints one `ENV-SKIPPED n` line.

No test reads the person's real home: the root `conftest.py` points `HOME`, the `XDG_*` dirs, `LAMPWAY_HOME`, `LAMPWAY_LEGACY_HOME`
and `LAMPWAY_TEST_ROOT` inside the basetemp for the whole session (the server's conftest does the same for `HOME` and `XDG_*`);
`mixar.config.paths` refuses a relative or placeholder-shaped home loudly and refuses to migrate from outside `LAMPWAY_TEST_ROOT`;
`run_script` refuses an unexpanded `@PLACEHOLDER@` before the binary starts.

## 4. Test-first, and the claim discipline

- **No behaviour change without a failing test first.** Run it, see it fail for the reason you claim (a compile or import error is
  not RED), make it pass, run the suite. The commit body carries the RED line, then the GREEN.
- **An assertion that cannot fail is not an assertion.** For every new check, plant the offender once and watch it fire; keep the
  plant as a test when you can (`rail/selftest.py` and `prepublish_gate.py --self-test` are the model).
- **Enumeration is not a gate.** A rule held by a list is held by whoever last read the list. Prefer a check that compares the
  list against the tree in both directions, or a structure that cannot express the mistake.
- **Never weaken or delete a failing test to go green.** Fix the code, or raise the wrong test as a decision.
- **A claim carries its receipt**: the command and its real output. Grade it out loud: said-so, pointed-at-the-line,
  ran-it, reproduced-live. A skipped suite is UNVERIFIED, never green.
- **Read before you write.** Before re-deriving any 3D algorithm (fit, weights, pose, placement, proportion, retopology, UV,
  bake, clearance), load `lampway-canon`; before driving the app, load `lampway-agent-tools`; before adding a tool, load
  `lampway-tool-authoring`.

## 4b. Size

Upstream's limit of 500 lines per file is a **guideline, not a gate** (captain, 2026-10-06): split a file when a second
responsibility has grown in it, not to meet a number. Only the glass-kit family pins it in a test
(`tests/test_mixar_liquid_glass_kit.py`); nine of Lampway's own server and tool modules were over it at the rail's adoption, and
that is not a finding.

## 5. Lanes and integration

- Work in your lane's worktree on its `lp/<lane>` branch. The integration branch `lp/wave5` merges lanes with `--no-ff` and
  **never rebases**; `main` moves only on the captain's word, fast-forwarded to a gated integration tip.
- At each milestone a lane runs `git fetch origin && git merge origin/lp/wave5` (merge, never rebase). Resolve a conflict in an
  anneal table by keeping both sides' rows, sorted by date; the rail accepts that as inherited.
- Push only your own branch; never force-push, never push `main` or another lane's branch. Stage explicit paths, never `-A`.
- Keep to the files your contract names. A shared file another lane owns is changed by that lane, or raised as a decision.

## 6. The gates before every push

1. The suites your change touches (§3), plus the full server suite when `server/` changed.
2. `python3 rail/rail.py check` (the rail; it also runs in CI) and, when you changed `rail/`, `python3 rail/rail.py selftest`.
3. The pre-publish gate and `rail.py check --quick` run in the `pre-push` hook (`git config core.hooksPath .githooks`); CI runs
   both in full. Never bypass the hook.
4. `reuse lint` (CI): every new file carries SPDX copyright and licence lines, or a `REUSE.toml` entry.

## 7. Keeping this skill true

Change the procedure here, in `rail/skills/lampway-coding-guidelines/SKILL.md`, append a row to the Anneal log in the same
commit, then `python3 rail/rail.py sync`. The generated copies under `.agents/skills/` and `.claude/skills/` are never edited by
hand. A fact goes in once it is reproduced; a change of doctrine is the captain's, proposed with its exact text.

Provenance: Titan's `titan-coding-guidelines` (the operating-guide shape, the claim ladder, F1-F6 test-first), Vellum's
`vellum-coding-guidelines` (graph-first, design-first, prove-it-works), Lampway's `BUILD-LAMPWAY.md`, `CONTRIBUTING.md`, the
module docstrings cited above, and the build order's rulings of 2026-10-05.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the root guide was upstream's and named its closed backend; Lampway's laws lived only in module docstrings and the build order | one canonical operating guide carrying the laws, the build, the suites, the test-first contract and the merge-only lanes, verified against the tree | captain ruling, 2026-10-05 |
| 2026-10-06 | the 500-line limit is a guideline; the rail in the hook | captain: "Those recs are fine" (recommendations 2 and 5) | upstream's 500-line rule read as a gate that nine Lampway modules already broke; the rail ran only in CI | §4b states the limit as a guideline with its one pinned family; §6 names the hook's quick rail check | captain ruling, 2026-10-06 |
| 2026-10-06 | suite hygiene | the integrator's batches: a full client run left ~25 GB and the coordinator's /tmp filled twice | test homes were never removed, scripts inside the binary wrote to the shared /tmp, and the first-run migration copied the person's real ~/.mixar (109.7 MB) into every test home | run_script owns the binary's TMPDIR and the legacy home; tmp_path_retention_policy = failed in pytest.ini; the temp-files paragraph in section 3 | none |
| 2026-10-06 | test isolation | the coordinator's stop: 436 private files committed under `@RUN_TMP@/home/…/app/` | a test passed LAMPWAY_HOME="@RUN_TMP@/home" before the harness expanded it; the relative home landed in the repository and the first-run migration copied the person's real ~/.mixar into it | the conftest isolation fixture, the loud refusals in paths.py and run_script, the isolation paragraph in section 3 | none |
| 2026-10-06 | secrets out of the Lampway home | Connections decision C7 (captain, "Those recs are fine"); lane connections, migration step 2 | the client's file keyring and the server's secrets sat inside the agent sandbox's roots | the launcher moves the keyring to the state dir once and exports LAMPWAY_SECRETS_DIR; section 2 names both places | captain ruling, 2026-10-06 |
| 2026-10-06 | the canon check among the suites | coordinator: "GO for rail row 1" | the canon's self-tests ran only on the shelf | `docs/canon/check_canon.py` in the suites table (CI: canon.yml) | captain ruling, 2026-10-06 |
| 2026-10-06 | merge of lp/orphans into lp/wave5 | the integrator's merge: lp/vault-ops added LAMPWAY_MODELS_DIR to the launcher, lp/orphans added LAMPWAY_BLENDER on the same line | two lanes edited the launcher's server-start line; the merged line carries both | the launcher bullet in section 2 names both variables | none |
| 2026-10-06 | merge of lp/uelook into lp/wave5 | the integrator's merge: lp/vault-ops added a models line and lp/uelook a ue_look line to the launcher's start banner | two lanes appended to the same banner block; the merged banner prints both | the banner bullet in section 2 | none |
| 2026-10-06 | secrets out of the Lampway home | Connections decision C7 (captain, "Those recs are fine"); lane connections, migration step 2 | the client's file keyring and the server's secrets sat inside the agent sandbox's roots | the launcher moves the keyring to the state dir once and exports LAMPWAY_SECRETS_DIR; section 2 names both places | captain ruling, 2026-10-06 |
| 2026-10-06 | merge of lp/connections into lp/wave5 | the integrator's merge: lp/connections added LAMPWAY_SECRETS_DIR, lp/orphans LAMPWAY_BLENDER, on the launcher's server-start line | two lanes edited the same line; the merged line carries both | the launcher bullet in section 2 names LAMPWAY_SECRETS_DIR | none |
| 2026-10-06 | one test environment | the coordinator's gate: 704eba5 gave a different verdict in a fresh worktree (no upstream/ checkout, no MCP SDK) | the suite's outcome depended on which checkout and venv ran it | test_env.sh, test_all's environment check, the conftest's explicit environment skips, the paragraph in section 3 | none |
| 2026-10-06 | merge of lp/wave5 into lp/connections | lane connections' merge: lp/orphans added LAMPWAY_BLENDER and lp/connections LAMPWAY_SECRETS_DIR on the launcher's server-start line | two lanes edited the same line; the merged line carries both | the launcher bullet in section 2 names all three variables | none |
| 2026-10-06 | merge of lp/connections (bbf4d3c) into lp/wave5 | the integrator's merge: lp/connections' own merge of lp/wave5 put the "secrets out of the Lampway home" row before the canon row; lp/wave5's merge of lp/connections (b10) put it after the uelook row | the two parents ordered one row differently, and the rail keeps every parent's rows in order, so that row appears at both places (the same row, recorded twice, not two events); the launcher bullet now names its three variables in one sentence | the launcher bullet in section 2 (lp/connections' wording) | none |
| 2026-10-06 | merge of lp/wave5 into lp/orphans | the orphans lane's merge: lp/wave5 brought LAMPWAY_MODELS_DIR to the launcher's server-start line, where lp/orphans had added LAMPWAY_BLENDER | two lanes edited the same line; the merged line carries both | the launcher bullet in section 2 names both variables | none |
| 2026-10-06 | agent contracts out of the install | coordinator: "EXCLUDE agent contract files (AGENTS.md, CLAUDE.md, skills under src/) from the installed app" | the scripts install copied `lampway_tools/AGENTS.md` and `CLAUDE.md` into the app, and the Python sync kept them | the install excludes and removes them, the sync excludes and deletes them; the bullet in section 2 | none |
| 2026-10-06 | merge of lp/wave5 into lp/facelift | the facelift lane's merge: lp/wave5 named LAMPWAY_SECRETS_DIR in the launcher bullet where lp/facelift had added the install bullet above it | two lanes edited neighbouring lines of section 2; the merged section carries the install bullet and the three-variable launcher bullet | section 2 | none |
