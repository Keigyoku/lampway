<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 worker qualification, images and native skill review

## Latest complete source-suite result

Committed source `404476557584d1e2297013b1780a9828022e1ebe` completed the full server suite with **3,149 PASS,
27 FAIL and 31 SKIP/NOT RUN** in **1,242.051 seconds**. No cases were left unstarted. The source fingerprints held unchanged,
and recorded owned cleanup had no survivors. Exact failure accounting is
`<workspace>/scratch/pr4-exact-final-head-full-server-20261011/final-failure-accounting.json`.

Twenty-five failures were legacy pane fixtures missing the required prior human harness acknowledgement. Two were long-
basetemp socket-path assertions: `test_existing_outer_socket_requires_the_exact_native_wrap_parent` and
`test_user_config_untouched`. This failed snapshot remains retained without subtracting later repairs. Q1/B5 changes
previously described as uncommitted preparation are committed at this source snapshot.

Subsequent uncommitted fixture repairs passed all 25 notice cases plus 36 fresh controls with assertions preserved. The
original two socket-path cases passed with a short temporary root: **2 PASS in 0.19 seconds**, retained in
`<workspace>/scratch/pr4-short-basetemp-original-tests.xml`. No repaired-candidate full-suite receipt exists yet. A separate
actual-app Q1 loopback-consent audit retained **1 FAIL, 2 PASS** in
`<workspace>/scratch/pr4-q1-consent-boundary-audit`. The subsequent authenticated human-client ticket/admission and UI
repairs are applied, uncommitted and frozen: **85 server PASS in 2.53 seconds**, **39 client PASS in 1.58 seconds**, with no
failures or skips, retained as `server-freeze.{log,xml}` and `client-freeze.{log,xml}` in that directory. This is focused
source proof, not a full-suite, new-build or account receipt.

Ticket/admission lifetime is 120 seconds; the browser form lasts at most 600 seconds and remains bounded by the original
JWT expiry. Scope/model binding and one-use admission are enforced; no active-JWT revocation is claimed. The client requires
its human gate, opens only the fixed local URL off-thread, uses cache-only state, surfaces errors and avoids ended-scene RNA.
Canonical i18n is frozen for three new messages across 48 PO files; all **411,057 retained translations** are unchanged,
recorded in `<workspace>/scratch/pr4-q1-i18n-20261010/receipt.json`.

The suite used the historical `84d896f3` binary. A repaired-candidate full server receipt, matching new build, complete
built-client run, final published-head CI and real-account qualification remain owed. Grok's production path-mapping repair
is now applied but uncommitted, with **73 focused PASS**; readiness remains false and no complete repaired native Grok CI
is claimed. Actual project-native Grok baseline positives failed for both fresh and Git workspaces within their bounds:
normal native startup requested `_x.ai/folder_trust/request` for the exact synthetic workspace with `configKinds=["mcp"]`.
The diagnostic rejected it and granted no trust. A source-proof proposal remains pending root/user authority; worker
readiness stays false. These later focused results do not change the failed 404 snapshot.
The earlier passing `7bf02b8c` receipt is historical and does not override this failed result. This is not acceptance.


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
