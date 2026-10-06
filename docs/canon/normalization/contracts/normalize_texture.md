<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# Contract: `lampway_normalize_texture` and `lampway_normalize_material`

Status: **new** (absorbs the role-to-colour-space logic of `asset_place_shading.py:13`, :80-92 and `pbr_pack`'s conventions).
Priority P1. Placeholders as in `../AUDIT.md`.

## 1. Name and one-line purpose
`lampway_normalize_texture` / `normalize_texture`: an image into a canonical `texture` (role, colour space, normal convention,
UV binding or physical tiling). `lampway_normalize_material` / `normalize_material`: a Blender material or a texture set into a
canonical `material` (one model, every channel bound to a canonical texture).

## 2. Source
- ue_parity TEX-01: "Blender loads every 8- and 16-bit PNG as sRGB, data maps included ... A data map read as sRGB is wrong on both sides by default." NRM-01: "UE expects DirectX (Y-) and Interchange does not flip on import."
- AUDIT rank 10: `SRV/library/ingest.py:113-121` (no colour space, no convention), `SRV/library/cc0.py:260` (whole set sRGB), `LT/pipeline/pbr_pack.py:7` (input normal assumed GL), `LT/features/bake.py:112-113` (DX attached without a flip).

## 3. User story
Runs when an image enters (Vault ingest, a Studio texture pass, a bake, a CC0 fetch) and when a material is placed or exported.
`pbr_pack`, `bake_maps attach`, `asset_place assign_maps` and `fit_export` then read the convention instead of assuming it.

## 4. Inputs
```json
{"input": "image name | project path", "role": "auto | basecolor | normal | roughness | metallic | ao | orm | height | emission | opacity | mask | material_id | curvature | hdri | reference",
 "normal_convention": "auto | gl | dx", "uv_mesh": "canonical mesh asset id | null", "uv_set": "name | null",
 "tiling_real_world_m": "[w, h] | null", "source_naming": "ambientcg | polyhaven | tripo | lampway | none"}
```
Material: `{"material": "name | asset id", "class": "metal | leather | cloth | embroidery | skin | other (the captain's or the recipe's)"}`.

## 5. Outputs
`{ok, document, receipt}`; the image's `colorspace_settings.name` set from the role; for a material, a Principled BSDF wired
by role (DX normals through the green flip of `asset_place_shading._flip_green`, :95-104), stamped.

## 6. Engine (proven code)
Role from the source's naming tables (`cc0.py:33-38` `ACG_SUFFIX`, :35 `PH_KEYS`; `pbr_pack` file names; Lampway bake outputs
name their map), else declared. Normal convention: from the naming (`_NormalGL`, `nor_dx`), from Lampway's own bake settings
(`scripts/bake/bake_maps.py:49-51`, `material_bake_export`), else declared, else a **sign test**: on a mesh with the map's UV
binding, the mean green channel over faces whose tangent-space bump is known from the high-poly (a bake pair) or from a
height map [UNVERIFIED method; until measured, `auto` refuses rather than guesses].

## 7. Model slot
None.

## 8. Preconditions and refusals
"role unknown for <file>: declare role=<...>"; "normal convention unknown: declare normal_convention=gl|dx (it is never
assumed)"; "a data role cannot be sRGB: the file is 8-bit sRGB-encoded data, re-export it linear or declare role=reference";
material: "channel roughness is bound to an image whose role is basecolor".

## 9. Side effects and safety
Sets colour-space flags on images (no pixel change); a green flip happens in nodes or, for an export, in a NEW file
(`pbr_pack` already writes both conventions, :79-83). Never overwrites an image file.

## 10. Tests (RED first)
1. RED `test_cc0_set_is_not_all_srgb`: importing a fixture ambientCG set records `colorspace: sRGB` for the set today (`cc0.py:260`); after, each map document has its own colour space and the normal its `gl` convention.
2. RED `test_bake_attach_dx`: `bake_maps attach` with `normal_green=dx` wires the image straight into a Normal Map node today (`bake.py:112-113`); a lit sphere render differs from the GL bake by the green inversion. After: identical renders.
3. `test_pbr_pack_reads_declared_convention`: a DX input normal packs into `Normal_GL` with green flipped back (today it is passed through as GL).
4. `test_role_colour_space_table`: every role in SCHEMA.md §4.5 maps to its colour space; falsifier: a roughness map left sRGB reads 0.214 for 0.5 (ue_parity TEX-01's number).

## 11. Acceptance evidence
The chest's PBR set (`pbr_merge` output) normalized: six documents, a material document, and a Workbench/EEVEE capture identical
before and after on the GL path.

## 12. Dependencies and order
`canon_asset`, `canon_door`; `normalize_mesh` for UV bindings.

## 13. Open questions
None new (the UE-side colour-space recipe is ue_parity's `ue_material`).
