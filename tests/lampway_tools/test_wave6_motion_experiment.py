# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""motion_experiment (specs/wiki/motion_experiment.md) in the real binary: variant A is keyed from the brief's explicit start, contact and end poses with the default
interpolation; imported variants B and C must share A's start and end poses (checked, not assumed); each variant is measured and tabulated."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

RIG = '''
rig = armature(bones=(("root", (0, 0, 0), (0, 0, 0.5)), ("upper", (0, 0, 0.5), (0, 0, 1.0)), ("lower", (0, 0, 1.0), (0, 0, 1.4))))
bpy.context.scene.render.fps = 24
START = {"bones": [{"bone": "upper", "rotate": [0, 0, 0]}, {"bone": "lower", "rotate": [0, 0, 0]}]}
END = {"bones": [{"bone": "upper", "rotate": [45, 0, 0]}, {"bone": "lower", "rotate": [30, 0, 0]}]}
BRIEF = {"duration_s": 2.0, "start": START, "end": END, "action": "vault the low wall", "contact": {"time_s": 1.0, "landmark": "wall top"}, "preserve": ["grip"]}

def keyed(name, keys):
    """An action on the rig from [(frame, {bone: [rx, ry, rz]})], then unassigned (an imported variant)."""
    for f, pose in keys:
        for b, r in pose.items():
            pb = rig.pose.bones[b]; pb.rotation_mode = "XYZ"; pb.rotation_euler = [math.radians(x) for x in r]
            pb.keyframe_insert("rotation_euler", frame=f)
    act = rig.animation_data.action; act.name = name
    rig.animation_data.action = None
    for pb in rig.pose.bones:
        pb.rotation_euler = (0, 0, 0)
    return act

def rot_at(act_name, frame):
    from mixar.modules.lampway_tools.features import clip_classify as CC
    CC._set_action(rig, bpy.data.actions[act_name])
    bpy.context.scene.frame_set(frame)
    out = {b: [round(math.degrees(a), 4) for a in rig.pose.bones[b].matrix_basis.to_euler("XYZ")] for b in ("upper", "lower")}
    rig.animation_data.action = None
    return out
'''


def test_a_variant_hits_start_and_end_poses_exactly(tmp_path):
    d = one(go(tmp_path, RIG + '''
res = call("motion_experiment", brief=BRIEF, armature="rig", variants={"A": "keyed"})
a = res["A"]["action"]
print("RESULT", json.dumps({"res": res, "first": rot_at(a, 1), "last": rot_at(a, 49), "markers": [(m.name, m.frame) for m in bpy.data.actions[a].pose_markers]}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert d["first"] == {"upper": [0.0, 0.0, 0.0], "lower": [0.0, 0.0, 0.0]} and d["last"] == {"upper": [45.0, 0.0, 0.0], "lower": [30.0, 0.0, 0.0]}
    assert res["A"]["audit"]["frames"] == 49 and res["A"]["audit"]["start_error_deg"] == 0 and res["A"]["audit"]["end_error_deg"] == 0
    assert d["markers"] == [["contact: wall top", 25]] and res["B"] is None and res["C"] is None


def test_missing_end_pose_refused_and_foot_contact_needs_a_landmark(tmp_path):
    d = one(go(tmp_path, RIG + '''
noend = call("motion_experiment", brief=dict(BRIEF, end=None), armature="rig", variants={"A": "keyed"})
foot = call("motion_experiment", brief=dict(BRIEF, contact={"time_s": 1.0}, preserve=["foot_contact"]), armature="rig", variants={"A": "keyed"})
long = call("motion_experiment", brief=dict(BRIEF, duration_s=12), armature="rig", variants={"A": "keyed"})
print("RESULT", json.dumps({"noend": noend, "foot": foot, "long": long}))
'''))
    assert d["noend"]["ok"] is False and "explicit start and end poses are required" in d["noend"]["error"]
    assert d["foot"]["ok"] is False and "contact landmark" in d["foot"]["error"]
    assert d["long"]["ok"] is False and "0.5..10" in d["long"]["error"]


def test_variants_with_different_end_pose_refused_and_a_matching_one_is_compared(tmp_path):
    d = one(go(tmp_path, RIG + '''
keyed("B_off", [(1, {"upper": [0, 0, 0], "lower": [0, 0, 0]}), (30, {"upper": [60, 0, 0], "lower": [10, 0, 0]}), (49, {"upper": [50, 0, 0], "lower": [30, 0, 0]})])
keyed("B_ok", [(1, {"upper": [0, 0, 0], "lower": [0, 0, 0]}), (20, {"upper": [70, 0, 0], "lower": [0, 0, 0]}), (49, {"upper": [45, 0, 0], "lower": [30, 0, 0]})])
off = call("motion_experiment", brief=BRIEF, armature="rig", variants={"A": "keyed", "B": "B_off"})
ok = call("motion_experiment", brief=BRIEF, armature="rig", variants={"A": "keyed", "B": "B_ok"})
print("RESULT", json.dumps({"off": off, "ok": ok}))
'''))
    assert d["off"]["ok"] is False and "B" in d["off"]["error"] and "end" in d["off"]["error"] and "upper" in d["off"]["error"]
    ok = d["ok"]
    assert ok["ok"] and ok["B"]["action"] == "B_ok" and ok["B"]["audit"]["end_error_deg"] < 0.5
    table = {r["metric"]: r for r in ok["comparison"]}
    assert set(table) >= {"duration_s", "max_angular_speed_dps", "max_angular_accel_dps2"} and table["max_angular_speed_dps"]["B"] > table["max_angular_speed_dps"]["A"]
    assert ok["grade"]["by"] and ok["grade"]["smoothest"] in ("A", "B")
    assert ok["seed"] == "not_exposed"


def test_an_unknown_variant_action_or_armature_is_refused(tmp_path):
    d = one(go(tmp_path, RIG + '''
nob = call("motion_experiment", brief=BRIEF, armature="rig", variants={"A": "keyed", "B": "nope"})
noarm = call("motion_experiment", brief=BRIEF, armature="ghost", variants={"A": "keyed"})
badbone = call("motion_experiment", brief=dict(BRIEF, end={"bones": [{"bone": "tail", "rotate": [1, 0, 0]}]}), armature="rig", variants={"A": "keyed"})
print("RESULT", json.dumps({"nob": nob, "noarm": noarm, "badbone": badbone}))
'''))
    assert d["nob"]["ok"] is False and "nope" in d["nob"]["error"]
    assert d["noarm"]["ok"] is False and "ghost" in d["noarm"]["error"]
    assert d["badbone"]["ok"] is False and "tail" in d["badbone"]["error"]
