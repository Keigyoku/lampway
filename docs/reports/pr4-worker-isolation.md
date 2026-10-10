<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 worker qualification, images and native skill review

This report records the repaired candidate based on published head `84d896f328512d438bcc9d88f71e7cf9f8ea10de`.
Final published-head source, CI and build receipts are separate acceptance evidence. Earlier exact-head native receipts remain
historical evidence; they do not qualify the changed candidate.

This report distinguishes worker-only isolation from MAIN connectivity and from account-backed acceptance. MAIN retains the user's native configuration, persona, providers and tools. Workers retain native built-ins and persona but may discover only the owned Lampway connector. Unsupported workers refuse before run activation, jobs, owned files or panes, including with a stale saved readiness snapshot.

| Harness | Worker route | Evidence and limit |
|---|---|---|
| Lampway Hermes | Existing owned Mode 1 engine | Existing pinned-engine native proof; explicit worker qualification remains enabled. |
| Claude Code 2.1.293 | Native strict MCP configuration | Actual offline baseline discovered global, project, plugin and worker MCP; strict worker launch discovered only the worker. Native auth and persona preserved. |
| Pi 1.0.4 | Public native replacement MCP extension; native MCP disabled | Actual offline baseline discovered global, project and early/late extension MCP; worker launch discovered only the worker. Missing worker config connected nothing. Auth, settings and persona preserved. MAIN requires stable 0.99.0 or newer; workers require stable 1.0.4 or newer. |
| Your Hermes 0.21.5, release 2026.9.24 | Owned Python startup guard, native gateway handoff | Actual discovery, reload, reconnect, lower transport admission, native console/gateway preflight and herdr TUI/gateway startup passed. Normal interpreter and installed helper required; unsupported overrides refuse. Native built-ins and persona preserved. One initial teardown retained a D-Bus child; that failed run is retained separately from the clean rerun. |
| Grok 1.0.46 | Candidate private namespace policy layers and hard-bound installed helper | Controlled refusal and metadata tests pass. Native policy intersection, exact catalogue, helper rebind/unbind and native herdr interruption/cleanup require the dedicated CI job. Worker readiness remains disabled pending that proof. No host policy/security change or user connector installation is performed. |
| Codex, Cursor, OpenCode | Refused | No qualified exclusive discovery route preserving native behavior. MAIN remains available. Refusal is a support limitation, not proof of completed worker execution. |

Each worker validates its single direct swarm binding before launch. Bearers remain in owned configuration or the established environment seam, never task argv or Grok boundary metadata. Grok tasks use one literal `--task=TEXT` argument through native `wrap`, including leading hyphens and shell characters.

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
vision were not witnessed.

Grok's proof driver now attacks the installed canonical helper and retains exact child identities through early ACP exit.
The original early-exit cleanup control failed; three permanent in-process controls pass. The combined boundary, naming,
readiness and cleanup run passed **53 tests, zero skips**. Workflow checkout and artifact naming use the authored PR head.
These controlled repairs do not qualify the unrun native Grok boundary.

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
| Final full server suite after all repairs and documentation freeze | **NOT RUN**; focused passes do not substitute for it. |
| Matching final build and complete built-client suite | **NOT RUN** for this candidate; the published-head receipts are historical. |
| Native Hermes user attachment | **PASS** for two local-candidate process tests; matching build, TUI display, native screenshot tool turn and account vision remain **NOT RUN**. |
| Account-backed tool calls, vision, interruption and session records across selected services/harnesses | **NOT RUN**; no provider/account or paid call was made by these fixtures. |
| Grok candidate native policy/helper/herdr CI | **NOT RUN**; worker readiness remains disabled pending that dedicated proof. |
| Production Chromium sandbox in this container | **UNVERIFIED**; the synthetic `/usr/bin/chromium` scene closed its DevTools pipe before capture. |

The browser baseline receipt `browser-baseline-source.json` records that motion `frames.py` and its test are byte-identical to
published `84d896f3`. A separate owned test-only no-sandbox fixture still failed local-file navigation with
`net::ERR_BLOCKED_BY_ADMINISTRATOR`. Read-only managed-policy metadata showed a blanket URL block without a file allowance;
no policy values were copied, and no browser-policy bypass or host security change was performed. Browser acceptance needs a
permitted environment and remains separate from passing source tests.

These statuses describe the candidate at this report's documentation freeze. A subsequent final-head receipt must identify the
exact source/build it tested and preserve failures and unrun checks.
