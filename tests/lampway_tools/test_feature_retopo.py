# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Retopology (Mixar docs: "Retopology creates a new mesh with a different polygon layout or density ... keep the original until
the replacement passes your checks"). Proven code: Blender's QuadriFlow, voxel remesh as the fallback; a measured report
(face count against the target, open boundary, non-manifold edges, surface deviation) instead of a claim. The studio slot
(Tripo retopology) answers with the action and price for approval; it never clicks."""

from features_support import run


def test_quadriflow_makes_a_new_all_quad_mesh_near_the_target_and_leaves_the_original(tmp_path):
    r = run(tmp_path, '''
src = sphere("dense", 0.5, subdiv=5)
before = len(src.data.polygons)
res = call("retopo", object="dense", target_faces=600)
new = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "before": before, "after_src": len(src.data.polygons),
                            "new_faces": len(new.data.polygons) if new else None,
                            "quads": sum(1 for p in new.data.polygons if len(p.vertices) == 4) if new else None,
                            "src_hidden": src.hide_get(), "new_name": new.name if new else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["method"] == "quadriflow" and out["new_name"] == "dense_retopo"
    assert out["after_src"] == out["before"], "the original is untouched"
    assert abs(out["new_faces"] - 600) / 600 < 0.35 and out["quads"] / out["new_faces"] > 0.9
    rep = res["report"]
    assert rep["faces"] == out["new_faces"] and rep["non_manifold_edges"] == 0 and rep["open_boundary_edges"] == 0
    assert 0 <= rep["mean_deviation"] < 0.01 and rep["max_deviation"] < 0.05, rep


def test_voxel_is_the_fallback_method_and_reports_the_same_fields(tmp_path):
    r = run(tmp_path, '''
src = sphere("dense", 0.5, subdiv=4)
res = call("retopo", object="dense", target_faces=800, method="voxel")
print("RESULT", json.dumps(res))
''')
    res = r.results[0]
    assert res["ok"] is True and res["method"] == "voxel" and res["report"]["faces"] > 100


def test_a_studio_engine_answers_with_the_action_and_price_for_approval_and_changes_nothing(tmp_path):
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=3)
res = call("retopo", object="dense", engine="studio:tripo")
print("RESULT", json.dumps({"res": res, "objects": sorted(o.name for o in bpy.data.objects)}))
''')
    out = r.results[0]
    assert out["res"]["ok"] is False and out["res"]["needs_approval"] is True
    assert out["res"]["studio"] == "tripo" and out["res"]["action"] and "credits" in out["res"]["price"]
    assert out["res"]["studio_action"] is None and "no Tripo Studio driver" in out["res"]["how"], "the shelf has no retopology driver yet: say so"
    assert out["objects"] == ["dense"]


def test_a_missing_object_and_a_too_small_target_are_refused_with_the_reason(tmp_path):
    r = run(tmp_path, '''
sphere("dense", 0.5, subdiv=3)
print("RESULT", json.dumps({"a": call("retopo", object="nope"), "b": call("retopo", object="dense", target_faces=3)}))
''')
    out = r.results[0]
    assert out["a"]["ok"] is False and "nope" in out["a"]["error"]
    assert out["b"]["ok"] is False and "target_faces" in out["b"]["error"]
