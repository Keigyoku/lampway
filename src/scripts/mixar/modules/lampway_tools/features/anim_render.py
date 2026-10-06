# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""anim_reference_render: the character at rest from a KNOWN orthographic camera on a plain grey background, front and side, with the camera recorded.

Workbench in a throw-away scene (the same pattern as video.py; Cycles is never used: the owner works live). Anti-aliasing is off and the colour transform is Standard, so the grey is exact,
the silhouette mask is the pixels that differ from it, and two renders are byte-identical. The recorded camera (pipeline/anim_ref.py) is what later steps project through."""

import json
import os

import bpy

from .. import canon_io
import numpy as np
from mathutils import Vector

from ..pipeline import anim_ref as AR
from . import common as C


def _hex(bg):
    s = str(bg).lstrip("#")
    if len(s) != 6:
        raise C.FeatureError(f"background is #RRGGBB, not {bg!r}")
    return tuple(int(s[i:i + 2], 16) for i in (0, 2, 4))


def _linear(c8):
    c = c8 / 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _character(name):
    ob = bpy.data.objects.get(name)
    meshes = []
    if ob is not None:
        meshes = [o for o in ([ob] + list(ob.children_recursive)) if o.type == "MESH"]
    else:
        col = bpy.data.collections.get(name)
        if col is not None:
            meshes = [o for o in col.all_objects if o.type == "MESH"]
    if not meshes:
        raise C.FeatureError(f"no skinned model found: no object or collection named {name!r} holds a mesh")
    return meshes


def _rest_check(meshes):
    for m in meshes:
        for mod in m.modifiers:
            if mod.type == "ARMATURE" and mod.object is not None:
                for pb in mod.object.pose.bones:
                    if any(abs(x) > 1e-6 for x in pb.location) or any(abs(a - b) > 1e-6 for a, b in zip(pb.rotation_quaternion, (1, 0, 0, 0))) or any(abs(s - 1) > 1e-6 for s in pb.scale):
                        raise C.FeatureError("the character is not at rest: run lampway_pose_test reset or choose the rest action")


def _world_geometry(meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    verts, tris, base = [], [], 0
    for m in meshes:
        ev = m.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        mw = ev.matrix_world
        verts += [tuple(mw @ v.co) for v in me.vertices]
        tris += [tuple(base + i for i in t.vertices) for t in me.loop_triangles]
        base += len(me.vertices)
        ev.to_mesh_clear()
    return np.asarray(verts, float), np.asarray(tris, int)


def _render(sc, cam_obj, cam_rec, out, bg8):
    cam = cam_obj.data
    cam.type, cam.ortho_scale, cam.clip_start, cam.clip_end = "ORTHO", cam_rec["ortho_scale"], 0.1, 100.0
    cam_obj.location = Vector(cam_rec["location"])
    cam_obj.rotation_euler = (1.5707963267948966, 0.0, 0.0) if cam_rec["view"] == "front" else (1.5707963267948966, 0.0, 1.5707963267948966)
    sc.camera = cam_obj
    r = sc.render
    r.engine = "BLENDER_WORKBENCH"
    r.resolution_x, r.resolution_y, r.resolution_percentage = cam_rec["size"][0], cam_rec["size"][1], 100
    r.film_transparent = False
    r.image_settings.file_format, r.image_settings.color_mode, r.image_settings.color_depth = "PNG", "RGB", "8"
    r.dither_intensity = 0.0
    sc.display.render_aa = "OFF"
    sc.display.shading.light, sc.display.shading.color_type, sc.display.shading.single_color = "FLAT", "SINGLE", (0.1, 0.1, 0.1)
    sc.display.shading.show_cavity = sc.display.shading.show_object_outline = sc.display.shading.show_shadows = False
    sc.view_settings.view_transform, sc.view_settings.look = "Standard", "None"
    sc.display_settings.display_device = "sRGB"
    world = bpy.data.worlds.new("lw_aref_world")
    world.color = tuple(_linear(c) for c in bg8)
    sc.world = world
    r.filepath = out
    bpy.ops.render.render(write_still=True, scene=sc.name)
    img = canon_io.load_image(out)
    try:
        px = np.array(img.pixels[:], dtype=np.float32).reshape(cam_rec["size"][1], cam_rec["size"][0], 4)
    finally:
        bpy.data.images.remove(img)
    return bpy.data.worlds, world, px


def _write_mask(path, mask):
    h, w = mask.shape
    img = bpy.data.images.new("lw_aref_mask", w, h, alpha=False, float_buffer=False)
    try:
        img.colorspace_settings.name = "Non-Color"
        rgba = np.ones((h, w, 4), np.float32)
        rgba[..., :3] = mask[..., None].astype(np.float32)
        img.pixels.foreach_set(rgba[::-1].ravel())                       # Blender stores image rows bottom-up
        img.filepath_raw = path
        img.file_format = "PNG"
        img.save()
    finally:
        bpy.data.images.remove(img)


def reference_render(character, views=None, size="720x1280", background="#808080", camera=None, out_dir="anim/reference", root=""):
    views = list(views or ["front", "side"])
    for v in views:
        if v not in AR.VIEWS:
            raise C.FeatureError("views are front and side")
    camera = dict(camera or {})
    if str(camera.get("type", "ORTHO")).upper() != "ORTHO":
        raise C.FeatureError("the fit needs a known orthographic camera: perspective is refused")
    try:
        w, h = AR.parse_size(size)
    except AR.RefError as exc:
        raise C.FeatureError(str(exc))
    bg8 = _hex(background)
    meshes = _character(character)
    _rest_check(meshes)
    verts, tris = _world_geometry(meshes)
    lo, hi = verts.min(axis=0), verts.max(axis=0)
    height = float(hi[2] - lo[2])
    center = camera.get("center") or [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2]
    out = os.path.abspath(os.path.join(root, out_dir)) if root and not os.path.isabs(out_dir) else out_dir
    os.makedirs(out, exist_ok=True)
    recs = {v: AR.camera_record(v, center, camera.get("height_m") or height, (w, h), camera.get("ortho_scale")) for v in views}
    for v, rec in recs.items():
        fc = AR.frame_check(lo, hi, rec)
        if not fc["inside"]:
            raise C.FeatureError(f"the whole body and feet must be in frame: the {v} view puts the figure at rows {fc['top_px']:.0f} to {fc['bottom_px']:.0f} of {h} "
                                 f"(a figure taller than the frame minus its margin, or off-centre, is refused)")
    home = bpy.context.scene
    sc = bpy.data.scenes.new("lw_aref")
    cam_data = bpy.data.cameras.new("lw_aref_cam")
    cam_obj = bpy.data.objects.new("lw_aref_cam", cam_data)
    images, masks, worlds = {}, {}, []
    try:
        sc.collection.children.link(home.collection)
        sc.collection.objects.link(cam_obj)
        for v in views:
            png = os.path.join(out, f"ref_{v}.png")
            _, world, px = _render(sc, cam_obj, recs[v], png, bg8)
            worlds.append(world)
            rgb8 = np.rint(px[..., :3][::-1] * 255.0).astype(int)                       # image rows are bottom-up in Blender
            bgarr = np.asarray(bg8)
            mask = (np.abs(rgb8 - bgarr).max(axis=-1) > 2)
            mpath = os.path.join(out, f"ref_{v}_mask.png")
            _write_mask(mpath, mask)
            images[v], masks[v] = png, mpath
            rows = np.flatnonzero(mask.any(axis=1))
            recs[v]["figure_px"] = {"height": int(rows.max() - rows.min() + 1) if len(rows) else 0, "top": int(rows.min()) if len(rows) else None,
                                    "bottom": int(rows.max()) if len(rows) else None}
    finally:
        bpy.data.scenes.remove(sc)
        bpy.data.objects.remove(cam_obj)
        bpy.data.cameras.remove(cam_data)
        for w_ in worlds:
            bpy.data.worlds.remove(w_)
    cams_path = os.path.join(out, "cameras.json")
    with open(cams_path, "w") as f:
        json.dump({"cameras": recs, "background": background}, f, sort_keys=True, indent=1)
    return {"ok": True, "images": images, "masks": masks, "cameras": recs, "cameras_json": cams_path, "height_m": round(height, 6), "meshes": [m.name for m in meshes]}
