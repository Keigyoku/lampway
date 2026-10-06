"""texture_route_select: the one table that maps a texturing need to its supported routes, in Lampway and in the Studios, with each route's acceptance
condition (specs/wiki/texture_route_select.md, from the wiki's comparisons/material-engines-and-local-repair.md rows). Read-only.

The table is data; whether a route can run is read from the live registries at every call: a Studio route's ``driver_exists`` is its action id's presence
in studios/actions.py, a Lampway route's ``tool_exists`` is its agent Def's presence. A shape fix never gets a texture route: a texture cannot correct
geometry. Module depth is low by design: it earns its place by being the one table that stops route confusion."""

NEEDS = ("restyle", "keep_uv", "local_defect", "shared_material", "shape_fix")

#: need -> [(route, lampway tool, studio, studio action, acceptance, notes)]
TABLE = {
    "restyle": [
        ("Lampway texture_gen: clay views painted by the image model, projected into the atlas", "texture_gen", None, None,
         "Compare surface coverage; independently check geometry/rig", "keeps the mesh; the UV layout must exist"),
        ("Tripo Texture on the Smart UV copy", None, "tripo", "tripo.texture", "Compare surface coverage; independently check geometry/rig", "30 credits + 5 PBR; texturing comes last"),
        ("3D AI Studio Texture Generator", None, "3dai", None, "Compare surface coverage; independently check geometry/rig", "the wiki's whole-mesh restyle route; no driver"),
    ],
    "keep_uv": [
        ("Tripo Texture on the saved Smart UV copy (it fills that copy's islands)", None, "tripo", "tripo.texture", "Verify export layout, seams and map compatibility",
         "keeps the copy's Smart UV layout (PIECE_PIPELINE:56); UV Unfold replaces UVs and is not this route"),
        ("Meshy retexture with Preserve original UV", None, "meshy", "meshy.retexture", "Verify export layout, seams and map compatibility", "keeps the original UV by default"),
    ],
    "local_defect": [
        ("Lampway repair_texture: a patch blended through a mask into the atlas, from one view", "repair_texture", None, None,
         "Inspect only the intended region and hidden surfaces", "writes a new texture, never overwrites"),
        ("Modddif patch", None, "modddif", None, "Inspect only the intended region and hidden surfaces", "no driver"),
        ("3D AI Studio Painter projection", None, "3dai", None, "Inspect only the intended region and hidden surfaces", "no driver"),
        ("Tripo Magic Brush", None, "tripo", None, "Inspect only the intended region and hidden surfaces", "no driver action"),
    ],
    "shared_material": [
        ("Lampway procedural_library: a parametric node-group material on the paint stack", "procedural_library", None, None,
         "Tiling and per-map inspection; correct target shader", "no UVs needed (object space)"),
        ("Lampway seamless_tile", "seamless_tile", None, None, "Tiling and per-map inspection; correct target shader", "a contract (STATUS orphan O9)"),
        ("3D AI Studio Material AI", None, "3dai", None, "Tiling and per-map inspection; correct target shader", "no driver"),
    ],
    "shape_fix": [
        ("Lampway mesh_local_edit: a region edit with an edit-locality check", "mesh_local_edit", None, None,
         "Silhouette/thickness/fit checks, not texture preview", "a contract (STATUS orphan O1)"),
        ("Modddif Geometry Editor", None, "modddif", None, "Silhouette/thickness/fit checks, not texture preview", "no driver"),
        ("A geometry-specific workflow (fit_place, fit_openings, mesh QA)", "fit_place", None, None, "Silhouette/thickness/fit checks, not texture preview", ""),
    ],
}


class RouteError(ValueError):
    pass


def select(need, engine_available=None) -> dict:
    if need not in TABLE:
        raise RouteError(f"need is one of {', '.join(NEEDS)}")
    from .agent import lampway_tools as LT
    from .studios.actions import ACTIONS
    avail = set(engine_available) if engine_available else None
    routes = []
    for route, tool, studio, action, acceptance, notes in TABLE[need]:
        row = {"route": route, "lampway_tool": tool, "tool_exists": (f"lampway_{tool}" in LT.BY_NAME) if tool else None, "studio": studio,
               "studio_action": action, "driver_exists": (action in ACTIONS) if action else (False if studio else None), "acceptance": acceptance, "notes": notes}
        row["available"] = (bool(row["tool_exists"]) if tool else bool(row["driver_exists"])) and (avail is None or studio is None or studio in avail)
        routes.append(row)
    return {"need": need, "routes": routes, "note": "a shape fix is never a texture route; check the acceptance condition, not the preview"}
