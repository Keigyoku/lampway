<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 runtime verification

## Latest completed evidence before the display repair

Exact source `83aedc057a718e29d720919d599c853126a1238b` completed the full server suite: **3,251 PASS, zero failures/errors,
31 unchanged opt-ins SKIP/NOT RUN**, in **1,097.967 seconds**. All **3,282** cases started and finished; source, normally
built pinned engine, TUI, manifest, herdr and historical application fingerprints held unchanged. All **51** recorded owned
completion identities and the runner were absent after exact cleanup, including zombies. The retained ResourceTracker
destructor `ChildProcessError` followed exact reaping and was not a pytest failure. Accounting:
`<workspace>/scratch/pr4-exact-final-head-full-server-20261011-attempt5/final-accounting.json`, SHA-256
`fa9ed9ffb06af9ba7af6a8ceef563a274be1c7f842ffd4189bf43a87aaf147c1`.

Its normal pinned Hermes engine build completed with exit zero; manifest SHA-256
`57bbd71c3f8e09cdd63492439bd1415d12954149e1f2517a21bd245ea33278b7`, TUI SHA-256
`32b9ab5eef04eac96473af30ee817757628ff9d6b39b14c13f6a8388618691f5`.
Four actual terminal diagnostics passed in **62.18 seconds**: external Undo, own Undo after mixed-origin turns, own Undo
after genuinely typed turns, and selected concise personality plus Lampway guidance on the next local-provider request.
All eight recorded native identities were absent after cleanup. Receipt:
`<workspace>/scratch/pr4-83aedc05-native-history-personality-attempt1/qualification.json`.

These checks missed a confirmed display regression. Public `session.history` supplies model-context history without
compacted rows; ordinary-info replacement could hide older visible turns and discard frontend command output. The new
compatibility repair uses Hermes's full native display projection only after successful Undo or explicit own-Undo refresh,
leaves ordinary native rendering alone, and retains proven frontend notices in their own order as a display-only suffix.
No role/text heuristic, serialized provenance or second conversation store is introduced. Scratch controls retained two
causal failures against the old code, then nine passes against the repair; reserved-marker and duplicate-notification
failures are retained too. The applied focused packet passed **120 tests without failures or skips**, including explicit
TypeScript compiler/controller qualification, in **12.06 seconds**. Receipt:
`<workspace>/scratch/pr4-history-display-candidate/tracked-receipt.json`.
The original native four-case assertions and deadlines remain unchanged. Compression/resume
and command-output terminal diagnostics, a fresh normal engine build, final source suite and matching application/client
qualification remain required. The application used above is the historical bare `477006fc` build, never a matching83 build.

