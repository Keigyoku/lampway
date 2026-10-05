# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Video. Proven code: a turntable or a keyframed camera path rendered by the LIGHT engines (Workbench or EEVEE; Cycles is
refused: the owner works live) in a throw-away scene and encoded to H.264 by Blender's own FFmpeg. The result is read back (frame
count, size, bytes) to prove it. The generative video model (Seedance and the like) is the slot behind ``engine="model:<name>"``:
no driver exists, so it says so instead of pretending."""

import math
import os

import bpy
from mathutils import Vector

from . import common as C

MAX_FRAMES = 1200
ENGINES = {"workbench": "BLENDER_WORKBENCH", "eevee": "BLENDER_EEVEE"}


def _center_and_radius(ob):
    corners = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    return (lo + hi) / 2, max((hi - lo).length / 2, 1e-3)


def render_video(object, out, kind="turntable", frames=48, width=640, height=360, fps=24, engine="workbench", waypoints=None,
                 elevation=20.0, distance=None):
    if engine.startswith("model:"):
        raise C.FeatureError(f"{engine}: the generative video model is not wired (no driver exists); use engine='workbench' or 'eevee' for a rendered move")
    if engine == "cycles":
        raise C.FeatureError("Cycles is refused: it locks the machine while the owner works live; use workbench or eevee")
    if engine not in ENGINES:
        raise C.FeatureError(f"unknown engine {engine!r}; workbench | eevee")
    if kind not in ("turntable", "camera_path"):
        raise C.FeatureError(f"unknown kind {kind!r}; turntable | camera_path")
    frames = int(frames)
    if not 1 <= frames <= MAX_FRAMES:
        raise C.FeatureError(f"frames must be between 1 and {MAX_FRAMES}")
    if kind == "camera_path" and not waypoints:
        raise C.FeatureError("camera_path needs waypoints: [{frame, location: [x, y, z]}, ...]")
    src = C.need_object(object)
    center, radius = _center_and_radius(src)
    home = bpy.context.scene
    sc = bpy.data.scenes.new("lw_video")
    target = bpy.data.objects.new("lw_video_target", None)
    cam_data = bpy.data.cameras.new("lw_video_cam")
    cam = bpy.data.objects.new("lw_video_cam", cam_data)
    try:
        sc.collection.children.link(home.collection)
        for o in (target, cam):
            sc.collection.objects.link(o)
        target.location = center
        con = cam.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
        sc.camera = cam
        sc.frame_start = 1
        sc.render.fps = int(fps)
        if kind == "turntable":
            sc.frame_end = frames
            dist = float(distance) if distance else radius * 3.2
            el = math.radians(float(elevation))
            for f in range(1, frames + 1):
                a = 2 * math.pi * (f - 1) / frames
                cam.location = center + Vector((dist * math.cos(el) * math.sin(a), -dist * math.cos(el) * math.cos(a), dist * math.sin(el)))
                cam.keyframe_insert("location", frame=f)
        else:
            pts = sorted(waypoints, key=lambda w: int(w["frame"]))
            sc.frame_end = int(pts[-1]["frame"])
            frames = sc.frame_end - sc.frame_start + 1
            edit = bpy.context.preferences.edit
            before = edit.keyframe_new_interpolation_type
            edit.keyframe_new_interpolation_type = "LINEAR"        # the Action API differs across builds: set it where keys are made
            try:
                for w in pts:
                    cam.location = Vector(w["location"])
                    cam.keyframe_insert("location", frame=int(w["frame"]))
            finally:
                edit.keyframe_new_interpolation_type = before
        r = sc.render
        r.engine = ENGINES[engine]
        r.resolution_x, r.resolution_y, r.resolution_percentage = int(width), int(height), 100
        if hasattr(r.image_settings, "media_type"):
            r.image_settings.media_type = "VIDEO"            # this Blender lists FFMPEG only once the media type is VIDEO
        r.image_settings.file_format = "FFMPEG"
        r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.constant_rate_factor = "MPEG4", "H264", "MEDIUM"
        os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
        r.filepath = out
        world = bpy.data.worlds.new("lw_video_world")
        world.use_nodes = False
        world.color = (0.05, 0.05, 0.06)
        sc.world = world
        if engine == "eevee":
            sun = bpy.data.objects.new("lw_video_sun", bpy.data.lights.new("lw_video_sun", "SUN"))
            sc.collection.objects.link(sun)
            sun.rotation_euler = (math.radians(50), 0, math.radians(30))
        bpy.ops.render.render(animation=True, scene=sc.name)
    finally:
        for o in list(sc.objects):
            if o.name.startswith("lw_video_"):
                bpy.data.objects.remove(o)
        bpy.data.scenes.remove(sc)
        for d in (cam_data,):
            bpy.data.cameras.remove(d)
    path = out if os.path.exists(out) else next((os.path.join(os.path.dirname(out), f) for f in os.listdir(os.path.dirname(out)) if f.startswith(os.path.basename(out).rsplit(".", 1)[0])), out)
    if not os.path.exists(path):
        raise C.FeatureError(f"the render produced no file at {out}")
    return {"file": path, "frames": frames, "fps": int(fps), "size": [int(width), int(height)], "engine": engine, "kind": kind,
            "bytes": os.path.getsize(path), "waypoints": len(waypoints or [])}
