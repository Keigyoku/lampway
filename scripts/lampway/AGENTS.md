---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# scripts/lampway — build, launch, sync and the pre-publish gate

Lampway's own operator scripts: `build_linux.sh` (clone to runnable app in the build box), `lampway` (the one command: server plus
app on a copy of a file), `sync_python.sh` (a Python-only change into an installed build), `prepublish_gate.py` with
`pii_allow.txt` (what may never be published). Upstream's build machinery stays in `scripts/unix/` and `scripts/windows/`; these
wrap it. The procedures: the `lampway-coding-guidelines` skill (build and run) and the `lampway-release` skill (the gate).


`measure_fit_decisions.py` runs in an explicitly supplied disposable scene and project config, never saving the blend or selecting defaults. Receipts/views remain under the project root; failed jobs produce a nonzero exit.

Body-relative fit captures require explicit world-metre body context, fixed camera bounds and caller clearance limits. Keep execution success separate from all-vertex clearance acceptance; sampled diagnostics and isolated silhouettes cannot select physical defaults.

`test_all.py --shrink-baseline` removes only exact node IDs with affirmative pytest PASS receipts. Skipped or uncollected known-red rows remain and make the reference verdict unverified; absence from the failure summary is never a passing receipt.

## Invariants

1. **AXI refusals.** A refusal prints `error: <why>` and a `help[N]:` list of next commands on stdout and exits 1; an unknown flag
   exits 2; `--plan` / `--check-deps` print what a run would do and touch nothing. A new script follows the same shape.
2. **The build runs in the box, never on the host,** and never writes `.env`: a `.env` that contradicts the requested environment
   is refused, because `settings.sh` sources it after the environment and would silently win.
3. **The launcher never takes a secret as an argument and never prints one**; the OpenRouter key comes from the environment or a
   dotenv file the user points at, and the session budget is a hard ceiling. `--copy` opens a copy; the user's file is never
   opened for saving. The profile lives under `LAMPWAY_HOME`.
4. **The pre-publish gate holds no owner value.** The maintainer's patterns come from `PII_OWNER_*_RE` variables (a 0600
   `pii_owner.env` in the shared git directory locally, repository secrets in CI). `pii_allow.txt` holds only known-fake values,
   each with its reason on its line. Secrets are printed as their first four characters only; personal identifiers and commit email domains are fully redacted.
A Python matrix expression is executable code rather than a contact address only when the scanner proves its operator and structured operands. Quoted strings, comments, bare email-shaped expressions and owner-specific patterns remain blocking; no value/domain allowlist is added for code.

5. **The gate proves itself.** `prepublish_gate.py --self-test` plants one offender of each kind and fails if any goes unseen; a
   change to the patterns lands with its plant.

UE cube capture scripts run only in an explicitly disposable UE QA project, save no scene/material asset, and write generated DATA solely under that project's `Saved/LampwayCubeQA`. The read-only capability marker is not rendering proof. Exact native shaper provenance, engine/profile agreement, raw-input controls and disabled native tone-curve controls precede a cube sidecar; the initial capture records its 8-bit display precision. Offline `--plan` reports the full capture count and bounded runtime allowance without launching UE or choosing settings. Pure packing tests are synthetic; actual UE capture remains a separate owner-run receipt. Postprocess readback compares finite scalar and Vector4 component values within the existing tolerance; native enum readback uses matching types and semantic member values. Wrapper display strings and addresses never determine equality or enter the settings receipt. Keep differing values, nonfinite inputs and missing overrides blocking.

Construct UE rotations with explicit pitch/yaw/roll keywords. Before allocating render targets or taking controls, verify the capture component's actual finite world forward vector points down world Z at the disposable QA plane; an actor direction cannot substitute for component readback. Record the verified vector and preserve raw-control refusals, actor cleanup and no-output failure behavior.

Read back all disabled-tone fields and overrides before sampling, and verify restored normal settings even on a capture exception. Retain path-free numeric QA control readbacks before the unchanged curve-difference refusal; a diagnostic marker is not cube acceptance or proof of a rendering cause.

Source FBX bind diagnostics use the exact-hash pinned pure parser without package bootstrap, bpy or scene import. Record raw Model ancestors, authored unit/axis/transform properties, bind poses and cluster matrices without inferred coordinate conversion or engine acceptance. Hash the source before/after, refuse malformed/unsupported layouts, and write only a new exclusive0600 private receipt; stdout and errors contain aggregate counts/hash or sanitized reasons.

