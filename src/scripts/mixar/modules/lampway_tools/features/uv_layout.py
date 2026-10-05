# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_layout: orient islands, align them to the world, stack mirrored pairs, fix flipped islands, sort (resources/uv_layout.md). A NEW object ``<name>_lay``; the source keeps its UVs.

orient         each island to its minimal axis-aligned box (mathutils box_fit_2d, folded to +-45 degrees), rotated about its box centre
align_world    the island is rotated so the chosen world axis maps to UV +V: per triangle the UV->3D Jacobian J gives the UV direction d = J^+ a of the axis a, area- and projection-weighted
stack_mirrored islands whose geometry mirrors across ``mirror_axis`` (symmetric Chamfer distance <= match_tolerance, NOT a face-count rule) share one UV: the twin takes its partner's UVs vertex by vertex
fix_flipped    islands whose signed UV area disagrees with the majority are mirrored in U about their centre
sort           a shelf layout, tallest first, with padding
Texturing comes last: a textured object is refused. Written from the descriptions of the TexTools/UniV/Mio3 operations, not copied."""

import json
import math
from pathlib import Path

import bmesh
import numpy as np

from . import common as C
from . import uv_islands as UI
from .uv_rectify import _bbox, _faces_by_island
from .uv_texel import _textured

OPS = ("orient", "align_world", "stack_mirrored", "fix_flipped", "sort")
AXES = {"x": 0, "y": 1, "z": 2}


def _loops(faces, uvl):
    return [l for fc in faces for l in fc.loops]


def _rotate(faces, uvl, ang):
    lo, hi = _bbox(faces, uvl)
    c = (lo + hi) / 2
    ca, sa = math.cos(ang), math.sin(ang)
    seen = set()
    for l in _loops(faces, uvl):
        x, y = l[uvl].uv[0] - c[0], l[uvl].uv[1] - c[1]
        l[uvl].uv = (c[0] + ca * x - sa * y, c[1] + sa * x + ca * y)


def _fold(a):
    return ((a + math.pi / 4) % (math.pi / 2)) - math.pi / 4


def orient(faces, uvl):
    from mathutils.geometry import box_fit_2d
    pts = list({tuple(round(c, 7) for c in l[uvl].uv) for l in _loops(faces, uvl)})
    a = _fold(box_fit_2d(pts))
    _rotate(faces, uvl, a)
    return abs(a) > 1e-6


def _axis_dir(faces, uvl, vco, axis):
    """(summed UV direction of the world axis, total weight) over the island's triangles."""
    a = np.zeros(3)
    a[axis] = 1.0
    total, wsum = np.zeros(2), 0.0
    for fc in faces:
        ls = list(fc.loops)
        for k in range(1, len(ls) - 1):
            tri = (ls[0], ls[k], ls[k + 1])
            P = np.array([vco[l.vert.index] for l in tri])
            Q = np.array([l[uvl].uv[:] for l in tri])
            E = np.stack([P[1] - P[0], P[2] - P[0]], axis=1)
            U = np.stack([Q[1] - Q[0], Q[2] - Q[0]], axis=1)
            if abs(np.linalg.det(U)) < 1e-14:
                continue
            J = E @ np.linalg.inv(U)
            d = np.linalg.pinv(J) @ a
            n = np.linalg.norm(d)
            area = 0.5 * np.linalg.norm(np.cross(E[:, 0], E[:, 1]))
            proj = np.linalg.norm(J @ d) if n > 0 else 0.0
            if n > 1e-12:
                w = area * proj
                total += w * d / n
                wsum += w
    return total, wsum


def align_world(faces, uvl, vco, axis):
    if axis is None:
        best = max(range(3), key=lambda i: _axis_dir(faces, uvl, vco, i)[1])
    else:
        best = axis
    d, w = _axis_dir(faces, uvl, vco, best)
    if np.linalg.norm(d) < 1e-12:
        return False
    _rotate(faces, uvl, math.pi / 2 - math.atan2(d[1], d[0]))
    return True


def _signed_area(faces, uvl):
    s = 0.0
    for fc in faces:
        p = np.array([l[uvl].uv[:] for l in fc.loops])
        s += 0.5 * float(np.dot(p[:, 0], np.roll(p[:, 1], -1)) - np.dot(p[:, 1], np.roll(p[:, 0], -1)))
    return s


