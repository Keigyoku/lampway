# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 15: inside / outside and signed distance.

* ``winding_numbers``: the generalized winding number (Jacobson, Kavan, Sorkine-Hornung 2013) - 1 inside a closed outward
  mesh, 0 outside, fractional near the holes of an open one. Exact, O(points x triangles).
* ``closest_points``: the nearest point on the triangles (Ericson 2004, 5.1.5), with the triangle and the feature it lies on.
* ``signed_distance``: the unsigned distance signed by the winding number (inside when w > 0.5) - never by one face's normal.
* ``pseudonormal_signs``: the fast sign for a CLOSED mesh from a nearest point found elsewhere (a BVH): the angle-weighted
  pseudonormal of the nearest feature (Baerentzen and Aanaes 2005) - the face normal only when the nearest point is inside a
  face, the edge or vertex pseudonormal otherwise. INV-15.1: a sign is never taken from one face normal at an edge or vertex.
* ``boundary_edges``: how many edges have one face - a body with any is open (INV-15.2)."""

import math

import numpy as np

CHUNK = 2_000_000          # point x triangle evaluations per block (memory bound)


def _blocks(n_points, n_tris):
    step = max(1, CHUNK // max(1, n_tris))
    for i in range(0, n_points, step):
        yield slice(i, min(n_points, i + step))


def winding_numbers(V, T, P):
    """(n,): the generalized winding number of every point of P with respect to the triangles T over V."""
    V, T, P = np.asarray(V, float), np.asarray(T, int), np.asarray(P, float).reshape(-1, 3)
    out = np.empty(len(P))
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    for s in _blocks(len(P), len(T)):
        p = P[s, None, :]
        a, b, c = A[None] - p, B[None] - p, C[None] - p
        la, lb, lc = (np.linalg.norm(x, axis=2) for x in (a, b, c))
        num = np.einsum("ptk,ptk->pt", a, np.cross(b, c))
        den = la * lb * lc + np.einsum("ptk,ptk->pt", a, b) * lc + np.einsum("ptk,ptk->pt", b, c) * la + np.einsum("ptk,ptk->pt", c, a) * lb
        out[s] = 2 * np.arctan2(num, den).sum(1) / (4 * math.pi)
    return out


def _closest_one(A, B, C, p):
    """Closest points from p to every triangle (vectorised over triangles): (distance, point, feature) where feature is
    0 face interior, 1..3 vertex A/B/C, 4..6 edge AB/AC/BC."""
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - B
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - C
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    vc, vb, va = d1 * d4 - d3 * d2, d5 * d2 - d1 * d6, d3 * d6 - d5 * d4
    out = np.empty_like(A)
    feat = np.full(len(A), -1)

    def put(mask, val, f):
        sel = mask & (feat < 0)
        out[sel] = val[sel]
        feat[sel] = f
    put((d1 <= 0) & (d2 <= 0), A, 1)
    put((d3 >= 0) & (d4 <= d3), B, 2)
    with np.errstate(divide="ignore", invalid="ignore"):
        v = np.where(np.abs(d1 - d3) > 1e-30, d1 / (d1 - d3), 0)
        put((vc <= 0) & (d1 >= 0) & (d3 <= 0), A + v[:, None] * ab, 4)
        put((d6 >= 0) & (d5 <= d6), C, 3)
        w = np.where(np.abs(d2 - d6) > 1e-30, d2 / (d2 - d6), 0)
        put((vb <= 0) & (d2 >= 0) & (d6 <= 0), A + w[:, None] * ac, 5)
        w2 = np.where(np.abs((d4 - d3) + (d5 - d6)) > 1e-30, (d4 - d3) / ((d4 - d3) + (d5 - d6)), 0)
        put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), B + w2[:, None] * (C - B), 6)
        den = np.where(np.abs(va + vb + vc) > 1e-30, 1 / (va + vb + vc), 0)
    put(np.ones(len(A), bool), A + ab * (vb * den)[:, None] + ac * (vc * den)[:, None], 0)
    return np.linalg.norm(out - p, axis=1), out, feat


def closest_points(V, T, P):
    """(distance (n,), closest point (n, 3), triangle (n,)) of every point of P on the mesh."""
    V, T, P = np.asarray(V, float), np.asarray(T, int), np.asarray(P, float).reshape(-1, 3)
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    dist, loc, tri = np.empty(len(P)), np.empty((len(P), 3)), np.empty(len(P), int)
    for i, p in enumerate(P):
        d, q, _f = _closest_one(A, B, C, p)
        k = int(np.argmin(d))
        dist[i], loc[i], tri[i] = d[k], q[k], k
    return dist, loc, tri


def signed_distance(V, T, P):
    """(signed distance (n,), winding number (n,)): negative inside (w > 0.5), positive outside."""
    d, _loc, _tri = closest_points(V, T, P)
    w = winding_numbers(V, T, P)
    return np.where(w > 0.5, -d, d), w


def boundary_edges(T):
    """The number of edges used by exactly one triangle (0 for a closed mesh)."""
    T = np.asarray(T, int)
    e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
    _u, counts = np.unique(e, axis=0, return_counts=True)
    return int((counts == 1).sum())


class PseudoNormals:
    """Angle-weighted pseudonormals of a closed triangle mesh: per face, per edge (sum of the two face normals) and per
    vertex (face normals weighted by the incident angle). ``signs(P, loc, tri)`` signs points whose nearest point ``loc``
    on triangle ``tri`` was found elsewhere: +1 outside, -1 inside."""

    def __init__(self, V, T):
        self.V, self.T = np.asarray(V, float), np.asarray(T, int)
        A, B, C = (self.V[self.T[:, k]] for k in range(3))
        n = np.cross(B - A, C - A)
        self.face = n / np.maximum(np.linalg.norm(n, axis=1), 1e-300)[:, None]
        self.vert = np.zeros_like(self.V)
        for k, (P0, P1, P2) in enumerate(((A, B, C), (B, C, A), (C, A, B))):
            u, v = P1 - P0, P2 - P0
            cosang = np.einsum("ij,ij->i", u, v) / np.maximum(np.linalg.norm(u, axis=1) * np.linalg.norm(v, axis=1), 1e-300)
            np.add.at(self.vert, self.T[:, k], self.face * np.arccos(np.clip(cosang, -1, 1))[:, None])
        self.edge = {}
        for f, (a, b, c) in enumerate(self.T):
            for i, j in ((a, b), (b, c), (c, a)):
                key = (min(i, j), max(i, j))
                self.edge[key] = self.edge.get(key, 0) + self.face[f]

    def signs(self, P, loc, tri, rel_eps=1e-7):
        P, loc, tri = np.asarray(P, float).reshape(-1, 3), np.asarray(loc, float).reshape(-1, 3), np.asarray(tri, int)
        out = np.empty(len(P))
        for n, (p, q, f) in enumerate(zip(P, loc, tri)):
            a, b, c = self.T[f]
            A, B, C = self.V[a], self.V[b], self.V[c]
            nrm = np.cross(B - A, C - A)
            area2 = float(nrm @ nrm)
            if area2 <= 0:
                normal = self.face[f]
            else:
                l1 = float(np.cross(C - B, q - B) @ nrm) / area2          # barycentric weight of A
                l2 = float(np.cross(A - C, q - C) @ nrm) / area2          # of B
                l3 = 1.0 - l1 - l2                                      # of C
                small = [x <= rel_eps for x in (l1, l2, l3)]
                if sum(small) >= 2:                                     # at a vertex: the one whose weight is ~1
                    normal = self.vert[(a, b, c)[int(np.argmax((l1, l2, l3)))]]
                elif sum(small) == 1:                                   # on an edge: the two other corners
                    k = small.index(True)
                    i, j = [x for m, x in enumerate((a, b, c)) if m != k]
                    normal = self.edge[(min(i, j), max(i, j))]
                else:
                    normal = self.face[f]
            out[n] = 1.0 if float((p - q) @ normal) >= 0 else -1.0
        return out
