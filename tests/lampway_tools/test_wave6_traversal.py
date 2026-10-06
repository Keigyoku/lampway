# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""traversal_check (specs/wiki/traversal_check.md) in the real binary: a player capsule swept along a route over a blockout reports ok, blocked (a step above max_step
or a wall), too_steep, low_ceiling and gap (wider than the jump), plus sightlines. Read-only; the project's capsule values are required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

COURSE = '''
coll = bpy.data.collections.new("course"); bpy.context.scene.collection.children.link(coll)
def block(name, center, size):
    ob = boxes(name, [(center, size)])
    bpy.context.scene.collection.objects.unlink(ob); coll.objects.link(ob)
    return ob
PLAYER = {"capsule_radius_m": 0.3, "capsule_height_m": 1.8, "max_step_m": 0.3, "max_slope_deg": 45, "jump_height_m": 1.0, "jump_gap_m": 2.0}
def states(res):
    return [s["state"] for s in res["steps"]]
'''


def test_flat_route_passes(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("floor", (5, 0, -0.05), (12, 4, 0.1))
res = call("traversal_check", route=[[0, 0, 0], [3, 0, 0], [6, 0, 0], [9, 0, 0]], collection="course", player=PLAYER)
print("RESULT", json.dumps(res))
'''))
    assert d["ok"] and [s["state"] for s in d["steps"]] == ["ok"] * 4 and d["blocked_count"] == 0


def test_a_step_above_max_step_blocks_and_one_below_does_not(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("floor", (5, 0, -0.05), (12, 4, 0.1))
block("step", (5, 0, 0.25), (2, 4, 0.5))
high = call("traversal_check", route=[[0, 0, 0], [3, 0, 0], [7, 0, 0]], collection="course", player=PLAYER)
low = call("traversal_check", route=[[0, 0, 0], [3, 0, 0], [7, 0, 0]], collection="course", player=dict(PLAYER, max_step_m=0.6))
print("RESULT", json.dumps({"high": states(high), "low": states(low), "detail": high["steps"][2]["detail"]}))
'''))
    assert d["high"] == ["ok", "ok", "blocked"] and "step" in d["detail"] and d["low"] == ["ok", "ok", "ok"]


def test_door_lower_than_capsule_is_low_ceiling(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("floor", (5, 0, -0.05), (12, 4, 0.1))
block("lintel", (5, 0, 1.75), (0.4, 4, 0.5))                                        # its underside at 1.5 m, the capsule is 1.8 m
res = call("traversal_check", route=[[0, 0, 0], [3, 0, 0], [7, 0, 0]], collection="course", player=PLAYER)
tall = call("traversal_check", route=[[0, 0, 0], [3, 0, 0], [7, 0, 0]], collection="course", player=dict(PLAYER, capsule_height_m=1.4))
print("RESULT", json.dumps({"res": states(res), "tall": states(tall)}))
'''))
    assert d["res"] == ["ok", "ok", "low_ceiling"] and d["tall"] == ["ok", "ok", "ok"]


def test_gap_wider_than_jump_is_gap_and_half_the_gap_passes(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("near", (1.5, 0, -0.05), (3, 4, 0.1))
block("far", (8.0, 0, -0.05), (4, 4, 0.1))                                           # ground from 0..3 and 6..10: a 3 m gap
wide = call("traversal_check", route=[[0, 0, 0], [2, 0, 0], [7, 0, 0]], collection="course", player=PLAYER)
coll.objects["far"].location.x = -1.5                                                # move the far side to 4.5..8.5: a 1.5 m gap
bpy.context.view_layer.update()
narrow = call("traversal_check", route=[[0, 0, 0], [2, 0, 0], [7, 0, 0]], collection="course", player=PLAYER)
print("RESULT", json.dumps({"wide": wide, "narrow": states(narrow)}))
'''))
    assert states_of(d["wide"]) == ["ok", "ok", "gap"] and "3.0" in d["wide"]["steps"][2]["detail"]
    assert d["narrow"] == ["ok", "ok", "ok"]


def states_of(res):
    return [s["state"] for s in res["steps"]]


def test_a_steep_ramp_is_too_steep_and_a_gentle_one_is_ok(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("floor", (5, 0, -0.05), (12, 4, 0.1))
def ramp(name, x0, run, rise):
    bm = bmesh.new()
    v = [bm.verts.new(p) for p in ((x0, -2, 0), (x0 + run, -2, rise), (x0 + run, 2, rise), (x0, 2, 0), (x0 + run, -2, 0), (x0 + run, 2, 0))]
    bm.faces.new((v[0], v[1], v[2], v[3])); bm.faces.new((v[0], v[4], v[1])); bm.faces.new((v[3], v[2], v[5])); bm.faces.new((v[1], v[4], v[5], v[2]))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); coll.objects.link(ob); return ob
r = ramp("ramp", 3, 1.0, 2.0)                                                         # about 63 degrees
steep = call("traversal_check", route=[[0, 0, 0], [2, 0, 0], [3.6, 0, 1.2]], collection="course", player=PLAYER)
bpy.data.objects.remove(r); ramp("gentle", 3, 4.0, 1.0)                               # about 14 degrees
bpy.context.view_layer.update()
gentle = call("traversal_check", route=[[0, 0, 0], [2, 0, 0], [5, 0, 0.5]], collection="course", player=PLAYER)
print("RESULT", json.dumps({"steep": states(steep), "gentle": states(gentle)}))
'''))
    assert d["steep"][-1] == "too_steep" and d["gentle"] == ["ok", "ok", "ok"]


def test_sightlines_and_the_refusals(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("floor", (5, 0, -0.05), (12, 4, 0.1))
block("wall", (5, 3, 1.0), (0.2, 2, 2.0))
res = call("traversal_check", route=[[0, 0, 0], [3, 0, 0]], collection="course", player=PLAYER,
           sightlines=[{"from": [0, 0, 1.6], "to": [9, 0, 1.6]}, {"from": [0, 3, 1.6], "to": [9, 3, 1.6]}])
nop = call("traversal_check", route=[[0, 0, 0], [3, 0, 0]], collection="course", player={"capsule_radius_m": 0.3})
nocoll = call("traversal_check", route=[[0, 0, 0], [3, 0, 0]], collection="nope", player=PLAYER)
far = call("traversal_check", route=[[0, 0, 0], [300, 0, 0]], collection="course", player=PLAYER)
print("RESULT", json.dumps({"lines": [s["ok"] for s in res["sightlines"]], "nop": nop, "nocoll": nocoll, "far": far}))
'''))
    assert d["lines"] == [True, False]
    assert d["nop"]["ok"] is False and "the capsule decides what is traversable" in d["nop"]["error"] and "max_step_m" in d["nop"]["error"]
    assert d["nocoll"]["ok"] is False and "nope" in d["nocoll"]["error"]
    assert d["far"]["ok"] is False and "outside" in d["far"]["error"]


def test_a_step_just_above_max_step_and_below_the_knee_probe_is_still_blocked(tmp_path):
    d = one(go(tmp_path, COURSE + '''
block("floor", (5, 0, -0.05), (12, 4, 0.1))
block("kerb", (5, 0, 0.165), (2, 4, 0.33))                                             # 3 cm over max_step, under the wall probe at max_step + 5 cm
res = call("traversal_check", route=[[0, 0, 0], [3, 0, 0], [7, 0, 0]], collection="course", player=PLAYER)
print("RESULT", json.dumps(res))
'''))
    assert states_of(d) == ["ok", "ok", "blocked"] and "a step of 0.33" in d["steps"][2]["detail"]
