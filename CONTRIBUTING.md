<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contributing

Lampway is free software under GPL-3.0-or-later. Contributions are welcome through pull requests on <https://github.com/Keigyoku/lampway>.

**Inbound = outbound.** By submitting a contribution you license it under GPL-3.0-or-later, the licence of the project. There is no CLA. A `Signed-off-by:` line is welcome and not required.

## Before opening an issue

Check whether the problem is in this repository, then use <https://github.com/Keigyoku/lampway/issues> with a reproduction and the Lampway version.

Do not post security vulnerabilities (follow [SECURITY.md](SECURITY.md)), credentials, API keys, tokens, logs containing secrets, or private scene data.

## Development rules

- **Test first.** Write the failing test, watch it fail for the right reason, then write the code. Put the RED line (the failing assertion or error) in the commit body. When a guard matters, mutate the guarded line and show that a test goes red.
- Durable source changes go under `src/` (Python modules in `src/scripts/mixar/modules/`, native code in `src/source/blender/`) and `server/`. Never edit the generated `source/` or `build/` trees.
- Keep reusable logic in the relevant module or `common`. Prefer deep modules: a small interface over a lot of behaviour.
- Use the build scripts (see [BUILD-LAMPWAY.md](BUILD-LAMPWAY.md)) instead of building generated trees directly.
- Keep environment variables in `.env` locally and never commit `.env`.
- User-visible text uses the brand constants in `src/scripts/mixar/config/brand.py`; `tests/lampway` enforces the brand rules (no upstream product names in user-visible strings, only allowed hosts in links).
- **Spend and privacy laws.** No tool may confirm a spend; only the user's click does. Every outbound route goes through the egress gate and is off until the user opts in. A new provider, studio or download needs a route in `server/lampway_server/egress.py`. See [docs/privacy.md](docs/privacy.md) and [docs/spend.md](docs/spend.md).
- Never commit a key, a token, a signed URL, a personal path or a recorded session that contains one.

## The build box

Blender 5.2 needs GCC 14 and the maintainer builds inside an Ubuntu 24.04 distrobox named `lampway-build` (any Ubuntu 24.04 container or VM works). Build there, run the client tests there, and keep one engine bench per box: two builds sharing a box serialise on the same lock files. Build and launch instructions are in [BUILD-LAMPWAY.md](BUILD-LAMPWAY.md) and [docs/getting-started.md](docs/getting-started.md); `scripts/lampway/build_linux.sh --plan` prints what a run would do.

## Test commands

```bash
python -m pytest -q tests/lampway          # the fork's own contract: hosts, gate, brand, art, env, links (no Blender needed)
cd server && pytest                        # the server: no Blender, no network, no model (needs the server venv, see docs/getting-started.md)
python -m pytest -q tests/lampway_tools    # the client tools: drives the REAL built binary
```

- `tests/lampway_tools` runs inside the built application. After a change to the Python half, copy it into the install with `scripts/lampway/sync_python.sh [--bin-dir build/<env>/bin]`; the test helpers do this for you.
- Some tests need your own data and skip without it: set `LAMPWAY_PYTHON_SCIENCE` (a Python with numpy, scipy, Pillow, OpenCV) and the shelf variables the test names, and keep `TMPDIR` and `--basetemp` on a filesystem with space (a quota-limited tmpfs can fail a full run with a disk-full error that looks like a test failure).
- The root suite (`python -m pytest -q`) has pre-existing failures that are not Lampway's; compare against the failing-id list from the commit you branched from rather than expecting a clean run.
- A suite that is green on a subset can hide a red one: before you push, run the whole server suite and the whole of `tests/lampway`.
- Regenerate `docs/tools.md` after adding or changing a tool: `server/.venv/bin/python docs/gen_tools.py` (use `--check` in review).

## Before you push: the pre-publish gate

`scripts/lampway/prepublish_gate.py` blocks personal emails, home paths, account ids, tokens, signed URLs and media metadata. The `pre-push` hook runs it on your new commits and CI runs it on every push (`.github/workflows/pii-gate.yml`, plus gitleaks over the branch history).

**Turn the hooks on once per clone:**

```bash
git config core.hooksPath .githooks      # the same setting scripts/unix/init.sh makes
```

- Use your GitHub **noreply** address as the commit email, and do not add agent or co-author trailers.
- A known-fake test value goes in `scripts/lampway/pii_allow.txt`, with a reason on the same line.
- The gate also checks for the maintainer's own identifiers, but those patterns are never in the repository: locally the hook reads them from a `pii_owner.env` file in the shared git directory (`PII_OWNER_EMAIL_RE`, `PII_OWNER_USER_RE`, `PII_OWNER_PATH_RE`, one regular expression each, mode 0600), and CI reads them from the repository secrets of the same names. If you have your own identifiers to keep out, put them in the same three variables.
- Check the tree yourself: `python3 scripts/lampway/prepublish_gate.py --tree .`, a range with `--git origin/main..HEAD`, shipped media with `--media docs`, and the gate's own check with `--self-test`.
- Write `<workspace>` or `/home/user` in docs and tests, never a real path. Split a test literal that looks like a URL with userinfo or a signed URL so the gate does not read it as one.

## Lanes and integration

Work happens on `lp/*` branches, one lane per branch:

- **Integration branch.** `lp/wave5` (and its successors) is owned by the **integrator**. It merges lane branches with `--no-ff`, never rebases, runs the full suites and the gate, and never moves `main` on its own. `main` advances only after the gated integration tip is approved.
- **Lanes.** An implementer works on its own `lp/<lane>` branch from the integration branch, in its own worktree and, for client tests, its own reflink copy of the application binary (the test helper syncs Python into the binary, so lanes must not share one). Pushing is limited to your own branch: never force, never `main`, never another lane's branch.
- **Documentation lane.** `lp/docs` touches only documentation (`README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY.md`, `docs/**` except the wave reports). The wave reports in `docs/reports/` are the record of what was measured; they are not rewritten after the fact, and a wrong code fact is reported to the lane that owns the code instead of being patched in the docs.
- **Staying current.** When integration has moved, `git fetch origin && git merge origin/lp/wave5` (merge, never rebase), and merge again before you finish.
- **A wave ends** with a pushed branch, a report in `docs/reports/` and a build path for the next consumer.

Outside contributors without lane access: fork, branch off the current integration branch and open a pull request. Branch names are lowercase kebab-case with the most specific prefix (`feature/`, `bugfix/`, `refactor/`, `chore/`, `test/`, `experiment/`, `task/`); no ticket ids, no personal names, nothing vague like `task/changes`.

## Licence requirements

Every new file carries SPDX licence metadata. For source files add an inline SPDX header (see existing files for the format); for binary assets or formats that cannot carry comments, add an entry to `REUSE.toml`. CI runs `reuse lint` on every PR and fails the build if any file lacks copyright or licence information.

```bash
reuse --no-multiprocessing lint            # the same check as CI
pip install pre-commit && pre-commit install   # optional: the check before each commit (.pre-commit-config.yaml)
```

Lampway's own files carry `SPDX-FileCopyrightText: 2026 Lampway contributors` and `GPL-3.0-or-later`. Upstream files keep their upstream notices.
