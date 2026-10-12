# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""IMPLEMENTATION_PLAN item 5 (canon 09): lampway_fit_place centres a piece by enclosure of its INNER wall (golden C06) and
scales it by the inner wall's span, one uniform scale; a gauntlet's residual axis angle is corrected rigidly, not left.
pipeline/fit_place is pure numpy: these run in-process on .npz files written from the goldens."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from canon_support import J, goldens, obj, tris  # noqa: E402,F401
from mixar.modules.lampway_tools.pipeline import fit_place as FP  # noqa: E402

# The C06 torso stands z 1.0 .. 1.4; the waist band is measured at spine_01 + 3 cm and the piece's top 6 %.
JOINTS = {"pelvis": (0, 0, 1.05), "spine_01": (0, 0, 1.17), "calf_l": (0.1, 0, 0.5), "calf_r": (-0.1, 0, 0.5)}


def _npz(tmp, goldens):
    Vb, Fb, *_ = obj(goldens, "C06_enclosure/body.obj")
    Vp, Fp, *_ = obj(goldens, "C06_enclosure/piece_displaced.obj")
    names = list(JOINTS)
    np.savez(tmp / "body.npz", V=Vb, T=tris(Fb), J=np.array([JOINTS[n] for n in names], float), names=np.array(names))
    np.savez(tmp / "piece.npz", V=Vp, T=tris(Fp))
    return tmp / "body.npz", tmp / "piece.npz"


def test_g09_1_the_waist_is_centred_by_its_inner_wall_and_recovers_the_displacement(goldens, tmp_path):
    e = J(goldens, "C06_enclosure/expected.json")["inner_wall_enclosure"]
    body, piece = _npz(tmp_path, goldens)
    V, T, meta, rep = FP.place("waist", body, piece, turn=0.0, clear_mm=15.0)
    assert meta["scale"] == pytest.approx(1.0, abs=0.02)                       # G09.3: the body's own offset reads scale 1
    assert np.abs(np.array(meta["translation"][:2]) - np.array(e["translation_m"][:2])).max() < e["tol_m"], meta["translation"]
    assert rep["inner_wall_shift_m"] is not None and rep["slices"] >= 3


def test_g09_1_falsifier_the_all_vertex_centre_of_the_same_band_is_off_by_half_the_wall_difference(goldens):
    from mixar.modules.lampway_tools.pipeline import sections as S
    exp = J(goldens, "C06_enclosure/expected.json")
    Vb, Fb, *_ = obj(goldens, "C06_enclosure/body.obj")
    Vp, Fp, *_ = obj(goldens, "C06_enclosure/piece_displaced.obj")
    _, _, bp = S.section(Vb, tris(Fb), np.zeros(3), S.Z, S.X, 1.2)
    _, _, pp = S.section(Vp, tris(Fp), np.zeros(3), S.Z, S.X, 1.2)
    err = (S.centre(bp) - S.centre(pp))[1] - exp["inner_wall_enclosure"]["translation_m"][1]
    assert abs(abs(err) - exp["all_vertex_extents_midpoint"]["translation_error_y_m"]) < 0.002


def test_g09_4_the_applied_linear_map_has_equal_singular_values(goldens, tmp_path):
    body, piece = _npz(tmp_path, goldens)
    V, T, meta, rep = FP.place("waist", body, piece)
    src = np.load(piece)["V"]
    A = np.c_[src - src.mean(0)]
    Mlin, *_ = np.linalg.lstsq(A, V - V.mean(0), rcond=None)
    sv = np.linalg.svd(Mlin, compute_uv=False)
    assert sv.max() - sv.min() < 1e-6


def test_g09_5_boots_default_width_matches_explicit_anchor_and_unknown_names_the_three(tmp_path):
    # Actual boot/body shape: the old torso fixture cannot measure a shaft anchor.
    vertices=np.array([(.1+.04*np.cos(a),.04*np.sin(a),z)
                       for z in np.linspace(0,.5,11) for a in np.arange(16)*2*np.pi/16])
    triangles=[]
    for i in range(10):
        for j in range(16):
            a=i*16+j;b=i*16+(j+1)%16;c=b+16;d=a+16
            triangles.extend(((a,b,c),(a,c,d)))
    body,piece=tmp_path/'body.npz',tmp_path/'boot.npz'
    np.savez(body,V=vertices,T=triangles,J=[[.1,0,.7],[.1,0,.5],[.1,0,.08],[.1,-.06,.02]],
             names=['thigh_l','calf_l','foot_l','ball_l'])
    np.savez(piece,V=vertices,T=triangles)
    default=FP.place('boots',body,piece,sides='l')
    explicit=FP.place('boots',body,piece,sides='l',scale_anchor='width')
    assert np.array_equal(default[0],explicit[0]) and np.array_equal(default[1],explicit[1])
    assert default[2]['scale']==explicit[2]['scale'] and default[2]['scale_anchor']=='width'
    assert default[2]['defaults']['boots_scale_anchor']['physical_status']=='untested'
    with pytest.raises(FP.PlaceError) as e:
        FP.place('boots',body,piece,sides='l',scale_anchor='unknown')
    assert all(a in str(e.value) for a in ('width','height','foot'))


