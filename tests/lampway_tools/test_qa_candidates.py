# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA candidates: open loops and floating shells with typed descriptors (the shelf's mesh_qa.py).

Synthetic cases run in the REAL binary. The recorded-run regression replays the shelf's own chest run
(chest_9c052d49_r2: 103 candidates) when the shelf's scratch data is present."""

import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

SPHERE = '''
import bpy, bmesh, json, math
from mathutils import Vector, Matrix
from mixar.modules.lampway_tools.meshqa import candidates as C

def build(cut_deg=25, float_gap=0.045):
    me = bpy.data.meshes.new("m")
    bm = bmesh.new()
    bmesh.ops.create_icosphere(bm, subdivisions=4, radius=0.3)
    bm.faces.ensure_lookup_table()
    axis = Vector((1, 0, 0))
    cut = [f for f in bm.faces if math.degrees(f.calc_center_median().angle(axis)) < cut_deg]
    bmesh.ops.delete(bm, geom=cut, context="FACES_ONLY")
    cube = bmesh.ops.create_cube(bm, size=0.05, matrix=Matrix.Translation((0, 0, 0.3 + float_gap)))
    bm.to_mesh(me); bm.free()
    return me

me = build()
n = len(me.polygons)
import numpy as np
owner = np.array([0 if me.polygons[i].center.z >= 0 else 1 for i in range(n)])
rec = {"parts": {"top": {"class": "rigid-metal"}, "bottom": {"class": "cloth-sim"}}}
'''


def test_an_open_loop_and_a_floating_shell_are_found_with_typed_descriptors():
    run = run_script(SPHERE + '''
prep = C.prepare(me, Matrix.Identity(4), owner)
cands = C.analyse(prep, rec, C.Params())
print("RESULT", json.dumps({
    "kinds": sorted(c["kind"] for c in cands),
    "loop": next(c for c in cands if c["kind"] == "open_loop"),
    "shell": next(c for c in cands if c["kind"] == "loose_shell"),
}))
''')
    assert run.rc == 0, run.out[-2500:]
    res = run.results[0]
    assert res["kinds"] == ["loose_shell", "open_loop"]
    loop, shell = res["loop"], res["shell"]
    assert loop["id"] == "L000" and shell["id"] == "S000"
    assert loop["perimeter_m"] > 0.5 and loop["edges"] > 8
    assert loop["side"] in ("front", "back", "left", "right")           # the cut faces +x: the body's side in a -y-front frame
    assert set(loop["seen_from_pct"]) == {"front", "back", "left", "right", "top", "bottom"}
    assert set(loop["bordering_parts_pct"]) <= {"top", "bottom"}
    assert set(loop["bordering_classes"]) <= {"rigid-metal", "cloth-sim"}
    assert len(loop["segments_m"]) == loop["edges"]
    assert "behind" in loop
    assert shell["tris"] == 12 and 15 < shell["gap_to_nearest_mm"] < 25
    assert shell["orig_polys"] and not any(k.startswith("_") for k in shell)


