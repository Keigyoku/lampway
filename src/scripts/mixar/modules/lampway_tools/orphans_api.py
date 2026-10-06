# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The orphan tools' api functions (STATUS.md ORPHANS). They register through ``api.tool`` like every other tool, and ``api`` star-imports this module
just before it freezes TOOL_FUNCS, so ``api.call(name, ...)`` reaches them. Kept apart so api.py does not grow past reading."""

from .api import _p, _settings, tool  # noqa: F401  (api is mid-import here: these names are already bound)

__all__ = []


def _export(fn):
    __all__.append(fn.__name__)
    return fn


@_export
@tool
def side_label_check(object, declared_side=None, facing="-Y", armature="", body_midline_x=None, pair="", asym_threshold=0.02):
    """Is a piece labelled left/right on the FIGURE's left/right (not the camera's), and is it not a mirrored copy of its pair? Read-only."""
    from .features import handedness as _H
    return _H.side_label_check(object, declared_side, facing, armature, body_midline_x, pair, asym_threshold)


@_export
@tool
def mirror_pair(object, design_symmetric=None, plane="x", origin="bounds_centre", rename=None, mirror_uv=False, weights="swap", force=False, body_midline_x=None,
                armature="", asym_threshold=0.02, piece="", by="agent", captain_words=""):
    """The opposite piece by a mirror across a stated plane, on a COPY, only after the typed decision design_symmetric; a decision row in <root>/<piece>/decisions.jsonl."""
    from .features import handedness as _H
    return _H.mirror_pair(object, str(_settings().project_root), design_symmetric, plane, origin, rename, mirror_uv, weights, force, body_midline_x, armature,
                          asym_threshold, piece, by, captain_words)


@_export
@tool
def scale_to_measure(object, target=None, reference_object="", apply=True, unit_scale=1.0, children="include", rollback=False):
    """Put an object's dimension at a measured real size (target {axis, length_m} or a reference object's), applied safely; rollback restores lw_prev_scale."""
    from .features import scale_measure as _SM
    return _SM.scale_to_measure(object, target, reference_object, apply, unit_scale, children, rollback)


@_export
@tool
def uv_check(object, action="measure", target_density_px_m=None, texture_size=2048, tolerance=0.15, tile_from=None, tile_to=None, islands=None, dry_run=True,
             mirror_axis="x", match_tolerance=0.003, res=512, discard_texture=False):
    """UV measurements per island (density, overlaps stacked vs accidental, space usage, orientation, UDIM tiles) and two dry-run-by-default edits (udim_move, stack)."""
    from .features import uv_check as _UC
    return _UC.run(object, action, target_density_px_m, texture_size, tolerance, tile_from, tile_to, islands, dry_run, mirror_axis, match_tolerance, res, discard_texture)


@_export
@tool
def render_condition_passes(objects, camera="auto", passes=None, size=1024, out_dir="condition", engine="workbench"):
    """The conditioning images from ONE camera: flat id colour per object (with its palette), depth (nearer brighter), edges and clay; light engines only."""
    from .features import condition_passes as _CP
    s_ = _settings()
    return _CP.run(objects, str(s_.project_root), camera, passes, size, _p(out_dir, s_.project_root), engine)


@_export
@tool
def image_material_id(piece, object="", view="Front", palette=None, source="parts", recipe="", owner="", part_materials=None, design_plate="", live=False, size=768,
                      out_dir="material_id"):
    """A flat material-ID map: source parts renders each part in its material's palette colour from the clay camera (exact, free); source model is a gated DRAFT."""
    from .features import material_id as _MI
    s_ = _settings()
    return _MI.run(piece, str(s_.project_root), object, view, palette, source, _p(recipe, s_.project_root), _p(owner, s_.project_root), part_materials,
                   _p(design_plate, s_.project_root), live, size, _p(out_dir, s_.project_root))


@_export
@tool
def parts_material_slots(object, recipe, owner="", by="part", name=""):
    """On a copy <object>_slots: the piece's one material becomes one slot per part (or per material class), each a copy sharing the images, faces by part."""
    from .features import parts_slots as _PS
    s_ = _settings()
    return _PS.run(object, _p(recipe, s_.project_root), _p(owner, s_.project_root), by, name)


@_export
@tool
def zone_sheet(object, by="material_slot", views=None, size=768, out="zones/sheet.png", recipe=""):
    """One image where every material slot, part, segment or vertex group is a flat colour with a number, and its legend; answer with a zone number."""
    from .features import zones as _Z
    s_ = _settings()
    return _Z.zone_sheet(object, by, views, size, _p(out, s_.project_root), _p(recipe, s_.project_root))


@_export
@tool
def mesh_region_extract(object, region, cap="fill_holes", keep_in_source=True, name="", recipe=""):
    """A chosen region (bbox, a lasso in a view, vertex group, material slot or zone number) as its own object from copies, capped or filled; the source is unchanged."""
    from .features import region_extract as _RX
    return _RX.run(object, region, cap, keep_in_source, name, _p(recipe))


@_export
@tool
def mesh_local_edit(object, region, engine="deform", op="move", delta=None, falloff_m=0.01, instruction="", side="", anchors=None):
    """One bounded edit of a derivative with a lineage, on a copy <object>_edit (deform with falloff; studio:tripo = the exact-box Edit Mesh plan), then its locality."""
    from .features import local_edit as _LE
    return _LE.mesh_local_edit(object, region, str(_settings().project_root), engine, op, delta, falloff_m, instruction, side, anchors)


@_export
@tool
def edit_locality_check(before, after, region=None, margin_m=0.005, tolerance_m=0.0005):
    """What a region edit changed OUTSIDE its region: moved vertices, faces, open edges, UVs, materials, dimensions, weights; read-only."""
    from .features import local_edit as _LE
    return _LE.edit_locality_check(before, after, region, margin_m, tolerance_m)


@_export
@tool
def mesh_join_boolean(op, objects, voxel_m="coarse_first", clearance_mm=None, connector=None, name=""):
    """Fuse (join + voxel remesh), union, difference with clearance, or plug/socket connectors with a measured gap; on copies, originals kept."""
    from .features import join_boolean as _JB
    return _JB.run(op, objects, voxel_m, clearance_mm, connector, name)


@_export
@tool
def multi_piece_material(action, pieces=None, atlas_res=4096, individual_res=None, density_floor_ratio=0.7, proxy="", atlas="", out_dir="mpm", res=None, keep_proxy=False,
                         name=""):
    """One material across pieces: merge copies into a proxy with a shared atlas, texture it once, transfer the atlas back to each piece's original UVs."""
    from .features import multi_piece as _MP
    s_ = _settings()
    return _MP.run(action, str(s_.project_root), pieces, atlas_res, individual_res, density_floor_ratio, proxy, _p(atlas, s_.project_root),
                   _p(out_dir, s_.project_root), res, keep_proxy, name)
