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

The site-link gate admits exact recorded attribution URLs only in the files that carry them: the offline Blender corpus's
packaged manifest and NOTICE, its provenance link templates, the vendored Lab summaries' docstring and the UE handoff's
versioned Python API pages. It preserves the global host list and rejects runtime reuse, changed pins/versions/queries,
lookalike hosts and extra URLs on an allowed line. These static references grant no runtime retrieval or egress route.

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
policy and cleanup assertions. Historical artifacts and native baselines remain separate receipts. The runtime, offline QA
and CI download all pin the official Linux x86_64 Grok 1.0.50 artifact by the same SHA256; rerun unchanged native availability
and exclusion controls for that artifact, keeping 1.0.46 observations historical.
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
The native deny-intersection control writes its deny into the fixture's `$GROK_HOME/requirements.toml`: native Grok enforces
MCP allow/deny lists only from its policy layers, never from `config.toml` (`grok inspect`, 1.0.50), so a deny there proves nothing.
Native Grok treats that file as a managed cache (one agent start honours it, then removes it), so the deny is written before each
run and a run may only leave it as written or removed.

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

Bounded issue #11 intake preserves named tests, original algorithms, refusal assertions, tolerances and native deadlines.
AXI goldens follow the accepted PR1 canonical renderer while decoded values and commands remain; expanded help/newline
forms can still be legal decoder input. Synthetic RED/GREEN controls prove components only. F23 controls preserve dynamic
walk steps/defaults and plant missing temporary popup refresh; physical clicks, layout and save remain native acceptance.
Hidden-copy controls retain source visibility/collection state and restoration after exceptions, including repeated conform calls after baseline removal. The imported issue2 helper
requires an outer exact matching binary/overlay fingerprint receipt; absent binaries or owner assets are NOT RUN. Pure
frame arrays do not replace native normalization or private-asset proportion/appearance proof.

