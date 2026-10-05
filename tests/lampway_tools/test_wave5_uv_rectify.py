# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_rectify (resources/uv_rectify.md): straighten, rectify and gridify UV islands of strap-like geometry, in the real binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

STRIP = '''
def strip(name, rows=6, cols=40, r1=1.0, r2=1.15, arc=120.0, triangulate=False, uv=True):
    """A flat annulus sector (rows across, cols along the arc) with its UVs = the planar projection: a curved ribbon island."""
    bm = bmesh.new()
    verts = []
    for j in range(rows + 1):
        r = r1 + (r2 - r1) * j / rows
        row = []
        for i in range(cols + 1):
            a = math.radians(arc) * i / cols
            row.append(bm.verts.new((r * math.cos(a), r * math.sin(a), 0.0)))
        verts.append(row)
    for j in range(rows):
        for i in range(cols):
            bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
    if triangulate:
        bmesh.ops.triangulate(bm, faces=bm.faces[:])
    uvl = bm.loops.layers.uv.new("UVMap") if uv else None
    if uv:
        for f in bm.faces:
            for l in f.loops:
                l[uvl].uv = (l.vert.co.x * 0.4 + 0.5, l.vert.co.y * 0.4 + 0.1)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))

def uvs(ob):
    uvl = ob.data.uv_layers.active
    return [tuple(l.uv) for l in uvl.data]

def positions(ob):
    return [tuple(round(c, 7) for c in v.co) for v in ob.data.vertices]
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, STRIP + body, **kw)


def test_gridify_straightens_a_curved_strip_into_an_even_grid_and_changes_nothing_in_3d(tmp_path):
    r = go(tmp_path, '''
