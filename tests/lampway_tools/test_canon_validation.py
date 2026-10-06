# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 05 receipts in their pure form (goldens C01 breathe, C03 seam ledger, C07 expectation sign, C14 capped control).

pipeline/validate judges under canon 05's limits (Titan recipes/armour-limits.json, status PROPOSED, needs_decision);
canon_geom builds the source seam ledger, measures it, and counts surface crossings of segments through triangles."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens, obj, tris  # noqa: E402,F401
from mixar.modules.lampway_tools import canon_geom as G  # noqa: E402
from mixar.modules.lampway_tools.pipeline import validate as V  # noqa: E402


# ------------------------------------------------------------------ limits and the verdict (canon 05 B.10, H)
def test_the_default_limits_are_titans_adopted_by_the_captain_and_name_only_the_decisions_still_owed():
    lim = V.DEFAULT_LIMITS                                # the captain, 2026-10-06: "go with Titans fit limit"
    assert lim["status"] == "adopted" and lim["metal"] == {"rigid_max_mm": 0.5, "strain_p95": 0.01} and lim["body"] == {"crossings": 0}
    assert "leather" not in lim and "cloth" not in lim and "embroidery" not in lim
    owed = " ".join(lim["needs_decision"])
    assert "metal" not in owed and "leather" in owed and "seam" in owed


def test_g05_1_breathing_fails_the_metal_rigid_limit_and_a_scaled_fit_would_have_passed_it(goldens):
    inp = J(goldens, "C01_rigid/input.json")
    P, Q = np.array(inp["P"]), np.array(inp["Q_breathe_1pct"])
    rigid = V.rigid_fit(P, Q, with_scale=False)
    j = V.judge("metal", {"rigid_max_mm": rigid["max_m"] * 1000, "strain_p95": 0.0, "crossings": 0})
    assert rigid["max_m"] * 1000 >= 0.975 and j["verdict"] == "FAIL" and j["over"] == ["rigid_max_mm"]
    scaled = V.rigid_fit(P, Q, with_scale=True)
    assert V.judge("metal", {"rigid_max_mm": scaled["max_m"] * 1000, "strain_p95": 0.0, "crossings": 0})["verdict"] == "PASS"


def test_a_residual_between_the_old_placeholder_and_the_canons_limit_now_fails():
    j = V.judge("metal", {"rigid_max_mm": 0.7, "strain_p95": 0.001, "crossings": 0})
    assert j["verdict"] == "FAIL" and j["limits_status"] == "adopted"


def test_strain_is_judged_at_its_p95_and_a_body_crossing_fails_any_role_with_limits():
    assert V.judge("metal", {"rigid_max_mm": 0.1, "strain_p95": 0.02, "crossings": 0})["over"] == ["strain_p95"]
    assert V.judge("metal", {"rigid_max_mm": 0.1, "strain_p95": 0.0, "crossings": 3})["over"] == ["crossings"]


def test_g05_6_a_role_without_limits_or_a_missing_metric_is_unverified_never_pass():
    assert V.judge("cloth", {"rigid_max_mm": 0.0, "strain_p95": 0.0, "crossings": 0})["verdict"] == "UNVERIFIED"
    j = V.judge("metal", {"rigid_max_mm": 0.1, "crossings": 0})
    assert j["verdict"] == "UNVERIFIED" and j["missing"] == ["strain_p95"]


def test_strain_is_a_fraction_and_a_zero_length_rest_edge_is_refused():
    P = np.array([[0.0, 0, 0], [1, 0, 0], [0, 2, 0]])
    s = V.edge_strain(P, np.array([[0.0, 0, 0], [1, 0, 0], [0, 2.2, 0]]), np.array([[0, 1], [0, 2]]))
    assert s["max"] == pytest.approx(0.1) and s["p95"] <= s["max"]
    with pytest.raises(ValueError, match="rest length"):
        V.edge_strain(np.array([[0.0, 0, 0], [0, 0, 0]]), np.zeros((2, 3)), np.array([[0, 1]]))


# ------------------------------------------------------------------ G05.2: the source seam ledger (C03)
def _c03(goldens):
    V_, F, _, _, groups = obj(goldens, "C03_seam_tube/piece.obj")
    part = np.full(len(V_), -1)
    for k, name in enumerate(("lower", "upper")):
        for f in groups[name]:
            for v in F[f]:
                part[v] = k
    return V_, F, part, J(goldens, "C03_seam_tube/rig.json"), J(goldens, "C03_seam_tube/expected.json")


def test_g05_2_the_ledger_is_the_exact_coordinate_pairs_across_parts(goldens):
    V_, F, part, rig, exp = _c03(goldens)
    led = G.seam_ledger(V_, part)
    assert len(led) == exp["seam_ledger_pairs"]
    assert {tuple(sorted(p)) for p in led} == {tuple(sorted(p)) for p in rig["seam_pairs_source_ledger"]}


def _twist(rig):
    head = np.array(rig["bones"]["spine_03"]["head"])
    a = math.radians(rig["pose"]["spine_03"]["deg"])
    Mt = np.eye(4)
    Mt[:3, :3] = [[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]]
    Mt[:3, 3] = head - Mt[:3, :3] @ head
    return Mt


