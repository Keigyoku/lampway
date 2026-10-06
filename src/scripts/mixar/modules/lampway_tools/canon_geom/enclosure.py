# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 09: placement by enclosure of the INNER wall.

At several heights, slice body and piece; from the body section's centre cast rays (+side, -side, +front, -front) and take
the FIRST piece hit - the inner wall; the shift that puts the inner wall's centre on the body's centre, median over the
slices. Never the all-vertex extents (golden C06: a thick front wall biases them by (t_front - t_back) / 2 = 12.5 mm), never
the centroid, never surface ICP (INV-09.3)."""

import math

import numpy as np


def slice_segments(V, T, z, axis=2):
    """(k, 2, 2): the segments where the plane ``coordinate[axis] == z`` cuts the triangles, in the two other coordinates
    (for axis 2: (x, y))."""
    V, T = np.asarray(V, float), np.asarray(T, int)
    keep = [i for i in range(3) if i != axis]
    Z = V[T, axis]
    s = Z > z
    out = []
    for t in T[s.any(1) & ~s.all(1)]:
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = V[t[i]], V[t[j]]
            if (a[axis] > z) != (b[axis] > z):
                u = (z - a[axis]) / (b[axis] - a[axis])
                pts.append(a[keep] + u * (b[keep] - a[keep]))
        if len(pts) == 2:
            out.append(pts)
    return np.array(out).reshape(-1, 2, 2)


def first_hit(segs, c, d):
    """The distance along the 2D ray c + t d (t > 0) to the first segment it meets, or NaN."""
    segs = np.asarray(segs, float)
    if not len(segs):
        return math.nan
    p, e = segs[:, 0] - c, segs[:, 1] - segs[:, 0]
    den = d[0] * (-e[:, 1]) + e[:, 0] * d[1]
    ok = np.abs(den) > 1e-15
    t = np.where(ok, (p[:, 0] * (-e[:, 1]) + e[:, 0] * p[:, 1]) / np.where(ok, den, 1), -1)
    u = np.where(ok, (d[0] * p[:, 1] - d[1] * p[:, 0]) / np.where(ok, den, 1), -1)
    m = ok & (t > 1e-12) & (u >= -1e-9) & (u <= 1 + 1e-9)          # a ray through a vertex must not slip between segments
    return float(t[m].min()) if m.any() else math.nan


_DIRS = (np.array([1.0, 0]), np.array([-1.0, 0]), np.array([0, 1.0]), np.array([0, -1.0]))


def inner_wall_centre(segs, start, iters=4, partial=False):
    """The centre of the wall that rays from ``start`` meet first in +x, -x, +y, -y, re-cast from the new centre ``iters``
    times. A ray that finds no wall raises ValueError (the section does not enclose the start) - or, with ``partial``, leaves
    that axis's coordinate where it is and returns (centre, (x resolved, y resolved)) (an opening in the piece's wall)."""
    c = np.asarray(start, float)
    ok = [True, True]
    for _ in range(iters):
        xp, xm, yp, ym = (first_hit(segs, c, d) for d in _DIRS)
        ok = [not (math.isnan(xp) or math.isnan(xm)), not (math.isnan(yp) or math.isnan(ym))]
        if not all(ok) and not partial:
            raise ValueError(f"a ray from {c.round(5).tolist()} meets no wall: the section does not enclose it")
        c = c + np.array([(xp - xm) / 2 if ok[0] else 0.0, (yp - ym) / 2 if ok[1] else 0.0])
    return (c, tuple(ok)) if partial else c


def harmonic_centre(segs, start, rays=36, iters=6, min_hits=8):
    """(centre, hits): the inner wall's centre as the fitted FIRST HARMONIC of its radii (canon 09 B.4): ``rays`` rays from the
    current centre to the first wall, r(theta) ~ r0 + a cos(theta) + b sin(theta) by least squares over the rays that hit, the
    centre moved by (a, b), re-cast ``iters`` times. Rays through an opening in the wall are simply absent from the fit, so a
    slit front does not stop the centring; fewer than ``min_hits`` hits raise ValueError."""
    c = np.asarray(start, float)
    th = 2 * math.pi * np.arange(rays) / rays
    dirs = np.stack([np.cos(th), np.sin(th)], 1)
    n = 0
    for _ in range(iters):
        r = np.array([first_hit(segs, c, d) for d in dirs])
        ok = ~np.isnan(r)
        n = int(ok.sum())
        if n < min_hits:
            raise ValueError(f"only {n} of {rays} rays from {c.round(5).tolist()} meet a wall: the section does not enclose it")
        A = np.stack([np.ones(n), np.cos(th[ok]), np.sin(th[ok])], 1)
        r0, a, b = np.linalg.lstsq(A, r[ok], rcond=None)[0]
        c = c + np.array([a, b])
    return c, n


def enclosure_shift(Vb, Tb, Vp, Tp, levels, axis=2):
    """{shift (2,), per_level [[level, dx, dy]], slices}: the translation (in the two coordinates across ``axis``) that
    centres the piece's inner wall on the body, the median over the levels whose sections close around the body centre."""
    rows = []
    for z in levels:
        bs, ps = slice_segments(Vb, Tb, z, axis), slice_segments(Vp, Tp, z, axis)
        if not len(bs) or not len(ps):
            continue
        try:
            bc = inner_wall_centre(bs, bs.reshape(-1, 2).mean(0))
            pc = inner_wall_centre(ps, bc)
        except ValueError:
            continue
        rows.append([float(z), *(bc - pc)])
    if not rows:
        raise ValueError("no level has a body section enclosed by a piece section: place the piece over the body first")
    arr = np.array(rows)
    return {"shift": np.median(arr[:, 1:], 0), "per_level": rows, "slices": len(rows)}
