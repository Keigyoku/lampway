# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_check (specs/mixar_docs/uv_check.md): per-island density, overlaps (accidental vs deliberately stacked), space usage, orientation, UDIM tiles and the two
edits (udim_move, stack), dry-run by default. REAL binary, synthetic quads with hand-set UVs."""

import json

from features_support import run

QUADS = '''
def quads(name, rects, xs=None, mirror_second=False):
    """One 1 m x 1 m quad per UV rect (u0, v0, u1, v1), laid along X at xs; mirror_second puts quad 1 at -x of quad 0 with its winding mirrored in 3D."""
    xs = xs or [i * 2.0 for i in range(len(rects))]
    me = bpy.data.meshes.new(name)
    verts, faces = [], []
    for i, x in enumerate(xs):
        b = len(verts)
        verts += [(x, 0, 0), (x + 1, 0, 0), (x + 1, 0, 1), (x, 0, 1)]
        faces.append((b, b + 1, b + 2, b + 3))
    me.from_pydata(verts, [], faces)
    uv = me.uv_layers.new(name="UVMap")
    for i, (u0, v0, u1, v1) in enumerate(rects):
        for k, (u, v) in enumerate(((u0, v0), (u1, v0), (u1, v1), (u0, v1))):
            uv.data[4 * i + k].uv = (u, v)
    me.update()
    ob = link(bpy.data.objects.new(name, me))
    canon(name)                                 # the door: uv_check reads a canonical mesh at real scale
    return ob

def mirrored_pair(name):
    """Two quads mirrored across x = 0 in 3D (x in [0.5, 1.5] and [-1.5, -0.5]), each its own UV island."""
    me = bpy.data.meshes.new(name)
    verts = [(0.5, 0, 0), (1.5, 0, 0), (1.5, 0, 1), (0.5, 0, 1), (-0.5, 0, 0), (-0.5, 0, 1), (-1.5, 0, 1), (-1.5, 0, 0)]
    me.from_pydata(verts, [], [(0, 1, 2, 3), (4, 5, 6, 7)])
    uv = me.uv_layers.new(name="UVMap")
    for k, p in enumerate([(0.0, 0.0), (0.4, 0.0), (0.4, 0.4), (0.0, 0.4), (0.6, 0.0), (0.6, 0.4), (1.0, 0.4), (1.0, 0.0)]):
        uv.data[k].uv = p
    me.update()
    ob = link(bpy.data.objects.new(name, me))
    canon(name)                                 # the door: uv_check reads a canonical mesh at real scale
    return ob

def uvhash(ob):
    return [tuple(round(c, 6) for c in d.uv) for d in ob.data.uv_layers.active.data]
'''


def _go(tmp_path, body):
    r = run(tmp_path, QUADS + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_half_scale_island_reads_half_the_density(tmp_path):
    res = _go(tmp_path, '''
quads("p", [(0.0, 0.0, 0.4, 0.4), (0.5, 0.5, 0.7, 0.7)])
canon("p")
print("RESULT", json.dumps(call("uv_check", object="p", action="measure", texture_size=1000)))
''')
    assert res["ok"] is True and res["action"] == "measure" and len(res["islands"]) == 2, res
    d = sorted(i["density_px_m"] for i in res["islands"])
    assert abs(d[1] / d[0] - 2.0) < 1e-3 and abs(d[1] - 400.0) < 0.5, d
    assert all(i["tiles"] == [1001] for i in res["islands"]), res["islands"]


def test_overlapping_islands_are_counted_and_a_one_tile_shift_clears_them(tmp_path):
    res = _go(tmp_path, '''
quads("p", [(0.0, 0.0, 0.5, 0.5), (0.25, 0.25, 0.75, 0.75)])
quads("q", [(0.0, 0.0, 0.5, 0.5), (1.25, 0.25, 1.75, 0.75)], xs=[5.0, 7.0])
canon("p", "q")
print("RESULT", json.dumps({"p": call("uv_check", object="p", action="overlaps"), "q": call("uv_check", object="q", action="overlaps")}))
''')
    p, q = res["p"], res["q"]
    assert p["overlap"]["fraction"] > 0.1 and p["overlap"]["accidental"] == [[0, 1]], p
    assert q["overlap"]["fraction"] == 0.0 and q["overlap"]["accidental"] == [], q


def test_a_mirrored_island_is_flagged_and_stacked_overlap_is_not_accidental(tmp_path):
    res = _go(tmp_path, '''
mirrored_pair("m")
canon("m")
o = call("uv_check", object="m", action="orientation")
before = uvhash(bpy.data.objects["m"])
canon("m")
dry = call("uv_check", object="m", action="stack")
same = uvhash(bpy.data.objects["m"]) == before
canon("m")
done = call("uv_check", object="m", action="stack", dry_run=False)
canon("m")
ov = call("uv_check", object="m", action="overlaps")
print("RESULT", json.dumps({"o": o, "dry": dry, "same": same, "done": done, "ov": ov}))
''')
    assert res["o"]["orientation"]["mirrored"] == [[0, 1]], res["o"]
    assert res["dry"]["applied"] is False and res["same"] is True and res["dry"]["stacked"][0]["a"] == 0, res
    assert res["done"]["applied"] is True, res["done"]
    assert res["ov"]["overlap"]["stacked"] == [[0, 1]] and res["ov"]["overlap"]["accidental"] == [], res["ov"]


def test_stack_refuses_a_non_mirrored_pair_by_name(tmp_path):
    res = _go(tmp_path, '''
quads("p", [(0.0, 0.0, 0.2, 0.2), (0.5, 0.5, 0.9, 0.9)])
canon("p")
print("RESULT", json.dumps(call("uv_check", object="p", action="stack", islands=[0, 1], dry_run=False)))
''')
    assert res["ok"] is False and "islands 0 and 1" in res["error"] and "not mirror" in res["error"], res


def test_udim_move_is_a_dry_run_by_default_and_moves_whole_tiles(tmp_path):
    res = _go(tmp_path, '''
ob = quads("p", [(0.1, 0.1, 0.4, 0.4), (0.5, 0.5, 0.9, 0.9)])
before = uvhash(ob)
canon("p")
dry = call("uv_check", object="p", action="udim_move", islands=[1], tile_to=1012)
same = uvhash(ob) == before
canon("p")
done = call("uv_check", object="p", action="udim_move", islands=[1], tile_to=1012, dry_run=False)
canon("p")
m = call("uv_check", object="p", action="measure")
canon("p")
far = call("uv_check", object="p", action="udim_move", islands=[1], tile_to=1100)
print("RESULT", json.dumps({"dry": dry, "same": same, "done": done, "m": m, "far": far, "uv": [list(d.uv) for d in ob.data.uv_layers.active.data][4:5]}))
''')
    assert res["dry"]["applied"] is False and res["same"] is True and res["dry"]["moved"][0]["to"] == 1012, res["dry"]
    assert res["done"]["applied"] is True and abs(res["uv"][0][0] - 1.5) < 1e-6 and abs(res["uv"][0][1] - 1.5) < 1e-6, res
    tiles = {i["index"]: i["tiles"] for i in res["m"]["islands"]}
    assert tiles == {0: [1001], 1: [1012]} and res["m"]["udim"]["tiles"] == [1001, 1012], res["m"]
    assert res["far"]["ok"] is False and "1001..1099" in res["far"]["error"], res["far"]


def test_an_island_across_a_tile_border_is_a_udim_finding(tmp_path):
    res = _go(tmp_path, '''
quads("p", [(0.8, 0.1, 1.2, 0.5)])
canon("p")
print("RESULT", json.dumps(call("uv_check", object="p", action="measure")))
''')
    assert res["udim"]["crossing"] == [0] and res["islands"][0]["tiles"] == [1001, 1002], res


def test_select_by_density_and_space_usage(tmp_path):
    res = _go(tmp_path, '''
ob = quads("p", [(0.0, 0.0, 0.4, 0.4), (0.5, 0.5, 0.7, 0.7)])
canon("p")
s = call("uv_check", object="p", action="select_by_density", target_density_px_m=400, texture_size=1000, tolerance=0.1)
sel = [p.index for p in ob.data.polygons if p.select]
canon("p")
u = call("uv_check", object="p", action="space_usage")
print("RESULT", json.dumps({"s": s, "sel": sel, "u": u}))
''')
    assert res["s"]["selected"] == [1] and res["sel"] == [1] and res["s"]["islands"][0]["index"] == 1, res
    assert abs(res["u"]["usage"]["coverage"] - 0.20) < 0.01 and res["u"]["usage"]["free_blocks"] > 0, res["u"]


def test_refusals_name_the_fix(tmp_path):
    res = _go(tmp_path, '''
me = bpy.data.meshes.new("n"); me.from_pydata([(0, 0, 0), (1, 0, 0), (1, 1, 0)], [], [(0, 1, 2)]); link(bpy.data.objects.new("n", me)); canon("n")
quads("p", [(0.0, 0.0, 0.4, 0.4)])
canon("n", "p")
print("RESULT", json.dumps({"nouv": call("uv_check", object="n", action="measure"), "bad": call("uv_check", object="p", action="explode")}))
''')
    assert res["nouv"]["ok"] is False and "lampway_uv_unwrap" in res["nouv"]["error"], res
    assert res["bad"]["ok"] is False and "measure" in res["bad"]["error"], res
