# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The one definition of what a UV layout measures: utilization, overlap, islands, stretch spread, off-density fraction, mirrored faces, seam length, composite score.

Ported from the owner's shelf (tools/texlib/uv_score.py, SPIKE 2026-10-04) so the Smart UV attempts of the pipeline and Lampway's own unwraps are judged alike:
  utilization  fraction of the 0..1 square covered, rasterised at ``res`` (the number Tripo's panel shows, measured independently) with canon 13's
               half-open edge rule (canon_geom.coverage): a texel centre on an edge two triangles share is counted once
  overlap      fraction of covered texels hit by 2+ triangles
  islands      UV-connected components (corners welded by vertex index + UV position)
  stretch      per-face sqrt(UV area / 3D area) normalised by the median; p90/p10 of its area-weighted distribution; ``off_density_2x`` = fraction of 3D area off by more than 2x
  flipped      fraction of faces whose UV winding is mirrored relative to the majority
  seam_m       3D length of UV seams (edges whose two faces disagree in UV) in mesh units (world space)
  score        utilization * (1 - overlap) * (1 - off_density_2x) - 0.5 * flipped  (higher is better; the shelf's untuned weights)
Pure numpy over bmesh; works on a scene object (a throw-away copy of its data) and never changes it."""

import bmesh
import numpy as np

from ..canon_geom import coverage, uv_island_ids

GATES = {"max_overlap": 0.005, "max_flipped": 0.02, "max_off_density_2x": 0.05}      # [UNVERIFIED] defaults: the user has not seen them on real pieces


class UVError(ValueError):
    pass


def _bm(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.transform(ob.matrix_world)
    return bm


def island_ids(bm, uvl, budget=None):
    """Per face of ``bm`` (index order): a stable island id - canon 13's one definition (canon_geom.uv_island_ids): corners
    joined by (vertex index, UV rounded to 6 places)."""
    F, FUV, UV = [], [], []
    for fc in bm.faces:
        if budget is not None: budget.check()
        F.append([l.vert.index for l in fc.loops])
        FUV.append(list(range(len(UV), len(UV) + len(fc.loops))))
        UV.extend(l[uvl].uv[:] for l in fc.loops)
    return uv_island_ids(F, FUV, np.array(UV).reshape(-1, 2), budget=budget)


def _seam_length(bm, uvl, budget=None) -> float:
    seam = 0.0
    for e in bm.edges:
        if budget is not None: budget.check()
        if len(e.link_faces) != 2:
            continue
        f0, f1 = e.link_faces
        u0 = {l.vert.index: tuple(round(c, 6) for c in l[uvl].uv) for l in f0.loops}
        u1 = {l.vert.index: tuple(round(c, 6) for c in l[uvl].uv) for l in f1.loops}
        if any(u0.get(v.index) != u1.get(v.index) for v in e.verts):
            seam += e.calc_length()
    return seam


def _raster(TU, res):
    """Texel coverage counts under canon 13's half-open (top-left) rule: canon_geom.coverage, the one raster."""
    return coverage(TU, res)


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
    rim = {v for e in bm.edges if len(e.link_faces) == 1 for v in e.verts}
    split = len(rim) - len({tuple(round(c, 6) for c in v.co) for v in rim})          # rim vertices that coincide: the mesh was split there
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
    flat = TU.reshape(-1, 2)
    lo, hi = flat.min(axis=0), flat.max(axis=0)
    from .uv_check import _tiles
    tiles = sorted({tile for tri in TU for tile in _tiles(tri.min(axis=0), tri.max(axis=0))})
    warnings = []                                   # audit F10: a zero must say why
    inside = float(au[(TU.mean(axis=1) >= 0).all(axis=1) & (TU.mean(axis=1) < 1).all(axis=1)].sum() / max(au.sum(), 1e-30))
    if faces and inside < 0.999:
        warnings.append(f"{round(100 * (1 - inside))} % of the UV area lies outside the 0..1 tile (UVs span u {lo[0]:.3f}..{hi[0]:.3f}, v {lo[1]:.3f}..{hi[1]:.3f}) "
                        "and is not scored: utilization measures the 0..1 tile only (lampway_uv_check action=space_usage reads every tile)")
    if seam == 0 and split:
        warnings.append(f"seam_m is 0 but the mesh is split ({split} coincident vertices on open edges): an importer (glTF) splits vertices at the UV seams, so no "
                        "edge is shared across one; weld it first (lampway_normalize_mesh welds a generated mesh) to measure its seams")
    return {"name": ob.name, "faces": faces, "utilization": round(cov, 4), "overlap": round(ovl, 4), "islands": isl, "stretch_p90_p10": round(float(p90 / p10), 3),
            "off_density_2x": round(offd, 4), "flipped": round(flipped, 4), "seam_m": round(seam, 2), "score": round(score, 4),
            "uv_bounds": [round(float(x), 4) for x in (*lo, *hi)], "tiles": tiles, "warnings": warnings}


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
