# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Generate every canon golden case: synthetic inputs (OBJ / JSON) and expected.json per case.

    python3 gen_goldens.py [out_dir]        # default: the directory of this file

Expected values are ANALYTIC (derived from the construction), never produced by running the tool under test. Where a value
is a measured property of the fixture (e.g. the error of a known-wrong method), the docstring of the case says how it is
computed, and selftest.py recomputes it independently. Deterministic: run twice, compare bytes."""

import math
import sys
from pathlib import Path

import numpy as np

import meshgen as M


# ------------------------------------------------------------------ C01 rigid similarity (canon 02)
def c01_rigid(out):
    rng = np.random.default_rng(1)
    P = rng.uniform(-0.15, 0.15, (40, 3))
    R = M.rot((1, 2, 3), 37.0)
    s, t = 1.07, np.array([0.12, -0.40, 1.30])
    Q = s * P @ R.T + t
    Qm = Q * np.array([-1, 1, 1])                       # a mirror image: no PROPER similarity fits it
    Qb = 1.01 * ((P - P.mean(0)) @ R.T) + P.mean(0) @ R.T + t       # 'breathing' by 1 %: a rigid test must see it
    Qd = Q.copy()
    Qd[7] += (0.005, 0, 0)                              # one vertex moved 5 mm
    M.write_json(out / "C01_rigid/input.json", M.r9({"P": P, "Q_similar": Q, "Q_mirror": Qm, "Q_breathe_1pct": Qb, "Q_one_vertex_5mm": Qd}))
    rmax = float(np.linalg.norm(P - P.mean(0), axis=1).max())
    M.write_json(out / "C01_rigid/expected.json", M.r9({
        "Q_similar": {"scale": s, "rotation_deg": 37.0, "axis": (np.array([1, 2, 3]) / math.sqrt(14)).tolist(), "translation_m": t, "rms_m": 0.0, "tol": 1e-9},
        "Q_mirror": {"det_R": 1.0, "rms_m_min": 0.01, "why": "a proper rotation cannot reproduce a reflection; a solver that returns det -1 is wrong"},
        "Q_breathe_1pct": {"with_scale_false_max_m_min": 0.5 * 0.01 * rmax, "with_scale_true_scale": 1.01, "why": "scale is never fitted per pose (metal pose receipt)"},
        "Q_one_vertex_5mm": {"max_m_min": 0.004, "max_m_max": 0.005, "rms_m_max": 0.005 / math.sqrt(40) + 1e-4},
    }))


# ------------------------------------------------------------------ C02 bind at the fit pose and return to rest (canon 04)
def _two_bone():
    heads = {"A": np.array([0.0, 0.0, 0.0]), "B": np.array([0.0, 0.0, 0.3])}
    return heads


def c02_inverse_lbs(out):
    """A piece authored at the FIT pose (bone B turned 60 deg about X at its head) must be returned to the REST pose so that
    forward LBS of the returned rest reproduces the authored fit-pose geometry exactly.
    exact:  p_rest = (sum_b w_b M_b)^-1 p_fit    (inverse of the blend)
    wrong:  p_rest = sum_b w_b M_b^-1 p_fit      (blend of inverses; equipment_fitpose.bind_return and GENERATED-EQUIPMENT 7l)"""
    heads = _two_bone()
    MB = M.about(M.rot((1, 0, 0), 60.0), heads["B"])
    Vr, F = M.tube(0.05, 0.10, 0.50, 17, 16)
    z = Vr[:, 2]
    u = np.clip((z - 0.25) / 0.10, 0, 1)
    wB = u * u * (3 - 2 * u)                             # smoothstep blend over the elbow band 0.25..0.35
    W = np.stack([1 - wB, wB], 1)
    # the fixture's fit-pose geometry is the forward LBS of a known rest, so the exact rest is known
    Vf = np.array([((1 - b) * np.eye(4) + b * MB) @ np.r_[p, 1] for p, b in zip(Vr, wB)])[:, :3]
    M.write_obj(out / "C02_inverse_lbs/piece_fit_pose.obj", Vf, F, header="tube authored at the fit pose; weights in weights.json")
    blend_err = []
    for p, b in zip(Vf, wB):
        q = ((1 - b) * np.eye(4) + b * np.linalg.inv(MB)) @ np.r_[p, 1]
        back = ((1 - b) * np.eye(4) + b * MB) @ q
        blend_err.append(np.linalg.norm(back[:3] - p))
    blend_err = np.array(blend_err)
    M.write_json(out / "C02_inverse_lbs/weights.json", M.r9({"bones": ["A", "B"], "heads": heads, "W": W, "fit_pose": {"B": MB}, "rest_pose": {"A": np.eye(4), "B": np.eye(4)}}))
    # the singular case: equal weights, 180 deg -> the blended linear part has rank 1
    MB180 = M.about(M.rot((1, 0, 0), 180.0), heads["B"])
    M.write_json(out / "C02_inverse_lbs/expected.json", M.r9({
        "exact_inverse": {"rest_vertices": Vr, "max_round_trip_m": 0.0, "tol": 1e-12},
        "blend_of_inverses": {"max_round_trip_m": float(blend_err.max()), "vertices_over_1mm": int((blend_err > 0.001).sum()),
                              "rigid_vertices_error_m": 0.0, "why": "inverse(sum w A) != sum w inverse(A): the error lives only in blended vertices"},
        "singular": {"weights": [0.5, 0.5], "fit_pose_B": MB180, "expected": "REFUSE: the blended transform is singular (det of linear part = 0)"},
    }))


# ------------------------------------------------------------------ C03 one shell, two parts: the seam (canon 07, 05)
def c03_seam_tube(out):
    """A genned piece is ONE shell cut into parts; the cut ring exists twice (UV-split duplicates at identical positions).
    Twist spine_03 by 40 deg: one bone per part opens the seam by the chord 2 r sin(theta/2); weights by position keep it 0."""
    r, zs, th = 0.12, 1.20, 40.0
    segs = 32
    Vlo, Flo = M.tube(r, 0.95, zs, 6, segs)
    Vhi, Fhi = M.tube(r, zs, 1.50, 7, segs)
    V = np.vstack([Vlo, Vhi])
    F = Flo + [tuple(i + len(Vlo) for i in f) for f in Fhi]
    groups = {"lower": list(range(len(Flo))), "upper": list(range(len(Flo), len(F)))}
    M.write_obj(out / "C03_seam_tube/piece.obj", V, F, groups=groups, header="one shell, two parts; the ring at z=1.20 is duplicated (UV-split)")
    seam_pairs = [[(5 * segs) + j, len(Vlo) + j] for j in range(segs)]
    bones = {"spine_01": {"head": [0, 0, 0.95], "tail": [0, 0, 1.20], "parent": None}, "spine_03": {"head": [0, 0, 1.20], "tail": [0, 0, 1.55], "parent": "spine_01"}}
    M.write_json(out / "C03_seam_tube/rig.json", M.r9({"bones": bones, "pose": {"spine_03": {"axis_world": [0, 0, 1], "deg": th, "about": "head"}},
                                                         "seam_pairs_source_ledger": seam_pairs}))
    M.write_json(out / "C03_seam_tube/expected.json", M.r9({
        "seam_ledger_pairs": segs,
        "per_part_bones": {"seam_gap_max_m": 2 * r * math.sin(math.radians(th) / 2), "tol": 1e-9,
                           "recorded_real_case": "cuirass opened 7.3 cm in a twist (memory seams-need-positional-weights, 2026-09-29)"},
        "positional_weights": {"seam_gap_max_m": 0.0, "tol": 1e-12, "rule": "both copies of a seam vertex get bit-identical weight vectors"},
    }))


# ------------------------------------------------------------------ C04 weld before inpainting (canon 07)
def c04_weld_inpaint(out):
    """Two UV islands of one surface share a seam row by POSITION but not by index (smart-mesh split). Island A lies on the
    body (matched); island B is beyond the transfer distance (unmatched). A graph fill over vertex indices cannot reach B;
    the same fill over position-welded vertices fills it."""
    nx, ny, h = 6, 5, 0.02
    VA, VB = [], []
    for j in range(ny):
        for i in range(nx):
            VA.append((i * h, j * h, 0.0))
    for j in range(ny):
        for i in range(nx):
            VB.append(((nx - 1) * h + i * h, j * h, 0.0))       # column i=0 of B duplicates column nx-1 of A
    V = np.array(VA + VB)
    F = []
    for base in (0, nx * ny):
        for j in range(ny - 1):
            for i in range(nx - 1):
                a = base + j * nx + i
                F.append((a, a + 1, a + nx + 1, a + nx))
    matched = np.array([True] * (nx * ny) + [False] * (nx * ny))
    x = V[:, 0]
    W = np.stack([1 - x / x.max(), x / x.max()], 1) * matched[:, None]
    M.write_obj(out / "C04_weld_inpaint/piece.obj", V, F, header="two islands split at x=0.10 (duplicated column), island B unmatched")
    M.write_json(out / "C04_weld_inpaint/matches.json", M.r9({"bones": ["thigh_l", "calf_l"], "matched": matched, "W_matched": W, "weld_m": 1e-5}))
    M.write_json(out / "C04_weld_inpaint/expected.json", {
        "unwelded_index_graph_fill": {"unweighted_vertices": nx * ny - 0, "why": "every vertex of island B (30) keeps no weight: its graph component has no constraint"},
        "welded_fill": {"unweighted_vertices": 0, "duplicate_pairs_bit_identical": ny, "sums_to_one_tol": 1e-9},
    })


# ------------------------------------------------------------------ C05 signed distance and inside/outside (canon 15)
def c05_clearance(out):
    """(a) closed sphere: signed distance is |p-c| - r analytically. (b) a needle spike: the query point's nearest body point
    is the apex, where an arbitrary incident face normal gives the WRONG sign; the generalized winding number does not.
    (c) an open body (cap removed) must refuse nearest-normal signing near the opening."""
    c, r = np.array([0.0, 0.0, 1.0]), 0.2
    V, F = M.uv_sphere(r, 48, 24, c)
    M.write_obj(out / "C05_clearance/sphere.obj", V, F)
    rng = np.random.default_rng(5)
    dirs = rng.normal(size=(60, 3))
    dirs /= np.linalg.norm(dirs, axis=1, keepdims=True)
    rad = np.r_[np.linspace(0.05, 0.19, 30), np.linspace(0.21, 0.30, 30)]
    Pq = c + dirs * rad[:, None]
    sd = rad - r
    # spike: square pyramid, base half-width 0.02 at z=0, apex at z=1 (needle), closed with its base
    Vs = np.array([[0, 0, 1.0], [-0.02, -0.02, 0], [0.02, -0.02, 0], [0.02, 0.02, 0], [-0.02, 0.02, 0]])
    Fs = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1), (1, 4, 3, 2)]
    M.write_obj(out / "C05_clearance/spike.obj", Vs, Fs)
    pq = np.array([0.05, 0.0, 1.01])
    nfar = np.cross(Vs[4] - Vs[0], Vs[1] - Vs[0])
    nfar /= np.linalg.norm(nfar)
    # open sphere: remove the top cap ring (the 'headless body')
    Fo = [f for f in F if min(V[list(f)][:, 2]) < c[2] + 0.17]
    M.write_obj(out / "C05_clearance/open_sphere.obj", V, Fo, header="sphere with its top cap removed: an open body")
    sag = r * (1 - math.cos(math.pi / 48))
    M.write_json(out / "C05_clearance/queries.json", M.r9({"sphere_points": Pq, "spike_point": pq}))
    M.write_json(out / "C05_clearance/expected.json", M.r9({
        "sphere": {"signed_distance_m": sd, "tol_m": 2 * sag + 1e-6, "sign_exact_beyond_m": 2 * sag},
        "spike": {"inside": False, "winding_number": 0.0, "winding_tol": 1e-6,
                  "far_face_normal_sign": float(np.sign(np.dot(pq - Vs[0], nfar))), "why": "nearest point = apex; the far face's normal says INSIDE (wrong)"},
        "open_sphere": {"point_inside_near_top": [0, 0, c[2] + 0.18], "expected": "REFUSE signed clearance on an open body, or report the winding number with the body declared open"},
    }))


# ------------------------------------------------------------------ C06 placement by enclosure (canon 09)
def c06_enclosure(out):
    """Elliptic torso a=0.17 (x), b=0.12 (y). The piece's INNER wall is the body + 15 mm all round; its front wall is 30 mm
    thick and its back 5 mm (ornaments in front). The piece arrives displaced by d0. Expected placements:
    inner-wall enclosure recovers d0 exactly; all-vertex extents midpoint is biased by (t_front - t_back)/2."""
    a, b, C, tf, tb = 0.17, 0.12, 0.015, 0.030, 0.005
    d0 = np.array([0.012, 0.040, 0.0])
    zs = np.linspace(1.0, 1.4, 9)
    segs = 72
    body, inner, outer = [], [], []
    for z in zs:
        for j in range(segs):
            th = 2 * math.pi * j / segs
            ca, sa = math.cos(th), math.sin(th)
            body.append((a * ca, b * sa, z))
            inner.append(((a + C) * ca, (b + C) * sa, z))
            # thickness: front (-y, sa<0) tf, back tb, blended smoothly by sin
            t = tb + (tf - tb) * max(0.0, -sa)
            outer.append(((a + C + t) * ca, (b + C + t) * sa, z))
    def grid(Vl):
        F = []
        for i in range(len(zs) - 1):
            for j in range(segs):
                p, q = i * segs + j, i * segs + (j + 1) % segs
                F.append((p, q, q + segs, p + segs))
        return np.array(Vl), F
    Vb, Fb = grid(body)
    Vi, Fi = grid(inner)
    Vo, Fo = grid(outer)
    Vp = np.vstack([Vi, Vo]) + d0
    Fp = Fi + [tuple(k + len(Vi) for k in f) for f in Fo]
    M.write_obj(out / "C06_enclosure/body.obj", Vb, Fb)
    M.write_obj(out / "C06_enclosure/piece_displaced.obj", Vp, Fp, groups={"inner": list(range(len(Fi))), "outer": list(range(len(Fi), len(Fp)))})
    allv_err_y = (tf - tb) / 2           # all-vertex midpoint sits (tb-tf)/2 toward the front; correcting by it overshoots back
    M.write_json(out / "C06_enclosure/expected.json", M.r9({
        "inner_wall_enclosure": {"translation_m": -d0, "tol_m": 0.001},
        "all_vertex_extents_midpoint": {"translation_error_y_m": allv_err_y, "why": "outer extents include the thick front: a placement by them leaves the inner wall (tf-tb)/2 toward the thin (+y, back) side"},
        "centroid": {"why": "not a placement rule: a centroid follows mass, not enclosure"},
    }))


# ------------------------------------------------------------------ C07 pose the body to the piece (canon 08)
def c07_pose_solve(out):
    """An upper-arm cylinder (r 5 cm) hangs 40 deg below horizontal (A-pose). A sleeve (inner radius 6.5 cm = 15 mm clearance)
    was authored around an arm lowered 30 deg further. Sweeping the 'lower' DOF 0..40 step 5 must pick 30 with zero
    penetration, while the A-pose (0) penetrates."""
    sh = np.array([0.20, 0.0, 1.40])
    def arm_dir(lower):
        ang = math.radians(-40.0 - lower)
        return np.array([math.cos(ang), 0.0, math.sin(ang)])
    L, ra, rs = 0.30, 0.05, 0.065
    d_s = arm_dir(30.0)
    # the sleeve: a tube from 5 to 28 cm down the authored arm axis
    Vt, Ft = M.tube(rs, 0.05, 0.28, 12, 24)
    z = np.array([0, 0, 1.0])
    Rz = _align(z, d_s)
    Vs = Vt @ Rz.T + sh
    M.write_obj(out / "C07_pose_solve/sleeve.obj", Vs, Ft)
    M.write_json(out / "C07_pose_solve/rig.json", M.r9({"shoulder": sh, "upperarm_length_m": L, "arm_radius_m": ra,
                                                         "dof": {"bone": "upperarm_l", "name": "lower", "axis_world": [0, 1, 0], "sign": "+deg lowers the arm (measured by the sign check)", "range": [0, 40], "step": 5}}))
    M.write_json(out / "C07_pose_solve/expected.json", {
        "best_lower_deg": 30, "tol_deg": 0, "penetrating_at_best": 0, "a_pose_penetrating_min": 1,
        "sign_check": "rotating +20 must move the elbow DOWN (z decreases); a negated axis must be REFUSED, not measured",
        "selection": "fewest penetrations > 10 mm, then smallest worst depth, then smallest |angle| (shelf pose_clearance.py:118)",
    })


def _align(a, b):
    a = a / np.linalg.norm(a)
    b = b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(np.dot(a, b))
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3) if c > 0 else M.rot((1, 0, 0), 180)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * (1 / (1 + c))


# ------------------------------------------------------------------ C08 multi-view joints (canon 11)
def _cam(name, res=1024, ortho=2.2, centre=(0, 0, 0.95)):
    looks = {"front": ((0, 1, 0), (1, 0, 0)), "back": ((0, -1, 0), (-1, 0, 0)), "left": ((-1, 0, 0), (0, 1, 0)), "right": ((1, 0, 0), (0, -1, 0))}
    look, right = looks[name]
    up = np.cross(right, look)
    return {"name": name, "res": res, "ortho": ortho, "center": list(centre), "right": list(map(float, right)), "up": list(map(float, up)), "look": list(map(float, look))}


def _project(cam, p):
    k = cam["res"] / cam["ortho"]
    d = np.asarray(p) - np.asarray(cam["center"])
    return cam["res"] / 2 + float(d @ cam["right"]) * k, cam["res"] / 2 - float(d @ cam["up"]) * k


def c08_multiview(out):
    """Synthetic joints seen by four orthographic cameras (front, back, left, right; pixels right and DOWN). Triangulation is
    exact for orthographic views; one view cannot fix depth; a 40 px outlier in one view is dropped by the robust rule."""
    J = {"pelvis": (0, 0.02, 0.95), "spine_03": (0, 0.0, 1.30), "head": (0, -0.01, 1.62), "upperarm_l": (0.18, 0.02, 1.42),
         "lowerarm_l": (0.40, 0.03, 1.20), "hand_l": (0.55, -0.02, 1.02), "upperarm_r": (-0.18, 0.02, 1.42), "lowerarm_r": (-0.40, 0.05, 1.20),
         "hand_r": (-0.55, -0.04, 1.02), "thigh_l": (0.10, 0.02, 0.93), "calf_l": (0.12, 0.00, 0.50), "foot_l": (0.12, 0.05, 0.08),
         "thigh_r": (-0.10, 0.02, 0.93), "calf_r": (-0.12, -0.03, 0.50), "foot_r": (-0.12, 0.06, 0.08)}
    cams = [_cam(n) for n in ("front", "back", "left", "right")]
    obs = {n: {c["name"]: _project(c, p) for c in cams} for n, p in J.items()}
    corrupt = {"joint": "lowerarm_l", "view": "left", "dx_px": 40.0}
    M.write_json(out / "C08_multiview/input.json", M.r9({"cameras": cams, "keypoints_px": obs, "corrupt": corrupt}))
    M.write_json(out / "C08_multiview/expected.json", M.r9({
        "joints_m": J, "tol_m": 1e-9,
        "front_only": "REFUSE: depth (y) unfixed by one view",
        "robust_drop_px": 4.0, "robust_with_corrupt_tol_m": 1e-9,
        "plain_least_squares_with_corrupt_error_min_m": 0.005,
    }))


# ------------------------------------------------------------------ C09 UV measurements and the smart-mesh split (canon 13)
def c09_uv(out):
    """Two 1 m quads (islands A and B) and a mirrored island C. A covers UV [0,.5]^2, B [.5,1]x[0,.25], C [0,.25]x[.5,.75]
    flipped in U. Utilization at 1024 is exact (edges on texel boundaries)."""
    V = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
                  [2, 0, 0], [3, 0, 0], [3, 1, 0], [2, 1, 0],
                  [4, 0, 0], [5, 0, 0], [5, 1, 0], [4, 1, 0]], float)
    UV = np.array([[0, 0], [.5, 0], [.5, .5], [0, .5],
                   [.5, 0], [1, 0], [1, .25], [.5, .25],
                   [.25, .5], [0, .5], [0, .75], [.25, .75]], float)
    F = [(0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11)]
    FUV = [(0, 1, 2, 3), (4, 5, 6, 7), (8, 9, 10, 11)]
    M.write_obj(out / "C09_uv/three_islands.obj", V, F, UV, FUV)
    # overlap variant: B placed over A
    UV2 = UV.copy()
    UV2[4:8] = [[0, 0], [.5, 0], [.5, .25], [0, .25]]
    M.write_obj(out / "C09_uv/overlap.obj", V, F, UV2, FUV)
    # split-vertex variant: one surface 2x1 m cut into two UV islands at x=1; the seam column is duplicated by index
    Vs = np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0], [1, 0, 0], [2, 0, 0], [2, 1, 0], [1, 1, 0]], float)
    UVs = np.array([[0, 0], [.4, 0], [.4, .4], [0, .4], [.5, 0], [.9, 0], [.9, .4], [.5, .4]], float)
    M.write_obj(out / "C09_uv/split_seam.obj", Vs, [(0, 1, 2, 3), (4, 5, 6, 7)], UVs, [(0, 1, 2, 3), (4, 5, 6, 7)])
    # relief islands: 100 faces of 64 mm^2 (a dense relief) and 10 faces of 400 mm^2 (a plate), per the 70 mm^2 rule
    M.write_json(out / "C09_uv/relief_islands.json", {"islands": [{"id": 0, "faces": 100, "mean_face_mm2": 64.0}, {"id": 1, "faces": 10, "mean_face_mm2": 400.0},
                                                                   {"id": 2, "faces": 40, "mean_face_mm2": 58.0}, {"id": 3, "faces": 30, "mean_face_mm2": 79.0}]})
    sA, sB, sC = math.sqrt(0.25), math.sqrt(0.125), math.sqrt(0.0625)
    s = np.array([sA, sA, sB, sB, sC, sC])
    sn = s / np.median(s)
    M.write_json(out / "C09_uv/expected.json", M.r9({
        "three_islands": {"utilization_1024": 0.25 + 0.125 + 0.0625, "overlap": 0.0, "islands": 3, "flipped_fraction_faces": 1 / 3,
                          "texel_density_px_per_m_2048": {"A": 2048 * sA, "B": 2048 * sB, "C": 2048 * sC},
                          "off_density_2x": float(np.mean((sn > 2) | (sn < 0.5)))},
        "overlap": {"overlap_fraction_of_covered": 0.125 / (0.25 + 0.0625), "utilization_1024": 0.25 + 0.0625},
        "raster_rule": "a texel counts for a triangle under a half-open (top-left) edge rule; an inclusive rule double-counts texel centres on an island's own diagonal as overlap (0.00167 here)",
        "split_seam": {"components_by_vertex_index": 2, "components_by_position_weld_1e-5": 1, "uv_islands": 2,
                       "why": "Tripo smart meshes duplicate vertices at every UV seam: index adjacency sees each island as its own component"},
        "relief_islands": {"threshold_mm2": 70.0, "relief": [0, 2], "not_relief": [1, 3]},
    }))


# ------------------------------------------------------------------ C10 cage ray-cast bake (canon 14)
def c10_bake(out):
    """LP: flat plane z=0, [-0.5,0.5]^2, UV=(x+0.5,y+0.5), tangent +U=+X, bitangent +V=+Y. HP: the same plane with a
    spherical cap (base radius a=0.15, height h=0.05, sphere radius R=(a^2+h^2)/(2h)=0.25, centre z=h-R). Expected tangent
    normal at a texel inside the footprint: (x, y, sqrt(R^2-rho^2))/R; outside (0,0,1). Variant 'sunk': HP lowered 1 cm."""
    a, h = 0.15, 0.05
    R = (a * a + h * h) / (2 * h)
    zc = h - R
    n = 61
    xs = np.linspace(-0.5, 0.5, n)
    Vh, Fh = [], []
    for j in range(n):
        for i in range(n):
            x, y = xs[i], xs[j]
            rho = math.hypot(x, y)
            z = (math.sqrt(R * R - rho * rho) + zc) if rho < a else 0.0
            Vh.append((x, y, max(z, 0.0)))
    for j in range(n - 1):
        for i in range(n - 1):
            p = j * n + i
            Fh.append((p, p + 1, p + n + 1, p + n))
    M.write_obj(out / "C10_bake/hp_bump.obj", Vh, Fh, header="heightfield tessellation; the analytic surface is in expected.json")
    Vl = np.array([[-0.5, -0.5, 0], [0.5, -0.5, 0], [0.5, 0.5, 0], [-0.5, 0.5, 0]], float)
    M.write_obj(out / "C10_bake/lp_plane.obj", Vl, [(0, 1, 2, 3)], np.array([[0, 0], [1, 0], [1, 1], [0, 1]], float), [(0, 1, 2, 3)])
    samples = []
    for (u, v) in [(0.5, 0.5), (0.55, 0.5), (0.5, 0.6), (0.58, 0.58), (0.62, 0.5), (0.9, 0.9), (0.1, 0.5)]:
        x, y = u - 0.5, v - 0.5
        rho = math.hypot(x, y)
        nrm = np.array([x, y, math.sqrt(R * R - rho * rho)]) / R if rho < a else np.array([0, 0, 1.0])
        gl = (nrm + 1) / 2
        dx = gl.copy()
        dx[1] = 1 - dx[1]
        samples.append({"uv": [u, v], "normal_tangent": nrm, "rgb_gl": gl, "rgb_dx": dx})
    footprint = math.pi * a * a          # area fraction of the unit plane covered by the cap base
    M.write_json(out / "C10_bake/expected.json", M.r9({
        "surface": {"cap_base_radius": a, "cap_height": h, "sphere_radius": R, "sphere_centre_z": zc},
        "samples": samples, "tol_normal": 0.02, "tol_rgb": 0.01,
        "base_case": {"cage_extrusion": 0.06, "max_ray": 0.12, "hit_fraction": 1.0,
                      "rule": "the cage must ENCLOSE the high-poly (extrusion >= its greatest height above the low-poly) and the ray must reach its greatest depth below (max_ray >= extrusion + depth)"},
        "dx_is_gl_green_flipped": True,
        "sunk_variant": {"hp_offset_z": -0.01, "cage_extrusion": 0.06,
                         "max_ray_0p5x_cage": {"max_ray": 0.03, "hit_fraction_max": 0.03,
                                               "why": "rays from the cage (z=+0.06) travel 0.03 and stop at z=+0.03: the sunk plane (z=-0.01) and most of the cap are missed; only the cap's top (rho <= 0.07 m, area 0.0154) is hit"},
                         "max_ray_2x_cage": {"max_ray": 0.12, "hit_fraction": 1.0}},
    }))


# ------------------------------------------------------------------ C11 proportion primitives (canon 10)
def c11_proportion(out):
    """Sections of an elliptic body (a, b per level) and of a piece = body + C on both axes. The section-extent primitive must
    give W=2(a+C), D=2(b+C); ratios against body+C deviate 0; a uniform rescale leaves ratios unchanged; a 10 % depth scale
    moves D/W by exactly +10 %. Plus the silhouette aspect trap."""
    levels = [(1.0, 0.150, 0.110), (1.2, 0.165, 0.120), (1.4, 0.175, 0.125)]
    C = 0.015
    M.write_json(out / "C11_proportion/sections.json", {"levels_z_a_b": levels, "clearance_m": C})
    rows = []
    for z, a, b in levels:
        rows.append({"z": z, "W": 2 * (a + C), "D": 2 * (b + C), "DW": (b + C) / (a + C)})
    # silhouette aspect: a 2:1 rectangle mask vs a 1:1 square mask
    M.write_json(out / "C11_proportion/expected.json", M.r9({
        "sections": rows, "rms_logdev_vs_body_plus_C": 0.0, "uniform_scale_1p37_dev": 0.0, "depth_x1p10_DW_dev_pct": 10.0, "tol": 1e-9,
        "silhouette_aspect": {"mask_a": "rectangle 200x100 px", "mask_b": "square 100x100 px",
                              "iou_aspect_preserved": 0.5, "iou_crop_and_stretch_to_square": 1.0,
                              "why": "cropping each mask to its own box and resizing to a square erases proportion (astra measure.py; Lampway silhouette._fit)"},
    }))


# ------------------------------------------------------------------ C12 the gasket opening (canon 06)
def c12_gasket(out):
    """A cylinder shell (r 9 cm) capped at its top (fan) around a neck cylinder (r 5.5 cm). Gasket with 15 mm clearance:
    the cap's inside goes, a rim loop at r 7.0 cm appears, the collar runs flange_mm into the piece."""
    Vt, Ft = M.tube(0.09, 1.40, 1.60, 5, 32)
    centre = len(Vt)
    V = np.vstack([Vt, [[0, 0, 1.60]]])
    top = 4 * 32
    F = Ft + [(top + j, top + (j + 1) % 32, centre) for j in range(32)]
    M.write_obj(out / "C12_gasket/piece_capped.obj", V, F, header="open bottom rim, capped top")
    Vn, Fn = M.tube(0.055, 1.30, 1.75, 4, 32)
    M.write_obj(out / "C12_gasket/neck.obj", Vn, Fn)
    M.write_json(out / "C12_gasket/expected.json", {
        "detect": {"capped_sites": 1, "axis": [0, 0, 1], "plane_z": 1.60},
        "gasket_clearance_15mm": {"rim_radius_m": 0.070, "rim_tol_m": 0.0015, "boundary_loops_after": 2, "non_manifold_edges": 0, "bad_winding_edges": 0,
                                  "collar_depth": "= flange_mm (no default: the captain's number)"},
        "keep": {"mesh_sha_unchanged": True},
        "too_small": {"neck_radius_m": 0.08, "expected": "REFUSE: the body's section plus clearance does not fit inside this opening"},
    })


