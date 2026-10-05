# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Client workflows from Stefan's wiki (engine-asset-acceptance, geometry-game-mesh-preparation, rigging-existing-armor): each is a
checklist turned into measured gates on real data, composed from the proven feature code. Nothing here calls a model."""

from features_support import run


def test_mesh_prep_branches_the_source_records_its_hash_and_repairs_only_the_defects_it_reports(tmp_path):
    r = run(tmp_path, '''
src = boxes("helm", [((0, 0, 0), (1, 1, 1)), ((3, 0, 0), (0.2, 0.2, 0.2))])
bm = bmesh.new(); bm.from_mesh(src.data)
bm.verts.new((9, 9, 9))                                    # a loose vertex
dup = bmesh.ops.duplicate(bm, geom=[f for f in bm.faces][:1])  # a doubled face's vertices
bm.to_mesh(src.data); bm.free()
before = (len(src.data.vertices), len(src.data.polygons))
res = call("mesh_prep", object="helm")
prep = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "src_unchanged": (len(src.data.vertices), len(src.data.polygons)) == before,
                            "prep_hash": prep.get("lw_source_hash") if prep else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["object"] == "helm_prep" and out["src_unchanged"] is True
    assert len(res["source_hash"]) == 64 and out["prep_hash"] == res["source_hash"]
    assert res["found"]["loose_vertices"] >= 1 and res["after"]["loose_vertices"] == 0
    assert res["after"]["shells"] <= res["before"]["shells"]
    assert res["dimensions"] and res["pivot_offset_from_bounds_centre"] is not None


def test_asset_acceptance_gates_pass_a_clean_copy_and_fail_a_flipped_and_a_drifting_one(tmp_path):
    r = run(tmp_path, '''
ref = boxes("ref", [((0, 0, 0), (1, 1, 1))])
good = boxes("good", [((0, 0, 0), (1, 1, 1))])
bad = boxes("bad", [((0.8, 0, 0), (1, 1, 1.6))])
bm = bmesh.new(); bm.from_mesh(bad.data); bmesh.ops.reverse_faces(bm, faces=bm.faces[:]); bm.to_mesh(bad.data); bm.free()
a = call("asset_acceptance", object="good", reference="ref")
b = call("asset_acceptance", object="bad", reference="ref")
print("RESULT", json.dumps({"a": a, "b": b}))
''')
    assert r.rc == 0, r.out[-2500:]
    a, b = r.results[0]["a"], r.results[0]["b"]
    assert a["ok"] is True and a["accepted"] is True and set(a["gates"]) == {"identity", "orientation", "geometry", "materials"}
    assert all(g["pass"] for g in a["gates"].values()), a["gates"]
    assert b["ok"] is True and b["accepted"] is False
    assert b["gates"]["geometry"]["pass"] is False and "inverted" in " ".join(b["gates"]["geometry"]["reasons"])
    assert b["gates"]["orientation"]["pass"] is False, "bounds drifted off the reference"


def test_rig_armor_fits_a_rigid_plate_to_one_bone_on_a_copy_and_reports_pose_stretch(tmp_path):
    r = run(tmp_path, '''
body = humanoid("body")
call("auto_rig", object="body", kind="humanoid")
plate = boxes("plate", [((0, -0.2, 1.15), (0.5, 0.06, 0.5))])
res = call("rig_armor", object="plate", armature="body_rig", bone="spine_03")
fit = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "plate_vg": [g.name for g in plate.vertex_groups], "fit_vg": [g.name for g in fit.vertex_groups] if fit else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["object"] == "plate_fit" and res["mode"] == "rigid"
    assert out["plate_vg"] == [] and out["fit_vg"] == ["spine_03"], "the original is never bound"
    assert len(res["poses"]) >= 2 and all(p["max_edge_stretch"] < 1.001 for p in res["poses"])
    assert res["accepted"] is True
