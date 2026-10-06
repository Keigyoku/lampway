<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The UE Renderer

Lampway is where a piece is edited; Unreal Engine 5.8 is where it is judged. The UE Renderer predicts what UE will show and
says, per difference class, how far that prediction can be trusted. It never signs a look off: the final judgement is an
in-engine render.

Code: `src/scripts/mixar/modules/lampway_tools/ue/`. Agent tools: `lampway_ue_material`, `lampway_ue_look`,
`lampway_ue_export`, `lampway_ue_parity`. Panel: Lampway sidebar, **UE Look** (a profile picker and one toggle).

## One profile governs it

`ue/profiles/engine_defaults.json` (schema `lampway.ue-profile/1`) describes the UE scene a piece is judged in. Every field
is required; there are no defaults in the code. The shipped file holds UE 5.8.2's engine defaults, which are **not** the
Titan project: the UE editor leg's live dump replaces it. The captain's open choices are named fields, each with its default
and reason in the file's `notes`:

| field | default | the choice |
|---|---|---|
| `light_units.k` | 683 | the light-unit factor (683 lm/W, Blender's glTF convention; 1 is the alternative) |
| `judgement_surface` | `capture` | the scripted capture, the editor viewport, or `map:<name>` |
| `project.cvars["r.Material.EnergyConservation"]` | 0 | UE's legacy Default Lit; 1 is refused by the material group until it is rebuilt |
| `preview.texture_compression` | `source` | Lampway samples source textures; `bc_decoded` is the alternative |
| `export.precision` | `standard` | UE's import defaults; `hero` asks for 16-bit tangents, full UVs and 16-bit weights |

Two more fields name the tonemapper cube: `tonemap_cube` and `tonemap_cube_meta` (its sidecar). The cube is generated on the
UE side and read as data; Lampway holds none of the tonemapper's maths ([UE Look](../ue-look.md)).

## The parts

- **UE Default Lit material** (`ue_material`): a deterministic Principled -> Default Lit map (BaseColor clamped, Specular from
  IOR and level clamped at UE's 0.08 F0, Emissive x k, Masked at 0.3333, Two Sided = not backface culling), a loss report and
  `translation_sha256`; the `LW_UE_DefaultLit_v1` node group adds Lambert to one single-scatter GGX lobe with UE's F0 and its
  F90 = saturate(50 F0.g), and reads DirectX normals with Z rebuilt. Preview builds `<material> [UE]` beside the original.
- **UE Look mode** (`ue_look`): enable / apply / status / revert / disable. Apply writes a receipt of every value it changed
  (and the cube's sha256 and engine version); revert restores them byte for byte; a failure part-way rolls back. Apply needs a
  valid cube (`ue/cube.py`), else it refuses with the fix.
- **UE view** (`ue_look generate` / `enable`): the sidecar's log2 shaper and the cube, read where it lies, added to the app's
  OCIO config under `<lampway data>/ue_look/<key8>/ocio/` (key: the cube's sha256 and shaper). The launcher starts Lampway
  with `OCIO=<that config>` while UE Look is enabled and the cube validates; a config that failed to load (Blender falls back
  to AgX silently) and a cube changed on disk (Blender keeps the old one) are both refused.
- **UE export** (`ue_export`): one canonical FBX path per type (`skinned_piece`, `static_prop`, `animation`, `texture_set`),
  canonical input only (metres, transforms applied), one fixed triangulation shared with the bake, `content_sha256` with the
  FBX timestamp zeroed, and `ue_import.json`, the only import settings the editor leg may use.
- **Parity harness** (`ue_parity`): standard scenes (chart, furnace, normals, lights) from one JSON description, rendered
  headless in EEVEE under the parity rules to float EXR, compared per class against fixed tolerances when the UE captures
  exist. The UE half needs box time (`needs_box`).

Status and measured numbers: `docs/reports/uelook.md`. Specification: `specs/ue_parity/` (outside this repository).