# ------------------------------------------------------------------ C13 retopology targets (canon 12)
def c13_retopo(out):
    V, F = M.uv_sphere(0.5, 64, 32)
    M.write_obj(out / "C13_retopo/sphere_dense.obj", V, F)
    M.write_json(out / "C13_retopo/expected.json", {
        "surface": "sphere r=0.5 at origin: deviation of a vertex = | |p| - 0.5 |",
        "target_faces": 600, "faces_within_frac": 0.35, "quad_fraction_min": 0.90, "max_deviation_rel_diag_max": 0.05,
        "non_manifold_edges": 0, "deterministic_repeat": "same input, same seed: byte-identical OBJ",
        "source_untouched": True,
    })


# ------------------------------------------------------------------ C14 validation controls (canon 05)
def c14_controls(out):
    """A 4 mm metal rivet sits 2 mm outside a sphere 'body' (r 0.2). The positive crossing control pushes the piece INTO the
    skin where it is nearest. Uncapped (1 cm) the rivet is buried whole and a SURFACE-crossing counter sees nothing; capped at
    half the piece's extent along the push (2 mm) it straddles the skin. Titan armour_validate.control_shift (run25)."""
    c, r, half, gap = np.array([0.0, 0.0, 1.0]), 0.2, 0.002, 0.002
    ctr = c + np.array([0, -(r + gap + half), 0])
    corners = np.array([[x, y, z] for x in (-half, half) for y in (-half, half) for z in (-half, half)]) + ctr
    F = [(0, 1, 3, 2), (4, 6, 7, 5), (0, 4, 5, 1), (2, 3, 7, 6), (0, 2, 6, 4), (1, 5, 7, 3)]
    M.write_obj(out / "C14_controls/rivet.obj", corners, F)
    M.write_json(out / "C14_controls/expected.json", M.r9({
        "body": {"sphere_centre": c, "radius": r}, "push_direction": [0, 1, 0],
        "uncapped_1cm": {"surface_crossing_edges": 0, "inside_vertices": 8, "verdict": "control UNPROVEN for a surface-crossing instrument"},
        "capped_half_extent": {"push_m": gap + half, "surface_crossing_edges_min": 4, "why": "the push = distance to the skin + min(depth, half extent): the rivet straddles the skin"},
    }))


def main(out=None):
    out = Path(out or Path(__file__).parent)
    for f in (c01_rigid, c02_inverse_lbs, c03_seam_tube, c04_weld_inpaint, c05_clearance, c06_enclosure, c07_pose_solve, c08_multiview,
              c09_uv, c10_bake, c11_proportion, c12_gasket, c13_retopo, c14_controls):
        f(out)
    print("goldens written:", out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
