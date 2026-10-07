---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# tests — the client-side suites and the gates

The standalone suites run outside Blender with `bpy` mocked (the root `conftest.py`); `tests/lampway_tools/` drives the real
built binary; `tests/lampway/` holds Lampway's fork gates (hosts, brand words, native strings, shipped metadata, links, the
build script, the pre-publish gate); `tests/qa/` is upstream's GUI end-to-end harness; `tests/rail/` tests this rail. The server
has its own suite under `server/tests/`.

## Invariants

1. **RED first.** A behaviour change lands with a test that was seen to fail for the stated reason before the fix; the commit
   body carries the RED line. A compile or import error is not RED.
2. **A gate proves it can fire.** Every gate keeps a planted offender that it must catch (the brand gates' fixtures,
   `prepublish_gate.py --self-test`, `rail/selftest.py`); a gate that has never been seen to fail is not counted.
3. **Allow-lists only shrink, in plain sight.** The brand allow-list's size is pinned by `tests/lampway/brand_allowlist.ratchet`
   and every entry must still match its line; the rail's exemptions fail when they stop matching. Widening either is a
   reviewed change with its reason, never a way to turn a gate green.
4. **A skip is not a pass.** A binary-driven test without `LAMPWAY_BIN` (or a built `build/<env>/bin/mixar`) skips; a report counts
   it as not run. Tests that need the user's own assets skip with a stated reason where those are absent.
5. **No live spend, no live egress.** Paid and outbound paths are tested against fake transports; nothing in a suite calls a
   provider or the upstream service. Test data holds only known-fake identities (listed in `scripts/lampway/pii_allow.txt`).
6. **Never weaken or delete a failing test to go green.** Fix the code or raise the test as wrong, with the evidence.
7. **Test code never ships.** In-tree `tests/` directories under `src/scripts/mixar` are excluded from the install; keep test
   helpers there or here, never in a shipped module.

## Test

```bash
python -m pytest -q                       # every standalone suite in pytest.ini's testpaths
python -m pytest -q tests/lampway         # the fork gates
python -m pytest -q tests/rail            # the rail, including its self-test and the check of this repository
LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools
```

The MCP-specific binary tests accept `LAMPWAY_INSPECT_BIN` and `LAMPWAY_VIEW_BIN`, load the current source overlay in an isolated background profile, and never sync an installed app. TOON fixtures run from `tests/toon/`. `LAMPWAY_VIEW_XVFB` selects a separately extracted Xvfb for disposable cloud GUI tests: actual masked editor PNGs, repeated thumbnail/default-current stills, one visibility undo and all-view inspection history falsifiers. `LAMPWAY_MCP_ACCEPTANCE_ASSETS` names externally pinned public fixtures; `LAMPWAY_MCP_ACCEPTANCE_RECEIPTS` retains named-asset timings outside the repository. Missing binaries/displays/assets are explicit skips, never passes; no test connects to the user desktop. The GUI fixture waits for the normal connector snapshot to report the native/controller opt-in ready, with a bounded diagnostic timeout, before capturing pixels; it never enables the native gate directly or repeatedly toggles preferences.

The inspection integration fixture also verifies main-owned canonical translation and refused-import cleanup through T1 world metrics and counts, using the same isolated current-overlay profile.

The isolated onboarding GUI fixture defaults to software GL. `LAMPWAY_VIEW_SOFTWARE_GL=0` requests hardware: it removes inherited desktop display/software flags, creates a fresh display, records the requested mode and actual renderer, and refuses software fallback. Hardware acceptance requires a measured hardware renderer; a cloud llvmpipe refusal is a negative control, not a GPU pass.

Checkpoint tests measure full document writes across an armed read turn: certified complete scene-summary/OBSERVE wrappers write zero copies; forged read names, arbitrary scripts and admitted typed commits capture once before mutation. Keep pre-turn transcript/new-session/bookmark restoration, scene-renaming, reverted-branch pruning and existing tip/safety/undo regressions. Typed commit admission failures and idempotent replays must not capture. Every file load clears pending metadata before the restore branch while retaining the restored session. Source-structure and fake-`bpy` proofs are reported separately from an isolated GUI mock-provider lifecycle.

