# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The one definition of what a UV layout measures: utilization, overlap, islands, stretch spread, off-density fraction, mirrored faces, seam length, composite score.

Ported from the owner's shelf (tools/texlib/uv_score.py, SPIKE 2026-10-04) so the Smart UV attempts of the pipeline and Lampway's own unwraps are judged alike:
  utilization  fraction of the 0..1 square covered, rasterised at ``res`` (the number Tripo's panel shows, measured independently)
  overlap      fraction of covered texels hit by 2+ triangles
  islands      UV-connected components (corners welded by vertex index + UV position)
  stretch      per-face sqrt(UV area / 3D area) normalised by the median; p90/p10 of its area-weighted distribution; ``off_density_2x`` = fraction of 3D area off by more than 2x
  flipped      fraction of faces whose UV winding is mirrored relative to the majority
  seam_m       3D length of UV seams (edges whose two faces disagree in UV) in mesh units (world space)
  score        utilization * (1 - overlap) * (1 - off_density_2x) - 0.5 * flipped  (higher is better; the shelf's untuned weights)
Pure numpy over bmesh; works on a scene object (a throw-away copy of its data) and never changes it."""

import bmesh
import numpy as np

GATES = {"max_overlap": 0.005, "max_flipped": 0.02, "max_off_density_2x": 0.05}      # [UNVERIFIED] defaults: the captain has not seen them on real pieces


class UVError(ValueError):
    pass


def _bm(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    return bm


def island_ids(bm, uvl):
    """Per face of ``bm`` (index order): a stable island id, corners welded by (vertex index, UV rounded to 6 places)."""
    parent = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    key = lambda l: (l.vert.index, round(l[uvl].uv[0], 6), round(l[uvl].uv[1], 6))      # noqa: E731
    for fc in bm.faces:
        ks = [key(l) for l in fc.loops]
        for k in ks[1:]:
            parent[find(k)] = find(ks[0])
    roots = [find(key(fc.loops[0])) for fc in bm.faces]
    index = {r: i for i, r in enumerate(dict.fromkeys(roots))}
    return np.array([index[r] for r in roots], dtype=np.int64)


def _seam_length(bm, uvl) -> float:
    seam = 0.0
    for e in bm.edges:
        if len(e.link_faces) != 2:
            continue
        f0, f1 = e.link_faces
        u0 = {l.vert.index: tuple(round(c, 6) for c in l[uvl].uv) for l in f0.loops}
        u1 = {l.vert.index: tuple(round(c, 6) for c in l[uvl].uv) for l in f1.loops}
        if any(u0.get(v.index) != u1.get(v.index) for v in e.verts):
            seam += e.calc_length()
    return seam


def _raster(TU, res):
    cnt = np.zeros((res, res), np.uint16)
    P = TU * res
    for t in P:
        x0, y0 = np.floor(t.min(0)).astype(int).clip(0, res - 1)
        x1, y1 = np.ceil(t.max(0)).astype(int).clip(0, res - 1)
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (t[1, 1] - t[2, 1]) * (t[0, 0] - t[2, 0]) + (t[2, 0] - t[1, 0]) * (t[0, 1] - t[2, 1])
        if abs(d) < 1e-12:
            continue
        l0 = ((t[1, 1] - t[2, 1]) * (gx - t[2, 0]) + (t[2, 0] - t[1, 0]) * (gy - t[2, 1])) / d
        l1 = ((t[2, 1] - t[0, 1]) * (gx - t[2, 0]) + (t[0, 0] - t[2, 0]) * (gy - t[2, 1])) / d
        m = (l0 >= 0) & (l1 >= 0) & (1 - l0 - l1 >= 0)
        cnt[y0:y1 + 1, x0:x1 + 1] += m.astype(np.uint16)
    return cnt


def measure_object(ob, res: int = 1024) -> dict:
    """The score row of one mesh object (first/active UV layer); ``{"error": ...}`` when it has none."""
    if ob.type != "MESH" or not ob.data.uv_layers:
        return {"name": ob.name, "error": f"no UV layer on {ob.name}: unwrap it first (lampway_uv_unwrap)"}
    bm = _bm(ob)
    uvl = bm.loops.layers.uv.active
    if uvl is None:
        bm.free()
        return {"name": ob.name, "error": f"no UV layer on {ob.name}: unwrap it first (lampway_uv_unwrap)"}
    faces = len(bm.faces)
    isl = int(island_ids(bm, uvl).max() + 1) if faces else 0
    seam = _seam_length(bm, uvl)
    bmesh.ops.triangulate(bm, faces=bm.faces[:])
    bm.faces.ensure_lookup_table()
    T3 = np.array([[l.vert.co[:] for l in fc.loops] for fc in bm.faces])
    TU = np.array([[l[uvl].uv[:] for l in fc.loops] for fc in bm.faces])
    bm.free()
    a3 = np.linalg.norm(np.cross(T3[:, 1] - T3[:, 0], T3[:, 2] - T3[:, 0]), axis=1) / 2
    cu = (TU[:, 1, 0] - TU[:, 0, 0]) * (TU[:, 2, 1] - TU[:, 0, 1]) - (TU[:, 2, 0] - TU[:, 0, 0]) * (TU[:, 1, 1] - TU[:, 0, 1])
    au = np.abs(cu) / 2
    sgn = np.sign(cu)
    maj = 1 if (sgn > 0).sum() >= (sgn < 0).sum() else -1
    flipped = float((sgn == -maj).mean())
    ok = (a3 > 1e-12) & (au > 1e-14)
    s = np.sqrt(au[ok] / a3[ok])
    s = s / np.median(s)
    w = a3[ok]
    order = np.argsort(s)
    cw = np.cumsum(w[order]) / w.sum()
    p10, p90 = s[order][np.searchsorted(cw, 0.1)], s[order][np.searchsorted(cw, 0.9)]
    offd = float(w[(s > 2) | (s < 0.5)].sum() / w.sum())
    cnt = _raster(TU, res)
    cov = float((cnt > 0).mean())
    ovl = float((cnt > 1).sum() / max((cnt > 0).sum(), 1))
    score = cov * (1 - ovl) * (1 - offd) - 0.5 * flipped
    return {"name": ob.name, "faces": faces, "utilization": round(cov, 4), "overlap": round(ovl, 4), "islands": isl, "stretch_p90_p10": round(float(p90 / p10), 3),
            "off_density_2x": round(offd, 4), "flipped": round(flipped, 4), "seam_m": round(seam, 2), "score": round(score, 4)}


def gate_row(row: dict, gates: dict = None) -> dict:
    g = dict(GATES, **(gates or {}))
    failed = []
    if row["overlap"] > g["max_overlap"]:
        failed.append(f"overlap {row['overlap']} > {g['max_overlap']}")
    if row["flipped"] > g["max_flipped"]:
        failed.append(f"flipped {row['flipped']} > {g['max_flipped']}")
    if row["off_density_2x"] > g["max_off_density_2x"]:
        failed.append(f"off_density_2x {row['off_density_2x']} > {g['max_off_density_2x']}")
    return {"pass": not failed, "failed": failed}
