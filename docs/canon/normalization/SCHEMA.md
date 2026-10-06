<!-- SPDX-FileCopyrightText: 2026 Lampway contributors -->
<!-- SPDX-License-Identifier: GPL-3.0-or-later -->

# The canonical asset: `lampway.canonical-asset/1`

Status: **DRAFT for the captain's decisions D1-D4 (REPORT.md)**; the machine schema validates (self-test below).
Machine schema: [`canonical-asset.schema.json`](canonical-asset.schema.json) (JSON Schema draft 2020-12, `$id`
`lampway.canonical-asset/1`). Examples and their self-test: [`canonical-asset.examples.json`](canonical-asset.examples.json),
[`selftest_schema.py`](selftest_schema.py) (`python3 selftest_schema.py`: 3 valid and 7 invalid cases, 0 mismatches on
2026-10-06). Builds on canon 01 (frames, bones, identities), 17 (rest frames), 18 (units), 22 (canonical animation).

## 1. What "canonical" means, in one paragraph

A canonical asset is the one form every Lampway tool may assume: **metres, right-handed, +Z up, the body faces -Y, the
wearer's left is +X** (canon 01 B, the body frame), object transforms applied (or the reason they are not, recorded), a
**scale state** with its evidence, bones described by **head -> next joint** in one declared convention with a named rest pose
and names mapped to a reference skeleton, topology flags that say whether seam-split vertices were welded, UVs with one
origin rule, every texture tagged with a colour space consistent with its role and every normal map with its green-channel
convention, one material model, and the sha256 of the raw bytes it came from. It is written only by a `lampway_normalize_<kind>`
tool and checked at every tool's door.

## 2. Two layers of frame, kept apart

| layer | convention | who uses it | how it is reached |
|---|---|---|---|
| **working canonical** (this schema) | `lampway.body/1`: m, right-handed, +Z up, front -Y, left +X | every Lampway tool inside Blender and every npz/JSON a tool writes | `lampway_normalize_<kind>` from any raw input |
| **interchange** (canon 22, Titan `canon.py`) | `titan.canonical-mesh/1`: cm, left-handed, +X forward, +Y right, +Z up | Titan's converters and the engine | an adapter (`to-titan`, `to-ue`) from the working form; never stored as working canonical |

The two coexist by design (canon REPORT contradiction 18, "both, at different layers, mapped by an adapter"); the captain has
not yet confirmed it (decision D1). This schema never encodes the interchange frame: a document whose `conventions.frame` is
anything but `lampway.body/1` is invalid.

## 3. The header every kind carries

| field | type | invariant |
|---|---|---|
| `schema`, `schema_version` | `"lampway.canonical-asset"`, `1` | a new version is a migration, never an edit |
| `kind` | `mesh, rigged_mesh, skeleton, animation_clip, texture, material, part, set` | selects `body` |
| `asset_id` | string | the Vault asset id of the CANONICAL version |
| `raw` | `{sha256, container, bytes, path_hint?, vault_asset_id?, vault_version?, generator{source, action?, job_id?, model_version?, derived_from?}}` | `raw.sha256` is the sha256 of the bytes as they arrived; the raw file is never modified and stays in the Vault |
| `conventions` | `{frame, up, front, wearer_left, handedness, units, source_frame{name, up, front, units_per_m?}, axis_map (3x3), axis_map_det (+1 or -1), turn_deg, winding_reversed, frame_decision{kind, evidence}}` | `frame/up/front/wearer_left/handedness/units` are constants; `axis_map_det = -1` requires `winding_reversed = true` (canon 01 D.4); `frame_decision.kind` is `already_canonical`, `declared` (a recipe or caller turn), `measured` (plate silhouette registration, skeleton features) or `source_convention` (a source that obeys its own spec); `unknown` does not exist: the normalizer refuses instead |
| `transform` | `{applied, object_matrix (4x4), not_applied_reason?}` | `applied = true` requires the identity matrix; `false` requires a reason (`skinned_rig_preserved`, `placed_instance`, `linked_library`) |
| `scale` | `{state, decision, factor_applied, uniform: true, evidence?, generator_norm?}` | see 3.1 |
| `pivot` | `{rule, offset_m?}` | required for mesh, rigged_mesh, part: `bbox_bottom_centre` (unplaced), `body_frame_placed` (after `fit_place`), `source_origin`, `skeleton_root` |
| `normalized_by` | `{tool: lampway_normalize_<kind>, tool_version, blender_version?}` | only a normalizer writes a document |
| `canonical_sha256` | sha256 | over the canonical file's bytes (or, for a scene datablock, over the canonical payload: `geometry_sha256` + `uv` + `materials`) |
| `receipt_sha256` | sha256 | of the normalize receipt (DOOR.md §3) |

