# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What each orphan-lane tool consumes, declared against the canonical asset (specs/canon/normalization SCHEMA.md, DOOR.md §2) BEFORE the door
exists. The door (``api.tool(consumes=...)``, ``canon_asset.Need``) is the canon lane's item N2; until it lands this table is the declaration,
in Need's own fields, so N2 turns each row into ``consumes=`` mechanically. Every tool here assumes canonical input: metres, right-handed, +Z
up, front -Y, wearer's left +X, a bone's direction head -> next joint, generated meshes welded by position.

A row is {argument: need} or NONE(reason). A need is {kind, scale, welded?, convention?, roles?}: ``scale`` lists the accepted scale states
(SCHEMA 3.1); tools with absolute thresholds (metres, millimetres, px/m) accept only ``real``, scale-free ones accept all three."""

ALL = ("real", "generator_normalised", "unknown")
REAL = ("real",)
GEOMETRY = ("mesh", "part", "rigged_mesh")


def need(kind, scale=ALL, welded=None, convention=None, roles=()):
    return {"kind": tuple(kind), "scale": tuple(scale), "welded": welded, "convention": convention, "roles": tuple(roles)}


def NONE(reason):
    return {"none": reason}


IMAGE_IN = ("basecolor", "reference", "height", "material_id")

CONSUMES = {
    # side and mirror: signs and ratios of the bounding diagonal; the armature is read for its paired bone HEADS only
    "side_label_check": {"object": need(GEOMETRY), "armature": need(("skeleton",)), "pair": need(GEOMETRY)},
    "mirror_pair": {"object": need(GEOMETRY), "armature": need(("skeleton",))},
    # the route TO real scale: it accepts every state and re-stamps the piece; its reference must already be real
    "scale_to_measure": {"object": need(GEOMETRY), "reference_object": need(GEOMETRY, REAL)},
    "uv_check": {"object": need(("mesh", "part"), REAL)},                       # texel density in px per canonical metre
    "render_condition_passes": {"objects": need(GEOMETRY)},
    "image_material_id": {"object": need(("mesh", "part")), "design_plate": need(("texture",), roles=("reference",))},
    "parts_material_slots": {"object": need(("mesh", "part"))},
    "zone_sheet": {"object": need(("mesh", "part"))},
    "mesh_region_extract": {"object": need(("mesh", "part"), welded=True)},     # regions follow adjacency
    "mesh_local_edit": {"object": need(("mesh", "part"), REAL, welded=True)},   # falloff in metres
    "edit_locality_check": {"before": need(("mesh", "part"), REAL), "after": need(("mesh", "part"), REAL)},   # margin and tolerance in metres
    "mesh_join_boolean": {"objects": need(("mesh", "part"), REAL, welded=True)},   # voxel size and clearance in mm
    "multi_piece_material": {"pieces": need(("mesh", "part"), REAL)},          # texel density floor
    "seamless_tile": {"src": need(("texture",), roles=IMAGE_IN)},
    "relief_tiles": {"v3_dir": need(("texture",), roles=("reference",)), "tile_dir": need(("texture",), roles=("height",))},
    "image_upscale": {"image": need(("texture",), roles=IMAGE_IN)},
    "reference_pack": {"approved_reference": need(("texture",), roles=("reference",)), "image": need(("texture",), roles=("reference",))},
    "workflow_reference_to_asset": {"reference": need(("texture",), roles=("reference",)), "existing_object": need(("mesh", "part")),
                                    "body_refs": need(("texture",), roles=("reference",)), "example_sheet": need(("texture",), roles=("reference",))},
    "image_matte": {"src": need(("texture",), roles=("reference",))},     # 8-bit sRGB plates; pixel-only, no scale
    "prompt_image": {"references": need(("texture",), roles=("reference",))},   # images only; the template carries the rest
    "scribble_read": NONE("reads the Client's own mark records and frozen frames; no asset"),
}

# tools that existed before this lane and gained a mode here: the need of the mode added (the canon lane marks the tool itself LEGACY)
EXTENDED = {
    "segment_mesh": {"object": need(("mesh", "part"), welded=True)},           # labels by UV island: islands are vertex index + uv
    "texture_gen": {"object": need(("mesh", "part")), "reference_image": need(("texture",), roles=("reference",))},
    "layered_material": {"object": need(("mesh", "part"))},
    "auto_rig": {"object": need(("mesh", "part"))},                             # body plans: bands are fractions of the height
    "image_to_3d": {"images": need(("texture",), roles=("reference",))},
    "anim_multiview_fit": {"armature": need(("skeleton",)), "mesh": need(("rigged_mesh",), REAL)},   # swing about head -> next joint, any convention
}
