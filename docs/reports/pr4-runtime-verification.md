<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 runtime verification

This is a partial verification report for the continued agent-modes work. It is not an acceptance receipt or permission to
merge. The governing scope is [agent-modes-spec.md](agent-modes-spec.md), including the captain's decisions. Account-backed
adapter execution and exact final-head verification remain required. Historical short commit IDs below name the
pre-publication checkpoints; those unpublished commits were replayed with the required release-skill anneal before normal push.

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

## Remaining acceptance and decisions

* Saved worker mode and service are separate and the configured production factory consumes the worker resolution. The initial
  service ruling is settled: it follows the parent implicitly until explicitly changed, after which the worker override stays
  pinned. The compatibility mapping now preserves explicit worker choices through parent-only preference, environment and
  dialog updates, with 165 focused Choices/provider/wiring checks passing and 20 pre-fix mapping failures retained.
* The historical checkpoints above retain their exact matching evidence. After the E1.6 seam/diagnostic correction, complete
  the full client/server suites and exact final published-head CI; retain a new matching build and rerun the required native/
  runtime checks against that candidate. No historical result is silently relabelled as proof of the later source head.
* All seven adapters still require real account-backed scene-tool, interrupt, supported image behavior and session-record
  acceptance; Cursor currently refuses image attachment explicitly, so its required image proof must verify that refusal. No provider,
  paid-call, credential or persistent-grant authorization has been supplied. Correct sequence-shaped `mcpServers` activated
  Grok 1.0.46's primary custom-agent body and inline MCP in a network-denied synthetic first turn. Earlier mapping-shaped
  fixtures were invalid, so no primary-activation vendor defect is claimed. Primary overlays still retain unrelated global
  MCP entries, and `enabled: false` does not remove inherited entries. Symbolic variables were proven in doctor/disk config;
  inline environment placeholders arrived literally. Grok's explicit `GROK_AUTH_PATH` works but can write its auth file, while
  project MCP remains loaded: a primary-agent exclusive interface from the vendor, or the captain's B0 working-directory
  exception and explicit auth-file-use decision, is still required. Native Hermes `--toolsets` can restrict a four-server
  native/portable/project catalog to only the worker connector, but that route requires approval to install a
  persistent dedicated symbolic stdio connector/helper. These source-interface gaps are not repaired by account approval.
  Neither persistent installation nor the working-directory/auth-file exception has been accepted. A terminal opening or
  offline probe is not account acceptance.
* The final contract audit found unused R3/Q3 Context configuration and native internal-helper interpretation gaps. A separate
  PR4-only candidate has typed project overrides, displayed pinned defaults, no default writes, user-only routes and guarded
  client controls; 154 client checks and 179 combined server/adapter checks passed, with four live-engine checks not run in that
  candidate focus. It refuses live saves because the pinned runtime lacks a guarded reload of these fields, and cannot select
  an independent summarizer model through the current gateway. It is not published or accepted. The captain's ruling is pending
  on next-user-reopen application versus retaining the live-reload requirement, and on whether Hermes's native internal helpers
  may remain inside the existing pane under A0/A1/Q14. A proposed delegation restriction alone does not fence native `/bg` or
  `/btw`; no complete internal-helper isolation is claimed.

* Q2 retains approved 30-day/200-session values, but its older physical archive/live-store terms need mapping to Hermes-owned
  sessions. The pin defaults to pruning ended history at 90 days, optional soft archive at three days, and a soft in-memory
  detached-session LRU of 16; these are not proof of the approved archive policy. No second Lampway conversation store or
  silent native pruning policy was introduced. R5 explicitly supersedes parked turns, so the old 24-hour parked TTL is not
  a separate acceptance requirement under this pane architecture.

No force push, merge, deployment, paid provider call, account credential transfer, user desktop operation or private asset
upload was performed by this cloud crew. User originals were not purged; image-expiry tests use their own temporary files.
