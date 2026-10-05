# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_validate (shelf/fit_validate.md section 10): the pure measurement functions in-process, and the measure/judge stages in the real binary on synthetic pieces."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from blender_run import run_script  # noqa: E402
from mixar.modules.lampway_tools.pipeline import validate as V  # noqa: E402
from test_wave3_weights import PRE  # noqa: E402


def _cube(n=2):
    g = np.array([[x, y, z] for x in (0, 1) for y in (0, 1) for z in (0, 1)], float)
    return g


def test_rigid_fit_recovers_a_rotation_and_a_uniform_scale_and_reports_the_residual():
    P = _cube() - 0.5
    th = np.radians(30)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    Q = 1.02 * (P @ R.T) + np.array([0.3, -0.2, 0.1])
    fit = V.rigid_fit(P, Q)
    assert fit["scale"] == pytest.approx(1.02, abs=1e-9) and fit["rms_m"] < 1e-9 and fit["max_m"] < 1e-9
    Q[3] += 0.005                                               # one vertex moved 5 mm: the residual shows it
    bent = V.rigid_fit(P, Q)
    assert bent["max_m"] > 0.003 and bent["rms_m"] > 0.001


def test_edge_strain_is_percent_change_and_a_breathing_scale_fails_the_rigid_test_because_scale_is_never_fitted_per_pose():
    P = _cube()
    edges = np.array([[0, 1], [0, 2], [0, 4], [1, 3], [2, 3], [4, 5], [4, 6], [5, 7], [6, 7], [1, 5], [2, 6], [3, 7]])
    s = V.edge_strain(P, 1.01 * P, edges)
    assert s["max_pct"] == pytest.approx(1.0, abs=1e-6)
    j = V.judge("metal", {"rigid_residual_mm": 0.0, "strain_max_pct": s["max_pct"] + 0.5, "seam_gap_mm_max": 0.0}, {"status": "proposed", "metal": {"rigid_max_mm": 1.0, "strain_max_pct": 1.0}})
    assert j["verdict"] == "FAIL" and "strain_max_pct" in j["over"]


def test_the_verdict_words_and_the_never_a_bare_pass_rule():
    lim = {"status": "proposed", "metal": {"rigid_max_mm": 1.0, "strain_max_pct": 1.0, "seam_gap_mm": 1.0}}
    ok = V.judge("metal", {"rigid_residual_mm": 0.2, "strain_max_pct": 0.1, "seam_gap_mm_max": 0.0}, lim)
    assert ok["verdict"] == "PASS" and ok["limits_status"] == "proposed"
    un = V.judge("cloth", {"rigid_residual_mm": 5.0, "strain_max_pct": 40, "seam_gap_mm_max": 0.0}, lim)
    assert un["verdict"] == "UNVERIFIED" and un["missing"] == ["limits for cloth"]
    s = V.summarize([ok, un], crossing_control_ok=True)
    assert s["ok"] is False and s["counts"]["UNVERIFIED"] == 1 and "PASS under proposed limits" not in s["note"]
    s2 = V.summarize([ok], crossing_control_ok=True)
    assert s2["ok"] is True and "PASS under proposed limits" in s2["note"]
    s3 = V.summarize([ok], crossing_control_ok=False)
    assert s3["ok"] is False and s3["counts"]["UNPROVEN"] == 1


def test_bind_mismatch_is_zero_for_the_identity_and_names_the_bone_that_differs():
    bind = {"pelvis": {"rot": [0, 0, 0, 1], "pos": [0, 0, 90], "scale": [1, 1, 1]}, "spine_01": {"rot": [0, 0, 0, 1], "pos": [0, 0, 10], "scale": [1, 1, 1]}}
    assert V.bind_mismatch(bind, bind)["over_tolerance"] == []
    own = {k: dict(v) for k, v in bind.items()}
    own["spine_01"] = {"rot": [0.0, 0.7071068, 0.0, 0.7071068], "pos": [0, 0, 10.5], "scale": [1, 1, 1]}
    bad = V.bind_mismatch(bind, own)
    assert [r["bone"] for r in bad["over_tolerance"]] == ["spine_01"] and bad["over_tolerance"][0]["rot_deg"] == pytest.approx(90, abs=0.01) and bad["over_tolerance"][0]["pos_cm"] == pytest.approx(0.5)


def test_a_wrong_sign_pose_is_refused_and_the_expect_check_names_why():
    exp = {"bone": "wrist_r", "axis": "up", "min_deg": 20}
    assert V.check_expect(exp, {"wrist_r": {"up_deg": 30}})["ok"] is True
    assert V.check_expect(exp, {"wrist_r": {"up_deg": -30}})["ok"] is False


def test_the_crossing_control_pushes_the_piece_into_the_skin_and_must_see_it():
    body_c = np.array([[0.0, 0, 0]])
    piece = np.array([[0.02, 0, 0], [0.5, 0, 0]])
    shifted = V.control_shift(piece, np.array([[1.0, 0, 0], [1.0, 0, 0]]), depth_m=0.01, nearest_idx=np.array([0]))
    assert shifted[0][0] == pytest.approx(0.02 - 0.01) and shifted[1][0] == pytest.approx(0.5)      # only the nearest vertex is pushed (-normal), into the skin


