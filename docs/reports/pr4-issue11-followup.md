<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue #11 implementation follow-up

This follow-up consumes the [current local acceptance record](https://github.com/Keigyoku/lampway/issues/11)
for source `fdca31642db312b76943fb9bb8932f6a714dcbf8`, base
`dfe0d1a448f58dfbf9bffcec9a287c0e21c6ab39`. It does not certify overall acceptance.

The downloaded repair archive matches its reported SHA256
`56bafe9922b3542f79fd4f0745b309a2152676fe432fb0045261e63e7885f1cc`;
all 238 archived member sizes and hashes were verified. Its complete maintained client run is RED:
9,720 passed, 34 failed, four errors and 47 skipped. The original log affirmatively passes
all 122 baseline identities, with none failed or unverified.

## Implemented

- **P4-T01:** positive model-free adapter argv/wiring tests now select an isolated, owned compatible Pi version fixture.
  Actual detection and compatibility checks remain active. Missing, older, unknown and prerelease ambient installations
  have separate controls. All original test bodies/assertions remain unchanged. Controlled ambient 0.84.2 RED:
  seven failures and 29 passes. Corrected effect-refusing control: 40 passes. Focused adapter, compatibility and worker
  suite: 79 passes, zero skips/errors. No shared CLI upgrade or production admission change.
- **P4-T02:** opt-in compiler/controller prerequisites use the normal engine resolver's exact destination and verify
  `engine.json` against its normal pin/route record. Verified tagless SHA destinations and explicit engine roots work;
  foreign, missing or malformed manifests and changed checkout pins refuse. Causal synthetic tagless RED: one failure.
  Corrected TUI/engine-resolver packet: 45 passes, zero skips. Actual compiler/controller checks use the currently
  installed normal release-tag build; the tagless path control is synthetic. Original Node scripts, assertions,
  effect guards, timeouts and opt-in markers remain unchanged.
- **P4-T03:** removed exactly the 122 baseline identities after verifying their affirmative per-case PASS receipts in
  the matching FDCA whole-client log and rerunning the same 122 identities in cloud: 122 passes, zero skips/errors,
  1.14 seconds. No test was deleted or weakened. The empty baseline does not excuse any other failure.

Maintained gate/rail tests also pass: 91 passes. Full server and publication results for the eventual published follow-up
head belong in the PR description; these focused receipts do not replace them or a complete green client gate.

## Local proof and remaining work

The verified local record contains a normal matching FDCA application build, automatic bare stamp and binary SHA256
`f0a9cf226fbcbe89f68b3d359f90abd6c1e94c41147c1d689770c7b97f3152c6`, normal pinned Hermes/herdr builds,
and a complete server run with 3,349 passes and 16 skips. Its maintained native integrated test passes pane-origin
steer/Stop and Blender Undo, pane `/new`, production History opening and disconnected pre-new file reopening in
synthetic-login scope. Both procedural-material cases pass with their original assertions and deadlines.

These are FDCA receipts, not receipts for a later follow-up head. Physical purge ownership, complete OFF build/runtime,
remaining preferences/Context/skill-review/history/worker UI scopes and authorized real-account proof remain individually
tracked in issue #11. All skips retain their original unavailable-prerequisite status.

Current native Grok 1.0.46 CI still fails canonical MCP retention on hostile hot reload in both phases. Controlled
source checks do not qualify that boundary, and Grok workers remain refused. No new trust or security grant is inferred.

Inherited intake, hidden-armature, proportion/AXI and onboarding-footer repairs belong to PR1. Their published freeze is
`6b99d1730e10db1aec790658b0e09d4c564d180d`; integration requires the shared owners' compatibility reconciliation and
fresh combined proof. The shared full-client qualification failures remain RED and PR1-owned. Mixed-axis export is still
unresolved on both tips; issue #10 retains its explicit post-merge follow-ups. No codec, registry or scanner is rewritten here.
