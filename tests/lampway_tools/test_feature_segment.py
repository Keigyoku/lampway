# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh Segment (Mixar docs: "select the mesh and use Mesh Segment to create separate part objects ... it is not simply renaming the
original mesh; keep a saved copy"). Proven code: connected shells, region growing across smooth edges (dihedral angle), UV
islands; small regions are merged into the neighbour they share the longest border with. The parts are real objects in a
collection, with the original hidden, never deleted."""

from features_support import run


def test_shells_split_a_figure_into_its_connected_parts_largest_first(tmp_path):
    r = run(tmp_path, '''
src = humanoid("body")
res = call("segment_mesh", object="body", method="shells")
parts = [bpy.data.objects[p["object"]] for p in res.get("parts", [])]
print("RESULT", json.dumps({"res": res, "src_faces": len(src.data.polygons), "sum_faces": sum(len(o.data.polygons) for o in parts),
                            "src_hidden": src.hide_get(), "coll": [c.name for c in bpy.data.collections],
                            "in_coll": sorted(o.name for o in bpy.data.collections["body_parts"].objects) if "body_parts" in bpy.data.collections else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and len(res["parts"]) == 6 and out["sum_faces"] == out["src_faces"]
    assert out["src_hidden"] is True and "body_parts" in out["coll"] and len(out["in_coll"]) == 6
    sizes = [p["faces"] for p in res["parts"]]
    assert sizes == sorted(sizes, reverse=True)
    assert all(set(p) >= {"object", "faces", "area", "center", "size"} for p in res["parts"])


def test_sharp_edges_split_a_connected_mesh_into_its_flat_regions(tmp_path):
    r = run(tmp_path, '''
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
me = bpy.data.meshes.new("cube"); bm.to_mesh(me); bm.free()
ob = link(bpy.data.objects.new("cube", me))
res = call("segment_mesh", object="cube", method="sharp", angle=40)
print("RESULT", json.dumps({"res": res, "faces": len(me.polygons)}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is True and len(out["res"]["parts"]) == 6
    assert {p["faces"] for p in out["res"]["parts"]} == {out["faces"] // 6}


def test_uv_islands_are_a_method_and_small_regions_merge_into_a_neighbour(tmp_path):
    r = run(tmp_path, '''
bm = bmesh.new()
bmesh.ops.create_cube(bm, size=1.0)
bmesh.ops.subdivide_edges(bm, edges=bm.edges[:], cuts=3, use_grid_fill=True)
me = bpy.data.meshes.new("cube"); bm.to_mesh(me); bm.free()
link(bpy.data.objects.new("cube", me))
uv = call("uv_unwrap", object="cube", method="angle", angle_limit=40)
by_uv = call("segment_mesh", object=uv["object"], method="uv_islands")
merged = call("segment_mesh", object="cube", method="sharp", angle=40, min_faces=20)
print("RESULT", json.dumps({"by_uv": len(by_uv["parts"]), "merged": len(merged["parts"]), "merged_faces": sorted(p["faces"] for p in merged["parts"])}))
''')
    out = r.results[0]
    assert out["by_uv"] == 6
    assert out["merged"] == 1 and out["merged_faces"] == [96], "every 16-face region is below min_faces=20 and ends up in one part"


def test_studio_slot_and_bad_arguments(tmp_path):
    r = run(tmp_path, '''
humanoid("body")
print("RESULT", json.dumps({"studio": call("segment_mesh", object="body", engine="studio:tripo"),
                            "bad": call("segment_mesh", object="body", method="magic"),
                            "no_uv": call("segment_mesh", object="body", method="uv_islands")}))
''')
    out = r.results[0]
    assert out["studio"]["needs_approval"] is True and out["studio"]["studio"] == "tripo"
    assert out["bad"]["ok"] is False and "magic" in out["bad"]["error"]
    assert out["no_uv"]["ok"] is False and "UV" in out["no_uv"]["error"]
