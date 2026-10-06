# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""camera_shot (specs/mixar_docs/camera_shot.md) in the real binary: shots as native camera keys, the Director's move presets (orbit, dolly, crane, pan, dolly zoom), and beauty / clay / depth guide passes across
the shot, with the lens bound, the aspect list and the 'key at least two poses' refusal."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_CS = '''
import mathutils
def subject(name="Subject", size=2.0, loc=(0, 0, 1)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=size)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.location = loc
    return link(ob)
def dist_to(cam, ob):
    bpy.context.view_layer.update()
    return (cam.matrix_world.translation - ob.matrix_world.translation).length
def aim_error(cam, ob):
    d = (ob.matrix_world.translation - cam.matrix_world.translation).normalized()
    fwd = -(cam.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, 1)))
    return 1.0 - float(d.dot(fwd))
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_CS + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_new_frames_the_subject_sets_lens_and_aspect_and_refuses_a_lens_outside_18_to_135(tmp_path):
    d = one(go(tmp_path, '''
s = subject()
ok = call("camera_shot", action="new", shot="hero", target="Subject", lens_mm=50, aspect="2.39:1")
low = call("camera_shot", action="new", shot="x", target="Subject", lens_mm=17)
high = call("camera_shot", action="new", shot="x", target="Subject", lens_mm=136)
asp = call("camera_shot", action="new", shot="y", target="Subject", aspect="5:4")
no_target = call("camera_shot", action="new", shot="z")
cam = bpy.data.objects[ok["shots"][0]["camera"]]
sc = bpy.context.scene
print("RESULT", json.dumps({"ok": ok, "low": low, "high": high, "asp": asp, "nt": no_target, "lens": cam.data.lens, "res": [sc.render.resolution_x, sc.render.resolution_y], "aim": aim_error(cam, s), "dist": dist_to(cam, s)}))
'''))
    assert d["ok"]["ok"] and d["ok"]["shots"][0]["shot_id"] == "hero" and d["ok"]["shots"][0]["lens_mm"] == 50 and d["ok"]["shots"][0]["aspect"] == "2.39:1" and d["ok"]["shots"][0]["keys"] == [1]
    assert "lens is 18 to 135 mm" in d["low"]["error"] and "lens is 18 to 135 mm" in d["high"]["error"] and "aspect" in d["asp"]["error"] and "select the subject or pass target" in d["nt"]["error"]
    assert d["lens"] == 50 and d["res"][0] / d["res"][1] > 2.3 and d["aim"] < 1e-4 and d["dist"] > 2.0


def test_an_orbit_preset_keys_an_arc_that_stays_on_the_orbit_radius_and_keeps_the_subject_framed(tmp_path):
    d = one(go(tmp_path, '''
s = subject()
call("camera_shot", action="new", shot="hero", target="Subject")
cam = bpy.data.objects[call("camera_shot", action="list")["shots"][0]["camera"]]
r0 = dist_to(cam, s)
res = call("camera_shot", action="preset", shot="hero", preset="ORBIT_LEFT", target="Subject")
keys = res["shots"][0]["keys"]
out = []
for f in keys:
    bpy.context.scene.frame_set(f)
    out.append({"f": f, "r": dist_to(cam, s), "aim": aim_error(cam, s)})
print("RESULT", json.dumps({"keys": keys, "r0": r0, "out": out, "res": res["shots"][0]}))
'''))
    assert d["keys"] == [1, 13, 25]
    for k in d["out"]:
        assert abs(k["r"] - d["r0"]) / d["r0"] < 0.05 and k["aim"] < 1e-3, k


def test_a_dolly_in_writes_depth_guides_whose_mean_rises_as_the_camera_approaches_and_clay_and_beauty_exist(tmp_path):
    d = one(go(tmp_path, '''
s = subject()
call("camera_shot", action="new", shot="hero", target="Subject")
call("camera_shot", action="preset", shot="hero", preset="DOLLY_IN", target="Subject")
res = call("camera_shot", action="render_guides", shot="hero", passes=["beauty", "clay", "depth"], out_dir="guides", size=96)
from PIL import Image
import numpy as np
means = [float(np.asarray(Image.open(p).convert("L"), dtype=float).mean()) for p in res["guides"]["depth"]]
sizes = {k: [list(Image.open(p).size) for p in v] for k, v in res["guides"].items()}
print("RESULT", json.dumps({"res": res, "means": means, "sizes": sizes, "scene_engine": bpy.context.scene.render.engine, "frame": bpy.context.scene.frame_current}))
'''))
    g = d["res"]["guides"]
    assert d["res"]["ok"] and len(g["beauty"]) == len(g["clay"]) == len(g["depth"]) == 2
    assert d["means"][0] < d["means"][1], d["means"]                                              # the subject fills more of the frame and is nearer: brighter on average
    assert all(s[0] <= 96 and s[1] <= 96 for v in d["sizes"].values() for s in v) and d["sizes"]["depth"][0] == d["sizes"]["beauty"][0]
    assert d["frame"] == 1                                                                         # the user's frame and render engine are restored


def test_guides_need_two_keyed_poses_and_the_lens_zoom_and_pan_presets_key_what_they_say(tmp_path):
    d = one(go(tmp_path, '''
s = subject()
call("camera_shot", action="new", shot="hero", target="Subject", lens_mm=50)
few = call("camera_shot", action="render_guides", shot="hero", out_dir="guides")
dz = call("camera_shot", action="preset", shot="hero", preset="DOLLY_ZOOM", target="Subject")
cam = bpy.data.objects[dz["shots"][0]["camera"]]
lens = {}
for f in dz["shots"][0]["keys"]:
    bpy.context.scene.frame_set(f); lens[f] = cam.data.lens
bad = call("camera_shot", action="preset", shot="hero", preset="BARREL_ROLL", target="Subject")
print("RESULT", json.dumps({"few": few, "dz": dz, "lens": lens, "bad": bad}))
'''))
    assert d["few"]["ok"] is False and "key at least two poses" in d["few"]["error"]
    assert d["dz"]["shots"][0]["keys"] == [1, 13] and abs(d["lens"]["1"] - 50) < 1e-6 and abs(d["lens"]["13"] - 30) < 1e-6          # widens by (1 - 0.4)
    assert d["bad"]["ok"] is False and "ORBIT_LEFT" in d["bad"]["error"]


def test_handheld_is_deterministic_and_delete_removes_the_camera_and_its_keys(tmp_path):
    d = one(go(tmp_path, '''
s = subject()
def shot_pose(handheld):
    for o in list(bpy.data.objects):
        if o.type == "CAMERA": bpy.data.objects.remove(o)
    call("camera_shot", action="new", shot="hero", target="Subject")
    res = call("camera_shot", action="preset", shot="hero", preset="PAN_LEFT", target="Subject", handheld=handheld)
    cam = bpy.data.objects[res["shots"][0]["camera"]]
    bpy.context.scene.frame_set(res["shots"][0]["keys"][-1])
    return [round(x, 6) for x in cam.rotation_euler]
a, b, plain = shot_pose(True), shot_pose(True), shot_pose(False)
deleted = call("camera_shot", action="delete", shot="hero")
print("RESULT", json.dumps({"a": a, "b": b, "plain": plain, "deleted": deleted, "cams": [o.name for o in bpy.data.objects if o.type == "CAMERA"], "list": call("camera_shot", action="list")}))
'''))
    assert d["a"] == d["b"] and d["a"] != d["plain"] and max(abs(x - y) for x, y in zip(d["a"], d["plain"])) < 0.02
    assert d["deleted"]["ok"] and d["cams"] == [] and d["list"]["shots"] == []
