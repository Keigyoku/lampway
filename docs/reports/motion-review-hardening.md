<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# PR #3 motion review hardening

Implementation and full-server validation snapshot: `91225a927a430958b011cff27f29341a11fa9515` on `lp/motion`.
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

## Repository contracts and integration handoff

This handoff records the published implementation and its measured evidence. The required original source is `specs/motion_graphics/motion_graphics.md`: both [the public tool](../../server/lampway_server/agent/motion_tools.py) and [the renderer](../../server/lampway_server/motion/__init__.py) cite it, and [the original tests](../../server/tests/test_motion_graphics.py) cite sections 4, 5, 10, 11 and 13. Its bytes and authoritative revision are unavailable in this checkout and the verified supplied archive inventory. The associated spike handoff's exact filename/revision was not supplied. Recover these sources through the coordinator before declaring conformity to the complete original specification; this report introduces no replacement specification or new product promise.

| Contract | Published implementation | Evidence and integration requirement |
|---|---|---|
| Public call and inputs | [motion_tools.SPEC](../../server/lampway_server/agent/motion_tools.py) and [motion.inputs](../../server/lampway_server/motion/__init__.py): render/verify; project-relative scene or named inline HTML; 1..60 fps; even dimensions within 16..3840 by 16..2160; duration (0,120]; non-empty MP4/WebM subset; at most 24 sample times. | Original input/refusal cases plus explicit-empty, inline-symlink and output-isolation regressions. Keep the existing tool surface. |
| Scene and local-file boundary | [frames.Chromium](../../server/lampway_server/motion/frames.py): scene metadata, awaited setup, frame function and required audit with text/marks arrays. Checked file bytes remain within the scene; unattested loaders are refused. | Eight actual isolated-Chromium public-fixture cases, six helper cases, setup-time audit regression and the parent-managed original teaser. |
| Timing and determinism | [motion._run/_probe/verify](../../server/lampway_server/motion/__init__.py): t=i/fps sequentially from frame zero; eight probe samples from a fresh sequential browser; verify rerenders and compares every frame/output. | Determinism falsifiers and real original-teaser repeat/verify proof. Preserve fresh-browser ordering and encoder thread pin. |
| Self-check and artifacts | [check.findings](../../server/lampway_server/motion/check.py) checks empty/sparse frames, title-safe text, minimum text size, measured contrast, overlap and cropped marks. Each exclusive run writes `<name>.mp4` and/or `<name>.webm`, `receipt.json`, `frames.sha256`, `contact.png`, and sampled PNG/JSON under `motion/out/<name>-<code8>-<unique-run>/`. | Runtime paths include the exclusive run suffix. Keep fail/warn distinct and retain the teaser's sparse-poster warning. Self-check failure returns files with ok=false and prevents Vault filing. |
| Vault and provenance | [receipt.file_in_vault](../../server/lampway_server/motion/receipt.py): MP4 primary when present, otherwise WebM; primary render/main, second video variant_of, receipt/contact derived_from; code/frame hashes, effective template variables/version and local engine identity retained. | WebM-only/default-variable tests and parent-managed real Vault proof without spooling. Shared provenance/schema/registry changes require coordinator approval. |
| Local processes and metadata | [encode](../../server/lampway_server/motion/encode.py), [frames](../../server/lampway_server/motion/frames.py), and the existing egress launch audit: pipe-only browser, declared local launches, pinned output descriptor, checked conditional metadata remux. | Launch audit, egress suite, output swap falsifiers and real media equality. Preserve no network/provider spend and asset provenance. |

For PR1 combined integration, the isolated fixture-race fix is **`0cfba29ae5394063c99748dda09910337b647519`**. Its complete two-file touch list is `server/tests/fixtures/fake_codex_app_server.py` and `server/tests/test_codex_app_server.py`. The fake consumes/logs response 900 before completion; the direct protocol regression observed RED before the fix and all 12 module tests passed afterwards. Existing method-not-found assertions remain intact. No production provider file changed. Integrate this isolated commit through the coordinator, preserving the recipient's changes.

## Additional regressions found and fixed

