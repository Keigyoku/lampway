<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Acceptance, evidence and open requirements

## Evidence ledger

The [PR3 hardening report](https://github.com/Keigyoku/lampway/blob/6d51409ad2164b133a4eb17f9ac6b11a6b9559f0/docs/reports/motion-review-hardening.md) carries commands, RED plants and measured counts. Its earlier missing-source interpretation is superseded by the captain's clarification: formal specs had never been written. These newly authorized documents establish an explicit contract; they do not retroactively certify completeness.

| Evidence | Exact tested revision and result | Limit |
|---|---|---|
| Full server | `91225a927a430958b011cff27f29341a11fa9515`: 1828 passed, 35 skipped, 0 failed; 196.94 s | Skips remain unverified; later `6d51409a` differs only in report prose |
| Public browser fixtures | Isolated HeadlessChrome 155.0.8059.39; containment/target suite 14 passed (8 real browser cases, 6 helpers) | Synthetic public assets; proves guarded loader behavior, not original-teaser acceptance |
| Original teaser | Parent-managed `042bedf3ce3d9cfc3b18b52e1b201e8b79f76278`: 29 passed, no failures/errors/skips; Chromium 153.0.8010.12, ffmpeg 8.1.2; 941.8 s | Coordinator-reported facts; private source and raw receipts are not published |
| Repeat and verify | Original teaser: all 390 RGB frame hashes and MP4/WebM bytes repeat; tool verify reproduces; 30 fps, 13 s | This exact engine/fixture result does not establish platform independence |
| Vault/publication | Original teaser filing, provenance and relations without spool; publication scans 0; 14 fixture files unchanged | Does not cover handoff mutation or spool relationship replay |
| Current PR3 CI | All five pass at `6d51409ad2164b133a4eb17f9ac6b11a6b9559f0`: [PII](https://github.com/Keigyoku/lampway/actions/runs/37695979642), [canon](https://github.com/Keigyoku/lampway/actions/runs/37695979870), [REUSE](https://github.com/Keigyoku/lampway/actions/runs/37695979700), [rail](https://github.com/Keigyoku/lampway/actions/runs/37695979934), [MCP](https://github.com/Keigyoku/lampway/actions/runs/37695979584) | CI is separate from reference/native acceptance and the later specification commit's CI |

Original teaser source code hash: `4b30a23cf619b197f67974f1b6ce70de95c6b0b9fb7d83d2abbfaaaec1e3337c`. Frame-list digest: `e6e517e036d987f639ebe59430a7f7eb4d3c0d81f5b8d2dce60d63b5e47b0645`. Opening sparse-poster warning remains. Motion runtime, original teaser tests, templates and native sources are unchanged between the teaser-tested revision and the current PR3 head; fixture-race tests and report changed. Do not relabel the teaser as a current-head run.

## Review disposition and retained regressions

All 13 initial Codex/Copilot findings were valid; duplicate findings remain listed. Replies were posted, no human thread resolved. Tests below refer to [PR3 tests at the pinned head](https://github.com/Keigyoku/lampway/tree/6d51409ad2164b133a4eb17f9ac6b11a6b9559f0/server/tests).

| Exact review | Severity / validity | Fix and falsifier |
|---|---|---|
| [4211668861](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668861) | P1 / valid | Pre-read opened-inode asset containment; `test_motion_browser_containment.py`: absolute/encoded/symlink/iframe/worker/popup loads |
| [4211668869](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668869) | P1 / valid | Exclusive runs; `test_each_render_preserves_earlier_receipt_and_media` |
| [4211668876](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668876) | P2 / valid duplicate | WebM primary and QA edges; `test_webm_only_is_the_primary_render_and_qa_parent` |
| [4211668883](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668883) | P2 / valid | Explicit empty formats refused; `test_explicit_empty_formats_is_refused` |
| [4211698563](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698563) | High / valid | Pinned no-follow output ancestors; `test_output_parent_swap_cannot_write_outside_project` plus late encoder-start swap |
| [4211698661](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698661) | High / valid duplicate | Loader containment and escaping scene-hash symlink refusal |
| [4211698745](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698745) | High / valid | NumPy contrast iteration; API-absence plants and Pillow 10.0.1 run |
| [4211698806](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698806) | Medium / valid | Wrong purpose refused before writes; `test_non_motion_template_refused_before_render_writes` |
| [4211698865](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698865) | Medium / valid | Effective defaults/version persisted; `test_effective_defaults_and_resolved_template_persist_in_receipt_and_vault` |
| [4211698931](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698931) | Medium / valid | Audit after setup, before output; missing-audit and setup-installed audit plants |
| [4211698995](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698995) | Medium / valid duplicate | WebM-only primary regression above |
| [4211699072](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211699072) | Low / valid | Animatic ignored palette removed; `test_titan_templates_refuse_unused_palette` |
| [4211699130](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211699130) | Low / valid | UI-motion ignored palette removed; same parameterized refusal plant |

Additional fixed regressions include inline-entry symlink overwrite, probe-only forbidden requests, receipt-controlled outside frame path, frame-file replacement during verify, ffmpeg 7 metadata tags, high-descriptor bash launcher, modern headless-shell target creation and browser-owned UI classification. The app-server fake-fixture race fix is `0cfba29ae5394063c99748dda09910337b647519`; PR1 integrated it at `18c00fef1254b2d63ad908a1e288708535f6cacc` (1879 server passes, 32 skips, zero failures/errors). That result is separate from combined reference acceptance.

## Open hardening requirements and owner decisions

Read-only contract audits at `6d51409a` exposed these boundaries. Synthetic orchestration reproductions below are gap evidence, not browser acceptance. No runtime fix or retained regression test was added in this specification-authoring commit.

| ID / status | Observed gap or decision | Required falsifier / closure evidence | Owner |
|---|---|---|---|
| M1 / open requirement | Caller cancellation leaves worker running; synthetic blocked-frame cancellation then release produced a receipt | Cancel during setup/capture/encode and before filing; prove owned worker/process shutdown and chosen publication/retention semantics, including live browser | PR3; captain chooses cancellation filing policy |
| M2 / open requirement | Deleting original MP4 still yields `reproduced=true` in synthetic rerender: only recorded hash is compared | Preserve current reproduction meaning; if adding artifact-integrity claim, delete/corrupt/swap original video and require checked read/hash failure | PR3; captain decides whether to add separate integrity verification |
| M3 / open requirement | Vault reopens logical paths after pinned render closes | Swap video/receipt/contact between render and capture; assert no outside bytes, checked hash identity and correct edges | PR3 with PR1 shared provenance owner |
| M4 / open requirement | Spool replay loses variant/QA edges; relation error may follow stored assets | Locked Vault → replay → all expected relationships exactly once; relation failure → explicit partial state and reconciliation | PR3 with PR1 provenance owner |
| M5 / decision | No total deadline, concurrency/queue policy, HTML/asset/receipt/CDP/output caps or CPU/memory quota | Captain sets limits and overflow behavior; hang/oversize/parallel plants enforce each chosen bound without arbitrary process kills | Captain; PR3 implementation, PR4 UI coordination |
| M6 / decision | Runtime failure leaves partial samples without receipt; cleanup failure ignored | Choose retained forensic output versus removal, then crash/cancel/cleanup-error tests report chosen state | Captain / PR3 |
| M7 / open requirement | Declared input types and runtime coercions differ; receipts/audit geometry lack strict validation/version; absolute input paths and unsanitized variable strings can persist in provenance | Invalid types, NaN/infinity, malformed receipts and omitted/nonfinite geometry must produce bounded corrective errors; retain valid older receipt policy | PR3 with PR1 schema/registry owner |
| M8 / decision | Linux-only evidence; application loader containment is narrower than OS sandbox | Choose platform/security scope; any broader promise needs isolated native execution and hostile file/executable plants | Captain / platform owner |
| M9 / open requirement | Scene inventory is not immutable; verify does not enforce code/driver/flags | Change asset mid-run and driver/flags/source before verify; report provenance differences. Decide required identity enforcement before claiming attestation | PR3; captain sets verification strength |
| M10 / open requirement | Public ToolSpec output-prefix prose is stale; template guidance is not enforced validation | Synchronize registry/generated prose to unique-run paths without changing surface; regenerate and check docs | PR3 with PR1 tool registry owner |

The captain's pending choices are specific: cancellation publication policy; partial-output retention; numeric resource caps and queue behavior; supported platforms and isolation boundary; whether verify additionally validates existing media and provenance identity. These documents choose none of those thresholds or broader promises.

## Required acceptance sequence

1. Keep observed RED and GREEN for every fix, with retained falsifiers. Run isolated motion/encoder, template/Vault, launch/egress and real Chromium loader fixtures using owned temporary directories and public assets.
2. Run full server at the exact implementation head; list skips and environment. Re-run original teaser in the coordinator's isolated environment when production changes affect it; verify hashes, both exports, warning dispositions, provenance/relations and read-only source inventory.
3. Run publication scans, generated-doc checks, rail/canon/REUSE and all exact-head CI. Attribute documentation checks and prior runtime checks to their exact heads. Retain the already-coordinated shared guard fixes; do not weaken validators or import unrelated PR1 work.
4. Obtain combined reference acceptance through parent/PR1: exact tested head, genuine matching BUILT_FROM, server/client failure and skip counts, known-red deltas and unchanged read-only shelf inventory. Cloud lacks the original shelf and genuine native provenance. No fabricated stamp, skipped fixture or historical baseline-relative GREEN closes acceptance.
5. Close all required runtime gaps or obtain an explicit scoped owner decision. Full zero-red reference acceptance remains pending; implementation, CI and documentation alone do not mean release accepted. Never merge, deploy or resolve human review threads prematurely.