def test_g05_2_per_part_bones_open_every_pair_and_the_ledger_sees_it(goldens):
    V_, F, part, rig, exp = _c03(goldens)
    led = G.seam_ledger(V_, part)
    posed = V_.copy()
    up = part == 1
    posed[up] = (_twist(rig)[:3, :3] @ V_[up].T).T + _twist(rig)[:3, 3]
    m = G.seam_gaps(posed, led, threshold=0.002)
    assert m["max"] == pytest.approx(exp["per_part_bones"]["seam_gap_max_m"], abs=1e-6) and m["open"] == 32 and m["pairs"] == 32


def test_g05_2_falsifier_a_seam_set_taken_from_distances_in_the_posed_mesh_finds_nothing(goldens):
    V_, F, part, rig, exp = _c03(goldens)
    posed = V_.copy()
    up = part == 1
    posed[up] = (_twist(rig)[:3, :3] @ V_[up].T).T + _twist(rig)[:3, 3]
    near = [(i, j) for i in np.flatnonzero(part == 0) for j in np.flatnonzero(part == 1) if np.linalg.norm(posed[i] - posed[j]) < 0.002]
    assert len(near) < exp["seam_ledger_pairs"]                       # the opened seam is invisible to a proximity seam set


def test_an_unlabelled_vertex_or_a_wrong_count_is_refused():
    with pytest.raises(ValueError, match="part"):
        G.seam_ledger(np.zeros((3, 3)), np.array([0, 1]))


# ------------------------------------------------------------------ G05.3: the capped crossing control (C14) on a mesh body
def _sphere_body(goldens):
    Vb, Fb, *_ = obj(goldens, "C05_clearance/sphere.obj")
    return Vb, tris(Fb)


def _edges(F):
    return np.array(sorted({tuple(sorted((a, b))) for f in F for a, b in zip(f, list(f[1:]) + [f[0]])}))


def test_g05_3_the_capped_control_crosses_the_body_surface_and_the_uncapped_one_does_not(goldens):
    exp = J(goldens, "C14_controls/expected.json")
    Vp, Fp, *_ = obj(goldens, "C14_controls/rivet.obj")
    Vb, Tb = _sphere_body(goldens)
    E = _edges(Fp)
    d, loc, _tri = G.closest_points(Vb, Tb, Vp)
    shift = np.array(G.control_shift(list(zip(map(tuple, Vp), map(tuple, loc))), 0.01))
    capped = G.segment_crossings(Vp[E[:, 0]] + shift, Vp[E[:, 1]] + shift, Vb, Tb)
    assert int(capped.sum()) >= exp["capped_half_extent"]["surface_crossing_edges_min"]
    u = shift / np.linalg.norm(shift)
    uncapped = G.segment_crossings(Vp[E[:, 0]] + 0.01 * u, Vp[E[:, 1]] + 0.01 * u, Vb, Tb)
    assert int(uncapped.sum()) == exp["uncapped_1cm"]["surface_crossing_edges"]


def test_segment_crossings_see_a_face_interior_crossing_with_both_ends_outside_and_ignore_a_miss():
    Vb = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0]])
    Tb = np.array([[0, 1, 2]])
    hits = G.segment_crossings(np.array([[0.2, 0.2, -1.0], [2.0, 2.0, -1.0], [0.2, 0.2, 0.5]]), np.array([[0.2, 0.2, 1.0], [2.0, 2.0, 1.0], [0.2, 0.2, 1.5]]), Vb, Tb)
    assert hits.tolist() == [True, False, False]


# ------------------------------------------------------------------ G05.5: the expectation is measured on the posed joints (C07)
def test_g05_5_lowering_the_arm_moves_the_elbow_down_and_the_negated_axis_is_refused(goldens):
    rig = J(goldens, "C07_pose_solve/rig.json")
    sh = np.array(rig["shoulder"])
    a = math.radians(-40.0)
    elbow = sh + rig["upperarm_length_m"] * np.array([math.cos(a), 0, math.sin(a)])
    ref = {"upperarm_l": {"parent": None, "rot": (0.0, 0, 0, 1), "pos": tuple(sh)}, "lowerarm_l": {"parent": "upperarm_l", "rot": (0.0, 0, 0, 1), "pos": tuple(elbow)}}
    rest = {b: t["pos"] for b, t in ref.items()}
    frame = {"up": (0.0, 0.0, 1.0), "forward": (0.0, -1.0, 0.0)}
    expect = {"joint": "lowerarm_l", "along": "-up", "min_cm": 2.0}
    for axis, ok_want in ((rig["dof"]["axis_world"], True), ([-x for x in rig["dof"]["axis_world"]], False)):
        posed = {b: t["pos"] for b, t in G.pose_cs(ref, [{"bone": "upperarm_l", "axis": axis, "deg": 20.0}]).items()}
        ok, got = G.check_expect(expect, rest, posed, frame, scale_to_cm=100.0)
        assert ok is ok_want, (axis, got)
