# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Self-test of the goldens: each case's expected values are reproduced by the canonical method in reference.py, and each
case's FALSIFIER (the known-wrong method) is shown to fail it. Exit 0 only when every check holds.

    python3 selftest.py [goldens_dir]"""

import json
import math
import sys
from pathlib import Path

import numpy as np

import meshgen as M
import reference as R

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent
RESULTS = []


def check(case, name, ok, detail=""):
    RESULTS.append((case, name, bool(ok), detail))


def J(p):
    return json.loads((ROOT / p).read_text())


def c01():
    inp, exp = J("C01_rigid/input.json"), J("C01_rigid/expected.json")
    P = np.array(inp["P"])
    f = R.similarity_fit(P, np.array(inp["Q_similar"]))
    ang, ax = R.rotation_angle_axis(f["R"])
    e = exp["Q_similar"]
    check("C01", "similar: scale, angle, axis, t, rms", abs(f["s"] - e["scale"]) < e["tol"] and abs(ang - e["rotation_deg"]) < 1e-6 and np.allclose(ax, e["axis"], atol=1e-6)
          and np.allclose(f["t"], e["translation_m"], atol=1e-6) and f["rms"] < 1e-6, f"s={f['s']:.9f} ang={ang:.6f} rms={f['rms']:.2e}")
    fm = R.similarity_fit(P, np.array(inp["Q_mirror"]))
    check("C01", "mirror: proper rotation, residual shows the reflection", np.linalg.det(fm["R"]) > 0.999 and fm["rms"] > exp["Q_mirror"]["rms_m_min"], f"rms={fm['rms']:.4f}")
    fb = R.similarity_fit(P, np.array(inp["Q_breathe_1pct"]), with_scale=False)
    fbs = R.similarity_fit(P, np.array(inp["Q_breathe_1pct"]), with_scale=True)
    check("C01", "breathing: rigid fit sees 1 %, a scaled fit hides it", fb["max"] >= exp["Q_breathe_1pct"]["with_scale_false_max_m_min"] and fbs["rms"] < 1e-9
          and abs(fbs["s"] - 1.01) < 1e-9, f"rigid max={fb['max'] * 1000:.3f} mm, scaled rms={fbs['rms']:.1e}")
    fd = R.similarity_fit(P, np.array(inp["Q_one_vertex_5mm"]))
    e = exp["Q_one_vertex_5mm"]
    check("C01", "one vertex 5 mm: max residual", e["max_m_min"] <= fd["max"] <= e["max_m_max"], f"max={fd['max'] * 1000:.3f} mm")


def c02():
    w, exp = J("C02_inverse_lbs/weights.json"), J("C02_inverse_lbs/expected.json")
    V, F, *_ = M.read_obj(ROOT / "C02_inverse_lbs/piece_fit_pose.obj")
    W = np.array(w["W"])
    mats = [np.eye(4), np.array(w["fit_pose"]["B"])]
    rest = np.array([R.lbs_inverse(p, ww, mats) for p, ww in zip(V, W)])
    err_exact = max(np.linalg.norm(R.lbs(q, ww, mats) - p) for q, p, ww in zip(rest, V, W))
    check("C02", "exact inverse recovers the rest", np.abs(rest - np.array(exp["exact_inverse"]["rest_vertices"])).max() < 1e-7 and err_exact < 1e-9, f"round trip {err_exact:.1e} m")
    wrong = np.array([R.blend_of_inverses(p, ww, mats) for p, ww in zip(V, W)])
    err_wrong = np.array([np.linalg.norm(R.lbs(q, ww, mats) - p) for q, p, ww in zip(wrong, V, W)])
    eb = exp["blend_of_inverses"]
    rigid = (W.max(1) > 1 - 1e-12)
    check("C02", "falsifier: blend of inverses fails in the band only", abs(err_wrong.max() - eb["max_round_trip_m"]) < 1e-7 and err_wrong[rigid].max() < 1e-9
          and int((err_wrong > 0.001).sum()) == eb["vertices_over_1mm"], f"max {err_wrong.max() * 1000:.3f} mm over {int((err_wrong > 0.001).sum())} vertices")
    try:
        R.lbs_inverse(np.array([0, 0.05, 0.3]), [0.5, 0.5], [np.eye(4), np.array(exp["singular"]["fit_pose_B"])])
        check("C02", "singular blend refused", False)
    except ValueError:
        check("C02", "singular blend refused", True)


def c03():
    V, F, _, _, groups = M.read_obj(ROOT / "C03_seam_tube/piece.obj")
    rig, exp = J("C03_seam_tube/rig.json"), J("C03_seam_tube/expected.json")
    pairs = np.array(rig["seam_pairs_source_ledger"])
    check("C03", "ledger pairs = exact duplicates", len(pairs) == exp["seam_ledger_pairs"] and np.abs(V[pairs[:, 0]] - V[pairs[:, 1]]).max() == 0.0)
    head = np.array(rig["bones"]["spine_03"]["head"])
    Mt = M.about(M.rot((0, 0, 1), rig["pose"]["spine_03"]["deg"]), head)
    upper_v = sorted({v for k in groups["upper"] for v in F[k]})
    posed_part = V.copy()
    for i in upper_v:                                   # per-part rigid bones: the upper part rides spine_03 whole
        posed_part[i] = (Mt @ np.r_[V[i], 1])[:3]
    gap_part = np.linalg.norm(posed_part[pairs[:, 0]] - posed_part[pairs[:, 1]], axis=1).max()
    e = exp["per_part_bones"]
    check("C03", "per-part bones open the seam by the chord", abs(gap_part - e["seam_gap_max_m"]) < 1e-6, f"{gap_part * 100:.3f} cm")
    z = V[:, 2]
    u = np.clip((z - 1.15) / 0.10, 0, 1)
    wB = u * u * (3 - 2 * u)                           # weights by POSITION only (a 10 cm band about the cut)
    posed_pos = np.array([((1 - b) * np.eye(4) + b * Mt) @ np.r_[p, 1] for p, b in zip(V, wB)])[:, :3]
    gap_pos = np.linalg.norm(posed_pos[pairs[:, 0]] - posed_pos[pairs[:, 1]], axis=1).max()
    check("C03", "positional weights keep it closed", gap_pos < 1e-12, f"{gap_pos:.1e} m")


def c04():
    V, F, *_ = M.read_obj(ROOT / "C04_weld_inpaint/piece.obj")
    mt, exp = J("C04_weld_inpaint/matches.json"), J("C04_weld_inpaint/expected.json")
    matched, W0 = np.array(mt["matched"]), np.array(mt["W_matched"])
    def fill(keyof):
        keys = [keyof(i) for i in range(len(V))]
        uniq = {k: n for n, k in enumerate(dict.fromkeys(keys))}
        idx = np.array([uniq[k] for k in keys])
        n = len(uniq)
        nb = [set() for _ in range(n)]
        for f in F:
            for a, b in zip(f, f[1:] + f[:1]):
                nb[idx[a]].add(idx[b]); nb[idx[b]].add(idx[a])
        fixed = np.zeros(n, bool)
        Wc = np.zeros((n, W0.shape[1]))
        for i in range(len(V)):
            if matched[i]:
                fixed[idx[i]] = True
                Wc[idx[i]] = W0[i]
        for _ in range(4000):
            new = Wc.copy()
            for k in np.flatnonzero(~fixed):
                if nb[k]:
                    new[k] = Wc[list(nb[k])].mean(0)
            Wc = new
        return Wc[idx]
    Wi = fill(lambda i: i)
    Ww = fill(lambda i: tuple(np.round(V[i] / 1e-5).astype(int)))
    unw_i = int((Wi.sum(1) < 1e-6).sum())
    unw_w = int((Ww.sum(1) < 1e-6).sum())
    keys = [tuple(np.round(v / 1e-5).astype(int)) for v in V]
    dup = [(i, j) for i in range(len(V)) for j in range(i + 1, len(V)) if keys[i] == keys[j]]
    ident = all(np.array_equal(Ww[i], Ww[j]) for i, j in dup)
    check("C04", "falsifier: index-graph fill leaves island B empty", unw_i == exp["unwelded_index_graph_fill"]["unweighted_vertices"], f"{unw_i} unweighted")
    check("C04", "welded fill weights everything, duplicates identical", unw_w == 0 and ident and len(dup) == exp["welded_fill"]["duplicate_pairs_bit_identical"]
          and np.abs(Ww.sum(1) - 1).max() < 1e-6, f"{unw_w} unweighted, {len(dup)} duplicate pairs")


def c05():
    exp, q = J("C05_clearance/expected.json"), J("C05_clearance/queries.json")
    V, F, *_ = M.read_obj(ROOT / "C05_clearance/sphere.obj")
    T = M.triangulate(F)
    e = exp["sphere"]
    errs, signs = [], []
    for p, sd in zip(np.array(q["sphere_points"]), e["signed_distance_m"]):
        got, _ = R.signed_distance(V, T, p)
        errs.append(abs(got - sd))
        if abs(sd) > e["sign_exact_beyond_m"]:
            signs.append(np.sign(got) == np.sign(sd))
    check("C05", "sphere signed distance", max(errs) <= e["tol_m"] and all(signs), f"max err {max(errs) * 1000:.3f} mm")
    Vs, Fs, *_ = M.read_obj(ROOT / "C05_clearance/spike.obj")
    Ts = M.triangulate(Fs)
    p = np.array(q["spike_point"])
    w = R.winding_number(Vs, Ts, p)
    signs = []
    for t in Ts:
        if 0 in t:
            n = np.cross(Vs[t[1]] - Vs[t[0]], Vs[t[2]] - Vs[t[0]])
            signs.append(np.sign((p - Vs[0]) @ n))
    check("C05", "spike: winding number says outside", abs(w) < exp["spike"]["winding_tol"], f"w={w:.2e}")
    check("C05", "falsifier: some apex face normal says inside", min(signs) < 0, f"apex face signs {sorted(set(int(s) for s in signs))}")
    Vo, Fo, *_ = M.read_obj(ROOT / "C05_clearance/open_sphere.obj")
    wo = R.winding_number(Vo, M.triangulate(Fo), np.array(exp["open_sphere"]["point_inside_near_top"]))
    check("C05", "open body: winding is fractional (refuse or declare)", 0.05 < wo < 0.95, f"w={wo:.3f}")


def c06():
    exp = J("C06_enclosure/expected.json")
    Vb, Fb, *_ = M.read_obj(ROOT / "C06_enclosure/body.obj")
    Vp, Fp, _, _, g = M.read_obj(ROOT / "C06_enclosure/piece_displaced.obj")
    Tb, Tp = M.triangulate(Fb), M.triangulate(Fp)
    shifts_inner, shifts_all = [], []
    for z in np.linspace(1.05, 1.35, 7):
        bs = R.slice_segments(Vb, Tb, z)
        bc = R.inner_wall_centre(bs, (0.0, 0.0))
        ps = R.slice_segments(Vp, Tp, z)
        pc = R.inner_wall_centre(ps, bc)
        shifts_inner.append(bc - pc)
        pts = ps.reshape(-1, 2)
        mid = (pts.min(0) + pts.max(0)) / 2
        shifts_all.append(bc - mid)
    si, sa = np.median(shifts_inner, 0), np.median(shifts_all, 0)
    e = exp["inner_wall_enclosure"]
    check("C06", "inner-wall enclosure recovers the displacement", np.abs(si - np.array(e["translation_m"][:2])).max() < e["tol_m"], f"shift {si.round(5).tolist()}")
    err = (sa - np.array(e["translation_m"][:2]))[1]
    check("C06", "falsifier: all-vertex extents are biased by (tf-tb)/2", abs(err - exp["all_vertex_extents_midpoint"]["translation_error_y_m"]) < 0.001, f"y error {err * 1000:.2f} mm")


def c07():
    rig, exp = J("C07_pose_solve/rig.json"), J("C07_pose_solve/expected.json")
    Vs, Fs, *_ = M.read_obj(ROOT / "C07_pose_solve/sleeve.obj")
    sh = np.array(rig["shoulder"])
    def adir(lower):
        a = math.radians(-40.0 - lower)
        return np.array([math.cos(a), 0, math.sin(a)])
    sax = adir(30.0)                                   # the sleeve's axis, as authored; radius from its vertices
    rs = float(np.median(np.linalg.norm((Vs - sh) - np.outer((Vs - sh) @ sax, sax), axis=1)))
    ra = rig["arm_radius_m"]
    def penetrations(lower):
        d = adir(lower)
        u = np.cross(d, [0, 1, 0]); u /= np.linalg.norm(u)
        v = np.cross(d, u)
        deps = []
        for s in np.linspace(0.06, 0.27, 12):
            o = sh + s * d
            for k in range(16):
                th = 2 * math.pi * k / 16
                dirv = math.cos(th) * u + math.sin(th) * v
                t = R.ray_cylinder(o, dirv, sh, sax, rs, 0.05, 0.28)
                deps.append(ra - t if (t is not None and t < ra) else 0.0)
        deps = np.array(deps)
        return int((deps > 0.01).sum()), float(deps.max())
    rows = [(lo,) + penetrations(lo) for lo in range(0, 45, 5)]
    best = min(rows, key=lambda r: (r[1], r[2], abs(r[0])))
    check("C07", "the sweep picks the authored arm angle", best[0] == exp["best_lower_deg"] and best[1] == 0, f"best {best}")
    check("C07", "the A-pose penetrates", rows[0][1] >= exp["a_pose_penetrating_min"], f"A-pose {rows[0]}")


def c08():
    inp, exp = J("C08_multiview/input.json"), J("C08_multiview/expected.json")
    cams = {c["name"]: c for c in inp["cameras"]}
    worst = 0.0
    for n, p in exp["joints_m"].items():
        obs = [(cams[v], *inp["keypoints_px"][n][v], 1.0) for v in cams]
        worst = max(worst, float(np.abs(R.triangulate(obs) - np.array(p)).max()))
    check("C08", "four orthographic views triangulate exactly", worst < exp["tol_m"], f"{worst:.1e} m")
    try:
        R.triangulate([(cams["front"], *inp["keypoints_px"]["head"]["front"], 1.0)])
        check("C08", "one view refused", False)
    except ValueError:
        check("C08", "one view refused", True)
    c = inp["corrupt"]
    obs = [(cams[v], *inp["keypoints_px"][c["joint"]][v], 1.0) for v in cams]
    obs = [(o[0], o[1] + (c["dx_px"] if o[0]["name"] == c["view"] else 0.0), o[2], 1.0) for o in obs]
    true = np.array(exp["joints_m"][c["joint"]])
    plain = np.abs(R.triangulate(obs) - true).max()
    rob, used = R.triangulate_robust(obs, exp["robust_drop_px"])
    check("C08", "robust drops the corrupt view; plain is off", np.abs(rob - true).max() < exp["robust_with_corrupt_tol_m"] and plain > exp["plain_least_squares_with_corrupt_error_min_m"] and used == 3,
          f"plain {plain * 1000:.1f} mm, robust used {used}")


def c09():
    exp = J("C09_uv/expected.json")
    V, F, UV, FUV, _ = M.read_obj(ROOT / "C09_uv/three_islands.obj")
    m = R.uv_metrics(V, F, UV, FUV)
    e = exp["three_islands"]
    check("C09", "utilization, overlap, flipped", abs(m["utilization"] - e["utilization_1024"]) < 1e-9 and m["overlap"] == 0 and abs(m["flipped_tris"] - e["flipped_fraction_faces"]) < 1e-9,
          f"util {m['utilization']:.6f} flipped {m['flipped_tris']:.3f}")
    V2, F2, UV2, FUV2, _ = M.read_obj(ROOT / "C09_uv/overlap.obj")
    m2 = R.uv_metrics(V2, F2, UV2, FUV2)
    check("C09", "overlap fraction", abs(m2["overlap"] - exp["overlap"]["overlap_fraction_of_covered"]) < 1e-9 and abs(m2["utilization"] - exp["overlap"]["utilization_1024"]) < 1e-9,
          f"overlap {m2['overlap']:.4f}")
    V3, F3, UV3, FUV3, _ = M.read_obj(ROOT / "C09_uv/split_seam.obj")
    ci = R.components(F3)
    cw = R.components(F3, key=lambda v: tuple(np.round(V3[v] / 1e-5).astype(int)))
    e = exp["split_seam"]
    check("C09", "split seam: index sees 2, weld sees 1", ci == e["components_by_vertex_index"] and cw == e["components_by_position_weld_1e-5"], f"{ci} vs {cw}")
    isl = J("C09_uv/relief_islands.json")["islands"]
    rel = [i["id"] for i in isl if i["mean_face_mm2"] < exp["relief_islands"]["threshold_mm2"]]
    check("C09", "relief islands by the 70 mm2 rule", rel == exp["relief_islands"]["relief"], str(rel))


def c10():
    exp = J("C10_bake/expected.json")
    s = exp["surface"]
    a, Rr, zc = s["cap_base_radius"], s["sphere_radius"], s["sphere_centre_z"]
    b = exp["base_case"]
    ok = True
    for smp in exp["samples"]:
        n = R.bake_cap(*smp["uv"], a, Rr, zc, b["cage_extrusion"], b["max_ray"])
        ok &= n is not None and np.abs(n - np.array(smp["normal_tangent"])).max() < exp["tol_normal"]
        gl = (n + 1) / 2
        dx = gl.copy(); dx[1] = 1 - dx[1]
        ok &= np.abs(dx - np.array(smp["rgb_dx"])).max() < exp["tol_rgb"]
    check("C10", "analytic cap normals and the DX green flip", ok)
    sv = exp["sunk_variant"]
    grid = [(u, v) for u in np.linspace(0.005, 0.995, 100) for v in np.linspace(0.005, 0.995, 100)]
    def hit_frac(max_ray):
        return np.mean([R.bake_cap(u, v, a, Rr, zc, sv["cage_extrusion"], max_ray, sv["hp_offset_z"]) is not None for u, v in grid])
    h_short, h_long = hit_frac(sv["max_ray_0p5x_cage"]["max_ray"]), hit_frac(sv["max_ray_2x_cage"]["max_ray"])
    check("C10", "falsifier: ray shorter than the cage misses the sunk HP", h_short <= sv["max_ray_0p5x_cage"]["hit_fraction_max"] and abs(h_long - 1.0) < 1e-9,
          f"hit {h_short:.3f} vs {h_long:.3f}")


def c11():
    exp = J("C11_proportion/expected.json")
    sec = J("C11_proportion/sections.json")
    C = sec["clearance_m"]
    ok = True
    for (z, a, b), row in zip(sec["levels_z_a_b"], exp["sections"]):
        th = np.linspace(0, 2 * np.pi, 721)
        pts = np.stack([(a + C) * np.cos(th), (b + C) * np.sin(th)], 1)
        segs = np.stack([pts[:-1], pts[1:]], 1)
        W = R.first_hit(segs, np.zeros(2), np.array([1.0, 0])) + R.first_hit(segs, np.zeros(2), np.array([-1.0, 0]))
        D = R.first_hit(segs, np.zeros(2), np.array([0, 1.0])) + R.first_hit(segs, np.zeros(2), np.array([0, -1.0]))
        ok &= abs(W - row["W"]) < 1e-6 and abs(D - row["D"]) < 1e-6
    check("C11", "section extents of body + C", ok)
    A = np.zeros((300, 300), bool); A[100:200, 50:250] = True
    B = np.zeros((300, 300), bool); B[100:200, 100:200] = True
    iou_true = float((A & B).sum() / (A | B).sum())
    def crop_stretch(m, size=128):
        ys, xs = np.nonzero(m)
        c = m[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
        yi = (np.arange(size) * c.shape[0] / size).astype(int)
        xi = (np.arange(size) * c.shape[1] / size).astype(int)
        return c[np.ix_(yi, xi)]
    iou_bad = float((crop_stretch(A) & crop_stretch(B)).sum() / (crop_stretch(A) | crop_stretch(B)).sum())
    e = exp["silhouette_aspect"]
    check("C11", "aspect-preserved IoU 0.5; falsifier crop-and-stretch reads 1.0", abs(iou_true - e["iou_aspect_preserved"]) < 1e-9 and abs(iou_bad - e["iou_crop_and_stretch_to_square"]) < 1e-9,
          f"{iou_true:.3f} vs {iou_bad:.3f}")


def c12():
    exp = J("C12_gasket/expected.json")
    V, F, *_ = M.read_obj(ROOT / "C12_gasket/piece_capped.obj")
    cap = [f for f in F if len(f) == 3 and np.allclose(V[list(f)][:, 2], 1.60)]
    edges = {}
    for f in F:
        for a, b in zip(f, f[1:] + f[:1]):
            k = (min(a, b), max(a, b)); edges[k] = edges.get(k, 0) + 1
    bnd = sum(1 for n in edges.values() if n == 1)
    check("C12", "fixture: one capped site, one open rim", len(cap) == 32 and bnd == 32, f"cap faces {len(cap)}, boundary edges {bnd}")


def c13():
    V, F, *_ = M.read_obj(ROOT / "C13_retopo/sphere_dense.obj")
    dev = np.abs(np.linalg.norm(V, axis=1) - 0.5).max()
    check("C13", "fixture: dense sphere vertices on the surface", dev < 1e-8, f"{dev:.1e}")


def c14():
    exp = J("C14_controls/expected.json")
    V, F, *_ = M.read_obj(ROOT / "C14_controls/rivet.obj")
    c, r = np.array(exp["body"]["sphere_centre"]), exp["body"]["radius"]
    d = np.array(exp["push_direction"], float)
    edges = {tuple(sorted((a, b))) for f in F for a, b in zip(f, f[1:] + f[:1])}
    def counts(P):
        ins = np.linalg.norm(P - c, axis=1) < r
        return sum(1 for a, b in edges if ins[a] != ins[b]), int(ins.sum())
    cx_u, in_u = counts(V + 0.01 * d)
    ext = float((V @ d).max() - (V @ d).min())
    dist = float(np.linalg.norm(V - c, axis=1).min() - r)              # distance from the nearest vertex to the skin
    push = dist + min(0.01, ext / 2)
    cx_c, _ = counts(V + push * d)
    check("C14", "uncapped control buries the rivet: surface crossings 0", cx_u == exp["uncapped_1cm"]["surface_crossing_edges"] and in_u == 8, f"{cx_u} crossings, {in_u} inside")
    check("C14", "capped control straddles the skin", cx_c >= exp["capped_half_extent"]["surface_crossing_edges_min"], f"push {push * 1000:.2f} mm, {cx_c} crossings")


def c15():
    from copy import deepcopy
    case = J("C15_ac65_defaults/case.json")
    errors = R.ac65_default_errors(case)
    check("C15", "all authorized defaults, full tables and untested status", not errors, "; ".join(errors))
    mutations = {}
    missing = deepcopy(case); del missing["settings"]["facing_margin"]
    mutations["missing_default"] = missing
    crossed = deepcopy(case); crossed["tables"]["boots"]["r"] = deepcopy(crossed["tables"]["boots"]["l"])
    mutations["wrong_side"] = crossed
    wrong = deepcopy(case); wrong["tables"]["gauntlets"]["l"]["dofs"][0]["expect"]["along"] = "forward"
    mutations["wrong_sign"] = wrong
    promoted = deepcopy(case); promoted["physical_status"] = "tested"
    mutations["physical_status_promoted"] = promoted
    check("C15", "complete named falsifiers", set(case["falsifiers"]) == set(mutations))
    for name, bad in mutations.items():
        check("C15", "falsifier: " + name, bool(R.ac65_default_errors(bad)))
    probes = case["sign_probes"]
    check("C15", "every sided table has a synthetic sign probe", {(p["kind"],p["side"]) for p in probes} == {(k,s) for k in ("waist","boots","gauntlets") for s in ("l","r")} and len(probes) == 6)
    for probe in probes:
        good = R.ac65_sign_probe(probe)
        reverse = deepcopy(probe); reverse["axis"] = [-x for x in reverse["axis"]]
        check("C15", f"{probe['kind']}/{probe['side']} +20 sign; reversed axis refuses", good > 0 and R.ac65_sign_probe(reverse) < 0)


def main():
    for f in (c01, c02, c03, c04, c05, c06, c07, c08, c09, c10, c11, c12, c13, c14, c15):
        try:
            f()
        except Exception as exc:                       # a crash is a failed check, named
            check(f.__name__.upper(), "crashed", False, repr(exc))
    bad = [r for r in RESULTS if not r[2]]
    print(f"checks[{len(RESULTS)}]{{case,check,ok,detail}}:")
    for c, n, ok, d in RESULTS:
        print(f"  {c},{n},{'ok' if ok else 'FAIL'},{d}")
    print(f"summary: {len(RESULTS) - len(bad)} ok, {len(bad)} failed")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