Grok worker compatibility tests preserve OFF behavior and the original native unrestricted discovery/auth/persona baseline.
Explicit ON enrollment uses the exact displayed version/effects digest and scope; missing or stale consent refuses before
native lookup/probes/files. Preserve hostile-reload canonical availability, foreign initialization/call refusals and the
original twenty-second deadlines. Test-instance candidate admission never promotes production worker readiness. UI
controls retain MAIN/B5 paths, warn on every Grok selection, and plant mutable-disclosure and stale-server digest failures.
Native QA planning uses only its owned fixture environment and restores the full caller environment after success or failure. The STDIO diagnostic removes every exact HTTP shim mount only from its copied policy-only probe boundary; loopback uses the unchanged production plan. Retained malformed consent options refuse renewal without changing state. Use the production AST extractor on client consent messages; verify whole-sentence translation before wrapping, translated action labels and unchanged exact server disclosure/digest. Source passes and consent do not establish native mount behavior, configuration preservation or worker qualification.
Hostile same-name reload controls cover STDIO, HTTP and SSE independently, using the native advertised transports and exact ACP payload schema. HTTP/SSE controls use only owned rejecting loopback endpoints, retain the original restart fence and twenty-second budget, and require canonical readiness plus a successful next owned call. A name-only STDIO sentinel cannot qualify URL-keyed native attribution. Translation fixtures bind the actual production helper body to their current synthetic `bpy`, so earlier module collection cannot select an identity stub or another fixture's translator.
P4-17 (captain, 2026-10-12): `tests/qa/grok_worker_boundary_validation.py` runs the original validator unchanged with Lampway's ACP
boundary in front of the restricted native agent; only the same-name update replies must become the boundary's refusal, every
retention, next-call and no-contact check stays, and it stops before the project-source and native-pane stages the boundary does
not sit in. `--without-boundary` must fail at the original's line 700. The original runs in CI under
`grok_native_retention_watch.py`: the known failure is a tracked warning, a pass or any other first failure is a loud error.
Supplemental transport and selected-inline-agent diagnostics run separately after the original native checks, with their own receipts and an exact clean-checkout grant in a nonroot loopback-only namespace. Pin the reviewed validator and keep every original acceptance assertion intact; preserve the failed prior bytes and exact assertion/deadline comparison when repairing fixture mechanics. Observe current loaded policy, canonical next calls and hostile endpoint contact independently; metadata alone cannot attest the runtime transport. Fresh independent sessions may continue after a semantic failure only when exact-owned cleanup succeeds. Synthetic inline profiles establish their own limited configuration behavior, never universal selected-agent preservation or production readiness. Deadline controls refuse expired requests before writing; all update/completion/catalogue/next-call work shares the original twenty-second budget.
Native pane startup follows production: the worker starts without its task under the original ten-second admission deadline, and the task is its first real frontend prompt, one herdr `agent prompt` after genuine readiness (`herdr/host.py`); the CtrlC case holds that prompt's request. The CtrlC observation wait also requires the pending request in its current event range, never a prior startup/persona marker. Capture exact PID/start identities continuously before pane creation through closure, fail closed on monitor errors, and reap only recorded same-start adopted zombies with the original cleanup bounds. Preserve the separate native and cleanup failures, every cancellation/retention assertion and environment restoration, including failed receipt writes. Controlled lifecycle tests prove fixture mechanics only; native execution remains required.
On native failure, retain bounded pane reads and agent status for only this fixture's known pane/name pairs before closure. Witness or receipt failures never replace the original native exception. Diagnose retryable local model refusals with a separate explicit HTTP400 variant alongside the unchanged HTTP503 run; retain the original response body, held request behavior, all MCP handlers, native assertions and deadlines. Record the exact selected handler/status and archive both roots. A paired fixture result does not qualify production worker readiness.
Separate ACP cancellation diagnostics send a real native prompt and cancellation notification against the same owned rejecting HTTP handler. Annotate only actual handler observations with per-request identities, timestamps and a boolean for the synthetic probe; never record request bodies or manufacture native events. Require the same persona-bearing probe request to become pending and close within the original eight-second window; stale, unrelated and late closure cannot count. Prompt/cancel writes, drains and the actual cancelled reply share twenty seconds, independently of that peer-close window. Missing PID/start identity, monitor/cleanup failure or changed protected inputs refuses subsequent cases. Retain the original terminal failure and distinguish frontend idle, native cancelled reply and request closure.
Native pane identifiers can contain colons. Preserve their original paths inside a compressed evidence archive before artifact upload; keep raw receipt/config/log bytes and a matching embedded/uploaded manifest. Archive only explicit owned fixture roots, never dereference symlinks or redirect output paths. Record native sockets and other special resources as omitted metadata, missing roots as NOTRUN, and refuse changed inputs; packaging does not establish cleanup or acceptance.
Original MCP regressions verify definitive empty paint-layer summaries for non-mesh object detail, byte-identical finite view editor schemas and explicit view defaults. Plant an invented editor identifier to prove rejection before runtime, and retain the supported-but-absent editor no_area control. Isolated native Camera and view calls verify these boundaries without changing the scene/selection snapshot or enabling pixels. Focused worktree receipts do not replace final consolidated-head, named-performance, GUI-history or package verification.

Generic bind-region/ancestor fixtures use anatomical descendants rather than claiming incomplete native helper topology. Assert plan success before measuring weights and retain an explicit partial-native-helper plan refusal with unchanged objects/state. Influence histograms include zero rows; compare their full count and zero bin to actual written weights instead of adding unweighted_vertices twice. Keep complete public-chain acceptance, source integrity, normalization and lineage checks separate from skin-quality acceptance. Original V3 plates are supplied through LAMPWAY_V3_PLATES_DIR, remain read only and join the reference snapshot.

UE output-encoding controls exercise actual capture orchestration with native-shaped targets, enum types and same-capture byte/raw reads. Preserve target/state corruption plants, the ruled disabled-tone controls (identical 0.18 gray with a moving white completes; unchanged white or a moving gray refuses; captain, 2026-10-11), settings restoration and failed-completion revocation. Synthetic surface and orchestration passes are not actual UE/GPU evidence.

