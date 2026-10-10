<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 worker qualification, images and native skill review

## Latest complete source-suite result

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

This report distinguishes the documentation-freeze candidate from historical receipts. Earlier published PR4 `7b5faed6` had runtime identical to frozen `7bf02b8c`: full server **3,073 PASS, 31 NOT RUN**, in **1,089.575 seconds**.
The existing `84d896f328512d438bcc9d88f71e7cf9f8ea10de` application binary is explicitly historical. Q1 consent/probe/serializer changes, subsequently committed at `40447655`, passed 167 focused, 98 pinned, then 211 applied-source checks in 12.29 seconds. The runs
overlap and are not summed as unique checks. Final full-source/new-build verification remains pending.
Final published-head source, CI, matching build and complete client receipts are separate acceptance evidence. Earlier native
receipts are not relabelled as proof of the changed candidate.

This report distinguishes worker-only isolation from MAIN connectivity and from account-backed acceptance. MAIN retains the user's native configuration, persona, providers and tools. Workers retain native built-ins and persona but may discover only the owned Lampway connector. Unsupported workers refuse before run activation, jobs, owned files or panes, including with a stale saved readiness snapshot.

| Harness | Worker route | Evidence and limit |
|---|---|---|
| Lampway Hermes | Existing owned Mode 1 engine | Existing pinned-engine native proof; explicit worker qualification remains enabled. |
| Claude Code 2.1.293 | Native strict MCP configuration | Actual offline baseline discovered global, project, plugin and worker MCP; strict worker launch discovered only the worker. Native auth and persona preserved. |
| Pi 1.0.4 | Public native replacement MCP extension; native MCP disabled | Actual offline baseline discovered global, project and early/late extension MCP; worker launch discovered only the worker. Missing worker config connected nothing. Auth, settings and persona preserved. MAIN requires stable 0.99.0 or newer; workers require stable 1.0.4 or newer. |
| Your Hermes 0.21.5, release 2026.9.24 | Owned Python startup guard, native gateway handoff | Actual discovery, reload, reconnect, lower transport admission, native console/gateway preflight and herdr TUI/gateway startup passed. Normal interpreter and installed helper required; unsupported overrides refuse. Native built-ins and persona preserved. One initial teardown retained a D-Bus child; that failed run is retained separately from the clean rerun. |
| Grok 1.0.46 | Candidate private namespace policy layers and hard-bound installed helper | Controlled refusal and metadata tests pass. Native policy intersection, exact catalogue, helper rebind/unbind and native herdr interruption/cleanup require the dedicated CI job. Worker readiness remains disabled pending that proof; candidate workflow `38013110045` completed FAIL before acceptance; the retained artifact is under diagnosis, with no readiness enablement. No host policy/security change or user connector installation is performed. |
| Codex, Cursor, OpenCode | Refused | No qualified exclusive discovery route preserving native behavior. MAIN remains available. Refusal is a support limitation, not proof of completed worker execution. |

Cursor's worker-isolation provenance is its official [CLI MCP configuration documentation](https://cursor.com/docs/cli/mcp)
and the inspected public installed runtime `cursor-agent 2026.10.01-e373342`. That runtime loads root `plugin.json` and
`.mcp.json` and passes `pluginMcpService` into the agent's MCP manager. The documentation describes merged global, project,
parent and plugin sources; `--plugin-dir` adds the owned pane entries without proving exclusive discovery. The full URL
is retained here as bibliography, outside shipped source. It grants no runtime retrieval permission and changes neither
MAIN binding nor the worker refusal. Account-backed execution remains unverified.

The native-helper ruling is settled: main Mode 1 exposes three separate experimental preferences for delegation, cron and
background agents, all default off with an untested-layering warning. Swarm workers keep all three off. Hermes worker
isolation is implemented and proved by the offline native scopes below; installing its owned connector is not a pending
approval question. These checks do not qualify an actual bound provider/account turn. Context and Q2 native history
visibility are present, with matching final-head/build qualification still pending.

