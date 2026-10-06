# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_geom's joint grammar, bone directions, finger axes, views, the crossing control and the fast sign.

The pose / axis / expectation / curl / segment-box / control-shift / chain-end / finger-axis / curl-delta / calibration
cases are Titan's own tests (tools/test_armour_validate.py, test_proc_body.py, test_views_joints.py), ported with their
numbers: canon_geom carries the maths those modules were measured with (IMPLEMENTATION_PLAN item 1, "keep their tests")."""

import math
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens, obj, tris  # noqa: E402,F401
from mixar.modules.lampway_tools import canon_geom as G  # noqa: E402


def q_axis(axis, deg):
    n = math.sqrt(sum(a * a for a in axis))
    s = math.sin(math.radians(deg) / 2)
    return tuple(a / n * s for a in axis) + (math.cos(math.radians(deg) / 2),)


def chain():
    """A three-bone arm along +x, identity rotations: shoulder at 0, elbow at 30, hand at 55."""
    return {"upperarm": {"parent": None, "rot": (0.0, 0.0, 0.0, 1.0), "pos": (0.0, 0.0, 0.0)},
            "lowerarm": {"parent": "upperarm", "rot": (0.0, 0.0, 0.0, 1.0), "pos": (30.0, 0.0, 0.0)},
            "hand": {"parent": "lowerarm", "rot": (0.0, 0.0, 0.0, 1.0), "pos": (55.0, 0.0, 0.0)}}


def close(a, b, tol=1e-9):
    assert np.allclose(np.asarray(a, float), np.asarray(b, float), atol=tol), (a, b)


def rotate(v, axis, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    k = axis
    d = sum(x * y for x, y in zip(k, v))
    kx = (k[1] * v[2] - k[2] * v[1], k[2] * v[0] - k[0] * v[2], k[0] * v[1] - k[1] * v[0])
    return tuple(v[i] * c + kx[i] * s + k[i] * d * (1 - c) for i in range(3))


# ------------------------------------------------------------------ pose_cs
def test_rest_is_the_identity():
    posed = G.pose_cs(chain(), [])
    for b, t in chain().items():
        close(posed[b]["pos"], t["pos"])
        close(posed[b]["rot"], t["rot"])


def test_a_bend_at_the_elbow_moves_the_hand_and_not_the_elbow():
    posed = G.pose_cs(chain(), [{"bone": "lowerarm", "axis": (0.0, 0.0, 1.0), "deg": 90.0}])
    close(posed["lowerarm"]["pos"], (30.0, 0.0, 0.0))
    close(posed["hand"]["pos"], (30.0, 25.0, 0.0))
    close(posed["hand"]["rot"], q_axis((0, 0, 1), 90))


def test_two_rotations_compose_down_the_chain_about_their_rest_axes():
    posed = G.pose_cs(chain(), [{"bone": "upperarm", "axis": (0.0, 0.0, 1.0), "deg": 90.0}, {"bone": "lowerarm", "axis": (0.0, 0.0, 1.0), "deg": 90.0}])
    close(posed["lowerarm"]["pos"], (0.0, 30.0, 0.0))
    close(posed["hand"]["pos"], (-25.0, 30.0, 0.0))


def test_a_non_identity_rest_rotation_is_respected():
    c = chain()
    r = q_axis((1, 0, 0), 90)
    for b in c:
        c[b]["rot"] = r
    posed = G.pose_cs(c, [{"bone": "lowerarm", "axis": (0.0, 0.0, 1.0), "deg": 90.0}])
    close(posed["hand"]["pos"], (30.0, 25.0, 0.0))
    close(posed["hand"]["rot"], G.qmul(q_axis((0, 0, 1), 90), r))


def test_an_unknown_bone_a_zero_axis_a_nan_or_a_parent_after_its_child_is_refused():
    for bad in ([{"bone": "wrist", "axis": (0, 0, 1), "deg": 10}], [{"bone": "hand", "axis": (0, 0, 0), "deg": 10}],
                [{"bone": "hand", "axis": (0, 0, 1), "deg": float("nan")}]):
        with pytest.raises(ValueError):
            G.pose_cs(chain(), bad)
    c = chain()
    with pytest.raises(ValueError, match="before its parent"):
        G.pose_cs({b: c[b] for b in ("hand", "lowerarm", "upperarm")}, [])


# ------------------------------------------------------------------ resolve_axis, check_expect, expand_pose
def test_named_axes_resolve_from_the_joints():
    joints = {"a": (0.0, 0.0, 0.0), "b": (0.0, 2.0, 0.0), "c": (1.0, 2.0, 0.0)}
    frame = {"up": (0.0, 0.0, 1.0), "forward": (1.0, 0.0, 0.0)}
    close(G.resolve_axis({"line": ["a", "b"]}, joints, frame), (0.0, 1.0, 0.0))
    close(G.resolve_axis("up", joints, frame), (0.0, 0.0, 1.0))
    close(G.resolve_axis("-forward", joints, frame), (-1.0, 0.0, 0.0))
    close(G.resolve_axis("lateral", joints, frame), (0.0, 1.0, 0.0))
    close(G.resolve_axis({"perp": ["a", "b"], "to": "forward"}, joints, frame), (0.0, 0.0, -1.0))
    with pytest.raises(ValueError):
        G.resolve_axis({"line": ["a", "a"]}, joints, frame)
    with pytest.raises(ValueError):
        G.resolve_axis("sideways", joints, frame)


JOINTS = {"lowerarm": (30.0, 0.0, 0.0), "hand": (55.0, 0.0, 0.0), "thigh": (55.0, 20.0, 0.0)}
FRAME = {"up": (0.0, 0.0, 1.0), "forward": (0.0, 1.0, 0.0)}


def test_a_joint_moving_along_a_named_axis_meets_its_expectation_and_the_negated_axis_does_not():
    posed = dict(JOINTS, hand=(30.0, 25.0, 0.0))
    ok, got = G.check_expect({"joint": "hand", "along": "forward", "min_cm": 5.0}, JOINTS, posed, FRAME)
    assert ok and got == pytest.approx(25.0)
    ok, got = G.check_expect({"joint": "hand", "along": "-forward", "min_cm": 5.0}, JOINTS, posed, FRAME)
    assert not ok and got == pytest.approx(-25.0)


def test_a_joint_coming_nearer_another_meets_its_expectation():
    posed = dict(JOINTS, hand=(40.0, 15.0, 0.0))
    ok, got = G.check_expect({"joint": "hand", "closer_to": "thigh", "min_cm": 1.0}, JOINTS, posed, FRAME)
    assert ok and got == pytest.approx(20.0 - math.dist((40.0, 15.0, 0.0), (55.0, 20.0, 0.0)))


def test_joints_in_metres_are_measured_in_centimetres_against_the_recipes_min_cm():
    rest = {k: tuple(x / 100 for x in v) for k, v in JOINTS.items()}
    posed = dict(rest, hand=(0.30, 0.25, 0.0))
    ok, got = G.check_expect({"joint": "hand", "along": "forward", "min_cm": 5.0}, rest, posed, FRAME, scale_to_cm=100.0)
    assert ok and got == pytest.approx(25.0)
    ok, _ = G.check_expect({"joint": "hand", "along": "forward", "min_cm": 26.0}, rest, posed, FRAME, scale_to_cm=100.0)
    assert not ok


def test_an_unknown_expectation_or_joint_is_refused():
    with pytest.raises(ValueError):
        G.check_expect({"joint": "hand", "beside": "thigh"}, JOINTS, JOINTS, FRAME)
    with pytest.raises(ValueError, match="joint"):
        G.check_expect({"joint": "wrist", "along": "up"}, JOINTS, JOINTS, FRAME)


def test_a_curl_expands_to_every_finger_bone_at_its_fraction_about_one_axis():
    recipe = {"curl": {"fingers": ["index", "pinky"], "deg": {"01": 80, "02": 95, "03": 60}, "axis": {"line": ["pinky_01_{s}", "index_01_{s}"]}}}
    bones = G.expand_pose({"curl": {"side": "r", "fraction": 0.5}}, recipe)
    assert [(b["bone"], b["deg"]) for b in bones] == [("index_01_r", 40.0), ("index_02_r", 47.5), ("index_03_r", 30.0),
                                                      ("pinky_01_r", 40.0), ("pinky_02_r", 47.5), ("pinky_03_r", 30.0)]
    assert bones[0]["axis"] == {"line": ["pinky_01_r", "index_01_r"]}
    assert G.expand_pose({"bones": [{"bone": "hand_r", "axis": "up", "deg": 5}]}, recipe) == [{"bone": "hand_r", "axis": "up", "deg": 5}]
    with pytest.raises(ValueError):
        G.expand_pose({"curl": {"side": "x", "fraction": 0.5}}, recipe)


# ------------------------------------------------------------------ segment_box_overlap, control_shift
def test_segment_box_overlap():
    assert G.segment_box_overlap((-5.0, 0.5, 0.5), (5.0, 0.5, 0.5), (0, 0, 0), (1, 1, 1))
    assert G.segment_box_overlap((0.5, 0.5, 0.5), (9.0, 9.0, 9.0), (0, 0, 0), (1, 1, 1))
    assert G.segment_box_overlap((9.0, 9.0, 9.0), (0.5, 0.5, 0.5), (0, 0, 0), (1, 1, 1))
    assert not G.segment_box_overlap((-5.0, 2.0, 0.5), (5.0, 2.0, 0.5), (0, 0, 0), (1, 1, 1))
    assert not G.segment_box_overlap((-5.0, 0.5, 0.5), (-1.0, 0.5, 0.5), (0, 0, 0), (1, 1, 1))
    assert not G.segment_box_overlap((-1.0, -1.0, 0.5), (0.4, -0.1, 0.5), (0, 0, 0), (1, 1, 1))


def test_the_shift_follows_the_closest_vertex_to_its_skin_and_goes_past_it():
    pairs = [((0.0, 0.0, 10.0), (0.0, 0.0, 7.0)), ((2.0, 0.0, 10.0), (2.0, 0.0, 8.0)), ((0.0, 2.0, 12.0), (0.0, 2.0, 7.0))]
    close(G.control_shift(pairs, 1.0), (0.0, 0.0, -3.0))


def test_a_wrapping_piece_is_pushed_in_at_its_closest_point_not_along_its_centroid():
    pairs = [((5.0, 0.0, 0.0), (4.5, 0.0, 0.0)), ((-6.0, 0.0, 0.0), (-4.0, 0.0, 0.0)), ((0.0, 6.0, 0.0), (0.0, 4.0, 0.0))]
    close(G.control_shift(pairs, 1.0), (-1.5, 0.0, 0.0))


def test_a_thin_piece_straddles_the_skin_instead_of_sinking_through_it():
    pairs = [((0.0, 0.0, 10.0), (0.0, 0.0, 8.0)), ((1.0, 0.0, 10.2), (1.0, 0.0, 8.0))]
    close(G.control_shift(pairs, 1.0), (0.0, 0.0, -2.1))


def test_no_pairs_or_a_vertex_on_the_skin_is_refused():
    for pairs in ([], [((1.0, 1.0, 1.0), (1.0, 1.0, 1.0))]):
        with pytest.raises(ValueError):
            G.control_shift(pairs, 1.0)


def test_c14_the_capped_control_straddles_the_skin_and_the_uncapped_one_buries_the_rivet(goldens):
    exp = J(goldens, "C14_controls/expected.json")
    V, F, *_ = obj(goldens, "C14_controls/rivet.obj")
    c, r = np.array(exp["body"]["sphere_centre"]), exp["body"]["radius"]
    skin = c + (V - c) / np.linalg.norm(V - c, axis=1)[:, None] * r
    edges = {tuple(sorted((a, b))) for f in F for a, b in zip(f, list(f[1:]) + [f[0]])}

    def crossings(P):
        ins = np.linalg.norm(P - c, axis=1) < r
        return sum(1 for a, b in edges if ins[a] != ins[b]), int(ins.sum())
    shift = np.array(G.control_shift(list(zip(map(tuple, V), map(tuple, skin))), 0.01))
    cx, _ = crossings(V + shift)
    assert cx >= exp["capped_half_extent"]["surface_crossing_edges_min"]
    d = shift / np.linalg.norm(shift)
    cx_u, inside = crossings(V + 0.01 * d)                                   # the uncapped 1 cm push of the falsifier
    assert cx_u == exp["uncapped_1cm"]["surface_crossing_edges"] and inside == len(V)


# ------------------------------------------------------------------ bones
PAR = {"pelvis": None, "spine_01": "pelvis", "thigh_l": "pelvis", "calf_l": "thigh_l", "hand_l": None, "index_01_l": "hand_l",
       "middle_01_l": "hand_l", "middle_02_l": "middle_01_l"}
HEAD = {"pelvis": (0.0, 0.0, 1.0), "spine_01": (0.0, 0.0, 1.1), "thigh_l": (0.1, 0.0, 0.95), "calf_l": (0.1, 0.0, 0.5),
        "hand_l": (0.5, 0.0, 1.0), "index_01_l": (0.58, 0.02, 1.0), "middle_01_l": (0.6, 0.0, 1.0), "middle_02_l": (0.64, 0.0, 1.0)}


def test_a_bone_with_one_child_ends_at_its_childs_head():
    assert G.chain_ends(HEAD, PAR)["thigh_l"] == (0.1, 0.0, 0.5)


def test_a_bone_with_several_children_ends_at_its_named_continuation():
    T = G.chain_ends(HEAD, PAR)
    assert T["pelvis"] == (0.0, 0.0, 1.1) and T["hand_l"] == (0.6, 0.0, 1.0)


def test_a_last_bone_continues_its_parents_line():
    close(G.chain_ends(HEAD, PAR)["calf_l"], (0.1, 0.0, 0.5 - 0.8 * 0.45), 1e-12)


def test_several_children_and_no_named_continuation_is_refused():
    with pytest.raises(ValueError, match="no named continuation"):
        G.chain_ends(dict(HEAD, ring_01_l=(0.62, -0.02, 1.0)), dict(PAR, ring_01_l="middle_01_l"))


def test_bone_segments_run_head_to_chain_end_never_along_an_imported_tail():
    seg = G.bone_segments(HEAD, PAR)
    close(seg["thigh_l"][0], (0.1, 0.0, 0.95))
    close(seg["thigh_l"][1], (0.1, 0.0, 0.5))
    assert isinstance(seg["thigh_l"][0], np.ndarray)


def test_the_right_and_left_hands_close_towards_their_palms():
    for side, index, pinky in (("r", (-0.03, 0.1, 0.0), (0.03, 0.1, 0.0)), ("l", (0.03, 0.1, 0.0), (-0.03, 0.1, 0.0))):
        axis = G.flex_axis((0.0, 1.0, 0.0), (0.0, 0.0, 0.0), index, (0.0, 0.1, 0.0), pinky, side)
        close(rotate((0.0, 1.0, 0.0), axis, 90), (0.0, 0.0, -1.0))
    with pytest.raises(ValueError):
        G.flex_axis((0.0, 1.0, 0.0), (0, 0, 0), (-0.03, 0.1, 0), (0, 0.1, 0), (0.03, 0.1, 0), "x")


def test_the_finger_axis_is_the_flex_axis_of_the_hands_own_direction_and_closes_past_the_palm_normal():
    hand, idx, mid, pin = (0.0, 0.0, 0.0), (-0.03, 0.1, 0.0), (0.0, 0.1, 0.0), (0.03, 0.1, 0.0)
    a = G.finger_axis(hand, idx, mid, pin, "r")
    close(a, G.flex_axis((0.0, 1.0, 0.0), hand, idx, mid, pin, "r"), 1e-12)
    more = rotate(rotate((0.0, 1.0, 0.0), a, 120.0), a, 30.0)
    assert G.curl_delta((0.0, 1.0, 0.0), more, a, 0.0) == pytest.approx(-150.0, abs=1e-9)


@pytest.mark.parametrize("curl,parent,target,want", [(0.0, (0.0, 1.0, 0.0), 70.0, 70.0), (50.0, (0.0, 1.0, 0.0), 70.0, 20.0),
                                                     (90.0, (0.0, 1.0, 0.0), 70.0, -20.0), (-10.0, (0.0, 1.0, 0.0), 70.0, 80.0)])
def test_curl_delta_turns_a_joint_to_its_target(curl, parent, target, want):
    b = rotate((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), curl)
    assert G.curl_delta(parent, b, (-1.0, 0.0, 0.0), target) == pytest.approx(want, abs=1e-9)


def test_a_splayed_finger_is_measured_across_the_axis():
    b = rotate((0.0, 1.0, 0.0), (-1.0, 0.0, 0.0), 50.0)
    b = (b[0] - 0.4, b[1], b[2])
    assert G.curl_delta((-0.5, 1.0, 0.0), b, (-1.0, 0.0, 0.0), 70.0) == pytest.approx(20.0, abs=1e-9)


# ------------------------------------------------------------------ views: calibration (Titan test_views_joints)
FRONT = {"res": 1000, "ortho": 2.0, "center": [0.0, -5.0, 1.0], "right": [1.0, 0.0, 0.0], "up": [0.0, 0.0, 1.0], "look": [0.0, 1.0, 0.0]}
LEFT = {"res": 1000, "ortho": 2.0, "center": [5.0, 0.0, 1.0], "right": [0.0, 1.0, 0.0], "up": [0.0, 0.0, 1.0], "look": [-1.0, 0.0, 0.0]}


def test_a_point_seen_front_and_side_is_recovered_and_a_zero_weight_view_changes_nothing():
    p = (0.3, 0.2, 1.4)
    obs = [(FRONT, *G.project(FRONT, p), 1.0), (LEFT, *G.project(LEFT, p), 1.0)]
    close(G.triangulate(obs), p)
    close(G.triangulate(obs + [(FRONT, 0.0, 0.0, 0.0)]), p)


def test_calibration_offsets_are_true_less_triangulated_and_apply_moves_each_keypoint():
    off = G.calibrate({"hand_l": (1.0, 2.0, 3.0), "foot_l": (0.0, 0.0, 0.0)}, {"hand_l": (0.9, 2.1, 3.0), "knee": (5, 5, 5)})
    assert set(off) == {"hand_l"}
    close(off["hand_l"], (0.1, -0.1, 0.0))
    got = G.apply_offsets({"hand_l": (2.0, 2.0, 2.0), "elbow": (1, 1, 1)}, off)
    assert set(got) == {"hand_l"}
    close(got["hand_l"], (2.1, 1.9, 2.0))


# ------------------------------------------------------------------ the fast sign for closed meshes
def test_pseudonormals_sign_the_spike_apex_point_outside_where_one_face_normal_says_inside(goldens):
    q = J(goldens, "C05_clearance/queries.json")
    V, F, *_ = obj(goldens, "C05_clearance/spike.obj")
    T = tris(F)
    pn = G.PseudoNormals(V, T)
    sx, sy, sz = q["spike_point"]
    pts = np.array([[sx, sy, sz], [-sx, sy, sz], [sy, sx, sz], [sy, -sx, sz]])     # round the apex: the nearest point is the apex
    d, loc, tri = G.closest_points(V, T, pts)
    assert np.allclose(loc, V[0]) and (G.PseudoNormals(V, T).signs(pts, loc, tri) > 0).all()
    assert any((p - V[0]) @ pn.face[k] < 0 for p in pts for k in range(len(T)) if 0 in T[k])      # one apex face says inside


def test_pseudonormals_agree_with_the_winding_sign_on_the_closed_sphere(goldens):
    q = J(goldens, "C05_clearance/queries.json")
    V, F, *_ = obj(goldens, "C05_clearance/sphere.obj")
    T = tris(F)
    pts = np.array(q["sphere_points"])
    d, loc, tri = G.closest_points(V, T, pts)
    sd, _w = G.signed_distance(V, T, pts)
    assert (G.PseudoNormals(V, T).signs(pts, loc, tri) == np.sign(sd)).all()


# ------------------------------------------------------------------ conventions
def test_the_conventions_block_carries_every_canon_field_and_refuses_a_missing_one_by_name():
    b = G.conventions_block(turn_deg=-90, weld_m=1e-5, source_frame="tripo glTF after Blender import")
    assert b == {"frame": "body", "units": "m", "turn_deg": -90, "bone_direction": "head->child head", "bone_axis_export": "Z/X",
                 "weld_m": 1e-5, "source_frame": "tripo glTF after Blender import"}
    with pytest.raises(ValueError, match="turn_deg"):
        G.conventions_block(turn_deg=None, weld_m="n/a", source_frame="body")
    assert G.BODY_FRAME["front"] == (0.0, -1.0, 0.0) and G.BODY_FRAME["left"] == (1.0, 0.0, 0.0)
