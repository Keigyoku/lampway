<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Issue 2 fit-decision measurements

Run the measurement helper in a copied application runtime with a disposable
scene copy. It writes receipts and candidate images under the project root;
it does not save the input scene, contact a provider, or choose canon defaults.

```sh
COPIED_BIN --background DISPOSABLE_SCENE_COPY.blend --python-exit-code 1 \
  --python scripts/lampway/measure_fit_decisions.py -- \
  --config PROJECT/ac65-config.json
```

The config must be inside its `project_root`. A minimal facing job is:

```json
{
  "project_root": "/absolute/path/to/disposable/project",
  "out": "measurements/decisions.json",
  "jobs": [
    {"id": "helmet-facing", "action": "facing",
     "args": {"object": "RAW_HELMET", "plate": "plates/HelmetFront.png"}}
  ]
}
```

Replace object names from the copied scene inventory and use the actual approved
plate. Facing reports all four cardinal IoUs and the best-minus-second gap without
requiring or applying a margin.

| Action | Explicit inputs | Measured outputs |
|---|---|---|
| `pair` | `kind`, project-relative canonical `body` and `piece` NPZs; authored `turn`, clearance and sides | Common and per-side transforms, sampled body distances, Front/Left/Back images |
| `boots` | Same NPZ inputs and declared pair mode | Width, shaft-height and foot anchors with comparable images and distances |
| `pose` | Existing placed piece, skinned body and armature; explicit DOFs/chain/regions or `candidate` with side, anatomical sign expectation and positive region threshold | Bounded waist/thigh, boot/knee or wrist/forearm search; explicit coupled finger curl targets include the thumb |
| `collar` | Existing chest and actually posed limb section, actual pose receipt, axis and reviewed opening parameters | 10/20/35 mm variants for an informed choice |

`max_samples` controls deterministic distance sampling (1–4096); `image_size`
controls diagnostic renders. The final receipt uses
`lampway.fit-decision-measurements/1`, records each failed job, and leaves
`default_choices_applied` false. The command exits unsuccessfully if any job fails.

Candidate pose envelopes are experiments. Sign expectations and region thresholds
must come from the actual body before recommending defaults. Sampled distances
near native openings require the declared-band review; Blender renders and raw
frame read-back do not establish physical Unreal acceptance. Select collar and
boot alternatives only after reviewing their actual measurements and images.
