# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_validate, the pure half: the measurements and the judgement, with no scene.

* rigid_fit: the best rotation + translation (and, only when asked, ONE uniform scale: Umeyama) taking one point set onto another, with the residual. A metal part is judged with the scale FIXED, so a pose
  that "breathes" a part by 1 % fails; the source similarity (rest fidelity) is the only place a scale is fitted, and it is reported.
* edge_strain: the percent change of edge lengths.
* judge: a verdict per part under the limits of its role: PASS | FAIL | UNVERIFIED (no limits declared for the role) ; never a bare PASS: the limits' status (proposed | adopted) rides along.
* summarize: the counts, and ``ok`` only when nothing is UNVERIFIED/UNPROVEN; a failed crossing control makes the whole run UNPROVEN.
* bind_mismatch: the piece's own reference pose against the native bind, bone by bone (tolerances 0.01 cm, 0.01 deg, scale 1e-4: the contract's).
The default limits are PROPOSED (the user has adopted none); cloth, leather and embroidery have none at all."""

import numpy as np

PROPOSED = {"status": "proposed", "metal": {"rigid_max_mm": 1.0, "strain_max_pct": 1.0, "seam_gap_mm": 1.0}}      # [UNVERIFIED] placeholders: the user's measured numbers replace them
BIND_TOL = {"pos_cm": 0.01, "rot_deg": 0.01, "scale": 1e-4}


def rigid_fit(P, Q, with_scale=True):
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    mp, mq = P.mean(0), Q.mean(0)
    A, B = P - mp, Q - mq
    U, S, Vt = np.linalg.svd(B.T @ A)
    d = np.sign(np.linalg.det(U @ Vt))
    D = np.diag([1, 1, d])
    R = U @ D @ Vt
    s = float((S * np.array([1, 1, d])).sum() / (A ** 2).sum()) if with_scale else 1.0
    t = mq - s * (R @ mp)
    fit = s * (P @ R.T) + t
    err = np.linalg.norm(fit - Q, axis=1)
    return {"R": R, "t": t, "scale": s, "rms_m": float(np.sqrt((err ** 2).mean())), "max_m": float(err.max())}


def edge_strain(P0, P1, edges):
    e = np.asarray(edges)
    l0 = np.linalg.norm(P0[e[:, 0]] - P0[e[:, 1]], axis=1)
    l1 = np.linalg.norm(P1[e[:, 0]] - P1[e[:, 1]], axis=1)
    keep = l0 > 1e-12
    pct = np.abs(l1[keep] / l0[keep] - 1.0) * 100.0
    return {"p95_pct": float(np.percentile(pct, 95)), "max_pct": float(pct.max())}


def judge(role, metrics, limits=None):
    lim = limits or PROPOSED
    out = {"limits_status": lim.get("status", "proposed"), "over": [], "missing": []}
    role_lim = lim.get(role)
    if not role_lim:
        out.update(verdict="UNVERIFIED", missing=[f"limits for {role}"])
        return out
    pairs = (("rigid_max_mm", "rigid_residual_mm"), ("strain_max_pct", "strain_max_pct"), ("seam_gap_mm", "seam_gap_mm_max"))
    for key, metric in pairs:
        if key in role_lim and metrics.get(metric) is not None and metrics[metric] > role_lim[key]:
            out["over"].append(key)
    if metrics.get("crossings_body"):
        out["over"].append("crossings_body")
    out["verdict"] = "FAIL" if out["over"] else "PASS"
    return out


def summarize(judges, crossing_control_ok=True):
    counts = {"PASS": 0, "FAIL": 0, "UNVERIFIED": 0, "REFUSED": 0, "UNPROVEN": 0}
    status = "proposed"
    for j in judges:
        counts[j["verdict"]] += 1
        status = j.get("limits_status", status)
    if crossing_control_ok is False:
        counts["UNPROVEN"] += 1
    ok = counts["FAIL"] == 0 and counts["UNVERIFIED"] == 0 and counts["UNPROVEN"] == 0 and counts["PASS"] > 0
    if ok:
        note = "PASS" if status == "adopted" else "PASS under proposed limits"
    else:
        note = "not ok: " + ", ".join(f"{n} {k}" for k, n in counts.items() if n and k != "PASS") if any(n for k, n in counts.items() if k != "PASS") else "nothing was measured"
    return {"ok": ok, "counts": counts, "limits_status": status, "note": note}


def _quat_angle_deg(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    d = abs(float(np.dot(a / np.linalg.norm(a), b / np.linalg.norm(b))))
    return float(np.degrees(2 * np.arccos(min(1.0, d))))


def bind_mismatch(leader, own, tol=None):
    t = dict(BIND_TOL, **(tol or {}))
    rows, over = [], []
    for bone, ref in leader.items():
        if bone not in own:
            over.append({"bone": bone, "missing": True})
            continue
        o = own[bone]
        row = {"bone": bone, "pos_cm": float(np.linalg.norm(np.array(ref["pos"]) - np.array(o["pos"]))), "rot_deg": _quat_angle_deg(ref["rot"], o["rot"]),
               "scale": float(np.abs(np.array(ref.get("scale", [1, 1, 1])) - np.array(o.get("scale", [1, 1, 1]))).max())}
        rows.append(row)
        if row["pos_cm"] > t["pos_cm"] or row["rot_deg"] > t["rot_deg"] or row["scale"] > t["scale"]:
            over.append(row)
    return {"ok": not over, "bones": len(leader), "over_tolerance": over, "tolerance": t}


def check_expect(expect, measured):
    """A pose's declared direction ("wrist_r goes UP by at least 20 degrees") against what the pose measured: {bone: {<axis>_deg: value}}."""
    got = measured.get(expect["bone"], {}).get(f"{expect['axis']}_deg")
    if got is None:
        return {"ok": False, "why": f"{expect['bone']} has no measured {expect['axis']}_deg"}
    ok = got >= float(expect["min_deg"])
    return {"ok": ok, "why": "" if ok else f"expect failed: {expect['bone']} {expect['axis']} is {got:.1f} degrees, wanted at least {expect['min_deg']} (a wrong-sign pose is refused, not measured)"}


def control_shift(points, normals, depth_m, nearest_idx):
    """The crossing control: push the piece vertices ``nearest_idx`` into the skin (against the body's outward normal there) so a crossing counter that is blind shows itself."""
    out = np.array(points, float).copy()
    for i in np.atleast_1d(nearest_idx):
        out[i] = out[i] - np.asarray(normals[i], float) * depth_m
    return out