src = strip("belt")
u0, p0 = uvs(src), positions(src)
res = call("uv_rectify", object="belt", op="gridify")
new = bpy.data.objects[res["object"]]
print("RESULT", json.dumps({"res": res, "src_same": uvs(src) == u0, "pos_same": positions(new) == p0, "name": new.name}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    res = d["res"]
    assert res["ok"] is True and d["name"] == "belt_rect" and d["src_same"] and d["pos_same"]
    op = res["ops"][0]
    assert op["op"] == "gridify" and op["rectangularity_before"] < 0.85 and op["rectangularity_after"] >= 0.98 and op["stretch_p90_p10_after"] <= 1.1, op
    assert res["skipped"] == [] and abs(op["uv_area_after"] - op["uv_area_before"]) < 0.01 * op["uv_area_before"]          # the island keeps its UV area (its texel density)


def test_an_island_that_is_not_a_quad_grid_is_skipped_with_the_reason_never_dropped(tmp_path):
    r = go(tmp_path, '''
bm = bmesh.new(); bmesh.ops.create_icosphere(bm, subdivisions=2, radius=0.5)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().z < 0.0], context="FACES")
uvl = bm.loops.layers.uv.new("UVMap")
for f in bm.faces:
    for l in f.loops: l[uvl].uv = (l.vert.co.x + 0.5, l.vert.co.y + 0.5)
me = bpy.data.meshes.new("cap"); bm.to_mesh(me); bm.free(); link(bpy.data.objects.new("cap", me))
res = call("uv_rectify", object="cap", op="auto")
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    assert res["ok"] is True and res["ops"] == [] and len(res["skipped"]) == 1 and "not a quad grid" in res["skipped"][0]["reason"] and "triangles" in res["skipped"][0]["reason"]


def test_straighten_puts_a_chain_on_a_line_keeping_its_edge_length_ratios(tmp_path):
    r = go(tmp_path, '''
src = strip("belt")
cols = 40; rows = 6
mid = 3 * (cols + 1)
chain = [[mid + i, mid + i + 1] for i in range(5, 16)]               # 12 vertices of the middle row
res = call("uv_rectify", object="belt", op="straighten", edges=chain)
new = bpy.data.objects[res["object"]]
me = new.data; uvl = me.uv_layers.active
at = {}
for poly in me.polygons:
    for li in poly.loop_indices:
        at[me.loops[li].vertex_index] = tuple(uvl.data[li].uv)
pts = [at[mid + i] for i in range(5, 17)]
import numpy as np
P = np.array(pts); c = P - P.mean(0); u, s, vt = np.linalg.svd(c); dev = float(np.abs(c @ vt[1]).max())
uvlen = [float(np.linalg.norm(P[k + 1] - P[k])) for k in range(11)]
geo = [float((me.vertices[mid + 5 + k + 1].co - me.vertices[mid + 5 + k].co).length) for k in range(11)]
bnd = [li for poly in src.data.polygons for li in poly.loop_indices if src.data.loops[li].vertex_index < cols + 1]      # the outer row of vertices
same = all(tuple(round(c, 6) for c in new.data.uv_layers.active.data[li].uv) == tuple(round(c, 6) for c in src.data.uv_layers.active.data[li].uv) for li in bnd)
print("RESULT", json.dumps({"res": res, "dev": dev, "boundary_same": same, "ratio": [uvlen[k] / uvlen[0] / (geo[k] / geo[0]) for k in range(11)]}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["res"]["ok"] is True and d["dev"] < 1e-4 and d["boundary_same"], d
    assert all(abs(x - 1.0) < 0.02 for x in d["ratio"]), d["ratio"]


def test_rectify_maps_a_triangulated_island_s_boundary_onto_a_rectangle(tmp_path):
    r = go(tmp_path, '''
strip("tri", rows=4, cols=24, triangulate=True)
res = call("uv_rectify", object="tri", op="rectify")
print("RESULT", json.dumps(res))
''')
    assert r.rc == 0, r.out[-2500:]
    res = r.results[0]
    op = res["ops"][0]
    assert res["ok"] is True and op["op"] == "rectify" and op["rectangularity_before"] < 0.85 and op["rectangularity_after"] >= 0.97, res


def test_refusals_no_uv_layer_bad_evenness_a_broken_chain_and_a_textured_object(tmp_path):
    r = go(tmp_path, '''
strip("nouv", uv=False)
strip("ok")
out = {"nouv": call("uv_rectify", object="nouv"),
       "even": call("uv_rectify", object="ok", evenness=1.5),
       "chain": call("uv_rectify", object="ok", op="straighten", edges=[[0, 1], [5, 6]]),
       "nochain": call("uv_rectify", object="ok", op="straighten"),
       "op": call("uv_rectify", object="ok", op="swirl")}
ob = bpy.data.objects["ok"]
mat = bpy.data.materials.new("m"); mat.use_nodes = True
img = bpy.data.images.new("t", 8, 8); img.filepath = os.path.join(root, "t.png"); img.source = "FILE"
tex = mat.node_tree.nodes.new("ShaderNodeTexImage"); tex.image = img
mat.node_tree.links.new(tex.outputs["Color"], mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"])
ob.data.materials.append(mat)
out["textured"] = call("uv_rectify", object="ok")
out["discard"] = call("uv_rectify", object="ok", discard_texture=True)["ok"]
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert "no UV layer on nouv: run lampway_uv_unwrap first" in d["nouv"]["error"]
    assert "evenness must be in 0..1" in d["even"]["error"]
    assert "edges chain must be connected and inside one island" in d["chain"]["error"] and "edges is required for op=straighten" in d["nochain"]["error"]
    assert "op is auto | rectify | gridify | straighten" in d["op"]["error"]
    assert "is textured; a UV change discards the texture" in d["textured"]["error"] and d["discard"] is True


def test_evenness_blends_the_column_spacing_between_the_geometry_s_and_a_uniform_one(tmp_path):
    r = go(tmp_path, '''
bm = bmesh.new(); cols = 10; rows = 3
verts = [[bm.verts.new(((i / cols) ** 2 * 4.0, j * 0.3, 0.0)) for i in range(cols + 1)] for j in range(rows + 1)]      # columns widen quadratically
for j in range(rows):
    for i in range(cols): bm.faces.new((verts[j][i], verts[j][i + 1], verts[j + 1][i + 1], verts[j + 1][i]))
uvl = bm.loops.layers.uv.new("UVMap")
for f in bm.faces:
    for l in f.loops: l[uvl].uv = (l.vert.co.x * 0.1 + 0.2, l.vert.co.y * 0.1 + 0.2)
me = bpy.data.meshes.new("taper"); bm.to_mesh(me); bm.free(); link(bpy.data.objects.new("taper", me))
def widths(res):
    o = bpy.data.objects[res["object"]]; m = o.data; uv = m.uv_layers.active; at = {}
    for poly in m.polygons:
        for li in poly.loop_indices: at[m.loops[li].vertex_index] = uv.data[li].uv[0]
    xs = [at[i] for i in range(cols + 1)]            # the bottom row
    return [abs(xs[k + 1] - xs[k]) for k in range(cols)]
a = call("uv_rectify", object="taper", op="gridify", evenness=0.0, name="e0")
b = call("uv_rectify", object="taper", op="gridify", evenness=1.0, name="e1")
print("RESULT", json.dumps({"e0": widths(a), "e1": widths(b), "geo": [((k + 1) / cols) ** 2 * 4.0 - (k / cols) ** 2 * 4.0 for k in range(cols)]}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    r0 = [w / d["e0"][0] for w in d["e0"]]
    g0 = [w / d["geo"][0] for w in d["geo"]]
    assert all(abs(a - b) < 1e-3 * max(1, b) for a, b in zip(r0, g0)), (r0, g0)                    # evenness 0: spacing follows the 3D edge lengths
    assert max(d["e1"]) - min(d["e1"]) < 1e-5                                                         # evenness 1: uniform


def test_a_tall_island_stays_tall_the_long_side_keeps_its_axis(tmp_path):
    r = go(tmp_path, '''
src = strip("tall", rows=4, cols=30, arc=60.0)
for l in src.data.uv_layers.active.data:
    l.uv = (l.uv[1] * 0.2, l.uv[0] * 0.9)             # swap the axes and squash: the island is tall
res = call("uv_rectify", object="tall", op="gridify")
uv = bpy.data.objects[res["object"]].data.uv_layers.active.data
xs = [l.uv[0] for l in uv]; ys = [l.uv[1] for l in uv]
print("RESULT", json.dumps({"w": max(xs) - min(xs), "h": max(ys) - min(ys), "ok": res["ok"]}))
''')
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["ok"] and d["h"] > 2 * d["w"], d
