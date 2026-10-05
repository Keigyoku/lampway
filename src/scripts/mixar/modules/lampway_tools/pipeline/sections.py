# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cross-section geometry shared by the fit tools: the outer extents of a section cut perpendicular to an axis. Copied from the ported scripts/proportion/piece_ratios.py
(shelf tools/proportion/piece_ratios.py) so the fit tools measure the way the proportion scorer does; tests/lampway_tools/test_wave2_fit_place.py pins the two copies together."""

import numpy as np

Z, X = np.array([0.0, 0, 1]), np.array([1.0, 0, 0])


def section(V, T, origin, axis, side, t):
    """Outer extents of the cross-section at distance t along axis: (W along side, D along front = axis x side, the section's point cloud)."""
    front = np.cross(axis, side)
    P = V - origin
    w = P @ axis
    e = P @ side
    f = P @ front
    s = w[T] > t
    m = s.any(1) & ~s.all(1)
    pts = []
    for tri in T[m]:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ia, ib = tri[a], tri[b]
            if (w[ia] > t) != (w[ib] > t):
                u = (t - w[ia]) / (w[ib] - w[ia])
                pts.append((e[ia] + u * (e[ib] - e[ia]), f[ia] + u * (f[ib] - f[ia])))
    if len(pts) < 6:
        return np.nan, np.nan, None
    p = np.array(pts)
    lo, hi = np.percentile(p, 1, 0), np.percentile(p, 99, 0)
    return hi[0] - lo[0], hi[1] - lo[1], p


def centre(p):
    """The centre of a section's point cloud in (side, front) coordinates (the 1 % / 99 % extents' midpoint)."""
    lo, hi = np.percentile(p, 1, 0), np.percentile(p, 99, 0)
    return (lo + hi) / 2


def profile(V, T, origin, axis, side, ts):
    out = [section(V, T, origin, axis, side, t) for t in ts]
    return np.array([o[0] for o in out]), np.array([o[1] for o in out]), [o[2] for o in out]