Chat fixture repairs preserve complete-collection behavior, positive custom-property mapping and cached-import restoration controls. Mock mirror/executor signatures accept and assert actual scene/session forwarding. Specialized turn-recovery fixtures share the same scene collection with the actual transport consumer, preserving live-stream exclusion and positive prompt assertions. Confirm exact original failed identities under full collection; retain genuine production provenance/resume conflicts instead of deleting their assertions or treating them as environment skips. The two inherited ones are settled in production: MatGen stamps agent provenance at enqueue (`matgen_queue.enqueue_matgen_job`), and parked auto-resume fires once per reconnect event (captain, 2026-10-11); their tests keep the original assertions on the real interfaces.

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

The real pane-origin and disconnected saved-file/History cases run in
`tests/lampway_tools/test_agent_modes_integrated_live.py::test_real_blender_roundtrip_through_real_hermes_and_herdr`, using
`tests/qa/agent_modes_integrated_client.py` inside Blender. Supply `LAMPWAY_BIN` for the matching normal build and a fresh
outside-repository `LAMPWAY_INTEGRATION_ARTIFACTS` directory; retain XML, logs and actual native receipts. The FDCA local
receipt in issue #11 passes these added cases with a matching normal build in synthetic-login scope. Later source changes
still require their own qualification; static planted checks never close native acceptance.

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

