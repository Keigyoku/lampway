<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# PR3: assigned publication findings

Source: [review5450133925](https://github.com/Keigyoku/lampway/pull/3#pullrequestreview-5450133925), reviewed commit `b16e14b44df26be4b03a5aee621e89b834bf5530`. The captain assigned only its two LOW findings to this branch.

- [Font inventory](https://github.com/Keigyoku/lampway/pull/3#discussion_r4213515895): `THIRD_PARTY.md` now links the tracked `src/release/datafiles/fonts/ClashGrotesk-LICENSE.txt` and records upstream/absent status, matching `NOTICE.md`. No font asset ships or was added.
- [Anneal table](https://github.com/Keigyoku/lampway/pull/3#discussion_r4213515925): removed the blank line before the existing strict-no-red row, preserving all historical row contents. Added the current publication directive/receipt and regenerated both skill copies with `rail.py sync`.

Verification checks the actual licence file, absence of the deleted inventory target, one contiguous pipe table and byte-identical canonical/generated release skills. Full rail and diff checks pass. No changes were made to the first three HIGH/HIGH/MED findings or their motion implementation files.

## Subsequently assigned domain-exemption finding

The captain also assigned [4213654799](https://github.com/Keigyoku/lampway/pull/3#discussion_r4213654799). Main `dfe0d1a448f58dfbf9bffcec9a287c0e21c6ab39` was merged into this branch, retaining both crews' registry/dispatch and rail histories.

The new suffix plants first reproduced **21 failures and seven exact-domain passes**. Bounding the regex alone exposed the separate legacy known-fake-prefix bypass; those RED receipts were retained. The corrected scanner consumes complete hosts, bounds regex exemptions and matches known-fake email exemptions by whole address/host. The legacy example prefix now covers only exact reserved hosts. A fake address cannot suppress a second address on the same line. Retained tests cover three suffix forms across eleven exempt/fake hosts, exact-host controls, existing owner-pattern/matrix refusals and CLI redaction. The gate self-test checks both originally reported lookalikes. Two retained RED filename controls prevented the expanded host matcher from treating versioned prompt JSON names as contacts; the final matcher retains the original alphabetic-label admission while consuming suffix labels. Three responsive-layout fake addresses now use the reserved invalid domain with unchanged total lengths, so no arbitrary domain exception is introduced.

Motion requirements now follow the documentation convention: [method](../canon/motion_graphics/motion_graphics.md), [tool/receipt](../canon/motion_graphics/tool.md) and [scene/workflow](../canon/motion_graphics/scene.md) are indexed in the canon; [acceptance and evidence](motion-graphics-acceptance.md) stay in reports. The original measurements, bounds, open requirements and review history are retained. Production motion changes inherited from main remain its crew's work; this follow-up changes their documentation references only.

Verification: the combined server/MCP merge selection passed **81 tests**. The full merged server suite passed **2,235 tests**, with **54 skips** and no failures/errors. Final privacy/workflow/site-link and responsive-layout checks passed **126 tests**. The complete fork/rail suite passed **559 tests**, with **two skips** and no failures/errors. All **134** audited local Markdown targets resolve; canon goldens, schema and byte determinism pass. These results do not replace hardware/native-owner or full reference acceptance.

Retained receipts: `main-dfe-final-server.xml`, `main-dfe-final-gates-current.xml`, `pr3-final-publication-green.xml`, `pr3-4213654799-red.xml`, `pr3-4213654799-allowlist-red.xml`, `pr3-versioned-filename-red.xml` and `main-dfe-motion-doc-links-final.json`. The complete server skips include optional browser/native tools, private seed/teaser fixtures and consented/live services; no skipped check is counted as a pass. The same-length responsive fixture replacement is unit-tested; its macOS QA script was not executed in this Linux environment.

Publication checks used a tracked-only snapshot (tree `c8dea1d0c470c88e04dc5da0cba7fcda693bc738`): the content/owner-pattern scan returned **zero findings**, and REUSE validated **10,019/10,019 files** with no licence, copyright or read errors. Untracked session data was excluded. Full rail, generated skill copies, canon and whitespace checks pass. This report adds the resulting receipt after that snapshot; the final commit is additionally checked by the publication hook.
