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

Expiring synthetic credentials are minted when a test executes, not at collection: the native suite can outlast a fixture
credential's lifetime. Expiry/rotation controls keep their explicit clocks and production refusals.

After interface message changes, run the canonical `make i18n_update` before publication and full client verification.
Keep the ignored generated `mixar.pot` available for currentness checks, synchronize tracked language catalogs with the
canonical extractor/updater, preserve retained translations and placeholders, and leave new messages with their documented
English fallback until translated. Removing the generated template to turn a required check into a skip is not verification.

The site-link gate admits the offline Blender corpus's exact recorded attribution URLs only in its packaged manifest and
NOTICE. It preserves the global host list and rejects runtime reuse, changed pins/versions/queries, lookalike hosts and extra
URLs on an allowed line. These static references grant no runtime retrieval or egress route.

## Test

```bash
python -m pytest -q                       # every standalone suite in pytest.ini's testpaths
python -m pytest -q tests/lampway         # the fork gates
python -m pytest -q tests/rail            # the rail, including its self-test and the check of this repository
LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools
```

The standalone suite has failures that predate the rail; measure a change against the integration branch's own run on the
same commit rather than against zero.

## Owner

Each lane owns the tests of its contracts; the fork gates in `tests/lampway` and the rail's tests change only with the gate they
pin. A test's intent is changed only with the captain's word when it encodes one of his rulings.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the test discipline lived in the gates' docstrings and the lanes' reports | seven invariants (RED first, plants, shrinking allow-lists, skips, no live spend, no weakening, no shipped tests) and the suite commands | captain ruling, 2026-10-05 |
| 2026-10-08 | exact static corpus attribution | parent approved bounded PR4 provenance compatibility | ten official packaged attribution references failed the shipped-host gate | admit exact manifest/NOTICE URL literals while preserving runtime host refusals and planted path/pin/query/lookalike/extra-link controls | actual ten-reference RED and focused gate controls |
| 2026-10-08 | voice fixture lifetime follows execution | whole native client run lasted longer than the one-hour collection credential | three late voice tests failed before handshake because the valid fixture had expired | execution-time credentials; keep expiry, rotation, handshake-count and two-second controls | controlled full-run delay: three RED failures, all thirteen GREEN |
| 2026-10-08 | language catalogs follow the current interface | full-client template currentness RED; canonical fresh template found 22 new messages and 48 stale catalogs | tracked catalogs and the ignored template stayed behind the Context and profile UI strings | canonical extraction/update before publication and full client proof; retained translations and placeholders unchanged, new strings use English fallback | original template RED, 48 fresh-template catalog RED errors, canonical external GREEN; matching final full suite required |