Native fit_bind seam-band checks drive C03 through the public plan/weights path, preserve exact inverse bars and reject missing contact authority, rigid/profile/axis/endpoint/overlap and stale inputs before publication. Native transfer checks preserve twelve influences by default and retain an explicitly requested cap. Older-binary current-source controls remain distinct from matching native acceptance.

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
| 2026-10-08 | exact static corpus attribution | parent approved bounded PR4 provenance compatibility | ten official packaged attribution references failed the shipped-host gate | admit exact manifest/NOTICE URL literals while preserving runtime host refusals and planted path/pin/query/lookalike/extra-link controls | actual ten-reference RED and focused gate controls |
| 2026-10-08 | voice fixture lifetime follows execution | whole native client run lasted longer than the one-hour collection credential | three late voice tests failed before handshake because the valid fixture had expired | execution-time credentials; keep expiry, rotation, handshake-count and two-second controls | controlled full-run delay: three RED failures, all thirteen GREEN |
| 2026-10-08 | language catalogs follow the current interface | full-client template currentness RED; canonical fresh template found 22 new messages and 48 stale catalogs | tracked catalogs and the ignored template stayed behind the Context and profile UI strings | canonical extraction/update before publication and full client proof; retained translations and placeholders unchanged, new strings use English fallback | original template RED, 48 fresh-template catalog RED errors, canonical external GREEN; matching final full suite required |
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
| 2026-10-09 | public positional seam and native influence tests | canon07 B.6/B.9 missing implementation | primitive-only goldens did not detect disconnected bands or the public four-influence default | public C03, endpoint/identity and twelve-influence behavioral controls | genuine old-code/reversion RED and native current-source GREEN |
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
| 2026-10-10 | complete local-audit fixture and encoding controls | issue2 G30/G34/G35/G36 supplied failures | native-helper fixture refused before unasserted plan; zero rows were counted twice; target encoding and original-fixture admission lacked falsifiers | require admitted anatomical fixtures with explicit native refusal, actual histogram/row agreement, original V3 snapshot and native-shaped encoding/state plants while retaining all numerical/acceptance bars | genuine native planning and full Bunny RED/GREEN, corruption plants and selective-gray encoding controls; matching native/GPU acceptance remains separate |
| 2026-10-10 | inherited fixture repair controls | original54 exact identities under full collection | cached mocks and obsolete scene/registry/fake-call interfaces obscured behavioral checks | model current native scene properties, restore cached imports and retain explicit forwarding and lifecycle assertions | original52 PASS; original two production conflicts retained RED; old-fixture property/restoration plants rejected |
| 2026-10-10 | full-suite turn-recovery fixture qualification | expanded complete collection | specialized recovery mocks patched one module while real transport held another scene collection | use one native-shaped scene collection across the observed recovery consumers and retain live-stream and prompt assertions | full-collection failure trace and strict restored-fixture controls; missing sync executable remains explicit preflight refusal |
| 2026-10-11 | normal engine prerequisites and affirmative baseline reconciliation | issue #11 P4-T02/T03 | tag-only test paths rejected valid SHA builds and 122 passing identities remained in the baseline | compiler prerequisites use the normal resolved manifest; baseline entries need exact PASS receipts, preserving every other failure; qualify completed FDCA integrated native cases by their scope | causal tagless RED; 45 focused passes; verified archive and all 122 original baseline identities pass again in cloud; whole-client remains RED |
| 2026-10-11 | bounded issue #11 dependency qualification | accepted exact PR1 intake and inherited hidden-copy correction | canonical output migration, mocked popup refresh and pure geometry could be overstated as native proof | intake paragraph: retained semantic controls and original assertions, explicit native/helper fingerprint prerequisites and physical scope | causal AXI 9F21P to39P, F23 10F43P to53P, hidden5F2P to7P; native proof separate |
| 2026-10-11 | Grok compatibility controls retain native acceptance | explicit worker-only consent ruling and source review | consent metadata ignored effects and async enable could accept an unseen warning; pure guards could overstate safety | Grok paragraph: exactdigest OFF/ON gates, unchanged native baseline/deadlines, MAIN/B5 and stale-state controls, candidate-only QA admission | causal boundary6F, UI4F and digest/preflight REDs retained; native safety qualification remains separate |
| 2026-10-11 | consent QA environment and repeated visibility controls | integrated native diagnostic and independent review | stale view-layer entries broke a second conform; native QA planned under the wrong HOME and retained a repeated HTTP shim | synchronize before visibility snapshots; retain repeated-call controls, exact fixture-environment restoration and all exact STDIO shim removal; malformed consent refuses | causal RED/GREEN plus actual historical-native diagnostic; final-head native acceptance remains open |
| 2026-10-11 | consent extraction and translation controls | new consent UI catalog review | positional messages escaped extraction and wrapped fragments would not match catalog messages | production extractor and whole-message translation controls preserve exact server effects/digest | four causal REDs; canonical catalog regeneration remains a separate check |
| 2026-10-11 | native transport reload and translation fixture isolation | primary native reload audit and whole-client two-failure receipt | URL-keyed HTTP/SSE attribution can evade a STDIO name sentinel; cached translation helpers retain another fixture's globals | independently require all three native transport preservation controls, unchanged timing and owned endpoints; bind the actual translation helper to current fixture globals | cached-helper causal two failures then 174 passes; HTTP/SSE native controls remain NOT RUN and production readiness remains disabled |
| 2026-10-11 | same-artifact native requalification | captain requests newest official Grok before diagnosis | runtime, QA and download could diverge or reuse older native proof | offline QA paragraph: one 1.0.50 hash and unchanged availability/exclusion controls with historical receipts retained | old-pin refusal retained; updated artifact static probes pass; original native checks still required |
| 2026-10-11 | independent native configuration diagnosis | actual 1.0.50 original checks lose canonical readiness after HTTP reload | the first failing assertion leaves next-call and SSE behavior unwitnessed, while a synthetic inline profile could be mistaken for universal repair | supplemental diagnostics paragraph: original byte-pinned acceptance stays intact; fresh restricted cases, loaded-policy/endpoint/next-call evidence, exact cleanup and separate inline scope | expired-write causal RED; portable deadline and refusal controls; actual restricted diagnostic receipts required |
| 2026-10-11 | native evidence artifact portability | actual diagnostic CI rejects native pane path w1:p1 | platform filename restrictions discard the entire upload, hiding later native startup/cleanup receipts | archive paragraph: retain native paths and raw evidence inside compressed tar, exact manifest, no link dereference, visible special-resource/missing-root scope | actual upload RED retained; colon/manifest/link/omission/change/refusal controls; native rerun required |
| 2026-10-11 | native pane fixture sequencing and ownership | archive-enabled 1.0.50 diagnostic timeout and cleanup failure | the fixture held an initial model request beyond startup admission and observed ownership only after synchronous commands | pane paragraph: genuine initial startup before held native prompt, continuous exact PID/start capture, owned zombie reaping, preserved failures and restoration | original causal two failures plus two stale/pending observation failures, eighteen portable lifecycle controls PASS; all nineteen original checks/assertions and deadlines exact, native rerun required |
| 2026-10-11 | native startup failure witnesses and paired refusal diagnosis | actual 1.0.50 initial startup times out despite corrected hold sequencing and successful thirteen-identity cleanup | missing native screen/status hides whether repeated HTTP503 model refusals cause retries; a replacement fixture could conceal the original RED | failure paragraph: bounded owned witnesses preserve the primary exception, separate explicit400 diagnostic retains the original503 run and all inherited assertions/deadlines | witness original5F18P to23P; explicit refusal causal RED and27 inline controls PASS; actual paired native execution required |
| 2026-10-11 | request-specific native cancellation diagnosis | actual permanent-refusal run reaches startup and CtrlC but fails eight-second request closure | frontend idle or an unrelated/late HTTP close could be mistaken for cancellation of the interrupted request | ACP cancellation paragraph: actual request annotations, unchanged handler, exact peer window and separate shared reply deadline, identity/cleanup guards | original native terminal failure retained; causal request/deadline controls and actual independent native receipts required |
| 2026-10-11 | inherited production conflicts settled | PR1 FINAL account AC05 (two known reds still failing); captain: "fix both now", one resume per reconnect | the MatGen test targeted upstream's withheld job class while Lampway's MatGen dropped provenance; parked resume fired every eligible tab against the test's one-per-event policy | provenance stamped at enqueue and sent with the request; one resume per reconnect event so no two agent streams start together; both tests keep their assertions on the real interfaces | matgen payload RED and parked-resume RED, then 5 and 16 GREEN |
| 2026-10-11 | disabled-tone control fakes | captain's G30 ruling | the fakes moved every sample, gray included, unlike the engine, so they pinned an impossible control | fakes keep 0.18 gray fixed and move the others; plants for unchanged white and moving gray | 15 RED, 119 GREEN |
| 2026-10-12 | merge main into PR #4: test notes and site links | lampway-finish-pr4 brief: merge main (PR #1 at 079522c2) into PR #4 | both parents appended test notes; main admitted two Blender hosts globally while PR #4 admitted exact attribution URLs only | keep both notes; the site-link gate keeps PR #4's exact-reference rule and extends it to main's provenance templates, vendored docstring and UE handoff | merge receipts on the lampway-finish-pr4 shelf |
| 2026-10-12 | P4-17 boundary proof and native watch | captain's ruling on issue #11 P4-17 (option b) | the original native check could only stay red against the pinned Grok, and rerouting it would have weakened it | a separate boundary validation with its no-boundary control, and the original kept unchanged under a watch that is loud when it passes or changes | native stdio/loopback RED/GREEN; 11 watch unit cases |
| 2026-10-12 | native pane startup follows the production task delivery | captain (direct): Grok BYOA workers must work | the pane check pinned the task on the worker's command line, so herdr's start waited out the working first turn and timed out | pane paragraph: task-less start, then one agent prompt after readiness; the CtrlC case holds that prompt; the original line-700 check is unchanged and both reviewed-hash pins re-reviewed | lifecycle controls unchanged and GREEN; native inline diagnostic rerun |
| 2026-10-12 | native deny intersection in Grok's policy layer | first native run past the pane stage (ec590777, observe-only) | the control wrote the user's deny into config.toml, which native Grok never treats as MCP policy, so its baseline served the denied connector and the check proved nothing | the deny goes into $GROK_HOME/requirements.toml, with the same checks and restored bytes | grok inspect: config.toml deny absent and server loaded; requirements.toml deny reported as the disabled reason; native rerun |
| 2026-10-12 | the deny is written before each native run | native rerun at 425e0596 | native Grok removes $GROK_HOME/requirements.toml after one agent start, so the plain-native baseline consumed the deny and the restricted run started with none, which read as Lampway overriding the user's policy | write the deny before each run; each run may leave it written or removed, recorded per run | ACP catalogue probe: deny honoured then file gone after one start; with the file rewritten, plain and restricted (pid namespace, HOME view) both deny |
