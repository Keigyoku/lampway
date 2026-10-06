# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_validate, the pure half: the measurements and the judgement, with no scene.

* rigid_fit: canon 02's similarity fit (canon_geom): the best PROPER rotation + translation (and, only when asked, ONE uniform scale: Umeyama) taking one point set onto another, with the residual (rms, max, p95). A metal part is judged with the scale FIXED, so a pose
  that "breathes" a part by 1 % fails; the source similarity (rest fidelity) is the only place a scale is fitted, and it is reported.
* edge_strain: the relative change of edge lengths (a fraction; a zero-length rest edge is refused).
* judge: a verdict per part under the limits of its role plus the body's: PASS | FAIL | UNVERIFIED (no limits for the role, or a metric not measured); never a bare PASS: the limits' status (proposed | adopted) rides along.
* summarize: the counts, and ``ok`` only when nothing is UNVERIFIED/UNPROVEN; a failed crossing control makes the whole run UNPROVEN.
* bind_mismatch: the piece's own reference pose against the native bind, bone by bone (tolerances 0.01 cm, 0.01 deg, scale 1e-4: the contract's).
The default limits are canon 05's (Titan's armour-limits, adopted by the captain 2026-10-06); cloth, leather and embroidery have none at all."""

import numpy as np

from ..canon_geom import similarity_fit

# Canon 05's limits: Titan recipes/armour-limits.json (titan.armour-limits/1), ADOPTED by the captain on 2026-10-06 ("go with
# Titans fit limit"): metal rigid residual < 0.5 mm, metal edge strain p95 < 1 % (a fraction), no surface crossing of the body.
# Leather, cloth and embroidery have NO limits (they judge UNVERIFIED), and no seam limit exists: those are still owed.
DEFAULT_LIMITS = {"schema": "titan.armour-limits/1", "status": "adopted", "body": {"crossings": 0}, "metal": {"rigid_max_mm": 0.5, "strain_p95": 0.01},
                  "source": "specs/canon/05-fit-validation.md H.1; adopted 2026-10-06",
                  "needs_decision": ["leather, cloth and embroidery limits (canon 05 H.2): those roles judge UNVERIFIED until declared",
                                     "a seam acceptance limit (canon 05 H.3): the ledger counts pairs open over 2 mm, nothing is judged on it"]}
PROPOSED = DEFAULT_LIMITS                                  # the old name, kept for importers (the limits are now adopted)
BIND_TOL = {"pos_cm": 0.01, "rot_deg": 0.01, "scale": 1e-4}


def rigid_fit(P, Q, with_scale=True):
    """Canon 02's similarity fit (canon_geom.similarity_fit) in this module's receipt keys: refuses fewer than 3 pairs, collinear
    points and non-finite input; ``p95_m`` beside ``rms_m`` and ``max_m`` so one bad vertex is never averaged away."""
    f = similarity_fit(P, Q, with_scale=with_scale)
    return {"R": f["R"], "t": f["t"], "scale": f["s"], "rms_m": f["rms"], "max_m": f["max"], "p95_m": f["p95"]}


def edge_strain(P0, P1, edges):
    """{p95, max}: |l_posed / l_rest - 1| per edge as a FRACTION (canon 05 B.3); a zero-length rest edge is refused."""
    e = np.asarray(edges, int).reshape(-1, 2)
    if not len(e):
        return {"p95": 0.0, "max": 0.0}
    l0 = np.linalg.norm(P0[e[:, 0]] - P0[e[:, 1]], axis=1)
    if (l0 <= 1e-12).any():
        k = int(np.flatnonzero(l0 <= 1e-12)[0])
        raise ValueError(f"edge {int(e[k, 0])}-{int(e[k, 1])} has no rest length (weld or remove the degenerate edge first)")
    f = np.abs(np.linalg.norm(P1[e[:, 0]] - P1[e[:, 1]], axis=1) / l0 - 1.0)
    return {"p95": float(np.percentile(f, 95)), "max": float(f.max())}


def judge(role, metrics, limits=None):
    """{verdict PASS|FAIL|UNVERIFIED, limits_status, over, missing}: ``metrics`` against the role's limits plus the body's
    (Titan armour_validate.judge): a role without limits, or a limit whose metric was not measured, is UNVERIFIED - never PASS."""
    lim = limits or DEFAULT_LIMITS
    status = lim.get("status", "proposed")
    if role not in lim:
        return {"verdict": "UNVERIFIED", "limits_status": status, "over": [], "missing": [f"limits for {role}"]}
    want = dict(lim.get("body", {}))
    want.update(lim[role])
    over = sorted(k for k, v in want.items() if metrics.get(k) is not None and metrics[k] > v)
    missing = sorted(k for k in want if metrics.get(k) is None)
    return {"verdict": "FAIL" if over else ("UNVERIFIED" if missing else "PASS"), "limits_status": status, "over": over, "missing": missing}


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