## Test

```bash
python -m pytest -q tests/lampway/test_build_linux.py tests/lampway/test_prepublish_gate.py
python -m pytest -q tests/lampway_tools/test_launcher.py tests/lampway_tools/test_linux_scripts.py
python -m pytest -q tests/lampway_tools/test_ue_cube_generator_probe.py tests/lampway_tools/test_ue_cube_generator_capture.py
python3 scripts/lampway/prepublish_gate.py --self-test
scripts/lampway/build_linux.sh --plan
```

Native frame diagnostics read loaded modules and authored matrices without projection or scene mutation. Capture the installed classifier source/hash, exact sampled child identities and X/Y/Z joint-line angles with the unchanged rest fingerprint; median/max angles alone cannot authorize conversion or a wider convention bar. Write the complete owner-only receipt exclusively with restrictive permissions; print aggregate errors and source identities, never owner matrices.

Run the read-only supplemental UE surface probe before full cube capture. Missing LDR/material/neutral-grading APIs refuse; surface availability is not shader or pixel proof.

Reference summary parsing strips ANSI formatting and separates interleaved warning messages only outside balanced parameter brackets. Preserve exact parameter node IDs, unknown failures and process errors; warning contamination cannot manufacture a new failure or an affirmative PASS.

A pytest process error refuses GREEN even when no failure IDs were printed. Flaky classification requires a successful retry and an exact PASS receipt; crashed or silent retries retain the original failure.

## Owner

The build script and the build box belong to the native-build lane (`lp/facelift` at the time of writing). The pre-publish gate is
the coordinator's final gate; widening what it allows is the captain's call. Changes to `prepublish_gate.py`, `build_linux.sh`,
`sync_python.sh` and `lampway` owe their skill an anneal row and a body change in the same commit (`rail/catalog.json` triggers).

The full-run harness reports RED for inherited as well as new failures/errors. Preserve attribution and affirmative exact PASS shrinking, but never treat known-red membership as permission for GREEN. Keep missing/skipped/crashed proof refusals.

Physical bind diagnostics capture signed rest transforms locally and return derived deltas, topology and actual import metadata. Never upload original FBX, vertices or weights. Preserve the extra container and independent native reference, verify actual accessor/composition semantics, and keep supplied-data comparisons distinct from physical acceptance.

Component joint-distance diagnostics report signed differences only, using unchanged parent edges and explicitly bounded fixed pairs from the existing capture. Mark changed/missing pairs instead of inventing correspondence. These invariants add no acceptance bars and do not select a rigid correction or alter the comparator verdict.

The published export-copy probe pins its loaded exporter source files, measures only the eight refused twist rows on disposable centimetre copies, and verifies unchanged scene/source fingerprints after success or failure. Return lengths, magnitudes, derived errors and hashes only; sanitize nested failures and never import/export/save, read credentials, alter bone lengths or loosen bars. Real-binary synthetic probe tests verify bounded output and cleanup independently of owner acceptance.

Derived bind diagnostics include left-relative and right-relative quaternion deltas and rotation/translation invariants. Variable left deltas alone cannot rule out a common right correction or basis conjugation. Keep raw absolute transforms local and all existing pass metrics unchanged.

The bounded export-copy probe identifies its overlay by exact source hashes. Preserve immutable historical probes; update current pins when the owned exporter changes, without claiming a commit identity from an arbitrary checkout or native engine acceptance.

Generic email scanning consumes the complete host and bounds every domain exemption. Legacy example placeholders retain only exact reserved hosts; other known-fake hosts/addresses cannot exempt suffix lookalikes or another address on the line.

The UE bind comparator also evaluates all48 signed permutation conjugacy bases and every matched pair's relative-angle invariant locally. Publish residual/count summaries only; normalize captured quaternions solely for comparison, select no corrective basis and preserve every existing pass metric and bind bar. Repin the current export-copy probe when the owned exporter changes; historical probes remain immutable.

Export-copy diagnostics pin the current exporter module bytes and retain mismatch refusals; refresh a pin only with the measured exporter change, never to admit an unrelated installed overlay.

