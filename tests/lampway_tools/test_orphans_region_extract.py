# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_region_extract (specs/wiki/mesh_region_extract.md): a chosen region (box, 2D polygon in a view, vertex group, material slot or zone number) becomes its
own object, capped or filled, from COPIES: the source is never changed. REAL binary."""

import json

from features_support import run

GRID = '''
import bmesh
from mathutils import Matrix
def plate(name):
    """A subdivided box (5 x 5 faces per side, 150 faces), the left third's faces in a second material slot and a vertex group."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation((0, 0, 0.5)))
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=4, use_grid_fill=True)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = link(bpy.data.objects.new(name, me))
    for n in ("steel", "gold"):
        me.materials.append(bpy.data.materials.new(n))
    left = [p.index for p in me.polygons if p.center.x < -0.3]
    for i in left: me.polygons[i].material_index = 1
    g = ob.vertex_groups.new(name="left"); g.add(sorted({v for i in left for v in me.polygons[i].vertices}), 1.0, "REPLACE")
    return ob, left
ob, left = plate("plate")
canon("plate", welded=True, scale="any")              # the door: regions follow adjacency, so the mesh is welded by position
def loops(name):
    bm = bmesh.new(); bm.from_mesh(bpy.data.objects[name].data)
    edges = [e for e in bm.edges if len(e.link_faces) == 1]; seen, n = set(), 0
    for e in edges:
        if e.index in seen: continue
        n += 1; stack = [e]
        while stack:
            c = stack.pop()
            if c.index in seen: continue
            seen.add(c.index)
            for v in c.verts:
                stack += [x for x in v.link_edges if len(x.link_faces) == 1 and x.index not in seen]
    bm.free(); return n
def info(name):
    o = bpy.data.objects[name]; return {"faces": len(o.data.polygons), "loops": loops(name)}
'''


def _go(tmp_path, body):
    r = run(tmp_path, GRID + body)
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_box_region_separates_the_expected_faces(tmp_path):
    res = _go(tmp_path, '''
r = call("mesh_region_extract", object="plate", region={"bbox": [-0.6, -0.6, -0.1, -0.3, 0.6, 1.1]}, cap="none")
print("RESULT", json.dumps({"r": r, "left": len(left), "src": info("plate")}))
''')
    r = res["r"]
    assert r["ok"] is True and r["faces"] == res["left"] and r["extracted"] == "plate_region", r
    assert res["src"] == {"faces": 150, "loops": 0}, "the source is untouched"


def test_fill_holes_makes_the_part_watertight_and_cap_none_leaves_the_loop(tmp_path):
    res = _go(tmp_path, '''
a = call("mesh_region_extract", object="plate", region={"material_slot": "gold"}, cap="fill_holes", name="filled")
b = call("mesh_region_extract", object="plate", region={"vertex_group": "left"}, cap="none", name="open")
c = call("mesh_region_extract", object="plate", region={"zone": 2, "by": "material_slot"}, cap="fan", name="fanned")
print("RESULT", json.dumps({"a": a, "b": b, "c": c, "fa": info("filled"), "fb": info("open"), "fc": info("fanned")}))
''')
    assert res["a"]["open_loops_before_cap"] == 1 and res["a"]["capped"] == 1 and res["fa"]["loops"] == 0, res
    assert res["fb"]["loops"] == 1 and res["b"]["capped"] == 0, "the falsifier: cap none leaves the open loop"
    assert res["fc"]["loops"] == 0 and res["fc"]["faces"] > res["a"]["faces"] + 1, "a fan caps with triangles around a centre"


def test_keep_in_source_false_leaves_a_hole_in_the_remainder(tmp_path):
    res = _go(tmp_path, '''
r = call("mesh_region_extract", object="plate", region={"material_slot": 1}, keep_in_source=False)
print("RESULT", json.dumps({"r": r, "rem": info(r["remainder"]), "src": info("plate")}))
''')
    assert res["r"]["remainder"] == "plate_remainder" and res["rem"]["loops"] == 1 and res["rem"]["faces"] == 150 - res["r"]["faces"], res
    assert res["src"] == {"faces": 150, "loops": 0}


def test_a_lasso_in_the_front_view_and_the_refusals(tmp_path):
    res = _go(tmp_path, '''
lasso = call("mesh_region_extract", object="plate", region={"polygon_2d": [[-0.6, -0.1], [-0.3, -0.1], [-0.3, 1.1], [-0.6, 1.1]], "view": "Front"}, cap="none")
out = {"lasso": lasso,
       "empty": call("mesh_region_extract", object="plate", region={"bbox": [5, 5, 5, 6, 6, 6]}),
       "whole": call("mesh_region_extract", object="plate", region={"bbox": [-1, -1, -1, 1, 1, 2]}),
       "bad": call("mesh_region_extract", object="plate", region={"colour": "red"})}
print("RESULT", json.dumps(out))
''')
    assert res["lasso"]["ok"] is True and res["lasso"]["faces"] > 0, res["lasso"]
    assert res["empty"]["ok"] is False and "empty" in res["empty"]["error"], res
    assert res["whole"]["ok"] is False and "whole mesh" in res["whole"]["error"], res
    assert res["bad"]["ok"] is False and "bbox" in res["bad"]["error"], res
