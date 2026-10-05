# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh QA candidates for a typed decision (the captain reviews now, a decision model later).

Ported from the shelf's tools/meshqa/mesh_qa.py (SPIKE 2026-10-04), analysis half; the review renders stay in the
command-line script (scripts/meshqa/mesh_qa.py). Two kinds:

  open_loop   - connected boundary edges (after a weld by distance) of at least ``min_perimeter``; a loop that borders
                several parts is split per part when it is giant (one boundary on the Tripo chest was 2,264 edges joining
                every hem);
  loose_shell - a mesh shell of at most ``max_shell_tris`` triangles whose nearest other shell is further than
                ``float_mm`` (it floats).

Each candidate carries a typed descriptor: geometry, the bordering parts and their motion classes, which side of the
body, which standard views see it, and what a ray through it hits behind. Frame: -y front, +x the body's left (the matrix
passed to ``prepare`` brings the live object there: offset removed, then its turn about Z).

Measured 2026-10-04 on chest seed 9c052d49: 321 boundary loops; 152 are 8-edge loops (rivet bases, open by design,
hidden on the plate) - the perimeter floor drops them; 62 loops are >= 0.15 m.
"""

import math
from dataclasses import dataclass

import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


@dataclass
class Params:
    min_perimeter: float = 0.15
    max_shell_tris: int = 400
    float_mm: float = 3.0


class Prepared:
    """A welded, deletion-applied copy of a mesh in the analysis frame, with each face's part and source index."""

    def __init__(self, bm, fpart, forig):
        self.bm = bm
        self.fpart = fpart
        self.forig = forig


def prepare(me, matrix, owner, delete_polys=()) -> Prepared:
    """``me`` (a Mesh), brought into the analysis frame by ``matrix``; ``owner`` is one part index per polygon;
    ``delete_polys`` (source polygon indices) are removed before the weld, so a ruled deletion's new boundary is seen."""
    owner = np.asarray(owner)
    if len(owner) != len(me.polygons):
        raise ValueError(f"owner has {len(owner)} labels for {len(me.polygons)} polygons")
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.transform(matrix)
    bm.normal_update()                                   # a turn changes the face normals the descriptors read
    bm.faces.ensure_lookup_table()
    lay = bm.faces.layers.int.new("orig")
    for f in bm.faces:
        f[lay] = f.index
    if len(delete_polys):
        dl = set(int(i) for i in delete_polys)
        bmesh.ops.delete(bm, geom=[f for f in bm.faces if f[lay] in dl], context="FACES_ONLY")
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    bm.faces.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    fpart = np.array([owner[f[lay]] for f in bm.faces])
    forig = np.array([f[lay] for f in bm.faces])
    return Prepared(bm, fpart, forig)


_VIEWS = {"front": Vector((0, -1, 0)), "back": Vector((0, 1, 0)), "left": Vector((1, 0, 0)),
          "right": Vector((-1, 0, 0)), "top": Vector((0, 0, 1)), "bottom": Vector((0, 0, -1))}
_DIRS = (Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 1, 0)), Vector((0, -1, 0)), Vector((0, 0, 1)), Vector((0, 0, -1)))