def _arm_body_and_gauntlet(tmp, tilt_deg):
    """A forearm tube along +x (elbow at x 0.30, wrist at 0.55) and a bracer tube 2 cm clear of it, laid along the forearm
    and tilted ``tilt_deg`` about y off its axis."""
    def tube(r, x0, x1, n=24, k=10):
        V = [(x0 + (x1 - x0) * i / k, r * np.cos(2 * np.pi * j / n), 1.4 + r * np.sin(2 * np.pi * j / n)) for i in range(k + 1) for j in range(n)]
        F = [(i * n + j, i * n + (j + 1) % n, (i + 1) * n + (j + 1) % n) for i in range(k) for j in range(n)]
        F += [(i * n + j, (i + 1) * n + (j + 1) % n, (i + 1) * n + j) for i in range(k) for j in range(n)]
        return np.array(V), np.array(F)
    Vb, Tb = tube(0.04, 0.0, 0.9)
    names = ["lowerarm_l", "hand_l", "middle_03_l"]
    Jl = np.array([(0.30, 0, 1.4), (0.55, 0, 1.4), (0.72, 0, 1.4)])
    np.savez(tmp / "body.npz", V=Vb, T=Tb, J=Jl, names=np.array(names))
    Vp, Tp = tube(0.06, 0.0, 0.25)
    Vp = Vp - Vp.mean(0)
    a = np.radians(tilt_deg)
    Ry = np.array([[np.cos(a), 0, np.sin(a)], [0, 1, 0], [-np.sin(a), 0, np.cos(a)]])
    Vp = Vp @ Ry.T + np.array([0.4, 0, 1.4])
    np.savez(tmp / "piece.npz", V=Vp, T=Tp)
    return tmp / "body.npz", tmp / "piece.npz"


def test_a_gauntlets_residual_axis_angle_is_corrected_rigidly_not_left(tmp_path):
    body, piece = _arm_body_and_gauntlet(tmp_path, 15.0)
    V, T, meta, rep = FP.place("gauntlets", body, piece, sides="l")
    c0 = V.mean(0)
    _, _, vt = np.linalg.svd(V - c0, full_matrices=False)
    ang = np.degrees(np.arccos(min(1.0, abs(vt[0] @ np.array([1.0, 0, 0])))))
    assert ang < 0.5 and rep["axis_error_deg"]["l"] == pytest.approx(15.0, abs=1.0) and rep["axis_corrected"] is True


def test_inv_09_4_a_body_twice_as_broad_places_the_same_way_no_absolute_torso_filter(goldens, tmp_path):
    """canon 09 INV-09.4: every constant is relative to the joints. The torso filter |x| < 0.27 m cut a broad body's own sides; it
    existed to drop the hanging arms, so the torso is now every vertex not nearest an arm bone (joint to next joint). Golden C06 scaled 2x in x and y: the scale the 1x
    widths predict (the 15 mm clearance stays 15 mm), the displacement doubled."""
    e = J(goldens, "C06_enclosure/expected.json")["inner_wall_enclosure"]
    Vb, Fb, *_ = obj(goldens, "C06_enclosure/body.obj")
    Vp, Fp, *_ = obj(goldens, "C06_enclosure/piece_displaced.obj")
    k = np.array([2.0, 2.0, 1.0])
    names = list(JOINTS)
    np.savez(tmp_path / "body.npz", V=np.asarray(Vb) * k, T=tris(Fb), J=np.array([np.array(JOINTS[n]) * k for n in names], float), names=np.array(names))
    np.savez(tmp_path / "piece.npz", V=np.asarray(Vp) * k, T=tris(Fp))
    V, T, meta, rep = FP.place("waist", tmp_path / "body.npz", tmp_path / "piece.npz")
    one = tmp_path / "one"
    one.mkdir()
    _, _, meta1, rep1 = FP.place("waist", *_npz(one, goldens))
    bw, pw = (rep1["body_width_mm"] - 30.0) / 1000, rep1["piece_width_mm"] / 1000        # 1x widths (the body's carries + 2C, C = 15 mm)
    assert meta["scale"] == pytest.approx((2 * bw + 0.030) / (2 * pw), abs=1e-3), (meta["scale"], bw, pw)   # the clearance does not scale
    # the inner-wall centre shift (the translation also carries (1 - s) x the anchor position once s != 1)
    assert np.abs(np.array(meta["anchor_shift"][:2]) - 2 * np.array(e["translation_m"][:2])).max() < 2 * e["tol_m"], meta["anchor_shift"]


def test_regions_are_the_vertices_nearest_their_bones():
    J = {"pelvis": np.array([0, 0, 1.0]), "spine_01": np.array([0, 0, 1.2]), "upperarm_l": np.array([0.2, 0, 1.4]), "lowerarm_l": np.array([0.45, 0, 1.2]),
         "hand_l": np.array([0.6, 0, 1.05])}
    P = np.array([[0.05, 0, 1.1], [0.32, 0, 1.3], [0.6, 0, 1.0], [0.1, 0.02, 1.25]])
    assert FP._region(P, J, ("pelvis", "spine_01")).tolist() == [True, False, False, True]
    assert FP._region(P, J, ("lowerarm_l", "hand_l")).tolist() == [False, False, True, False]


def test_helper_and_twist_bones_do_not_claim_their_limbs_vertices():
    """A real skeleton (the MetaHuman: 342 joints) has twist, corrective and toe bones inside the limbs; nearest-segment over ALL joints
    let them claim the leg (2799 of the shelf body's 49789 leg vertices). Regions are taken over the main skeleton (canon 16's names)."""
    J = {"upperarm_l": np.array([0.2, 0, 1.4]), "lowerarm_l": np.array([0.45, 0, 1.2]), "hand_l": np.array([0.6, 0, 1.05]),
         "lowerarm_twist_01_l": np.array([0.52, 0, 1.13]), "bigtoe_01_l": np.array([0.62, 0, 1.03])}
    P = np.array([[0.52, 0.01, 1.135], [0.61, 0, 1.03]])
    assert FP._region(P, J, ("lowerarm_l", "hand_l")).tolist() == [True, True]