### 3.1 Scale: three states, never a guess

| `state` | meaning | `decision` | required |
|---|---|---|---|
| `real` | one metre in the data is one metre on the body | `measured` (scale_to_measure, a reference-height ratio within canon 18's 5 % rule), `derived_from_body` (`fit_place` enclosure), `declared` (the captain's length), `source_real_world` (a vendor's real-scale output: Tripo API `auto_size`, Hyper3D `bbox_condition` [UNVERIFIED until measured]) | `evidence{method, value, reference?, ratio?, receipt_sha256?}` |
| `generator_normalised` | the generator rescaled it (Tripo: ~0.98 m on the longest side, canon 01 B) | `none` | `generator_norm{longest_side_m, source}` |
| `unknown` | no evidence either way | `none`, `factor_applied = 1` | nothing; any door that needs `real` refuses |

`units` is always `m`. A tool states which scale states it accepts (DOOR.md §2): scale-free tools (proportion ratios, model
compare, similarity, silhouettes after bbox fit) accept all three; tools with absolute thresholds (weights, clearance,
openings, defect thresholds, texel density, procedural materials, validation limits) accept only `real`. **An armour piece
never becomes `real` by a guess:** the normalizer writes `generator_normalised` and the piece becomes `real` only through
`fit_place` or `scale_to_measure`, each of which re-stamps it with its evidence.

## 4. Per kind

The JSON Schema `$defs` hold every field and type; this section states each kind's purpose and the invariants a reviewer must
know. Invariants marked **(code)** cannot be expressed in JSON Schema and are checked by `canon_asset.check(doc, datablock)`
(contract `canon_asset.md`).

### 4.1 `mesh` (`MeshBody`)

| field | invariant |
|---|---|
| `bbox_min_m`, `bbox_max_m` | in canonical coordinates; **(code)** equal to the datablock's measured bounds within 1e-6 m |
| `topology{verts, faces, tris, quads, ngons, welded, weld{rule, distance_m, vertices_merged, refused_reason?}, split_by_uv_seam_in_raw, manifold, non_manifold_edges, boundary_loops, shells, winding_consistent, degenerate_faces, triangulation_sha256?}` | `welded` requires `weld.rule = position` with distance and count; `manifold` requires 0 non-manifold edges. A generated mesh is welded by position (canon 01 D.1; default 1e-5 m, decision D5); an authored rig mesh is never welded (`refused_reason: authored_rig`, canon 01 D.2). `shells` counts AFTER the weld |
| `uv_sets[]{name, origin, v_up, range, islands, island_rule, overlap, flipped_fraction, layout_sha256, texel_density?}` | `origin = bottom_left`, `v_up = true` (Blender's rule; an importer that flips V is part of the normalizer's import record); islands counted by the one rule `vertex_index_and_uv` (`LT/features/uv_islands.py:34-50`); `texel_density.measured_in = canonical_world_m` and **(code)** only present when `scale.state = real` |
| `material_slots[]{slot, material?, name?}` | a slot names a canonical `material` asset when one exists |
| `normals{custom_split, shading}` | custom split normals are kept or dropped by record, never silently |
| `part_map{attribute: part, recipe_sha256, source_face_attribute: lw_source_face}` | part labels live in the face attribute `part`; every face carries `lw_source_face`, its id in the RAW mesh, so labels survive re-import and reorder (canon 01 D.3: map by position or by source id, never by index) |
| `geometry_sha256` | **(code)** recomputed at the door over canonical positions (float32 LE) and face loops; a mismatch means the mesh changed since normalization |

### 4.2 `skeleton` (`SkeletonBody`)

| field | invariant |
|---|---|
| `reference_skeleton{id, sha256, bones?}` | `metahuman_fullbody` (342 bones, canon 01 C.6), `ue5_manny`, `mixamo`, `custom` |
| `convention` | `blender` (local Y along the limb) or `ue_axes` (X along); **(code)** detected per canon 17 B.1 and `mixed` refused (INV-17.1) |
| `rest_pose{name, sha256, equals_reference?}` | a named pose, read by NAME (memory read-the-pose-by-name); `rest` for the bind pose |
| `naming{family, map_sha256, unmapped[]}` | every bone has a `canonical_name` or is listed unmapped (canon 16) |
| `roster{complete, missing[]}` | `complete` requires `missing = []`; a fit tool refuses an incomplete roster (canon 01 C.6) |
| `root{name, at_origin}` | |
| `bones[]{name, canonical_name, parent, head_m, along, along_source, frame, length_m, deform}` | **`along` is head -> head of the continuation child** (`child_head`, `named_continuation`, `leaf_parent_line`, `reference_transport`), never the imported tail (canon 01 C.1, INV-17.5); **(code)** `along` unit length, `frame` a proper rotation (det +1, INV-17.3), parents before children |
| `non_uniform_bone_scale` | `false`: a non-uniform scale is refused at normalize time (canon 18 INV-18.2, canon 22 B.5) |

### 4.3 `rigged_mesh` (`RiggedMeshBody`)

`mesh` (a `MeshBody`), `skeleton` (an `AssetRef` to a canonical skeleton), `skin{max_influences, sums_normalized,
unweighted_vertices, groups_not_bones[], weights_source}`, `bind{pose_name, equals_reference, bind_mismatch_receipt_sha256?}`.
Invariants: `transform.applied` may be `false` only with `skinned_rig_preserved` (memory and wiki scale_to_measure: never apply
scale blindly on a skinned mesh); **(code)** every vertex group naming a bone exists in the skeleton; a fit export requires
`bind.equals_reference = true` (canon 01 C.4, `fit_export`).

### 4.4 `animation_clip` (`AnimationClipBody`)

`skeleton` (AssetRef), `fps{num, den}`, `frames`, `duration_s` (0..3600), `time_rule` (`rational_fps_plus_terminal`,
canon 22 B.6, or `source_keys`), `rotation{encoding: quaternion_xyzw_hamilton, relative_to: rest | canonical_reference,
sign_rule: last_nonzero_positive}`, `translation_units: m`, `scale_channels: none | uniform_only`, `root_motion{mode,
root_bone, travel_front: -Y}`, `source_rest_sha256`, `naming_map_sha256`. Invariants: **(code)** samples carry exactly the
skeleton's bones (canon 22 B.6, INV-22.5); a clip from the multiview tracker is mapped from its +Y-forward frame to -Y front
by the normalizer, recorded in `conventions.axis_map`.

### 4.5 `texture` (`TextureBody`)

| field | invariant |
|---|---|
| `role` | `basecolor, normal, roughness, metallic, ao, orm, height, displacement, emission, opacity, mask, material_id, curvature, hdri, reference` |
| `colour_space` | **bound to the role**: basecolor/emission/reference `sRGB`; every data role `Non-Color`; hdri `Linear Rec.709` (ue_parity TEX-01: "a data map read as sRGB is wrong on both sides by default") |
| `normal{convention: gl | dx, space: tangent | object, tangent_basis: mikktspace, convention_evidence, baked_on_triangulation_sha256?}` | required for role `normal`; `convention_evidence` is `source_naming` (ambientCG `_NormalGL`), `declared`, `baked_by_lampway`, or `measured_sign_test`; never assumed (rank 10) |
| `packing{r: ao, g: roughness, b: metallic}` | required for role `orm` (Unreal's order) |
| `width, height, power_of_two, bit_depth, channels, alpha` | `alpha` is `none`, `straight` or `premultiplied` |
| `uv{mesh, uv_set, layout_sha256}` or `tiling{real_world_m, seamless?}` | a UV-bound map names the mesh and the exact layout it was made for (`fit_export` already refuses textures for another mesh); a tileable names its physical size (ambientCG and Poly Haven give it, `cc0.py:150`, :167) |
| `image_sha256` | of the image bytes |

### 4.6 `material` (`MaterialBody`)

`model: principled_bsdf/metal_roughness` (the one model; an engine adapter maps it), `material_class` (`metal, leather,
cloth, embroidery, skin, other`: from the captain or the recipe, never a render's colour), `channels{base_color, roughness,
metallic, normal, ao, emission, height, opacity}` each a texture AssetRef or a value, `procedural{node_group, script_sha256,
projection: uv | object_box | triplanar, object_space_scale_m?, library_version}`, `metal_zero_classes[]`. Invariants:
**(code)** each bound texture's role matches its channel and its colour space follows 4.5; an `object_box` or `triplanar`
procedural material on an asset whose `scale.state` is not `real` is accepted with a warning that its tiling is not physical
(T48, T49).

### 4.7 `part` (`PartBody`)

`parent` (AssetRef to the canonical mesh), `part_id`, `material_class`, `source_faces{id_space: lw_source_face, count,
ids_sha256}`, `side` (`left, right, center, paired`: the FIGURE's side, canon 01 B), `bind{mode, bones}`, `motion_class`.
Invariants: a metal part binds rigid to exactly one bone (memory metal-never-blended; the schema enforces it); **(code)** the
part's faces are a subset of the parent's by source id.

### 4.8 `set` (`SetBody`)

`members[]{asset, role, side?}`, `body{fit_body_package_sha256}`, `shared_frame: true`, `scale_group` (`per_piece`,
`pair_shared`, `set_shared`: decision D4), `pairs[]`. Invariants: **(code)** every member is canonical in the same frame and,
when `scale_group` is not `per_piece`, carries the same scale evidence.

## 5. Where the document lives

| carrier | form | written by |
|---|---|---|
| a file in the Vault | the canonical file (decision D2: `.blend` holding one stamped datablock tree, recommended; or GLB for a static mesh) plus `<file>.canon.json` | the normalizer, stored as a new asset version with relation `normalized_from` to the raw version (contract `canon_migration.md`) |
| a Blender datablock | custom property `lw_canon` = the JSON document (objects, armatures, actions, images, materials) | the normalizer, and the door's output stamping (DOOR.md §2) |
| an npz or JSON a tool writes | a top-level `canon` key holding the document (npz: a 0-d string array) | the tool through the door |

## 6. Typed Python form (the module's public interface)

```python
# LT/canon_asset.py  (pure: no bpy; the JSON Schema file ships beside it and is the source of truth)
SCHEMA_ID = "lampway.canonical-asset/1"
KINDS = ("mesh", "rigged_mesh", "skeleton", "animation_clip", "texture", "material", "part", "set")
ScaleState = Literal["real", "generator_normalised", "unknown"]

@dataclass(frozen=True)
class Need:                       # what a tool's door asks of one argument
    kind: tuple[str, ...]         # accepted kinds
    scale: tuple[ScaleState, ...] = ("real",)
    convention: str | None = None # skeletons: "blender" | "ue_axes"
    welded: bool | None = None    # adjacency tools: True
    roles: tuple[str, ...] = ()   # textures

def validate(doc: dict) -> list[str]: ...                    # JSON Schema errors, then the (code) invariants that need no datablock
def check(doc: dict, facts: dict) -> list[str]: ...          # (code) invariants against facts measured on the datablock (canon_io)
def satisfies(doc: dict, need: Need) -> list[str]: ...       # empty = the door opens; else each unmet requirement, named
def digest(payload: bytes) -> str: ...                       # sha256 hex
```

## 7. What the schema deliberately does not hold

- Interchange numbers (cm, quaternion rounding to 9 decimals): canon 22's adapter output, not working state.
- Engine import settings: the egress adapters' receipts (`fit_export`, `batch_export`, ue_parity `ue_export`).
- Decisions about fit (roles, bind overrides, openings): the typed decision logs that already exist; a canonical asset names
  its part classes but not who ruled them.
