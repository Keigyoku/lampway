# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Reference implementations of the canon's core measurements, numpy only. They exist to prove each golden's expected
values are reachable by the canonical method (selftest.py) and to give an implementer a readable statement of the maths.
They are not the production tools: those live in Lampway and must reproduce these numbers within each case's tolerance."""

import math

import numpy as np


# ------------------------------------------------------------------ canon 02: the similarity / rigid fit
def similarity_fit(P, Q, with_scale=True):
    """Least-squares Q ~ s R P + t, R a PROPER rotation (det +1). Umeyama 1991 (Kabsch/Horn equivalent); scale only when asked."""
    P, Q = np.asarray(P, float), np.asarray(Q, float)
    mp, mq = P.mean(0), Q.mean(0)
    A, B = P - mp, Q - mq
    U, S, Vt = np.linalg.svd(B.T @ A)
    d = np.sign(np.linalg.det(U @ Vt)) or 1.0
    D = np.diag([1.0, 1.0, d])
    R = U @ D @ Vt
    s = float((S * np.diag(D)).sum() / (A ** 2).sum()) if with_scale else 1.0
    t = mq - s * R @ mp
    err = np.linalg.norm(s * P @ R.T + t - Q, axis=1)
    return {"R": R, "s": s, "t": t, "rms": float(np.sqrt((err ** 2).mean())), "max": float(err.max())}


def rotation_angle_axis(R):
    ang = math.degrees(math.acos(max(-1.0, min(1.0, (np.trace(R) - 1) / 2))))
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    return ang, ax / np.linalg.norm(ax)


# ------------------------------------------------------------------ canon 04: linear blend skinning and its exact inverse
def lbs(p, weights, mats):
    """Forward LBS of one point: (sum_b w_b M_b) p, M_b = Posed_b Bind_b^-1 (4x4)."""
    Mb = sum(w * m for w, m in zip(weights, mats))
    return (Mb @ np.r_[p, 1.0])[:3]


def lbs_inverse(p, weights, mats, min_abs_det=1e-9):
    """The rest point whose forward LBS is p: the INVERSE OF THE BLEND. Refuses a singular blend."""
    Mb = sum(w * m for w, m in zip(weights, mats))
    det = float(np.linalg.det(Mb[:3, :3]))
    if abs(det) < min_abs_det:
        raise ValueError(f"the blended transform is singular (det {det:.3g}): this vertex cannot be returned to rest; split the band or reduce the fit pose")
    return (np.linalg.inv(Mb) @ np.r_[p, 1.0])[:3]


def blend_of_inverses(p, weights, mats):
    """The WRONG return (kept as the falsifier): sum_b w_b M_b^-1 p."""
    Mb = sum(w * np.linalg.inv(m) for w, m in zip(weights, mats))
    return (Mb @ np.r_[p, 1.0])[:3]


# ------------------------------------------------------------------ canon 15: inside / outside and signed distance
def winding_number(V, T, p):
    """Generalized winding number (Jacobson, Kavan, Sorkine-Hornung 2013): sum of signed solid angles / 4 pi.
    1 inside a closed outward mesh, 0 outside, fractional near holes of an open mesh."""
    a = V[T[:, 0]] - p
    b = V[T[:, 1]] - p
    c = V[T[:, 2]] - p
    la, lb, lc = (np.linalg.norm(x, axis=1) for x in (a, b, c))
    num = np.einsum("ij,ij->i", a, np.cross(b, c))
    den = la * lb * lc + np.einsum("ij,ij->i", a, b) * lc + np.einsum("ij,ij->i", b, c) * la + np.einsum("ij,ij->i", c, a) * lb
    return float(2 * np.arctan2(num, den).sum() / (4 * math.pi))