Prepublish tests plant both content identifiers and invalid authored commit identities: findings must block and must not echo personal values or email domains.

Historical failures retain source attribution, but the captain now requires zero failures/errors across inherited and new cases. A baseline-relative GREEN is not completion. Remove baseline rows only after exact affirmative passing evidence; keep unresolved input and cross-crew dependencies explicit. Source-location or mock-fixture repairs preserve the original behavioral assertions and corruption plants.

## Owner

Each lane owns the tests of its contracts; the fork gates in `tests/lampway` and the rail's tests change only with the gate they
pin. A test's intent is changed only with the captain's word when it encodes one of his rulings.

Native compile-definition regressions pin the target, option scope, creation order and concrete guarded consumers. Retain missing, wrong-target, public, unconditional and before-target corruption controls. Report source checks separately from actual ON/OFF compile commands and physical menu/palette acceptance.

Scanner regression fixtures remain self-contained when the security guard is shared across lanes. Preserve byte-exact reproductions with immutable source provenance, not dependencies on unrelated native tests; retain every planted security assertion.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the test discipline lived in the gates' docstrings and the lanes' reports | seven invariants (RED first, plants, shrinking allow-lists, skips, no live spend, no weakening, no shipped tests) and the suite commands | captain ruling, 2026-10-05 |
| 2026-10-07 | MCP wrapper contract receipt | captain: scoped MCP wrapper and migration | new transport, observation, schemas and offline data needed reproducible ownership and evidence | document the scoped implementation, generated checks and explicit limits above | scoped contract evidence in docs/reports/mcp-wrapper-migration.md |
| 2026-10-07 | complete MCP acceptance after re-audit | captain: finish original C0-C2 and T1-T3 scope | skipped geometry and isolated-only evidence left acceptance gaps | document metric shared interfaces, conservative budgets, source-pin backlinks and cloud GUI falsifiers | measured contract checklist and retained receipts |

| 2026-10-07 | MCP main integration acceptance | captain: rebase and redo affected contracts | prior-head proofs did not cover merged lease, translation and import-cleanup interfaces | verify current overlay and exact successor head; baseline main and native receipts remain distinct | MCP reconciliation report |

| 2026-10-07 | GUI opt-in startup readiness | exact-head acceptance reached native capture before the connector timer synchronized the saved opt-in | a fixed six-second startup delay raced deferred controller registration | await the observable native/controller snapshot once, retain pixel guards and undo/masking assertions | isolated seed-zero readiness receipt and exact-head aggregate |
| 2026-10-07 | PII diagnostic negative controls | captain: fix PR privacy exposure | public diagnostic output could reproduce the identifier being blocked | plant content and commit identifiers, assert refusal and complete personal-value redaction | prepublish ten-test pass |
| 2026-10-07 | read-turn checkpoint byte falsifiers | captain: complete issue 2 F25 | eager copies paid for reads and a naive skip could disable mutation recovery | pin certified whole scripts, forged-name mutation, once-only admitted writes and retained restore metadata; distinguish mocked proof from GUI lifecycle | checkpoint and typed-commit suites |

| 2026-10-07 | measured hardware GUI mode | issue 2 requires both software and GPU screenshots | the fixture forced software GL and could label fallback as hardware | expose an explicit isolated mode and reject measured software renderers; retain default software coverage | nine mode checks and real software/fallback GUI receipts |
| 2026-10-07 | inherited failure closure | captain: no red checks going forward | stale source pins and cross-suite mocks hid real incomplete inputs while baselines normalized failures | preserve security/behavior plants, update actual source and active mock identities, and require exact passing evidence for every inherited row | authoritative subtitle source mapping and complete122-ID ownership |
| 2026-10-07 | target-owned fork compile definitions | captain: physical AC34 wrong native operators | source-only guarded strings passed while consumers compiled the upstream branch | test concrete target ownership and planted option/scope regressions; require build and physical receipts | editor macro compilation contracts |

| 2026-10-07 | portable matrix scanner reproduction | PR4 publication dependency | scanner controls read an unrelated native-topology test absent from its lane | retain the exact reproduction as a local literal with immutable commit/blob provenance and unchanged security assertions | self-contained20scanner controls |
