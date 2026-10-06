# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_retarget (specs/canon/rig_tools/rig_retarget.md; canon 19 B.1-B.3, B.5), REAL binary. R04 on armatures: two 2-bone chains whose rests
differ by roll (90 / -30 deg) and length (0.27 / 0.30 m); the target's world rotations equal W_s R_s^-1 R_t every frame and its bone lengths
never change, while copying the source's local keys misses by 55.7 deg. R05 on armatures: a root bone extracted from the pelvis - on the
ground, never tilted, recomposing the pelvis exactly, yaw none or heading."""

import json
from pathlib import Path

import numpy as np

from features_support import run

GOLD = Path(__file__).resolve().parents[2] / "docs" / "canon" / "goldens"
R04 = json.loads((GOLD / "R04_retarget" / "case.json").read_text())
R05 = json.loads((GOLD / "R05_root_motion" / "case.json").read_text())

CHAINS = '''
R04 = json.loads(open(GOLD + "/R04_retarget/case.json").read())
def chain(name, rests, length_a):
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    head, prev = Vector((0, 0, 1.0)), None
    for n, L in (("A", length_a), ("B", 0.25)):
        R = Matrix(rests[n]); e = arm.edit_bones.new(n); e.head = head; e.tail = head + R.col[1] * L
        e.matrix = Matrix.Translation(head) @ R.to_4x4(); e.length = L
        if prev: e.parent = prev
        prev, head = e, head + R.col[1] * L
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob
def rotx(d): return Matrix.Rotation(math.radians(d), 3, "X")
def rotz(d): return Matrix.Rotation(math.radians(d), 3, "Z")
'''


def test_r04_the_target_turns_by_the_source_world_change_and_keeps_its_lengths(tmp_path):
    r = run(tmp_path, f"GOLD = {str(GOLD)!r}\n" + CHAINS + '''
i = R04["input"]
s = chain("s", i["Rs_rest"], i["lengths"]["source_A"]); t = chain("t", i["Rt_rest"], i["lengths"]["target_A"])
s.animation_data_create(); act = bpy.data.actions.new("swing"); s.animation_data.action = act
for k in range(5):
    for n, L in (("A", rotx(15 * k) @ rotz(5 * k)), ("B", rotx(20 * k))):
        pb = s.pose.bones[n]; pb.rotation_mode = "QUATERNION"; pb.rotation_quaternion = L.to_quaternion(); pb.keyframe_insert("rotation_quaternion", frame=k + 1)
call("rig_inspect", armature="s"); call("rig_inspect", armature="t")
r = call("rig_retarget", source="s", target="t", action="swing")
t.animation_data.action = bpy.data.actions.get("swing_rt")
got, lengths = [], []
for k in range(5):
    bpy.context.scene.frame_set(k + 1)
    got.append({n: [list(row) for row in (t.matrix_world @ t.pose.bones[n].matrix).to_3x3()] for n in ("A", "B")})
    a, b = t.pose.bones["A"], t.pose.bones["B"]
    lengths.append((b.head - a.head).length)
# the falsifier (R04's definition): the source's rest-relative rotation applied in the TARGET's own frame, W = R_t (R_s^-1 W_s)
naive = 0.0
for k in range(5):
    bpy.context.scene.frame_set(k + 1)
    Ws = (s.matrix_world @ s.pose.bones["B"].matrix).to_3x3()
    W = Matrix(i["Rt_rest"]["B"]) @ (Matrix(i["Rs_rest"]["B"]).transposed() @ Ws)
    E = Matrix(R04["expected"]["frames"][k]["Wt"]["B"])
    a = W.to_quaternion().rotation_difference(E.to_quaternion()).angle
    naive = max(naive, math.degrees(min(a, 2 * math.pi - a)))
print("RESULT", json.dumps({"r": r, "got": got, "lengths": lengths, "naive": naive}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    assert o["r"]["ok"] and o["r"]["action"] == "swing_rt" and o["r"]["frames"] == [1, 5], o["r"]
    for k, f in enumerate(R04["expected"]["frames"]):
        for n in ("A", "B"):
            assert np.allclose(o["got"][k][n], f["Wt"][n], atol=2e-6), (k, n)
    assert max(o["lengths"]) - min(o["lengths"]) < 1e-6 and abs(o["lengths"][0] - 0.30) < 1e-6, "INV-19.1: no bone length changes"
    assert o["r"]["metrics"]["max_world_angle_error_deg"] < 1e-3 and o["r"]["metrics"]["max_bone_length_change_m"] < 1e-6, o["r"]["metrics"]
    assert abs(o["naive"] - R04["falsifier"]["local_copy_max_error_deg"]) < 0.01, o["naive"]


PELVIS = '''
R05 = json.loads(open(GOLD + "/R05_root_motion/case.json").read())
def rig(name, with_root):
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    p = arm.edit_bones.new("pelvis"); p.head, p.tail = (0, 0, 0.95), (0, 0.1, 0.95)
    sp = arm.edit_bones.new("spine_01"); sp.head, sp.tail, sp.parent = (0, 0, 1.05), (0, 0.1, 1.05), p
    if with_root:
        r = arm.edit_bones.new("root"); r.head, r.tail = (0, 0, 0), (0, 0.1, 0); p.parent = r
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob
'''


def test_r05_a_root_bone_from_the_pelvis_on_the_ground_never_tilted_recomposing_exactly(tmp_path):
    r = run(tmp_path, f"GOLD = {str(GOLD)!r}\n" + PELVIS + '''
s = rig("s", False); t = rig("t", True); n = rig("n", False)
s.animation_data_create(); act = bpy.data.actions.new("walk"); s.animation_data.action = act
for f in R05["expected"]["frames"]:
    pb = s.pose.bones["pelvis"]; pb.rotation_mode = "QUATERNION"; pb.matrix = Matrix(f["pelvis"]); bpy.context.view_layer.update()
    pb.keyframe_insert("rotation_quaternion", frame=f["t"] + 1); pb.keyframe_insert("location", frame=f["t"] + 1)
for o in ("s", "t", "n"): call("rig_inspect", armature=o)
out = {}
for yaw in ("none", "heading"):
    r = call("rig_retarget", source="s", target="t", action="walk", root_motion="root_bone", root_yaw=yaw, name=f"walk_{yaw}")
    t.animation_data.action = bpy.data.actions.get(f"walk_{yaw}")
    rows = []
    for f in R05["expected"]["frames"]:
        bpy.context.scene.frame_set(f["t"] + 1)
        rows.append({"root": [list(x) for x in (t.matrix_world @ t.pose.bones["root"].matrix)], "pelvis": [list(x) for x in (t.matrix_world @ t.pose.bones["pelvis"].matrix)]})
    out[yaw] = {"r": r, "rows": rows}
no_root = call("rig_retarget", source="s", target="n", action="walk", root_motion="root_bone")
print("RESULT", json.dumps({"out": out, "no_root": no_root}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    for yaw in ("none", "heading"):
        res = o["out"][yaw]["r"]
        assert res["ok"] and res["root"]["bone"] == "root" and res["root"]["yaw"] == yaw, res
        assert res["root"]["max_tilt_deg"] < 1e-6 and res["root"]["recompose_error_m"] < 1e-5, res["root"]
        for f, row in zip(R05["expected"]["frames"], o["out"][yaw]["rows"]):
            assert np.allclose(row["root"], f["modes"][yaw]["root"], atol=2e-6), (yaw, f["t"])
            assert np.allclose(row["pelvis"], f["pelvis"], atol=2e-6), (yaw, f["t"])
    assert o["no_root"]["ok"] is False and "root" in o["no_root"]["error"], o["no_root"]