def _measure_script(extra):
    return PRE + r'''
from mixar.modules.lampway_tools.pipeline import validate as VV
def cube(name, s=0.2, loc=(0, 0, 1)):
    bm = bmesh.new(); bmesh.ops.create_cube(bm, size=s)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    ob = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(ob); ob.location = loc
    return ob
''' + extra


def test_a_rigid_cube_on_one_bone_passes_and_the_same_cube_with_blended_weights_fails_under_the_proposed_metal_limits():
    r = run_script(_measure_script('''
arm = armature()
orig = cube("orig"); rigid = cube("rigid"); weights(rigid, arm, lambda c: {"upperarm_l": 1.0})
blend = cube("blend"); weights(blend, arm, lambda c: {"spine_03": 0.5 + 0.5 * (c.x > 1.0e9), "upperarm_l": 0.5 if c.z - 1 < 0 else 0.9})
for v in blend.data.vertices: pass
bmesh_obj = blend
poses = [{"name": "rest"}, {"name": "arm_up", "bone": "upperarm_l", "rotate": [60, 0, 0]}]
a = api.fit_validate("measure", piece="p", bound="rigid", original="orig", poses=poses, roles={"p": "metal"})
b = api.fit_validate("measure", piece="p", bound="blend", original="orig", poses=poses, roles={"p": "metal"})
res({"a": a, "b": b})
'''), timeout=300)
    assert r.rc == 0, r.out[-1500:]
    a, b = r.results[-1]["a"], r.results[-1]["b"]
    pa = a["poses"][1]["pieces"]["p"]
    assert pa["rigid_residual_mm"] < 0.05 and pa["judge"]["verdict"] == "PASS" and a["rest_fidelity"]["scale"] == pytest.approx(1.0, abs=1e-6)
    assert b["poses"][1]["pieces"]["p"]["judge"]["verdict"] == "FAIL", b["poses"][1]["pieces"]["p"]


def test_the_original_is_required_and_a_scaled_original_reads_back_its_scale():
    r = run_script(_measure_script('''
arm = armature()
orig = cube("orig", s=0.2); piece = cube("piece", s=0.204); weights(piece, arm, lambda c: {"upperarm_l": 1.0})
a = api.fit_validate("measure", piece="p", bound="piece", original="orig", poses=[{"name": "rest"}], roles={"p": "metal"})
b = api.fit_validate("measure", piece="p", bound="piece", poses=[{"name": "rest"}], roles={"p": "metal"})
res({"a": a["rest_fidelity"], "b": b.get("error")})
'''), timeout=300)
    d = r.results[-1]
    assert d["a"]["scale"] == pytest.approx(1.02, abs=1e-4) and d["a"]["rms_mm"] < 0.05
    assert "original" in d["b"] and "baked rest" in d["b"]


def test_a_cloth_piece_with_no_limits_is_unverified_never_pass_and_the_limits_status_is_echoed():
    r = run_script(_measure_script('''
arm = armature()
orig = cube("orig"); piece = cube("piece"); weights(piece, arm, lambda c: {"upperarm_l": 1.0})
a = api.fit_validate("measure", piece="p", bound="piece", original="orig", poses=[{"name": "rest"}], roles={"p": "cloth"})
res({"v": a["poses"][0]["pieces"]["p"]["judge"], "sum": a["summary"], "limits": a["limits"]["status"]})
'''), timeout=300)
    d = r.results[-1]
    assert d["v"]["verdict"] == "UNVERIFIED" and d["limits"] == "proposed" and d["sum"]["ok"] is False


def test_a_pose_whose_expect_fails_is_refused_and_nothing_is_measured():
    r = run_script(_measure_script('''
arm = armature()
orig = cube("orig"); piece = cube("piece"); weights(piece, arm, lambda c: {"upperarm_l": 1.0})
a = api.fit_validate("measure", piece="p", bound="piece", original="orig", roles={"p": "metal"},
                     poses=[{"name": "wrong_way", "bone": "upperarm_l", "rotate": [-60, 0, 0], "expect": {"bone": "upperarm_l", "axis": "x", "min_deg": 20}}])
res(a["poses"][0])
'''), timeout=300)
    d = r.results[-1]
    assert d["verdict"] == "REFUSED" and d["pieces"] == {} and "expect" in d["why"]


def test_a_pose_that_breathes_the_part_one_percent_fails_the_rigid_residual_because_scale_is_never_fitted_per_pose():
    r = run_script(_measure_script('''
arm = armature()
orig = cube("orig", s=0.2, loc=(0, 0, 1.4)); piece = cube("piece", s=0.2, loc=(0, 0, 1.4)); weights(piece, arm, lambda c: {"upperarm_l": 1.0})
a = api.fit_validate("measure", piece="p", bound="piece", original="orig", roles={"p": "metal"},
                     poses=[{"name": "rest"}, {"name": "breathe", "bone": "upperarm_l", "rotate": [0, 0, 0], "scale": 1.05}])
res({"rest": a["poses"][0]["pieces"]["p"]["rigid_residual_mm"], "breathe": a["poses"][1]["pieces"]["p"]["rigid_residual_mm"]})
'''), timeout=300)
    d = r.results[-1]
    assert d["rest"] < 0.01 and d["breathe"] > 2.0, d            # a 5 % scale of a 0.2 m cube about 0.4 m away from the bone head is millimetres of residual
