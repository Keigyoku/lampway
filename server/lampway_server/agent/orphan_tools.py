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
]
