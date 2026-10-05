<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contributing

Lampway is free software under GPL-3.0-or-later. Contributions are welcome through pull requests on <https://github.com/Keigyoku/lampway>.

**Inbound = outbound.** By submitting a contribution you license it under GPL-3.0-or-later, the licence of the project. There is no CLA. A `Signed-off-by:` line is welcome and not required.

## Before opening an issue

Check whether the problem is in this repository, then use <https://github.com/Keigyoku/lampway/issues> with a reproduction and the Lampway version.

Do not post security vulnerabilities (follow [SECURITY.md](SECURITY.md)), credentials, API keys, tokens, logs containing secrets, or private scene data.

## Development rules

- Durable source changes go under `src/` (Python modules in `src/scripts/mixar/modules/`, native code in `src/source/blender/`) and `server/`.
- Keep reusable logic in the relevant module or `common`.
- Use the build scripts (see [BUILD-LAMPWAY.md](BUILD-LAMPWAY.md)) instead of building generated trees directly.
- Keep environment variables in `.env` locally and never commit `.env`.
- Write the failing test first, and keep user-visible text on the brand constants in `src/scripts/mixar/config/brand.py`; `tests/lampway` enforces the brand rules.

## Before you push: the pre-publish gate

`scripts/lampway/prepublish_gate.py` blocks personal emails, home paths, account ids, tokens, signed URLs and media metadata. The `pre-push` hook runs it on your new commits and CI runs it
on every push (`.github/workflows/pii-gate.yml`). Turn the hooks on once per clone: `git config core.hooksPath .githooks` (the same setting `scripts/unix/init.sh` makes). Use your GitHub
noreply address as the commit email. A known-fake test value goes in `scripts/lampway/pii_allow.txt` with a reason. Check the tree yourself with `python3 scripts/lampway/prepublish_gate.py --tree .`.

## Branch Naming

Branch off the current integration branch; releases are tagged.

| Prefix | Use for | Example |
|---|---|---|
| `feature/**` | A new feature or capability | `feature/procedural-material-nodes` |
| `bugfix/**` | A non-urgent bug found in development or testing | `bugfix/moodboard-video-playback` |
| `hotfix/**` | An urgent production issue that must ship quickly | `hotfix/update-installer-signature` |
| `refactor/**` | Restructuring without changing behaviour | `refactor/paint-layer-stack` |
| `chore/**` | Dependencies, configuration, tooling | `chore/bump-upstream-blender` |
| `test/**` | Tests only, no feature or fix | `test/job-queue-download` |
| `release/**` | Release preparation and version bumps | `release/v3.4.0` |
| `experiment/**` | A proof of concept that may never merge | `experiment/gpu-brush-cache` |
| `task/**` | Anything that fits none of the above | `task/update-api-docs` |
| `claude/**` | Work created or assisted by Claude | `claude/refactor-export-agent` |

- Lowercase kebab-case, short and descriptive.
- Use the most specific prefix — `bugfix/`, not `task/`, for a bug fix.
- No ticket IDs, no personal names, nothing vague like `task/changes` or `bugfix/fix`.

## License Requirements

Every new file must carry SPDX license metadata.

For source files, add an inline SPDX header. For binary assets or formats that cannot carry comments, add an entry to `REUSE.toml`.

### How SPDX Headers Get Added

Add the SPDX header to each new file yourself (see existing files for the
format). CI runs `reuse lint` on every PR and will fail the build if any file
lacks copyright or license information.

### Optional: Local Pre-Commit Hook

```bash
pip install pre-commit
pre-commit install
```

This runs the same `reuse` compliance check locally before each commit so you
catch missing headers early. It is purely a developer convenience and is not
required. Configured hooks live in `.pre-commit-config.yaml`.

### Manual Commands

```bash
# Full REUSE compliance check (same as CI)
reuse --no-multiprocessing lint
```

If `reuse lint` reports a file missing copyright or license info, add an SPDX
header to the top of the file (see existing files for the format) or record it
in `REUSE.toml`.