Launcher --help/-h lists supported flags and exits0 without requiring a build, creating profiles, launching services or printing secrets. Unknown flags still exit2.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-05 | rail adoption | captain: "make the DOE x DOX AGENTS rail for Lampway" | the scripts' refusal shape, secret handling and the gate's outside-the-tree patterns were known only from their headers | the five invariants, the test commands, and the scripts bound to their skills as rail triggers | captain ruling, 2026-10-05 |
| 2026-10-07 | PII diagnostics privacy | captain: fix PR privacy exposure | findings echoed identifiers and email domains into public logs | fully redact personal values while retaining every blocking rule and planted offender | prepublish privacy regression tests |
| 2026-10-07 | measured fit decision paths | captain: measure issue2 AC65 before defaults | configurable algorithm gaps and unmeasured proposals obscured required choices | `measure_fit_decisions.py` runs in an explicitly supplied disposable scene and project config, never saving the blend or selecting defaults. Receipts/views remain under the project root; failed jobs produce a nonzero exit. | native decision-pack fixture |
| 2026-10-07 | matrix code false positive | complete native topology regression push | adjacent matrix operator and structured bone attributes looked like an email | prove the Python operator and operands while retaining quoted, comment, bare-address and owner-pattern controls | planted matrix and email regressions |
| 2026-10-07 | body-relative decision receipts | captain: AC65 measured boot handoff | isolated cropped silhouettes and sampled counts hid actual body placement and implied acceptance | require explicit body context, fixed world bounds and limits; report all-vertex clearance separately with opening-band refusal and no default promotion | native body-context placement and threshold falsifiers |
| 2026-10-07 | affirmative baseline shrink receipts | issue 2 AC05 reference audit | subtracting failures treated skipped and uncollected known-red rows as passing and could delete them | require exact pytest PASS node IDs before shrinking, retain failures and unverified rows, and refuse an unverified green verdict | skipped, uncollected, teardown and parameter identity falsifiers |
| 2026-10-07 | genuine UE cube QA handoff | captain: provide actual UE tonemapper cube generation | external generator was absent and synthetic data could be mistaken for renderer proof | bounded QA-only scene captures with exact native shaper provenance, engine/profile agreement, readback controls and explicit display precision; pure tests remain distinct from physical UE proof | owner-run UE capability/capture receipt pending |
| 2026-10-07 | read-only native frame diagnostics | actual G4 numeric failure | loaded overlay and authored float32 matrices needed disambiguation | Native frame diagnostics read loaded modules and authored matrices without projection or scene mutation. Write the complete owner-only receipt exclusively with restrictive permissions; print aggregate errors and source identities, never owner matrices. | pure diagnostic controls and complete342 native unchanged-scene proof |
| 2026-10-07 | supplemental UE capture preflight | actual UE handoff | the initial probe omitted display readback and grading APIs | Run the read-only supplemental UE surface probe before full cube capture. Missing LDR/material/neutral-grading APIs refuse; surface availability is not shader or pixel proof. | missing API/property and complete mocked surface controls |
| 2026-10-07 | full-suite process failure receipts | issue 2 AC05 bounded crash controls | pytest crashes without test IDs and crashed retries could appear green | refuse process errors and require exact successful retry PASS receipts before flaky classification | suite crash, crashed retry and affirmative retry controls |
| 2026-10-07 | typed UE postprocess readback | actual UE QA capture rejected equal Vector4 values | wrapper display strings included different object addresses, causing a false settings mismatch and address-bearing receipts | compare finite four-component values numerically and enum values by matching types and stable members; serialize vector arrays, preserving mismatch and nonfinite refusals | actual UE-shaped address, component, scalar and enum falsifiers |
| 2026-10-07 | interleaved reference warning parsing | actual full client failed-node receipt | ANSI warning text contaminated a known-red identity and manufactured stale/new classifications | strip formatting and separate top-level warning text while preserving bracketed parameters, actual failure IDs and crash refusals | actual FAILED/ERROR/PASSED warning and colored-summary controls |
| 2026-10-07 | actual UE capture direction | owner-run9f90 raw control failed | positional Rotator arguments set roll instead of pitch and rendered background | explicit rotation keywords and finite component world-forward admission before targets/captures, retaining raw controls and cleanup | UE-shaped positional-order, relative-component direction and no-output controls |
| 2026-10-07 | raw source FBX bind evidence | actual physical UE bind failed and aggregate receipt omitted transforms | LimbNode-only scale checks missed container ancestors while Blender self-reference hid engine interpretation | preserve raw ancestry, properties and matrices through pinned pure parsing, source checks and private exclusive output without evaluator claims | container100/USF1, malformed/privacy and native unchanged-scene controls |

