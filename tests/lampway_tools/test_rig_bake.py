# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_bake (specs/canon/rig_tools/rig_bake.md; canon 19 B.6), REAL binary: a driver's actions become plain keys on the target, written
parent-first from the evaluated world matrices (not by visual keying), each with a per-frame world-error receipt against the driver
(R04 with an identity map: equal to storage precision). The baked action plays with the target's constraints muted and reproduces the
driver; GRT's naming, frame ranges, overwrite, offset and NLA semantics; the driver's previous action restored."""

from features_support import run

RIGS = '''
def chain(name):
    arm = bpy.data.armatures.new(name); ob = link(bpy.data.objects.new(name, arm))
    bpy.context.view_layer.objects.active = ob; bpy.ops.object.mode_set(mode="EDIT")
    a = arm.edit_bones.new("upper"); a.head, a.tail, a.roll = (0, 0, 1.0), (0.3, 0, 1.0), 0.4
    b = arm.edit_bones.new("lower"); b.head, b.tail, b.parent = (0.3, 0, 1.0), (0.55, 0.05, 1.0), a
    c = arm.edit_bones.new("ctrl"); c.head, c.tail, c.use_deform = (0, 0.4, 1.0), (0, 0.5, 1.0), False
    bpy.ops.object.mode_set(mode="OBJECT")
    return ob
def wave(ob, name="wave", frames=10):
    ob.animation_data_create(); act = bpy.data.actions.new(name); ob.animation_data.action = act
    for f in range(1, frames + 1):
        u, l = ob.pose.bones["upper"], ob.pose.bones["lower"]
        u.rotation_quaternion = Quaternion((0.3, 0.8, 0.2), 0.08 * f); l.rotation_quaternion = Quaternion((0, 0, 1), -0.11 * f)
        u.location = (0.0, 0.01 * f, 0.002 * f * f)
        for pb in (u, l):
            pb.keyframe_insert("rotation_quaternion", frame=f); pb.keyframe_insert("location", frame=f)
    return act
from mathutils import Quaternion
def world(ob, f):
    bpy.context.scene.frame_set(f)
    return {pb.name: ob.matrix_world @ pb.matrix for pb in ob.pose.bones}
'''


def test_the_bake_reproduces_the_driver_with_the_constraints_muted(tmp_path):
    r = run(tmp_path, RIGS + '''
drv = chain("drv"); act = wave(drv); prev = bpy.data.actions.new("idle"); drv.animation_data.action = prev
call("rig_inspect", armature="drv")
g = call("rig_game_extract", control="drv", rebind_meshes=False)
call("rig_inspect", armature="drv_game")
b = call("rig_bake", driver="drv", target="drv_game", actions=["wave"])
game = bpy.data.objects["drv_game"]
baked = bpy.data.actions.get("wave_baked")
muted = sorted({c.mute for pb in game.pose.bones for c in pb.constraints})
drv.animation_data.action = act
err = 0.0
for f in range(1, 11):
    a, z = world(drv, f), world(game, f)
    err = max(err, max((a[n].translation - z[n].translation).length for n in z))
tracks = [t.name for t in game.animation_data.nla_tracks] if game.animation_data else []
print("RESULT", json.dumps({"b": b, "muted": muted, "err": err, "tracks": tracks, "baked": bool(baked), "drv_action": prev.name}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    b = o["b"]
    assert b["ok"] and b["verdict"] == "PASS", b
    row = b["actions"][0]
    assert row["source"] == "wave" and row["baked"] == "wave_baked" and row["frames"] == [1, 10] and row["nla_track"] == "wave_baked", row
    assert row["max_world_error"]["m"] < 1e-5 and row["max_world_error"]["deg"] < 0.005, row["max_world_error"]
    assert row["keys"] == 10 * 2 * (3 + 4 + 3), row["keys"]                         # 10 frames, 2 bones, location + quaternion + scale
    assert o["muted"] == [True] and o["baked"] and o["tracks"] == ["wave_baked"], o
    assert o["err"] < 1e-5, "the baked keys play the driver's motion with the constraints muted"
    assert b["driver_action_restored"] == o["drv_action"], b


def test_bake_naming_ranges_offset_overwrite_and_refusals(tmp_path):
    r = run(tmp_path, RIGS + '''
drv = chain("drv"); act = wave(drv)
call("rig_inspect", armature="drv"); call("rig_game_extract", control="drv", rebind_meshes=False); call("rig_inspect", armature="drv_game")
part = call("rig_bake", driver="drv", target="drv_game", actions=["wave"], frames=[3, 8], offset_to_one=True, name={"mode": "prefix", "value": "B_"},
            push_to_nla=False, channels=["rotation"])
kf = sorted({k.co[0] for fc in bpy.data.actions["B_wave"].layers[0].strips[0].channelbags[0].fcurves for k in fc.keyframe_points})
paths = sorted({fc.data_path.rsplit(".", 1)[1] for fc in bpy.data.actions["B_wave"].layers[0].strips[0].channelbags[0].fcurves})
taken = call("rig_bake", driver="drv", target="drv_game", actions=["wave"], name={"mode": "prefix", "value": "B_"}, push_to_nla=False)
over = call("rig_bake", driver="drv", target="drv_game", actions=["wave"], name={"mode": "prefix", "value": "B_"}, push_to_nla=False, overwrite=True)
same = call("rig_bake", driver="drv", target="drv_game", actions=["wave"], name={"mode": "replace", "value": "x", "to": "y"}, overwrite=True)
other = bpy.data.actions.new("objonly")                                  # an action with no bone channel
nobone = call("rig_bake", driver="drv", target="drv_game", actions=["objonly"])
empty = call("rig_bake", driver="drv", target="drv_game", actions=["wave"], frames=[5, 4])
locs = call("rig_bake", driver="drv", target="drv_game", actions=["wave"], name={"mode": "suffix", "value": "_loc"}, channels=["location"])
print("RESULT", json.dumps({"part": part, "kf": kf, "paths": paths, "taken": taken, "over": over, "same": same, "nobone": nobone, "empty": empty, "locs": locs,
                            "loc_left": "wave_loc" in bpy.data.actions, "count": sum(1 for a in bpy.data.actions if a.name.startswith("B_wave"))}))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    o = r.results[0]
    p = o["part"]["actions"][0]
    assert p["baked"] == "B_wave" and p["frames"] == [3, 8] and p["offset"] == -2 and p["nla_track"] is None, p
    assert o["kf"] == [1.0, 2.0, 3.0, 4.0, 5.0, 6.0] and o["paths"] == ["rotation_quaternion"], (o["kf"], o["paths"])
    assert o["taken"]["ok"] is False and "B_wave" in o["taken"]["error"] and "overwrite" in o["taken"]["error"], o["taken"]
    assert o["over"]["ok"] and o["over"]["actions"][0]["overwrote"] is True and o["count"] == 1, (o["over"], o["count"])
    assert o["same"]["ok"] is False and "its source" in o["same"]["error"], o["same"]
    assert o["nobone"]["ok"] is False and "drives no bone" in o["nobone"]["error"], o["nobone"]
    assert o["empty"]["ok"] is False and "empty" in o["empty"]["error"], o["empty"]
    # location keys alone cannot place the child of a rotating bone: the bake fails, measured, and leaves no partial action
    lo = o["locs"]
    assert lo["ok"] and lo["verdict"] == "FAIL" and lo["actions"][0]["status"] == "failed" and lo["actions"][0]["max_world_error"]["m"] > 1e-3, lo
    assert o["loc_left"] is False