def analyse(prep: Prepared, rec: dict, params: Params = None) -> list:
    """Candidates for a prepared mesh. ``rec`` is the recipe (``{"parts": {name: {"class": ...}}}``)."""
    params = params or Params()
    bm, fpart, forig = prep.bm, prep.fpart, prep.forig
    names = list(rec["parts"])

    # ---- shells (union-find over edges)
    par = list(range(len(bm.verts)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    for e in bm.edges:
        par[find(e.verts[0].index)] = find(e.verts[1].index)
    vsh = np.array([find(v.index) for v in bm.verts])
    fsh = np.array([vsh[f.verts[0].index] for f in bm.faces])
    ids, fsh = np.unique(fsh, return_inverse=True)
    tri_cnt = np.bincount(fsh, weights=[len(f.verts) - 2 for f in bm.faces])
    V = np.array([v.co[:] for v in bm.verts])
    vfsh = np.full(len(V), -1)
    for f in bm.faces:
        for v in f.verts:
            vfsh[v.index] = fsh[f.index]
    bvh = BVHTree.FromBMesh(bm)
    center = V.mean(0)
    cands = []

    def side_of(c, n):
        r = Vector((c[0] - center[0], c[1] - center[1], 0))
        d = Vector(n)
        if abs(d.z) > 0.75:
            return "top" if d.z > 0 else "bottom"
        h = d.copy()
        h.z = 0
        if h.length < 1e-6:
            h = r
        ang = math.degrees(math.atan2(h.x, -h.y))                    # 0 = front (-y), 90 = the body's left (+x)
        return "front" if abs(ang) < 45 else "back" if abs(ang) > 135 else ("left" if ang > 0 else "right")

    def seen_from(pts):
        out = {}
        for vn, d in _VIEWS.items():
            hit = 0
            for p in pts:
                o = Vector(p) + d * 2.0
                loc, nrm, idx, dist = bvh.ray_cast(o, -d, 3.0)
                if loc is not None and (loc - Vector(p)).length < 0.006:
                    hit += 1
            out[vn] = round(100 * hit / max(len(pts), 1), 1)
        return out

    def behind(c, n):
        o = Vector(c) + Vector(n) * 0.5
        loc, nrm, idx, dist = bvh.ray_cast(o, -Vector(n), 1.5)
        if loc is None:
            return {"hit": "nothing"}
        return {"hit": names[int(fpart[idx])], "backfacing": bool(nrm.dot(-Vector(n)) > 0),
                "depth_mm": round((loc - Vector(c)).length * 1000, 1)}

    # ---- open loops, split per bordering part
    bnd = [e for e in bm.edges if e.is_boundary]
    bset = {e.index for e in bnd}
    seen = set()
    k = 0
    for e0 in bnd:
        if e0.index in seen:
            continue
        stack = [e0.index]
        comp = []
        while stack and len(comp) < 200000:                           # bounded walk over connected boundary edges
            ei = stack.pop()
            if ei in seen:
                continue
            seen.add(ei)
            comp.append(ei)
            for v in bm.edges[ei].verts:
                for f in v.link_edges:
                    if f.index in bset and f.index not in seen:
                        stack.append(f.index)
        per = sum(bm.edges[i].calc_length() for i in comp)
        if per < params.min_perimeter:
            continue
        groups = {}
        for i in comp:
            groups.setdefault(int(fpart[bm.edges[i].link_faces[0].index]), []).append(i)
        if per < 2.0:
            groups = {-1: comp}                                      # a normal-sized loop stays whole
        for gp, es in groups.items():
            gper = sum(bm.edges[i].calc_length() for i in es)
            if gper < params.min_perimeter:
                continue
            pts = np.array([v.co[:] for i in es for v in bm.edges[i].verts])
            c = pts.mean(0)
            n = Vector((0, 0, 0))
            for i in es:
                n += bm.edges[i].link_faces[0].normal * bm.edges[i].calc_length()
            rad = Vector((c[0] - center[0], c[1] - center[1], 0.0))
            if n.length < 1e-9 or n.dot(rad) < 0 and abs(n.z) < 0.7:
                n = rad if n.length < 1e-9 or n.dot(rad) < 0 else n
            n.normalize()
            bp = {}
            for i in es:
                nm = names[int(fpart[bm.edges[i].link_faces[0].index])]
                bp[nm] = bp.get(nm, 0) + bm.edges[i].calc_length()
            tot = sum(bp.values())
            bp = {kk: round(100 * vv / tot, 1) for kk, vv in sorted(bp.items(), key=lambda x: -x[1])}
            samp = pts[np.linspace(0, len(pts) - 1, min(24, len(pts))).astype(int)]
            cands.append({
                "id": f"L{k:03d}", "kind": "open_loop", "edges": len(es), "perimeter_m": round(gper, 3),
                "loop_perimeter_m": round(per, 3), "centroid_m": [round(x, 3) for x in c],
                "extent_m": [round(x, 3) for x in pts.max(0) - pts.min(0)], "side": side_of(c, n),
                "facing": [round(x, 3) for x in n], "bordering_parts_pct": bp,
                "bordering_classes": sorted({rec["parts"][p]["class"] for p in bp}),
                "seen_from_pct": seen_from(samp), "behind": behind(c, n),
                "segments_m": [[[round(x, 4) for x in bm.edges[i].verts[0].co],
                                [round(x, 4) for x in bm.edges[i].verts[1].co]] for i in es]})
            k += 1

    # ---- floating shells
    taken = 0
    for s in range(len(ids)):
        if tri_cnt[s] > params.max_shell_tris:
            continue
        vs = np.flatnonzero(vfsh == s)
        if not len(vs):
            continue
        best = 1e9
        for vi in vs[:: max(1, len(vs) // 30)]:
            p = Vector(V[vi])
            for d in _DIRS:
                loc, nrm, idx, dist = bvh.ray_cast(p + d * 1e-4, d, 0.05)
                if loc is not None and fsh[idx] != s:
                    best = min(best, dist)
        if best * 1000 <= params.float_mm:
            continue
        pts = V[vs]
        c = pts.mean(0)
        fids = [f.index for f in bm.faces if fsh[f.index] == s]
        bp = {}
        for fi in fids:
            bp[names[int(fpart[fi])]] = bp.get(names[int(fpart[fi])], 0) + 1
        rad = Vector((c[0] - center[0], c[1] - center[1], 0.0))
        n = rad.normalized() if rad.length > 1e-6 else Vector((0, 0, 1))
        cands.append({
            "id": f"S{taken:03d}", "kind": "loose_shell", "tris": int(tri_cnt[s]),
            "gap_to_nearest_mm": round(best * 1000, 1) if best < 1e8 else None,
            "centroid_m": [round(x, 3) for x in c], "extent_m": [round(x, 3) for x in pts.max(0) - pts.min(0)],
            "side": side_of(c, n), "facing": [round(x, 3) for x in n],
            "parts_pct": {kk: round(100 * vv / len(fids), 1) for kk, vv in bp.items()},
            "seen_from_pct": seen_from(pts[np.linspace(0, len(pts) - 1, min(24, len(pts))).astype(int)]),
            "orig_polys": sorted({int(forig[fi]) for fi in fids})})
        taken += 1
    return cands
