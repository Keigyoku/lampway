---
# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
anneal_on_error: true
anneal_on_success: true
anneal_safety: gated
verification-mode: deterministic
---

# docs/canon — the algorithm canon

One specification per core 3D algorithm (pages 01-22), the agent-facing rig-tool rewrites (`rig_tools/`), the canonical asset
schema and its door (`normalization/`), and the goldens with their generators, reference implementations and self-tests
(`goldens/`). [`INDEX.md`](INDEX.md) is the table of contents and the authority for each page's status. Agents load the
`lampway-canon` skill before any fit, rig, weight, pose, placement, proportion, retopology, UV, bake, clearance or normalization
work.


Issue2 supersedes the inevitably refused default export recipe with selection from measured normalized frames, retaining explicit Titan and mandatory physical M-RIG-01 confirmation. Keep native metacarpal fanout and120° corrective-roll default-export falsifiers.

## Invariants

1. **This copy is the source of truth.** It replaced the spec shelf's `specs/canon/` on 2026-10-06; edits land here, through a
   lane, never on the shelf.
2. **The goldens are generated, never hand-edited.** Change `goldens/gen_goldens.py` or `gen_rig_goldens.py`, regenerate, and
   commit the generator and its output together; the committed case files must equal a fresh run byte for byte.
3. **Every golden keeps its falsifier.** A case pins the canonical method AND shows the known-wrong method failing it; removing a
   falsifier, or loosening a tolerance to pass, is a doctrine change and needs the ruling it rests on.
4. **A page's open decision stays open** until the captain rules; the page's D table gains the row (date, what, ruling) in the
   same change as the ruling.
5. **No large binaries and no owner assets.** The goldens are synthetic; the MetaTailor exports stay out of git and
   `goldens/metatailor/README.md` records their SHA-256. A number measured on one of the captain's pieces is cited, not committed.

Canon 03 records analytical seam topology and generalized winding for native
openings; Canon 17 records authored MetaHuman corrective fan-out frames. R02's
regenerated corrective golden preserves 120° roll and retains the existing frame
and retarget falsifiers. The applied normalizer is verified on the corresponding
binary shape, while actual owner-asset receipts are reported separately.

Canon 08 distinguishes its accepted complete helmet table from still unspecified numerical rows for other kinds. The implementation uses named axes and retains sign falsifiers; the glove engine wiring does not infer mirror labels or substitute a pose model.

The normalize_mesh contract names the native cardinal-facing golden and symmetric tie falsifier. Canon 10 fixes native plate aspect and border-ring keying; the D6 default remains unset until a numeric ruling, while explicit margins exercise the implemented engine.

## Test

```bash
python3 docs/canon/check_canon.py               # the three self-tests + byte-identical goldens (numpy, jsonschema)
python3 docs/canon/check_canon.py --self-test   # a hand-edited golden in a scratch copy must be refused
```

CI runs both on every push and pull request (`.github/workflows/canon.yml`).

## Owner

The canon's authors (the canon and normalization auditors) wrote it; from 2026-10-06 a change is made by the lane whose work
needs it and lands through the integration lane. Statuses, thresholds and the decisions a page names are the captain's.

## Anneal log

| date | change-shape | trigger | failure-mode | fix-into-directive | promote-candidate |
|---|---|---|---|---|---|
| 2026-10-06 | canon into the repository | coordinator: "GO for rail row 1" (the captain's recommendation 1) | the canon lived on an off-tree shelf, so agents had no tracked page to load and nothing kept its goldens honest | the canon copied to docs/canon as the source of truth, its invariants stated, `check_canon.py` and its self-test in CI | captain ruling, 2026-10-06 |

| 2026-10-07 | native topology and corrective-root canon | issue 2 G2/G4 | closed-only intake and continuation-only normalization rejected native shapes | document analytical winding intake and authored corrective frames with regenerated R02 evidence | issue 2 acceptance receipts |

| 2026-10-07 | accepted helmet table | captain requested canon-recommended typed defaults | complete proposal remained stubbed while other numeric rows were absent | record the complete helmet proposal as accepted and keep other absent numerical rows explicit | issue 2 |

| 2026-10-07 | cardinal facing golden | issue 2 AC65 | plate registration had no implementation despite its existing canon engine contract | pin winning rotation and tie refusal against real rendered masks with explicit margin | canon 10 and normalization contract |

| 2026-10-07 | native MetaHuman normalization and export defaults | actual owner G4/G5 failures and issue2 default-chain instruction | metacarpal slide fanout lacked continuation and default recipe always rejected normalized frames | Issue2 supersedes the inevitably refused default export recipe with selection from measured normalized frames, retaining explicit Titan and mandatory physical M-RIG-01 confirmation. Keep native metacarpal fanout and120° corrective-roll default-export falsifiers. | native metacarpal and both-convention export RED/GREEN; UE proof remains pending |