def fix_flipped(groups, uvl):
    sg = {i: _signed_area(f, uvl) for i, f in groups.items()}
    total = sum(sg.values())
    majority = 1.0 if total >= 0 else -1.0
    fixed = 0
    for i, f in groups.items():
        if sg[i] * majority < 0:
            lo, hi = _bbox(f, uvl)
            cx = (lo[0] + hi[0]) / 2
            for l in _loops(f, uvl):
                l[uvl].uv = (2 * cx - l[uvl].uv[0], l[uvl].uv[1])
            fixed += 1
    return fixed


def _verts(faces, vco):
    ids = sorted({v.index for fc in faces for v in fc.verts})
    return ids, np.array([vco[i] for i in ids])


def _chamfer(A, B):
    d = np.linalg.norm(A[:, None, :] - B[None, :, :], axis=2)
    return float(max(d.min(axis=1).mean(), d.min(axis=0).mean())), d


def stack_mirrored(groups, uvl, vco, axis, tol):
    data = {}
    for i, f in groups.items():
        ids, P = _verts(f, vco)
        data[i] = (ids, P)
    order = sorted(groups)
    cands = []
    for ai, a in enumerate(order):
        for b in order[ai + 1:]:
            if len(groups[a]) != len(groups[b]) or len(data[a][0]) != len(data[b][0]) or len(data[a][0]) > 2000:
                continue
            M = data[a][1].copy()
            M[:, axis] *= -1.0
            ch, _d = _chamfer(M, data[b][1])
            if ch <= tol:
                cands.append((ch, a, b))
    used, pairs = set(), []
    for ch, a, b in sorted(cands):
        if a in used or b in used:
            continue
        used.update((a, b))
        ids_a, Pa = data[a]
        ids_b, Pb = data[b]
        M = Pa.copy()
        M[:, axis] *= -1.0
        d = np.linalg.norm(Pb[:, None, :] - M[None, :, :], axis=2)
        nearest = {ids_b[k]: ids_a[int(d[k].argmin())] for k in range(len(ids_b))}
        uv_a = {}
        for l in _loops(groups[a], uvl):
            uv_a[l.vert.index] = tuple(l[uvl].uv)
        for l in _loops(groups[b], uvl):
            l[uvl].uv = uv_a[nearest[l.vert.index]]
        mirrored = _signed_area(groups[a], uvl) * _signed_area(groups[b], uvl) < 0
        pairs.append({"a": a, "b": b, "chamfer_m": round(ch, 6), "flip_applied": False, "winding_mirrored": bool(mirrored)})
    return pairs


def sort_islands(groups, uvl, padding):
    boxes = {i: _bbox(f, uvl) for i, f in groups.items()}
    order = sorted(groups, key=lambda i: -(boxes[i][1][1] - boxes[i][0][1]))
    x = y = row_h = 0.0
    overflow = False
    for i in order:
        lo, hi = boxes[i]
        w, h = hi - lo
        if x + w > 1.0 and x > 0:
            x, y, row_h = 0.0, y + row_h + padding, 0.0
        for l in _loops(groups[i], uvl):
            l[uvl].uv = (l[uvl].uv[0] - lo[0] + x, l[uvl].uv[1] - lo[1] + y)
        x += w + padding
        row_h = max(row_h, h)
        if y + row_h > 1.0:
            overflow = True
    return overflow


def _tris(groups, uvl, ids):
    out = []
    for i in ids:
        for fc in groups[i]:
            ls = list(fc.loops)
            for k in range(1, len(ls) - 1):
                out.append([ls[0][uvl].uv[:], ls[k][uvl].uv[:], ls[k + 1][uvl].uv[:]])
    return np.array(out) if out else np.zeros((0, 3, 2))


def _overlap(TU, res=512):
    if not len(TU):
        return 0.0, 0.0
    cnt = UI._raster(TU, res)
    cov = float((cnt > 0).mean())
    return float((cnt > 1).sum() / max((cnt > 0).sum(), 1)), cov


