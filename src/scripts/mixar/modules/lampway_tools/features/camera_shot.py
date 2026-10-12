# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""camera_shot (specs/mixar_docs/camera_shot.md): shots as native camera keys, the Director's move presets (the Client's own `director/core/camera_moves.py` poses: orbit, dolly, dolly zoom, crane, pan), and
beauty / clay / depth guide passes across the shot. A shot is a camera object tagged `lw_shot`; its keys are ordinary location / rotation / lens keyframes, so they stay editable in the scene. Guides render with
Workbench (never Cycles: it locks the machine while the owner works live); depth is computed by ray casts against the scene with fixed near and far, so it is comparable between frames. The user's frame, render
engine and resolution are restored."""

import math
import os
import random

import bpy
import numpy as np
from mathutils import Vector

from . import common as C

ASPECTS = {"16:9": (16, 9), "2.39:1": (239, 100), "9:16": (9, 16), "1:1": (1, 1), "4:3": (4, 3)}
ACTIONS = ("list", "new", "frame", "key", "preset", "render_guides", "delete")
PASSES = ("beauty", "clay", "depth")
SPACING = 12                    # frames between beats: the Director's default keyframe spacing
HANDHELD_RAD = math.radians(0.25)


def _moves():
    from mixar.modules.director.core import camera_moves as CM
    return CM


def _res(aspect, size=1920):
    w, h = ASPECTS[aspect]
    return (size, max(2, round(size * h / w))) if w >= h else (max(2, round(size * w / h)), size)


def _shot_cam(shot):
    cams = [o for o in bpy.data.objects if o.type == "CAMERA" and o.get("lw_shot") == shot]
    if not cams:
        known = sorted(o["lw_shot"] for o in bpy.data.objects if o.type == "CAMERA" and o.get("lw_shot"))
        raise C.FeatureError(f"no shot named {shot!r}; the shots are {known}")
    return cams[0]


def _keys(cam) -> list:
    ad = cam.animation_data
    frames = set()
    if ad and ad.action:
        for fc in _fcurves(ad.action):
            if fc.data_path == "location":
                frames.update(int(round(k.co[0])) for k in fc.keyframe_points)
    return sorted(frames)


def _fcurves(act):
    if hasattr(act, "fcurves"):
        return list(act.fcurves)
    out = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                out += list(cb.fcurves)
    return out


def _info(cam) -> dict:
    return {"shot_id": cam["lw_shot"], "camera": cam.name, "keys": _keys(cam), "lens_mm": cam.data.lens, "aspect": cam.get("lw_aspect", "16:9")}


def _subject(target):
    if target:
        return C.need_object(target, kind="")
    sel = [o for o in bpy.context.selected_objects if o.type == "MESH"]
    if not sel:
        raise C.FeatureError("select the subject or pass target")
    return sel[0]


def _bounds(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo, hi = Vector([min(p[i] for p in pts) for i in range(3)]), Vector([max(p[i] for p in pts) for i in range(3)])
    return (lo + hi) / 2, max((hi - lo).length / 2, 1e-3)


def _aim(cam, location, target):
    d = target - location
    m = d.normalized().to_track_quat("-Z", "Y").to_matrix().to_4x4()
    m.translation = location
    cam.matrix_world = m


def _key(cam, frame):
    cam.rotation_mode = "XYZ"
    cam.keyframe_insert("location", frame=frame)
    cam.keyframe_insert("rotation_euler", frame=frame)
    cam.data.keyframe_insert("lens", frame=frame)


def _frame_on(cam, ob):
    c, r = _bounds(ob)
    fov = 2 * math.atan(min(cam.data.sensor_width, cam.data.sensor_height if cam.data.sensor_fit == "VERTICAL" else cam.data.sensor_width) / (2 * cam.data.lens))
    dist = r / math.sin(fov / 2) * 1.2
    loc = c + Vector((0.0, -dist * math.cos(math.radians(15)), dist * math.sin(math.radians(15))))
    _aim(cam, loc, c)


def _set_aspect(cam, aspect):
    if aspect not in ASPECTS:
        raise C.FeatureError(f"aspect must be one of {list(ASPECTS)}")
    sc = bpy.context.scene
    sc.render.resolution_x, sc.render.resolution_y = _res(aspect)
    sc.render.resolution_percentage = 100
    cam["lw_aspect"] = aspect


def _check_lens(lens):
    if lens is None:
        return None
    if not 18 <= float(lens) <= 135:
        raise C.FeatureError("lens is 18 to 135 mm")
    return float(lens)


def _preset(cam, subject, preset, frame, handheld):
    CM = _moves()
    names = [m[0] for m in CM.CAMERA_MOVES]
    if preset not in names:
        raise C.FeatureError(f"unknown preset {preset!r}: {names}")
    sc = bpy.context.scene
    sc.frame_set(frame)
    _key(cam, frame)                                                                  # the current pose is the first beat
    poses = CM.move_poses(sc, cam, preset)
    base_lens = cam.data.lens
    rnd = random.Random(f"{cam.name}:{preset}")
    for i, pose in enumerate(poses, 1):
        f = frame + i * SPACING
        cam.matrix_world = pose
        if i == len(poses):
            cam.data.lens = base_lens * CM.lens_scale(preset)
        if handheld:
            e = cam.rotation_euler.copy()
            e.x, e.y, e.z = e.x + rnd.uniform(-1, 1) * HANDHELD_RAD, e.y + rnd.uniform(-1, 1) * HANDHELD_RAD, e.z + rnd.uniform(-1, 1) * HANDHELD_RAD
            cam.rotation_euler = e
        _key(cam, f)
    sc.frame_set(frame)


def _depth(sc, cam, width, near, far):
    from mathutils import Vector as V
    h = max(2, round(width * sc.render.resolution_y / sc.render.resolution_x))
    corners = cam.data.view_frame(scene=sc)                                         # tr, br, bl, tl at z = -1 in camera space
    tr, br, bl, tl = (V(c) for c in corners)
    rot, org = cam.matrix_world.to_quaternion(), cam.matrix_world.translation
    dg = bpy.context.evaluated_depsgraph_get()
    img = np.zeros((h, width), dtype=np.float32)
    for j in range(h):
        v = (j + 0.5) / h
        left, right = tl + (bl - tl) * v, tr + (br - tr) * v
        for i in range(width):
            u = (i + 0.5) / width
            d = (rot @ (left + (right - left) * u)).normalized()
            hit, loc, _n, _i, _o, _m = sc.ray_cast(dg, org, d)
            if hit:
                img[j, i] = min(1.0, max(0.0, 1.0 - ((loc - org).length - near) / max(1e-6, far - near)))
    return img, h


def _save_gray(path, img):
    h, w = img.shape
    im = bpy.data.images.new("lw_guide", w, h, alpha=False)
    flat = np.flipud(img)                                                           # Blender images are bottom-up
    px = np.repeat(flat[:, :, None], 4, axis=2)
    px[:, :, 3] = 1.0
    im.pixels.foreach_set(px.ravel())
    im.filepath_raw, im.file_format = path, "PNG"
    im.save()
    bpy.data.images.remove(im)


def _render_guides(cam, subject, passes, out_dir, size):
    keys = _keys(cam)
    if len(keys) < 2:
        raise C.FeatureError("key at least two poses before rendering guides (new, then preset or key)")
    bad = [p for p in passes if p not in PASSES]
    if bad:
        raise C.FeatureError(f"unknown pass {bad}: {list(PASSES)}")
    os.makedirs(out_dir, exist_ok=True)
    home = bpy.context.scene
    keep = {"frame": home.frame_current, "engine": home.render.engine, "rx": home.render.resolution_x, "ry": home.render.resolution_y, "pct": home.render.resolution_percentage}
    w0, h0 = home.render.resolution_x, home.render.resolution_y
    scale = size / max(w0, h0)
    out = {p: [] for p in passes}
    c, r = _bounds(subject)
    home.frame_set(keys[0])
    dist0 = (cam.matrix_world.translation - c).length
    near, far = max(0.01, dist0 * 0.4 - 2 * r), dist0 + 3 * r                         # fixed for the whole shot: depth is comparable between frames
    try:
        home.render.resolution_x, home.render.resolution_y, home.render.resolution_percentage = max(2, round(w0 * scale)), max(2, round(h0 * scale)), 100
        home.camera = cam
        for f in keys:
            home.frame_set(f)
            for p in passes:
                path = os.path.join(out_dir, f"{cam['lw_shot']}_{p}_{f:04d}.png")
                if p == "depth":
                    img, _h = _depth(home, cam, home.render.resolution_x, near, far)
                    _save_gray(path, img)
                else:
                    home.render.engine = "BLENDER_WORKBENCH"
                    sh = home.display.shading
                    sh.light, sh.color_type = ("STUDIO", "OBJECT") if p == "beauty" else ("STUDIO", "SINGLE")
                    if p == "clay":
                        sh.single_color = (0.78, 0.78, 0.78)
                    home.render.film_transparent = False
                    home.render.image_settings.file_format = "PNG"
                    home.render.filepath = path
                    bpy.ops.render.render(write_still=True)
                out[p].append(path)
    finally:
        home.frame_set(keep["frame"])
        home.render.engine = keep["engine"]
        home.render.resolution_x, home.render.resolution_y, home.render.resolution_percentage = keep["rx"], keep["ry"], keep["pct"]
    return out


def camera_shot(root, action="list", shot=None, camera=None, lens_mm=None, aspect=None, frame=1, preset=None, target=None, passes=None, out_dir="guides", handheld=False, size=512, resolve=None):
    if action not in ACTIONS:
        raise C.FeatureError(f"action is one of {list(ACTIONS)}")
    if action == "list":
        return {"ok": True, "shots": [_info(o) for o in bpy.data.objects if o.type == "CAMERA" and o.get("lw_shot")]}
    if not shot:
        raise C.FeatureError("name the shot")
    lens = _check_lens(lens_mm)
    if action == "new":
        if any(o.get("lw_shot") == shot for o in bpy.data.objects if o.type == "CAMERA"):
            raise C.FeatureError(f"a shot named {shot!r} exists: pick another name or delete it")
        subject = _subject(target)
        if aspect is not None and aspect not in ASPECTS:
            raise C.FeatureError(f"aspect must be one of {list(ASPECTS)}")
        cam = bpy.data.objects.get(camera) if camera else None
        if camera and (cam is None or cam.type != "CAMERA"):
            raise C.FeatureError(f"no camera named {camera!r}")
        if cam is None:
            cam = bpy.data.objects.new(f"shot_{shot}", bpy.data.cameras.new(f"shot_{shot}"))
            bpy.context.scene.collection.objects.link(cam)
            cam["lw_made"] = True
        cam["lw_shot"] = shot
        if lens is not None:
            cam.data.lens = lens
        _set_aspect(cam, aspect or "16:9")
        bpy.context.scene.camera = cam
        _frame_on(cam, subject)
        bpy.context.view_layer.update()
        _key(cam, int(frame))
        return {"ok": True, "shots": [_info(cam)]}
    cam = _shot_cam(shot)
    if action == "frame":
        _frame_on(cam, _subject(target))
        _key(cam, int(frame))
    elif action == "key":
        if lens is not None:
            cam.data.lens = lens
        _key(cam, int(frame))
    elif action == "preset":
        if not preset:
            raise C.FeatureError("name a preset")
        _preset(cam, _subject(target), preset, int(frame), bool(handheld))
    elif action == "render_guides":
        requested = list(PASSES) if passes is None else ([p.strip() for p in passes.split(",")] if isinstance(passes, str) else passes)
        if not isinstance(requested, (list, tuple)) or not requested or any(not isinstance(p, str) or p not in PASSES for p in requested):
            raise C.FeatureError(f"passes must name one or more of {list(PASSES)} (comma-separated string or list)")
        out = Path_resolve(resolve, out_dir)
        guides = _render_guides(cam, _subject(target) if target else _guess_subject(cam), list(dict.fromkeys(requested)), out, int(size))
        return {"ok": True, "shots": [_info(cam)], "guides": guides}
    elif action == "delete":
        made = bool(cam.get("lw_made"))
        data = cam.data
        if made:
            bpy.data.objects.remove(cam)
            if data.users == 0:
                bpy.data.cameras.remove(data)
        else:
            for k in ("lw_shot", "lw_aspect"):
                cam.pop(k, None)
            if cam.animation_data:
                cam.animation_data_clear()
        return {"ok": True, "shots": []}
    if lens is not None and action == "new":
        cam.data.lens = lens
    return {"ok": True, "shots": [_info(cam)]}


def Path_resolve(resolve, p):
    return str(resolve(p)) if resolve else str(p)


def _guess_subject(cam):
    meshes = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    if not meshes:
        raise C.FeatureError("select the subject or pass target")
    c = cam.matrix_world.translation
    return min(meshes, key=lambda o: (o.matrix_world.translation - c).length)
