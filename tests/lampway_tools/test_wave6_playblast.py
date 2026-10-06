# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""playblast_capture (specs/wiki/playblast_capture.md) in the real binary: one light-engine playblast per shot from a named camera or a waypoint path, exact first and
last frame stills, a shot list, and the refusal when a shot's length does not match the planned video duration."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

SCENE = '''
ball = sphere("ball", 0.4, subdiv=3)
ball.location = (-1.5, 0, 0); ball.keyframe_insert("location", frame=1)
ball.location = (1.5, 0, 0); ball.keyframe_insert("location", frame=12)
cd = bpy.data.cameras.new("shotcam"); cam = bpy.data.objects.new("shotcam", cd); link(cam)
cam.location = (0, -8, 0); cam.rotation_euler = (math.radians(90), 0, 0)
bpy.context.scene.frame_current = 7
'''

CENTROID = '''
def centroid_x(path):
    im = bpy.data.images.load(path)
    w, h = im.size
    px = np.array(im.pixels[:]).reshape(h, w, 4)
    lum = px[..., :3].mean(axis=2)
    bg = np.median(lum)
    mask = np.abs(lum - bg) > 0.08
    xs = np.nonzero(mask)[1]
    return float(xs.mean() / w) if len(xs) else None
'''


def test_shots_produce_one_file_each_with_matching_frame_counts(tmp_path):
    d = one(go(tmp_path, SCENE + '''
res = call("playblast_capture", fps=24, width=96, height=64, shots=[
    {"name": "s01", "camera": "shotcam", "frames": [1, 12]},
    {"name": "s02", "camera": [{"frame": 1, "location": [4, -6, 1]}, {"frame": 8, "location": [-4, -6, 1]}], "frames": [1, 8], "look_at": "ball"}])
clips = {s["name"]: bpy.data.movieclips.load(os.path.join(root, s["file"])).frame_duration for s in res.get("shots", [])}
print("RESULT", json.dumps({"res": res, "clips": clips, "scenes": [s.name for s in bpy.data.scenes], "frame": bpy.context.scene.frame_current,
                            "cams": sorted(o.name for o in bpy.data.objects if o.type == "CAMERA"),
                            "list": json.load(open(os.path.join(root, "playblast", "shot_list.json")))}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert [s["name"] for s in res["shots"]] == ["s01", "s02"] and d["clips"] == {"s01": 12, "s02": 8}
    assert [s["frames"] for s in res["shots"]] == [12, 8] and all(s["engine"] == "workbench" for s in res["shots"])
    assert len(d["scenes"]) == 1 and d["frame"] == 7 and d["cams"] == ["shotcam"]             # the temp scene and the waypoint camera are gone; the frame is restored
    assert [s["name"] for s in d["list"]["shots"]] == ["s01", "s02"] and all(len(s["sha256"]) == 64 for s in d["list"]["shots"])


def test_first_and_last_png_are_the_first_and_last_frames(tmp_path):
    d = one(go(tmp_path, SCENE + CENTROID + '''
res = call("playblast_capture", fps=24, width=128, height=64, shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 12]}])
s = res["shots"][0]
print("RESULT", json.dumps({"res": res, "first": centroid_x(os.path.join(root, s["first_png"])), "last": centroid_x(os.path.join(root, s["last_png"]))}))
'''))
    assert d["res"]["ok"]
    assert d["first"] is not None and d["last"] is not None
    assert d["first"] < 0.4 and d["last"] > 0.6                       # frame 1 has the ball at the left, frame 12 at the right


def test_duration_mismatch_refused_within_one_frame_accepted(tmp_path):
    d = one(go(tmp_path, SCENE + '''
short = call("playblast_capture", fps=24, width=32, height=32, target_duration_s=2.0, shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 46]}])
edge = call("playblast_capture", fps=24, width=32, height=32, target_duration_s=2.0, shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 47]}], stills="none")
per_shot = call("playblast_capture", fps=24, width=32, height=32, shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 12], "duration_s": 1.0}])
print("RESULT", json.dumps({"short": short, "edge": edge, "per_shot": per_shot, "files": sorted(os.listdir(root))}))
'''))
    assert d["short"]["ok"] is False and "playblast length must match the planned video duration" in d["short"]["error"]
    assert d["edge"]["ok"] is True and d["edge"]["shots"][0]["first_png"] is None             # 47 frames is one frame short of 2 s: accepted
    assert d["per_shot"]["ok"] is False and "s01" in d["per_shot"]["error"]


def test_cycles_unknown_cameras_and_hidden_objects_are_refused(tmp_path):
    d = one(go(tmp_path, SCENE + '''
cyc = call("playblast_capture", engine="cycles", shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 4]}])
nocam = call("playblast_capture", shots=[{"name": "s01", "camera": "nope", "frames": [1, 4]}])
ball.hide_render = True
hidden = call("playblast_capture", scene_objects=["ball"], shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 4]}])
dup = call("playblast_capture", shots=[{"name": "s01", "camera": "shotcam", "frames": [1, 4]}, {"name": "s01", "camera": "shotcam", "frames": [1, 4]}])
print("RESULT", json.dumps({"cyc": cyc, "nocam": nocam, "hidden": hidden, "dup": dup}))
'''))
    assert d["cyc"]["ok"] is False and "Cycles" in d["cyc"]["error"]
    assert d["nocam"]["ok"] is False and "shotcam" in d["nocam"]["error"]
    assert d["hidden"]["ok"] is False and "ball" in d["hidden"]["error"] and "visible" in d["hidden"]["error"]
    assert d["dup"]["ok"] is False and "unique" in d["dup"]["error"]
