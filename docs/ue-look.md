<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# UE Look: pointing Lampway at the tonemapper cube

UE Look shows a piece the way Unreal Engine 5.8 will: exposure, lights, materials and, through an OCIO view, UE's tonemapper.
The tonemapper is a 32x32x32 colour cube. **The cube is generated on the UE side**, by a generator that lives outside Lampway
(with the Titan project, under UE's licence). Lampway contains none of the tonemapper's maths: it reads the cube as data,
checks it against its sidecar, and never copies or redistributes it. It keeps only the cube's path and sha256.

## 1. Generate the cube on the UE side

The generator writes two files:

- `<name>.cube`: a 3D `.cube` (Adobe/Resolve format, red fastest), `LUT_3D_SIZE` equal to the project's `r.LUT.Size` (32),
  sampled on UE's log2 grid.
- `<name>.cube.json`: the sidecar, schema `lampway.ue-cube-meta/1`:

```json
{"schema": "lampway.ue-cube-meta/1",
 "engine": {"version": "5.8.2", "changelist": 56702186},
 "tonemapper": {"method": "Filmic", "film": {"slope": 0.88, "toe": 0.55, "shoulder": 0.26, "black_clip": 0.0, "white_clip": 0.04},
                "blue_correction": 0.6, "expand_gamut": 1.0, "tone_curve_amount": 1.0, "white_temp": 6500, "white_tint": 0,
                "grading": "neutral"},
 "generator": {"name": "<the UE-side generator>", "version": "<its version>"},
 "cube": {"file": "<name>.cube", "sha256": "<sha256 of the .cube bytes>", "size": 32,
          "domain_min": [0, 0, 0], "domain_max": [1, 1, 1], "order": "red_fastest"},
 "shaper": {"base": 2, "lin_side_slope": 1, "lin_side_offset": "<number>", "log_side_slope": "<number>", "log_side_offset": "<number>"}}
```

`tonemapper` must equal the UE Look profile's `tonemap` block, and `engine.version` the profile's engine version. `shaper` is
the log2 encoding the cube was sampled in (an OCIO `LogAffineTransform`). It comes from the generator too, because it is
part of UE's grid.

## 2. Point UE Look at it

Either way works:

- **In the app:** the Lampway sidebar, **UE Look**: pick the profile (empty = the shipped engine defaults, which are not the
  project), the **Tonemapper cube** and the **Cube sidecar**. The glyph next to them says **valid**, **missing** or
  **mismatch** (with the reason). Then press **UE Look**.
- **In the profile:** set `tonemap_cube` and `tonemap_cube_meta` to the two paths (`lampway.ue-profile/1`).

The check runs whenever a path changes and again at every apply. It covers:

- both files are present;
- the sidecar's schema;
- the cube's sha256 equals the sidecar's;
- the grid: `LUT_3D_SIZE`, the sidecar's size and `r.LUT.Size` agree, with exactly size³ finite rows;
- the domain equals the sidecar's;
- the engine version equals the profile's;
- the tonemapper settings equal the profile's.

Any failure refuses with: *generate the cube on the UE side, then point UE Look at it*.

## 3. Restart once

Blender reads its colour configuration (`OCIO`) once, at start. Turning UE Look on writes the UE view's OCIO config under
`<lampway data>/ue_look/<key>/ocio/` and the launcher's state file `<lampway data>/ue_look/launch.state`. The config points at
the cube where it lies; it is not a copy. If the running session lacks the view, the toggle says *restart Lampway*.

`scripts/lampway/lampway` exports `OCIO=<that config>` only when the state file exists, the config exists and the cube's
sha256 is still the one recorded. Otherwise it leaves `OCIO` exactly as it was and says why. `lampway --plan` prints
`ue_look: on | off | invalid`. Turning UE Look off reverts the scene exactly and removes the state file.

## 4. What is recorded

The UE Look receipt, every parity report (`ue_parity`) and every export receipt (`ue_export`, `export.json` →
`ue_look_cube`) record the cube's path, sha256, engine version and generator, never its data.

## 5. Traps it refuses

- **A broken OCIO config:** Blender logs one line and silently falls back to its built-in config (AgX). Apply checks that the
  UE view exists in this session and refuses otherwise.
- **A cube changed after Blender loaded it:** Blender keeps the cube it already read.
  - Edited alone, the cube no longer matches its sidecar's sha256: refused.
  - Re-described by a new sidecar, it is a new view name the running session does not have: refused until a restart.

See also: [The UE Renderer](lampway/ue-renderer.md).
