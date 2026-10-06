# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""level_blockout (specs/wiki/level_blockout.md) in the real binary: a primitive blockout at real gameplay scale in named sets (ground, route, obstacles, landmarks),
three fixed cameras, and traversal_check run on it before any art. The scale anchor turns layout units into metres; the player dimensions are required."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from wave6_support import go, one  # noqa: E402

PLAYER = {"capsule_radius_m": 0.3, "capsule_height_m": 1.8, "max_step_m": 0.3, "max_slope_deg": 45, "jump_height_m": 1.0, "jump_gap_m": 2.0}
LAYOUT = {"start": [0, 0, 0], "goal": [9, 0, 0], "route": [[3, 0, 0], [6, 0, 0]]}
PRIMS = [{"set": "ground", "kind": "box", "size": [12, 4, 0.1], "at": [5, 0, -0.05], "name": "floor"},
         {"set": "obstacles", "kind": "box", "size": [1, 1, 1], "at": [5, 1.6, 0.5]},
         {"set": "landmarks", "kind": "box", "size": [0.5, 0.5, 4], "at": [10, 1.5, 2]},
         {"set": "route", "kind": "ramp", "size": [2, 1.5, 0.4], "at": [1, -1.4, 0]},
         {"set": "obstacles", "kind": "stair", "size": [2, 1, 1.0], "at": [7, 1.4, 0]}]


def test_named_sets_cameras_and_a_passing_traversal(tmp_path):
    d = one(go(tmp_path, f'''
res = call("level_blockout", layout={LAYOUT!r}, player={PLAYER!r}, primitives={PRIMS!r}, name="yard")
colls = {{c.name: sorted(o.name for o in c.objects) for c in bpy.data.collections if c.name.startswith("yard")}}
stair = next(o for o in bpy.data.objects if o.name.startswith("yard_obstacles_stair"))
print("RESULT", json.dumps({{"res": res, "colls": colls, "cams": sorted(o.name for o in bpy.data.objects if o.type == "CAMERA"),
                            "floor": [round(x, 4) for x in bpy.data.objects["yard_floor"].dimensions], "stair_faces": len(stair.data.polygons)}}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert set(res["collections"]) == {"ground", "route", "obstacles", "landmarks"}
    for s in ("ground", "route", "obstacles", "landmarks"):
        assert d["colls"][f"yard_{s}"], s
    assert "yard_floor" in d["colls"]["yard_ground"] and "yard_route_path" in d["colls"]["yard_route"]
    assert d["cams"] == ["yard_cam1", "yard_cam2", "yard_cam3"] and res["cameras"] == d["cams"]
    assert d["floor"] == [12.0, 4.0, 0.1] and d["stair_faces"] > 6
    assert res["traversal"]["blocked_count"] == 0 and [s["state"] for s in res["traversal"]["steps"]] == ["ok"] * 4
    assert res["scale"] == {"factor": 1.0, "source": "metres (no scale anchor)"}


def test_scale_anchor_sets_metres(tmp_path):
    prims = [{"set": "ground", "kind": "box", "size": [600, 200, 5], "at": [250, 0, -2.5], "name": "floor"},
             {"set": "landmarks", "kind": "box", "size": [40, 40, 110], "at": [500, 80, 55], "name": "door"}]
    layout = {"start": [0, 0, 0], "goal": [450, 0, 0], "route": [[200, 0, 0]], "scale_anchor": {"object": "door", "length_m": 2.2}}
    d = one(go(tmp_path, f'''
res = call("level_blockout", layout={layout!r}, player={PLAYER!r}, primitives={prims!r}, name="map")
print("RESULT", json.dumps({{"res": res, "door": [round(x, 4) for x in bpy.data.objects["map_door"].dimensions],
                            "floor": [round(x, 4) for x in bpy.data.objects["map_floor"].dimensions]}}))
'''))
    res = d["res"]
    assert res["ok"], res
    assert res["scale"]["factor"] == 0.02 and d["door"] == [0.8, 0.8, 2.2] and d["floor"] == [12.0, 4.0, 0.1]
    assert res["traversal"]["steps"][-1]["point"] == [9.0, 0.0, 0.0]


def test_missing_player_dimensions_and_a_non_metre_scene_are_refused(tmp_path):
    d = one(go(tmp_path, f'''
nop = call("level_blockout", layout={LAYOUT!r}, primitives={PRIMS!r}, name="a")
part = call("level_blockout", layout={LAYOUT!r}, player={{"capsule_radius_m": 0.3}}, primitives={PRIMS!r}, name="b")
bpy.context.scene.unit_settings.scale_length = 0.01
units = call("level_blockout", layout={LAYOUT!r}, player={PLAYER!r}, primitives={PRIMS!r}, name="c")
bpy.context.scene.unit_settings.scale_length = 1.0
bad = call("level_blockout", layout={LAYOUT!r}, player={PLAYER!r}, primitives=[{{"set": "sky", "kind": "box", "size": [1, 1, 1], "at": [0, 0, 0]}}], name="d")
call("level_blockout", layout={LAYOUT!r}, player={PLAYER!r}, primitives={PRIMS!r}, name="e")
again = call("level_blockout", layout={LAYOUT!r}, player={PLAYER!r}, primitives={PRIMS!r}, name="e")
print("RESULT", json.dumps({{"nop": nop, "part": part, "units": units, "bad": bad, "again": again, "colls": sorted(c.name for c in bpy.data.collections)}}))
'''))
    for k in ("nop", "part"):
        assert d[k]["ok"] is False and "project dimensions are required: the capsule decides what is traversable" in d[k]["error"]
    assert d["units"]["ok"] is False and "scale_to_measure" in d["units"]["error"]
    assert d["bad"]["ok"] is False and "ground, route, obstacles, landmarks" in d["bad"]["error"]
    assert d["again"]["ok"] is False and "exists" in d["again"]["error"]
    assert not any(c.startswith(("a", "b", "c", "d")) for c in d["colls"])
