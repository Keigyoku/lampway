<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The agent rail

Lampway is built mostly by AI agents working in parallel lanes. The rail is what keeps the instructions those agents read
true to the code they describe. It has two halves, named after the framework it comes from, and one tool that holds both.

## The two halves

**DOE: Directive, Orchestration, Execution.** Instructions are layered: *directives* are human-readable procedures (here, the
canonical skills under `rail/skills/`), the *orchestrator* is the agent deciding what to run and in what order, and *execution*
is deterministic code (Lampway's tools and scripts). Judgement goes up, into the directive and the agent; determinism goes down,
into the code. The directives self-anneal: when a procedure turns out wrong, or a run teaches something worth keeping, the agent
that finds it fixes the procedure and records the fix in the procedure's own `## Anneal log`, in the same change.

**DOX: AGENTS.md as binding contracts.** Every `AGENTS.md` is the binding contract for the files below it. Before editing a file,
an agent reads every `AGENTS.md` on the way from the repository root down to it; the closest one controls local detail, and none
may weaken a rule above it. After a change, the agent updates the nearest `AGENTS.md` whose contract changed and refreshes the
index in its parent. Claude Code reads `CLAUDE.md` rather than `AGENTS.md`, so every `AGENTS.md` has a `CLAUDE.md` beside it that
holds exactly one line, `@AGENTS.md`, which imports it.

Where the names come from: the Agentic-Workflows wiki defines DOE as "Directive, Orchestration, Execution", Nick Saraev's
three-layer framework, and DOX as "the binding-contract protocol layered on this AGENTS.md tree" (from the agent0ai/dox
project). Lampway's sister projects adopted them first: Titan as its captain's decisions D88 and D89 ("adopt the DOE half of the
DOExDOX rail ... directives with anneal frontmatter, self-annealing logs kept by the crew that lands the change in the same
commit, auto-maintain drift gate, dox-closeout at every tag") and its ADR 0034; Vellum through its root `AGENTS.md`'s Child
DOX Index and its guard battery.

## What is where

| path | what it is |
|---|---|
| `AGENTS.md` (root) | the laws, the repository map, the Skills table, the Child DOX Index, the DOX closeout table |
| `<subsystem>/AGENTS.md` | a subsystem's invariants, its test commands and its owner |
| `CLAUDE.md` (beside each) | exactly `@AGENTS.md` |
| `rail/skills/<name>/SKILL.md` | the canonical procedures (and any files beside them) |
| `.agents/skills/`, `.claude/skills/` | generated full copies for the agent harnesses, with a manifest; never edited by hand |
| `rail/catalog.json` | the adoption baseline, the triggers that bind a script to the procedure that documents it, the exemptions |
| `rail/rail.py` | the tool: `check`, `sync`, `selftest`, `closeout`, `codes` |

## The rule

From the adoption commit on, every commit is judged on its own, and so is the uncommitted worktree:

1. An `AGENTS.md` or canonical skill that changes **appends a row** to its Anneal log, leaves every earlier row exactly as it was,
   and **changes its body**. A body change with no row is an unreceipted change; a row with no body change is a receipt for nothing.
2. A **trigger** (a file the catalog binds to a rail) that changes owes that rail a row and a body change in the same commit. The
   triggers are the rail's own code, the pre-publish gate and its CI, the build, launch and sync scripts, and the test
   configuration: files whose procedure a skill documents step by step.
3. A rail is removed only by **moving** it: a new rail in the same commit carries all its rows and appends its own.
4. At a **merge**, a file equal to one parent's version is inherited, and so is a clean three-way combination of two parents'
   bodies; every parent's rows must survive in order, and only what the merge itself wrote owes a receipt. Two lanes that both
   appended a row produce a conflict in the table; keep both rows, sorted by date.
5. Work merged in from a branch that had not yet merged the rail is inherited and **listed** (`inherited_pre_adoption` in the
   check's output), not judged: the rule binds the commits that could see it. This is the captain's ruling (2026-10-06), and
   its cost is stated rather than hidden: a branch forked before the rail's baseline can bring an unreceipted change to a rail
   or a trigger in through a merge, and the check will name it in that list without failing. Once every lane has merged the
   integration branch past the baseline, its later commits descend from the baseline and are judged one by one.
6. A **generated document** named in the catalog's `generated` list (the tool reference, rendered from the live registry) must
   pass its generator's own `--check`. That is how tool knowledge is held: no skill row is owed when a tool is added, but a
   tool added without regenerating its page fails the check. A generator that cannot run is a red check, never a skip.

An anneal row has six cells: `date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate`, an ISO date
first, dates in order, and nothing but the table in the section.

The check also holds the shape of the tree: every `AGENTS.md` carries the gated anneal frontmatter and its required sections,
every `CLAUDE.md` is exactly the import line (compared with the literal, never with its siblings, so a uniform drift cannot pass),
the Skills table and the Child DOX Index match what is on disk in both directions, the catalog names only files that exist, the
generated copies match their sources byte for byte, nothing generated exists without a source, and nothing is a symlink.

## Using it

```bash
python3 rail/rail.py              # what the rail holds, and the next commands
python3 rail/rail.py sync         # after editing a skill: regenerate the copies
python3 rail/rail.py check        # the gate; exit 1 lists each finding with its code
python3 rail/rail.py check --quick   # what the pre-push hook runs
python3 rail/rail.py codes        # what each finding code means
python3 rail/rail.py selftest     # prove each code fires on a planted violation
python3 rail/rail.py closeout --tag v0.1.0   # before a tag: the root AGENTS.md row for that tag
```

The check runs in two places. The `pre-push` hook runs the **quick** form, `rail.py check --quick`, after the pre-publish gate:
the tree's shape (stubs, indexes, frontmatter, registrations) and only the commits no remote-tracking ref holds yet, so a push
costs a fraction of a second however long the history grows. CI runs the **full** form on every push and pull request
(`.github/workflows/rail.yml`): the self-test, every commit since the baseline, the generated documents (with the server's
dependencies installed), and the rail's tests. The full check needs the history back to the baseline; a shallow clone is a red
check, not a skipped one.

Repairing a finding: run `rail.py codes` for its meaning. Most repairs are one of three: append the missing row and make the
body change in an amend of your own unpushed commit; run `sync` and commit the copies; or fix the index the finding names. A
finding that only another lane can fix becomes an **exemption** in the catalog with its reason; an exemption that stops
matching a finding is itself a finding, so exemptions can only shrink.

## Why it is built this way

Each choice answers a failure the sister projects recorded:

- **An assertion that cannot fail is not an assertion.** The self-test builds a scratch repository, plants one violation for every
  finding code, and fails if any goes unseen, if a clean control is flagged, or if a code exists with no plant. A test also
  switches the rule off and checks that the self-test then fails.
- **Enumeration is not a gate.** A rule enforced by a list is enforced by whoever last read the list. So the indexes are compared
  with the tree both ways, and the codes with the plants.
- **A count or a list restated in prose goes stale silently** (Titan rewrote its smoke-row headers three times before it stopped
  counting in prose). The skills point at the file that owns a list instead of copying it.
- **A merge of two lanes cannot satisfy an append-only prefix rule** (Titan ADR 0023 amendment A2): both lanes appended rows to the
  same table. The rule keeps the strict prefix for ordinary commits and accepts, at a merge, exactly what both parents brought.
- **A stub that points elsewhere may not be followed**: Vellum measured that whether a harness loads an instruction file is a
  property of the harness. The generated skill copies are therefore full copies, not pointers.
- **A symlink is a one-line text file on Windows**, so no part of the rail is a symlink (Vellum's instruction-discovery guard).
- **A baseline that moves whenever the gate is red is not a gate.** The baseline names the adoption commit; moving it is the
  captain's decision and is recorded with its reason and its cost.

## What it does not do

It cannot tell whether a body change is a good one, or whether a fact was verified before it was written: those are review
questions. It does not judge files outside the rails and the catalog's triggers; most code changes owe the rail nothing. It does
not run the product's tests; it runs beside them.
