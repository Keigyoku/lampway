# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""recon_measure (STATUS O39): a reconstructed mesh measured against its approved plates (pipeline/recon_measure.py: the 24-orientation search, six-view
IoU, cavity, crest fin) plus its albedo's left/right luminance, read here: the active colour attribute, else the image texture feeding the material's
Base Color sampled at the loop UVs. Read-only; the evaluated mesh in world space."""

import os

import numpy as np

from . import common as C
from ..pipeline import recon_measure as RM

LUMA = np.array([0.2126, 0.7152, 0.0722])


def _mesh(ob):
    import bpy
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mw = np.array(ob.matrix_world)
        co = (mw[:3, :3] @ co.reshape(-1, 3).T).T + mw[:3, 3]
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
        lum, src = _albedo(ob, me)
        return co, tris.reshape(-1, 3), lum, src
    finally:
        ev.to_mesh_clear()


def _albedo(ob, me):
    """(per-vertex luminance or None, source): vertex/corner colours first, then the Base Color image at the loop UVs (averaged per vertex)."""
    nv = len(me.vertices)
    ca = me.color_attributes.active_color if hasattr(me, "color_attributes") else None
    if ca is not None:
        col = np.empty(len(ca.data) * 4)
        ca.data.foreach_get("color", col)
        lum = col.reshape(-1, 4)[:, :3] @ LUMA
        if ca.domain == "POINT":
            return lum, f"colour attribute {ca.name}"
        vi = np.empty(len(me.loops), dtype=np.int64)
        me.loops.foreach_get("vertex_index", vi)
        return np.bincount(vi, lum, nv) / np.maximum(np.bincount(vi, None, nv), 1), f"colour attribute {ca.name}"
    img = None
    for slot in ob.material_slots:
        m = slot.material
        if not (m and m.use_nodes):
            continue
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED" and n.inputs["Base Color"].is_linked:
                src = n.inputs["Base Color"].links[0].from_node
                if src.type == "TEX_IMAGE" and src.image is not None:
                    img = src.image
                    break
        if img is not None:
            break
    if img is None or not me.uv_layers.active:
        return None, "no albedo: no colour attribute and no image texture on Base Color"
    w, h = img.size
    px = np.empty(w * h * img.channels, dtype=np.float32)
    img.pixels.foreach_get(px)
    px = px.reshape(h, w, img.channels)[:, :, :3]
    uv = np.empty(len(me.loops) * 2)
    me.uv_layers.active.data.foreach_get("uv", uv)
    uv = uv.reshape(-1, 2)
    xs = np.clip((uv[:, 0] % 1.0 * (w - 1)).astype(int), 0, w - 1)
    ys = np.clip((uv[:, 1] % 1.0 * (h - 1)).astype(int), 0, h - 1)               # Blender pixels are bottom-up, as UV v is
    lum = px[ys, xs] @ LUMA
    vi = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", vi)
    return np.bincount(vi, lum, nv) / np.maximum(np.bincount(vi, None, nv), 1), f"image {img.name}"


def run(object, plates, root, size=256):
    ob = C.need_object(object)
    if not isinstance(plates, dict) or not plates:
        raise C.FeatureError("plates is {view: PNG with alpha}: front, left and top drive the orientation search; right, back and bottom are scored too")
    bad = sorted(set(plates) - set(RM.VIEWS))
    if bad:
        raise C.FeatureError(f"unknown view(s) {bad}: the views are {', '.join(RM.VIEWS)} (the wearer's axes)")
    masks = {}
    for view, p in plates.items():
        path = p if os.path.isabs(p) else os.path.join(root, p)
        if not os.path.isfile(path):
            raise C.FeatureError(f"no plate at {path}")
        masks[view] = RM.plate_mask(path)
    co, tris, lum, src = _mesh(ob)
    out = RM.measure(co, tris, masks, size=int(size))
    if lum is None:
        out.update(lum_left_right_ratio=None, lum_source=src)
    else:
        x = (RM.normalise(co) @ np.array(out["orientation"], float).T)[:, 0]
        out.update(lum_left_right_ratio=RM.lum_ratio(x, lum), lum_source=src)
    out["object"] = ob.name
    out["note"] = ("views on the wearer's axes (front -Y, wearer's left +X, +Z up); orientation is the turn that best matches the plates; "
                   "lum ratio = the wearer's left over right (a baked light shows as one side brighter)")
    return out
