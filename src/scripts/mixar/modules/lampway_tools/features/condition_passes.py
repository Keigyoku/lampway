# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""render_condition_passes (specs/wiki/render_condition_passes.md): the conditioning images an image or video model needs, from ONE camera, in a throw-away
scene (the user's scene, frame and objects' colours are restored):

id     flat Workbench colour per object, anti-aliasing off, every opaque pixel snapped to its object's palette colour (sRGB 8-bit); the palette is returned so
       a prompt can name regions ("the red zone is the helmet")
depth  a ray cast per pixel through the camera against the objects (BVH), 1 - (d - near) / (far - near) with near/far fixed from the objects' bounds:
       nearer is brighter, the background 0
edge   1-pixel lines where the id changes or the depth jumps (> 0.04)
clay   Workbench studio light, one grey (EEVEE when engine=eevee); Cycles is refused
``camera`` names a scene camera or 'auto' (a 50 mm camera 15 degrees above the -Y front, framing the objects' bounding sphere)."""

import colorsys
import math
import os

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import common as C

PASSES = ("id", "depth", "edge", "clay")
ENGINES = {"workbench": "BLENDER_WORKBENCH", "eevee": "BLENDER_EEVEE"}


def palette(n):
    """n high-contrast sRGB colours: golden-ratio hues, alternating value, never black or white."""
    out = []
    for i in range(n):
        h = (i * 0.61803398875) % 1.0
        r, g, b = colorsys.hsv_to_rgb(h, 0.85, 0.95 if i % 2 == 0 else 0.7)
        out.append((int(round(r * 255)), int(round(g * 255)), int(round(b * 255))))
    return out


def _lin(c8):
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _bounds(objs):
    pts = np.array([list(o.matrix_world @ Vector(c)) for o in objs for c in o.bound_box])
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return pts, Vector(((lo + hi) / 2).tolist()), float(np.linalg.norm(hi - lo) / 2)


def _auto_camera(sc, objs):
    _pts, c, r = _bounds(objs)
    cd = bpy.data.cameras.new("lw_cond_cam")
    cd.lens = 50.0
    cam = bpy.data.objects.new("lw_cond_cam", cd)
    sc.collection.objects.link(cam)
    fov = 2 * math.atan(cd.sensor_width / (2 * cd.lens))
    dist = r / math.sin(fov / 2) * 1.15
    loc = c + Vector((0.0, -dist * math.cos(math.radians(15)), dist * math.sin(math.radians(15))))
    cam.matrix_world = Matrix.LocRotScale(loc, (c - loc).to_track_quat("-Z", "Y"), None)     # set the matrix itself: a new object's matrix waits for a depsgraph
    return cam


def _rays(sc, cam, w, h):
    """(origin per pixel, direction per pixel) rows top to bottom."""
    frame = [Vector(v) for v in cam.data.view_frame(scene=sc)]           # tr, br, bl, tl in camera space
    tr, br, bl, tl = frame
    mw = cam.matrix_world
    ortho = cam.data.type == "ORTHO"
    rot = mw.to_3x3()
    orgs, dirs = [], []
    for j in range(h):
        v = (j + 0.5) / h
        left, right = tl + (bl - tl) * v, tr + (br - tr) * v
        for i in range(w):
            p = left + (right - left) * ((i + 0.5) / w)
            if ortho:
                orgs.append(mw @ Vector((p.x, p.y, 0.0)))
                dirs.append((rot @ Vector((0.0, 0.0, -1.0))).normalized())
            else:
                orgs.append(mw.translation.copy())
                dirs.append((rot @ p).normalized())
    return orgs, dirs


def _tree(objs):
    dg = bpy.context.evaluated_depsgraph_get()
    verts, polys = [], []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        try:
            base = len(verts)
            verts += [o.matrix_world @ v.co for v in me.vertices]
            polys += [[base + i for i in p.vertices] for p in me.polygons]
        finally:
            ev.to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


def _depth(sc, cam, objs, w, h):
    pts, _c, _r = _bounds(objs)
    eye = np.array(list(cam.matrix_world.translation))
    d = np.linalg.norm(pts - eye, axis=1)
    near, far = max(0.0, float(d.min()) * 0.9), float(d.max()) * 1.05
    tree = _tree(objs)
    orgs, dirs = _rays(sc, cam, w, h)
    img = np.zeros(w * h, dtype=np.float64)
    for k in range(w * h):
        loc, _n, _i, dist = tree.ray_cast(orgs[k], dirs[k])
        if loc is not None:
            img[k] = min(1.0, max(0.0, 1.0 - (dist - near) / max(1e-6, far - near)))
    return img.reshape(h, w), near, far


def _save_rgba(path, arr):
    from PIL import Image
    Image.fromarray(arr.astype(np.uint8), "RGBA" if arr.shape[-1] == 4 else "RGB").save(path)


def _workbench(sc, path, shading):
    sc.render.engine = "BLENDER_WORKBENCH"
    sh = sc.display.shading
    for k, v in shading.items():
        setattr(sh, k, v)
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)


