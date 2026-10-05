# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""animation_retarget (resources/anim_retarget.md): bake an animation from one skeleton onto another with the rest pose compensated, measured. In the real binary on synthetic rigs."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

RIGS = r'''
def humanoid(name, arms_down, loc=(0, 0, 0)):
    """UE-named humanoid: pelvis, spine_01, head, both arms (upperarm, lowerarm, hand) and both legs (thigh, calf, foot). arms_down: A-pose (45 degrees down) or T-pose (horizontal)."""
    d = Vector((0, 0, -1)) if False else None
    bones = [("pelvis", (0, 0, 1.0), (0, 0, 1.2), None), ("spine_01", (0, 0, 1.2), (0, 0, 1.5), "pelvis"), ("head", (0, 0, 1.5), (0, 0, 1.75), "spine_01")]
    for side, sx in (("l", 1), ("r", -1)):
        sh = (0.1 * sx, 0, 1.45)
        if arms_down:
            u = (sh[0] + 0.2 * sx * 0.7071, 0, sh[2] - 0.2 * 0.7071); l = (u[0] + 0.2 * sx * 0.7071, 0, u[2] - 0.2 * 0.7071); h = (l[0] + 0.1 * sx * 0.7071, 0, l[2] - 0.1 * 0.7071)
        else:
            u = (sh[0] + 0.2 * sx, 0, sh[2]); l = (u[0] + 0.2 * sx, 0, u[2]); h = (l[0] + 0.1 * sx, 0, l[2])
        bones += [(f"upperarm_{side}", sh, u, "spine_01"), (f"lowerarm_{side}", u, l, f"upperarm_{side}"), (f"hand_{side}", l, h, f"lowerarm_{side}")]
        hip = (0.08 * sx, 0, 1.0)
        bones += [(f"thigh_{side}", hip, (hip[0], 0, 0.55), "pelvis"), (f"calf_{side}", (hip[0], 0, 0.55), (hip[0], 0, 0.1), f"thigh_{side}"), (f"foot_{side}", (hip[0], 0, 0.1), (hip[0], -0.15, 0.0), f"calf_{side}")]
    ob = armature(name, bones=tuple(bones)); ob.location = loc
    return ob

def key(ob, bone, frame, euler=None, loc=None):
    pb = ob.pose.bones[bone]
    if euler is not None:
        pb.rotation_mode = "XYZ"; pb.rotation_euler = [math.radians(a) for a in euler]; pb.keyframe_insert("rotation_euler", frame=frame)
    if loc is not None:
        pb.location = loc; pb.keyframe_insert("location", frame=frame)

def animate_source(ob, name="walk"):
    ob.animation_data_create(); ob.animation_data.action = bpy.data.actions.new(name)
    key(ob, "upperarm_l", 1, euler=(0, 0, 0)); key(ob, "upperarm_l", 10, euler=(60, 0, 0))
    key(ob, "thigh_r", 1, euler=(0, 0, 0)); key(ob, "thigh_r", 10, euler=(0, 35, 0))
    key(ob, "pelvis", 1, loc=(0, 0, 0)); key(ob, "pelvis", 10, loc=(0.2, 0.9, 0.1))
    ob.animation_data.action = ob.animation_data.action
    bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, 10
src = humanoid("src", True); tgt = humanoid("tgt", False, loc=(3, 0, 0))
animate_source(src)
def world_dir(ob, bone, frame):
    bpy.context.scene.frame_set(frame); pb = ob.pose.bones[bone]
    return (ob.matrix_world.to_3x3() @ (pb.tail - pb.head)).normalized()
'''


def run(body, **kw):
    return run_script(PRE + RIGS + body, timeout=600, **kw)


