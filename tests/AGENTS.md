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

Original MCP regressions verify definitive empty paint-layer summaries for non-mesh object detail, byte-identical finite view editor schemas and explicit view defaults. Plant an invented editor identifier to prove rejection before runtime, and retain the supported-but-absent editor no_area control. Isolated native Camera and view calls verify these boundaries without changing the scene/selection snapshot or enabling pixels. Focused worktree receipts do not replace final consolidated-head, named-performance, GUI-history or package verification.


Native screenshot regressions compile the actual maintained full-window readback dispatcher with controlled context/capability/failure boundaries, retain upstream OFF routing and target-definition corruption plants. Isolated operator comparisons must assert nonblack pixels after the maintained rebuild and record genuine binary/source provenance; an operator FINISHED result or working QA offscreen capture does not certify screenshot output.

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

Onboarding GUI transitions await both the handled walk step and the native
current-panel widgets with a bounded timeout. Every sampled popup must contain
one panel and one stable Back/Continue footer, including observations before
input handling and layout refresh. Record draw callbacks and actual popup
identity. Keep delayed-input, persistent stale-panel, overlap and moved-footer
controls; sampled telemetry is not proof of every frame rendered between polls.
`LAMPWAY_GUI_CLICK_DELAY` and `LAMPWAY_GUI_STALE_PANEL` inject isolated timing
and content falsifiers without changing product defaults. Historical half-CPU
failures and current measured binary provenance remain explicit.

Checkpoint tests measure full document writes across an armed read turn: certified complete scene-summary/OBSERVE wrappers write zero copies; forged read names, arbitrary scripts and admitted typed commits capture once before mutation. Keep pre-turn transcript/new-session/bookmark restoration, scene-renaming, reverted-branch pruning and existing tip/safety/undo regressions. Typed commit admission failures and idempotent replays must not capture. Every file load clears pending metadata before the restore branch while retaining the restored session. Source-structure and fake-`bpy` proofs are reported separately from an isolated GUI mock-provider lifecycle.

Prepublish tests plant both content identifiers and invalid authored commit identities: findings must block and must not echo personal values or email domains.

Historical failures retain source attribution, but the captain now requires zero failures/errors across inherited and new cases. A baseline-relative GREEN is not completion. Remove baseline rows only after exact affirmative passing evidence; keep unresolved input and cross-crew dependencies explicit. Source-location or mock-fixture repairs preserve the original behavioral assertions and corruption plants.

## Owner

Each lane owns the tests of its contracts; the fork gates in `tests/lampway` and the rail's tests change only with the gate they
pin. A test's intent is changed only with the captain's word when it encodes one of his rulings.

Native compile-definition regressions pin the target, option scope, creation order and concrete guarded consumers. Retain missing, wrong-target, public, unconditional and before-target corruption controls. Report source checks separately from actual ON/OFF compile commands and physical menu/palette acceptance.

Scanner regression fixtures remain self-contained when the security guard is shared across lanes. Preserve byte-exact reproductions with immutable source provenance, not dependencies on unrelated native tests; retain every planted security assertion.

Native bind tests distinguish source-copy error, authored node/BindPose/cluster error and imported display reconstruction. Preserve the unchanged shortest-quaternion rotation bar, including a diagonal-axis near-bar falsifier. A synthetic display-tail mechanism does not establish an owner-source cause. Native source_copy and exact Armature container controls preserve originals and refuse unsupported graphs/conventions or occupied names before copies.

Privacy regression coverage includes suffix lookalikes for every exempt email host and legacy fake domain, positive exact-host controls, and mixed-line addresses. Preserve generic and owner-specific blocking plus matrix-code and CLI redaction controls. Keep versioned prompt filename controls and use same-length reserved fake addresses for responsive layout fixtures.

Diagnostic source-integrity checks retain every loaded module pin, including rig_core. Native frame admission remains independently referenced and fingerprint-bound with stale-reference and unchanged tolerance falsifiers; report current Python overlay separately from rebuilt native pixel acceptance. Cockpit label regressions model the real herdr identifier grammar while preserving labels, durable identity and once-only launch.

