# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The swarm's lane and merge scripts, run in the REAL binary: three lanes whose workers all name their cube the same thing.

Blender object names are unique across the whole file, so same-named cubes in three lane scenes get suffixes; the merge must
keep all three (tagged with the worker that made each), leave the parent's own objects alone, and leave no lane scene or
orphan object behind. A cancelled worker's lane is discarded completely."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
from blender_run import run_script  # noqa: E402
from lampway_server.agent import swarm as SW  # noqa: E402

PARENT = "parent-1"


def workers(names):
    return [SW.Worker(f"worker-{i}", n, "p", f"agentlane:{PARENT}:{i}", f"sw1_{n}") for i, n in enumerate(names, 1)]


def scene_script(names, keep, cube_name="shared_cube"):
    ws = workers(names)
    plan = [{"id": w.id, "name": w.name, "scene": w.scene_name, "keep": keep[i]} for i, w in enumerate(ws)]
    return f'''
import bpy, json
if not hasattr(bpy.types.Scene, "mixie_session_id"):
    bpy.types.Scene.mixie_session_id = bpy.props.StringProperty()
for _o in list(bpy.data.objects):
    bpy.data.objects.remove(_o)
parent = bpy.context.scene
parent.mixie_session_id = {PARENT!r}
keepme = bpy.data.objects.new("parent_owned", bpy.data.meshes.new("parent_owned")); parent.collection.objects.link(keepme)
{SW.lane_script(PARENT, ws)}
lanes = {{s.mixie_session_id: s for s in bpy.data.scenes if s.mixie_session_id.startswith("agentlane:")}}
assert sorted(lanes) == {[w.lane for w in ws]!r}, sorted(lanes)
assert all(s.get("mixar_workspace_main_session") == {PARENT!r} for s in lanes.values())
made = {{}}
for i, w in enumerate({[w.lane for w in ws]!r}, 1):
    scene = lanes[w]
    me = bpy.data.meshes.new({cube_name!r})
    ob = bpy.data.objects.new({cube_name!r}, me)
    ob.location = (i * 100, 0, 0)
    scene.collection.objects.link(ob)
    made[w] = ob.name
{SW.merge_script(plan)}
print("RESULT", json.dumps({{"made": made, "merge": __RESULT__,
    "scenes": [s.name for s in bpy.data.scenes],
    "tagged": sorted([o.name, o["lw_worker"], round(o.location.x)] for o in bpy.data.objects if "lw_worker" in o.keys()),
    "in_parent": sorted(o.name for o in parent.objects),
    "all_objects": sorted(o.name for o in bpy.data.objects)}}))
'''


def test_three_workers_that_name_their_cube_the_same_all_survive_the_merge_attributed_to_their_own_worker():
    r = run_script(scene_script(["one", "two", "three"], [True, True, True]))
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["scenes"] == ["Scene"], "every lane scene must be gone"
    assert [t[1] for t in res["tagged"]] == ["worker-1", "worker-2", "worker-3"] or sorted(t[1] for t in res["tagged"]) == ["worker-1", "worker-2", "worker-3"]
    assert sorted(t[2] for t in res["tagged"]) == [100, 200, 300] and len({t[0] for t in res["tagged"]}) == 3
    by_worker = {t[1]: t[2] for t in res["tagged"]}
    assert by_worker == {"worker-1": 100, "worker-2": 200, "worker-3": 300}, "each object stays attributed to the worker that made it"
    assert "parent_owned" in res["in_parent"] and len(res["in_parent"]) == 4
    assert set(res["all_objects"]) == set(res["in_parent"]), "no object may be left outside the parent scene"


def test_a_discarded_lane_leaves_nothing_behind_and_the_kept_ones_are_untouched():
    r = run_script(scene_script(["one", "two", "three"], [True, False, True]))
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["scenes"] == ["Scene"]
    assert {t[1]: t[2] for t in res["tagged"]} == {"worker-1": 100, "worker-3": 300}
    assert len(res["in_parent"]) == 3 and set(res["all_objects"]) == set(res["in_parent"])
    assert "worker-2" in res["merge"]["discarded"] and "worker-2" not in res["merge"]["merged"]
