# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 05 B.4-B.5: the source seam ledger and surface crossings.

* ``seam_ledger``: vertex pairs of DIFFERENT parts with exactly equal coordinates in the SOURCE shell (Titan
  tools/seam_ledger.py, ``coverage.origin = source-exact-coordinate-groups``). Membership comes from the source, never from
  distances in an already deformed mesh (a proximity seam set cannot see a seam that opened).
* ``seam_gaps``: every ledger pair's distance in a pose; how many open over ``threshold`` (2 mm) and the maximum.
* ``segment_crossings``: which segments cross a triangle (Moller-Trumbore, 0 < t < 1) - the surface-crossing instrument
  that sees a face-interior crossing with both ends outside (a vertex-inside count reads 0 there)."""

import numpy as np

from .axes import segment_box_overlap

SEAM_OPEN_M = 0.002


def seam_ledger(V, part):
    """[[i, j], ...] (i < j): pairs of vertices of different parts at exactly the same source coordinates. ``part`` labels
    every vertex (an int or string per vertex); an unlabelled vertex (None or -1) is refused."""
    V = np.asarray(V, float)
    part = list(part)
    if len(part) != len(V) or any(p is None or (isinstance(p, (int, np.integer)) and p < 0) for p in part):
        raise ValueError("every source vertex needs its part label (one per vertex) to build the seam ledger")
    groups = {}
    for i, p in enumerate(map(tuple, V)):
        groups.setdefault(p, []).append(i)
    out = []
    for ids in groups.values():
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                i, j = ids[a], ids[b]
                if part[i] != part[j]:
                    out.append([i, j])
    return sorted(out)


def seam_gaps(P, pairs, threshold=SEAM_OPEN_M):
    """{pairs, open, max, threshold}: the ledger pairs measured in a pose (units of P)."""
    pairs = np.asarray(pairs, int).reshape(-1, 2)
    if not len(pairs):
        return {"pairs": 0, "open": None, "max": None, "threshold": threshold}
    P = np.asarray(P, float)
    g = np.linalg.norm(P[pairs[:, 0]] - P[pairs[:, 1]], axis=1)
    return {"pairs": int(len(pairs)), "open": int((g > threshold).sum()), "max": float(g.max()), "threshold": threshold}


def segment_crossings(A, B, V, T, eps=1e-12):
    """(k,) bool: whether segment A[k]-B[k] crosses any triangle of (V, T) strictly between its ends."""
    A, B = np.asarray(A, float).reshape(-1, 3), np.asarray(B, float).reshape(-1, 3)
    V, T = np.asarray(V, float), np.asarray(T, int)
    P0, P1, P2 = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    lo, hi = np.minimum(np.minimum(P0, P1), P2), np.maximum(np.maximum(P0, P1), P2)
    blo, bhi = lo.min(0), hi.max(0)
    e1, e2 = P1 - P0, P2 - P0
    out = np.zeros(len(A), bool)
    for k, (a, b) in enumerate(zip(A, B)):
        if not segment_box_overlap(a, b, blo, bhi):
            continue
        smin, smax = np.minimum(a, b), np.maximum(a, b)
        cand = np.flatnonzero(np.all((hi >= smin) & (lo <= smax), axis=1))
        if not len(cand):
            continue
        d = b - a
        h = np.cross(d, e2[cand])
        det = np.einsum("ij,ij->i", e1[cand], h)
        ok = np.abs(det) > eps
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = a - P0[cand]
        u = inv * np.einsum("ij,ij->i", s, h)
        q = np.cross(s, e1[cand])
        v = inv * (q @ d)
        t = inv * np.einsum("ij,ij->i", e2[cand], q)
        out[k] = bool((ok & (u >= 0) & (v >= 0) & (u + v <= 1) & (t > 0) & (t < 1)).any())
    return out
