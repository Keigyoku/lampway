# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What every feature shares: the studio slot's answer, a duplicate-and-name helper, and the mesh report."""

import bmesh
import bpy
import numpy as np

# (feature, studio) -> what the slot would do and what it costs. Prices are NOT guessed: the driver reads the button before
# any click and refuses on a mismatch; this only says which action and that it spends credits.
STUDIO_ACTIONS = {
    ("retopo", "tripo"): ("Tripo Studio Retopology (Quad) on the saved copy of the model", "credits (the Generate button's price, read back before any click; >= 500 faces)"),
    ("uv", "tripo"): ("Tripo Studio Smart UV on the saved copy of the model", "20 credits (+ 3 free retries, per the owner's measurements)"),
    ("segment", "tripo"): ("Tripo Studio Segment on the saved copy of the model", "credits (read back before any click)"),
    ("rig", "tripo"): ("Tripo Studio Auto Rig on the saved copy of the model", "credits (read back before any click)"),
    ("image_to_3d", "tripo"): ("Tripo Studio Smart Mesh from the four cardinal views, 4 variants at maximum polycount", "100 credits"),
    ("texture", "tripo"): ("Tripo Studio Texture (8K, Remove Lighting) then PBR on the Smart UV clone", "30 credits (texture) + 5 credits (PBR)"),
    ("image_to_3d", "meshy"): ("Meshy Multi-Image to 3D (REST) from the cardinal views", "the docs' list price, read back by the driver's plan before the user's confirm"),
    ("image_to_3d", "hi3d"): ("Hi3D image to 3D (REST) from the cardinal views", "the docs' list price, read back by the driver's plan before the user's confirm"),
    ("local_edit", "tripo"): ("Tripo Studio Edit Mesh exact-box retry on the ORIGINAL (tripo.regen.region)", "0 credits (free; the user's confirm is the approval flag)"),
}


# (feature, studio) -> the server's Studio action id (studios/actions.py); absent = no driver exists yet
STUDIO_ACTION_IDS = {("uv", "tripo"): "tripo.uv.unwrap", ("image_to_3d", "tripo"): "tripo.mesh", ("texture", "tripo"): "tripo.texture",
                     ("local_edit", "tripo"): "tripo.regen.region", ("image_to_3d", "meshy"): "meshy.multi_image_to_3d", ("image_to_3d", "hi3d"): "hi3d.image_to_3d"}


class FeatureError(ValueError):
    pass


def studio_slot(feature: str, engine: str) -> dict:
    """The answer for ``engine="studio:<name>"``: no click, the action and the price for the owner's approval."""
    studio = engine.split(":", 1)[1] if ":" in engine else ""
    if engine != "algorithmic" and not engine.startswith("studio:"):
        raise FeatureError(f"unknown engine {engine!r}; use 'algorithmic' or 'studio:tripo' (also studio:meshy, studio:hi3d)")
    action, price = STUDIO_ACTIONS.get((feature, studio), (None, None))
    if action is None:
        known = sorted({s for (f, s) in STUDIO_ACTIONS if f == feature})
        raise FeatureError(f"{feature} has no studio:{studio} driver yet; its drivers: {known or 'none'}. "
                           "(The meshy and hi3d driver folders on the owner's shelf are empty; only Tripo's exist.)")
    studio_action = STUDIO_ACTION_IDS.get((feature, studio))
    how = ("Ask the owner to approve this exact action and price: call studio_plan with action "
           f"{studio_action!r}; the driver reads the price back (nothing is clicked) and the USER confirms it in the Client's Studios panel. "
           "The result lands in the scene from there." if studio_action else
           f"There is no Tripo Studio driver for {feature} on the owner's shelf yet (it has mesh, Smart UV, texture, image), so nothing can run; "
           "use engine='algorithmic'.")
    return {"ok": False, "needs_approval": True, "studio": studio, "studio_action": studio_action, "action": action, "price": price, "how": how,
            "error": f"{action} spends credits: nothing was clicked; it needs the owner's approval of the price first"}


def need_object(name: str, kind: str = "MESH"):
    ob = bpy.data.objects.get(name)
    if ob is None or (kind and ob.type != kind):
        meshes = sorted(o.name for o in bpy.data.objects if o.type == (kind or "MESH"))
        raise FeatureError(f"no {kind.lower() or 'object'} named {name!r}; the {kind.lower() or 'object'}s are: {meshes}")
    return ob


def duplicate(ob, suffix: str):
    """A linked-to-the-same-collections copy with its own mesh data, named ``<name><suffix>``; the original is untouched."""
    new = ob.copy()
    new.data = ob.data.copy()
    new.name = ob.name + suffix
    new.data.name = new.name
    for coll in (ob.users_collection or [bpy.context.scene.collection]):
        coll.objects.link(new)
    return new


def activate(ob) -> None:
    for o in bpy.context.view_layer.objects:
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob


def mesh_report(ob, ref=None) -> dict:
    """Faces, tris/quads, non-manifold and open-boundary edges, shells, and the surface deviation from ``ref`` (the distance
    from every vertex of ``ob`` to ``ref``'s surface: mean, max, and relative to ref's bounding diagonal)."""
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    faces = len(bm.faces)
    quads = sum(1 for f in bm.faces if len(f.verts) == 4)
    tris = sum(1 for f in bm.faces if len(f.verts) == 3)
    non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    loose = sum(1 for v in bm.verts if not v.link_edges)
    seen, shells = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        shells += 1
        stack = [v]
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            stack.extend(e.other_vert(cur) for e in cur.link_edges)
    rep = {"faces": faces, "tris": tris, "quads": quads, "ngons": faces - tris - quads, "vertices": len(bm.verts),
           "non_manifold_edges": non_manifold, "open_boundary_edges": boundary, "loose_vertices": loose, "shells": shells}
    bm.free()
    if ref is not None:
        from mathutils.bvhtree import BVHTree
        dg = bpy.context.evaluated_depsgraph_get()
        tree = BVHTree.FromObject(ref, dg)
        to_ref = ref.matrix_world.inverted() @ ob.matrix_world
        d = []
        for v in me.vertices:
            hit = tree.find_nearest(to_ref @ v.co)
            d.append(hit[3] if hit[0] is not None else 0.0)
        d = np.asarray(d, dtype=np.float64)
        diag = max(1e-9, float(np.linalg.norm(np.asarray(ref.dimensions))))
        rep.update(mean_deviation=round(float(d.mean()), 6), max_deviation=round(float(d.max()), 6),
                   relative_max_deviation=round(float(d.max()) / diag, 6))
    return rep
