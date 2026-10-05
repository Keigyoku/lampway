# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_layout (resources/uv_layout.md): orient islands, align them to the world, stack mirrored pairs, fix flipped islands, in the real binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_LAYOUT = '''
def box(name, center, size, slot=0):
    """An axis-aligned box whose six faces are six separate unit-square UV islands laid out in a 3x2 grid."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.Translation(center) @ Matrix.Diagonal((size[0], size[1], size[2], 1.0)))
    uvl = bm.loops.layers.uv.new("UVMap")
    for k, f in enumerate(bm.faces):
        cx, cy = (k % 3) * 0.16 + 0.02 + (0.5 if slot == 1 else 0.0), (k // 3) * 0.2 + 0.02 + (0.5 if slot == 2 else 0.0)
        for i, l in enumerate(f.loops):
            l[uvl].uv = (cx + (0.12 if i in (1, 2) else 0.0), cy + (0.12 if i in (2, 3) else 0.0))
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    return link(bpy.data.objects.new(name, me))

def join(name, objs):
    bm = bmesh.new()
    for o in objs:
        me = o.data.copy(); me.transform(o.matrix_world); bm.from_mesh(me)
    uvl = bm.loops.layers.uv.active
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    out = link(bpy.data.objects.new(name, me))
    for o in objs: bpy.data.objects.remove(o)
    return out

def rot_island(ob, face_ids, deg):
    uv = ob.data.uv_layers.active.data; a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    pts = [(poly.index, li) for poly in ob.data.polygons if poly.index in face_ids for li in poly.loop_indices]
    cx = sum(uv[li].uv[0] for _p, li in pts) / len(pts); cy = sum(uv[li].uv[1] for _p, li in pts) / len(pts)
    for _p, li in pts:
        x, y = uv[li].uv[0] - cx, uv[li].uv[1] - cy
        uv[li].uv = (cx + c * x - s * y, cy + s * x + c * y)
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_LAYOUT + body, **kw)


def test_orient_brings_rotated_islands_back_to_their_minimal_axis_aligned_box(tmp_path):
    r = go(tmp_path, '''
b = box("b", (0, 0, 0), (1, 1, 1))
for k in range(6): rot_island(b, {k}, 33.0)
res = call("uv_layout", object="b", ops=["orient"])
new = bpy.data.objects[res["object"]]
from mathutils.geometry import box_fit_2d
me = new.data; uv = me.uv_layers.active.data
resid = []
for poly in me.polygons:
    pts = [tuple(uv[li].uv) for li in poly.loop_indices]
    a = math.degrees(box_fit_2d(pts)); a = ((a + 45) % 90) - 45
    resid.append(abs(a))
print("RESULT", json.dumps({"res": res, "resid": max(resid), "name": new.name}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["res"]["ok"] and d["name"] == "b_lay" and d["res"]["oriented"] == 6 and d["resid"] < 0.5, d


def test_stack_mirrored_pairs_exactly_the_mirrored_twins_and_not_the_equal_count_stranger(tmp_path):
    r = go(tmp_path, '''
a = box("a", (1.5, 0, 0), (0.6, 0.4, 0.4)); b = box("b", (-1.5, 0, 0), (0.6, 0.4, 0.4), slot=1); c = box("c", (0, 0, 0), (0.3, 0.9, 0.4), slot=2)     # c: same counts, different shape, on the plane
j = join("trio", [a, b, c])
res = call("uv_layout", object="trio", ops=["stack_mirrored"])
new = bpy.data.objects[res["object"]]
me = new.data; uv = me.uv_layers.active.data
# island = box: faces 0-5 a, 6-11 b, 12-17 c
def uvs_of(face_set):
    return sorted(tuple(round(c, 5) for c in uv[li].uv) for poly in me.polygons if poly.index in face_set for li in poly.loop_indices)
print("RESULT", json.dumps({"res": res, "a_b_same": uvs_of(set(range(0, 6))) == uvs_of(set(range(6, 12))), "a_c_same": uvs_of(set(range(0, 6))) == uvs_of(set(range(12, 18)))}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    pairs = d["res"]["stacked"]
    assert d["res"]["ok"] and len(pairs) == 7 and all(p["chamfer_m"] < 0.003 for p in pairs), d["res"]
    # islands = faces: 0-5 are a's, 6-11 b's, 12-17 c's. a pairs with b face by face; c is never paired with a or b (it is only the twin of its own +x/-x faces)
    across = [p for p in pairs if p["a"] < 6]
    assert len(across) == 6 and all(6 <= p["b"] < 12 for p in across)
    assert sum(1 for p in pairs if p["a"] >= 12 and p["b"] >= 12) == 1 and not any(12 <= p["a"] and p["b"] < 12 or p["a"] < 12 <= p["b"] for p in pairs)
    assert not d["a_c_same"] and d["res"]["report"]["stacked_overlap_fraction"] > 0 and d["res"]["report"]["overlap_fraction"] < 0.005
    assert d["res"]["note"] and "bake_maps" in d["res"]["note"]


def test_a_mesh_off_the_mirror_plane_is_refused_and_no_pairs_is_a_note_not_an_error(tmp_path):
    r = go(tmp_path, '''
box("lone", (2.0, 0, 0), (0.4, 0.4, 0.4))
out = {"off": call("uv_layout", object="lone", ops=["stack_mirrored"])}
tri = bpy.data.meshes.new("tri"); tri.from_pydata([(-1, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)]); tri.uv_layers.new(name="UVMap")
link(bpy.data.objects.new("tri", tri))
out["none"] = call("uv_layout", object="tri", ops=["stack_mirrored"])
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert "stack_mirrored needs the mesh centred on the mirror plane" in d["off"]["error"] and "apply the transform or pass mirror_axis" in d["off"]["error"]
    assert d["none"]["ok"] is True and d["none"]["stacked"] == [] and "no mirrored pairs" in d["none"]["note"]


def test_fix_flipped_mirrors_the_minority_island_so_the_flipped_fraction_is_zero(tmp_path):
    r = go(tmp_path, '''
b = box("b", (0, 0, 0), (1, 1, 1))
uv = b.data.uv_layers.active.data
for poly in b.data.polygons:
    if poly.index == 2:
        lis = list(poly.loop_indices)
        pts = [tuple(uv[li].uv) for li in lis]
        for li, p in zip(lis, reversed(pts)): uv[li].uv = p                  # reverse the winding of one island
before = call("uv_score", objects=["b"])["rows"][0]["flipped"]
res = call("uv_layout", object="b", ops=["fix_flipped"])
after = call("uv_score", objects=[res["object"]])["rows"][0]["flipped"]
print("RESULT", json.dumps({"before": before, "after": after, "fixed": res["flipped_fixed"], "rep": res["report"]["flipped"]}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["before"] > 0 and d["after"] == 0 and d["fixed"] == 1 and d["rep"] == 0


def test_align_world_turns_a_tilted_vertical_strap_island_so_world_up_is_uv_up(tmp_path):
    r = go(tmp_path, '''
bm = bmesh.new(); rows, cols = 12, 2
vs = [[bm.verts.new((i * 0.1, 0.0, j * 0.1)) for i in range(cols + 1)] for j in range(rows + 1)]      # a strap in the XZ plane, long along world Z
for j in range(rows):
    for i in range(cols): bm.faces.new((vs[j][i], vs[j][i + 1], vs[j + 1][i + 1], vs[j + 1][i]))
uvl = bm.loops.layers.uv.new("UVMap")
a = math.radians(40)
for f in bm.faces:
    for l in f.loops:
        x, y = l.vert.co.x, l.vert.co.z
        l[uvl].uv = (0.5 + math.cos(a) * x - math.sin(a) * y, 0.5 + math.sin(a) * x + math.cos(a) * y)       # tilted by 40 degrees
me = bpy.data.meshes.new("strap"); bm.to_mesh(me); bm.free(); link(bpy.data.objects.new("strap", me))
res = call("uv_layout", object="strap", ops=["align_world"], world_axis="z")
new = bpy.data.objects[res["object"]]; m = new.data; uv = m.uv_layers.active.data
import numpy as np
pts = np.array([(m.vertices[m.loops[li].vertex_index].co.z, uv[li].uv[0], uv[li].uv[1]) for li in range(len(m.loops))])
cz = np.corrcoef(pts[:, 0], pts[:, 2])[0, 1]; cu = np.corrcoef(pts[:, 0], pts[:, 1])[0, 1]
print("RESULT", json.dumps({"res": res, "cz": float(cz), "cu": float(cu)}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["res"]["ok"] and d["res"]["aligned"] == 1 and d["cz"] > 0.999 and abs(d["cu"]) < 0.02, d


def test_refusals_unknown_op_no_uv_layer_textured_and_per_face_not_built(tmp_path):
    r = go(tmp_path, '''
b = box("b", (0, 0, 0), (1, 1, 1))
out = {"op": call("uv_layout", object="b", ops=["swirl"]), "axis": call("uv_layout", object="b", ops=["align_world"], world_axis="w"),
       "tol": call("uv_layout", object="b", ops=["stack_mirrored"], match_tolerance=1.0), "pf": call("uv_layout", object="b", ops=["orient"], per_face=True)}
nb = bpy.data.meshes.new("n"); nb.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)]); link(bpy.data.objects.new("nouv", nb))
out["nouv"] = call("uv_layout", object="nouv")
print("RESULT", json.dumps(out))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert "ops are orient | align_world | stack_mirrored | fix_flipped | sort" in d["op"]["error"] and "world_axis is auto | x | y | z" in d["axis"]["error"]
    assert "match_tolerance must be between 0.0005 and 0.05" in d["tol"]["error"] and "per_face is not built" in d["pf"]["error"]
    assert "no UV layer on nouv: run lampway_uv_unwrap first" in d["nouv"]["error"]