Each worker validates its single direct swarm binding before launch. Bearers remain in owned configuration or the established environment seam, never task argv or Grok boundary metadata. Codex specifically uses the established bearer environment seam. Grok tasks use one literal `--task=TEXT` argument through native `wrap`, including leading hyphens and shell characters.

Generic selection, manager and timeout tests now use a qualified Claude worker where their previous Codex-positive assumption contradicted exclusive discovery. Codex selection remains covered by explicit refusal with its saved choice unchanged and no fallback to the parent. Pi fixtures explicitly represent supported 1.0.4. Token secrecy, task, independent choice, timeout precedence and MAIN wiring assertions remain in place.

Account/provider-backed tool calls, images, interruption and session records are not proved by these offline fixtures. Final source-suite, matching build and full client results must be reported for their exact final head separately; earlier PR4 receipts are historical evidence and are not relabeled.

## Selected-provider images

The gateway now preserves native user attachments and screenshot tool-result images as typed neutral content: bytes, MIME,
captions and ordering survive to Anthropic and OpenAI-compatible request serializers. Vision follows the selected service/model:
MAIN is resolved per request, while worker and named-summary choices retain independent captured support. The shared provider
is not mutated. A matching explicit false is respected; unknown support receives an omission note for this request, and
ChatGPT-plan vision remains false pending a consented live probe. Known Anthropic defaults remain available for older settings
without a vision flag. OpenAI parallel tool replies acknowledge each call before labeled image content in a single request.

The candidate image receipt is `<workspace>/scratch/pr4-gateway-images-preparation/final-receipt.json`. Its causal runs failed
five attachment/provider cases, two native screenshot-shape cases and one selected MAIN/worker case before repair. The focused
final run passed **155 tests, zero skips, in 12.49 seconds**, covering `test_gateway_images.py`, engine gateway/wiring, providers,
Context summaries, BYOK, worker choices, ChatGPT-plan and turn context. Its log SHA-256 is
`8ffdb4dabf6abdc8c09845a6b27f539d8ffc772a7c7840d0ed051fd7dbe6b5d4`.

This used actual Anthropic SDK and OpenAI-compatible MockTransport requests with synthetic keys. Native Hermes image shapes
were derived from pinned source. It proves serialization and selection; the later native user-attachment evidence below is separate. No account-backed vision
execution ran. The full final server suite is separate acceptance work.

A later source run was interrupted as **incomplete and failed**: 1,647 passed, two failed, seven skipped, with 1,442 cases not
started. Its source fingerprint remained unchanged. The failures were the original Context test's unrelated BYOK access and
the original native test's byte-exact unknown-vision configuration assertion. The prescribed native library environment was
also absent, so the run cannot qualify final native acceptance. Its failed XML/log/receipt are retained under
`<workspace>/scratch/pr4-worker-candidate-20261010/final-source-full-server`.
The narrow repair preserves unknown native support as unset while gateway admission remains strict and reads BYOK only for
relevant providers. **170 focused tests passed, zero skips**, followed by all **13 original Context and first-native checks**
passing unchanged in 9.28 seconds under the prescribed environment. Their receipts are `compatibility-receipt.json` and
`vision-native-regression-green.xml` in the corresponding scratch evidence directories.

Actual pinned Hermes user attachments passed **two process tests in 16.99 seconds**, recorded in
`<workspace>/scratch/pr4-native-images-actual-20261010-attempt2/receipt.json`. Supported vision preserved the valid synthetic
1×1 PNG bytes, MIME and caption through real Hermes, Front and gateway to the selected provider. Unknown vision withheld the
image before the gateway; gateway omission itself is covered by the HTTP regression. Source hashes stayed unchanged, egress
logs stayed empty and all four recorded owned PID/start identities were absent after teardown. An earlier setup-only attempt
failed before any app or pane because its scratch parent directory was absent; its two errors remain preserved. This evidence
uses the local candidate and earlier binary, not a matching final build. TUI display, native screenshot tool turns and account
vision were not witnessed by that historical attachment packet; the later follow-up below resolves only its TUI gap.

