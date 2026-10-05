# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_score (specs/shelf, resources and wiki uv_score.md: ONE tool) and uv_texel_density (specs/resources/uv_texel_density.md). The measurement is the shelf's uv_score.py
(utilization rasterised at 1024, overlap, UV-welded islands, stretch p90/p10, off-density, flipped faces, seam length, composite score), reproduced on the shelf's REAL Smart UV
attempts; texel density is measured per island and equalised, then repacked. REAL binary."""

import json
import os
from pathlib import Path

import pytest

from features_support import run

SHELF = Path(os.environ.get("LAMPWAY_SHELF_DIR") or "/nonexistent-shelf")
SCR = Path(os.environ.get("LAMPWAY_SHELF_SCRATCH") or SHELF / "scratch")
UVD = SCR / "tripo_uv"
REAL = (UVD / "Boots1/attempt_2.fbx").exists()
real = pytest.mark.skipif(not REAL, reason="the shelf's Boots1 Smart UV attempts are not on this machine")

PLANE = '''
def plane(name, n=4, size=1.0, uv=lambda x, y: (x, y)):
    bm = bmesh.new()
    bmesh.ops.create_grid(bm, x_segments=n, y_segments=n, size=size / 2)
    uvl = bm.loops.layers.uv.new("UVMap")
    for f in bm.faces:
        for l in f.loops:
            l[uvl].uv = uv((l.vert.co.x + size / 2) / size, (l.vert.co.y + size / 2) / size)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))
'''


def test_one_plane_is_one_island_without_overlap_and_a_mirrored_half_is_flipped(tmp_path):
    r = run(tmp_path, PLANE + '''
good = plane("good", uv=lambda u, v: (u * 0.9, v * 0.9))
half = plane("half", uv=lambda u, v: ((1 - u) if v > 0.5 else u, v))                  # the upper half mirrored in U
res = call("uv_score", objects=["good", "half"])
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    rows = {x["name"]: x for x in r.results[0]["rows"]}
    g, h = rows["good"], rows["half"]
    assert g["islands"] == 1 and g["overlap"] < 0.005 and g["flipped"] == 0 and g["utilization"] == pytest.approx(0.81, abs=0.02)
    assert 0.3 < h["flipped"] < 0.7 and h["score"] < g["score"], "the winding test: a mirrored half reads as flipped (RED if the winding test is absent)"
    assert g["gates"]["pass"] is True and h["gates"]["pass"] is False and "flipped" in " ".join(h["gates"]["failed"])
    assert r.results[0]["best"] == "good"


def test_two_islands_stacked_on_each_other_overlap(tmp_path):
    r = run(tmp_path, PLANE + '''
stack = plane("stack", n=2, uv=lambda u, v: (u * 0.5, v * 0.5))
b = plane("b", n=2, uv=lambda u, v: (u * 0.5, v * 0.5))
bpy.ops.object.select_all(action="DESELECT"); stack.select_set(True); b.select_set(True); bpy.context.view_layer.objects.active = stack
bpy.ops.object.join()
res = call("uv_score", objects=["stack"])
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    row = r.results[0]["rows"][0]
    assert row["overlap"] > 0.4 and row["islands"] == 2 and row["gates"]["pass"] is False


def test_refusals_name_the_fix(tmp_path):
    r = run(tmp_path, '''
bpy.data.objects.new("nouv", bpy.data.meshes.new("nouv"))
sphere("nouvmesh")
a = call("uv_score", objects=["nouvmesh"])
b = call("uv_score")
c = call("uv_score", objects=["nouvmesh"], res=64)
d = call("uv_score", files=["../../outside.fbx"])
print("RESULT", json.dumps({"a": a, "b": b, "c": c, "d": d}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["a"]["rows"][0]["error"] == "no UV layer on nouvmesh: unwrap it first (lampway_uv_unwrap)"
    assert o["b"]["ok"] is False and "objects or files" in o["b"]["error"]
    assert o["c"]["ok"] is False and "256..4096" in o["c"]["error"] and o["d"]["ok"] is False and "outside the project root" in o["d"]["error"]


@real
def test_the_real_boots1_attempts_reproduce_the_shelfs_rows_and_ranking(tmp_path):
    import shutil
    files = []
    for i in (2, 3, 4):                                                    # files must be inside the project root: copy the shelf's attempts in
        shutil.copy(UVD / f"Boots1/attempt_{i}.fbx", tmp_path / f"attempt_{i}.fbx")
        files.append(f"attempt_{i}.fbx")
    r = run(tmp_path, f'''
res = call("uv_score", files={files!r}, out="uv_score_test.json")
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is True, res
    shelf = {x["file"]: x for x in json.loads((UVD / "Boots1/uv_score.json").read_text())["rows"]}
    for row in res["rows"]:
        want = shelf[row["file"]]
        assert row["islands"] == want["islands"] and row["faces"] == want["faces"]
        for k in ("utilization", "overlap", "flipped", "off_density_2x", "stretch_p90_p10", "seam_m", "score"):
            assert row[k] == pytest.approx(want[k], rel=0.01, abs=0.001), (row["file"], k, row[k], want[k])
    assert [x["file"] for x in sorted(res["rows"], key=lambda x: -x["score"])] == ["attempt_2.fbx", "attempt_3.fbx", "attempt_4.fbx"] and res["best"] == "attempt_2.fbx"
    assert all(x["gates"]["pass"] for x in res["rows"]), "the shelf attempts pass the gates"
    assert (tmp_path / "uv_score_test.json").exists()


# ------------------------------------------------------------------------------------------------ texel density
TWO = '''
def two_boxes(name="tb"):
    """A big (1 m) and a small (0.2 m) cube smart-projected together (uniform density), then every UV corner of the small cube is scaled by 0.25 about its own centroid: its density is 1/4 of the big one's."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 0)))
    bmesh.ops.create_cube(bm, size=0.2, matrix=Matrix.Translation((3, 0, 0)))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me))
    bpy.context.view_layer.objects.active = ob; ob.select_set(True)
    bpy.ops.object.mode_set(mode="EDIT"); bpy.ops.mesh.select_all(action="SELECT"); bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02); bpy.ops.object.mode_set(mode="OBJECT")
    uvl = ob.data.uv_layers.active.data
    small = [l for p in ob.data.polygons if ob.data.vertices[p.vertices[0]].co.x > 1.5 for l in p.loop_indices]
    cx = sum(uvl[i].uv[0] for i in small) / len(small); cy = sum(uvl[i].uv[1] for i in small) / len(small)
    for i in small: uvl[i].uv = (cx + (uvl[i].uv[0] - cx) * 0.25, cy + (uvl[i].uv[1] - cy) * 0.25)
    return ob
