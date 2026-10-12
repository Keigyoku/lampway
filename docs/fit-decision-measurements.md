<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Fit candidate measurement handoff

Run `scripts/lampway/measure_fit_decisions.py` inside an explicitly supplied
disposable scene with the matching installed client code. The config must live
inside its `project_root`. The runner never saves the scene or selects canonical
defaults. Its process exit reports failed execution jobs; acceptance is a separate
field in the JSON summary and retained receipt.

For `pair` and `boots` jobs, request body-relative captures with `body_context` at
config or job level. Supply exactly one `npz` (project-relative `V`/`T`, already in
world metres) or `object` (a mesh in the current disposable scene). For an object,
also supply explicit positive `metres_per_unit`; its evaluated world vertices are
converted using that value. `body_relative_views: true` without context refuses.

Supply explicit cardinal `views` and increasing `bounds_m` for the common camera
frame. All candidates keep that frame and their actual placed world coordinates;
the body is blue, the candidate orange. Images are not independently cropped or
recentred. Receipts retain body geometry identity, bounds, image paths and measured
visible pixel counts. An occluded body or candidate is reported as not visible.

The following is a template. Replace every `null` with the owner's measured frame
or chosen acceptance value; null acceptance values refuse, rather than selecting
physical defaults.

```json
{
  "project_root": "<project>",
  "body_context": {
    "npz": "body-posed.npz",
    "views": ["Front", "Left", "Back"],
    "bounds_m": null
  },
  "clearance_acceptance": {
    "min_signed_m": null,
    "max_below_min_vertices": null
  },
  "jobs": [{
    "id": "explicit-boot-candidates",
    "action": "boots",
    "args": {
      "kind": "boots", "body": "body.npz", "piece": "boots.npz",
      "turn": null, "clear_mm": null,
      "pair_scale_group": "per_side", "sides": "both"
    }
  }]
}
```

`min_signed_m` is a finite signed distance in metres;
`max_below_min_vertices` is a nonnegative integer. Measurement checks every placed
vertex, with BVH nearest distances and canonical closed-body pseudonormal signs.
An open body additionally requires explicit positive `body_open_band_m`; signs
within that distance of a boundary refuse and acceptance becomes `null`. Outside
the declared band, open-body signs use generalized winding. Nonmanifold or inward
closed bodies refuse. These controls do not supply missing anatomy or approve a
facing, anchor, pair scaling policy or physical gap.

`job.ok` means execution completed. `candidate.vertex_clearance.pass` and
`job.acceptance.pass` answer only the explicit **all-vertex signed clearance**
limits. A completed measurement can fail those limits. `full_fit_acceptance` stays
`null`: face-interior surface crossings, innermost-layer gap, hideable skin,
material-class limits and owner approval require their own evidence. Diagnostic
sample counts remain separate and cannot select a default.

Native covering test: `tests/lampway_tools/test_decision_body_context.py` checks a
known inside/outside fixture, evaluated object translation, missing context and
limits, path escape, open-body refusal, both objects visible at their supplied
relative positions, temporary ID cleanup and execution/acceptance separation.
