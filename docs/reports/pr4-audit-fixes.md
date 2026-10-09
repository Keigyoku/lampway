<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# PR4 audit fixes A01–A07

The supplied audit tested `c2b433e11ade146dc251f9f55112258982c2d3c9`, based on
`dfe0d1a448f58dfbf9bffcec9a287c0e21c6ab39`. This change fixes its seven assigned PR4 defects;
inherited tool, input, scan and motion findings remain with PR1 under the audit's ownership rule.
The supplied sanitized logs and recorded Codex rollout are evidence, not authorization for new account or provider calls.

| Finding | Resulting behavior | Verification |
|---|---|---|
| A01: first MCP initialization raced pane registration | Persist the digest-only authenticated `starting` record before launch, transition to `live` after success, revoke before owned rollback on failure/cancellation; reconcile inspects interrupted starts. | Causal first-init HTTP401 RED becomes HTTP200 once without retry; independent disk reader and rollback controls; 96 focused passes, one fleet-witness test not run. The endpoint is production, the launch is played. |
| A02: current Codex final answer missing | Read current raw messages and optional completed TurnItems alongside legacy events; deduplicate echoes by native identities/counts, preserve distinct equal messages and tool identity, finish on task completion. | Supplied recorded commentary/final/lifecycle replay passes; official rust-v0.159.0 source shapes cover user/tool items; 17 mirror tests pass without skips. No new model turn. |
| A03: Pi without required extension API offered | Require locally verified stable Pi 0.99.0 or newer before connector readiness/activation/launch; explain incompatible or unknown versions and leave the shared CLI unchanged. | Installed 1.0.4 changelog identifies API introduction; 78 focused tests pass, including older/unknown/prerelease refusals. |
| A04: incompatible npm passed dependency check | Check installed npm against the pinned package manifest before build writes; unsupported version/constraint syntax refuses with help. | npm 11.16 refusal and compatible ranges tested; combined A04/A05 packet: 35 passes, no skips. |
| A05: shallow herdr checkout lacked release tag | Derive stable version from verified pinned Cargo.toml, reject manifest drift, require exact binary version, record success last. | Real shallow no-tags checkout with controlled compiler passes; unrelated tag and 0.9.30 lookalike controls refuse. This fixture does not claim a fresh real Cargo compilation. |
| A06: capability catalog inflated all wizard pages | Size each capability-enabled step from actual content and paginate by a fixed metadata-based row budget; ticks cannot move controls between pages, paging makes no settings writes. | Three causal RED controls, 43 focused passes; 100-capability all-enabled growth fixture verifies coverage, warning rows, stable partition and ticks. Matching native visibility proof is separate. |
| A07: fresh server test setup lacked YAML | Declare PyYAML in the test extra; preserve all native policy assertions. | Fresh isolated environment installed with the normal test extra: unchanged policy file 66 passes without skips or engine Python-path injection. |

The combined client/build focused command covers the engine and herdr scripts, onboarding, build script,
privacy gate, shipped metadata and links: **134 passes, zero skips**. Canonical `make i18n_update`,
extractor currentness and placeholder checks pass; three messages were added to 48 catalogs with all
existing translations retained. Rail and privacy self-test pass. No inline PR review findings were present;
Copilot reported its 300-file limit.

## Source and native qualification

The frozen source candidate passed the full server suite: **2,897 passes, zero failures/errors, 31 explicitly not run**, in 1,049.195 seconds. The run enabled the real pinned Hermes/herdr, local bundled models and isolated Pi 1.0.4. It used the previous c2b433e1 binary and therefore proves this server source, not a matching new native build. Before/after candidate fingerprints match. A committed-tree link and final native evidence retain this qualification.

The full standalone client, full OFF native build, real account-backed turns/interrupts/images/session
records, private assets and local GPU validation were not rerun by this audit-fix packet. Earlier receipts
remain historical and are not relabeled as acceptance of this change. Synthetic local providers grant no
paid or outbound access. New exact-head normal-build/runtime receipts and physical wizard visibility
results belong to the final integration evidence; source passes alone do not establish them.