Remote `b6bbea0c` separately completed **3,199 PASS and 31 unchanged opt-ins NOT RUN** in **1,190.451 seconds**. Its rail,
REUSE, pii-gate, canon and mcp-launcher CI passed; BYOA run
[38022686720](https://github.com/Keigyoku/lampway/actions/runs/38022686720) failed both baseline initialization checks before
native MCP completion. Neither phase reached project trust. Both that artifact and the earlier477 artifact were subsequently
retrieved and retained; an earlier403 observation does not describe their final collection status. Grok's completion wait and
first call share the original twenty-second budget. Local original and candidate baselines both passed, so the historical
race was not reproduced and full repaired native CI remains required. The dedicated workflow now watches and runs its
readiness regression tests. Grok workers remain refused pending qualification; no trust or account grant was made.

The sections below retain historical results and their then-current gaps; this latest evidence supersedes their old rerun
status without erasing failed runs. Final matching-build, complete client, physical helper/skill/consent and separately
approved account acceptance remain open.

## Earlier complete source-suite result


Committed source `b978857e3c1b9df2fba568a4ceb190c2abb52736` completed the full server suite with **3,198 PASS,
1 FAIL and 31 SKIP/NOT RUN** in **1,030.207 seconds**. All 3,230 cases started. Clean source/native fingerprints held
unchanged and exact owned cleanup left zero survivors. The owned resource tracker required TERM then KILL; its destructor
warning is retained. The full receipt and failure accounting are in
`<workspace>/scratch/pr4-exact-final-head-full-server-20261011-attempt2/`.

The sole failure was `test_readiness_queries_native_identity_at_project_and_requires_namespace_success`: its legacy
success mock returned a tuple where production `candidate_paths` returns a named mapping. The correction uses the real
`native`, `bwrap` and `connector` keys. Original assertions and the 60-second timeout are unchanged; the separate malformed-
tuple refusal control remains. Scratch causal proof retained **1 FAIL/5 PASS**, then **6 PASS**; repository integration
passed **16 checks**, no failures or skips, including path-contract controls. Receipts are in
`<workspace>/scratch/pr4-grok-adapter-mock-shape/`. The complete corrected-source rerun is still owed.

The earlier `40447655` full suite remains retained: **3,149 PASS, 27 FAIL, 31 SKIP/NOT RUN** in **1,242.051 seconds**.
Its 25 notice-fixture failures were repaired by seeding prior human acknowledgement only in synthetic positive fixtures;
fresh-admission controls remain unseeded. Its two original socket cases passed with a short temporary root. Neither later
focused passes nor the b978 result erase that failed receipt.

Q1 human-ticket/admission, native preference UI and canonical i18n are committed at `b978857e`. The actual-app raw-loopback
consent audit retained **1 FAIL/2 PASS** before repair. Final focused controls passed **85 server checks in 2.53 seconds**
and **39 client checks in 1.58 seconds**, without failures or skips, in
`<workspace>/scratch/pr4-q1-consent-boundary-audit/`. Admission lasts 120 seconds; the browser form lasts at most 600 seconds,
bounded by original JWT expiry. Scope/model/one-use checks and native script refusal hold; active-JWT revocation is not
claimed. Canonical extraction adds three messages across 48 PO files and preserves all **411,057 retained translations**,
recorded in `<workspace>/scratch/pr4-q1-i18n-20261010/receipt.json`.

Grok's production mapping repair and removal of the native QA override are committed at `b978857e`, with **73 focused
passes**. Readiness remains false. Actual project-native positive controls failed in fresh and Git-bounded workspaces:
native `_x.ai/folder_trust/request` requested the exact synthetic project and `configKinds=["mcp"]`; diagnostics rejected
it without grants. The scoped native-approval proposal awaits explicit authority. No complete repaired native Grok CI
or enabled worker route is claimed.

The source suites used historical `84d896f3` Blender. The complete corrected-source suite, matching normal build, full
client/native packets, final published-head CI, consented ChatGPT probe and real-account qualification remain owed.
Historical passing checkpoints do not override either failed full run. This is not acceptance.

This is a partial verification report for the continued agent-modes work. It is not an acceptance receipt or permission to
merge. The governing scope is [agent-modes-spec.md](agent-modes-spec.md), including the captain's decisions. Account-backed
adapter execution and exact final-head verification remain required. Historical short commit IDs below name the
pre-publication checkpoints; those unpublished commits were replayed with the required release-skill anneal before normal push.

## Status at this documentation freeze

The earlier published PR4 `7b5faed6` had runtime identical to the frozen `7bf02b8c` checkpoint. That checkpoint's
full server run passed **3,073**, with **31 NOT RUN**, in **1,089.575 seconds**. This is a source-suite receipt for that
checkpoint, not proof of the later 404 snapshot, subsequent repairs or a matching final native build. The existing `84d896f3` application
binary is historical. Final exact published-head server/client suites, matching build and required native checks remain pending.

The native-helper ruling is settled: main Mode 1 has three separate experimental preferences for delegation, cron and
background agents, all default off and accompanied by the untested-layering warning. Swarm workers keep all three off.
Context and Q2 native history visibility are implemented; their matching final-head/build qualification remains pending.
Hermes worker exclusive discovery has offline native evidence; there is no remaining approval question about installing its
owned isolation connector. Grok's candidate workflow `38013110045` completed **FAIL**: dependency, artifact, herdr and
controlled steps passed, but stdio ACP hit its 20-second timeout and loopback/`/dev/null` permission failures occurred before
acceptance. Its artifact is retained for diagnosis; worker readiness remains disabled.
Codex pane bearers use the established environment seam, not task argv. Account-backed acceptance for every selected
service/harness remains **NOT RUN**.

The Sign in with ChatGPT terms were successfully fetched and read; the former research/fetch gap is closed. The reading
receipt is `<workspace>/scratch/pr4-siwc-terms-reading.md`. It does not establish the captain's acceptance of those terms or
account authorization. Q1 consent, fixed synthetic vision probe, scoped receipt validation and serializer controls are
committed at `40447655`. Earlier **167 focused checks**, then **98 pinned checks**, passed. The later applied-source
Q1 run passed **211 checks in 12.29 seconds**, retained in `<workspace>/scratch/pr4-q1-final-source-focused-retry.xml`.
These runs overlap and are not added as unique checks. Its first attempt retained two collection import errors; relative
fixture imports were corrected for the successful retry. Final full-source/new-build qualification and every real-account
probe remain pending. B5's first-launch disclosure is implemented and committed at `40447655`; offline client controls
passed 58 checks, with final source/native/account qualification still pending.

The actual TUI/native-MCP follow-up passed **two tests in 19.78 seconds**, with all five recorded owned process identities
absent after cleanup. Its receipt is `<workspace>/scratch/pr4-native-image-followup-actual-20261011-attempt2/receipt.json`.
TUI captions, filename and provider answer were visible. Generic native MCP retained exact PNG bytes in its MEDIA cache/text
path with call IDs and captions; it did **not** promote those generic results into typed model images. No actual Blender
screenshot turn, new-build or account acceptance is established. Earlier failed cleanup/zombie packets remain retained.
The unchanged LP4 material calibration still failed at 240 seconds; no remedy or passing hardware proof is claimed.

A later pinned-native receipt-adoption scenario passed **one test in 23.47 seconds**; its receipt is
`<workspace>/scratch/pr4-native-receipt-adoption-actual-20261011/receipt.json`. Genuine native `vision_analyze` succeeded on
an owned synthetic PNG with support enabled, preserving typed image bytes and caption through the production Front/gateway.
The corrected two-case driver passed in 18.00 seconds; the initial two driver `AttributeError` failures remain retained and
are not a behavioral RED. Its support-false bridge-shaped control was limited and is superseded by the direct native negative:
**one pass in 9.38 seconds**, with `vision_analyze` unavailable, no auxiliary fallback, selected-provider image bytes or egress.
Receipts are `<workspace>/scratch/pr4-native-vision-tool-actual-20261011-attempt2/receipt.json` and
`<workspace>/scratch/pr4-native-vision-tool-direct-negative-20261011/receipt.json`. All fourteen recorded owned identities
in the latest aggregate recheck were absent. These are actual pinned serve/TUI and production wrapper observations with
played herdr, synthetic auth/providers/receipts and local fixtures, not a built-Blender screenshot or account receipt.

Grok's subsequent toy-plugin probe reached actual native MCP `initialize` successfully. Its overall probe still failed:
vendor cold-start modified its native cache/config, so production QA now compares the warmed baseline. This initialization
control does not replace the failed CI packet or establish the complete exclusive worker catalogue, cleanup or account route.
No full repaired CI has completed; readiness remains false. B5's causal nonce defects are repaired in the committed `40447655`
candidate; the offline qualification below does not replace final full-source/server, matching build, whole-client or account proof.

## B5 disclosure candidate at this freeze

B5 first-launch disclosure is implemented and committed at `40447655`. Retained causal REDs exposed nonce reuse on an existing pane and
cross-endpoint/scope reuse; both are repaired. Route-off and readiness checks precede the account-notice guard, preserving
actionable refusals before owned writes. Prior human acknowledgement persists per harness. New acknowledgements require an
auth/path/project/operation-bound, one-use nonce; native UI controls cover cancel, script origin and stale scene identity.
The client controls passed **58 checks**. The final synthetic server focus passed **178**, with zero failures or skips,
recorded in `<workspace>/scratch/pr4-b5-launch-notice/server-focused.xml`. A separate admission recheck after printable
identity hardening passed **28**, with zero failures or skips, in `admission-final.xml` in that evidence directory. These
focused runs overlap and are not added as unique coverage. Native UI/account, matching build and whole-client qualification remain NOT RUN; the complete `40447655` source suite
failed as recorded above, and the repaired-candidate full rerun is pending.

Claude Code 2.1.293 exposes only a confirmed signed-in email from its status JSON, with bounded printable output. Other
identities are displayed as UNKNOWN. Synthetic status fixtures are not evidence of an actual person's signed-in session.

## Completed boundaries

| Commit | Change | Retained verification |
|---|---|---|
| `6e90433f` | Separate native mode chip from the model picker | RED mode-chip tests; 95 focused tests passed. Native execution subsequently verified at published `eeb3039d`; see current checkpoint below. |
| `9f53af5c` | Independent swarm cards and contiguous terminal-tail recovery | RED client/server witnesses; 132 client and 26 server tests passed. |
| `7d1acd4e` | Engine TOON result seam with the accepted PR1 codec | RED six cases; 179 focused server tests passed. |
| `0d847875` | Native chip and real Blender RNA verification fixtures | 2,728 fitter spans/configurations and four RNA tests passed. RNA used the prior native binary. |
| `a7b77710`, `28739a4f` | Repair lifecycle fixtures against the actual runtime | 54 and 46 focused tests passed; five mutation controls detected the relevant defects. |
| `7319ae5f` | Capture MatGen job provenance at construction | RED HTTP-body witness; 38 tests passed. Server-side persistence of the additive metadata is not claimed. |
| `a39b5a04` | Fence old conversations, recover new conversations and defer archives during live work | RED archive, recovery, attachment and pending-command witnesses; 91 client and 41 server tests passed. |
| `ee701bdc` | Verify library discovery through the engine TOON response | RED JSON-only assertion; 12 library/engine tests passed. External MCP retains its existing JSON envelope. |
| `f7ed0958` | Configurable worker deadline, explicit expiry and deterministic fixture teardown | RED deadline/lifetime witnesses; 135 tests passed, no skips or errors. The existing 1,800-second default is a proposal, not a captain ruling. |
| `d2254968`, `4b459845` | Keep a stopped scene bound while fencing retired turns; preserve legacy event recovery | Expanded focused suite: 36 tests passed. Real Blender/Hermes/herdr integration passed using a deterministic local provider and the prior native binary. |
| `10e41390` | Session-owned image-copy records and 30-day expiry | 13 tests passed, including replacements, links, corrupt metadata, restart and original-file preservation. Periodic app maintenance wiring remains pending. |
| `dea9eaa9` | Expire owned image copies after session-registry pruning | RED orphan-expiry and ancestor-link witnesses; 39 retention/Mode 2 controls passed. Private ownership records survive pruning; originals and substituted files remain untouched. |
| `6ac2b45b` | Cursor's supported per-pane plugin route | Final focused suite: 83 tests passed, no skips or errors. Account-backed tool execution remains unverified. |
| `d68c17ac` | Accepted PR1 publication metadata dependency | REUSE 6.2.0 covered 9,847 files with no missing or invalid license expressions. |
| `c7457315` | Self-contained accepted PR1 privacy and workflow controls | 20 scanner and six workflow controls passed; no scanner exemptions or bypass were added. |
| `3b7be613` | Conditional native definitions on interface, View3D and agent-bubble targets | Accepted consumer controls and agent-bubble ON/OFF source controls passed. Six real cached compiler syntax checks passed; newly linked executable and physical clicks remain pending. |
| `6f6701f9` | Separate saved worker mode from its Mode 1 service | 242 focused Choices/runtime tests passed. Receipts pin mode and service separately; the configured-app factory's resolution forwarding remains a shared-file dependency. |
| `d9206cdc` | Scoped accepted PR1 client68 fixes and subtitle recovery | Imported the accepted code/data/licensing dependency and two bounded prerequisites. Full current client verification remains in progress; the shared ROOT AGENTS render-contract link remains pending. |

The table above records statuses at those historical checkpoints. Later scoped repairs resolved its maintenance-tick,
configured-app forwarding, rendered native chip and governing render-link gaps; those old pending cells are retained as
history, not current blockers. Their exact evidence is in the later checkpoint sections and the current freeze status above.

The integrated Mode 1 fixture exercises actual TUI-originated turns, client steer and Stop, immediate post-Stop recovery,
Blender mutation and Undo, checkpoint mark/rewind, image copying, conversation reset and reopening an ended pane. Its provider
is deterministic and local. It does not establish ChatGPT account access, paid API access, a Mode 2 account session or the new
native chip's rendered behavior.

## Published native checkpoint

Published PR4 `eeb3039d4edc3ecc1d842aa12b038de2d755d1ab` has a clean source/bare matching `BUILT_FROM` receipt.
The native binary SHA-256 is `795dee99a94835145d9e8b9724d6fa23f570fcab089c62908aa337318f0e176c`.
Actual native GUI checks show a separate, positive-height Mode chip beside Model, correct BYOA tooltip, and a mouse-opened
registered Mode menu. The five fitter/RNA checks and eleven native consumer ON/OFF syntax/branch and planted-definition
controls passed. Physical View3D drawer and brand tests measured both requested palette changes. This is not a full OFF build.
All 54 required checkpoint identities passed together on that published head with no skips. Its immutable full client run
finished with 9,597 passed, 10 failed and 79 skipped, plus 96 passed subtests. Before/after clean source, build stamp and binary
hash match. The failures were static attribution, worker Stop, two dimensionless SVG fixtures, the governing render-contract
link, three expired collection-time voice credentials and two unchanged 240-second procedural-render timeouts. The first five
were repaired by `96ab5403`; the three voice fixtures now mint credentials at execution. No production expiry or test deadline
was weakened. Matching Mesa's renderer pool to the cloud CPU quota (`LP_NUM_THREADS=4`) still timed out the unchanged first
material test at 240 seconds, with source, generated overlay and installed script bytes held. The second calibration was not
run. Both original full-run render failures remain unverified and need the requested built-app hardware validation.

## Published `ad15ad77` checkpoint

Published `ad15ad7761e16decd1e7da32e0b7c9feadeed51f` has clean source and a bare matching `BUILT_FROM` from the normal build.
Its binary SHA-256 is `30a6f831d90767e8b4e4607bbbbfecb06f3eef26b2cb40dead925afb85bf8d1e`.
The physical Mode-chip mouse check, five fitter/RNA checks and eleven native consumer ON/OFF checks passed. These consumer
checks are not a full OFF build. Actual physical Docs and Report clicks each produced HTTP 200 after correcting the fixture
to use physical XTest clicks without `--enable-event-simulate`, which suppresses operating-system input. Five retained palette PNGs carry
causal measurements and were visually inspected by the coordinator.

All four real Blender/Hermes/herdr cases passed without skips: the integrated main conversation, two-worker collection,
worker Stop after streaming and worker Stop before the first token. Their retained `pr4-ad15ad77-real-runtime` receipt
compares all 5,441 compiled source files, the binary, build cache, compile commands and clean source before and after; all
fingerprints match. The guarded full pinned-server receipt reports 2,345 passed, zero failed and thirteen skipped in
809.937 seconds against that same matching build. The seven exact repaired client regressions also passed. All five CI
workflows succeeded on this published head; there were no review-thread or review-submission findings.

The newly available Pi 1.0.4 offline test exposed a real fixture failure: `communicate` flushed stdin after the fixture had
deliberately closed it. The bounded fix detaches that closed pipe and waits after killing only its owned child, preserving
the six-second window, thirty-second communication limit and both MCP assertions. The exact original case passed once
without skips in 6.119 seconds. Inherited seccomp denied IPv4 and IPv6 socket creation with `EACCES`; a separate Unix-socket
control succeeded. This fixture fix is not yet a matching-build or final-head native receipt. A new full client run has not
been performed: the two known 240-second material failures and account/owner acceptance blocks remain unresolved.

## Later matching checkpoint and E1.6 audit

The published `78461063bd204e75957b3be9555417ab85fc321a` checkpoint has an actual clean matching native build
(binary SHA256 `22eb6354194e84528c6b3ed02373eebeadeba8d840690d41008b07ac7dd800e3`). All 54 required checkpoint
identities plus the seven exact repaired client cases passed together: 61 passed, no skips. Native fitter/RNA checks passed
5 and native consumer syntax/preprocessor controls passed 11; this is not a full OFF binary build. Fresh physical Docs/Report
clicks returned HTTP 200 from the actual local backend. Root inspected the new profile, Mode chip/menu and five palette
screenshots. All four actual pinned Hermes/herdr native runtime cases passed without skips: integrated turn, two-worker
collection and Stop after streaming/before the first token. Source, binary, CMake and compiled-source fingerprints stayed
unchanged. GitHub returned no workflow runs or commit statuses for this checkpoint; CI remains unverified.

The E1.6 paired deterministic task audit then found that optional `structuredContent` beside TOON text is copied into the
pinned Hermes model message as JSON. Identical flat-row and escaped/nested tasks succeeded through the real pinned Hermes
and its TUI in a played herdr PTY, with a scripted recording provider; this is semantic transport/calculation proof, not
generative reasoning or account proof. Reference `cl100k_base` counts were JSON 855/559 versus duplicate TOON 1572/1159 for
the complete model-visible tool message. Smaller TOON text alone did not establish a model-context saving. The generic
engine endpoint advertises no output schema, so the scoped repair removes its optional duplicate while retaining lossless
TOON text, error flags, the byte-identical shared codec and all external wrapper schemas. The native-renderer regression
was RED before this repair and all 13 focused seam/library controls passed afterward. The six deterministic comparison turns
all completed; corrected full model-message counts were 550/648 versus JSON 855/559, preserving identical answers and
recording zero actual external sends. Fresh final-source/native/server proof after publication is required; earlier checkpoint results
are not relabelled as later-head acceptance. Token results are workload-specific, not a promise of savings for every shape.

## Scoped completion repairs

PR4 now owns the production configured-app wiring. The app factory forwards the pinned worker resolution with its existing
app-owned authentication; the idle maintenance tick applies the established 30-day owned-copy policy and joins in-flight
expiry on shutdown. Originals and replacement/unrecorded files remain untouched. The bounded public Docs/Report operators,
registrations and local routes retain the accepted PR1 helper interface. Focused app checks passed 25/25; auth helper and
existing refresh checks passed 14/14. Valid dimensioned SVG fixtures passed both launcher controls with the real renderer.

Worker token revocation cancels every active model request for that key even while TCP stays open, including concurrent calls;
main requests are unaffected. Owned worker Stop and confirmed worker close revoke before pane shutdown. The 152 focused lifetime,
wiring and provider controls passed without skips; both actual two-worker Stop phases passed with the repaired server and
prior published binary. This mixed-source diagnostic is not final-head/build acceptance. Existing main-pane close token
behavior was not changed by the worker repair.

The exact three-file PR1 dependency `323d44b99e5c4418e5412de710bbc436982034d5` is imported with provenance. Its R04 angle
measurement uses `atan2(cross norm, dot)` to preserve actual angles without BLAS-dependent arccos amplification; matrices,
keys, tolerances, falsifiers and the exact-byte gate remain intact. PR1's published `b1e300cf` canon CI passed. All five PR4 CI
workflows passed at `96ab54031af4957be77b80781ba54bba8d43d727`, and its 54 required checkpoint identities passed without skips.

The guarded full server run at immutable clean `96ab5403` finished with 2,341 passed, zero failed and 17 skipped. Four of those
skips were a supplied engine-path mistake; the separate corrected-root run passed all four without skips. This is 2,345 unique
passing tests and thirteen still unverified. Native cases used the explicitly recorded prior `eeb3039d` binary; they are not
a matching final-build receipt. The earlier stdin-launched run failed five multiprocessing cases; that receipt is retained and
all five passed under the reloadable file launcher.

## Current-main reconciliation

The captain authorized a local main-to-PR4 sync and keeping the base current. The first new base is
`dfe0d1a448f58dfbf9bffcec9a287c0e21c6ab39`, which merged PR3 motion; fourteen conflicts cover shared directives, release
mirrors, licences, registry/docs, removed-loop tests and publication controls. The reconciliation preserves motion tools
and Capabilities without restoring the removed provider loop, retains exact path/URL attribution instead of widening
global hosts, and regenerates skill mirrors and tool docs from their authoritative sources. Both parents' anneal rows and
licence provenance remain. Relevant unknown-RPC correlation/usability coverage moves to the supported engine MCP path.

Review also found that a local motion tool runs in a separate MCP request from the island/native Hermes turn. Stop now
cancels and joins the stopped unit's transient tool tasks, fences admission during cleanup, returns paired cancellation
errors and preserves other units. The real Front/MCP blocked-motion control was RED before the repair; five causal
lifecycle cases passed afterward, including the live island-task path. These tests use deterministic local motion mocks;
real Chromium checks and final source/native/full-suite evidence are recorded separately. No private teaser is substituted.
The available Chromium 151.0.7922.173 browser opt-in diagnostic was RED: 6 passed, 14 failed, no skips. Six production
render cases aborted because the SUID helper is not root-owned; eight containment cases were blocked before their assertions
by managed file-URL policy. No sandbox, helper ownership or managed-policy control was changed. The three original outside-
repository teaser cases were not run because their exact fixture is unavailable. These are retained environment/proof gaps,
not passing acceptance; a skipped default opt-in does not erase the separately observed RED diagnostic.

## Remaining acceptance and decisions

* Saved worker mode and service are separate and the configured production factory consumes the worker resolution. The initial
  service ruling is settled: it follows the parent implicitly until explicitly changed, after which the worker override stays
  pinned. The compatibility mapping now preserves explicit worker choices through parent-only preference, environment and
  dialog updates, with 165 focused Choices/provider/wiring checks passing and 20 pre-fix mapping failures retained.
* The historical checkpoints above retain their exact matching evidence. After the E1.6 seam/diagnostic correction, complete
  the full client/server suites and exact final published-head CI; retain a new matching build and rerun the required native/
  runtime checks against that candidate. No historical result is silently relabelled as proof of the later source head.
* Selected services and supported MAIN/worker harnesses still require real account-backed scene-tool, interrupt, image and
  session-record acceptance. Unsupported worker routes refuse; this does not imply all seven worker routes are qualified.
  Cursor's explicit image refusal must be tested as a refusal. Offline native Hermes worker discovery/reload/reconnect,
  installed-helper and herdr startup proof is recorded in [pr4-worker-isolation.md](pr4-worker-isolation.md); the earlier
  persistent connector approval gap is resolved. Grok's exclusive worker candidate remains gated on its dedicated native
  policy/helper/herdr proof. Workflow `38013110045` completed FAIL before acceptance: stdio ACP timed out at 20 seconds and
  loopback/`/dev/null` permission failures occurred after passing dependency/artifact/herdr/controlled steps. The retained
  artifact is under diagnosis; readiness is not enabled. None of these offline checks grants real
  account execution or proves provider-backed worker calls. Codex bearer transport is the established environment seam.
* The Sign in with ChatGPT terms reading is complete. Captain acceptance and real-account authorization are separate and
  are not inferred. Q1's consent/probe/serializer implementation, committed at `40447655`, has the overlapping focused, pinned and 211-check
  applied-source passes stated above; final full-source/new-build and real-account execution remain pending. B5 disclosure
  is implemented in the committed `40447655` candidate; its native/account proof is still NOT RUN.
* R3/Q3 Context now has typed explicit project overrides, exact pinned defaults, user-only guarded client controls, no default
  writes, and model-window provenance. The native pin synchronizes compression settings before the next normal turn and
  rereads auxiliary compression routing per call; the earlier blanket live-reload blocker was incorrect. Context writes are
  serialized with capability refresh, preserving capability changes and coherent config. Explicit selected-service summaries
  use existing Choices, auth, privacy, spend and gateway lifetime checks for main and live owned worker bindings; the normal
  worker service remains pinned. Candidate checks passed 172 with four native checks not run; root server focus passed 149
  without skips and client focus passed 22. Pinned-source causal tests execute actual synchronization function bodies with
  loader/provider/runtime edges stubbed; they are not actual native-process or account proof. Matching full/native verification
  remains owed. `/model --once` defers adoption, and manual `/compress` before a normal turn can retain earlier threshold/recent
  settings. No next-reopen-only contract was substituted. The A0/A1/Q14 helper ruling is now settled: main-only delegation,
  cron and background preferences default off, and each experimental enablement carries an untested-layering warning.
  Workers keep all three disabled. This is a scoped native-helper exception, not proof of account-backed layering.

* The captain settled Q2: soft-hide native ended sessions after 30 days, cap visible ended history at 200, and preserve resumable
  records. This is a global visibility cap across recorded owned native homes; a two-home native control caught and corrected
  the initial per-home interpretation. Startup and periodic maintenance now call pinned native SessionDB helpers over recorded
  owned homes, without a second conversation store. Config preservation shares the Context/capabilities lock. The candidate's
  47 focused and four actual native controls passed without skips; final root qualification is still required. Selection is a
  native ended-tip snapshot, so a concurrent resume can change visibility without ending its process or deleting messages.
  The pin's default destructive pruning and unended automatic archive are not this policy. No second Lampway conversation
  store is introduced. R5 explicitly supersedes parked turns, so the old 24-hour parked TTL is not
  a separate acceptance requirement under this pane architecture.

No force push, pull-request merge, deployment, paid provider call, account credential transfer, user desktop operation or private asset
upload was performed by this cloud crew. User originals were not purged; image-expiry tests use their own temporary files.