- Audit readiness must be checked after setup, allowing setup to install the required audit before output creation. A setup-time initialization plant reproduced the ordering regression.
- Inline scene entry symlinks could be written before refusal; the regression observes the external file's mtime.
- A request appearing only in the fresh probe could escape the network result; both passes now contribute forbidden requests.
- Verify trusted a receipt-controlled frame path and later reread it through a raceable pathname. Checked regular-file reads precede rerender, and checked rereads detect replacement.
- ffmpeg 7 adds stream encoder metadata after metadata options. A conditional local stream-copy remux removes it, checked afterwards. Already-clean engines keep their original bytes.
- The pipe launcher failed on dash with high-numbered descriptors; bash handles the inherited descriptors. Modern headless-shell target creation no longer receives unsupported dimensions.
- Browser-owned UI targets are distinguished from scene loaders. Workers remain paused/refused because their targets do not expose Fetch interception.
- A full server run exposed an unchanged app-server fake-fixture log race: it completed the turn before consuming/logging reply 900. Parent assigned fixture-only ownership here, coordinated with PR1. The fake now drains/logs the reply before completion; a direct causal protocol test observed RED on the old fixture. Existing method-not-found code/message assertions remain intact; production provider is unchanged.

The renderer remains sequential from frame zero. The determinism probe remains a fresh browser and preserves sampled audit timing. No socket, provider, spend, pricing or product expansion was added. The parent assigned the single shared local `motion/encode.py:Encoder.finish` launch declaration; no network/spend route changed.

## Measured validation

- Baseline browser RED: nine containment/audit/scene-hash plants failed to refuse. Launcher compatibility alone was applied to make that baseline executable.
- Containment/target suite: 14 pass, comprising eight actual isolated-Chromium cases and six helper/target unit cases. The browser engine is HeadlessChrome 155.0.8059.39; the allowed SVG test asserts the actual green pixel.
- Output/probe/verify hardening: 12 tests pass; each reported defect was observed failing before its fix. These use the fake capture seam and real ffmpeg; they are unit/encoder evidence, not browser acceptance.
- Pillow checks: 15 tests pass on Pillow 12.3.0 and actual Pillow 10.0.1.
- Template/library review tests: 37 pass.
- Launch audit: 7 pass. Egress suite: 37 pass.
- Existing motion plus output and browser hardening run: 49 pass, 3 teaser tests skip (before the final extra verify-race and UI classification tests).
- Rail and canon pass locally; generated tool documentation is current. Changed motion code/tests have zero prepublish findings.
- Historical full server suite at `192cbaebe9d50292942bd8af2ee4d77c416a1cb5`: `LAMPWAY_CHROMIUM=<isolated-headless-shell> server/.venv/bin/python -m pytest -q -o addopts='' server/tests`: **1,826 passed, 35 skipped, zero failures** (182.92 seconds). Skips remain unverified, including the three absent original-teaser tests.
- Full published-head server rerun at `042bedf3ce3d9cfc3b18b52e1b201e8b79f76278`: **1,827 passed, 35 skipped, zero failures** (187.17 seconds). An earlier full run had the diagnosed fake-fixture race; clean repeats did not close it. After the fixture-only fix, all 12 app-server module tests pass, including the causal regression.
- Exact-head full server at `91225a927a430958b011cff27f29341a11fa9515`: **1,828 passed, 35 skipped, zero failures** (196.94 seconds), including the fixture-race regression. Cloud skips remain skips; original-teaser cases have separate local evidence below.
- Selected standalone client/rail gates: 59 pass after the parent-authorized official documentation host entries and lookalike refusal test.
- Actual unpushed range `origin/lp/motion..HEAD`, own commit range `origin/main..HEAD`, and shipped docs media: zero prepublish findings after the scoped gate integration. REUSE v3.3 passes, with metadata on all 9,760 files.
- Documentation handoff validation: docs tree/media scans have zero findings; generated tools are current; shipped-metadata and site-link modules total **8 passed**. The preceding documentation commit message incorrectly stated 14; this measured count corrects it.
- Scoped gate, workflow, host and R04 regressions: 33 pass. Both BLAS kernels retain exact byte assertions and small-angle/falsifier checks.

The public synthetic fixtures were rendered by real isolated Chromium. The original teaser has separate parent-managed real-browser evidence at its exact tested head below.

## Remaining coordinated gates

The original-head CI failures were mapped to PR1's assigned G24-G26 fixes: [PII commit-range](https://github.com/Keigyoku/lampway/actions/runs/37665448930), [R04 determinism](https://github.com/Keigyoku/lampway/actions/runs/37665448853), and [REUSE](https://github.com/Keigyoku/lampway/actions/runs/37665448852). The parent supplied tested scoped sources: gate prerequisite `75a00df9`, matrix classification `a4f2cee3`, workflow endpoints `dc732196`, R04 `323d44b9`, license metadata `d4f768de`, and official docs host entries `afcbe66d`. Their scoped integration preserves newer corpus metadata and excludes unfinished PR1/native changes. The exact source matrix expression is self-contained in the gate fixture because its PR1 native test file is absent. REUSE adds eight exact missing Lampway paths and keeps the full adjacent ITF legal terms.