Brand scans exclude only exact test/cache descendants of each configured production root. Ancestors named tests or testing must still expose production strings and planted offenders; retain both ancestor and nested-fixture controls.

UI Save As evidence checks the exact chosen path, repeated Save, and reopened document content through the opted-in isolated interface. Native save-path and active-text controls compile maintained routine bodies against controlled boundaries, retain secret and OFF controls, and identify the separately owed full native build.

Inherited animation controls use the exact supplied profiles and packets, true evaluated REST skin and source action/slot/pose/frame preservation. Keep exact inverse digests, oblique-basis controls and stale/wrong-binding refusals; successful mapped-joint agreement never overrides poor skin quality or unmapped weighted channels. Multipart normalization retains actual assembly coordinates, height and source bytes under the unchanged metric bar. Scene-summary tests model current-scene membership independently of global data and retain certified-body/forged-script controls.

Provisional shutdown and overlap investigations retain the precise UI action, process exit, native popup lifetime, X11 map states and binary/source provenance. Compile platform-selection and dock-suppression controls separately; an older executable cannot certify a successor native patch or symbolicate a different build.

The C02 exact inverse control supplies its unchanged authored weights on the
disposable fit copy. Coincident vertices do not imply those weights survive the
30-degree triangle-normal sampling gate. Verify actual transferred weights in a
separate forward round-trip control under the same 1e-6 metre bar; never narrow
compatible-surface matching to retain an incidental golden transfer result.

Uncovered bind-source vertices are a prepublication refusal, including the
faceless orphan shape. Verify bounded original IDs, unchanged bind state and
absence of a new fit object. An explicit copied cleanup must prove retained
source identities, face-corner membership and coordinates before a corrected
predecessor's numerical chain is measured.

Text-replacement controls model a prior native editor consuming the first outside press, no existing editor, and an already active target. Keep empty/Unicode replacements and SearchMenu/Num single-activation falsifiers, then verify exact Save As, repeat Save and reopened content on the isolated app; input timing experiments alone do not establish focus correction.

Platform-guard models evaluate the bounded defined/AND/OR grammar with real precedence and parentheses, retain unknown-form refusal, and compare every maintained conditional against actual compiler preprocessing for Linux fork ON/OFF, Apple, Windows and unsupported platforms. Header-free preprocessing is a selection proof, not complete native compilation or linkage.

Authored FACE-part copy tests preserve exact source identities, corners, UVs,
materials and normal-vector provenance, while reporting native normal encoding
separately. Plant changed ownership/topology/source and moved copied seams;
original seam gates must survive every valid preparation transform. Template
refit tests use real bound/parented examples, REST-versus-POSE rays, injected BVH
failure and independent canonical procedural-body weight expectations. Retain
source action, pose, parent, weights and world transforms; reject the old global
falloff by actual weight rows, not only by missing metadata.

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

| 2026-10-08 | actual native bind correction controls | measured long source bones, implicit Manny and verified UE predicate | synthetic source-short-bone diagnosis did not explain actual readback; independent authored binds were missing | Test source preservation, exact disposable container naming and redundant node/pose/cluster evidence separately, with unchanged quaternion bars and explicit physical proof limits. | default-reference/container RED and corrupt bind/near-bar plants |

| 2026-10-08 | original MCP contract boundary controls | complete C0-C2/T1-T3 re-audit | omitted non-mesh summaries and unrestricted editor strings passed existing tests while defaults remained implicit | preserve missing-summary, invented-editor and explicit-default RED controls plus native empty-state and no_area checks | 753 standalone, 78 server and two post-enum isolated native checks; aggregate acceptance remains separate |
| 2026-10-08 | email exemption falsifiers | PR3 finding4213654799 | domain prefix exceptions and line-wide email allowlisting hid planted offenders | test complete hosts and independent addresses while retaining exact fake controls | initial21 and allowlist RED receipts plus privacy suite |

| 2026-10-08 | bounded onboarding GUI observations | private AC51 half-CPU stale panel audit | a one-second assertion ran before queued input was handled and editor redraw did not explicitly refresh popup layout | distinguish model/input acknowledgement from native convergence; preserve persistent stale, overlap, footer and single-popup controls with sampled evidence | delayed-input RED, popup-refresh REDs and software native receipts |

