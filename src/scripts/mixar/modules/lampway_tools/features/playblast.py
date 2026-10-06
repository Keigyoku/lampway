# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""playblast_capture: a light-engine playblast of the posed blockout per shot (specs/wiki/playblast_capture.md), extending render_video's throw-away-scene
approach: each shot renders frames [a, b] of the user's own scene from a named camera or a waypoint path, to an H.264 mp4 plus exact first and last frame
PNG stills for the video model, and a shot_list.json with every file's sha256.

Measured (Blender 5.2, background): a throw-away scene that links the user's collection does NOT evaluate the user's animation at its own frame (a ball
keyed from x=-1.5 to 1.5 rendered at the user's current position on every frame). So each frame is reached with the USER's scene ``frame_set`` (the
only change to it; the frame is restored), rendered as a PNG from the throw-away scene, and the PNG sequence is encoded by a second throw-away scene's
sequencer. The first and last stills are the very frames the movie was made from.

A shot's length must equal the planned video duration within one frame: a playblast that runs long or short conditions the video model on the wrong
timing. Light engines only (Workbench, EEVEE): Cycles is refused. The temporary scene, the waypoint cameras and their data are removed; the user's frame
is restored."""

import hashlib
import json
import math
import os
import shutil
import tempfile

import bpy
from mathutils import Vector

from . import common as C
from .video import ENGINES, MAX_FRAMES

STILLS = ("first", "last", "both", "none")


def _sha(p) -> str:
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def _check(shots, fps, engine, stills, target_duration_s, scene_objects):
    if engine == "cycles":
        raise C.FeatureError("Cycles is refused: it locks the machine while the owner works live; use workbench or eevee")
    if engine not in ENGINES:
        raise C.FeatureError(f"unknown engine {engine!r}; workbench | eevee")
    if stills not in STILLS:
        raise C.FeatureError(f"stills is {' | '.join(STILLS)}")
    if not shots:
        raise C.FeatureError("give the shots: [{name, camera: <camera object> | [{frame, location}], frames: [a, b], duration_s, look_at}]")
    names = [s.get("name") for s in shots]
    if len(set(names)) != len(names) or not all(isinstance(n, str) and n and "/" not in n for n in names):
        raise C.FeatureError("shot names are unique plain names (they name the files)")
    for o in scene_objects or []:
        ob = bpy.data.objects.get(o)
        if ob is None:
            raise C.FeatureError(f"no object {o!r} in the scene")
        if ob.hide_render or ob.hide_get():
            raise C.FeatureError(f"{o!r} is hidden: the objects of a playblast must be visible")
    for s in shots:
        fr = s.get("frames")
        if not (isinstance(fr, list) and len(fr) == 2 and int(fr[0]) <= int(fr[1])):
            raise C.FeatureError(f"shot {s['name']!r}: frames is [first, last]")
        n = int(fr[1]) - int(fr[0]) + 1
        if n > MAX_FRAMES:
            raise C.FeatureError(f"shot {s['name']!r}: at most {MAX_FRAMES} frames")
        cam = s.get("camera")
        if isinstance(cam, str):
            ob = bpy.data.objects.get(cam)
            if ob is None or ob.type != "CAMERA":
                cams = sorted(o.name for o in bpy.data.objects if o.type == "CAMERA")
                raise C.FeatureError(f"shot {s['name']!r}: no camera named {cam!r}; the cameras are: {cams}")
        elif not (isinstance(cam, list) and cam and all("frame" in w and "location" in w for w in cam)):
            raise C.FeatureError(f"shot {s['name']!r}: camera is a camera object's name or waypoints [{{frame, location}}]")
        planned = s.get("duration_s", target_duration_s)
        if planned is not None and abs(n / float(fps) - float(planned)) > 1.0 / float(fps) + 1e-9:
            raise C.FeatureError(f"playblast length must match the planned video duration: shot {s['name']!r} is {n} frames = {n / float(fps):.3f} s at "
                                 f"{fps} fps, the plan says {float(planned):.3f} s (one frame of slack)")


def _path_camera(sc, s):
    data = bpy.data.cameras.new("lw_pb_cam")
    cam = bpy.data.objects.new("lw_pb_cam", data)
    sc.collection.objects.link(cam)
    look = s.get("look_at")
    if look:
        target = bpy.data.objects.get(look) if isinstance(look, str) else None
        if target is None and isinstance(look, str):
            raise C.FeatureError(f"shot {s['name']!r}: no object {look!r} to look at")
        if target is None:
            target = bpy.data.objects.new("lw_pb_target", None)
            sc.collection.objects.link(target)
            target.location = Vector(look)
        con = cam.constraints.new("TRACK_TO")
        con.target, con.track_axis, con.up_axis = target, "TRACK_NEGATIVE_Z", "UP_Y"
    edit = bpy.context.preferences.edit
    before = edit.keyframe_new_interpolation_type
    edit.keyframe_new_interpolation_type = "LINEAR"
    try:
        for w in sorted(s["camera"], key=lambda w: int(w["frame"])):
            cam.location = Vector(w["location"])
            cam.keyframe_insert("location", frame=int(w["frame"]))
    finally:
        edit.keyframe_new_interpolation_type = before
    return cam


def _png(sc, path):
    r = sc.render
    if hasattr(r.image_settings, "media_type"):
        r.image_settings.media_type = "IMAGE"
    r.image_settings.file_format = "PNG"
    r.filepath = path
    bpy.ops.render.render(write_still=True, scene=sc.name)
    return path


def _encode(frames, fps, width, height, path):
    """The PNG sequence to an H.264 mp4 through a throw-away scene's sequencer."""
    sc = bpy.data.scenes.new("lw_playblast_enc")
    try:
        se = sc.sequence_editor_create()
        strips = se.strips if hasattr(se, "strips") else se.sequences          # an empty collection is falsy: test the attribute
        strip = strips.new_image("lw_pb_frames", frames[0], 1, 1)
        for f in frames[1:]:
            strip.elements.append(os.path.basename(f))
        sc.frame_start, sc.frame_end = 1, len(frames)
        r = sc.render
        r.fps = int(fps)
        r.resolution_x, r.resolution_y, r.resolution_percentage = int(width), int(height), 100
        if hasattr(r.image_settings, "media_type"):
            r.image_settings.media_type = "VIDEO"
        r.image_settings.file_format = "FFMPEG"
        r.ffmpeg.format, r.ffmpeg.codec, r.ffmpeg.constant_rate_factor = "MPEG4", "H264", "MEDIUM"
        r.filepath = path
        bpy.ops.render.render(animation=True, scene=sc.name)
    finally:
        bpy.data.scenes.remove(sc)
    if os.path.exists(path):
        return path
    stem = os.path.basename(path).rsplit(".", 1)[0]
    found = [os.path.join(os.path.dirname(path), f) for f in os.listdir(os.path.dirname(path)) if f.startswith(stem) and f.endswith(".mp4")]
    if not found:
        raise C.FeatureError(f"the render produced no file at {path}")
    os.replace(found[0], path)
    return path


def playblast_capture(root, out_dir, shots, fps=24, width=640, height=360, engine="workbench", stills="both", target_duration_s=None, scene_objects=None):
    _check(shots, fps, engine, stills, target_duration_s, scene_objects)
    os.makedirs(out_dir, exist_ok=True)
    home = bpy.context.scene
    frame0 = home.frame_current
    out = []
    for s in shots:
        a, b = int(s["frames"][0]), int(s["frames"][1])
        sc = bpy.data.scenes.new("lw_playblast")
        made = []
        try:
            sc.collection.children.link(home.collection)
            if isinstance(s["camera"], str):
                sc.camera = bpy.data.objects[s["camera"]]
            else:
                sc.camera = _path_camera(sc, s)
                made = [o for o in sc.collection.objects if o.name.startswith("lw_pb_")]
            r = sc.render
            r.engine = ENGINES[engine]
            r.resolution_x, r.resolution_y, r.resolution_percentage = int(width), int(height), 100
            r.fps = int(fps)
            world = bpy.data.worlds.new("lw_pb_world")
            world.use_nodes = False
            world.color = (0.05, 0.05, 0.06)
            sc.world = world
            if engine == "eevee":
                sun = bpy.data.objects.new("lw_pb_sun", bpy.data.lights.new("lw_pb_sun", "SUN"))
                sc.collection.objects.link(sun)
                sun.rotation_euler = (math.radians(50), 0, math.radians(30))
                made.append(sun)
            seq_dir = tempfile.mkdtemp(prefix="lw_pb_", dir=out_dir)
            frames = []
            for f in range(a, b + 1):
                home.frame_set(f)                                          # the user's scene evaluates its animation; the throw-away scene renders it
                sc.frame_set(f)                                            # the waypoint camera's keys live in the throw-away scene
                frames.append(_png(sc, os.path.join(seq_dir, f"f{f - a:05d}.png")))
            movie = _encode(frames, fps, width, height, os.path.join(out_dir, f"{s['name']}.mp4"))
            first = last = None
            if stills in ("first", "both"):
                first = os.path.join(out_dir, f"{s['name']}_first.png")
                shutil.copyfile(frames[0], first)
            if stills in ("last", "both"):
                last = os.path.join(out_dir, f"{s['name']}_last.png")
                shutil.copyfile(frames[-1], last)
            shutil.rmtree(seq_dir, ignore_errors=True)
        finally:
            for o in made:
                data = o.data
                bpy.data.objects.remove(o)
                if isinstance(data, bpy.types.Camera):
                    bpy.data.cameras.remove(data)
                elif isinstance(data, bpy.types.Light):
                    bpy.data.lights.remove(data)
            for o in [o for o in bpy.data.objects if o.name.startswith("lw_pb_target")]:
                bpy.data.objects.remove(o)
            w = sc.world
            bpy.data.scenes.remove(sc)
            if w is not None and w.users == 0:
                bpy.data.worlds.remove(w)
            home.frame_set(frame0)
        rel = lambda p: os.path.relpath(p, root) if p else None  # noqa: E731
        out.append({"name": s["name"], "file": rel(movie), "frames": b - a + 1, "frame_range": [a, b], "fps": int(fps), "duration_s": round((b - a + 1) / float(fps), 4),
                    "size": [int(width), int(height)], "engine": engine, "kind": "playblast", "bytes": os.path.getsize(movie), "first_png": rel(first),
                    "last_png": rel(last), "camera": s["camera"] if isinstance(s["camera"], str) else "waypoints", "sha256": _sha(movie)})
    listing = {"fps": int(fps), "engine": engine, "target_duration_s": target_duration_s, "shots": out}
    lp = os.path.join(out_dir, "shot_list.json")
    with open(lp, "w", encoding="utf-8") as fh:
        json.dump(listing, fh, indent=1)
    return {"shots": out, "shot_list": os.path.relpath(lp, root),
            "note": "a rough playblast is an animated storyboard for framing and timing, not a finished render"}
