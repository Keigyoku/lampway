---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# rail — the DOE x DOX rail

The canonical skills (`skills/<name>/SKILL.md`), the catalog (`catalog.json`: the adoption baseline, the triggers that bind a
script to its procedure, the exemptions), and the tooling that holds them: `rail.py` (the CLI), `railcore.py` (the tree, the
history, the registrations and the verdict), `anneal.py` (the anneal rule as a pure function over snapshots), `selftest.py`
(one planted violation per finding code). How it works, for people: [`docs/rail.md`](../docs/rail.md); maintaining it: the
`lampway-rail` skill.

## Invariants

1. **Stdlib only, no network, no writes outside `sync`.** The check runs anywhere Python 3.11+ and git run; it reads the tree and
   the history and writes nothing; `selftest` works in a temporary directory (it honours `TMPDIR`).
2. **Every finding code has a plant.** `selftest.py` fails when a code in `railcore.CODES` has no planted violation, when a plant
   is not caught, or when a control (a receipted edit, a receipted trigger, a move, a clean two-lane merge) is reported. A new
   code lands with its plant in the same commit.
3. **The baseline never moves to make a check green.** It names the adoption commit; moving it is the captain's call and is
   recorded in `catalog.json` with its reason and what it stops re-checking.
4. **Exemptions only shrink.** Each names a code, a path and a reason a reviewer can check, and an exemption that matches no
   finding is itself a finding.
5. **Generated copies are full copies, never stubs.** `.agents/skills/` and `.claude/skills/` carry the canonical bytes plus a
   manifest; a harness never has to follow a pointer to reach a procedure. Stubs are for `CLAUDE.md` only, and those are exactly
   `@AGENTS.md`.
6. **No symlinks** anywhere the rail reads or writes: a git symlink checks out as a one-line text file on Windows.
7. **Two forms of the check.** `check --quick` (the pre-push hook) judges the tree's shape and only the commits no remote-tracking
   ref holds yet; it skips the worktree and the generated documents. The full `check` (CI) judges every commit since the
   baseline, the worktree, and runs each catalog `generated` row's own `--check`, red when the generator cannot run.

## Test

```bash
python3 rail/rail.py selftest
python3 rail/rail.py check
python -m pytest -q tests/rail
```

The generated inspection schema directory is held by its own deterministic `schema.py --check` catalog row; changes to the schemas are made in the shared client/server schema source.

CI runs all three on every push and pull request (`.github/workflows/rail.yml`), with the full history so the baseline is
reachable and the server's dependencies installed for the generated documents. `.githooks/pre-push` runs `check --quick`.

## Owner

The rail lane (`lp/rail`) built it; after it lands, the integration lane owns it. Changing a finding code, the anneal rule or the
baseline policy is doctrine: the captain's word.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway, examples of it are in Vellum and Titan" | no rail: procedures could drift from the code they describe, and nothing tied an AGENTS.md edit to a receipt | the check, sync, self-test and closeout; seventeen codes each with its plant; merge inheritance by three-way combination | captain ruling, 2026-10-05 |
| 2026-10-06 | quick form and generated-doc leg | captain: "Those recs are fine" | a full history walk is the wrong cost for every push, and nothing held the generated tool docs | `--quick` for the hook (unpushed commits only), RAIL-018 for the catalog's generated documents, each with its plant and tests | captain ruling, 2026-10-06 |
| 2026-10-07 | MCP wrapper contract receipt | captain: scoped MCP wrapper and migration | new transport, observation, schemas and offline data needed reproducible ownership and evidence | document the scoped implementation, generated checks and explicit limits above | scoped contract evidence in docs/reports/mcp-wrapper-migration.md |
