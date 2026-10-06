# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 11: joints from orthographic views (ported from Titan tools/views_joints.py, its maths unchanged).

A camera is {res, ortho (the square view's side, metres), center, right, up, look}; pixels run right and DOWN from the
top-left corner. Each observation fixes a point's offsets along its camera's ``right`` and ``up``; the weighted least
squares point of all of them is exact for orthographic cameras. One view (or views all looking one way) leaves depth
unfixed and is refused (INV-11.1). The robust solve drops the view that misses most while the miss exceeds ``max_px``."""

import math

import numpy as np


def project(cam, p):
    """(x right, y down) pixel of the world point ``p``."""
    k = cam["res"] / cam["ortho"]
    d = np.asarray(p, float) - np.asarray(cam["center"], float)
    return cam["res"] / 2 + float(d @ np.asarray(cam["right"], float)) * k, cam["res"] / 2 - float(d @ np.asarray(cam["up"], float)) * k


def triangulate(obs):
    """(3,): the point the observations [(cam, px, py, weight)] agree on; ValueError when a direction stays unfixed."""
    M = np.zeros((3, 3))
    v = np.zeros(3)
    for cam, px, py, w in obs:
        if w <= 0:
            continue
        s = cam["ortho"] / cam["res"]
        r, u, c = (np.asarray(cam[k], float) for k in ("right", "up", "center"))
        a = r @ c + (px - cam["res"] / 2) * s
        b = u @ c + (cam["res"] / 2 - py) * s
        for axis, target in ((r, a), (u, b)):
            M += w * np.outer(axis, axis)
            v += w * axis * target
    if np.linalg.matrix_rank(M, tol=1e-9 * max(1.0, np.abs(M).max())) < 3:
        raise ValueError("the views leave the point unfixed along one direction: add a view that looks across it")
    return np.linalg.solve(M, v)


def triangulate_robust(obs, max_px):
    """(point, views used): ``triangulate``, then drop the worst-reprojecting view while it misses by more than ``max_px``
    and the rest still fix the point."""
    act = [o for o in obs if o[3] > 0]
    q = triangulate(act)
    while len(act) > 2:
        miss = [math.hypot(*np.subtract(project(o[0], q), o[1:3])) for o in act]
        k = int(np.argmax(miss))
        if miss[k] <= max_px:
            break
        rest = act[:k] + act[k + 1:]
        try:
            q2 = triangulate(rest)
        except ValueError:
            break
        act, q = rest, q2
    return q, len(act)


def calibrate(true, triangulated):
    """{joint: offset}: true - triangulated, for the joints of a body with KNOWN joints seen in the same cameras."""
    return {n: np.asarray(true[n], float) - np.asarray(p, float) for n, p in triangulated.items() if n in true}


def apply_offsets(triangulated, offsets):
    """{joint: point + its calibrated offset}; joints without an offset are left out."""
    return {n: np.asarray(p, float) + offsets[n] for n, p in triangulated.items() if n in offsets}
