# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_geom against the algorithm canon's goldens (specs/canon goldens C01, C02, C05, C06, C08, C09).

Each test loads a generated golden case and its expected.json, runs the canon_geom primitive and compares within the
case's tolerance; where the canon ships a reference implementation (reference.py) the primitive is also compared with it.
Each case's FALSIFIER (the known-wrong method the canon names) is a second test showing that method fails the golden.
"""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens, obj, reference as REF, tris  # noqa: E402,F401
from mixar.modules.lampway_tools import canon_geom as G  # noqa: E402


# ------------------------------------------------------------------ C01: similarity (canon 02)
def test_c01_similarity_recovers_scale_rotation_axis_translation(goldens):
    inp, exp = J(goldens, "C01_rigid/input.json"), J(goldens, "C01_rigid/expected.json")
    f = G.similarity_fit(np.array(inp["P"]), np.array(inp["Q_similar"]))
    e = exp["Q_similar"]
    ang, ax = G.rotation_angle_axis(f["R"])
    assert abs(f["s"] - e["scale"]) < e["tol"] and abs(ang - e["rotation_deg"]) < 1e-6
    assert np.allclose(ax, e["axis"], atol=1e-6) and np.allclose(f["t"], e["translation_m"], atol=1e-6)
    assert f["rms"] < 1e-6 and f["max"] < 1e-6 and f["p95"] < 1e-6 and f["n"] == 40 and f["with_scale"] is True


def test_c01_a_mirror_gets_a_proper_rotation_and_shows_as_residual(goldens):
    inp, exp = J(goldens, "C01_rigid/input.json"), J(goldens, "C01_rigid/expected.json")
    f = G.similarity_fit(np.array(inp["P"]), np.array(inp["Q_mirror"]))
    assert np.linalg.det(f["R"]) > 0.999 and f["rms"] > exp["Q_mirror"]["rms_m_min"]


def test_c01_breathing_is_seen_by_the_rigid_fit_and_hidden_by_a_scaled_one(goldens):
    inp, exp = J(goldens, "C01_rigid/input.json"), J(goldens, "C01_rigid/expected.json")
    P, Q = np.array(inp["P"]), np.array(inp["Q_breathe_1pct"])
    rigid, scaled = G.similarity_fit(P, Q, with_scale=False), G.similarity_fit(P, Q, with_scale=True)
    assert rigid["s"] == 1.0 and rigid["max"] >= exp["Q_breathe_1pct"]["with_scale_false_max_m_min"]
    assert scaled["rms"] < 1e-9 and abs(scaled["s"] - 1.01) < 1e-9


def test_c01_one_vertex_moved_5mm_shows_in_max_and_p95_not_only_rms(goldens):
    inp, exp = J(goldens, "C01_rigid/input.json"), J(goldens, "C01_rigid/expected.json")
    f = G.similarity_fit(np.array(inp["P"]), np.array(inp["Q_one_vertex_5mm"]))
    e = exp["Q_one_vertex_5mm"]
    assert e["max_m_min"] <= f["max"] <= e["max_m_max"] and f["rms"] <= e["rms_m_max"] + 1e-12


def test_c01_matches_the_canon_reference_on_every_target(goldens):
    inp = J(goldens, "C01_rigid/input.json")
    P = np.array(inp["P"])
    for key in ("Q_similar", "Q_mirror", "Q_breathe_1pct", "Q_one_vertex_5mm"):
        for ws in (True, False):
            a, b = G.similarity_fit(P, np.array(inp[key]), with_scale=ws), REF.similarity_fit(P, np.array(inp[key]), with_scale=ws)
            assert np.allclose(a["R"], b["R"], atol=1e-12) and abs(a["s"] - b["s"]) < 1e-12 and np.allclose(a["t"], b["t"], atol=1e-12)


def test_similarity_refuses_too_few_collinear_or_non_finite_points():
    line = np.array([[0.0, 0, 0], [1, 0, 0], [2, 0, 0], [3, 0, 0]])
    with pytest.raises(ValueError, match="at least 3"):
        G.similarity_fit(line[:2], line[:2])
    with pytest.raises(ValueError, match="line"):
        G.similarity_fit(line, line + 1)
    bad = np.array([[0.0, 0, 0], [1, 0, 0], [0, 1, 0], [np.nan, 0, 1]])
    with pytest.raises(ValueError, match="finite"):
        G.similarity_fit(bad, bad)
    with pytest.raises(ValueError, match="pairs"):
        G.similarity_fit(np.eye(3), np.eye(4)[:, :3])


def test_the_similarity_receipt_carries_the_canon_fields_in_mm_and_degrees(goldens):
    inp = J(goldens, "C01_rigid/input.json")
    r = G.similarity_receipt(G.similarity_fit(np.array(inp["P"]), np.array(inp["Q_one_vertex_5mm"])))
    assert set(r) == {"scale", "rotation_deg", "axis", "translation_m", "rms_mm", "max_mm", "p95_mm", "n", "with_scale"}
    assert 4.0 <= r["max_mm"] <= 5.0 and r["n"] == 40 and r["with_scale"] is True
    exact = G.similarity_receipt(G.similarity_fit(np.array(inp["P"]), np.array(inp["Q_similar"])))
    assert exact["rotation_deg"] == pytest.approx(37.0, abs=1e-6) and exact["scale"] == pytest.approx(1.07, abs=1e-9)


# ------------------------------------------------------------------ C02: the exact inverse of LBS (canon 04)
def _c02(goldens):
    w, exp = J(goldens, "C02_inverse_lbs/weights.json"), J(goldens, "C02_inverse_lbs/expected.json")
    V, *_ = obj(goldens, "C02_inverse_lbs/piece_fit_pose.obj")
    return V, np.array(w["W"]), np.array([np.eye(4), np.array(w["fit_pose"]["B"])]), exp


def test_c02_exact_inverse_recovers_the_rest_and_round_trips(goldens):
    V, W, mats, exp = _c02(goldens)
    rest = G.lbs_inverse(V, W, mats)
    assert np.abs(rest - np.array(exp["exact_inverse"]["rest_vertices"])).max() < 1e-7
    assert np.linalg.norm(G.lbs(rest, W, mats) - V, axis=1).max() < 1e-9


def test_c02_lbs_matches_the_reference_point_by_point(goldens):
    V, W, mats, _ = _c02(goldens)
    want = np.array([REF.lbs(p, w, list(mats)) for p, w in zip(V, W)])
    assert np.abs(G.lbs(V, W, mats) - want).max() < 1e-12


def test_c02_falsifier_the_blend_of_inverses_misses_in_the_band_only(goldens):
    V, W, mats, exp = _c02(goldens)
    wrong = np.array([REF.blend_of_inverses(p, w, list(mats)) for p, w in zip(V, W)])
    err = np.linalg.norm(G.lbs(wrong, W, mats) - V, axis=1)
    eb = exp["blend_of_inverses"]
    assert abs(err.max() - eb["max_round_trip_m"]) < 1e-7 and int((err > 0.001).sum()) == eb["vertices_over_1mm"]
    assert err[W.max(1) > 1 - 1e-12].max() < 1e-9


def test_c02_a_singular_blend_is_refused_naming_the_vertex(goldens):
    exp = J(goldens, "C02_inverse_lbs/expected.json")
    mats = np.array([np.eye(4), np.array(exp["singular"]["fit_pose_B"])])
    pts = np.array([[0.0, 0.0, 0.0], [0, 0.05, 0.3]])
    with pytest.raises(G.SingularBlendError) as e:
        G.lbs_inverse(pts, np.array([[1.0, 0.0], [0.5, 0.5]]), mats)
    assert [v["vertex"] for v in e.value.vertices] == [1] and abs(e.value.vertices[0]["det"]) < 1e-9


# ------------------------------------------------------------------ C05: inside/outside by the winding number (canon 15)
def test_c05_sphere_signed_distance_within_twice_the_sag_and_the_sign_exact_beyond(goldens):
    exp, q = J(goldens, "C05_clearance/expected.json"), J(goldens, "C05_clearance/queries.json")
    V, F, *_ = obj(goldens, "C05_clearance/sphere.obj")
    sd, w = G.signed_distance(V, tris(F), np.array(q["sphere_points"]))
    e = exp["sphere"]
    want = np.array(e["signed_distance_m"])
    assert np.abs(sd - want).max() <= e["tol_m"]
    far = np.abs(want) > e["sign_exact_beyond_m"]
    assert (np.sign(sd[far]) == np.sign(want[far])).all()


def test_c05_the_point_beside_the_needle_apex_is_outside(goldens):
    exp, q = J(goldens, "C05_clearance/expected.json"), J(goldens, "C05_clearance/queries.json")
    V, F, *_ = obj(goldens, "C05_clearance/spike.obj")
    p = np.array([q["spike_point"]])
    w = G.winding_numbers(V, tris(F), p)
    assert abs(w[0]) < exp["spike"]["winding_tol"]
    sd, _ = G.signed_distance(V, tris(F), p)
    assert sd[0] > 0


def test_c05_falsifier_some_apex_face_normal_says_inside(goldens):
    q = J(goldens, "C05_clearance/queries.json")
    V, F, *_ = obj(goldens, "C05_clearance/spike.obj")
    p = np.array(q["spike_point"])
    signs = {int(np.sign((p - V[0]) @ np.cross(V[t[1]] - V[t[0]], V[t[2]] - V[t[0]]))) for t in tris(F) if 0 in t}
    assert -1 in signs and 1 in signs


def test_c05_an_open_body_gives_a_fractional_winding_and_is_declared_open(goldens):
    exp = J(goldens, "C05_clearance/expected.json")
    V, F, *_ = obj(goldens, "C05_clearance/open_sphere.obj")
    w = G.winding_numbers(V, tris(F), np.array([exp["open_sphere"]["point_inside_near_top"]]))
    assert 0.05 < w[0] < 0.95
    assert G.boundary_edges(tris(F)) > 0
    Vs, Fs, *_ = obj(goldens, "C05_clearance/sphere.obj")
    assert G.boundary_edges(tris(Fs)) == 0


def test_c05_winding_matches_the_reference(goldens):
    q = J(goldens, "C05_clearance/queries.json")
    V, F, *_ = obj(goldens, "C05_clearance/sphere.obj")
    T = tris(F)
    pts = np.array(q["sphere_points"][::7])
    assert np.allclose(G.winding_numbers(V, T, pts), [REF.winding_number(V, T, p) for p in pts], atol=1e-12)


# ------------------------------------------------------------------ C06: enclosure of the inner wall (canon 09)
def _c06_shifts(goldens, centre_of_piece):
    Vb, Fb, *_ = obj(goldens, "C06_enclosure/body.obj")
    Vp, Fp, *_ = obj(goldens, "C06_enclosure/piece_displaced.obj")
    Tb, Tp = tris(Fb), tris(Fp)
    out = []
    for z in np.linspace(1.05, 1.35, 7):
        bc = G.inner_wall_centre(G.slice_segments(Vb, Tb, z), (0.0, 0.0))
        out.append(bc - centre_of_piece(G.slice_segments(Vp, Tp, z), bc))
    return np.median(out, 0)


def test_c06_inner_wall_enclosure_recovers_the_displacement(goldens):
    e = J(goldens, "C06_enclosure/expected.json")["inner_wall_enclosure"]
    shift = _c06_shifts(goldens, lambda segs, start: G.inner_wall_centre(segs, start))
    assert np.abs(shift - np.array(e["translation_m"][:2])).max() < e["tol_m"]


def test_c06_falsifier_all_vertex_extents_are_biased_by_half_the_wall_difference(goldens):
    exp = J(goldens, "C06_enclosure/expected.json")
    shift = _c06_shifts(goldens, lambda segs, start: (segs.reshape(-1, 2).min(0) + segs.reshape(-1, 2).max(0)) / 2)
    err = shift[1] - exp["inner_wall_enclosure"]["translation_m"][1]
    assert abs(err - exp["all_vertex_extents_midpoint"]["translation_error_y_m"]) < 0.001


def test_c06_enclosure_shift_is_the_median_over_the_slices(goldens):
    e = J(goldens, "C06_enclosure/expected.json")["inner_wall_enclosure"]
    Vb, Fb, *_ = obj(goldens, "C06_enclosure/body.obj")
    Vp, Fp, *_ = obj(goldens, "C06_enclosure/piece_displaced.obj")
    r = G.enclosure_shift(Vb, tris(Fb), Vp, tris(Fp), np.linspace(1.05, 1.35, 7))
    assert np.abs(r["shift"] - np.array(e["translation_m"][:2])).max() < e["tol_m"] and r["slices"] == 7


# ------------------------------------------------------------------ C08: orthographic triangulation (canon 11)
def test_c08_four_orthographic_views_triangulate_exactly(goldens):
    inp, exp = J(goldens, "C08_multiview/input.json"), J(goldens, "C08_multiview/expected.json")
    cams = {c["name"]: c for c in inp["cameras"]}
    for n, p in exp["joints_m"].items():
        q = G.triangulate([(cams[v], *inp["keypoints_px"][n][v], 1.0) for v in cams])
        assert np.abs(q - np.array(p)).max() < exp["tol_m"], n


def test_c08_one_view_is_refused(goldens):
    inp = J(goldens, "C08_multiview/input.json")
    cams = {c["name"]: c for c in inp["cameras"]}
    with pytest.raises(ValueError, match="unfixed"):
        G.triangulate([(cams["front"], *inp["keypoints_px"]["head"]["front"], 1.0)])


def test_c08_the_robust_solve_drops_the_corrupt_view_and_plain_least_squares_is_off(goldens):
    inp, exp = J(goldens, "C08_multiview/input.json"), J(goldens, "C08_multiview/expected.json")
    cams = {c["name"]: c for c in inp["cameras"]}
    c = inp["corrupt"]
    obs = [(cams[v], inp["keypoints_px"][c["joint"]][v][0] + (c["dx_px"] if v == c["view"] else 0.0), inp["keypoints_px"][c["joint"]][v][1], 1.0) for v in cams]
    true = np.array(exp["joints_m"][c["joint"]])
    assert np.abs(G.triangulate(obs) - true).max() > exp["plain_least_squares_with_corrupt_error_min_m"]
    q, used = G.triangulate_robust(obs, exp["robust_drop_px"])
    assert used == 3 and np.abs(q - true).max() < exp["robust_with_corrupt_tol_m"]


# ------------------------------------------------------------------ C09: UV measurements (canon 13)
def _uv(goldens, name):
    V, F, UV, FUV, _ = obj(goldens, f"C09_uv/{name}")
    return V, F, UV, FUV


def test_c09_three_islands_utilization_overlap_flipped_islands(goldens):
    e = J(goldens, "C09_uv/expected.json")["three_islands"]
    V, F, UV, FUV = _uv(goldens, "three_islands.obj")
    m = G.uv_metrics(V, F, UV, FUV, res=1024)
    assert abs(m["utilization"] - e["utilization_1024"]) < 1e-9 and m["overlap"] == 0.0
    assert abs(m["flipped"] - e["flipped_fraction_faces"]) < 1e-9 and m["islands"] == e["islands"]


def test_c09_overlap_fraction_of_covered(goldens):
    e = J(goldens, "C09_uv/expected.json")["overlap"]
    m = G.uv_metrics(*_uv(goldens, "overlap.obj"), res=1024)
    assert abs(m["overlap"] - e["overlap_fraction_of_covered"]) < 1e-9 and abs(m["utilization"] - e["utilization_1024"]) < 1e-9


def test_c09_falsifier_an_inclusive_raster_counts_a_phantom_overlap(goldens):
    V, F, UV, FUV = _uv(goldens, "three_islands.obj")
    TU = np.array([[UV[fu[0]], UV[fu[k]], UV[fu[k + 1]]] for fu in FUV for k in range(1, len(fu) - 1)]) * 1024
    gx, gy = np.meshgrid(np.arange(1024) + 0.5, np.arange(1024) + 0.5)
    cnt = np.zeros((1024, 1024), int)
    for t in TU:
        d = (t[1, 1] - t[2, 1]) * (t[0, 0] - t[2, 0]) + (t[2, 0] - t[1, 0]) * (t[0, 1] - t[2, 1])
        l0 = ((t[1, 1] - t[2, 1]) * (gx - t[2, 0]) + (t[2, 0] - t[1, 0]) * (gy - t[2, 1])) / d
        l1 = ((t[2, 1] - t[0, 1]) * (gx - t[2, 0]) + (t[0, 0] - t[2, 0]) * (gy - t[2, 1])) / d
        cnt += (l0 >= 0) & (l1 >= 0) & (1 - l0 - l1 >= 0)
    assert (cnt > 1).sum() / (cnt > 0).sum() == pytest.approx(0.00167, abs=1e-5)


def test_c09_split_seam_index_sees_two_components_the_weld_one_and_uv_islands_two(goldens):
    e = J(goldens, "C09_uv/expected.json")["split_seam"]
    V, F, UV, FUV = _uv(goldens, "split_seam.obj")
    assert G.components(F) == e["components_by_vertex_index"]
    keys = G.weld_keys(V, 1e-5)
    assert G.components(F, key=lambda v: keys[v]) == e["components_by_position_weld_1e-5"]
    assert int(G.uv_island_ids(F, FUV, UV, vertex_key=keys).max() + 1) == e["uv_islands"]


def test_c09_uv_metrics_match_the_reference(goldens):
    for name in ("three_islands.obj", "overlap.obj"):
        V, F, UV, FUV = _uv(goldens, name)
        a, b = G.uv_metrics(V, F, UV, FUV, res=1024), REF.uv_metrics(V, F, UV, FUV, res=1024)
        assert a["utilization"] == b["utilization"] and a["overlap"] == b["overlap"] and a["flipped"] == b["flipped_tris"]


def test_the_half_open_raster_gives_a_shared_edge_texel_to_exactly_one_triangle():
    gx, gy = np.meshgrid(np.arange(5) + 0.5, np.arange(5) + 0.5)
    a, b, c, d = np.array([0.0, 0.0]), np.array([3.0, 0.0]), np.array([3.0, 3.0]), np.array([0.0, 3.0])
    t1 = G.raster_half_open(np.array([a, b, c]), gx, gy)          # the diagonal a-c runs through three texel centres
    t2 = G.raster_half_open(np.array([a, c, d]), gx, gy)
    assert not (t1 & t2).any()
    assert ((t1 | t2) == ((gx < 3) & (gy < 3))).all() and (t1 | t2).sum() == 9
    mirrored = G.raster_half_open(np.array([a, c, b]), gx, gy)
    assert (mirrored == t1).all()


def test_uv_island_ids_by_vertex_index_and_uv():
    F = [[0, 1, 2], [0, 2, 3], [4, 5, 6]]
    UV = np.array([[0, 0], [1, 0], [1, 1], [0, 1], [0.5, 0.5], [0.6, 0.5], [0.6, 0.6], [0.9, 0.9]])
    FUV = [[0, 1, 2], [0, 2, 3], [4, 5, 6]]
    assert G.uv_island_ids(F, FUV, UV).tolist() == [0, 0, 1]
    FUV2 = [[0, 1, 2], [7, 2, 3], [4, 5, 6]]                  # corner 0 of face 1 has another UV: still joined along 2
    assert G.uv_island_ids(F, FUV2, UV).tolist() == [0, 0, 1]
    FUV3 = [[0, 1, 2], [7, 5, 3], [4, 5, 6]]                  # no shared (vertex, uv) corner: two islands
    assert G.uv_island_ids(F, FUV3, UV).tolist() == [0, 1, 2]
