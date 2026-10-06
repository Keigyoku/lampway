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
