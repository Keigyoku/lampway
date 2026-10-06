# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""glb_optimize: a lighter GLB for web preview and the proof that it still holds the same asset (specs/wiki/glb_optimize.md).

The in-tree engine is Blender's own glTF add-on: the GLB is imported into a throw-away scene, its images are downsized to ``texture_px`` (longest side,
aspect kept) and it is written again with Draco mesh compression and WebP images at ``webp_quality``. Then the output is re-imported and compared with the
input: ``vertex_deviation_rel`` (the farthest input vertex from the output surface over the input's bounding diagonal), ``texture_ssim`` (the first
image of the input, downsized the same way, against the output's), and the animations (counts, frame ranges and the animated objects' positions at the
first, middle and last frames). Everything imported is removed again and the user's scene is not touched. meshopt is glTF Transform's (MIT, Node): an
external engine the captain may approve; it is refused here."""

import math
import os

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C

KINDS = ("objects", "meshes", "materials", "images", "actions", "cameras", "lights", "armatures", "textures", "node_groups", "collections")


def _import(path):
    before = {k: set(x.name for x in getattr(bpy.data, k)) for k in KINDS}
    sc = bpy.data.scenes.new("lw_glbopt")
    with bpy.context.temp_override(scene=sc, view_layer=sc.view_layers[0]):
        bpy.ops.import_scene.gltf(filepath=path)
    new = {k: [x for x in getattr(bpy.data, k) if x.name not in before[k]] for k in KINDS}
    return sc, new


def _cleanup(sc, new):
    if sc is not None and sc.name in bpy.data.scenes:
        bpy.data.scenes.remove(sc)
    for k in KINDS:
        coll = getattr(bpy.data, k)
        for x in new.get(k, []):
            try:
                coll.remove(x)
            except (ReferenceError, RuntimeError):
                pass


def _points(objs):
    pts = []
    for o in objs:
        if o.type == "MESH":
            pts += [o.matrix_world @ v.co for v in o.data.vertices]
    return pts


def _tree(objs):
    V, T = [], []
    for o in objs:
        if o.type != "MESH":
            continue
        me = o.data
        me.calc_loop_triangles()
        base = len(V)
        V += [o.matrix_world @ v.co for v in me.vertices]
        T += [tuple(base + i for i in t.vertices) for t in me.loop_triangles]
    return BVHTree.FromPolygons(V, T) if T else None


def _pixels(img):
    w, h = img.size
    return np.array(img.pixels[:], dtype=np.float64).reshape(h, w, -1)[..., :3]


def _ssim(a, b) -> float:
    """Global SSIM of the luminance (the standard constants for a 0..1 range)."""
    x, y = a.mean(axis=2), b.mean(axis=2)
    c1, c2 = 0.01 ** 2, 0.03 ** 2
    mx, my = x.mean(), y.mean()
    vx, vy, cov = x.var(), y.var(), ((x - mx) * (y - my)).mean()
    return float(((2 * mx * my + c1) * (2 * cov + c2)) / ((mx * mx + my * my + c1) * (vx + vy + c2)))


def _fit(img, px):
    w, h = img.size
    if max(w, h) <= px:
        return w, h
    s = px / float(max(w, h))
    return max(1, int(round(w * s))), max(1, int(round(h * s)))


def _anim(sc, new):
    acts = sorted(new["actions"], key=lambda a: a.name)
    animated = sorted((o for o in new["objects"] if o.animation_data and o.animation_data.action), key=lambda o: o.name)
    f0 = min((int(a.frame_range[0]) for a in acts), default=sc.frame_start)
    f1 = max((int(a.frame_range[1]) for a in acts), default=sc.frame_end)
    track = {}
    for f in sorted({f0, (f0 + f1) // 2, f1}):
        sc.frame_set(f)
        for o in animated:
            track.setdefault(o.name, []).append(tuple(round(x, 4) for x in o.matrix_world.translation))
    return {"count": len(acts), "ranges": [tuple(int(x) for x in a.frame_range) for a in acts], "track": track}


def glb_optimize(glb, out, mesh_compression="draco", texture_px=1024, webp_quality=80, keep_animation=True):
    if mesh_compression == "meshopt":
        raise C.FeatureError("meshopt is glTF Transform's (MIT, Node), an external engine the captain may approve: not wired here; use draco or none")
    if mesh_compression not in ("none", "draco"):
        raise C.FeatureError("mesh_compression is none | draco (meshopt needs glTF Transform)")
    if not 1 <= int(webp_quality) <= 100:
        raise C.FeatureError("webp_quality is 1..100")
    if not 16 <= int(texture_px) <= 8192:
        raise C.FeatureError("texture_px is 16..8192 (the longest side)")
    if os.path.realpath(glb) == os.path.realpath(out):
        raise C.FeatureError("out equals the input: write a new file (the source GLB is never overwritten)")
    if not os.path.isfile(glb) or not glb.lower().endswith(".glb"):
        raise C.FeatureError(f"{glb} is not a .glb file")
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    sc_in = sc_out = None
    new_in, new_out = {}, {}
    try:
        sc_in, new_in = _import(glb)
        before_pts = _points(new_in["objects"])
        lo = Vector([min(p[i] for p in before_pts) for i in range(3)]) if before_pts else Vector()
        hi = Vector([max(p[i] for p in before_pts) for i in range(3)]) if before_pts else Vector()
        diag = max(1e-9, (hi - lo).length)
        anim_before = _anim(sc_in, new_in)
        ref_px, sizes = None, []
        for img in new_in["images"]:
            if img.size[0] == 0:
                continue
            w, h = _fit(img, int(texture_px))
            if ref_px is None:
                ref = img.copy()
                ref.scale(w, h)
                ref_px = _pixels(ref)
                bpy.data.images.remove(ref)
            if (w, h) != tuple(img.size):
                img.scale(w, h)
                img.pack()
            sizes.append(max(w, h))
        with bpy.context.temp_override(scene=sc_in, view_layer=sc_in.view_layers[0]):
            bpy.ops.export_scene.gltf(filepath=out, export_format="GLB", use_active_scene=True, export_animations=bool(keep_animation),
                                      export_draco_mesh_compression_enable=mesh_compression == "draco", export_image_format="WEBP",
                                      export_image_quality=int(webp_quality))
        _cleanup(sc_in, new_in)
        sc_in, new_in = None, {}
        sc_out, new_out = _import(out)
        tree = _tree(new_out["objects"])
        dev = max(((tree.find_nearest(p)[3] or 0.0) for p in before_pts), default=0.0) / diag if tree else math.inf
        out_img = next((i for i in new_out["images"] if i.size[0]), None)
        ssim = None
        if ref_px is not None and out_img is not None:
            got = _pixels(out_img)
            ssim = round(_ssim(ref_px, got), 4) if got.shape == ref_px.shape else 0.0
        anim_after = _anim(sc_out, new_out)
        frames_equal = (anim_before["count"] == anim_after["count"] and anim_before["ranges"] == anim_after["ranges"] and anim_before["track"] == anim_after["track"]) \
            if anim_before["count"] else None
    finally:
        _cleanup(sc_in, new_in)
        _cleanup(sc_out, new_out)
    return {"out": out, "bytes_before": os.path.getsize(glb), "bytes_after": os.path.getsize(out),
            "checks": {"vertex_deviation_rel": round(float(dev), 6), "texture_ssim": ssim, "texture_px_after": max(sizes) if sizes else None,
                       "animation_frames_equal": frames_equal, "animations": {"before": anim_before["count"], "after": anim_after["count"]}},
            "settings": {"mesh_compression": mesh_compression, "texture_px": int(texture_px), "webp_quality": int(webp_quality), "keep_animation": bool(keep_animation)}}
