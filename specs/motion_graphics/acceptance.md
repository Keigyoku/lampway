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
| Prior implementation CI | All five pass at `6d51409ad2164b133a4eb17f9ac6b11a6b9559f0`: [PII](https://github.com/Keigyoku/lampway/actions/runs/37695979642), [canon](https://github.com/Keigyoku/lampway/actions/runs/37695979870), [REUSE](https://github.com/Keigyoku/lampway/actions/runs/37695979700), [rail](https://github.com/Keigyoku/lampway/actions/runs/37695979934), [MCP](https://github.com/Keigyoku/lampway/actions/runs/37695979584) | CI is separate from reference/native acceptance and the later specification commit's CI |

The intermediate mandatory-hardening runtime `fe9c994bb56da34345ca6494c87ef01285f3e80b` passed 1,929 server tests with 35 skips and zero failures (264.15 s), including actual isolated Chromium fixtures. A real public DOM-ramp passed render/Vault/verify; corrupting existing WebM separately failed integrity while reproduction/provenance remained true. Final dedup-provenance admission/partial-state and direct-filing cancellation fixes followed; their targeted suite passed 49 with one skip. Final exact-head full-server results belong to the parent's handoff receipt, without relabeling this intermediate run. Normal publication is blocked by the environment's invalid existing Git credential; remote `9bce67fb` has five successful workflows, while candidate CI is pending publication. Full original-teaser/reference/native acceptance remains open.

Original teaser source code hash: `4b30a23cf619b197f67974f1b6ce70de95c6b0b9fb7d83d2abbfaaaec1e3337c`. Frame-list digest: `e6e517e036d987f639ebe59430a7f7eb4d3c0d81f5b8d2dce60d63b5e47b0645`. Opening sparse-poster warning remains. Motion runtime was unchanged through specification head `9bce67fb`; subsequent mandatory correctness changes require a fresh parent-managed original-teaser rerun. The earlier evidence remains historical. Do not relabel the teaser as a current-head run.

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

Contract audits at `6d51409a` exposed the boundaries below. Mandatory correctness hardening now addresses them with retained regression tests; exact integrated results are recorded in the hardening report. Synthetic orchestration is logic evidence, never browser acceptance.

| ID / status | Disposition | Required evidence / remaining boundary | Owner |
|---|---|---|---|
| M1 / implemented, integration validation | Per-call cancellation joins owned workers, stops only owned processes, blocks new filing admission and reports already committed assets | Real Chromium blocked setup and owned encoder tests; repeated cancellation and in-flight Vault commit regression. No new deletion policy. | PR3 |
| M2 / implemented, integration validation | Existing-media integrity is separate from receipt reproduction | Missing/corrupt/swapped video checked before and after recapture; unchanged reproduction semantics | PR3 |
| M3 / implemented, integration validation | Checked immutable media/receipt/contact bytes sealed before pinned descriptors close | Post-render path swaps and pre-seal corruption refused; contact generation hash required | PR3; narrow shared provenance coordination announced to PR1 |
| M4 / implemented, integration validation | Replay carries QA/variant relationship intents and explicit partial results | Closed Vault/replay, idempotent edges, relation/bookkeeping failure reconciliation, cancelled dedup provenance admission, corrupted/shared spool blobs | PR3 with PR1 provenance owner |
| M5 / unchanged policy boundary | No new total deadline, concurrency/queue policy or CPU/memory/disk quotas | No arbitrary limits inferred. Existing input bounds retained. A future policy change requires captain direction. | Captain |
| M6 / unchanged policy boundary | Preserve user assets and interrupted failure evidence; existing verify temporary cleanup unchanged | Cancellation and failure preserve prior output. No automatic retention/deletion changes. | Captain / PR3 |
| M7 / implemented, integration validation | Object/type/finite JSON/source exclusivity, receipt and audit validation; scene/entry provenance normalized | Invalid types, NaN/infinity, malformed receipts and geometry; untouched old receipts verified. Authored variable strings remain subject to publication scans. | PR3 |
| M8 / unchanged evidence boundary | Platform support policy unchanged; available live proof is Linux-specific | Application loader checks do not claim OS isolation. Broader native execution evidence remains unverified. | Platform owner |
| M9 / partial boundary explicit | Verify separately reports source inventory, driver and flag differences | No immutable source snapshot or signed attestation; transient mid-run edits are not exhaustively detected. A stronger promise requires a scoped decision. | PR3 / captain |
| M10 / implemented | ToolSpec/generated documentation match unique-run paths and sampled probe meaning | Generator `--check`; template declarations remain authoring guidance where not executable | PR3 |

The captain authorized the correctness changes above while preserving assets and failure evidence. Numeric resource limits, automatic retention/deletion and narrower platform support were explicitly excluded; none is introduced here. Those choices are not prerequisites for these fixes. Full reference/native acceptance and the fresh original-teaser rerun remain separate required evidence.

## Required acceptance sequence

1. Keep observed RED and GREEN for every fix, with retained falsifiers. Run isolated motion/encoder, template/Vault, launch/egress and real Chromium loader fixtures using owned temporary directories and public assets.
2. Run full server at the exact implementation head; list skips and environment. Re-run original teaser in the coordinator's isolated environment when production changes affect it; verify hashes, both exports, warning dispositions, provenance/relations and read-only source inventory.
3. Run publication scans, generated-doc checks, rail/canon/REUSE and all exact-head CI. Attribute documentation checks and prior runtime checks to their exact heads. Retain the already-coordinated shared guard fixes; do not weaken validators or import unrelated PR1 work.
4. Obtain combined reference acceptance through parent/PR1: exact tested head, genuine matching BUILT_FROM, server/client failure and skip counts, known-red deltas and unchanged read-only shelf inventory. Cloud lacks the original shelf and genuine native provenance. No fabricated stamp, skipped fixture or historical baseline-relative GREEN closes acceptance.
5. Close all required runtime gaps or obtain an explicit scoped owner decision. Full zero-red reference acceptance remains pending; implementation, CI and documentation alone do not mean release accepted. Never merge, deploy or resolve human review threads prematurely.