Grok's proof driver now attacks the installed canonical helper and retains exact child identities through early ACP exit.
The original early-exit cleanup control failed; three permanent in-process controls pass. The combined boundary, naming,
readiness and cleanup run passed **53 tests, zero skips**. Workflow checkout and artifact naming use the authored PR head.
These controlled repairs do not qualify the unrun native Grok boundary.

## Later native image follow-up and Q1 status

The actual TUI/native-MCP follow-up at `7bf02b8c` passed **two tests in 19.78 seconds**, recorded in
`<workspace>/scratch/pr4-native-image-followup-actual-20261011-attempt2/receipt.json`. The actual TUI displayed the caption,
filename and provider answer. A synthetic owned generic native MCP tool returned Text/Image/Text blocks: the native layer
cached the exact PNG bytes and preserved MEDIA text, before/after captions and paired call IDs through Front/gateway/provider.
This generic MCP path did **not** promote its cached image to typed model-image content. It is not an actual built-Blender
screenshot/tool-image acceptance receipt. All five recorded owned PID/start identities were absent after cleanup; previous
failed cleanup/zombie packets remain retained separately. This used the historical application build and pinned Hermes,
with played herdr and offline synthetic fixtures; it proves neither a new build nor a real account.

The Sign in with ChatGPT terms were fetched and read, closing the former fetch/research gap. The retained reading is
`<workspace>/scratch/pr4-siwc-terms-reading.md`; captain acceptance and account authorization are not implied. The Q1
implementation committed at `40447655` includes separate human consent, a fixed synthetic vision request, scope-bound receipts and serializer controls.
Its 167 focused and 98 pinned passes are offline evidence. The later applied-source Q1 run passed **211 checks in 12.29
seconds**, retained in `<workspace>/scratch/pr4-q1-final-source-focused-retry.xml`; these overlapping runs are not added.
The first attempt's two collection import errors remain retained; the retry corrected relative fixture imports. Final
full-source/new-build checks and every real-account probe remain **NOT RUN**.
B5's first-launch disclosure is implemented and committed at `40447655`; its offline controls and pending final proof are
recorded below.

The later actual pinned-native receipt-adoption scenario passed **one test in 23.47 seconds** at the reviewed local
`7b5faed6` source, recorded in `<workspace>/scratch/pr4-native-receipt-adoption-actual-20261011/receipt.json`.
Genuine native `vision_analyze` on an owned synthetic PNG succeeded with support enabled: the typed tool-result image bytes,
MIME and caption reached the production Front/gateway/provider seam. The corrected native driver passed two cases in
18.00 seconds, recorded in `<workspace>/scratch/pr4-native-vision-tool-actual-20261011-attempt2/receipt.json`.
Its initial two driver `AttributeError` failures remain retained and are not a behavioral RED. Its support-false bridge-shaped
control only proved that limited refusal; fresh direct native admission evidence supersedes that negative qualification.

The direct support-false control passed **one test in 9.38 seconds**, with one other case deselected, recorded in
`<workspace>/scratch/pr4-native-vision-tool-direct-negative-20261011/receipt.json`. The actual runtime said `vision_analyze`
did not exist; no auxiliary fallback was entered, no image bytes reached the selected provider and no egress row was written.
All fourteen recorded owned identities in the latest aggregate recheck were absent. These scenarios use actual pinned
serve/TUI with production Front/gateway, played herdr, synthetic providers/auth/receipts and owned image files. They do not
prove a real account, an actual built-Blender screenshot or a matching new application build. Generic MCP MEDIA caching
remains separately qualified and is not relabelled as typed promotion.

Grok's later toy-plugin probe reached actual native MCP `initialize` successfully. The overall probe failed because vendor
cold-start modified native cache/config; production QA now compares a warmed baseline. Initialization alone does not prove
the exclusive catalogue, boundary, cleanup or account path. No full repaired CI has completed, and worker readiness remains
false. B5's causal nonce defects are repaired in the committed `40447655` candidate; this does not establish native/account
first-launch qualification.

## B5 first-launch disclosure

