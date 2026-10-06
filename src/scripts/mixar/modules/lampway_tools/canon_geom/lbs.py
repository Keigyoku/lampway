# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 04: linear blend skinning and its EXACT inverse.

Forward LBS (Magnenat-Thalmann et al. 1988; the engine's model): v_posed = (sum_b w_b M_b) v_rest, M_b = Posed_b Rest_b^-1.
The return to rest is the inverse OF THE BLEND, A(v)^-1 v, never the blend of inverses sum_b w_b M_b^-1 v (golden C02:
10.8 mm off on 46 blended vertices). A vertex whose blended transform is singular cannot be returned and is refused by id."""

import numpy as np

SINGULAR_DET_MIN = 1e-9


class SingularBlendError(ValueError):
    """The blended transform of some vertices is singular; ``vertices`` = [{vertex, det}] (up to ``limit``)."""

    def __init__(self, vertices, total):
        self.vertices = vertices
        self.total = total
        ids = ", ".join(str(v["vertex"]) for v in vertices[:10])
        super().__init__(f"the blended transform of {total} vertices is singular (e.g. {ids}): they cannot be returned to rest; "
                         "reduce the fit pose at their bones or narrow the blend band")


def _arrays(points, weights, mats):
    P = np.asarray(points, float).reshape(-1, 3)
    W = np.asarray(weights, float).reshape(len(P), -1)
    M = np.asarray(mats, float)
    if M.ndim != 3 or M.shape[1:] != (4, 4) or M.shape[0] != W.shape[1]:
        raise ValueError(f"lbs needs one 4x4 per weight column: weights {W.shape}, matrices {M.shape}")
    return P, W, M


def blended(weights, mats):
    """(n, 4, 4): the per-vertex blended transform sum_b w_b M_b."""
    W, M = np.asarray(weights, float), np.asarray(mats, float)
    return np.einsum("nb,bij->nij", W, M)


def lbs(points, weights, mats):
    """(n, 3): forward linear blend skinning of every point."""
    P, W, M = _arrays(points, weights, mats)
    A = blended(W, M)
    return np.einsum("nij,nj->ni", A[:, :3, :3], P) + A[:, :3, 3]


def lbs_inverse(points, weights, mats, min_abs_det=SINGULAR_DET_MIN, limit=50):
    """(n, 3): the rest points whose forward LBS are ``points`` - the inverse of each vertex's blended transform.
    Raises SingularBlendError naming the vertices whose |det A[:3,:3]| < ``min_abs_det``."""
    P, W, M = _arrays(points, weights, mats)
    A = blended(W, M)
    det = np.linalg.det(A[:, :3, :3])
    bad = np.flatnonzero(np.abs(det) < min_abs_det)
    if len(bad):
        raise SingularBlendError([{"vertex": int(i), "det": float(det[i])} for i in bad[:limit]], int(len(bad)))
    return np.linalg.solve(A[:, :3, :3], (P - A[:, :3, 3])[..., None])[..., 0]


def round_trip_error(rest, points, weights, mats):
    """(n,): ||lbs(rest) - points|| per vertex, the canon's INV-04.1 receipt."""
    return np.linalg.norm(lbs(rest, weights, mats) - np.asarray(points, float), axis=1)
