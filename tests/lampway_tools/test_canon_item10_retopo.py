# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 10 (canon 12): a QuadriFlow that refuses the mesh is never silently replaced by the voxel remesh - the
fallback is the caller's explicit choice, and the receipt says it was taken. Observed failing on the tool before the change."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402

NONMANIFOLD = r'''
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=10, y_segments=10, size=0.5)
e = next(e for e in bm.edges if len(e.link_faces) == 2)                         # an interior edge
a, b = e.verts
top = bm.verts.new((a.co + b.co) / 2 + Vector((0, 0, 0.3)))
bm.faces.new([a, b, top])                                                       # a third face on it: non-manifold
me = bpy.data.meshes.new("nm"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("nm", me); bpy.context.scene.collection.objects.link(ob)
bpy.context.view_layer.update(); ob.select_set(True); bpy.context.view_layer.objects.active = ob
'''


def test_a_refused_quadriflow_is_refused_unless_the_voxel_fallback_is_asked_for(tmp_path):
    from isolated_binary import run
    r = run(tmp_path, NONMANIFOLD + '''
a = api.retopo("nm", target_faces=200, method="quadriflow")
left = sorted(o.name for o in bpy.data.objects)
b = api.retopo("nm", target_faces=200, method="quadriflow", fallback=True)
assert b.get("ok"), b
print("RESULT", json.dumps({"a_ok": a.get("ok"), "a_err": a.get("error"), "a_method": a.get("method"), "left": left,
    "b_method": b.get("method"), "b_note": b.get("note"), "b_faces": b["report"]["faces"],
    "b_achieved": b["achieved_faces"], "b_target": b["target_faces"],
    "actual_faces": len(bpy.data.objects[b["object"]].data.polygons)}))
''')
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["a_ok"] is False and "fallback" in d["a_err"] and d["left"] == ["nm"], d
    assert d["b_method"] == "voxel" and "fallback" in (d["b_note"] or ""), d
    assert d["b_faces"] == d["b_achieved"] == d["actual_faces"] > 0 and d["b_target"] == 200, d
    assert f"achieved {d['actual_faces']} faces against target 200" in d["b_note"], d


HARD = r'''
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=12, use_grid_fill=True)
bmesh.ops.triangulate(bm, faces=bm.faces[:])
me = bpy.data.meshes.new("box"); bm.to_mesh(me); bm.free()
ob = bpy.data.objects.new("box", me); bpy.context.scene.collection.objects.link(ob)
'''


def test_b3_sharp_edges_are_preserved_by_default_and_a_target_above_3x_is_refused_for_every_method():
    """canon 12 B.3 (hard-surface flags) and INV-12.5. Measured on this 1 m box (2028 triangles, target 600): QuadriFlow's two-sided
    max deviation 3.98 mm without preserve-sharp, 1.41 mm with it."""
    r = run_script(PRE + HARD + '''
n = len(bpy.data.objects["box"].data.polygons)
a = api.retopo("box", target_faces=600, method="quadriflow")
b = api.retopo("box", target_faces=600, method="quadriflow", preserve_sharp=False)
big = {m: api.retopo("box", target_faces=3 * n + 1, method=m) for m in ("quadriflow", "voxel")}
res({"a": a["report"]["max_deviation"], "a_sharp": a.get("preserve_sharp"), "b": b["report"]["max_deviation"], "b_sharp": b.get("preserve_sharp"),
     "big": {m: {"ok": v.get("ok"), "error": v.get("error")} for m, v in big.items()}})
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["a_sharp"] is True and d["b_sharp"] is False and d["a"] < d["b"] / 2, d
    for m, v in d["big"].items():
        assert v["ok"] is False and "3x the source" in v["error"], (m, v)


C03 = r'''
G = GOLD + "/C03_seam_tube/piece.obj"
V, F, grp, cur = [], [], [], None
for line in open(G):
    w = line.split()
    if not w: continue
    if w[0] == "v": V.append(tuple(map(float, w[1:4])))
    elif w[0] == "g": cur = w[1]
    elif w[0] == "f": F.append([int(x.split("/")[0]) - 1 for x in w[1:]]); grp.append(cur)
def piece(name, part=True):
    me = bpy.data.meshes.new(name); me.from_pydata(V, [], F); me.update()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob)
    if part:
        a = me.attributes.new("part", "INT", "FACE"); a.data.foreach_set("value", [0 if g == "lower" else 1 for g in grp])
    bm = bmesh.new(); bm.from_mesh(me); bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5); bm.to_mesh(me); bm.free()   # one shell, as normalized
    return ob
def span(ob, eps=1e-4):
    me = ob.data
    return sum(1 for p in me.polygons if min(me.vertices[i].co.z for i in p.vertices) < 1.2 - eps and max(me.vertices[i].co.z for i in p.vertices) > 1.2 + eps)
'''


def test_g12_3_per_part_remesh_keeps_the_cut_and_carries_the_part_map():
    """canon 12 B.1 / INV-12.3 / G12.3 on golden C03 (one shell cut into two parts at z = 1.2, welded as a generated piece is): each
    part is remeshed alone with its boundary preserved, then welded by position; no face spans both parts, every face carries its part.
    The falsifier, measured: the whole shell remeshed puts faces across the cut."""
    from canon_support import goldens as _g  # noqa: F401
    import canon_support
    gold = str(canon_support.GOLDENS_SRC)
    r = run_script(PRE + f"GOLD = {gold!r}\n" + C03 + '''
whole = piece("whole"); w = api.retopo("whole", target_faces=400, method="quadriflow")
pp = piece("parts"); p = api.retopo("parts", target_faces=400, method="quadriflow", per_part=True)
none = piece("bare", part=False); n = api.retopo("bare", target_faces=400, method="quadriflow", per_part=True)
out = bpy.data.objects.get(p.get("object") or "")
parts = sorted(set(out.data.attributes["part"].data[i].value for i in range(len(out.data.polygons)))) if out and "part" in out.data.attributes else None
strays = sorted(o.name for o in bpy.data.objects if o.name.startswith("parts") and o.name not in ("parts", p.get("object")))
res({"strays": strays, "faces": len(out.data.polygons) if out else 0, "whole_span": span(bpy.data.objects[w["object"]]), "ok": p.get("ok"), "error": p.get("error"), "span": span(out) if out else None,
     "parts": parts, "per_part": p.get("per_part"), "bare": n.get("error")})
''', timeout=300)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert d["whole_span"] > 0, d                                       # the falsifier: a whole-shell remesh crosses the cut
    assert d["ok"], d["error"]
    assert d["span"] == 0 and d["parts"] == [0, 1] and d["strays"] == [], d          # one result object holding both parts
    assert d["faces"] == sum(v["faces"] for v in d["per_part"]["parts"].values()), d
    pp = d["per_part"]
    assert set(pp["parts"]) == {"0", "1"} and all(v["faces"] > 0 for v in pp["parts"].values()) and pp["attribute"] == "part", pp
    assert d["bare"] and "part" in d["bare"], d
