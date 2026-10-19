# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Video (Mixar docs: "Generate video ... camera keyframes and output ... sending frames to an AI video workflow produces a
separate media result"; Stefan's reference-blockout-to-cinematic). Proven code: a turntable or keyframed camera move rendered
by the light engines (Workbench / EEVEE, never Cycles) in a throw-away scene and encoded to H.264 by Blender's own FFmpeg. The
file is read back (frame count, size) to prove it. The generative video model is the slot: not wired, no driver exists."""

import math

from features_support import run


def test_a_turntable_renders_the_requested_frames_into_a_readable_mp4(tmp_path):
    r = run(tmp_path, '''
sphere("ball", 0.5, subdiv=3)
res = call("render_video", kind="turntable", object="ball", frames=6, width=96, height=64, out="video/turn.mp4", engine="workbench")
clip = bpy.data.movieclips.load(root + "/video/turn.mp4") if os.path.exists(root + "/video/turn.mp4") else None
print("RESULT", json.dumps({"res": res, "frames": clip.frame_duration if clip else None, "size": list(clip.size) if clip else None,
                            "bytes": os.path.getsize(root + "/video/turn.mp4") if clip else 0,
                            "scenes": [s.name for s in bpy.data.scenes], "cameras": [o.name for o in bpy.data.objects if o.type == "CAMERA"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    assert out["res"]["ok"] is True and out["res"]["frames"] == 6
    assert out["frames"] == 6 and out["size"] == [96, 64] and out["bytes"] > 1000
    assert len(out["scenes"]) == 1 and out["cameras"] == [], "the throw-away scene and camera are gone"


def test_a_camera_path_is_keyframed_through_the_given_waypoints(tmp_path):
    r = run(tmp_path, '''
sphere("ball", 0.5, subdiv=3)
res = call("render_video", kind="camera_path", object="ball", width=64, height=48, out="video/path.mp4", engine="workbench",
           waypoints=[{"frame": 1, "location": [3, -3, 1]}, {"frame": 5, "location": [0, -4, 2]}, {"frame": 9, "location": [-3, -3, 1]}])
clip = bpy.data.movieclips.load(root + "/video/path.mp4")
print("RESULT", json.dumps({"res": res, "frames": clip.frame_duration}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and out["frames"] == 9 and out["res"]["waypoints"] == 3


def _first_pixel(path):
    """The top-left RGB of the video's first frame, decoded by ffmpeg (the box's, on PATH)."""
    import subprocess
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         capture_output=True, check=True).stdout
    return list(raw[:3])


def test_elevation_distance_and_background_reach_the_render_and_the_file_is_project_relative(tmp_path):
    r = run(tmp_path, '''
sphere("ball", 0.5, subdiv=3)
res = call("render_video", kind="turntable", object="ball", frames=4, width=96, height=64, out="video/high.mp4", engine="workbench",
           elevation=60, distance=4, background="#C81E1E")
print("RESULT", json.dumps({"res": res}))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]["res"]
    assert res["ok"] is True and res["file"] == "video/high.mp4"
    x, y, z = res["camera_start"]                                                  # the ball sits at the origin: frame 1 is straight in front
    assert abs(x) < 1e-3 and abs(y + 4 * math.cos(math.radians(60))) < 1e-3 and abs(z - 4 * math.sin(math.radians(60))) < 1e-3
    red, green, blue = _first_pixel(tmp_path / "video" / "high.mp4")
    assert red > 120 and green < 60 and blue < 60, (red, green, blue)


def test_a_background_that_is_not_a_hex_colour_is_refused(tmp_path):
    r = run(tmp_path, '''
sphere("ball", 0.5, subdiv=2)
print("RESULT", json.dumps({"bad": call("render_video", object="ball", out="a.mp4", background="red")}))
''')
    out = r.results[0]["bad"]
    assert out["ok"] is False and "#RRGGBB" in out["error"]


def test_refusals_the_path_the_kind_the_engine_and_the_unwired_model_slot(tmp_path):
    r = run(tmp_path, '''
sphere("ball", 0.5, subdiv=2)
print("RESULT", json.dumps({"outside": call("render_video", object="ball", out="/etc/x.mp4"),
    "kind": call("render_video", kind="spin", object="ball", out="a.mp4"),
    "cycles": call("render_video", object="ball", out="a.mp4", engine="cycles"),
    "frames": call("render_video", object="ball", out="a.mp4", frames=100000),
    "model": call("render_video", object="ball", out="a.mp4", engine="model:seedance"),
    "path_needs_points": call("render_video", kind="camera_path", object="ball", out="a.mp4")}))
''')
    out = r.results[0]
    assert "outside the project root" in out["outside"]["error"]
    assert "spin" in out["kind"]["error"]
    assert out["cycles"]["ok"] is False and "Cycles" in out["cycles"]["error"]
    assert out["frames"]["ok"] is False and "frames" in out["frames"]["error"]
    assert out["model"]["ok"] is False and "not wired" in out["model"]["error"]
    assert out["path_needs_points"]["ok"] is False and "waypoints" in out["path_needs_points"]["error"]
