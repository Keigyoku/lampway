<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->
# PR4 runtime verification

This is a partial verification report for the continued agent-modes work. It is not an acceptance receipt or permission to
merge. The governing scope is [agent-modes-spec.md](agent-modes-spec.md), including the captain's decisions. Account-backed
adapter execution and exact final-head verification remain required. Historical short commit IDs below name the
pre-publication checkpoints; those unpublished commits were replayed with the required release-skill anneal before normal push.

## Completed boundaries

| Commit | Change | Retained verification |
|---|---|---|
| `6e90433f` | Separate native mode chip from the model picker | RED mode-chip tests; 95 focused tests passed. Native execution subsequently verified at published `eeb3039d`; see current checkpoint below. |
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

## Published native checkpoint

Published PR4 `eeb3039d4edc3ecc1d842aa12b038de2d755d1ab` has a clean source/bare matching `BUILT_FROM` receipt.
The native binary SHA-256 is `795dee99a94835145d9e8b9724d6fa23f570fcab089c62908aa337318f0e176c`.
Actual native GUI checks show a separate, positive-height Mode chip beside Model, correct BYOA tooltip, and a mouse-opened
registered Mode menu. The five fitter/RNA checks and eleven native consumer ON/OFF syntax/branch and planted-definition
controls passed. Physical View3D drawer and brand tests measured both requested palette changes. This is not a full OFF build.
All 54 required checkpoint identities passed together on that published head with no skips. Its full client suite is still
running and has recorded failures; earlier baseline counts and changing-tree runs are not final acceptance evidence.

## Scoped completion repairs

PR4 now owns the production configured-app wiring. The app factory forwards the pinned worker resolution with its existing
app-owned authentication; the idle maintenance tick applies the established 30-day owned-copy policy and joins in-flight
expiry on shutdown. Originals and replacement/unrecorded files remain untouched. The bounded public Docs/Report operators,
registrations and local routes retain the accepted PR1 helper interface. Focused app checks passed 25/25; auth helper and
existing refresh checks passed 14/14. Valid dimensioned SVG fixtures passed both launcher controls with the real renderer.

Worker token revocation cancels every active model request for that key even while TCP stays open, including concurrent calls;
main requests are unaffected. Owned worker Stop and confirmed worker close revoke before pane shutdown. The 152 focused lifetime,
wiring and provider controls passed without skips; both actual two-worker Stop phases passed with the repaired server and
prior published binary. This mixed-source diagnostic is not final-head/build acceptance. Existing main-pane close token
behavior was not changed by the worker repair.

The exact three-file PR1 dependency `323d44b99e5c4418e5412de710bbc436982034d5` is imported with provenance. Its R04 angle
measurement uses `atan2(cross norm, dot)` to preserve actual angles without BLAS-dependent arccos amplification; matrices,
keys, tolerances, falsifiers and the exact-byte gate remain intact. PR1's published `b1e300cf` canon CI passed. PR4 must
still earn its own current-head canon CI after publication.

## Remaining acceptance and decisions

* Saved worker mode and service are separate and the configured production factory consumes the worker resolution. The initial
  unsaved service still derives from main settings in `choices.bridge.chains`; the current independence ruling is documented
  separately from the older follow-main default. Its exact initial service policy remains unresolved.
* Complete the full client/server suites and exact final published-head CI; build and retain a matching receipt after these
  scoped repairs, then rerun actual Stop, profile Docs/Report, native Mode and palette checks against that same candidate.
* All seven adapters still require real account-backed scene-tool, interrupt, image and session-record acceptance. No provider,
  paid-call, credential or persistent-grant authorization has been supplied. Grok 1.0.46 symbolic MCP variables work in concurrent
  offline doctor checks, but the primary custom-agent activation did not apply scoped MCP during a network-denied synthetic
  first turn. A persistent setup exception is not ready to approve until its isolation is technically demonstrated. User Hermes's
  compatible login-preserving pane route also remains unproved. A terminal opening or offline probe is not account acceptance.

No force push, merge, deployment, paid provider call, account credential transfer, user desktop operation or private asset
upload was performed by this cloud crew. User originals were not purged; image-expiry tests use their own temporary files.