def run(object, ops=None, world_axis="z", per_face=False, mirror_axis="x", match_tolerance=0.003, padding=0.01, repack=False, name="", discard_texture=False, root=""):
    ob = C.need_object(object)
    ops = list(ops or ["orient"])
    bad = [o for o in ops if o not in OPS]
    if bad:
        raise C.FeatureError(f"unknown op {bad[0]!r}: the ops are " + " | ".join(OPS))
    if world_axis not in ("auto", "x", "y", "z"):
        raise C.FeatureError("world_axis is auto | x | y | z")
    if mirror_axis not in AXES:
        raise C.FeatureError("mirror_axis is x | y | z")
    if per_face:
        raise C.FeatureError("per_face is not built: islands are the unit (a per-face rotation would tear them apart)")
    if not 0.0005 <= float(match_tolerance) <= 0.05:
        raise C.FeatureError("match_tolerance must be between 0.0005 and 0.05 metres")
    if not 0.0 <= float(padding) <= 0.1:
        raise C.FeatureError("padding must be between 0 and 0.1")
    if not ob.data.uv_layers:
        raise C.FeatureError(f"no UV layer on {ob.name}: run lampway_uv_unwrap first")
    if _textured(ob) and not discard_texture:
        raise C.FeatureError(f"{ob.name} is textured; a UV change discards the texture. Run this on the pre-texture copy, or pass discard_texture=true")
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    mw = ob.matrix_world
    vco = {v.index: np.array(mw @ v.co) for v in bm.verts}
    groups = _faces_by_island(bm, uvl)
    axis = AXES[mirror_axis]
    if "stack_mirrored" in ops:
        coords = np.array(list(vco.values()))
        ext = float(coords[:, axis].max() - coords[:, axis].min())
        off = float((coords[:, axis].max() + coords[:, axis].min()) / 2)
        if abs(off) > max(1e-3, 0.02 * ext):
            bm.free()
            raise C.FeatureError(f"stack_mirrored needs the mesh centred on the mirror plane: {ob.name} bounds centre is {off:.4f} m off the {mirror_axis}=0 plane; apply the transform or pass mirror_axis")
    out = {"oriented": 0, "aligned": 0, "flipped_fixed": 0, "stacked": []}
    note = ""
    pre_pairs = None
    for op in ops:
        if op == "orient":
            out["oriented"] += sum(1 for f in groups.values() if orient(f, uvl) or True)
        elif op == "align_world":
            out["aligned"] += sum(1 for f in groups.values() if align_world(f, uvl, vco, None if world_axis == "auto" else AXES[world_axis]))
        elif op == "fix_flipped":
            out["flipped_fixed"] += fix_flipped(groups, uvl)
        elif op == "stack_mirrored":
            out["stacked"] = stack_mirrored(groups, uvl, vco, axis, float(match_tolerance))
            note = ("stacking overlaps UVs: lampway_bake_maps will refuse this object unless stacked_ok=true" if out["stacked"] else "no mirrored pairs found within the tolerance")
        elif op == "sort":
            if sort_islands(groups, uvl, float(padding)):
                note = (note + "; " if note else "") + "sort: the islands do not fit the 0..1 square at their size"
    if repack:
        from .uv_texel import _pack
        _pack(bm, uvl, UI.island_ids(bm, uvl), float(padding))
    second = {p["b"] for p in out["stacked"]}
    keep = [i for i in groups if i not in second]
    ov_acc, cov = _overlap(_tris(groups, uvl, keep))
    ov_all, _c = _overlap(_tris(groups, uvl, list(groups)))
    sg = [_signed_area(f, uvl) for f in groups.values()]
    maj = 1.0 if sum(sg) >= 0 else -1.0
    flipped = sum(1 for s in sg if s * maj < 0) / max(len(sg), 1)
    new = C.duplicate(ob, "_lay")
    if name:
        new.name = name
        new.data.name = name
    bm.to_mesh(new.data)
    bm.free()
    new.data.update()
    res = {"object": new.name, "source": ob.name, **out, "report": {"overlap_fraction": round(ov_acc, 4), "stacked_overlap_fraction": round(max(ov_all - ov_acc, 0.0), 4), "flipped": round(flipped, 4), "coverage": round(cov, 4)},
           "note": note}
    if root:
        Path(root).mkdir(parents=True, exist_ok=True)
        (Path(root) / "uv_layout.json").write_text(json.dumps(res, indent=1))
    return res
