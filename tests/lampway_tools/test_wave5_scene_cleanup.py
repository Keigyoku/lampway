# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scene_cleanup (specs/mixar_docs/scene_cleanup.md) in the real binary: report first, then clean in the documented order (transforms, loose, merge, non-manifold, normals, n-gons, purge, naming), scale-aware,
on `_clean` copies, with the guard that stops a merge that would eat the mesh."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE_SC = '''
def dirty_cube(name="dirty", scale=(1, 1, 2), size=1.0, gap=0.0):
    """A subdivided cube (98 vertices) with ONE doubled vertex (`gap` apart), one loose vertex, one small face wound backwards and a non-uniform object scale."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=size)
    bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    v = bm.verts[7]
    nv = bm.verts.new((v.co.x + gap, v.co.y, v.co.z))                                           # a DOUBLE of v: one adjacent face is rebuilt on it
    f = v.link_faces[0]
    vs = [nv if x is v else x for x in f.verts]
    bm.faces.remove(f)
    bm.faces.new(vs)
    bm.verts.ensure_lookup_table()
    bm.verts.new((9 * size, 9 * size, 9 * size))                                                # a loose vertex
    bm.faces.ensure_lookup_table()
    bm.faces[3].normal_flip()                                                                  # one small face wound backwards
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); ob.scale = scale
    return link(ob)

def snapshot(name):
    me = bpy.data.objects[name].data
    return [len(me.vertices), len(me.polygons), [round(c, 6) for v in me.vertices for c in v.co]]
'''


def go(tmp_path, body, **kw):
    return run(tmp_path, PRE_SC + body, **kw)


def one(r):
    assert r.rc == 0, r.out[-2500:]
    return r.results[0]


def test_the_report_counts_exactly_and_plan_mode_changes_nothing(tmp_path):
    d = one(go(tmp_path, '''
ob = dirty_cube()
before = snapshot("dirty")
res = call("scene_cleanup", objects=["dirty"])
rep = res["report"][0]
print("RESULT", json.dumps({"res": res, "same": snapshot("dirty") == before, "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    rep, res = d["res"]["report"][0], d["res"]
    assert res["ok"] and res["plan_only"] is True and d["same"] and d["objects"] == ["dirty"] and res["applied"] == []
    assert rep["object"] == "dirty" and rep["non_uniform_scale"] is True and rep["loose_verts"] == 1 and rep["doubles_at_distance"] == 1 and rep["flipped_faces"] == 1
    assert rep["non_manifold_edges"] >= 2 and rep["ngons"] == 0 and rep["uv_layers"] == 0 and rep["materials"]["slots"] == 0


def test_apply_works_on_a_clean_copy_in_the_documented_order_even_when_the_steps_are_given_reversed(tmp_path):
    d = one(go(tmp_path, '''
ob = dirty_cube()
before = snapshot("dirty")
dims0 = [round(x, 4) for x in ob.dimensions]
res = call("scene_cleanup", objects=["dirty"], plan_only=False, steps=["normals", "merge_by_distance", "loose", "apply_transforms"])
new = bpy.data.objects[res["branch"]["dirty"]]
bpy.context.view_layer.update()
after = call("scene_cleanup", objects=[new.name])["report"][0]
print("RESULT", json.dumps({"res": res, "name": new.name, "scale": [round(x, 4) for x in new.scale], "dims0": dims0, "dims1": [round(x, 4) for x in new.dimensions], "after": after,
                            "verts": len(new.data.vertices), "src_same": snapshot("dirty") == before, "src_scale": list(bpy.data.objects["dirty"].scale), "hash": new.get("lw_source_hash")}))
'''))
    res = d["res"]
    assert d["name"] == "dirty_clean" and d["src_same"] and d["src_scale"] == [1.0, 1.0, 2.0] and d["hash"]
    assert [a["step"] for a in res["applied"]] == ["apply_transforms", "loose", "merge_by_distance", "normals"]               # the documented order, whatever order was asked
    assert d["scale"] == [1.0, 1.0, 1.0] and d["dims1"] == [1.0, 1.0, 2.0] and d["verts"] == 98
    a = d["after"]
    assert a["loose_verts"] == 0 and a["doubles_at_distance"] == 0 and a["non_manifold_edges"] == 0 and a["flipped_faces"] == 0 and a["non_uniform_scale"] is False


def test_the_auto_merge_distance_scales_with_the_object(tmp_path):
    d = one(go(tmp_path, '''
small = dirty_cube("small", scale=(1, 1, 1), size=1.0, gap=5e-5)
big = dirty_cube("big", scale=(1, 1, 1), size=100.0, gap=5e-3)
a = call("scene_cleanup", objects=["small", "big"], merge_distance="auto")["report"]
b = call("scene_cleanup", objects=["small", "big"], merge_distance=1e-4)["report"]
print("RESULT", json.dumps({"auto": {r["object"]: r["doubles_at_distance"] for r in a}, "fixed": {r["object"]: r["doubles_at_distance"] for r in b}}))
'''))
    assert d["auto"] == {"small": 1, "big": 1}                                                  # 1e-4 x the bounding diagonal: a 100x object gets a 100x threshold
    assert d["fixed"]["small"] == 1 and d["fixed"]["big"] == 0                                  # the docs' trap: a fixed 1e-4 is far too small at another scale


def test_a_merge_that_would_remove_more_than_5_percent_stops_that_object_and_says_the_threshold_is_wrong(tmp_path):
    d = one(go(tmp_path, '''
dirty_cube("c", scale=(1, 1, 1))
res = call("scene_cleanup", objects=["c"], plan_only=False, steps=["merge_by_distance"], merge_distance=10.0)
print("RESULT", json.dumps({"res": res, "objects": sorted(o.name for o in bpy.data.objects)}))
'''))
    res = d["res"]
    assert res["applied"][0]["step"] == "merge_by_distance" and res["applied"][0]["changed"] == 0 and "threshold likely wrong" in res["applied"][0]["note"]


def test_refusals_edit_mode_shared_data_and_naming_without_a_convention(tmp_path):
    d = one(go(tmp_path, '''
a = dirty_cube("a")
b = a.copy(); link(b); b.name = "b"                                                           # shares a's mesh data
shared = call("scene_cleanup", objects=["a"], plan_only=False, copy=False, steps=["apply_transforms"])
naming = call("scene_cleanup", objects=["a"], plan_only=False, steps=["naming"])
bpy.context.view_layer.objects.active = a
bpy.ops.object.mode_set(mode="EDIT")
editing = call("scene_cleanup", objects=["a"])
bpy.ops.object.mode_set(mode="OBJECT")
bad = call("scene_cleanup", objects=["a"], steps=["teleport"])
print("RESULT", json.dumps({"shared": shared, "naming": naming, "editing": editing, "bad": bad}))
'''))
    assert d["shared"]["ok"] is False and "share this mesh" in d["shared"]["error"]
    assert d["naming"]["ok"] is False and "I cannot invent your naming convention: pass convention" in d["naming"]["error"]
    assert d["editing"]["ok"] is False and "leave Edit Mode" in d["editing"]["error"]
    assert d["bad"]["ok"] is False and "teleport" in d["bad"]["error"]


def test_ngons_policy_orphans_naming_and_unused_material_slots(tmp_path):
    d = one(go(tmp_path, '''
bm = bmesh.new()
vs = [bm.verts.new((math.cos(i * math.pi / 3), math.sin(i * math.pi / 3), 0)) for i in range(6)]
bm.faces.new(vs)
me = bpy.data.meshes.new("hex"); bm.to_mesh(me); bm.free()
ob = link(bpy.data.objects.new("Hex Thing.001", me))
m1, m2 = bpy.data.materials.new("Steel"), bpy.data.materials.new("Steel.001")
me.materials.append(m1); me.materials.append(m2)
for p in me.polygons: p.material_index = 0
base = sum(1 for m in bpy.data.meshes if m.users == 0)
bpy.data.meshes.new("orphan_mesh")
rep = call("scene_cleanup", objects=["Hex Thing.001"])
rep0 = rep["report"][0]
res = call("scene_cleanup", objects=["Hex Thing.001"], plan_only=False, ngon_policy="triangulate", steps=["ngons", "purge_orphans", "naming", "materials_uvs"],
           convention={"suffix": "_geo", "lowercase": True, "replace_spaces": "_", "strip_numeric_suffix": True})
new = bpy.data.objects[res["branch"]["Hex Thing.001"]]
print("RESULT", json.dumps({"rep0": rep0, "orphans": rep["orphans"], "base": base, "res": res, "name": new.name, "faces": len(new.data.polygons), "slots": len(new.data.materials), "orph_after": sum(1 for m in bpy.data.meshes if m.users == 0)}))
'''))
    r0 = d["rep0"]
    assert r0["ngons"] == 1 and r0["materials"] == {"slots": 2, "unused": 1, "duplicates": [["Steel", "Steel.001"]]} and d["orphans"]["meshes"] == d["base"] + 1
    assert d["name"] == "hex_thing_geo" and d["faces"] == 4 and d["slots"] == 1 and d["orph_after"] == 0
    steps = [a["step"] for a in d["res"]["applied"]]
    assert steps == ["ngons", "purge_orphans", "naming", "materials_uvs"]
