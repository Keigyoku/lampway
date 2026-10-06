# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lod_chain: LOD1..n of a mesh by collapse decimation on copies, with a protected vertex group and the UV seams kept, each LOD measured (specs/wiki/lod_chain.md).

Protection is hard: the protected vertices (the group's members, plus every vertex where the UV layout is split when ``preserve_uv_seams``) are the inverted
vertex group of the Decimate modifier, which never collapses a vertex of zero weight. Measurements per LOD: the face count; ``max_deviation_rel``, the
symmetric vertex-to-surface distance between the LOD and the source over the source's bounding diagonal (both directions: detail the LOD lost and
geometry it moved); ``silhouette_iou``, the smaller of the front and left orthographic silhouette IoUs from the source's own cameras; and, for a skinned
mesh, the weight audit of the copy. Whether decimation keeps skin weights acceptably is not assumed: it is audited per LOD. Textures listed are written
downsized per LOD (``<stem>_LOD<n>.png``); the materials are not rewired."""

import os
import tempfile
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from .. import canon_io
from . import silhouette as _sil
from . import weights as _w

KEEP = "_lw_lod_keep"
TAG = "lw_lod_of"


def _check(ratios, texture_scale):
    r = [float(x) for x in ratios]
    if not r or any(not 0.05 <= x <= 0.9 for x in r):
        raise C.FeatureError("each ratio is 0.05..0.9 (the fraction of faces a LOD keeps)")
    if any(b >= a for a, b in zip(r, r[1:])):
        raise C.FeatureError(f"ratios must be strictly decreasing (LOD1 keeps the most): got {r}")
    ts = [1.0 / 2 ** i for i in range(len(r))] if texture_scale is None else [float(x) for x in texture_scale]
    if len(ts) != len(r) or any(not 0 < x <= 1 for x in ts):
        raise C.FeatureError(f"texture_scale has one entry in (0, 1] per ratio ({len(r)}); got {ts}")
    return r, ts


def _armature(ob):
    return next((m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object is not None), None)


def _seam_vertices(me) -> set:
    if not me.uv_layers:
        return set()
    uv = me.uv_layers.active.data
    seen = {}
    for li, loop in enumerate(me.loops):
        seen.setdefault(loop.vertex_index, set()).add((round(uv[li].uv[0], 6), round(uv[li].uv[1], 6)))
    return {v for v, s in seen.items() if len(s) > 1}


def _members(ob, group) -> set:
    g = ob.vertex_groups.get(group)
    if g is None:
        raise C.FeatureError(f"no vertex group {group!r} on {ob.name}; the groups are: {sorted(x.name for x in ob.vertex_groups)}")
    return {v.index for v in ob.data.vertices for e in v.groups if e.group == g.index and e.weight > 0}


def _world(ob):
    return [ob.matrix_world @ v.co for v in ob.data.vertices]


def _tree(ob):
    ob.data.calc_loop_triangles()
    return BVHTree.FromPolygons(_world(ob), [tuple(t.vertices) for t in ob.data.loop_triangles])


def _deviation(lod, src) -> float:
    diag = max(1e-9, float(Vector(src.dimensions).length))
    t_src, t_lod = _tree(src), _tree(lod)
    d1 = max((t_lod.find_nearest(p)[3] or 0.0) for p in _world(src))
    d2 = max((t_src.find_nearest(p)[3] or 0.0) for p in _world(lod))
    return round(max(d1, d2) / diag, 6)


def _iou(lod, src, tmp) -> float:
    vals = []
    for view in ("Front", "Left"):
        a = _sil._render_mask(src, src, view, 128, Path(tmp) / f"a_{view}.png")
        b = _sil._render_mask(lod, src, view, 128, Path(tmp) / f"b_{view}.png")
        vals.append(float((a & b).sum()) / max(1.0, float((a | b).sum())))
    return round(min(vals), 4)


def _decimate(src, name, ratio, keep: set):
    for o in [o for o in bpy.data.objects if o.name == name]:
        if o.get(TAG) != src.name:
            raise C.FeatureError(f"an object named {name!r} exists and is not a LOD of {src.name}: pick another naming")
        bpy.data.objects.remove(o)
    lod = C.duplicate(src, "")
    lod.name = name
    lod.data.name = name
    lod[TAG] = src.name
    others = [(m, m.show_viewport) for m in lod.modifiers]
    for m, _ in others:
        m.show_viewport = False
    if keep:
        g = lod.vertex_groups.new(name=KEEP)
        g.add(sorted(keep), 1.0, "REPLACE")
    mod = lod.modifiers.new("lw_lod_decimate", "DECIMATE")
    mod.decimate_type, mod.ratio = "COLLAPSE", float(ratio)
    if keep:
        mod.vertex_group, mod.invert_vertex_group = KEEP, True
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(lod.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    lod.modifiers.remove(mod)
    old = lod.data
    lod.data = me
    me.name = name
    bpy.data.meshes.remove(old)
    for m, vis in others:
        m.show_viewport = vis
    if keep and lod.vertex_groups.get(KEEP):
        lod.vertex_groups.remove(lod.vertex_groups[KEEP])
    return lod


def _texture(path, scale, out_dir, n, root):
    img = canon_io.load_image(path, check_existing=False)   # the one image load: a texture copied downsized, colour space untouched (no role)
    try:
        w, h = img.size
        img.scale(max(1, int(round(w * scale))), max(1, int(round(h * scale))))
        dst = os.path.join(out_dir, f"{Path(path).stem}_LOD{n}.png")
        img.filepath_raw, img.file_format = dst, "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)
    return os.path.relpath(dst, root)


def lod_chain(root, object, ratios=None, protect=None, texture_scale=None, textures=None, naming="{name}_LOD{n}", preserve_uv_seams=True, out_dir="", resolve=None):
    src = C.need_object(object)
    ratios, ts = _check(ratios if ratios is not None else [0.5, 0.25, 0.1], texture_scale)
    arm = _armature(src)
    if arm is not None and not protect:
        raise C.FeatureError(f"{src.name} is skinned to {arm.name}: protect the joint loops or run weight_audit after (give `protect`, a vertex group of the joint "
                             "regions; each LOD's weights are audited either way)")
    if "{n}" not in naming:
        raise C.FeatureError("naming needs {n} (and may use {name}): e.g. '{name}_LOD{n}'")
    keep = _members(src, protect) if protect else set()
    if preserve_uv_seams:
        keep |= _seam_vertices(src.data)
    tex = [resolve(t) for t in (textures or [])]
    for t in tex:
        if not os.path.isfile(t):
            raise C.FeatureError(f"texture {t} not found")
    if tex:
        os.makedirs(out_dir, exist_ok=True)
    bpy.context.view_layer.update()
    lods = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, (r, s) in enumerate(zip(ratios, ts), start=1):
            lod = _decimate(src, naming.format(name=src.name, n=i), r, keep)
            bpy.context.view_layer.update()
            audit = None
            if arm is not None:
                try:
                    audit = bool(_w.audit(lod.name, arm.name)["pass"])
                except C.FeatureError:
                    audit = False
            lods.append({"object": lod.name, "ratio": r, "faces": len(lod.data.polygons), "max_deviation_rel": _deviation(lod, src),
                         "silhouette_iou": _iou(lod, src, tmp), "weight_audit_pass": audit, "texture_scale": s,
                         "textures": [_texture(t, s, out_dir, i, root) for t in tex]})
    return {"source": src.name, "source_faces": len(src.data.polygons), "protected_vertices": len(keep), "lods": lods,
            "note": "the engine import of a LOD is the user's check; whether decimation keeps skin weights is audited per LOD, not assumed"}
