---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
name: lampway-rail
description: "Change, add, move or anneal any AGENTS.md, CLAUDE.md, canonical skill or catalog trigger in Lampway, or repair a `rail.py check` finding: the DOE x DOX rule, the anneal row and body owed in the same commit, sync, exemptions, merges and the DOX closeout."
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# The DOE x DOX rail

**DOE** is Directive, Orchestration, Execution: directives are human-readable procedures, an agent orchestrates (chooses what
runs and in what order), and deterministic scripts execute. **DOX** is the binding-contract protocol over the `AGENTS.md` tree:
each `AGENTS.md` is the binding contract for its subtree; read every one on the route to a file before editing it, and update the
nearest owner after a change. In Lampway the directives are the canonical skills, the execution layer is the tools and scripts,
and `rail/rail.py` is what makes both rules hold. The long form, for people: [`docs/rail.md`](../../../docs/rail.md).

## What lives where

- `AGENTS.md` at the root and in each subsystem that has its own rules; beside each one a `CLAUDE.md` that is exactly the line
  `@AGENTS.md` (Claude Code reads `CLAUDE.md`; every other harness reads `AGENTS.md`).
- `rail/skills/<name>/SKILL.md`: the canonical skills, the one place a procedure is written. Files beside a `SKILL.md` are part
  of that skill.
- `.agents/skills/` and `.claude/skills/`: generated full copies plus a manifest (`LAMPWAY-RAIL.generated.json`). Never edited.
- `rail/catalog.json`: the adoption `baseline`, the `triggers` (a file whose change owes a named rail an anneal row and a body
  change), and the `exemptions` (recorded findings, each with its reason; they may only shrink).

## The rule (one commit at a time, from the baseline on)

1. A rail (an `AGENTS.md` or a canonical skill) that changes appends at least one row to its `## Anneal log`, leaves every
   earlier row exactly as it was, and changes its body. A body change without a row is unreceipted; a row without a body change
   is a receipt for nothing.
2. A trigger that changes owes its owner rail a row AND a body change in the same commit.
3. A rail is deleted only by moving it: a rail new in the same commit carries its rows unchanged and appends its own.
4. At a merge, whatever equals one parent's version, or is a clean three-way combination of the two parents' bodies, is
   inherited and owes nothing; every parent's rows survive in their order; a merge-owned row goes after the inherited ones.
   Resolving a conflict in an anneal table: keep both sides' rows, sorted by date.
5. The uncommitted worktree is judged the same way, so `check` is red until an edit is receipted.

A row: `| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |`, six non-empty cells, ISO
dates in order, and nothing but the table inside the Anneal log section. Record what happened and what changed, at its source.

## Commands

```bash
python3 rail/rail.py              # status and next commands
python3 rail/rail.py sync         # regenerate .agents/skills and .claude/skills from rail/skills
python3 rail/rail.py check        # the gate: inventory, registrations, and the rule over every commit since the baseline
python3 rail/rail.py selftest     # plant one violation per finding code in a scratch repository; prove each one fires
python3 rail/rail.py codes        # what each RAIL-0xx code means
python3 rail/rail.py closeout --tag <tag>   # the root rail's DOX closeout row for a planned tag
python -m pytest -q tests/rail    # the rail's own tests, including the self-test and the check of this repository
```

## Doing the common things

- **Edit a rail or skill:** change the body, append a row, `sync` (for a skill), `check`, commit everything together.
- **Add a nested rail:** write `<dir>/AGENTS.md` (frontmatter, `## Invariants`, `## Test`, `## Owner`, `## Anneal log`) and
  `<dir>/CLAUDE.md` = `@AGENTS.md`; add its row to the root Child DOX Index and append a root anneal row, in one commit.
- **Add a skill:** `rail/skills/<name>/SKILL.md` with `name` equal to the directory, a trigger `description`, the anneal fields and
  `verification-mode`; `sync`; commit the canonical file and its generated copies together.
- **Bind a script to a procedure:** add a `triggers` row in `rail/catalog.json` naming the owner rail. From then on that script
  cannot change without its procedure. Bind only scripts whose procedure the owner actually documents.
- **A finding you cannot fix in your lane:** record it as an exemption `{code, path, reason}` in the catalog, with the reason a
  reviewer can check; the check fails when an exemption stops matching, so it must be removed when the cause is fixed.
- **Doctrine** (what a rule says, not a fact about the tree) is the captain's: propose the exact text in your report or an
  adjacent `<stem>.annealing-proposal.md`; never rewrite doctrine as a "factual repair".

## What the rail refuses to do

It never moves the baseline to make a red check green; a baseline move is the captain's call and is recorded in the catalog with
its reason and cost (`baseline_reason`). It never edits generated copies by hand. It never treats a skipped check as a pass.

Provenance: the DOE and DOX definitions are the Agentic-Workflows-Wiki's (`AGENTS.md` §DOX framework, citing Saraev's DOE and
agent0ai/dox), adopted by Titan as captain decisions D88/D89 and Titan ADR 0034, with Titan ADR 0023 A2 for merges; Vellum's
`scripts/check-agent-instruction-discovery.sh` (stubs pinned against the literal, no symlinks) and `scripts/run-guards.sh`
(manifest checked against the tree both ways; one id per check).

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | Lampway had no AGENTS.md tree, no canonical skills and no rule tying a procedure to the code it describes | `rail/rail.py` with sync, check, selftest and closeout; the per-commit anneal rule with merge inheritance; seventeen finding codes, each planted and caught | captain ruling, 2026-10-05 |