| 2026-10-08 | native screenshot routing regressions | actual753 screenshot operator all-black output | successful save return hid zero-pixel frontbuffer output and a missing target definition could disable the fix | compile the actual dispatcher with ON/OFF, capability, context-switch and failed-read controls plus target-scope plants; require separate rebuilt native pixel evidence | two pre-fix failures, compiled dispatcher GREEN and hash-identical isolated RED |
| 2026-10-08 | actual audit regression reconciliation | native diagnostic and cockpit audit | an outdated two-module expectation failed and friendly labels violated launcher grammar | retain all three source pins and verify distinct durable valid identifiers without hiding labels | genuine diagnostic and 13 invalid-name RED controls; isolated GREEN with platform evidence separate |
| 2026-10-08 | root-relative brand scanner fixture admission | full client run under a tests-named ancestor | substring filtering hid every planted production offender | prune only exact tests/testing/cache child directories beneath each scan root | genuine StopIteration plus ancestor RED, all four brand controls GREEN |
| 2026-10-08 | Save As and startup UI falsifiers | additional914 audit I02/I11 | delivery receipts and stale text could hide missing filename commits or initial Continue registration | require exact save/repeat/reopen content and registration order, plus native suffix/edit-buffer/secret controls | genuine pre-fix failures, compiled boundary GREEN and isolated old-native/current-Python receipt |

| 2026-10-08 | inherited assembly and animation contract controls | actual additional audit I01/I03/I04/I05/I06 | synthetic success obscured assembly collapse, suffix crash, profile drift and wrong rest skin | require exact original-input RED/GREEN, exact digests and true rest/state conservation; report physical rejection independently | real54assembly, suppliedprofile/Walking inverse and73animation controls |
| 2026-10-09 | localized UI overlap and CtrlQ controls | additional914 provisional findings | Python popup gating hid missing native dock registration and unrelated symbol addresses could imply a false crash cause | record actual native map/registry states and fresh-region CtrlQ outcomes with explicit build identity; preserve source/physical evidence distinction | reopened mapped-island RED, platform-selection runtime RED,463 controls GREEN and isolated exit0 cases |
| 2026-10-09 | independent inverse and compatible transfer controls | resumed cape repair and C02 regression | coincident vertices with incompatible face normals accidentally inherited the authored golden weights through inpainting | preserve authored weights and exact inverse expected values, and separately verify transferred-weight forward round trip | native incident-face diagnosis and unchanged golden/bar controls |
| 2026-10-09 | native text focus acquisition | I02 repeated actual .mixar Save As failure | retained directory editing consumed the first filename click and text went to a highlighted field | establish Text-only focus through two bounded native clicks, retaining search/numeric activation and exact file/content evidence | GDB outside-press exit, three model REDs,77 focused and725 combined controls GREEN; matching native build remains separate |
| 2026-10-09 | orphan bind-source coverage | resumed actual full chain | weights claimed success with uncovered zero rows while return refused | test prepublication coverage and immutable state/object boundaries; copied cleanup retains original identity proof | genuine native orphan-shape RED and unchanged original-input guard GREEN |

| 2026-10-09 | native platform model compiler comparison | full5b aggregate exposed two new cinema controls | the OR-only test parser rejected the valid Linux-and-fork dock registration condition before reaching unchanged linkage assertions | model bounded logical grammar and verify every guard against real platform preprocessing, retaining unsupported-form refusal | two reproduced parser REDs; Linux ON/OFF, Apple, Windows and no-platform compiler comparisons GREEN |
| 2026-10-09 | authored copy and original seam falsifiers | real labelled gear preparation | overlapping rigid rows and geometry-only seam detection hid source boundaries | test exact face ownership, stable copied IDs, normal semantics and stale/moved original seam rejection without acceptance flags | actual preparation RED plus native source/recipe/topology/seam controls |
| 2026-10-09 | independent procedural body and replacement bind controls | supplied example rig quality audit | missing method metadata alone would not prove algorithm failure and copied bindings retained old rig dependencies | assert actual independent finger weights, single new binding, preserved source/parent/world state and restored REST evaluation on exception | native old-falloff functional RED and Titan/current-method comparison |