'''


def test_density_spread_is_equalised_and_the_original_keeps_its_uvs(tmp_path):
    r = run(tmp_path, TWO + '''
import math
ob = two_boxes()
before_uv = [tuple(l.uv) for l in ob.data.uv_layers.active.data]
res = call("uv_texel_density", object="tb", texture_size=2048)
new = bpy.data.objects[res["object"]]
print("RESULT", json.dumps({"res": res, "orig_unchanged": before_uv == [tuple(l.uv) for l in ob.data.uv_layers.active.data], "name": new.name}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    res = o["res"]
    assert res["ok"] is True and o["name"] == "tb_td" and o["orig_unchanged"] is True
    assert res["before"]["density_cv"] > 0.4, res["before"]
    assert res["after"]["density_cv"] < 0.02, res["after"]
    assert res["after"]["islands"] == res["before"]["islands"] and res["after"]["uv_min"][0] >= -1e-6 and res["after"]["uv_max"][0] <= 1 + 1e-6 and res["after"]["uv_max"][1] <= 1 + 1e-6
    assert 0 < res["shortfall"] <= 1.0 and res["achieved_target"] > 0


def test_weights_set_the_ratio_between_islands_by_vertex_group_and_the_pack_keeps_it(tmp_path):
    r = run(tmp_path, TWO + '''
import math
ob = two_boxes()
vg = ob.vertex_groups.new(name="small")
vg.add([v.index for v in ob.data.vertices if v.co.x > 1.5], 1.0, "REPLACE")
a = call("uv_texel_density", object="tb", texture_size=2048, name="auto_td")
w = call("uv_texel_density", object="tb", texture_size=2048, weights={"small": 2.0}, name="w_td")
print("RESULT", json.dumps({"a": a, "w": w}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    isl = sorted(o["w"]["islands_scaled"], key=lambda x: x["weight"])
    assert [x["weight"] for x in isl][-1] == 2.0 and len(isl) >= 2
    heavy = [x for x in isl if x["weight"] == 2.0]
    light = [x for x in isl if x["weight"] == 1.0]
    mean = lambda xs: sum(x["density_after"] for x in xs) / len(xs)      # noqa: E731
    assert mean(heavy) / mean(light) == pytest.approx(2.0, rel=0.03), (heavy, light)
    assert o["a"]["after"]["density_cv"] < 0.02 and o["a"]["requested_target"] > 0 and o["w"]["after"]["density_cv"] < 0.02, "the spread is measured on density / weight"


def test_refusals_name_the_reason(tmp_path):
    r = run(tmp_path, '''
sphere("nouv")
a = call("uv_texel_density", object="nouv")
b = call("uv_texel_density", object="nouv", texture_size=1000)
print("RESULT", json.dumps({"a": a, "b": b}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert "no UV layer on nouv: run lampway_uv_unwrap first" in o["a"]["error"] and "not a power of two" in o["b"]["error"]
