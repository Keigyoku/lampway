<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# PR4 cloud follow-up repairs

The follow-up source audit starts from published `1f25fa6e801effcfafc857796e7db9ee05ae47ce`.
It identified two live native-transcript defects and one latent activity-classifier defect without using accounts.

- A complete JSONL row larger than the one-poll read bound stalled every later poll at its prefix. The observer now
  advances a separate scan cursor and spools unfinished bytes in Lampway-owned anonymous temporary state. Native reads
  remain bounded, complete offsets remain exact and no record-size cap or drop is introduced. Replacement, observed
  truncation, explicit cursor reset, read/spool errors and cancellation have controls. Forget does not block the event loop
  while a completed JSON value is decoded; that completed value still requires memory proportional to its size.
- Replacing Codex task A with B failed to retire A. A late completion, abort, message or tool record could change or close B.
  The mirror now retires replaced IDs and ignores foreign explicit non-start identities while an explicit task is active,
  including an old task whose start observation missed. Legitimate new starts, current IDs, unidentified legacy records
  and existing message/tool echoes retain their behavior.
- The reusable activity classifier changed working/waiting to idle before rejecting an already completed identity.
  Duplicate rejection now precedes mutation. No production consumer of that classifier was identified, so this repair
  is not presented as proof of the live island's activity display.

The reader's causal RED is one failed large-record test; its focused packet passes **44 tests without skips**.
The observer's initial causal RED is **20 failures and 2 passes**; the missing-start follow-up RED adds **8 failures and
22 passes**. The final observer packet passes **57 tests without skips**. The packets include overlapping existing controls
and are not added together as unique coverage. The combined reader, stale-turn, mirror, view, island-control and activity
packet passes **101 tests without skips** in 14.151 seconds. Pure controls do not establish real account-backed execution.

The required complete server suite on the committed successor and its publication gates are separate closeout work.
The matching normal application build, complete client/native UI proof, account-backed harness acceptance and the existing
parent-owned local GPU/browser/private-fixture lanes remain unverified by these source packets. Earlier receipts remain
historical rather than being relabelled as successor proof.

The reopened Grok interface audit found no valid preserving fix in the inspected native mechanisms. The public child-session
flag changes history and Stop semantics and leaves other MCP mutation paths open; agent overlays and separate pools do not
provide an immutable connector for the selected native primary session. This is not a proof that no solution exists.
Both observed native 1.0.46 canonical-retention failures remain unresolved. The downloaded 1.0.50 did not execute because
its required namespace prerequisite failed; workers remain refused, with no pin change, account call or trust grant.
