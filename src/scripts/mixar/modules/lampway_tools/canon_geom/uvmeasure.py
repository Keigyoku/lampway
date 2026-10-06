# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 13: the ONE definition of what a UV layout measures (INV-13.1).

* islands: faces joined by a shared corner with the same (vertex identity, UV); vertex identity is the vertex index or a
  position weld key (``identity.weld_keys``) on a smart mesh that splits vertices at seams (canon 01 D.1).
* coverage: every UV triangle rasterised at ``res`` with a HALF-OPEN (top-left) edge rule - a texel centre on an edge two
  triangles share belongs to exactly one of them, so an island's own diagonals are never counted as overlap (golden C09:
  the inclusive rule reads 0.00167 on a layout with none).
* utilization = covered / all texels; overlap = texels covered 2+ times / covered; flipped = faces whose signed UV area
  disagrees with the majority sign."""

import numpy as np


def raster_half_open(t, gx, gy):
    """bool grid: the texel centres (gx, gy) covered by triangle ``t`` (3 x 2, pixel units) under the top-left rule.
    Orientation-independent (a mirrored triangle is turned counter-clockwise first)."""
    a, b, c = np.asarray(t, float)
    if (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]) < 0:
        b, c = c, b
    inside = np.ones(np.shape(gx), bool)
    for p, q in ((a, b), (b, c), (c, a)):
        dx, dy = q[0] - p[0], q[1] - p[1]
        e = dx * (gy - p[1]) - dy * (gx - p[0])
        owns_edge = (dy < 0) or (dy == 0 and dx > 0)
        inside &= (e > 0) | ((e == 0) & owns_edge)
    return inside


def coverage(TU, res):
    """(res, res) int grid: how many UV triangles (k x 3 x 2, in 0..1) cover each texel centre."""
    cnt = np.zeros((res, res), np.int32)
    for t in np.asarray(TU, float) * res:
        if abs((t[1, 0] - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[2, 0] - t[0, 0]) * (t[1, 1] - t[0, 1])) < 1e-12:
            continue
        x0, y0 = np.floor(t.min(0)).astype(int).clip(0, res - 1)
        x1, y1 = np.ceil(t.max(0)).astype(int).clip(0, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        cnt[y0:y1 + 1, x0:x1 + 1] += raster_half_open(t, gx, gy)
    return cnt


def fan(F, FUV, V, UV):
    """(3D triangles k x 3 x 3, UV triangles k x 3 x 2, face of each triangle) by a fan from each face's first corner."""
    T3, TU, owner = [], [], []
    V, UV = np.asarray(V, float), np.asarray(UV, float)
    for n, (f, fu) in enumerate(zip(F, FUV)):
        for k in range(1, len(f) - 1):
            T3.append((V[f[0]], V[f[k]], V[f[k + 1]]))
            TU.append((UV[fu[0]], UV[fu[k]], UV[fu[k + 1]]))
            owner.append(n)
    return np.array(T3).reshape(-1, 3, 3), np.array(TU).reshape(-1, 3, 2), np.array(owner, int)


def uv_island_ids(F, FUV, UV, vertex_key=None, decimals=6):
    """(faces,) island id per face, numbered in first-seen order. ``vertex_key`` maps a vertex index to its identity
    (default: the index itself; pass ``weld_keys`` on a seam-split smart mesh); UVs compare rounded to ``decimals``."""
    UV = np.round(np.asarray(UV, float), decimals)
    vk = (lambda v: v) if vertex_key is None else (lambda v: int(vertex_key[v]))
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    firsts = []
    for f, fu in zip(F, FUV):
        ks = [(vk(v), float(UV[u][0]), float(UV[u][1])) for v, u in zip(f, fu)]
        for k in ks[1:]:
            parent[find(k)] = find(ks[0])
        firsts.append(ks[0])
    roots = [find(k) for k in firsts]
    index = {r: i for i, r in enumerate(dict.fromkeys(roots))}
    return np.array([index[r] for r in roots], dtype=np.int64)


def uv_metrics(V, F, UV, FUV, res=1024, vertex_key=None):
    """{utilization, overlap, flipped, islands, triangles}: the canon measurements of one layout."""
    T3, TU, owner = fan(F, FUV, V, UV)
    cu = (TU[:, 1, 0] - TU[:, 0, 0]) * (TU[:, 2, 1] - TU[:, 0, 1]) - (TU[:, 2, 0] - TU[:, 0, 0]) * (TU[:, 1, 1] - TU[:, 0, 1])
    sgn = np.sign(cu)
    maj = 1 if (sgn > 0).sum() >= (sgn < 0).sum() else -1
    cnt = coverage(TU, res)
    covered = int((cnt > 0).sum())
    return {"utilization": float(covered / cnt.size), "overlap": float((cnt > 1).sum() / max(covered, 1)),
            "flipped": float((sgn == -maj).mean()) if len(sgn) else 0.0,
            "islands": int(uv_island_ids(F, FUV, UV, vertex_key).max() + 1) if len(F) else 0, "triangles": int(len(TU))}