| 2026-10-07 | inherited failures stay RED | captain: no red checks | baseline-known failures escaped the completion predicate | require zero known/new failures while preserving attribution and exact passing proof | both-suite FAILED/ERROR shrink/no-shrink controls |

| 2026-10-07 | physical bind capture contract | actual UE343bones/all342binds failed while Blender self-readback passed | signed transforms and actual importer semantics were absent, allowing root/unit speculation | derive private comparison-only reports from validated local captures without geometry, API guesses or correction selection | raw signed scales, quaternion signs, topology and privacy refusal controls |

| 2026-10-07 | actual unit-carrier and frame diagnosis | owner UE derived342-row capture | Blender self-readback hid scale100 Null ancestry; applying import object scale violated the existing drift guard | Derived bind diagnostics include left-relative and right-relative quaternion deltas and rotation/translation invariants. Variable left deltas alone cannot rule out a common right correction or basis conjugation. Keep raw absolute transforms local and all existing pass metrics unchanged. | old-default rawNull100 RED; disposable writer/skin/action/unit-factor and quaternion-order controls |

| 2026-10-07 | component joint-distance diagnosis | actual corrected-unit candidate still fails native positions and frames | origin-relative norms cannot distinguish rigid translation from joint deformation | report derived unchanged-edge and bounded fixed-pair distance differences without absolute tables, new bars or changed verdicts | rigid-transform, displaced-joint, changed-parent, missing-pair and finite-range controls |
| 2026-10-07 | public bounded export-copy probe | captain: local validator cannot read off-repository cloud probe | private task paths blocked reproducible short-bone diagnosis and nested failures could expose owner strings | publish source-pinned eight-row disposable-copy diagnostics with unchanged-scene and sanitized-refusal controls | real-binary bounded numeric rows, wrong-source, missing-row and post-yield cleanup tests |

| 2026-10-08 | current export-copy probe source pins | scoped native conform/export correction | historical1368 pins refused the corrected Python modules | Keep the historical probe immutable and pin current exporter bytes with a source-hash identity; no engine acceptance claim. | bounded numeric, wrong-source, missing-row and sanitized cleanup controls |
| 2026-10-08 | email scanner exact exemptions | PR3 finding4213654799 assigned to MCP owner | regex and allowlist prefixes hid suffix lookalikes | retain full-host matches, per-address exemptions and redaction | suffix, exact-domain, mixed-line, versioned-filename and self-test controls |
| 2026-10-08 | original mixed-frame diagnostic gap | current private audit rejected MetaHuman with median89.999448/max103.97325 | aggregate Y angles omitted child choices and X alignment, permitting unsupported convention guesses | capture installed classifier and sampled X/Y/Z rows under unchanged fingerprint; keep original heads/frames private and strict mixed refusal | two missing-interface REDs,34 pure GREEN tests and native unchanged-scene control |
| 2026-10-08 | runnable native rotation diagnosis | current calibrated mesh-reference audit omits per-bone deltas | aggregate near180-degree errors cannot identify a writer or basis change | compute all48 proper/improper basis residual summaries and all-pair angle invariants without raw tables, correction selection or altered verdicts; update current exporter pin | five missing-interface RED controls;56 pure GREEN cases and synthetic342-row bound |
| 2026-10-08 | disabled-tone state verification | N05 actual GPU no-difference refusal | disabled settings were assumed applied and failed control pixels were discarded | verify disabled and restored native settings and retain numeric control marker under unchanged bars; keep GPU cause and acceptance unverified | synthetic RED/GREEN and threshold controls; actual GPU rerun pending |
| 2026-10-08 | independent native export diagnostic pin | exporter reference correction | historical exporter pin refused the current diagnostic overlay | bind diagnostics to the corrected committed source and retain wrong-pin controls | exact current source SHA and diagnostic regressions |
| 2026-10-08 | launcher help entry | inherited setup audit I12 | unknown-flag path rejected help | early static help with no startup side effects or secret output | two behavioral REDs and32 existing/help/Linux checks GREEN |
