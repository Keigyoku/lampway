<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# PR #3 motion review hardening

Code snapshot: `192cbaebe9d50292942bd8af2ee4d77c416a1cb5` on `lp/motion`.
Reviewed original head: `8d13560765ac68bc6f67679f098c4d3fe3428a61`.
Current main `eab73f5f5a77780a7690378eec6c5dd44b468589` was merged normally, preserving both histories.

All 13 inline findings from the Codex and Copilot reviews are valid. Duplicate reports are retained below with their exact links.
The disposition describes tested code; remote publication, thread replies, exact-head CI and reference acceptance are separate gates.

| Review | Severity | Validity | Action and regression evidence |
|---|---|---|---|
| [4211668861](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668861) | P1 | Valid | Intercept file loads before Chromium receives bytes; decode the URI, resolve containment, and check the opened inode. Live absolute, encoded, symlink, iframe, popup and worker falsifiers in `test_motion_browser_containment.py`. |
| [4211668869](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668869) | P1 | Valid | Exclusive run directories preserve previous receipts and media for identical and changed configurations. Repeated-render and verify regression in `test_motion_output_hardening.py`. |
| [4211668876](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668876) | P2 | Valid; duplicate of 4211698995 | MP4 is primary when present, otherwise WebM; the primary is render/main and QA assets derive from it. WebM-only Vault regression. |
| [4211668883](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211668883) | P2 | Valid | Empty formats are refused instead of becoming both defaults. Explicit-empty regression. |
| [4211698563](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698563) | High | Valid | No-follow directory descriptors pin output ancestors and the new run. Encoder, remux and probe inherit only the output descriptor. Early swap regression and independent late encoder-start swap falsifier prevent outside writes/publication. |
| [4211698661](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698661) | High | Valid; duplicate of 4211668861 | Same pre-read browser containment fix; scene hashing also rejects escaping symlinks. |
| [4211698745](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698745) | High | Valid | Contrast pixel iteration uses the existing NumPy dependency. API-absence plants and actual Pillow 10.0.1 run pass. |
| [4211698806](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698806) | Medium | Valid | Resolve and refuse non-motion purpose before render writes. Wrong-purpose regression. |
| [4211698865](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698865) | Medium | Valid | Persist effective default/override variables and resolved template version into receipt and Vault provenance. Regression checks receipt, generation and prompt asset. |
| [4211698931](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698931) | Medium | Valid | Require audit presence before output creation and validate sampled audit text/marks arrays. Missing-audit live and adapter regressions. |
| [4211698995](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211698995) | Medium | Valid; duplicate of 4211668876 | WebM-only primary and QA derivation fix described above. |
| [4211699072](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211699072) | Low | Valid | Remove ignored palette variable from TITAN animatic; board preservation remains authoritative. Removed-variable refusal regression. |
| [4211699130](https://github.com/Keigyoku/lampway/pull/3#discussion_r4211699130) | Low | Valid | Remove ignored Lampway palette from TITAN UI-motion; TITAN tokens_source remains authoritative. Removed-variable refusal regression. |

No finding was rejected or treated as stale. No human thread was resolved.

## Additional regressions found and fixed

- Inline scene entry symlinks could be written before refusal; the regression observes the external file's mtime.
- A request appearing only in the fresh probe could escape the network result; both passes now contribute forbidden requests.
- Verify trusted a receipt-controlled frame path and later reread it through a raceable pathname. Checked regular-file reads precede rerender, and checked rereads detect replacement.
- ffmpeg 7 adds stream encoder metadata after metadata options. A conditional local stream-copy remux removes it, checked afterwards. Already-clean engines keep their original bytes.
- The pipe launcher failed on dash with high-numbered descriptors; bash handles the inherited descriptors. Modern headless-shell target creation no longer receives unsupported dimensions.
- Browser-owned UI targets are distinguished from scene loaders. Workers remain paused/refused because their targets do not expose Fetch interception.

The renderer remains sequential from frame zero. The determinism probe remains a fresh browser and preserves sampled audit timing. No socket, provider, spend, pricing or product expansion was added. The parent assigned the single shared local `motion/encode.py:Encoder.finish` launch declaration; no network/spend route changed.

## Measured validation

- Baseline browser RED: nine containment/audit/scene-hash plants failed to refuse. Launcher compatibility alone was applied to make that baseline executable.
- Isolated public-fixture Chromium: 14 containment/target tests pass on HeadlessChrome 155.0.8059.39. The allowed SVG test asserts the actual green pixel.
- Output/probe/verify hardening: 11 tests pass; each reported defect was observed failing before its fix. These use the fake capture seam and real ffmpeg; they are unit/encoder evidence, not browser acceptance.
- Pillow checks: 15 tests pass on Pillow 12.3.0 and actual Pillow 10.0.1.
- Template/library review tests: 37 pass.
- Launch audit: 7 pass. Egress suite: 37 pass.
- Existing motion plus output and browser hardening run: 49 pass, 3 teaser tests skip (before the final extra verify-race and UI classification tests).
- Rail and canon pass locally; generated tool documentation is current. Changed motion code/tests have zero prepublish findings.
- Full committed-head server suite: `LAMPWAY_CHROMIUM=<isolated-headless-shell> server/.venv/bin/python -m pytest -q -o addopts='' server/tests` at the code snapshot: **1,826 passed, 35 skipped, zero failures** (182.92 seconds). Skips remain unverified, including the three absent original-teaser tests.
- Selected standalone client/rail gates: 57 pass, one fails because the newly merged docs corpus NOTICE/manifest contains ten `projects.blender.org` references rejected by the shipped-host allowlist. This is a coordinated docs-integration dependency, not waived.
- Own commit range `origin/main..HEAD` and shipped docs media: zero prepublish findings. The pre-push range remains blocked as described below.

The public synthetic fixtures were rendered by real isolated Chromium. They do not establish the unavailable original teaser's section-11 acceptance.

## Remaining coordinated gates

The original-head CI failures are mapped to PR1's assigned G24-G26 fixes: [PII commit-range](https://github.com/Keigyoku/lampway/actions/runs/37665448930), [R04 determinism](https://github.com/Keigyoku/lampway/actions/runs/37665448853), and [REUSE](https://github.com/Keigyoku/lampway/actions/runs/37665448852). Tested dependency commits were requested through the parent; these files are not changed independently here. The normal pre-push range currently includes the already-published main merge identity and remains blocked by G24.

The supplied source index's 15 archive hashes verify, but no member contains the motion-graphics spec/handoff. The source remains unavailable; no unrelated text or private asset was extracted or published.

The original fixture contract is a directory with `teaser.html`, code SHA-256 `4b30a23cf619b197f67974f1b6ce70de95c6b0b9fb7d83d2abbfaaaec1e3337c`, frames digest `e6e517e036d987f639ebe59430a7f7eb4d3c0d81f5b8d2dce60d63b5e47b0645`, 390 frames at 30 fps. It is not present in this cloud checkout. Parent reports that the existing local validator located the hash-matching 14-file fixture and HeadlessChrome 153.0.8010.12; no fixture was uploaded to cloud.

The validation command for that parent-managed checkout is `server/.venv/bin/python -m pytest -q -o addopts='' server/tests/test_motion_graphics.py`, with `LAMPWAY_CHROMIUM` and `LAMPWAY_MOTION_TEASER` set to the verified local sources. Native source diff from the original PR head is zero files across `src/source`, `src/CMakeLists.txt`, `src/build_files` and `src/release/datafiles`.

Reference aggregate remains unverified: its read-only shelf fixtures and a verified native binary BUILT_FROM stamp are absent. Parent validation is queued; no stamp or fixture is fabricated and no baseline is weakened.
