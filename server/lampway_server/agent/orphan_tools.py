"""The orphan tools' definitions (STATUS.md ORPHANS): Defs like every other Lampway tool, kept in their own file. ``lampway_tools`` appends ORPHAN_DEFS to
its DEFS before it builds BY_NAME and SPECS, so they reach the agent's registry, the MCP endpoint and the generated tool pages the same way."""

from .lampway_tools import Def, P, _PATHS  # noqa: F401  (lampway_tools is mid-import here: these names are already bound)

ORPHAN_DEFS = [
    Def("lampway_side_label_check", "Is a piece labelled left/right on the FIGURE's left/right, not the camera's, and is it not a mirrored copy of its pair? Read-only. "
        "The lateral axis is world X: the figure's left is +X while it faces -Y (default) and -X while it faces +Y. The side is the sign of the piece's area-weighted "
        "surface centroid against the body midline (body_midline_x, or the mean of the armature's paired _l/_r bone heads); a piece whose lateral extent holds the midline "
        "and whose centroid lies within a quarter of it is center; paired = one mesh holding both sides. declared_side defaults to the name's suffix (_l/_r, Left/Right). "
        "Returns measured_side, centroid_offset_m, mirror_asymmetry (mean surface distance to its own mirror, fraction of the diagonal), pair {is_mirror_of, "
        "chamfer_to_mirrored_pair} when `pair` names the other piece, pass and reasons. asym_threshold (default 0.02) is UNVERIFIED. Thumb side, palm side and finger "
        "count are not measured from a mesh (the vision slot's). Refused: left/right with neither body_midline_x nor an armature, an unapplied rotation or scale "
        "(apply transform first), an unknown side or facing.",
        [P("object", required=True, desc="the mesh"), P("declared_side", desc="left | right | center | paired (default: from the name)"), P("facing", desc="-Y (default) | +Y"),
         P("armature", desc="an armature with paired _l/_r bones: its midline"), P("body_midline_x", "number", "the body's midline x in metres"),
         P("pair", desc="the other piece of the pair"), P("asym_threshold", "number", "fraction of the diagonal, default 0.02 [UNVERIFIED]")], api="side_label_check"),
    Def("lampway_mirror_pair", "Make the opposite-side piece by a mirror across a stated plane, on a COPY (the source is untouched), ONLY after the typed decision "
        "design_symmetric=true: the user says the design is symmetric; this tool never assumes it, and wearer-left/right asymmetry must survive. The copy's mesh is mirrored in "
        "world space, its normals flipped back outward, its transform identity; its name and its sided vertex groups swap sides (rename {from, to}, default _l -> _r, either "
        "way round; weights drop removes the groups); mirror_uv flips U (default off). origin: 'bounds_centre' (default: mirror in place), 'body_midline' (body_midline_x or "
        "the armature's paired bones; plane x) or 'x,y,z'. The piece's own measured asymmetry (mean surface distance to its mirror, fraction of the diagonal) above "
        "asym_threshold (0.02) is refused unless force=true. Every mirror appends a decision row (question design_symmetric, decider captain when by=captain, else model) to "
        "<root>/<piece>/decisions.jsonl. Refused: no design_symmetric, design_symmetric false, an unknown plane, origin or weights mode.",
        [P("object", required=True), P("design_symmetric", "boolean", "the user's typed decision that the design is symmetric (required)"), P("plane", desc="x (default) | y | z"),
         P("origin", desc="bounds_centre (default) | body_midline | 'x,y,z'"), P("rename", "object", "{from, to}, default {from: _l, to: _r}"), P("mirror_uv", "boolean", "flip U, default false"),
         P("weights", desc="swap (default) | drop"), P("force", "boolean", "mirror despite a measured asymmetry (the user confirmed)"), P("body_midline_x", "number"),
         P("armature", desc="for origin body_midline"), P("asym_threshold", "number", "default 0.02 [UNVERIFIED]"), P("piece", desc="the decision folder, default the object name"),
         P("by", desc="agent (default) | captain: who decided"), P("captain_words", desc="the user's words, quoted into the decision row")], api="mirror_pair"),
    Def("lampway_scale_to_measure", "Put an object at its measured real size: ONE uniform factor that makes its dimension on target.axis (x | y | z | max) equal target.length_m "
        "(metres, 0.001..1000) or the same dimension of reference_object, in scene units of unit_scale metres (1.0; 0.01 for a centimetre FBX). apply (default true) then "
        "moves the scale into the mesh; it is REFUSED on a skinned mesh (an Armature modifier or an armature parent), on an armature, on a mesh with shape keys and on a "
        "mesh shared by other objects: scale the armature object only, or pass apply=false. children include (default: they follow) | skip (they keep their world "
        "placement). The transform before the change is kept as the object's lw_prev_scale; rollback=true restores it. Returns dimensions_before/after, factor, applied, "
        "unit_scale. The named object is changed (that is the point).",
        [P("object", required=True), P("target", "object", "{axis: x|y|z|max, length_m}"), P("reference_object", desc="match this object's dimension on target.axis"),
         P("apply", "boolean", "default true"), P("unit_scale", "number", "metres per scene unit, default 1.0"), P("children", desc="include (default) | skip"),
         P("rollback", "boolean", "restore the transform recorded in lw_prev_scale")], api="scale_to_measure"),
    Def("lampway_uv_check", "UV checks per island on the object's ACTIVE UV layer (island ids are uv_score's). measure: faces, UV and 3D area, texel density in px/m at "
        "texture_size, UV bbox and the UDIM tiles each island touches, the tiles used and the islands CROSSING a tile border, density mean and CV. select_by_density: "
        "selects the faces of the islands off target_density_px_m (default the mean) by more than tolerance (0.15). overlaps: rasterised per tile at res (512): the "
        "overlapping fraction and the overlapping island pairs split into stacked (the two share their UV outline: deliberate) and accidental. space_usage: coverage "
        "of tile 1001 and every used tile, and the empty cells of a 16 x 16 grid. orientation: flipped islands (winding against the majority) and mirrored pairs "
        "(3D geometry mirrored across mirror_axis within match_tolerance metres: the stack candidates). Edits, DRY RUNS unless dry_run=false, one undo step: udim_move "
        "(islands to tile_to by whole tiles; tile_from filters; 1001..1099 [UNVERIFIED limit]) and stack (each mirrored twin takes its partner's UVs vertex by vertex; "
        "named islands pairs that are not mirror twins are refused by name). Refused: no UV layer (unwrap first), Edit Mode, over 1M triangles, an edit on a "
        "textured object (texturing comes last: discard_texture=true overrides).",
        [P("object", required=True), P("action", desc="measure (default) | select_by_density | overlaps | space_usage | orientation | udim_move | stack"),
         P("target_density_px_m", "number", "select_by_density: px per metre (default the mean)"), P("texture_size", "integer", "default 2048"),
         P("tolerance", "number", "fraction, default 0.15"), P("tile_from", "integer", "udim_move: only islands in this tile"), P("tile_to", "integer", "udim_move: 1001..1099"),
         P("islands", "array", "island ids (udim_move), or id pairs a, b, c, d (stack)"), P("dry_run", "boolean", "edits: default true"), P("mirror_axis", desc="x (default) | y | z"),
         P("match_tolerance", "number", "metres, 0.0005..0.05, default 0.003"), P("res", "integer", "raster size 64..4096, default 512"),
         P("discard_texture", "boolean", "allow an edit on a textured object")], api="uv_check"),
    Def("lampway_render_condition_passes", "Render a blockout to the conditioning images an image or video model needs, all from ONE camera in a throw-away scene "
        "(your scene, frame and the objects' colours are restored): id = a flat colour per object (Workbench, anti-aliasing off, every pixel snapped to its "
        "object's palette colour; the palette is returned so a prompt can name regions), depth = a ray cast per pixel, 1 - (d - near)/(far - near) with near/far "
        "from the objects' bounds (nearer is brighter, background 0), edge = 1-pixel lines where the id changes or the depth jumps, clay = studio-lit grey. "
        "camera: a scene camera's name or auto (50 mm, 15 degrees above the -Y front, framing the objects). size is the long edge (64..2048; the aspect is your "
        "scene's). Light engines only: workbench (default) or eevee for clay; Cycles is refused. Control-image inputs on the image APIs are [UNVERIFIED]: use "
        "the passes as plain reference images. Nothing is spent." + _PATHS,
        [P("objects", "array", "the mesh objects of the blockout", required=True), P("camera", desc="a camera name | auto (default)"),
         P("passes", "array", "subset of id, depth, edge, clay; default clay, depth, id"), P("size", "integer", "long edge 64..2048, default 1024"),
         P("out_dir", desc="under the project root, default condition"), P("engine", desc="workbench (default) | eevee")], api="render_condition_passes"),
]
