<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue 2 original-input normalization and export

This records owner-local execution on a disposable copy of the original native
MetaHuman reference. The input SHA256 is
`24c9a568b267dc62fc929a02b4deff3b3bbaae7adf4d5e323f8dc09a15297e32`.
Original inputs remained unchanged. Private paths and asset bytes are excluded.

The retained receipt uses Python candidate
`c4e91c37f7ac6290a44cc2fc42d1a7bdb9c383f0` over the genuine native build from
`6331e542727e52d9a67a42a4bb3c12e0cac63e3e`. The binary SHA256 is
`1e74974fbaeb0562c5de3f0eb7401d0f4578cd1017c12c16b09d6293b4a04840`.
The downloaded five-file receipt archive SHA256 is
`8c8cb9b78a9374940b948ca712dfdf4821a29f3f8f3159e843256ae31b130b83`.

| Stage | Observed result |
|---|---|
| Native inspection, mapping and conforming | Completed on the copied reference |
| `normalize_rigged`, `dry_run=false` | Refused at `pinky_03_l`: children `pinky_03_bulge_l` and `pinky_03_half_l` had no named continuation |
| Default `rig_export_ue` | Passed raw FBX read-back with the automatically selected `cm_native_blender_convention` recipe |

The export compared all **342 bones**:

| Measure | Worst observed | Unchanged rejection bar |
|---|---:|---:|
| Position | 0.000137876638 cm | 0.01 cm |
| Rotation | 0.004269356562 degrees | 0.01 degrees |
| Scale difference | 0.000035643578 | 0.0001 |

No bone exceeded the bars. This export followed a normalization refusal, so it
does not establish the successful normalization/default-export chain required by
AC15 and AC24, or physical Unreal parity.

The terminal-finger correction at
[`a0cb76dd`](https://github.com/Keigyoku/lampway/commit/a0cb76dd6d025a9d3bf84612eaab89d2c8be10b4)
was rerun on the copied original. Normalization advanced to the auxiliary
`pinky_03_half_l` branch, then refused its children `pinky_02_dip_l` and
`pinky_03_in_l`. Default export still passed the 342-bone read-back. AC15 remains
incomplete; individual terminal corrections do not establish full-rig support.

The complete 342-bone parent/child/deform topology has now been delivered as
metadata without geometry or weights. Its source archive SHA256 is
`88eae37c86ea250eb459bf22c2edbda5c2fc7f6aa3a7e87109829b8851972fa3`.
A complete helper-chain policy and topology regression are in progress.

The subsequent owner-local receipt archive SHA256 is
`ce13643bad433705fad5a7296da88d033612a15359fdbb5c9f3a1d3536822f39`.
It records Python candidate `a0cb76dd6d025a9d3bf84612eaab89d2c8be10b4`
over native build `6331e542727e52d9a67a42a4bb3c12e0cac63e3e`:

| Check | Observed result and limit |
|---|---|
| Hardware UI | Passed onboarding and Back navigation, 64 current visible labels, paging, modal refusal/ESC recovery and connected scene tools on NVIDIA RTX 4070 Ti SUPER with driver 615.71.09 |
| Application exit | Blender exited 0; the isolated gamescope compositor separately crashed with teardown status -11 |
| Actual chest frame parity | Raw input with experimental -90-degree facing and normalized input with zero residual facing produced identical ratios, deviations, placement and tight-front scores |
| Input integrity | All ten original input hashes remained unchanged |

The current 64-control GUI run and original 71-control inventory are distinct
proofs. The chest experiment does not approve a plate or a facing default.
Unreal/MetaTailor parity and the complete normalization/default-export chain
remain open.