def closest_on_triangles(V, T, p):
    """Distance and closest point from p to every triangle (Ericson, Real-Time Collision Detection 5.1.5), vectorized."""
    A, B, C = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    ab, ac, ap = B - A, C - A, p - A
    d1, d2 = np.einsum("ij,ij->i", ab, ap), np.einsum("ij,ij->i", ac, ap)
    bp = p - B
    d3, d4 = np.einsum("ij,ij->i", ab, bp), np.einsum("ij,ij->i", ac, bp)
    cp = p - C
    d5, d6 = np.einsum("ij,ij->i", ab, cp), np.einsum("ij,ij->i", ac, cp)
    vc = d1 * d4 - d3 * d2
    vb = d5 * d2 - d1 * d6
    va = d3 * d6 - d5 * d4
    out = np.empty_like(A)
    m = np.zeros(len(A), bool)
    def put(mask, val):
        nonlocal m
        sel = mask & ~m
        out[sel] = val[sel]
        m |= sel
    put((d1 <= 0) & (d2 <= 0), A)
    put((d3 >= 0) & (d4 <= d3), B)
    v = np.where(np.abs(d1 - d3) > 1e-30, d1 / (d1 - d3), 0)
    put((vc <= 0) & (d1 >= 0) & (d3 <= 0), A + v[:, None] * ab)
    put((d6 >= 0) & (d5 <= d6), C)
    w = np.where(np.abs(d2 - d6) > 1e-30, d2 / (d2 - d6), 0)
    put((vb <= 0) & (d2 >= 0) & (d6 <= 0), A + w[:, None] * ac)
    w2 = np.where(np.abs((d4 - d3) + (d5 - d6)) > 1e-30, (d4 - d3) / ((d4 - d3) + (d5 - d6)), 0)
    put((va <= 0) & ((d4 - d3) >= 0) & ((d5 - d6) >= 0), B + w2[:, None] * (C - B))
    den = np.where(np.abs(va + vb + vc) > 1e-30, 1 / (va + vb + vc), 0)
    vv, ww = vb * den, vc * den
    put(np.ones(len(A), bool), A + ab * vv[:, None] + ac * ww[:, None])
    return np.linalg.norm(out - p, axis=1), out


def signed_distance(V, T, p):
    """Unsigned distance to the mesh, signed by the winding number (inside if w > 0.5). Never by one face's normal."""
    d, _ = closest_on_triangles(V, T, p)
    w = winding_number(V, T, p)
    return (-1.0 if w > 0.5 else 1.0) * float(d.min()), w


# ------------------------------------------------------------------ canon 09: placement by enclosure (slice rays)
def slice_segments(V, T, z):
    Z = V[T, 2]
    s = Z > z
    out = []
    for t in T[s.any(1) & ~s.all(1)]:
        pts = []
        for i, j in ((0, 1), (1, 2), (2, 0)):
            a, b = V[t[i]], V[t[j]]
            if (a[2] > z) != (b[2] > z):
                u = (z - a[2]) / (b[2] - a[2])
                pts.append(a[:2] + u * (b[:2] - a[:2]))
        if len(pts) == 2:
            out.append(pts)
    return np.array(out)


def first_hit(segs, c, d):
    p, e = segs[:, 0] - c, segs[:, 1] - segs[:, 0]
    den = d[0] * (-e[:, 1]) + e[:, 0] * d[1]
    ok = np.abs(den) > 1e-15
    t = np.where(ok, (p[:, 0] * (-e[:, 1]) + e[:, 0] * p[:, 1]) / np.where(ok, den, 1), -1)
    u = np.where(ok, (d[0] * p[:, 1] - d[1] * p[:, 0]) / np.where(ok, den, 1), -1)
    m = ok & (t > 1e-12) & (u >= -1e-9) & (u <= 1 + 1e-9)      # a ray through a vertex must not slip between segments
    return float(t[m].min()) if m.any() else math.nan


def inner_wall_centre(segs, start, iters=4):
    """The centre of the wall a ray from `start` meets first in +x, -x, +y, -y, iterated from the new centre."""
    c = np.asarray(start, float)
    for _ in range(iters):
        xp, xm = first_hit(segs, c, np.array([1.0, 0])), first_hit(segs, c, np.array([-1.0, 0]))
        yp, ym = first_hit(segs, c, np.array([0, 1.0])), first_hit(segs, c, np.array([0, -1.0]))
        c = c + np.array([(xp - xm) / 2, (yp - ym) / 2])
    return c


# ------------------------------------------------------------------ canon 11: orthographic triangulation
def project(cam, p):
    k = cam["res"] / cam["ortho"]
    d = np.asarray(p) - np.asarray(cam["center"])
    return cam["res"] / 2 + float(d @ cam["right"]) * k, cam["res"] / 2 - float(d @ cam["up"]) * k


def triangulate(obs):
    """Weighted least squares of the point whose projections match (cam, px, py, w); exact for orthographic cameras.
    After titan/tools/views_joints.triangulate."""
    M = np.zeros((3, 3))
    v = np.zeros(3)
    for cam, px, py, w in obs:
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
    act = list(obs)
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


