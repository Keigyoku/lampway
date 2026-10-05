# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The lane guard's wrapped script in the REAL binary, through the real ScriptExecutor: a parent object `chest` and a lane
scene `sw1_alpha` holding the worker's own `alpha_1`. Each case is one worker body; the guard section of the result says what
was put back and what could not be."""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from blender_run import run_script  # noqa: E402
from lampway_server.agent import lane_guard  # noqa: E402

LANE = "sw1_alpha"

BODIES = {
    "move_parent": "bpy.data.objects['chest'].location.x += 5",
    "rename_parent": "bpy.data.objects['chest'].name = 'alpha_chest'",
    "delete_parent": "bpy.data.objects.remove(bpy.data.objects['chest'])",
    "edit_parent_mesh": "bpy.data.objects['chest'].data.vertices[0].co.x += 1",
    "rename_own": "bpy.data.objects['alpha_1'].name = 'alpha_cube'",
    "create_own": "me = bpy.data.meshes.new('alpha_2')\nob = bpy.data.objects.new('alpha_2', me)\nbpy.data.scenes['%s'].collection.objects.link(ob)\n__RESULT__ = {'made': ob.name}" % LANE,
    "body_raises": "bpy.data.objects['chest'].location.x += 5\nraise KeyError('nope')",
}

DRIVER = '''
import json
import bpy
from mixar.modules.space_mixie_chat.core.executor import ScriptExecutor
import os
scripts = json.loads(os.environ["LW_SCRIPTS"])
if not hasattr(bpy.types.Scene, "mixie_session_id"):
    bpy.types.Scene.mixie_session_id = bpy.props.StringProperty()
for _o in list(bpy.data.objects):
    bpy.data.objects.remove(_o)
parent = bpy.context.scene
me = bpy.data.meshes.new("chest"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
chest = bpy.data.objects.new("chest", me); parent.collection.objects.link(chest)
lane = bpy.data.scenes.new("%(lane)s"); lane.mixie_session_id = "agentlane:p:1"
own = bpy.data.objects.new("alpha_1", bpy.data.meshes.new("alpha_1")); lane.collection.objects.link(own)
ex = ScriptExecutor()
out = {}
for name, script in scripts.items():
    chest = bpy.data.objects.get("chest")
    if chest is None:
        me = bpy.data.meshes.new("chest"); me.from_pydata([(0,0,0),(1,0,0),(0,1,0)], [], [(0,1,2)])
        chest = bpy.data.objects.new("chest", me); parent.collection.objects.link(chest)
    chest.location = (0, 0, 0)
    res = ex.execute(script, push_undo=False)
    d = res.to_dict()
    chest = bpy.data.objects.get("chest")
    out[name] = {"success": d.get("success"), "error": d.get("error"), "body_error": d.get("body_error"),
                 "lane_guard": d.get("lane_guard"), "made": d.get("made"),
                 "chest_exists": chest is not None, "chest_x": round(chest.location.x, 3) if chest else None,
                 "lane_objects": sorted(o.name for o in lane.collection.all_objects)}
print("RESULT", json.dumps(out))
''' % {"lane": LANE}


@pytest.fixture(scope="module")
def outcomes():
    scripts = {name: lane_guard.guarded_script(LANE, "import bpy\n" + body) for name, body in BODIES.items()}
    r = run_script(DRIVER, env={"LW_SCRIPTS": json.dumps(scripts)})
    assert r.rc == 0 and r.results, r.out[-3000:]
    return r.results[0]


def test_moving_a_parent_object_is_put_back_and_reported(outcomes):
    got = outcomes["move_parent"]
    assert got["success"] is True and got["chest_x"] == 0
    assert [v["kind"] for v in got["lane_guard"]["violations"]] == ["moved"]
    assert got["lane_guard"]["restored"] == ["chest"] and got["lane_guard"]["unrestored"] == []


def test_renaming_a_parent_object_is_put_back(outcomes):
    got = outcomes["rename_parent"]
    assert got["chest_exists"] is True
    assert [v["kind"] for v in got["lane_guard"]["violations"]] == ["renamed"]
    assert got["lane_guard"]["restored"] == ["chest"]


def test_deleting_a_parent_object_cannot_be_put_back_and_is_reported_as_such(outcomes):
    got = outcomes["delete_parent"]
    assert got["chest_exists"] is False
    assert got["lane_guard"]["unrestored"] == ["chest"]
    assert [v["kind"] for v in got["lane_guard"]["violations"]] == ["deleted"]


def test_editing_a_parent_mesh_is_an_unrestored_violation(outcomes):
    got = outcomes["edit_parent_mesh"]
    assert got["lane_guard"]["unrestored"] == ["chest"]
    assert [v["kind"] for v in got["lane_guard"]["violations"]] == ["edited"]


def test_renaming_its_own_object_is_no_violation_and_is_reported_as_a_rename(outcomes):
    got = outcomes["rename_own"]
    assert got["lane_guard"]["violations"] == []
    assert got["lane_guard"]["renamed_own"] == {"alpha_1": "alpha_cube"}


def test_creating_in_its_own_lane_is_no_violation_and_the_body_result_survives(outcomes):
    got = outcomes["create_own"]
    assert got["lane_guard"]["violations"] == [] and got["made"] == "alpha_2"
    assert "alpha_2" in got["lane_objects"]


def test_a_raising_body_still_gets_checked_and_put_back(outcomes):
    got = outcomes["body_raises"]
    assert got["body_error"] and "KeyError" in got["body_error"]
    assert got["chest_x"] == 0 and got["lane_guard"]["restored"] == ["chest"]
