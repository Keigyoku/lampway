# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_rig_convert (STATUS O36, canon 22, rig_tools/rig_convert.md): the external rig-conversion and normalization tool over the ported
TITAN modules. A Blender armature becomes a native profile (the to-blender adapter: handedness reflected, metres = 100 cm per unit, the
reference = the bind unless alignment rules are given); its action becomes native samples on the 30 fps rational schedule; normalize ->
adapt -> compare returns the motion exactly; retarget, compare and verify (the A1 bars, both hashes) work on the packets; every output is an
immutable publication with a receipt. lampway_rig_skin is the WIP skin and morph half (canon 22 B.10 DRAFT). REAL binary."""

import json
from pathlib import Path

from features_support import run

from test_rig_tools import MIXAMO

ANIM = MIXAMO + '''
ob = mixamo()
ob.animation_data_create(); act = bpy.data.actions.new("swing"); ob.animation_data.action = act
bpy.context.scene.render.fps = 30
for f, a, z in ((1, 0.0, 0.0), (10, 0.7, 0.05)):
    pb = ob.pose.bones["mixamorig:LeftArm"]; pb.rotation_mode = "QUATERNION"
    from mathutils import Quaternion
    pb.rotation_quaternion = Quaternion((1, 0, 0), a); pb.keyframe_insert("rotation_quaternion", frame=f)
    hp = ob.pose.bones["mixamorig:Hips"]; hp.location = (0, 0, z); hp.keyframe_insert("location", frame=f)
call("rig_inspect", armature="mx")
'''


def test_profile_normalize_adapt_compare_round_trip_and_immutable_publication(tmp_path):
    r = run(tmp_path, ANIM + '''
p = call("rig_convert", verb="profile", armature="mx", out="conv/mx.profile.json")
x = call("rig_convert", verb="extract", armature="mx", action="swing", duration="0.3", out="conv/mx.native.json")
n = call("rig_convert", verb="normalize", input="conv/mx.native.json", profile="conv/mx.profile.json", out="conv/mx.canonical.json")
again = call("rig_convert", verb="normalize", input="conv/mx.native.json", profile="conv/mx.profile.json", out="conv/mx.canonical.json")
a = call("rig_convert", verb="adapt", input="conv/mx.canonical.json", profile="conv/mx.profile.json", out="conv/mx.adapted.json")
c = call("rig_convert", verb="compare", input="conv/mx.native.json", target="conv/mx.adapted.json")
clash = call("rig_convert", verb="adapt", input="conv/mx.canonical.json", profile="conv/mx.profile.json", out="conv/mx.native.json")
# the to-blender adapter: the native frame is Blender's REFLECTED across Y (F R F with F = diag(1, -1, 1)), rotation and translation alike
from mathutils import Quaternion as Q, Matrix as M
nat = json.load(open(os.path.join(root, "conv/mx.native.json")))["samples"][-1]["pose"]["mixamorig:LeftForeArm"]
bpy.context.scene.frame_set(10)
W = ob.matrix_world @ ob.pose.bones["mixamorig:LeftForeArm"].matrix
F = M.Diagonal((1, -1, 1))
x_, y_, z_, w_ = nat["rotation"]
refl = max(abs(a - b) for ra, rb in zip(Q((w_, x_, y_, z_)).to_matrix(), F @ W.to_3x3() @ F) for a, b in zip(ra, rb))
tdiff = max(abs(a - b) for a, b in zip(nat["translation"], F @ W.translation))
print("RESULT", json.dumps({"p": p, "x": x, "n": n, "again": again, "a": a, "c": c, "clash": clash, "refl": refl, "tdiff": tdiff}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    prof = json.loads((tmp_path / "conv/mx.profile.json").read_text())
    assert o["p"]["ok"] and prof["schema"] == "titan.animation-profile/1" and len(prof["bones"]) == 23 and prof["bones"][0]["name"] == "mx" and prof["adapter"]["centimeters_per_unit"] == 100, o["p"]
    assert o["x"]["ok"] and o["x"]["samples"] == 10, o["x"]                      # 0/30 .. 9/30 (0.3 s is exact: no terminal extra)
    canon = json.loads((tmp_path / "conv/mx.canonical.json").read_text())
    assert canon["schema"] == "titan.animation/1" and canon["fps"] == [30, 1] and o["n"]["packet_sha256"] == canon["sha256"], o["n"]
    assert o["again"]["ok"] and o["again"]["state"] == "unchanged", o["again"]
    assert o["c"]["ok"] and o["c"]["translation_max"] < 1e-6 and o["c"]["rotation_max_degrees"] < 1e-5, o["c"]
    assert o["clash"]["ok"] is False and "different existing output" in o["clash"]["error"], o["clash"]
    assert o["refl"] < 1e-6 and o["tdiff"] < 1e-6, (o["refl"], o["tdiff"])
    rec = json.loads((tmp_path / "conv/mx.canonical.json.receipt.json").read_text())
    assert rec["verb"] == "normalize" and rec["sha256"]["profile"] and rec["owners"]["animation_canon"], rec


def test_retarget_verify_and_the_refusals(tmp_path):
    r = run(tmp_path, ANIM + '''
call("rig_convert", verb="profile", armature="mx", out="c/p.json")
call("rig_convert", verb="extract", armature="mx", action="swing", duration="0.2", out="c/n.json")
call("rig_convert", verb="normalize", input="c/n.json", profile="c/p.json", out="c/k.json")
prof = json.load(open(os.path.join(root, "c/p.json")))
names = [b["name"] for b in prof["bones"]]
json.dump({"map": {n: n for n in names}, "reference_follow": [], "translation_scales": {n: 1 for n in names}, "anchors": {}}, open(os.path.join(root, "c/rules.json"), "w"))
rt = call("rig_convert", verb="retarget", input="c/k.json", target_profile="c/p.json", rules="c/rules.json", out="c/rt.json")
ok = call("rig_convert", verb="verify", input="c/k.json", target="c/n.json", profile="c/p.json")
native = json.load(open(os.path.join(root, "c/n.json")))
native["samples"][1]["pose"]["mixamorig:LeftHand"]["translation"][0] += 0.002          # 0.2 cm: over the A1 bar of 0.1 cm
json.dump(native, open(os.path.join(root, "c/n_bad.json"), "w"))
bad = call("rig_convert", verb="verify", input="c/k.json", target="c/n_bad.json", profile="c/p.json")
native = json.load(open(os.path.join(root, "c/n.json")))
native["samples"][0]["pose"]["mixamorig:LeftArm"]["scale"] = [1, 1.2, 1]
json.dump(native, open(os.path.join(root, "c/n_shear.json"), "w"))
shear = call("rig_convert", verb="normalize", input="c/n_shear.json", profile="c/p.json", out="c/x.json")
prof["bones"][1]["reference"]["translation"][0] += 1; json.dump(prof, open(os.path.join(root, "c/p_bad.json"), "w"))
tampered = call("rig_convert", verb="normalize", input="c/n.json", profile="c/p_bad.json", out="c/y.json")
mixamo(name="cold")
cold = call("rig_convert", verb="profile", armature="cold", out="c/cold.json")
print("RESULT", json.dumps({"rt": rt, "ok": ok, "bad": bad, "shear": shear, "tampered": tampered, "cold": cold}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["rt"]["ok"] and o["rt"]["compare"]["translation_max"] < 1e-5 and o["rt"]["compare"]["rotation_max_degrees"] < 1e-5, o["rt"]
    assert o["ok"]["ok"] and o["ok"]["verdict"] == "PASS" and o["ok"]["sha256"]["canonical"] and o["ok"]["sha256"]["native"], o["ok"]
    assert o["bad"]["verdict"] == "FAIL" and [x["bone"] for x in o["bad"]["over_bars"]] == ["mixamorig:LeftHand"], o["bad"]
    assert o["shear"]["ok"] is False and "non-uniform" in o["shear"]["error"], o["shear"]
    assert o["tampered"]["ok"] is False and "profile" in o["tampered"]["error"], o["tampered"]
    assert o["cold"]["ok"] is False and "rig_inspect" in o["cold"]["error"], o["cold"]


def test_the_skin_and_morph_half_is_wip_and_says_so(tmp_path):
    r = run(tmp_path, '''
mesh = {"meshes": [{"name": "body", "verts": [[0.02, 0.03, 0.04], [-0.05, 0.07, 0.09], [0.06, -0.02, 0.01]], "faces": [[0, 1, 2]],
                    "loop_uv": [[0, 0], [1, 0], [0, 1]], "materials": ["skin"], "face_mat": [0], "morphs": {"dent": [[0, 0, 0], [0, 0, 0], [0.01, 0, 0]]}}]}
os.makedirs(os.path.join(root, "s"), exist_ok=True)
json.dump(mesh, open(os.path.join(root, "s/native.json"), "w"))
json.dump({"unit_cm": 100, "basis_to_canonical": [[1, 0, 0], [0, -1, 0], [0, 0, 1]]}, open(os.path.join(root, "s/space.json"), "w"))
m = call("rig_skin", verb="mesh_normalize", input="s/native.json", space="s/space.json", out="s/canon_mesh.json")
back = call("rig_skin", verb="mesh_adapt", input="s/canon_mesh.json", space="s/space.json", out="s/back.json")
joints = [{"name": "root", "parent": None, "bind": [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]},
          {"name": "arm", "parent": "root", "bind": [[1, 0, 0, 1], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}]
json.dump(joints, open(os.path.join(root, "s/joints.json"), "w"))
json.dump({"body": [[["root", 1]], [["arm", 1]], [["arm", 0.5], ["root", 0.5]]]}, open(os.path.join(root, "s/weights.json"), "w"))
cap = call("rig_skin", verb="capture", input="s/canon_mesh.json", joints="s/joints.json", weights="s/weights.json", out="s/packet.json")
I = [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]; T = [[1, 0, 0, 10], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]
json.dump({"root": I, "arm": [[1, 0, 0, 11], [0, 1, 0, 0], [0, 0, 1, 0], [0, 0, 0, 1]]}, open(os.path.join(root, "s/pose.json"), "w"))
ev = call("rig_skin", verb="evaluate", input="s/packet.json", pose="s/pose.json", out="s/posed.json")
bad = call("rig_skin", verb="capture", input="s/native.json", joints="s/joints.json", weights="s/weights.json", out="s/x.json")
print("RESULT", json.dumps({"m": m, "back": back, "cap": cap, "ev": ev, "bad": bad}))
''', timeout=300)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    for k in ("m", "back", "cap", "ev"):
        assert o[k]["ok"] and o[k]["wip"] is True and o[k]["status"].startswith("WIP"), (k, o[k])
    canon = json.loads((tmp_path / "s/canon_mesh.json").read_text())
    assert canon["schema"] == "titan.canonical-mesh/1" and canon["meshes"][0]["verts"][0] == [2, -3, 4] and "dent" in canon["meshes"][0]["morphs"], canon
    posed = json.loads((tmp_path / "s/posed.json").read_text())["meshes"][0]["verts"]
    assert posed[0] == [2, -3, 4] and posed[1][0] == -5 + 10 and posed[2][0] == 6 + 5, posed     # P * inverse(B): the arm moved 10 cm
    assert o["bad"]["ok"] is False and o["bad"]["error"].startswith("WIP") and "canonical" in o["bad"]["error"], o["bad"]
