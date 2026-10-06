# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Deterministic synthetic geometry for the canon goldens. numpy only, no Blender, no randomness except seeded.

Every mesh is written as OBJ text with fixed formatting so the bytes are reproducible: same inputs, same file.
Frame of every golden unless the case says otherwise: metres, Blender frame (Z up, body faces -Y, wearer's left +X)."""

import json
import math
from pathlib import Path

import numpy as np

FMT = "%.9f"


def rot(axis, deg):
    """3x3 rotation about a unit axis by deg (right-handed)."""
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    t = math.radians(deg)
    K = np.array([[0, -a[2], a[1]], [a[2], 0, -a[0]], [-a[1], a[0], 0]])
    return np.eye(3) + math.sin(t) * K + (1 - math.cos(t)) * (K @ K)


def affine(R=None, t=(0, 0, 0), s=1.0):
    M = np.eye(4)
    M[:3, :3] = s * (np.eye(3) if R is None else np.asarray(R, float))
    M[:3, 3] = t
    return M


def about(R, pivot):
    """4x4 rotation R about the point pivot."""
    p = np.asarray(pivot, float)
    return affine(t=p) @ affine(R) @ affine(t=-p)


def tube(radius, z0, z1, rings, segs, cx=0.0, cy=0.0):
    """Open cylinder along Z. Returns V (rings*segs,3), F quads (index lists)."""
    V, F = [], []
    for i in range(rings):
        z = z0 + (z1 - z0) * i / (rings - 1)
        for j in range(segs):
            th = 2 * math.pi * j / segs
            V.append((cx + radius * math.cos(th), cy + radius * math.sin(th), z))
    for i in range(rings - 1):
        for j in range(segs):
            a, b = i * segs + j, i * segs + (j + 1) % segs
            F.append((a, b, b + segs, a + segs))
    return np.array(V), F


def uv_sphere(radius, segs, stacks, centre=(0, 0, 0)):
    """Closed UV sphere (poles shared). Triangles."""
    c = np.asarray(centre, float)
    V = [c + (0, 0, radius)]
    for i in range(1, stacks):
        ph = math.pi * i / stacks
        for j in range(segs):
            th = 2 * math.pi * j / segs
            V.append(c + radius * np.array((math.sin(ph) * math.cos(th), math.sin(ph) * math.sin(th), math.cos(ph))))
    V.append(c + (0, 0, -radius))
    V = np.array(V)
    F = []
    for j in range(segs):
        F.append((0, 1 + j, 1 + (j + 1) % segs))
    for i in range(stacks - 2):
        for j in range(segs):
            a = 1 + i * segs + j
            b = 1 + i * segs + (j + 1) % segs
            F.append((a, a + segs, b + segs))
            F.append((a, b + segs, b))
    s = len(V) - 1
    base = 1 + (stacks - 2) * segs
    for j in range(segs):
        F.append((base + j, s, base + (j + 1) % segs))
    return V, F


def write_obj(path, V, F, UV=None, FUV=None, groups=None, header=""):
    """OBJ with optional per-corner UV indices (FUV parallel to F) and face groups ({name: [face indices]})."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    out = ["# SPDX-FileCopyrightText: 2026 Lampway contributors", "# SPDX-License-Identifier: GPL-3.0-or-later"]
    if header:
        out += ["# " + line for line in header.splitlines()]
    out += ["v " + " ".join(FMT % x for x in v) for v in np.asarray(V, float)]
    if UV is not None:
        out += ["vt " + " ".join(FMT % x for x in uv) for uv in np.asarray(UV, float)]
    owner = {}
    if groups:
        for name, idx in groups.items():
            for k in idx:
                owner[int(k)] = name
    cur = None
    for k, f in enumerate(F):
        g = owner.get(k)
        if g is not None and g != cur:
            out.append("g " + g)
            cur = g
        if UV is not None and FUV is not None:
            out.append("f " + " ".join(f"{a + 1}/{b + 1}" for a, b in zip(f, FUV[k])))
        else:
            out.append("f " + " ".join(str(a + 1) for a in f))
    path.write_text("\n".join(out) + "\n")


def read_obj(path):
    V, UV, F, FUV, groups, cur = [], [], [], [], {}, None
    for line in Path(path).read_text().splitlines():
        p = line.split()
        if not p or p[0].startswith("#"):
            continue
        if p[0] == "v":
            V.append([float(x) for x in p[1:4]])
        elif p[0] == "vt":
            UV.append([float(x) for x in p[1:3]])
        elif p[0] == "g":
            cur = p[1]
        elif p[0] == "f":
            idx = [q.split("/") for q in p[1:]]
            F.append([int(q[0]) - 1 for q in idx])
            FUV.append([int(q[1]) - 1 for q in idx] if len(idx[0]) > 1 and idx[0][1] else None)
            if cur is not None:
                groups.setdefault(cur, []).append(len(F) - 1)
    return np.array(V), F, (np.array(UV) if UV else None), FUV, groups


def triangulate(F):
    T = []
    for f in F:
        for k in range(1, len(f) - 1):
            T.append((f[0], f[k], f[k + 1]))
    return np.array(T, int)


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1, sort_keys=True) + "\n")


def r9(x):
    """Round floats for expected files (nine decimals, the Titan canon's rule)."""
    if isinstance(x, dict):
        return {k: r9(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [r9(v) for v in x]
    if isinstance(x, (np.floating, float)):
        return round(float(x), 9)
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, np.ndarray):
        return r9(x.tolist())
    return x