def run(objects, root, camera="auto", passes=None, size=1024, out_dir="condition", engine="workbench"):
    from PIL import Image
    if str(engine).lower() == "cycles":
        raise C.FeatureError("Cycles is refused: it locks the machine while the owner works live (use workbench or eevee)")
    if engine not in ENGINES:
        raise C.FeatureError(f"engine is one of {tuple(ENGINES)}")
    passes = list(passes or ["clay", "depth", "id"])
    bad = [p for p in passes if p not in PASSES]
    if bad:
        raise C.FeatureError(f"unknown pass {bad[0]!r}: the passes are " + ", ".join(PASSES))
    names = list(objects or [])
    if not names:
        raise C.FeatureError("objects names at least one visible mesh object (the blockout)")
    objs = [C.need_object(n) for n in names]
    size = int(size)
    if not 64 <= size <= 2048:
        raise C.FeatureError("size (the long edge) is 64..2048")
    os.makedirs(out_dir, exist_ok=True)
    home = bpy.context.scene
    ax, ay = home.render.resolution_x, home.render.resolution_y
    w, h = (size, max(2, round(size * ay / ax))) if ax >= ay else (max(2, round(size * ax / ay)), size)
    sc = bpy.data.scenes.new("lw_condition")
    saved_colors = {o.name: tuple(o.color) for o in objs}
    made_cam = None
    files = {}
    pal = palette(len(objs))
    try:
        for o in objs:
            sc.collection.objects.link(o)
        if camera in (None, "", "auto"):
            cam = made_cam = _auto_camera(sc, objs)
        else:
            cam = C.need_object(camera, "CAMERA")
            sc.collection.objects.link(cam)
        sc.camera = cam
        r = sc.render
        r.resolution_x, r.resolution_y, r.resolution_percentage = w, h, 100
        r.film_transparent = True
        r.image_settings.file_format, r.image_settings.color_mode = "PNG", "RGBA"
        sc.view_settings.view_transform = "Standard"
        sc.view_settings.look = "None"
        sc.display.render_aa = "OFF"
        flat = {"light": "FLAT", "show_object_outline": False, "show_cavity": False, "show_shadows": False, "show_specular_highlight": False, "show_xray": False}
        id_img = None
        if "id" in passes or "edge" in passes:
            for o, c8 in zip(objs, pal):
                o.color = (_lin(c8[0]), _lin(c8[1]), _lin(c8[2]), 1.0)
            raw = os.path.join(out_dir, "id_raw.png")
            _workbench(sc, raw, {**flat, "color_type": "OBJECT"})
            a = np.asarray(Image.open(raw).convert("RGBA")).astype(int)
            os.remove(raw)
            P = np.array(pal)
            d = np.abs(a[..., None, :3] - P[None, None, :, :]).sum(axis=3)
            idx = d.argmin(axis=2)
            opaque = a[..., 3] > 127
            snapped = np.zeros(a.shape, np.uint8)
            snapped[opaque, :3] = P[idx[opaque]]
            snapped[opaque, 3] = 255
            id_img = np.where(opaque, idx, -1)
            if "id" in passes:
                files["id"] = os.path.join(out_dir, "id.png")
                _save_rgba(files["id"], snapped)
        dep = None
        out = {}
        if "depth" in passes or "edge" in passes:
            dep, near, far = _depth(sc, cam, objs, w, h)
            out["depth"] = {"near_m": round(near, 4), "far_m": round(far, 4), "encoding": "1 - (d - near) / (far - near); background 0; nearer is brighter"}
            if "depth" in passes:
                files["depth"] = os.path.join(out_dir, "depth.png")
                g = (dep * 255).round().astype(np.uint8)
                Image.fromarray(g, "L").save(files["depth"])
        if "edge" in passes:
            e = np.zeros((h, w), bool)
            e[:, 1:] |= id_img[:, 1:] != id_img[:, :-1]
            e[1:, :] |= id_img[1:, :] != id_img[:-1, :]
            e[:, 1:] |= np.abs(dep[:, 1:] - dep[:, :-1]) > 0.04
            e[1:, :] |= np.abs(dep[1:, :] - dep[:-1, :]) > 0.04
            files["edge"] = os.path.join(out_dir, "edge.png")
            Image.fromarray((e * 255).astype(np.uint8), "L").save(files["edge"])
        if "clay" in passes:
            files["clay"] = os.path.join(out_dir, "clay.png")
            if engine == "eevee":
                sc.render.engine = ENGINES["eevee"]
                for o in objs:
                    o.color = (0.6, 0.6, 0.6, 1.0)
                sc.render.filepath = files["clay"]
                bpy.ops.render.render(write_still=True, scene=sc.name)
            else:
                sc.display.render_aa = "8"
                _workbench(sc, files["clay"], {"light": "STUDIO", "color_type": "SINGLE", "single_color": (0.78, 0.78, 0.78), "show_object_outline": False})
    finally:
        for o in objs:
            o.color = saved_colors[o.name]
            if o.name in sc.collection.objects:
                sc.collection.objects.unlink(o)
        if made_cam is not None:
            cd = made_cam.data
            bpy.data.objects.remove(made_cam)
            bpy.data.cameras.remove(cd)
        elif camera not in (None, "", "auto") and bpy.data.objects.get(camera) and camera in sc.collection.objects:
            sc.collection.objects.unlink(bpy.data.objects[camera])
        bpy.data.scenes.remove(sc)
    return {"files": files, "camera": camera if camera not in (None, "", "auto") else "auto", "size": [w, h], "engine": engine,
            "palette": [{"object": o.name, "rgb": list(c)} for o, c in zip(objs, pal)] if ("id" in passes or "edge" in passes) else [], **out}