# ------------------------------------------------------------------ canon 13: UV measurements
def uv_metrics(V, F, UV, FUV, res=1024):
    T, TU = [], []
    for f, fu in zip(F, FUV):
        for k in range(1, len(f) - 1):
            T.append((V[f[0]], V[f[k]], V[f[k + 1]]))
            TU.append((UV[fu[0]], UV[fu[k]], UV[fu[k + 1]]))
    T, TU = np.array(T), np.array(TU)
    a3 = np.linalg.norm(np.cross(T[:, 1] - T[:, 0], T[:, 2] - T[:, 0]), axis=1) / 2
    cu = (TU[:, 1, 0] - TU[:, 0, 0]) * (TU[:, 2, 1] - TU[:, 0, 1]) - (TU[:, 2, 0] - TU[:, 0, 0]) * (TU[:, 1, 1] - TU[:, 0, 1])
    sgn = np.sign(cu)
    maj = 1 if (sgn > 0).sum() >= (sgn < 0).sum() else -1
    cnt = np.zeros((res, res), np.int32)
    gx, gy = np.meshgrid(np.arange(res) + 0.5, np.arange(res) + 0.5)
    for t in TU * res:
        if abs((t[1, 0] - t[0, 0]) * (t[2, 1] - t[0, 1]) - (t[2, 0] - t[0, 0]) * (t[1, 1] - t[0, 1])) < 1e-12:
            continue
        cnt += raster_half_open(t, gx, gy).astype(np.int32)
    cov = float((cnt > 0).mean())
    ovl = float((cnt > 1).sum() / max((cnt > 0).sum(), 1))
    return {"utilization": cov, "overlap": ovl, "flipped_tris": float((sgn == -maj).mean()), "density": np.sqrt(np.abs(cu) / 2 / a3)}


def raster_half_open(t, gx, gy):
    """Texel centres covered by triangle t (pixel units) under a half-open edge rule: a centre exactly on an edge belongs to
    exactly one of the two triangles sharing that edge (the D3D / OpenGL top-left convention), so no texel is counted twice
    inside one island. Orientation-independent (a mirrored island is turned CCW first)."""
    a, b, c = t
    if (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1]) < 0:
        b, c = c, b
    inside = np.ones(gx.shape, bool)
    for p, q in ((a, b), (b, c), (c, a)):
        dx, dy = q[0] - p[0], q[1] - p[1]
        e = dx * (gy - p[1]) - dy * (gx - p[0])
        owns_edge = (dy < 0) or (dy == 0 and dx > 0)
        inside &= (e > 0) | ((e == 0) & owns_edge)
    return inside


def components(F, key=None):
    """Connected components of faces sharing a vertex key (index by default; e.g. a rounded position for a weld)."""
    key = key or (lambda v: v)
    par = {}
    def find(x):
        while par.setdefault(x, x) != x:
            par[x] = par[par[x]]
            x = par[x]
        return x
    for f in F:
        ks = [key(v) for v in f]
        for k in ks[1:]:
            par[find(k)] = find(ks[0])
    return len({find(key(f[0])) for f in F})


# ------------------------------------------------------------------ canon 14: cage ray cast against an analytic cap
def bake_cap(u, v, a, R, zc, cage, max_ray, hp_offset=0.0):
    """Normal (tangent space of a flat LP) seen by a ray from the cage point straight down, or None on a miss."""
    x, y = u - 0.5, v - 0.5
    rho = math.hypot(x, y)
    if rho < a:
        z = math.sqrt(R * R - rho * rho) + zc + hp_offset
        n = np.array([x, y, math.sqrt(R * R - rho * rho)]) / R
    else:
        z, n = hp_offset, np.array([0.0, 0.0, 1.0])
    travel = cage - z
    if travel < 0 or travel > max_ray:
        return None
    return n


# ------------------------------------------------------------------ canon 08: the pose sweep (cylinder model)
def ray_cylinder(o, d, axis_p, axis_d, radius, s0, s1):
    """First t > 0 where o + t d meets the cylinder (axis point/direction, radius) within axial range [s0, s1]."""
    w = o - axis_p
    dp = d - (d @ axis_d) * axis_d
    wp = w - (w @ axis_d) * axis_d
    A, B, C = dp @ dp, 2 * dp @ wp, wp @ wp - radius * radius
    disc = B * B - 4 * A * C
    if A < 1e-15 or disc < 0:
        return None
    best = None
    for t in ((-B - math.sqrt(disc)) / (2 * A), (-B + math.sqrt(disc)) / (2 * A)):
        if t > 1e-9:
            s = (o + t * d - axis_p) @ axis_d
            if s0 <= s <= s1 and (best is None or t < best):
                best = t
    return best
