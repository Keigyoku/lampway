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

Known-red reconciliation removes only exact identities with affirmative current PASS receipts; failed, skipped and
uncollected identities remain. An empty baseline strengthens the gate and does not forgive other failures. Issue #11's
FDCA whole-client receipt affirmatively passes all 122 former entries while retaining its 38 other failure/error identities.

Expiring synthetic credentials are minted when a test executes, not at collection: the native suite can outlast a fixture
credential's lifetime. Expiry/rotation controls keep their explicit clocks and production refusals.

After interface message changes, run the canonical `make i18n_update` before publication and full client verification.
Keep the ignored generated `mixar.pot` available for currentness checks, synchronize tracked language catalogs with the
canonical extractor/updater, preserve retained translations and placeholders, and leave new messages with their documented
English fallback until translated. Removing the generated template to turn a required check into a skip is not verification.

The site-link gate admits the offline Blender corpus's exact recorded attribution URLs only in its packaged manifest and
NOTICE. It preserves the global host list and rejects runtime reuse, changed pins/versions/queries, lookalike hosts and extra
URLs on an allowed line. These static references grant no runtime retrieval or egress route.

Mode 1 integrated acceptance distinguishes a turn typed in the real pane from one submitted by the island. Preserve the
existing island-origin checks and also exercise island steer/Stop on an in-flight pane-origin turn, Blender undo after a
pane-origin tool mutation, opening the filed old chat through the production History operators, and reopening a native file
saved before the pane's `/new` while both app and server were absent. Use the pinned native pane and a synthetic loopback
model with real Blender execution; never inject turn or view frames to manufacture acceptance. Retain the saved-file hash,
native pane/backend identities, old transcript/media/checkpoints, production acknowledgements and exact-owned cleanup.
Keep every existing assertion and deadline. A fresh synthetic client keyring proves signed-out reopen followed by explicit
reconnection, not cached-login automatic reconnect; preserve the native registry, Hermes home and client profile/History.
Static syntax/assertion-preservation checks and planted invalid assertion fixtures establish only that those guards can
fire. They are not built-app RED/GREEN: each new case remains NOT RUN until executed on the matching published build.

Offline harness qualification retains child PID/start identities during each native request and through early parent exit.
Private session membership can identify reparented fixture children; cleanup signals only verified owned identities and records
its result even on failure. A vanished native parent or an empty final ancestry snapshot cannot establish successful cleanup.
Keep causal early-exit and identity-reuse controls beside the production QA driver, and qualify their in-process scope.
The standalone offline driver adopts orphaned descendants with a process-local subreaper and waits only for recorded,
same-start, adopted zombies; asyncio retains its direct child. A reused PID, a live child or another parent's zombie is
never reaped by this path. Model-free policy qualification uses native session-scoped MCP call/list requests with the
original twenty-second response bound, retaining every baseline and exclusion assertion. Synthetic user plugins are explicitly
enabled in their original fixture config; actual native initialization is required before their exclusion is credited.
Record native first-start config/cache changes separately, require original auth/persona preservation, and compare restricted
execution with the warmed native baseline without claiming cold-byte preservation.
Current-session native completion and the first MCP call share the original twenty-second deadline. Expired writes,
stdin backpressure and reply notifications consume that same budget; discovery/progress alone never releases a call.
Portable controls import the actual QA module by repository-relative path and refuse process/socket/signal operations.
Positive ACP mocks emit the witnessed native completion frame. Their fixed driver-budget clock leaves real wait timers
intact, and exact deadline assertions cover every drain/reply plus completion read. Retain method, no-model, session-ID,
policy and cleanup assertions. Historical artifacts and native baselines remain separate receipts.
Native MCP extension catalogues use the pinned nested result payload and explicit resolved session admission. Blocked
inherited configuration metadata remains in the evidence; it is not an enabled route. Require exactly one enabled
canonical connector in ready state; refuse missing/malformed admission, unresolved state and duplicate identities.
Preserve foreign/alias call refusals and native fixture noninitialization assertions independently of catalogue display.
Restart qualification fences notifications before update. Only valid fresh current-session progress identifies an observed
restart; its fresh completion plus update and next call share the original twenty-second budget. A filtered no-op can omit
completion: require one current resolved catalogue with exact canonical ready admission instead, never historical
completion. Initializing/malformed catalogues fail closed. Record observed native 1.0.46 ordering and public 1.0.45 source
corroboration separately from repaired actual execution.
Native pane qualification exercises production candidate-path lookup with owned executable links and checks exact artifact,
namespace and installed-helper hashes before herdr starts. Pure path-contract controls refuse process, socket, signal and
launcher seams; retain malformed-mapping and changed-hash failures without substituting a tuple for the production mapping.

