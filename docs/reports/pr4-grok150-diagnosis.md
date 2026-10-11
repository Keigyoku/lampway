<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 Grok 1.0.50 diagnosis

## Actual scope

The official Linux x86_64 artifact is Grok 1.0.50 (`c58f321264ba`),
SHA256 `c80de0155706ff2d995623887b102f2d0abd2c62b2643dea3a0cebaf7dd724d5`.
Runtime, original offline validator and CI download pin the same bytes.
No native source fork, real account or external model-provider call, trust grant or desktop run was used.
Native cases execute in an unprivileged loopback-only namespace with synthetic HOME/auth,
real installed connector, original assertions/deadlines and exact owned cleanup.
Production worker readiness remains false; human compatibility consent is separate.

## Restrictions and canonical availability

The [official restriction guide](https://github.com/xai-org/grok-build/blob/2bdd1d6a6369de0e8c68132ea4539e9abd9e14a8/crates/codegen/xai-grok-pager/docs/user-guide/09-plugins.md#restrict-which-mcp-servers-can-run)
explicitly applies allow/deny lists after merging user, project, plugin and imported
MCP configuration. URL selectors cover HTTP/SSE separately from STDIO command selectors.
Our worker requirements now deny every remote MCP URL and retain exact STDIO argv/name
constraints. This repaired the earlier missing URL restriction; loaded policy and actual
hostile endpoint noncontact are observed independently.

That exclusion does not restore the old connector after a same-name replacement is merged
and rejected. Current native tests demonstrate distinct-name HTTP/SSE updates preserve
the canonical connector and its next call; same-name updates disable it and fail the next
call. This agrees with documented post-merge filtering and is a separate Lampway worker
availability obligation. The update did not repair it.

The selected synthetic custom agent's inline canonical MCP entry does preserve it across
STDIO/HTTP/SSE hostile updates in the restricted ACP phase. Named references and marker-only
controls do not. This is limited explicit-file-profile evidence; default/builtin/plugin
profiles, live switching, load/resume and SDK rebuild routes are unqualified. Native
`_x.ai/session/info` reports the selected agent name, without definition path/content attestation.
Public source mirror `2bdd1d6a` is version 1.0.45, not matching 1.0.50 source.

## Startup and interruption

[Actual cbbf6fb7 native run](https://github.com/Keigyoku/lampway/actions/runs/38165345673)
preserves both the original HTTP 503 diagnostic and a separately selected HTTP 400 diagnostic:

| Case | Actual result | Interpretation |
|---|---|---|
| Original STDIO/loopback | HTTP same-name canonical admission FAIL | Later original cases not reached |
| Independent distinct-name HTTP/SSE | Canonical retention/next-call MET | Limited fresh-case scope |
| Independent same-name HTTP/SSE | Canonical retention/next-call FAIL | Exclusion alone is insufficient |
| Selected inline agent, HTTP 503 | Warmup/restricted ACP PASS; original 10-second startup FAIL | Actual TUI retries HTTP 503 at attempt 3; no idle admission |
| Selected inline agent, HTTP 400 | Warmup/restricted ACP PASS; startup reaches idle with interactive readiness | Permanent local refusal removes retry-induced startup failure |
| Selected inline agent, HTTP 400 Ctrl+C | Original eight-second pending-request-close assertion FAIL | Real pending request; frontend returns idle and restores prompt, request closure appears only later |

The earlier fixture held its initial request for 15 seconds before a 10-second start admission; this was
repaired by holding a second native prompt only after genuine startup. Continuous owned
PID/start capture and adoption-aware zombie reaping repaired the prior cleanup failure.
Failure witnesses now read only known owned panes/names before close, preserving the
primary failure even when witnessing/saving fails. All original 19 pane checks, assertions,
the ACP body and numeric deadlines remain; the original HTTPFixture body is unchanged.

The HTTP 503 rejection was an incorrect way to demand prompt completion within initial idle
admission: native retrying is now directly witnessed. The HTTP 400 variant isolates that fixture
problem while retaining the original HTTP 503 failure. After one Ctrl+C, the frontend returns to idle with interactive readiness and restores
the interrupted prompt to the composer. This supports receipt of the key by the native
frontend; it does not establish a semantic cancellation acknowledgement or transport closure. UI idle does not prove HTTP request closure. These terminal events lack
per-request timestamps; do not infer precise late-closure timing from them.
HUP/TERM, hard-close and native policy intersection remain NOT RUN after this failure.

## Independent native cancellation

[Actual f4d310bf native run](https://github.com/Keigyoku/lampway/actions/runs/38167366595)
compares four fresh sessions, with a real `session/prompt` followed by the documented
`session/cancel` notification. The same original HTTP handler records actual per-request
identities, monotonic timestamps and probe/persona presence; request bodies are not retained.
Cancellation targets the returned session and the currently held persona-bearing probe.

| Case | Native prompt reply | Same request closes within eight seconds | Native retained before cleanup | Owned cleanup, including zombies |
|---|---|---|---|---|
| Unrestricted native, HTTP 503 | `cancelled`, `MidTurnAbort` | FAIL | PASS | PASS, 9 identities |
| Unrestricted native, HTTP 400 | `cancelled`, `MidTurnAbort` | FAIL | PASS | PASS, 9 identities |
| Worker boundary, HTTP 503 | `cancelled`, `MidTurnAbort` | FAIL | PASS | PASS, 6 identities |
| Worker boundary, HTTP 400 | `cancelled`, `MidTurnAbort` | FAIL | PASS | PASS, 6 identities |

Every case fails only the original peer-close obligation. Replies have no failure; protected
inputs and constructed native persona/auth hashes stay unchanged, with no monitor or cleanup
errors. No matching request-close event exists in any before-cleanup snapshot. Matching close
events appear in the after-cleanup snapshots at 8.104, 8.068, 8.067 and 8.066 seconds after
the cancellation was sent. Cleanup had already started; these are not successful cancellation
latencies. Native frame capture has no timestamps, so do not infer cancelled-reply latency.

This reproduces semantic cancellation without timely HTTP peer closure on native 1.0.50
without the worker boundary or terminal wrapper. The HTTP request is held before response
headers; streaming responses, real providers and later tool/permission operations are not
qualified by this fixture. An HTTP 400 startup fixture or a terminal-key change cannot repair
the separately reproduced native condition.

The [ACP cancellation specification](https://agentclientprotocol.com/protocol/v1/prompt-turn#cancellation)
supports this notification shape and asks the agent to abort model requests and tools promptly.
The eight-second bound is Lampway's unchanged QA requirement; it is not a literal protocol
guarantee. Public native 1.0.45 source sends cancellation to the running task and aborts it;
the prompt releases the dispatch lock before awaiting completion. TUI cancellation uses the
same notification with optional rewind metadata. The running task awaits the sampler's
submit-and-collect future, whose intended drop guard is mentioned in the public source.
The sampler implementation is absent from the retained mirror, which is older than binary 1.0.50.
The unresolved native implementation boundary is propagation from turn abort/drop to the
already pending HTTP operation. No native transport patch or preserving adapter workaround
has been proved. Worker readiness remains false.

## Proof and remaining work

At `f4d310bfabacb1449161f95167685cb8e6717f3b`, 231 server, 95 QA and 18 documentation
controls PASS, zero skips; all seven publication gates PASS and five general CI workflows PASS. Local
owner-specific privacy patterns are unavailable; generic privacy controls passed.
The native job remains RED. Its six-root downloaded archive matches GitHub SHA256
`0a7e214465646cf94e9af8cbc8872b44ec2cff6282a96db89ece1ad3f3b28035`;
all 1,608 regular files and embedded/external manifests were verified, without extracting
symlinks. The earlier cbbf6fb7 archive remains retained with GitHub SHA256
`ae066ea14fe92299097b0109d950ff932bf935410871ac95dba9ef3fce2981e6`
and 1,131 verified regular files. Its inline cleanups PASS (13 and 15 exact PID/start identities,
including zombies in the absence check). Historical failures remain retained.

Runtime server/client Git objects are unchanged from `3ef68298`, whose full-server receipt
is 3,451 PASS / 31 original opt-in SKIP / no failures/errors; that receipt retains its original head.
A matching final application build and maintained client/native/account acceptance are
still owed. Cloud disk capacity remains below the required 16 GiB build floor. None of these
source/fixture results establish completed PR4 acceptance or native Grok worker readiness.