Committed `40447655` now implements the notice and durable per-harness human acknowledgement. Causal REDs for
existing-pane nonce reuse and cross-endpoint/scope reuse were repaired. Route-off and readiness refusals happen before the
notice guard and owned writes. Fresh acknowledgements require an auth/path/project/operation-bound, one-use nonce; client
controls cover native UI cancel, script origin and stale scene identity. **58 client checks passed**. The final synthetic
server focus passed **178**, with zero failures or skips, recorded in
`<workspace>/scratch/pr4-b5-launch-notice/server-focused.xml`. A separate printable-identity admission recheck passed **28**,
with zero failures or skips, in `admission-final.xml` in that directory. These focused runs overlap and are not summed.
Native first-launch UI/account, matching build and whole-client checks remain NOT RUN. The `40447655` full-source suite
failed as recorded above; the repaired-candidate rerun is pending.

Only Claude Code 2.1.293's confirmed signed-in status-JSON email is displayed, bounded to printable output; other harness
identities are UNKNOWN. Offline synthetic identity fixtures do not establish real-account acceptance.

## Human native skill review

Q8 now retains native staging when `skills.write` is enabled. From the island, use `/skills pending`, then `/skills diff <id>`
to see the proposed content; explicitly send `/skills approve <id>` or `/skills reject <id>`. Each ID is eight lowercase hex
characters. These commands call the bound native session's existing `slash.exec` and show its captured output in the normal
transcript, without a model turn or a second skill, pending or approval store. Approval requires `skills.write` enabled for that
pane's bound project. Pending, diff and reject remain available with writes off. Agent/MCP/worker and cross-origin sockets,
aliases, bulk forms, gate toggles and extra arguments refuse. Finish or stop an active turn and resolve its outstanding question
before reviewing; review commands never become steer or a question answer.

Causal tests first showed 18 wrapper/guard failures, two actual pinned-helper failures where enabling writes immediately created
`SKILL.md`, and one existing-pane reconnect failure. The targeted skill/front/config run then passed **101 tests**, including
28 new skill-review cases. This includes in-process pinned native staging, full diff, human apply/reject, other-home isolation,
socket identity, bound-project capability checks and revocation during refresh.

The process receipt is `<workspace>/scratch/pr4-skill-review-native/receipt.json`; `run1.log` and its failure receipt preserve an
initial scratch-harness result-shape error. Corrected run 2 passed; refinement `run3.log`/`run3.xml` passed **one process scenario
in 24.49 seconds**. Actual `Front.drive` reached native `slash.exec`, native CLI helpers and the native pending store in nine
review turns across two owned Mode 1 units. The second unit could not list, diff or approve the first unit's pending write.
Applying the original produced exact bytes with SHA-256
`f481795c2f13124b9e8dcc571c9f5017bcbf250fbcc03f37bf2e263ecc0d45ab`; rejecting its staged edit preserved those bytes. Review caused
no model requests or outbound sends. No recorded PID/start-tick identity remained live after fixture shutdown; six descendant
identities remained as zombies at the immediate check, as recorded separately from four absent identities.

The Lampway server, Mode 1 wrapper, Hermes serve, slash worker and TUI were real, using pinned Hermes `v2026.9.24`
(`f97608f178d1ffeca59860195ab7da295f7c8e5f`), synthetic skills and a local scripted model. Herdr transport was played. This is
native process evidence for the review seam, not built Blender presentation or real-account acceptance.

## Candidate acceptance still required

| Check | Current candidate status |
|---|---|
| Complete source server suite | **FAIL** at committed `40447655`: 3,149 PASS, 27 FAIL, 31 SKIP/NOT RUN, 1,242.051 seconds. Repaired-candidate rerun remains NOT RUN; frozen `7bf02b8c` is historical. |
| Matching final build and complete built-client suite | **NOT RUN** for this candidate; the published-head receipts are historical. |
| Native Hermes images and receipt adoption | Attachment/TUI/generic-MCP, pinned receipt adoption, supported native `vision_analyze` and direct unavailable-tool controls **PASS** only in their stated offline scopes. Generic MCP typed promotion is absent. Matching build, actual Blender screenshot turn and account vision remain **NOT RUN**. |
| Account-backed tool calls, vision, interruption and session records across selected services/harnesses | **NOT RUN**; no provider/account or paid call was made by these fixtures. |
| Grok candidate native policy/helper/herdr CI | Workflow `38013110045` **FAIL** before acceptance; dependency/artifact/herdr/controlled steps passed, but stdio ACP timed out at 20 seconds and loopback/`/dev/null` permission failures occurred. Artifact retained; later toy-plugin initialize passed but the overall cold-start probe failed. Warmed-baseline QA awaits full repaired CI; readiness remains false. |
| Production Chromium sandbox in this container | **UNVERIFIED**; the synthetic `/usr/bin/chromium` scene closed its DevTools pipe before capture. |

