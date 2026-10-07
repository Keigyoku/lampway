<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Local QA handoff

Pushed candidate: 6331e542727e52d9a67a42a4bb3c12e0cac63e3e
Branch: lp/mcp-wrapper-migration-main-20261007-v2
Base: 290ddd3a3a08ccc646ff4e3faa73326c09e1c154
Draft PR: https://github.com/Keigyoku/lampway/pull/1

Native sources are identical to checkpoint afcbe66d613ffd10c1495cf2d8d362ef2097e954. A clean native build stamped at either commit can validate this native source; the original 978793994b4f4f9c60795f0365c8290c0f778d2d build cannot validate the changed profile-card links. Rebuild inside an isolated checkout/build box, preserving the installed app and originals. Do not fabricate BUILT_FROM.

## First priority

Run these with a disposable executable and adjacent script tree: blender_run.py synchronizes Python into LAMPWAY_BIN.

```bash
PYTHONHASHSEED=0 LAMPWAY_BIN=/absolute/path/to/disposable/bin/mixar python -m pytest -q tests/lampway_tools/test_canon_normalize_rigged.py tests/lampway_tools/test_canon_fit_body_package.py tests/lampway_tools/test_rig_export_ue.py
```

Then repeat on the staged original MetaHuman copy, using its verified engine sidecar and actual armature/body names. normalize_rigged(armature=<name>, meshes=[<full-body>], profile="metahuman", turn_deg=0.0, dry_run=False). fit_body(verb="build", armature=<name>, mesh=<full-body>, sidecar=<engine JSON>, out="fit/body"). The sidecar must retain native centimeter units, original vertex IDs, triangles, bone parents and weights; do not substitute GLB weights. Retain every corrective-root authored roll/frame and downstream weight-plan result. Test both default titan_cm_native and explicit cm_native_blender_convention FBX recipes; the default remains unproven.

Repeat Tripo/chest normalization-versus-proportion scores with the SAME declared raw turn and canonical residual turn0. Do not assume a universal -90 turn. Approved plate matching accepts an explicit supplied IoU-gap margin; the canonical default remains unset. The synthetic 0.1 test threshold is not an owner ruling.

## GUI priorities

The following fixture copies the runtime and uses a newly owned display, never an inherited desktop. Use a supported GPU display configuration without changing security/driver settings. Hardware fallback is a refusal, not acceptance.

```bash
LAMPWAY_VIEW_SOFTWARE_GL=0 LAMPWAY_VIEW_BIN=/absolute/path/to/built/bin/mixar LAMPWAY_VIEW_XVFB=/absolute/path/to/Xvfb python -m pytest -q tests/lampway_tools/test_issue2_gui.py -o tmp_path_retention_policy=all
```

Retain receipt.json and all step1-4/Back/native-label/popup PNGs. Actual renderer must be hardware. Default mode1 is software coverage. The same connected fixture exercises in-app mock-account sign-in, actual modal-active refusal, ESC recovery and fresh scene inspection. The checkpoint fixture tests actual mock-provider read0 versus write1 document-copy bytes:

```bash
LAMPWAY_VIEW_BIN=/absolute/path/to/built/bin/mixar LAMPWAY_VIEW_XVFB=/absolute/path/to/Xvfb python -m pytest -q tests/lampway_tools/test_f25_gui.py -o tmp_path_retention_policy=all
```

## Reference aggregate

Locate the recorded read-only shelf, including scratch/proportion/audit/body.npz and scratch/proportion/piece_selftest/helmet.npz. Set LAMPWAY_SHELF_DIR and, if different, LAMPWAY_SHELF_SCRATCH. Follow scripts/lampway/test_env.sh and test_all.sh; retain source/binary stamps, XML/logs and the complete known-red comparison. Do not remove rows because a test skipped. No cloud reference test_all pass is claimed.

