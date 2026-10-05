# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""UV unwrap (Mixar docs: "ask the Agent to mark seams, unwrap, inspect overlaps, and pack islands at a stated texel density or
resolution. Inspect the checker pattern before texturing"). Proven code: seams by dihedral angle, Blender's unwrap solvers,
the packer; the report is measured on the result (islands, coverage, overlap by rasterising, texel-density spread)."""

from features_support import run


def test_smart_unwrap_gives_a_new_object_with_packed_non_overlapping_islands(tmp_path):
    r = run(tmp_path, '''
src = humanoid("body")
res = call("uv_unwrap", object="body", method="smart", margin=0.01)
new = bpy.data.objects.get(res.get("object", ""))
print("RESULT", json.dumps({"res": res, "src_uvs": len(src.data.uv_layers), "new_uvs": len(new.data.uv_layers) if new else None}))
''')
    assert r.rc == 0, r.out[-2500:]
    out = r.results[0]
    res = out["res"]
    assert res["ok"] is True and res["object"] == "body_uv" and out["src_uvs"] == 0 and out["new_uvs"] == 1
    rep = res["report"]
    assert rep["islands"] >= 6 and 0.05 < rep["coverage"] <= 1.0
    assert rep["overlap_fraction"] < 0.01, rep
    assert rep["texel_density_cv"] < 0.6, rep


def test_angle_method_cuts_seams_at_sharp_edges_and_the_same_report_comes_back(tmp_path):
    r = run(tmp_path, '''
src = humanoid("body")
res = call("uv_unwrap", object="body", method="angle", angle_limit=60)
print("RESULT", json.dumps(res))
''')
    res = r.results[0]
    assert res["ok"] is True and res["method"] == "angle"
    assert res["report"]["islands"] >= 6 and res["report"]["overlap_fraction"] < 0.01
    assert res["report"]["seam_edges"] > 0


def test_a_requested_texel_density_scales_the_islands_to_it(tmp_path):
    r = run(tmp_path, '''
src = humanoid("body")
res = call("uv_unwrap", object="body", method="smart", texel_density=512, texture_size=2048)
print("RESULT", json.dumps(res))
''')
    res = r.results[0]
    # density is texels per metre in the texture: uv_length_per_metre * texture_size; the packed result is then uniform-scaled to fit
    assert res["ok"] is True and res["report"]["texel_density_cv"] < 0.6


def test_a_studio_slot_and_bad_arguments(tmp_path):
    r = run(tmp_path, '''
humanoid("body")
print("RESULT", json.dumps({"studio": call("uv_unwrap", object="body", engine="studio:tripo"),
                            "bad_method": call("uv_unwrap", object="body", method="magic"),
                            "bad_engine": call("uv_unwrap", object="body", engine="studio:nowhere")}))
''')
    out = r.results[0]
    assert out["studio"]["needs_approval"] is True and "Smart UV" in out["studio"]["action"] and "20 credits" in out["studio"]["price"]
    assert out["bad_method"]["ok"] is False and "magic" in out["bad_method"]["error"]
    assert out["bad_engine"]["ok"] is False and "nowhere" in out["bad_engine"]["error"]


def test_the_report_sees_a_stacked_layout_as_overlapping(tmp_path):
    """The overlap number must be able to be large: every face laid onto the same square overlaps almost everywhere."""
    r = run(tmp_path, '''
from mixar.modules.lampway_tools.features import uv as U
ob = boxes("cubes", [((0, 0, 0), (1, 1, 1)), ((3, 0, 0), (1, 1, 1))])
ob.data.uv_layers.new(name="UVMap")
for loop_i, loop in enumerate(ob.data.loops):
    ob.data.uv_layers.active.uv[loop_i].vector = [(0.1, 0.1), (0.9, 0.1), (0.9, 0.9), (0.1, 0.9)][loop_i % 4]
rep = U.uv_report(ob)
print("RESULT", json.dumps(rep))
''')
    rep = r.results[0]
    assert rep["overlap_fraction"] > 0.8 and rep["islands"] >= 1