def test_the_rest_pose_is_compensated_so_the_target_moves_by_the_sources_world_rotation_and_a_plain_copy_rotation_does_not():
    r = run('''
out = api.animation_retarget("src", "tgt", name="walk_rt")
# the independent check: the world rotation the source bone went through, applied to the target's own rest direction
bpy.context.scene.frame_set(1); rest_s = world_dir(src, "upperarm_l", 1); rest_t = world_dir(tgt, "upperarm_l", 1)
s10 = world_dir(src, "upperarm_l", 10)
D = rest_s.rotation_difference(s10)
expected = D @ rest_t
got = world_dir(tgt, "upperarm_l", 10)
err_matrix = math.degrees(expected.angle(got))
tgt.animation_data.action = None
for pb in tgt.pose.bones: pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
bpy.context.view_layer.update()
con = api.animation_retarget("src", "tgt", method="constraints", name="walk_con")
res({"out": out, "err_matrix": err_matrix, "con": con})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["out"]["ok"] is True and d["out"]["action"].startswith("walk_rt") and d["out"]["frames"] == [1, 10]
    assert d["out"]["metrics"]["max_world_angle_error_deg"] < 0.5 and d["err_matrix"] < 0.5, d
    assert d["con"]["ok"] is True and d["con"]["metrics"]["max_world_angle_error_deg"] > 5.0           # the falsifier: the bridge's same-rest-pose limit


def test_labels_pair_the_bones_by_name_and_the_dry_run_returns_the_mapping_without_creating_an_action():
    r = run('''
before = len(bpy.data.actions)
out = api.animation_retarget("src", "tgt", dry_run=True)
res({"out": out, "same": before == len(bpy.data.actions)})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["same"] and d["out"]["ok"] is True and d["out"]["unmapped_required"] == []
    assert {"source": "upperarm_l", "target": "upperarm_l"} == {k: m[k] for m in d["out"]["mapping"] if m["source"] == "upperarm_l" for k in ("source", "target")}
    assert all(m["by"] in ("exact", "label") for m in d["out"]["mapping"])


def test_the_root_follows_the_source_scaled_and_in_place_zeroes_its_horizontal_travel():
    r = run('''
keep = api.animation_retarget("src", "tgt", name="keep", scale=2.0)
bpy.context.scene.frame_set(1); k1 = tuple(tgt.pose.bones["pelvis"].head); bpy.context.scene.frame_set(10); k10 = tuple(tgt.pose.bones["pelvis"].head)
tgt.animation_data.action = None
for pb in tgt.pose.bones: pb.rotation_quaternion = (1, 0, 0, 0); pb.location = (0, 0, 0)
inp = api.animation_retarget("src", "tgt", name="inplace", scale=2.0, root_motion="in_place")
bpy.context.scene.frame_set(1); i1 = tuple(tgt.pose.bones["pelvis"].head); bpy.context.scene.frame_set(10); i10 = tuple(tgt.pose.bones["pelvis"].head)
bpy.context.scene.frame_set(1); s1 = tuple(src.matrix_world @ src.pose.bones["pelvis"].head); bpy.context.scene.frame_set(10); s10 = tuple(src.matrix_world @ src.pose.bones["pelvis"].head)
tw = tgt.matrix_world.to_3x3()
res({"keep": [k1, k10], "inplace": [i1, i10], "src": [s1, s10], "ok": keep["ok"] and inp["ok"], "root_scale": keep["root_scale"]})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["ok"] and d["root_scale"] == 2.0
    (k1, k10), (i1, i10), (s1, s10) = d["keep"], d["inplace"], d["src"]
    sd = [b - a for a, b in zip(s1, s10)]                                                      # the source pelvis's WORLD travel (the keyed values are in the bone's own axes)
    assert max(abs(sd[i]) for i in range(3)) > 0.5
    assert all(abs((k10[i] - k1[i]) - 2.0 * sd[i]) < 1e-4 for i in range(3))                   # keep: the source's travel x scale 2
    assert abs(i10[0] - i1[0]) < 1e-6 and abs(i10[1] - i1[1]) < 1e-6 and abs((i10[2] - i1[2]) - 2.0 * sd[2]) < 1e-4       # in place: horizontal travel is zero, the height stays


def test_refusals_no_action_missing_required_bones_bad_scale_and_a_file_outside_the_project():
    r = run('''
out = {}
bare = humanoid("bare", True, loc=(6, 0, 0))
out["noaction"] = api.animation_retarget("bare", "tgt")
armature("tiny", bones=(("pelvis", (0, 0, 0), (0, 0, 1), None),)).location = (9, 0, 0)
out["missing"] = api.animation_retarget("src", "tiny")
out["scale"] = api.animation_retarget("src", "tgt", scale=0)
out["outside"] = api.animation_retarget("/etc/hostname", "tgt")
res(out)
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert "has no animation: pass action= or import a clip" in d["noaction"]["error"]
    assert d["missing"]["ok"] is False and "target tiny lacks" in d["missing"]["error"] and d["missing"]["unmapped_required"]
    assert "scale must be between 0.01 and 100" in d["scale"]["error"]
    assert "is outside the project root" in d["outside"]["error"]


def test_a_second_run_makes_a_second_action_with_identical_keys_and_never_overwrites_the_first():
    r = run('''
def poses(action_name):
    tgt.animation_data.action = bpy.data.actions[action_name]; out = []
    for f in range(1, 11):
        bpy.context.scene.frame_set(f); out.append([[round(x, 5) for x in (tgt.matrix_world @ pb.matrix).to_quaternion()] + [round(x, 5) for x in pb.head] for pb in tgt.pose.bones])
    return out
a = api.animation_retarget("src", "tgt", name="twice")
b = api.animation_retarget("src", "tgt", name="twice")
acts = [x.name for x in bpy.data.actions if x.name.startswith("twice")]
res({"a": a["action"], "b": b["action"], "acts": acts, "same": poses(a["action"]) == poses(b["action"])})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["a"] != d["b"] and len(d["acts"]) == 2 and d["same"] is True


def test_stretch_on_a_rigidly_bound_plate_is_one_and_the_retarget_json_and_preset_are_written():
    r = run('''
plate = tube("plate", r=0.05, z0=1.46, z1=1.7, seg=8, rings=3); weights(plate, tgt, lambda c: {"spine_01": 1.0})
soft = tube("soft", r=0.05, z0=0.2, z1=1.0, seg=8, rings=6, loc=(-0.08, 0, 0)); weights(soft, tgt, lambda c: {"pelvis": max(0.0, min(1.0, (0.8 - c.z) / 0.4)), "thigh_r": max(0.0, min(1.0, (c.z - 0.4) / 0.4))})
out = api.animation_retarget("src", "tgt", name="rig_check", check_objects=["plate", "soft"], sample_frames=4)
files = sorted(os.listdir(os.path.join(root, "anim"))) if os.path.isdir(os.path.join(root, "anim")) else []
res({"out": out, "files": files, "rt": json.load(open(out["retarget_json"]))})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert abs(d["out"]["metrics"]["max_edge_stretch"]["plate"] - 1.0) < 1e-3
    assert d["out"]["metrics"]["max_edge_stretch"]["soft"] > 1.01                                 # the falsifier: a plate blended across the moving thigh stretches
    assert d["rt"]["mapping"] and d["rt"]["rest_sha256"]["source"] and d["rt"]["rest_sha256"]["target"]


def test_a_clip_file_is_imported_in_a_hidden_collection_baked_and_removed_afterwards():
    r = run('''
os.makedirs(os.path.join(root, "clips"), exist_ok=True)
for o in bpy.context.selected_objects: o.select_set(False)
src.select_set(True); bpy.context.view_layer.objects.active = src
bpy.ops.export_scene.fbx(filepath=os.path.join(root, "clips", "walk.fbx"), use_selection=True, object_types={"ARMATURE"}, bake_anim=True, add_leaf_bones=False)
n_before = len(bpy.data.objects); cols = {c.name for c in bpy.data.collections}
out = api.animation_retarget("clips/walk.fbx", "tgt", name="from_file")
res({"out": out, "objects_same": len(bpy.data.objects) == n_before, "collections_same": {c.name for c in bpy.data.collections} == cols})
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[-1]
    assert d["out"]["ok"] is True, d["out"]
    assert d["objects_same"] and d["collections_same"] and len(d["out"]["mapping"]) >= 13 and d["out"]["metrics"]["max_world_angle_error_deg"] < 0.5
