# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""side_label_check (specs/wiki/side_label_check.md): a piece labelled left/right sits on the FIGURE's side (not the camera's) and is not a mirrored copy of
its pair. REAL binary, synthetic gauntlet-like shapes (a bar with a thumb block on one side, so the shape is not its own mirror)."""

import json

from features_support import run

SHAPES = '''
def gauntlet(name, cx, thumb_out=False):
    """A bracer bar along Z at x=cx with a thumb block toward +Y and toward the body's centre (thumb_out: away from it): NOT symmetric about its own x.
    Two default gauntlets at +x and -x are exact mirrors of each other about x = 0."""
    inward = -1.0 if cx > 0 else 1.0
    s = -1.0 if thumb_out else 1.0
    ob = boxes(name, [((cx, 0.0, 1.0), (0.10, 0.10, 0.30)), ((cx + s * inward * 0.08, 0.06, 0.95), (0.06, 0.04, 0.08))])
    canon(name)                                 # the door: a mesh tool reads canonical input
    return ob

def helmet(name):
    ob = boxes(name, [((0.0, 0.0, 1.7), (0.24, 0.26, 0.28))])
    canon(name)
    return ob
'''


def _go(tmp_path, body):
    r = run(tmp_path, SHAPES + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_left_piece_on_plus_x_facing_minus_y_passes(tmp_path):
    res = _go(tmp_path, '''
gauntlet("gauntlet_l", 0.5)
print("RESULT", json.dumps(call("side_label_check", object="gauntlet_l", declared_side="left", body_midline_x=0.0)))
''')
    assert res["ok"] is True and res["measured_side"] == "left" and res["pass"] is True, res
    assert res["centroid_offset_m"] > 0.4 and res["declared_side"] == "left"


def test_flipping_facing_turns_the_same_left_piece_into_a_right_one(tmp_path):
    """The falsifier of the first test: the figure's left is +X only while it faces -Y."""
    res = _go(tmp_path, '''
gauntlet("gauntlet_l", 0.5)
print("RESULT", json.dumps(call("side_label_check", object="gauntlet_l", declared_side="left", facing="+Y", body_midline_x=0.0)))
''')
    assert res["ok"] is True and res["measured_side"] == "right" and res["pass"] is False, res
    assert any("right" in r for r in res["reasons"]), res


def test_the_side_is_read_from_the_name_when_none_is_declared(tmp_path):
    res = _go(tmp_path, '''
gauntlet("Gauntlet_R", -0.5)
print("RESULT", json.dumps(call("side_label_check", object="Gauntlet_R", body_midline_x=0.0)))
''')
    assert res["ok"] is True and res["declared_side"] == "right" and res["measured_side"] == "right" and res["pass"] is True, res


def test_mirrored_pair_is_flagged_as_mirror(tmp_path):
    res = _go(tmp_path, '''
gauntlet("g_l", 0.5)
gauntlet("g_r", -0.5)                                  # the exact mirror of g_l about x = 0
gauntlet("g_r2", -0.5, thumb_out=True)                 # its own design: the thumb on the other side of the bracer
out = {"mirror": call("side_label_check", object="g_l", declared_side="left", body_midline_x=0.0, pair="g_r"),
       "own": call("side_label_check", object="g_l", declared_side="left", body_midline_x=0.0, pair="g_r2")}
print("RESULT", json.dumps(out))
''')
    m, o = res["mirror"], res["own"]
    assert m["ok"] is True and m["pair"]["is_mirror_of"] is True and m["pass"] is False, m
    assert m["pair"]["chamfer_to_mirrored_pair"] < 0.005, m
    assert o["pair"]["is_mirror_of"] is False and o["pass"] is True, o


def test_centred_symmetric_piece_reports_center(tmp_path):
    res = _go(tmp_path, '''
helmet("helmet")
print("RESULT", json.dumps(call("side_label_check", object="helmet", declared_side="center", body_midline_x=0.0)))
''')
    assert res["ok"] is True and res["measured_side"] == "center" and res["pass"] is True, res
    assert res["mirror_asymmetry"] < 0.001, res


def test_an_asymmetric_piece_reports_its_own_mirror_asymmetry(tmp_path):
    res = _go(tmp_path, '''
gauntlet("gauntlet_l", 0.5)
print("RESULT", json.dumps(call("side_label_check", object="gauntlet_l", declared_side="left", body_midline_x=0.0)))
''')
    assert res["mirror_asymmetry"] > 0.02, res


def test_the_midline_comes_from_an_armatures_paired_bones(tmp_path):
    res = _go(tmp_path, '''
arm = bpy.data.armatures.new("rig"); rig = link(bpy.data.objects.new("rig", arm))
bpy.context.view_layer.objects.active = rig; bpy.ops.object.mode_set(mode="EDIT")
for n, x in (("clavicle_l", 0.3), ("clavicle_r", -0.1), ("hand_l", 0.9), ("hand_r", -0.7)):
    b = arm.edit_bones.new(n); b.head = (x, 0, 1.4); b.tail = (x, 0, 1.5)
bpy.ops.object.mode_set(mode="OBJECT")
gauntlet("gauntlet_l", 0.5)
gauntlet("gauntlet_c", 0.1)
out = {"l": call("side_label_check", object="gauntlet_l", declared_side="left", armature="rig"),
       "c": call("side_label_check", object="gauntlet_c", declared_side="left", armature="rig")}
print("RESULT", json.dumps(out))
''')
    assert res["l"]["midline_x"] == 0.1 and res["l"]["midline_source"] == "armature" and res["l"]["pass"] is True, res
    assert res["c"]["measured_side"] == "center" and res["c"]["pass"] is False, res


def test_refusals_name_their_fix(tmp_path):
    res = _go(tmp_path, '''
g = gauntlet("gauntlet_l", 0.5)
nomid = call("side_label_check", object="gauntlet_l", declared_side="left")
g.rotation_euler = (0, 0, 0.5); bpy.context.view_layer.update()
rot = call("side_label_check", object="gauntlet_l", declared_side="left", body_midline_x=0.0)
g.rotation_euler = (0, 0, 0); bpy.context.view_layer.update()
bad = call("side_label_check", object="gauntlet_l", declared_side="up", body_midline_x=0.0)
noside = call("side_label_check", object="gauntlet_l", body_midline_x=0.0)
print("RESULT", json.dumps({"nomid": nomid, "rot": rot, "bad": bad, "noside": noside}))
''')
    assert res["nomid"]["ok"] is False and "body_midline_x or an armature" in res["nomid"]["error"], res["nomid"]
    # an unapplied rotation now stops at the door (the object no longer matches its canonical stamp) before the tool's own check
    assert res["rot"]["ok"] is False and "normalize first" in res["rot"]["error"], res["rot"]
    assert res["bad"]["ok"] is False and "left" in res["bad"]["error"], res["bad"]
    assert res["noside"]["ok"] is True and res["noside"]["declared_side"] == "left", res["noside"]   # gauntlet_l names it
