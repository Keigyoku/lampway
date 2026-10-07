<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 runtime verification

This is a partial verification report for the continued agent-modes work. It is not an acceptance receipt or permission to
merge. The governing scope is [agent-modes-spec.md](agent-modes-spec.md), including the captain's decisions. Account-backed
adapter execution and a native executable built from the published final head remain required.

## Completed boundaries

| Commit | Change | Retained verification |
|---|---|---|
| `6e90433f` | Separate native mode chip from the model picker | RED mode-chip tests; 95 focused tests passed. Native execution pending. |
| `9f53af5c` | Independent swarm cards and contiguous terminal-tail recovery | RED client/server witnesses; 132 client and 26 server tests passed. |
| `7d1acd4e` | Engine TOON result seam with the accepted PR1 codec | RED six cases; 179 focused server tests passed. |
| `0d847875` | Native chip and real Blender RNA verification fixtures | 2,728 fitter spans/configurations and four RNA tests passed. RNA used the prior native binary. |
| `a7b77710`, `28739a4f` | Repair lifecycle fixtures against the actual runtime | 54 and 46 focused tests passed; five mutation controls detected the relevant defects. |
| `7319ae5f` | Capture MatGen job provenance at construction | RED HTTP-body witness; 38 tests passed. Server-side persistence of the additive metadata is not claimed. |
| `a39b5a04` | Fence old conversations, recover new conversations and defer archives during live work | RED archive, recovery, attachment and pending-command witnesses; 91 client and 41 server tests passed. |
| `ee701bdc` | Verify library discovery through the engine TOON response | RED JSON-only assertion; 12 library/engine tests passed. External MCP retains its existing JSON envelope. |
| `f7ed0958` | Configurable worker deadline, explicit expiry and deterministic fixture teardown | RED deadline/lifetime witnesses; 135 tests passed, no skips or errors. The existing 1,800-second default is a proposal, not a captain ruling. |
| `d2254968`, `4b459845` | Keep a stopped scene bound while fencing retired turns; preserve legacy event recovery | Expanded focused suite: 36 tests passed. Real Blender/Hermes/herdr integration passed using a deterministic local provider and the prior native binary. |
| `10e41390` | Session-owned image-copy records and 30-day expiry | 13 tests passed, including replacements, links, corrupt metadata, restart and original-file preservation. Periodic app maintenance wiring remains pending. |
| `dea9eaa9` | Expire owned image copies after session-registry pruning | RED orphan-expiry and ancestor-link witnesses; 39 retention/Mode 2 controls passed. Private ownership records survive pruning; originals and substituted files remain untouched. |
| `6ac2b45b` | Cursor's supported per-pane plugin route | Final focused suite: 83 tests passed, no skips or errors. Account-backed tool execution remains unverified. |
| `d68c17ac` | Accepted PR1 publication metadata dependency | REUSE 6.2.0 covered 9,847 files with no missing or invalid license expressions. |
| `c7457315` | Self-contained accepted PR1 privacy and workflow controls | 20 scanner and six workflow controls passed; no scanner exemptions or bypass were added. |
| `3b7be613` | Conditional native definitions on interface, View3D and agent-bubble targets | Accepted consumer controls and agent-bubble ON/OFF source controls passed. Six real cached compiler syntax checks passed; newly linked executable and physical clicks remain pending. |
| `6f6701f9` | Separate saved worker mode from its Mode 1 service | 242 focused Choices/runtime tests passed. Receipts pin mode and service separately; the configured-app factory's resolution forwarding remains a shared-file dependency. |
| `d9206cdc` | Scoped accepted PR1 client68 fixes and subtitle recovery | Imported the accepted code/data/licensing dependency and two bounded prerequisites. Full current client verification remains in progress; the shared ROOT AGENTS render-contract link remains pending. |

The integrated Mode 1 fixture exercises actual TUI-originated turns, client steer and Stop, immediate post-Stop recovery,
Blender mutation and Undo, checkpoint mark/rewind, image copying, conversation reset and reopening an ended pane. Its provider
is deterministic and local. It does not establish ChatGPT account access, paid API access, a Mode 2 account session or the new
native chip's rendered behavior.

## Dependency and acceptance gaps

* Saved worker mode and service selection are implemented independently of the parent mode. The actual configured-app factory
  regression still fails until the parent-owned app factory accepts and forwards the pinned resolution. Focused injected-factory
  passes do not establish that integration.
* Conditional native definitions are implemented for interface, View3D and agent-bubble consumers. Actual combined ON/OFF
  compile commands, public Docs/Report helper dependencies and final rendered chip proof remain pending.
* Hermes and Grok currently lack a demonstrated additive, pane-only configuration route that preserves existing login without
  moving credentials. Supported persistent user MCP setup is a concrete owner decision, not an implemented permission grant.
  All seven registered adapters still require the specified real scene-tool acceptance; a terminal opening is insufficient.
* Full client and server suites, exact published-head CI and a matching native build receipt must be recorded after integration.
  Earlier baseline counts, changing-tree runs and opt-in skips are not final acceptance proof.

No force push, merge, deployment, paid provider call, account credential transfer, user desktop operation or private asset
upload was performed by this cloud crew. User originals were not purged; image-expiry tests use their own temporary files.