The earlier normal push was refused by the pre-push hook for the already-published main merge identity (`eab73f5f`). The supplied gate prerequisite admits only the exact public provider noreply identity, preserves personal/lookalike/secret-content controls, and now the actual unpushed range passes. No hook was bypassed and no history rewritten. Normal publication at `042bedf3ce3d9cfc3b18b52e1b201e8b79f76278` passed the commit, media and rail hooks. All five exact-head GitHub workflows passed: [PII](https://github.com/Keigyoku/lampway/actions/runs/37690204411), [canon](https://github.com/Keigyoku/lampway/actions/runs/37690204413), [REUSE](https://github.com/Keigyoku/lampway/actions/runs/37690204430), [rail](https://github.com/Keigyoku/lampway/actions/runs/37690204417), [MCP launcher](https://github.com/Keigyoku/lampway/actions/runs/37690204381). All five workflows also passed at the fixture-hardened `91225a927a430958b011cff27f29341a11fa9515`: [PII](https://github.com/Keigyoku/lampway/actions/runs/37691766117), [canon](https://github.com/Keigyoku/lampway/actions/runs/37691766119), [REUSE](https://github.com/Keigyoku/lampway/actions/runs/37691766110), [rail](https://github.com/Keigyoku/lampway/actions/runs/37691766146), [MCP launcher](https://github.com/Keigyoku/lampway/actions/runs/37691766024). No final acceptance claim is made.

The supplied source index's 15 archive hashes verify, but no member contains `specs/motion_graphics/motion_graphics.md`. This exact referenced authoritative source and the unidentified associated spike handoff remain missing. No unrelated text or private asset was extracted or published.

The original fixture contract is a directory with `teaser.html`, code SHA-256 `4b30a23cf619b197f67974f1b6ce70de95c6b0b9fb7d83d2abbfaaaec1e3337c`, frames digest `e6e517e036d987f639ebe59430a7f7eb4d3c0d81f5b8d2dce60d63b5e47b0645`, 390 frames at 30 fps. It is not present in this cloud checkout. Parent reports that the existing local validator completed **29 passed, zero failures/errors/skips** on exact `042bedf3ce3d9cfc3b18b52e1b201e8b79f76278` (941.8 seconds), using real Chromium 153.0.8010.12 and ffmpeg 8.1.2. All 390 frames match the committed digest; repeat frame hashes and MP4/WebM bytes match. Public-tool verify reproduces all outputs. Vault filing, provenance and relations pass without spooling. Publication tree/media scans report zero findings, and all 14 original fixture files are unchanged. The opening sparse-poster warning is retained. These are coordinator-reported summary facts; the owner-only raw receipt, private paths and assets remain private.

The complete diff from that teaser-tested head to `91225a927a430958b011cff27f29341a11fa9515` is the two fixture-race files and this report. Motion production code, original teaser tests, templates, provenance, encoding and native sources are unchanged. The later fixture fix has its own exact-head full-server/CI evidence above; the teaser run is attributed to `042bedf3`, not relabeled as a later-head run.

The validation command for that parent-managed checkout is `server/.venv/bin/python -m pytest -q -o addopts='' server/tests/test_motion_graphics.py`, with `LAMPWAY_CHROMIUM` and `LAMPWAY_MOTION_TEASER` set to the verified local sources. Native source diff from the original PR head is zero files across `src/source`, `src/CMakeLists.txt`, `src/build_files` and `src/release/datafiles`.

The zero-red reference acceptance requirement remains open. Historical baseline-relative GREEN allowed listed known-red failures and is not final acceptance. Combined reference aggregate remains pending with the parent/PR1 coordinator, who restored the local shelf fixtures. This cloud environment cannot supply the reference shelf or genuine native binary provenance. Required evidence is the combined exact tested head, genuine native-source-matching BUILT_FROM stamp, server/client failure and skip counts, zero new failures, explicit known-red/baseline deltas, and unchanged read-only shelf inventory. Final zero-red acceptance requires resolution of remaining failures rather than a baseline-relative GREEN label. No stamp or fixture is fabricated and no baseline is weakened.
