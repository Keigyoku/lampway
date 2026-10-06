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


def test_g09_5_boots_without_an_anchor_are_refused_naming_the_three(goldens, tmp_path):
    body, piece = _npz(tmp_path, goldens)
    with pytest.raises(FP.PlaceError) as e:
        FP.place("boots", body, piece)
    assert all(a in str(e.value) for a in ("width", "height", "foot"))


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
