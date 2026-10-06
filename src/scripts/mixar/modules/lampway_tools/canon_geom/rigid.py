# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 02: the rigid / similarity fit (the metal primitive).

Least squares Q ~ s R P + t with R a PROPER rotation (det +1): Umeyama 1991 (equivalent to Horn 1987 and Kabsch 1976).
Scale is fitted only when asked; a pose rigidity check passes ``with_scale=False`` (INV-02.2). Refuses fewer than three
pairs, points on one line (the rotation about it is unfixed) and non-finite input."""

import math

import numpy as np


def _check(P, Q):
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    if P.ndim != 2 or P.shape[1] != 3 or P.shape != Q.shape:
        raise ValueError(f"similarity_fit needs matching (n, 3) pairs, got {P.shape} and {Q.shape}")
    if len(P) < 3:
        raise ValueError(f"similarity_fit needs at least 3 point pairs, got {len(P)}")
    if not (np.isfinite(P).all() and np.isfinite(Q).all()):
        raise ValueError("similarity_fit needs finite points (a NaN or inf is in the input)")
    return P, Q


def _collinear(A, tol=1e-9):
    s = np.linalg.svd(A, compute_uv=False)
    return s[0] <= 0 or s[1] <= tol * s[0]


def similarity_fit(P, Q, with_scale=True):
    """{R, s, t, rms, max, p95, n, with_scale}: the best proper similarity (or rigid motion) taking P onto Q, with the
    per-point residual ||s R p + t - q|| summarised."""
    P, Q = _check(P, Q)
    mp, mq = P.mean(0), Q.mean(0)
    A, B = P - mp, Q - mq
    if _collinear(A) or _collinear(B):
        raise ValueError("the points lie on one line: the rotation about it is unfixed (give a third, off-line point)")
    U, S, Vt = np.linalg.svd(B.T @ A)
    d = np.sign(np.linalg.det(U @ Vt)) or 1.0
    D = np.diag([1.0, 1.0, d])
    R = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / (A ** 2).sum()) if with_scale else 1.0
    t = mq - s * R @ mp
    err = np.linalg.norm(s * P @ R.T + t - Q, axis=1)
    return {"R": R, "s": s, "t": t, "rms": float(np.sqrt((err ** 2).mean())), "max": float(err.max()),
            "p95": float(np.percentile(err, 95)), "n": int(len(P)), "with_scale": bool(with_scale), "residual": err}


def apply_similarity(fit, P):
    """s R p + t for every point."""
    return fit["s"] * np.asarray(P, float) @ fit["R"].T + fit["t"]


def rotation_angle_axis(R):
    """(degrees, unit axis) of a rotation matrix; the axis is +z for the identity."""
    R = np.asarray(R, float)
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(ax)
    if n < 1e-12:
        if ang < 1e-9:
            return 0.0, np.array([0.0, 0.0, 1.0])
        w, v = np.linalg.eigh((R + np.eye(3)) / 2)                 # a half turn: the axis is the eigenvector of eigenvalue 1
        return ang, v[:, int(np.argmax(w))]
    return ang, ax / n


def similarity_receipt(fit):
    """The canon 02 receipt fields: {scale, rotation_deg, axis, translation_m, rms_mm, max_mm, p95_mm, n, with_scale}."""
    ang, ax = rotation_angle_axis(fit["R"])
    return {"scale": round(float(fit["s"]), 9), "rotation_deg": round(float(ang), 6), "axis": [round(float(x), 9) for x in ax],
            "translation_m": [round(float(x), 9) for x in fit["t"]], "rms_mm": round(fit["rms"] * 1000, 6),
            "max_mm": round(fit["max"] * 1000, 6), "p95_mm": round(fit["p95"] * 1000, 6), "n": fit["n"], "with_scale": fit["with_scale"]}