B5 launch disclosure tests use synthetic status and recording launch seams. Downstream launch fixtures may seed an explicit
minimal prior human acknowledgement; they never disable the production admission guard. Keep fresh-first-launch, agent nonce,
malformed retained-file and independent-store update controls separate. A skipif alias is not a pytest marker: select exact
synthetic node IDs when native execution is prohibited, and preserve accidentally broader receipts with their actual scope.
An imported downstream fixture does not import its defining module's autouse fixtures. Each consumer declares retained
disclosure explicitly; mixed modules use a non-autouse dependency only on post-disclosure cases, leaving fresh worker and
first-launch refusal cases unseeded. Preserve the original test bodies, assertions and time limits.

The owned native TUI extension always runs source-hash refusal and normal-copy controls. Its pure TypeScript compiler and
controller checks require the normally installed pinned engine dependencies and Node, selected explicitly by
`LAMPWAY_TEST_ENGINE_TUI_COMPAT=1`. Missing prerequisites fail when selected. Final matching-build and whole-client proof
select these checks; a default environment's prerequisite skips remain NOT RUN. Typechecking copies the untouched pin,
uses installed dependencies without emitting a bundle and refuses child processes, network and signals inside the compiler.
Compiler/controller prerequisites use the normal engine resolver's exact destination, including verified release-tag or
pin-SHA builds and `LAMPWAY_ENGINES_DIR`. The installed `engine.json` must match the resolved normal pin/route record;
never guess another directory or accept a foreign manifest when selected prerequisites are absent.
History display controls distinguish native full display lineage from model-context history, forbid repainting on initial
and same-revision info/resume updates, and retain the original late-reply/session/busy/refusal/acknowledgement checks.
Successive external USER turns refresh only on strictly newer native revisions while idle; intermediate markers behind an
accepted snapshot stay quiet. Compacted native DISPLAY and frontend notices remain visible. Frontend provenance must
survive the actual native timestamp clone without entering JSON. Preserved notices keep their own order/content as a suffix;
no role or text heuristic identifies transient rows. Exercise actual patched factory recreation between events, latest
callback/busy state on pending snapshots, independent gateway admission, SID changes and real reconnect invalidation.
Holding one controller instance throughout a pure test cannot qualify native render lifetime.

## Test

```bash
python -m pytest -q                       # every standalone suite in pytest.ini's testpaths
python -m pytest -q tests/lampway         # the fork gates
python -m pytest -q tests/rail            # the rail, including its self-test and the check of this repository
LAMPWAY_BIN=build/<env>/bin/mixar python -m pytest -q tests/lampway_tools
```

The standalone suite has failures that predate the rail; measure a change against the integration branch's own run on the
same commit rather than against zero.

The real pane-origin and disconnected saved-file/History cases run in
`tests/lampway_tools/test_agent_modes_integrated_live.py::test_real_blender_roundtrip_through_real_hermes_and_herdr`, using
`tests/qa/agent_modes_integrated_client.py` inside Blender. Supply `LAMPWAY_BIN` for the matching normal build and a fresh
outside-repository `LAMPWAY_INTEGRATION_ARTIFACTS` directory; retain XML, logs and actual native receipts. The FDCA local
receipt in issue #11 passes these added cases with a matching normal build in synthetic-login scope. Later source changes
still require their own qualification; static planted checks never close native acceptance.

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
| 2026-10-10 | genuine pane-origin and disconnected old-file acceptance | captain requested the unfinished PR4 built-app proofs | idle pane mirroring and island-origin controls plus archive inspection did not prove pane-origin steer/Stop/undo, History opening or reopening a pre-new file after app/server absence | preserve original cases and bounds; add real native-origin controls, production History operators and durable saved-file reconciliation; qualify explicit-login flow separately | static syntax, preserved assertions and four planted assertion failures only; actual matching built-app acceptance NOT RUN |
| 2026-10-10 | early native ACP failure retains owned cleanup | read-only Grok proof-driver review and causal early-exit RED | late ancestry snapshots lost reparented MCP children, and the environment attack used a different helper path | retain private-session PID/start identities and exact cleanup through failure; attack the actual canonical helper | three in-process controls pass and 53 boundary/naming/readiness checks pass; native Grok CI remains required |
| 2026-10-10 | model-free native MCP fixtures and exact adopted-child reaping | failed native Grok CI and process-local denied-network reproduction | blocked model retries stalled policy proof, orphan zombies outlived the parent, and default-disabled plugins could not establish discovery | keep native session MCP assertions and response bounds, exact adopted zombie waits and explicitly enabled toy-plugin baselines | retained native timeout, direct-call, plugin initialization and cold-cache failure; 63 focused checks pass; repaired full native CI remains unverified |