def test_the_perimeter_floor_drops_small_loops():
    run = run_script(SPHERE + '''
prep = C.prepare(me, Matrix.Identity(4), owner)
loose = C.analyse(prep, rec, C.Params(min_perimeter=5.0))
print("RESULT", json.dumps({"loops": sum(c["kind"] == "open_loop" for c in loose)}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"loops": 0}]


def test_a_shell_closer_than_the_float_distance_is_not_floating():
    run = run_script(SPHERE + '''
me = build(float_gap=0.024)
owner = np.zeros(len(me.polygons), int)
prep = C.prepare(me, Matrix.Identity(4), owner)
cands = C.analyse(prep, rec, C.Params(float_mm=3.0))
print("RESULT", json.dumps({"shells": sum(c["kind"] == "loose_shell" for c in cands)}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"shells": 0}]


def test_ruled_deletions_are_applied_before_the_analysis():
    run = run_script(SPHERE + '''
before = C.analyse(C.prepare(me, Matrix.Identity(4), owner), rec, C.Params())
cube_polys = [p.index for p in me.polygons if p.center.z > 0.31]
after = C.analyse(C.prepare(me, Matrix.Identity(4), owner, delete_polys=cube_polys), rec, C.Params())
print("RESULT", json.dumps({"before": sum(c["kind"] == "loose_shell" for c in before), "after": sum(c["kind"] == "loose_shell" for c in after), "deleted": len(cube_polys)}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert run.results == [{"before": 1, "after": 0, "deleted": 6}]


def test_owner_length_must_match_the_polygon_count():
    run = run_script(SPHERE + '''
try:
    C.prepare(me, Matrix.Identity(4), owner[:-1]); out = "no error"
except ValueError as e:
    out = str(e)
print("RESULT", json.dumps({"msg": out}))
''')
    assert run.rc == 0, run.out[-2500:]
    assert "labels for" in run.results[0]["msg"]


SHELF = Path(os.environ.get("LAMPWAY_SHELF") or "/nonexistent")   # the owner's recorded runs; unset = skipped
RUN = SHELF / "meshqa" / "chest_9c052d49_r2" / "candidates.json"


@pytest.mark.skipif(not RUN.exists(), reason="the shelf's recorded chest run is not on this machine")
def test_the_recorded_chest_run_is_reproduced_candidate_for_candidate(tmp_path):
    recorded = json.load(open(RUN))
    run = run_script(f'''
import bpy, json, math, numpy as np
from mathutils import Matrix
from mixar.modules.lampway_tools.meshqa import candidates as C
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.fbx(filepath={recorded["mesh"]!r})
ob = next(o for o in bpy.data.objects if o.type == "MESH")
ob.rotation_euler[2] += math.radians({recorded["turn"]})
bpy.context.view_layer.update()
rec = json.load(open({recorded["recipe"]!r}))
owner = np.load({recorded["owner"]!r})
dele = json.load(open({recorded["deleted_before"]!r}))["polys"]
prep = C.prepare(ob.data, ob.matrix_world.copy(), owner, delete_polys=dele)
cands = C.analyse(prep, rec, C.Params())
print("RESULT", json.dumps([[c["id"], c["kind"], c.get("perimeter_m"), c.get("tris"), c["side"], c["centroid_m"]] for c in cands]))
''', timeout=900)
    assert run.rc == 0, run.out[-2500:]
    got = run.results[0]
    want = recorded["candidates"]
    # the deletions file has grown since the recorded run (the user later ruled more floating shells deletable),
    # so the shells that vanished must be exactly ones whose every face is now in that file
    deleted = set(json.load(open(recorded["deleted_before"]))["polys"])

    # open loops: same ids, same geometry
    got_loops = {r[0]: r for r in got if r[1] == "open_loop"}
    want_loops = {c["id"]: c for c in want if c["kind"] == "open_loop"}
    assert set(got_loops) == set(want_loops) and len(want_loops) == 84
    for cid, c in want_loops.items():
        assert got_loops[cid][4] == c["side"], cid
        assert got_loops[cid][5] == pytest.approx(c["centroid_m"], abs=2e-3), cid
        assert got_loops[cid][2] == pytest.approx(c["perimeter_m"], abs=2e-3), cid

    # floating shells: matched by position (ids shift when an earlier shell is gone)
    got_shells = [r for r in got if r[1] == "loose_shell"]
    unmatched = []
    for c in (c for c in want if c["kind"] == "loose_shell"):
        near = [r for r in got_shells if r[3] == c["tris"] and r[4] == c["side"]
                and all(abs(a - b) < 2e-3 for a, b in zip(r[5], c["centroid_m"]))]
        if not near:
            unmatched.append(c)
    assert len(got_shells) + len(unmatched) == 19
    assert unmatched, "expected the later-ruled shells to be gone"
    for c in unmatched:
        assert set(c["orig_polys"]) <= deleted, (c["id"], "vanished but not ruled deleted")
