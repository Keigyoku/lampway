# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""clip_classify (specs/mrmak/08-clip-classify.md) in the REAL binary: the Blender sampling layer feeds the translated pure layer. The rig is six bones pointing along +Y with roll 0, so a pose bone's local
axes are the world axes and a keyed ``location`` is a known world displacement: the features can be written down by hand."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_CC = '''
H = 1.8
def rig(name="rig", scale=1.0):
    arm = bpy.data.armatures.new(name)
    ob = bpy.data.objects.new(name, arm); link(ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    for bn, (x, z) in {"pelvis": (0, 0.95), "head": (0, 1.7), "hand_l": (-0.6, 1.3), "hand_r": (0.6, 1.3), "foot_l": (-0.12, 0.05), "foot_r": (0.12, 0.05)}.items():
        eb = arm.edit_bones.new(bn); eb.head = (x, 0, z); eb.tail = (x, 0.1, z); eb.roll = 0
    bpy.ops.object.mode_set(mode="OBJECT")
    ob.scale = (scale, scale, scale)
    bpy.context.view_layer.update()
    return ob

def act(ob, name, keys, bone="pelvis", path="location"):
    """keys: [(frame, value3)] on one pose bone; a new action assigned to the armature."""
    ad = ob.animation_data or ob.animation_data_create()
    a = bpy.data.actions.new(name); ad.action = a
    pb = ob.pose.bones[bone]
    rest = tuple(getattr(pb, path))
    for f, v in keys:
        setattr(pb, path, v); pb.keyframe_insert(data_path=path, frame=f)
    setattr(pb, path, rest)                                   # the pose bone keeps no leftover value: another action must not inherit it
    ad.action = None
    return a

def walk(ob, name="walk", d=1.08, frames=37):
    return act(ob, name, [(1, (0, 0, 0)), (frames, (0, d, 0))])
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_CC + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_blender_sampling_matches_a_hand_computed_walk(tmp_path):
    out = one(go(tmp_path, '''
ob = rig(); walk(ob)
res = call("clip_classify", armature="rig", action="walk", figure_height_m=H, fps=24)
c = res["clips"][0]
print("RESULT", json.dumps({"ok": res["ok"], "f": c["features"], "primary": c["classification"]["primary"], "src": res["figure_height_source"], "name": c["name"], "loop": c["loop"]}))
'''))
    f = out["f"]
    assert out["ok"] and out["src"] == "given"
    assert abs(f["duration_s"] - 1.5) < 1e-4 and abs(f["travel"] - 0.6) < 1e-4 and abs(f["speed"] - 0.4) < 1e-4 and abs(f["rise"]) < 1e-6, f
    assert out["primary"] == "walk" and "speed 0.400" in out["name"]["measured"] and out["name"]["inferred"] is False
    assert out["loop"]["loop"] is False                                                   # it ends 1.08 m from where it started


def test_seconds_not_frames_the_same_keys_at_another_fps_change_the_speed_by_the_fps_ratio(tmp_path):
    out = one(go(tmp_path, '''
ob = rig(); walk(ob)
a = call("clip_classify", armature="rig", action="walk", figure_height_m=H, fps=24)["clips"][0]["features"]
b = call("clip_classify", armature="rig", action="walk", figure_height_m=H, fps=30)["clips"][0]["features"]
print("RESULT", json.dumps({"a": a, "b": b}))
'''))
    assert abs(out["b"]["speed"] / out["a"]["speed"] - 30 / 24) < 1e-6 and abs(out["a"]["duration_s"] / out["b"]["duration_s"] - 30 / 24) < 1e-6
    assert abs(out["a"]["travel"] - out["b"]["travel"]) < 1e-9                              # the distance does not depend on the rate; the frame count as the duration would make the speeds equal


def test_the_same_rig_scaled_2x_classifies_identically(tmp_path):
    out = one(go(tmp_path, '''
ob = rig(); walk(ob)
a = call("clip_classify", armature="rig", action="walk", figure_height_m=H, fps=24)["clips"][0]
ob2 = rig("rig2", scale=2.0)
act(ob2, "walk2", [(1, (0, 0, 0)), (37, (0, 1.08, 0))])          # local units: the object's 2x scale doubles the world distance
b = call("clip_classify", armature="rig2", action="walk2", figure_height_m=2 * H, fps=24)["clips"][0]
print("RESULT", json.dumps({"a": a["features"], "b": b["features"], "pa": a["classification"]["primary"], "pb": b["classification"]["primary"]}))
'''))
    assert out["pa"] == out["pb"] == "walk"
    for k in ("travel", "speed", "rise", "hand_range", "foot_range"):
        assert abs(out["a"][k] - out["b"][k]) < 1e-4, (k, out["a"], out["b"])


def test_blenders_z_up_becomes_the_pure_layers_y_up_so_a_hip_that_rises_in_z_is_rise_not_travel(tmp_path):
    out = one(go(tmp_path, '''
ob = rig()
act(ob, "jump", [(1, (0, 0, 0)), (13, (0, 0, 0.9)), (25, (0, 0, 0))])
res = call("clip_classify", armature="rig", action="jump", figure_height_m=H, fps=24)
print("RESULT", json.dumps({"f": res["clips"][0]["features"], "labels": res["clips"][0]["classification"]["labels"], "loop": res["clips"][0]["loop"]}))
'''))
    f = out["f"]
    assert abs(f["rise"] - 0.5) < 1e-4 and f["travel"] < 1e-6, f
    assert "jump" in out["labels"] and out["loop"]["loop"] is True                       # the pose returns: the loop is decided from the pose, not from travel


def test_the_loop_is_decided_from_the_pose_not_from_travel_and_both_limits_are_reported(tmp_path):
    out = one(go(tmp_path, '''
ob = rig()
act(ob, "wander", [(1, (0, 0, 0)), (13, (0, 0.2178, 0)), (25, (0, 0, 0))])      # travels 0.121 H and comes back
res = call("clip_classify", armature="rig", figure_height_m=H, fps=24)
print("RESULT", json.dumps({c["action"]: c for c in res["clips"]}))
'''))
    w = out["wander"]
    assert abs(w["features"]["travel"] - 0.121) < 1e-3 and w["loop"]["loop"] is True
    assert w["loop"]["loop_at_anim_loop_export_limit"] is True and w["loop"]["anim_loop_export_limit_deg"] == 1.0


def test_a_clip_whose_last_pose_differs_does_not_loop_and_a_rotation_beyond_the_limit_is_measured(tmp_path):
    out = one(go(tmp_path, '''
ob = rig()
act(ob, "turn", [(1, (1, 0, 0, 0)), (25, (math.cos(math.radians(2)), 0, 0, math.sin(math.radians(2))))], bone="head", path="rotation_quaternion")
res = call("clip_classify", armature="rig", action="turn", figure_height_m=H, fps=24)
print("RESULT", json.dumps(res["clips"][0]["loop"]))
'''))
    assert abs(out["pose_return"] - 4.0) < 1e-3 and out["loop"] is False                # a quaternion half-angle of 2 deg is a 4 deg rotation


def test_a_rig_that_scales_joints_is_listed_first_and_the_tripwire_names_it(tmp_path):
    out = one(go(tmp_path, '''
ob = rig()
walk(ob, "a_clean")
act(ob, "z_scaled", [(1, (1, 1, 1)), (25, (1.2, 1, 1))], bone="hand_l", path="scale")
res = call("clip_classify", armature="rig", figure_height_m=H, fps=24)
print("RESULT", json.dumps({"order": [c["action"] for c in res["clips"]], "trip": res["scale_tripwire"]}))
'''))
    assert out["order"] == ["z_scaled", "a_clean"] and out["trip"] == ["z_scaled"]


def test_an_agent_cannot_rename_props_are_written_and_the_state_is_restored(tmp_path):
    out = one(go(tmp_path, '''
ob = rig(); walk(ob, "Armature|Action.003")
sc = bpy.context.scene; sc.frame_set(7)
before = (sc.frame_current, ob.animation_data.action if ob.animation_data else None)
refused = call("clip_classify", armature="rig", action="Armature|Action.003", figure_height_m=H, fps=24, apply="rename")
ok = call("clip_classify", armature="rig", action="Armature|Action.003", figure_height_m=H, fps=24, apply="props")
a = bpy.data.actions["Armature|Action.003"]
print("RESULT", json.dumps({"refused": refused, "props": {k: a[k] for k in a.keys() if k.startswith("lw_")}, "frame": sc.frame_current, "action": ob.animation_data.action is None,
                            "names": [x.name for x in bpy.data.actions], "pos": [round(c, 6) for c in ob.pose.bones["pelvis"].location]}))
'''))
    assert out["refused"]["ok"] is False and "user's click" in out["refused"]["error"] and out["names"] == ["Armature|Action.003"]
    assert out["props"]["lw_clip_primary"] == "walk" and out["props"]["lw_source_name"] == "Armature|Action.003" and out["frame"] == 7 and out["action"] is True


def test_the_users_apply_renames_and_keeps_the_source_name(tmp_path):
    out = one(go(tmp_path, '''
from mixar.modules.lampway_tools.features import clip_classify as CC
ob = rig(); walk(ob, "Armature|Action.003")
res = CC.classify_actions("rig", "Armature|Action.003", 24, 25, None, H, "default", "rename", {"Armature|Action.003": "walk-forward"}, by="user")
print("RESULT", json.dumps({"names": [a.name for a in bpy.data.actions], "src": bpy.data.actions[0].get("lw_source_name"), "renamed": res["clips"][0].get("renamed_to")}))
'''))
    assert out["names"] == ["walk-forward"] and out["src"] == "Armature|Action.003" and out["renamed"] == "walk-forward"


def test_the_refusals_name_their_fix(tmp_path):
    out = one(go(tmp_path, '''
ob = rig(); walk(ob)
ob.data.bones  # keep
bpy.context.view_layer.objects.active = ob
bpy.ops.object.mode_set(mode="EDIT"); ob.data.edit_bones.remove(ob.data.edit_bones["hand_l"]); bpy.ops.object.mode_set(mode="OBJECT")
miss = call("clip_classify", armature="rig", action="walk", figure_height_m=H)
ob2 = rig("rig2"); walk(ob2, "w2")
few = call("clip_classify", armature="rig2", action="w2", samples=3, figure_height_m=H)
neg = call("clip_classify", armature="rig2", action="w2", figure_height_m=-1)
act(ob2, "one_key", [(1, (0, 0, 0))])
one_key = call("clip_classify", armature="rig2", action="one_key", figure_height_m=H)
unk = call("clip_classify", armature="rig2", action="w2", figure_height_m=H, thresholds='{"warp": 1}')
print("RESULT", json.dumps({"miss": miss, "few": few, "neg": neg, "one": one_key, "unk": unk}))
'''))
    assert "landmark hand.l is not a bone of rig: pass landmarks to map it" in out["miss"]["error"]
    assert "samples is 8..120" in out["few"]["error"] and "figure_height_m must be a finite positive" in out["neg"]["error"]
    assert "fewer than two keys" in out["one"]["error"] and "unknown threshold" in out["unk"]["error"]