| 2026-10-10 | distinguish synthetic notice checks from native herdr | B5 verification and owned-process discipline | a skipif alias was incorrectly supplied as -m exclusion and a broader 23-pass run included real herdr | test body: exact synthetic node selection and honestly qualified receipts; no unsupported all-reaped claim | retained mixed-scope 23-pass evidence; fixture cleanup calls documented without PID identity proof |

| 2026-10-10 | inherited downstream fixtures retain explicit disclosure | frozen 40447655 full suite: 25 NoticeRequired failures | imported island/connector/card fixtures lacked their defining module's autouse disclosure record | test body: explicit consumer fixture import, non-autouse dependency only on positive mixed-module cases, fresh refusals unchanged | full frozen causal RED receipt and exact 25 focused recheck; original test body AST preservation retained |

| 2026-10-10 | production Grok path lookup reaches native QA | six causal mapping/hash failures in guarded scratch control | a tuple-shaped candidate mock bypassed the real consumer and hid key iteration as launch paths | offline QA body: actual owned PATH lookup, exact prelaunch hashes and process-refusing malformed-map controls; dedicated workflow watches and runs consumer tests | six causal REDs retained; ten path controls and 73 focused regressions pass; no native or account acceptance claimed |
| 2026-10-10 | session-bound native MCP completion and bounded writes | two native CI baseline errors during initialization, nine portable failures and two missing-completion mock failures | first calls raced the native pool; per-line waits and unbounded drain did not enforce one budget | offline QA body: native current-session completion plus first call share twenty seconds; bounded write/read; exact expanded mock deadline coverage and original method/policy assertions retained | 86 focused checks pass; both actual offline baselines pass with exact owned cleanup, without reproducing the historical race or qualifying restricted/full CI execution |
| 2026-10-10 | pinned terminal compiler and race qualification | native Undo failures and compiler test copying an already patched engine | default fork environments lacked compiler prerequisites, and rebuilt source would fail the original hash guard | TUI qualification paragraph: unconditional copy/refusal controls; explicit required final-run opt-in, missing prerequisites fail, untouched pin input and no-emission/effect guards | explicit focused packet passes 113 tests without skips; real terminal and matching full-client acceptance remain separate |
| 2026-10-10 | compacted display and frontend output controls | current native projection/controller causal RED and duplicate invalidation failure | model context was mistaken for display; normal info repainted; repeated Undo could fetch twice | history paragraph: full native display, ordinary-info refusal, cloned nonserialized provenance, bounded notice suffix and preserved race/ack checks | baseline two causal failures; candidate marker and duplicate failures retained; nine scratch controls pass |
| 2026-10-10 | successive native external USER display controls | actual pinned TUI external-user failure and real controller RED | ordinary-info prohibition also suppressed genuinely newer transcript revisions | history paragraph: preserve initial/same/intermediate quiet controls, mirror three successive external turns only when idle, retain compressed DISPLAY and cloned notice suffix | causal RED one failure/one pass; six existing and new compatibility checks pass without skips; matching native rerun remains required |
| 2026-10-10 | native extension catalogue admission | exact 9af native CI and native-faithful positive mock RED | a flat consumer discarded the extension payload and treated blocked configuration metadata as active routes | offline QA paragraph: exact nested envelope, resolved boolean session admission, ready canonical route and independent foreign side-effect checks | baseline mock PASS/restricted causal RED; 124 focused checks PASS; repaired native restricted/CI remains NOT RUN |
| 2026-10-10 | native MCP hot-reload completion versus filtered no-op | exact native 1.0.46 loopback baseline failure and eight controlled ordering REDs | update acknowledgement preceded handshake, while filtered no-op updates cannot emit fresh completion | offline QA paragraph: pre-update current-session fence, fresh restart completion, or one current ready no-op catalogue; shared twenty-second budget, no sleep or retry | original ten readiness controls preserved with seventeen new pure reload controls; repaired actual native/CI remains NOT RUN |
| 2026-10-10 | gateway-owned native history controller lifetime | b1 native compression still hides later USER rows and causal factory-recreation RED | native React renders recreated the handler and discarded its revision baseline | history paragraph: preserve controller state per gateway owner with fresh callbacks, isolate independent gateways and real resets, retain no transcript | actual compressed-history failures and causal recreated-factory RED retained; unchanged rebuilt terminal qualification remains required |
| 2026-10-11 | normal engine prerequisites and affirmative baseline reconciliation | issue #11 P4-T02/T03 | tag-only test paths rejected valid SHA builds and 122 passing identities remained in the baseline | compiler prerequisites use the normal resolved manifest; baseline entries need exact PASS receipts, preserving every other failure; qualify completed FDCA integrated native cases by their scope | causal tagless RED; 45 focused passes; verified archive and all 122 original baseline identities pass again in cloud; whole-client remains RED |