The browser baseline receipt `browser-baseline-source.json` records that motion `frames.py` and its test are byte-identical to
published `84d896f3`. A separate owned test-only no-sandbox fixture still failed local-file navigation with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. Read-only managed-policy metadata showed a blanket URL block without a file allowance;
no policy values were copied, and no browser-policy bypass or host security change was performed. Browser acceptance needs a
permitted environment and remains separate from passing source tests.

The historical tables and packets retain their then-current results; later resolution notes above supersede their old TUI
and connector-approval gaps without rewriting the measurements. The known unchanged LP4 material calibration still failed
at 240 seconds; no passing remedy is claimed. These statuses describe the candidate at this report's documentation freeze. A subsequent final-head receipt must identify the
exact source/build it tested and preserve failures and unrun checks.

## Native YAML readback repair

The actual pinned native `/personality concise` command at source `b6bbea0c` wrote valid YAML that the server's JSON-scalar
subset reader rejected. Production Context saves could fail before writes, and capability rerenders could keep stale config.
The repair accepts safe mapping-only native YAML and declares PyYAML as a production dependency. Context edits preserve
native settings and synthetic gateway/MCP tokens; rerenders retain `display`, root `personalities` and `agent.personalities`,
including later-agent precedence, while rebuilding controlled policy from current choices. Unsafe tags, recursive aliases,
unsupported data and malformed retained feature/personality mappings refuse before writes.

Source controls retained seven causal failures, then four additional failures for agent-level personality definitions.
The repaired focused packet passed **45 tests without failures or skips**, with process, socket and signal calls refused.
Receipts are under `<workspace>/scratch/pr4-native-yaml-candidate` and `.../pr4-native-yaml-agent-personalities-followup`.
This is source proof. The separate native-only packet at `b6bbea0c` retained **four failures in 138.61 seconds**: external and
own-terminal Undo left stale rows, and the next model request after personality selection omitted Lampway guidance. All eight
recorded process identities were absent after cleanup. Those failures are retained in
`<workspace>/scratch/pr4-b6bbea0c-native-history-personality-diagnostic-attempt2`; this readback repair alone does not close them
or qualify a matching application build, whole-client suite or account-backed acceptance.

## Native personality and history-display compatibility

The owned startup/pivot hooks compose Lampway guidance beside the native personality and preloaded skills, without changing
native choice, pivot text, persistence or command count. A successful native Undo emits complete native session information;
notification failure does not fail or repeat a committed Undo. A read-only snapshot uses the existing native history projection
and locked revision. The terminal extension rejects late replies across sessions, active turns and gateway resets, and retains
the native command and visible acknowledgement. It introduces no separate transcript or agent loop.

The normal engine prebuild checks two exact pinned source hashes and all replacement anchors before applying this display
extension in its own copy. Its final manifest records original/patched source, helper and patcher hashes; the submodule and
generated bundles are not edited directly. Focused controls passed **113 tests, zero failures and skips**, including explicit
pure TypeScript compilation, controller races, native rebinding and build fixtures. Initial prompt/history causal failures,
fixture mistakes and compiler attempts are retained under `<workspace>/scratch/pr4-hermes-*`.

This is source/control proof. The normal engine rebuild, four actual terminal diagnostic repeats, matching application build,
complete client suite and account acceptance remain NOT RUN at this documentation freeze. The original four native failures
above remain historical evidence until a separately identified repaired native run measures the result.
