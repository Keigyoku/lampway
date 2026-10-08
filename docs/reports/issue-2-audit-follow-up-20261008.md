<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue 2 audit follow-up, 2026-10-08

The [current audit](https://github.com/Keigyoku/lampway/issues/2) assesses PR1 head `0da106ec0d0a2d75a740147f84a8f830b6d5e43a`: 64 of the original73 criteria verified complete, six failed and three unverified. Its nine unchecked original identities are AC01, AC02, AC03, AC04, AC05, AC12, AC15, AC24 and AC51. It also adds G27/G28 and explicit live-verification obligations. This audit supersedes the earlier completion wording; the issue remains open. No checkbox is promoted here from a component pass.

## Public defects corrected

G27: the public StanfordBunny consumer requested compact defect candidates and then accessed their detailed descriptors, producing `KeyError: rim_length_m`. The existing API contract specifies `full=true` for descriptors. The acceptance consumer now requests that mode explicitly, accesses the declared descriptor fields, and compares compact/full candidate identities, counts and totals. It retains the actual public bunny and all five unchanged edge-count/rim-length goldens. Inspection and defect measurement algorithms remain the shared implementations.

G28: the old plate test expected an unset facing margin after the authorized0.05 judgment default was adopted. The empty plate remains refused for having no silhouette; the test now checks the adopted margin, that refusal and complete imported-ID cleanup. An additional real-binary approved-plate case exercises the default without an override and checks the measured minus90 turn, recorded0.05 margin and unchanged IoU acceptance. Existing unset, invalid and ambiguous-facing controls remain.

The full standalone run additionally exposed two installation fixtures supplying dimensionless SVGs when the real converter is present. Both now supply a bounded32-by32 SVG with actual geometry; real launcher and desktop-entry scripts still run only against disposable test trees. No installed desktop entry or production asset is modified.

## Newly reproduced production defects

Hidden native source copies inherited viewport, layer and selection restrictions. The pinned FBX writer reads `context.selected_objects`, which excluded those copies even after `select_set(True)`; the resulting file read back zero armatures. Export now temporarily admits only the requested prepared armature/meshes and restores their visibility restrictions on success or exception. The unchanged bind bars and wrong-axis refusal remain. Native regressions reproduce the original error and verify complete readback, source flags and scene-ID restoration.

Continue and Back redrew the editor region but did not request the temporary popup layout rebuild. Onboarding now calls `tag_refresh_ui` and redraw on the existing `context.region_popup`, retaining the single-popup flow. Separate regression controls exercise both callbacks. The GUI acceptance fixture now distinguishes delivered transition input from bounded model/layout convergence; delayed input cannot be mistaken for a persistent stale-panel defect. Software telemetry is sampled evidence, not a claim about every unobserved frame.

## Material timeout correction

Coordinate-safe material probes now render three equal-resolution emission tiles in one EEVEE frame and split their linear pixels. Local/object coordinates remain unchanged; unknown, world/camera or external-object graphs keep the previous isolated three-frame path. This reduces165 renders to55 for the full preset statistics checks. Independent real-pixel controls compare hammered bronze, heavy cloth and embroidery against the immutable pre-change renderer with nondefault inputs, including coordinate-sensitive fallback plants. Caller scene state and owned camera/world data are restored.

The final complete material file passed all12 checks with zero skips on one CPU and one renderer thread. Both originally timed-out55-preset cases pass in162.83s and105.96s; their240s native-process limit is unchanged. Total file runtime360.47s includes other controls. This is an actual constrained software-render result on the available native binary/current Python overlay, not matching-build or hardware acceptance.

## Admitted soft conform implementation

The2026-10-08 ruling admits ARAP as a measured candidate and delegates solver defaults. The NumPy-only solver uses positive uniform edge weights, proper local rotations and a constrained global solve through matrix-free preconditioned CG. It keeps original vertex identities, explicit source-ledger displacement constraints and rigid/ornament coordinates unchanged. Defaults are30 local/global iterations,1e-7m update tolerance,300 CG iterations,1e-10 residual tolerance and1e-5m generated duplicate welding; all are physically untested. Explicit controls override these values.

The native adapter reads the verified native sidecar at the recorded fit pose and applies bounded clearance-handle updates to selected cloth/leather. It rechecks all selected vertices, source seams and serialized output before creating an admitted candidate. Canonical raw/stale/wrong-frame mesh refusals remain. Solve records a candidate without completing conform; accept checks source/input/output/body/pose hashes and genuine candidate-output render review. Downstream stages must use the accepted candidate and returned bound output. Numerical convergence does not certify self-collision, surface crossings, appearance or native motion.

## Reproduced checks

Commands use the declared test interpreter and a disposable older native executable with the current Python overlay. These are component/native-Python diagnostics, not a matching-current-native-build gate.

| Check | Result |
|---|---|
| Original StanfordBunny consumer | RED: missing `rim_length_m` in compact candidates |
| Original unset-margin expectation | RED: actual empty-plate refusal differed |
| Named public assets, normalize-mesh, facing and defect scan | 30 passed; one authentic Boots shelf case skipped |
| Adopted default plus empty/no-plate cases | Three passed, including actual rendered approved plate |
| Five originally named covering files plus rig export | 63 passed; one separate externally pinned public-helmet case skipped |
| Real launcher/Linux installation fixture suites | 30 passed with actual SVG converter |
| Full procedural material file, oneCPU | 12 passed, no skips/failures/errors; unchanged240s limits, all55 presets and independent exact-pixel controls |
| Onboarding production refresh and probe controls | 18 pure tests; normal and throttled/delayed native runs each five passed; persistent stale-panel plant failed correctly |
| Hidden-source export and all public export routes | 13 rig/export-axis tests,18 public-route/source-pin tests and ten shared UE-writer tests passed; actual zero-armature/zero-bone REDs retained |
| Admitted ARAP solver, composite order and native adapter | 48 passed, including two native controls; raw/stale/wrong-frame, review/hash/modifier/armature, nonconvergence and receipt-cleanup plants retained |
| UE derived basis comparator | 56 pure tests passed;48 proper/improper bases and58,311 pairs per space on synthetic342 rows; existing pass verdict unchanged |
| Private normalization diagnostic | 34 pure and one native synthetic test passed; two missing-interface REDs retained |
| Standalone client repeat before subsequent production fixes | 9587 passed,1070 skipped,39 failures and15 errors; all54 failing/error identities match the existing Agent Mode dependency; zero new identities |
| Canon and documentation checks | 48 mesh and34 rig goldens, schema and byte determinism passed; ten documentation tests passed |
| Consumer reversion and temporary unset-default control | Two expected behavioral failures; no repository mutation |
| Isolated onboarding/connected UI | Passed; actual llvmpipe renderer; step1, steps2–4, Back and popup recovery captured |

The covering inventory compares AST test identities against the original `290ddd3a` audit base and ties execution to XML receipts. All five literal files contain the missing input cases: numpy scalars; UV-split/open native-shaped intake; corrective fan-out apply; default Cube/import cleanup; hidden-armature conform. It records source hashes and exact executed case identities. This is available evidence for AC03, not independent certification of every original acceptance clause or authentic historical RED-first order.

The final standalone repeat exposed one new full-catalogue ceiling regression in expanded conform guidance and three missing-rsync environment failures. The guidance was shortened with required inputs, candidate review and physically untested labels preserved, without increasing the335000B ceiling. Reruns use the existing isolated rsync binary and its libraries. Receipts distinguish this correction from the separately owned Agent Mode failures.

## Remaining interfaces and acceptance

| Criterion | Remaining requirement / dependency |
|---|---|
| AC01 | Conjunction of the outstanding criteria and explicit live obligations; remains open. |
| AC02 | Authentic historical pre-fix RED ordering for every earlier fix. Current reversion controls do not create missing historical records. |
| AC03 | Review the source-hashed, executed five-file covering inventory against the original missed cases; retain separate physical and chronological proof. |
| AC04 | Successful original-input receipts for every fixed item attached to PR1. New public-model evidence does not replace the other original assets. |
| AC05 | Zero-failure maintained gate, authentic read-only shelf and matching native build. The remaining54 baseline identities are the separately owned Agent Mode dependency; preserve their ownership and import a reviewed integration result rather than reimplementing that lane. |
| AC12 | Original intake/proportion passed; authentic match/render review still gates later stages. The captain admitted the ARAP-with-clearance candidate under03-H2 on2026-10-08 and delegated physically untested solver defaults. The solver/composite stage is implemented with explicit clearance/seam targets and pending-candidate versus accepted-stage receipts; original-piece output review and full downstream fit remain unverified. Existing rigid-only conform skipping is correct. |
| AC15 | Actual342-bone MetaHuman apply refuses mixed convention: Y/joint-line median89.999448°, maximum103.97325°. The package omits sampled child and per-axis rows. Updated read-only diagnostic captures exact installed classifier, fingerprint, selected children and X/Y/Z outliers; absolute owner frames stay local. No classifier relaxation or guessed conversion is applied. The exact original scene is identified by SHA256 `24c9a568b267dc62fc929a02b4deff3b3bbaae7adf4d5e323f8dc09a15297e32`; Drive discovery found GLB exports and references, but did not locate that scene. |
| AC24 | Hidden-source zero-armature bug fixed. Actual calibrated UE5.8.2 mesh reference still fails325 local/329 component rows despite matching342 names/parents and approximately0.000095cm component position agreement; rotations approach180°. Latest per-bone relative deltas and stage residuals are absent. Native self-control passes342 rows. No export-axis guess or tolerance change. |
| AC51 | Actual owner AMD/radeonsi screenshots pass; half-CPU software repeat reported stale step2 after step3 input, while another software repeat passed. Popup-layout refresh and delayed-input fixture fixes require successor local repeat with matching native binary. NVIDIA GUI exit139 is separate from RTX/CUDA acceptance. |

The supplied complete private audit archive was downloaded and read:3,749,232 bytes,39 CRC-verified entries, SHA256 `c6475d2f2467adb05dd4f361bc792205249a4b8a58f3807ec058771a19049de9`. It is actual report/reproduction/coverage/receipt content, not an access shell. Its exact-head local server run reports2273 passed,16 skipped; its raw client run reports10527 passed,118 failed,16 errors,49 skipped. The80 new identities were repeated with corrected software/display settings:74 passed,four failed,one error,one skipped. This does not establish aggregate GREEN. Two material probes exceeded240 seconds, the authentic chestplate fixture was missing, and the recorded Bunny/facing contracts failed. Raw vertices, weights, original FBX, absolute bind tables, account/session data and owner paths remain private. The earlier derived export packages are historical diagnostic inputs; they cannot establish a successful correction on this audit's head.

The native build preflight reports absent build dependencies and libraries; the selected filesystem initially had17GiB free versus the build script's100GiB requirement (later14GiB after verification artifacts). No new build stamp is written. The maintained reference admission requires the authentic shelf; no primitive is substituted. The selected environment exposes no GPU device.

The explicit live list also retains owner-provider sign-in/Connections tests, paid studio approval and execution, UE Look editor/render parity, native fit export/validate, actual MetaTailor export, authenticated cockpit/MCP workflows, missing authentic shelf/Boots fixtures, and final match/facing/physical fit review. Existing checked WezTerm and native-sidecar acceptance are preserved. No spend, account change, desktop operation, deployment or PR merge is performed by this follow-up.