UE requires a genuine native UE cube and lampway.ue-cube-meta/1; the existing analytic Python cube is insufficient. MetaTailor licence/export, real CLI/provider auth/agent turns and studio acceptance remain unverified. Any paid/live-upload action requires exact provider/account/action/data/quote/currency/limit approval; no paid generation is authorized by this handoff.

Original assets remain unchanged; outputs only in isolated copies/scratch. No merge/deploy/security settings/desktop operations.

## Cloud evidence and remaining GUI checks

The source candidate above is the exact committed reference. The isolated cloud GUI used a disposable copy of the older native executable with current Python sources; it does not prove the newly changed native profile-card links. Source comparison from `afcbe66d613ffd10c1495cf2d8d362ef2097e954` to `6331e542727e52d9a67a42a4bb3c12e0cac63e3e` shows no changes under `src/source`.

Software mode completed onboarding steps 1–4, Back navigation, local sign-in without an automatic browser launch, modal refusal and ESC recovery. Its receipt records requested software mode `1` and actual renderer `llvmpipe (LLVM 19.1.7, 256 bits)`. The hardware-request negative control records mode `0` with the same renderer and refuses acceptance. These are separate from the required hardware screenshots.

F17 has complete labels for the measured cloud layouts (59 or 60 targets across repeated runs, including 14 without text or tooltip). The issue reports a different original layout with 71 targets and 16 unlabeled controls. That original inventory has not been supplied, so exact original-target verification remains open; do not substitute the cloud count. Retain the complete original observe receipt and compare every formerly unlabeled target after the fix.

For G14, click every native profile-menu destination in the freshly built candidate: Buy Credits/See Plans and Dashboard must reach the local `/app` landing page; Docs must reach `/app/docs`; Report a Bug must reach `/app/bug-report`. An older executable cannot validate the changed native Docs and Report a Bug call sites.

## Connected GUI status regression evidence

A retained isolated run at source commit `6331e542727e52d9a67a42a4bb3c12e0cac63e3e` passed in 25.15 seconds. After native File-menu opening, modal refusal, ESC recovery and a successful scene inspection, the public MCP `lampway_ui_context` call reported `server_connected=true`, `scene_tools=available`, and an empty `next_step`. This checks the actual connected relay and public status enrichment, rather than a direct helper call. Restoring the former stale-catalog branch only in the disposable script copy made that same run fail: the server was connected but status incorrectly requested reconnect.

The run records these source SHA-256 values; its fixture has uncommitted acceptance assertions on top of the source candidate:

| Source | SHA-256 |
|---|---|
| `tests/lampway_tools/issue2_gui_fixture.py` | `01942187859cb7bbe64480ccc974e8eb2f4621dbad95eb959aace3d34f01a947` |
| `src/scripts/mixar/modules/common/ui_control/core/observe.py` | `ca772b53d2d1a8d7237fb98bd691da05237c5175dcd688bb1576feafc7104f53` |
| `src/scripts/mixar/modules/mcp_bridge/core/availability.py` | `283e9285b8294ebfee7e8004f22d47a1259e91c82523a3294f5480b899719384` |
| `src/scripts/mixar/modules/mcp_bridge/core/connector.py` | `f649bb7ae6cf0bfbb904c7ed0def165e3defdcec2c38c8533cfbe9942d28807b` |
| `src/scripts/mixar/modules/lampway_tools/ui/onboarding.py` | `5ce0b46f075d83bc52e9c5d63879dc70f808b694cb3d1be08709807ff8101868` |

The latest connected run observed 59 targets and labeled all of them, including all 14 text/tooltip-free controls. Fourteen maintained native-shape cases each fail under the old text/tooltip-only fallback and pass under the current source rule. These counts do not close verification of the unavailable original 71-target inventory. The older covering visual test now requires zero empty labels across its complete observed inventory and retains pagination checks.

Source/link audit passed six tests; local account and landing-route checks passed seven. The handoff tree/media gate reported zero findings. Native rebuilt-menu click proof and GPU-backed screenshots remain local QA requirements.
