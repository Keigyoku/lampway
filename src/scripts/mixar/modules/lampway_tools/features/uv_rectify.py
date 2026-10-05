# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""uv_rectify: straighten, rectify and gridify UV islands of strap-like geometry (resources/uv_rectify.md). A NEW object ``<name>_rect``; the 3D mesh and the source's UVs are never changed.

gridify   an island of quads laid out as a rectangular grid: quad-ring propagation gives every vertex integer (i, j); the spacing per column and row is the mean 3D edge length there (evenness blends it
          toward uniform), the aspect blends the grid counts and the 3D lengths (geometry_ratio); the result has the island's UV area and bounding-box centre.
rectify   any island with one simple boundary loop: the boundary goes onto a rectangle from four detected corners (largest turns), the interior is the harmonic solve with that boundary pinned.
straighten a vertex chain goes onto a straight axis-aligned line at its cumulative 3D lengths; the island's boundary stays, the rest relaxes harmonically.
Written from the published descriptions of these operations (Mio3 UV, TexTools, 3dxdev), not copied from any of them. Numpy over bmesh; no bpy.ops."""

import json
import math
from pathlib import Path

import bmesh
import numpy as np

from . import common as C
from . import uv_islands as UI
from .uv_texel import _textured

MAX_FREE = 3000                         # dense harmonic solve


class NotGrid(ValueError):
    pass


def _faces_by_island(bm, uvl):
    ids = UI.island_ids(bm, uvl)
    out = {}
    for fc in bm.faces:
        out.setdefault(int(ids[fc.index]), []).append(fc)
    return out


def _uv_area(faces, uvl):
    a = 0.0
    for fc in faces:
        p = np.array([l[uvl].uv[:] for l in fc.loops])
        a += 0.5 * abs(float(np.dot(p[:, 0], np.roll(p[:, 1], -1)) - np.dot(p[:, 1], np.roll(p[:, 0], -1))))
    return a


def _bbox(faces, uvl):
    p = np.array([l[uvl].uv[:] for fc in faces for l in fc.loops])
    return p.min(axis=0), p.max(axis=0)


def _rectangularity(faces, uvl):
    lo, hi = _bbox(faces, uvl)
    box = float((hi[0] - lo[0]) * (hi[1] - lo[1]))
    return _uv_area(faces, uvl) / box if box > 1e-18 else 0.0


def _stretch(faces, uvl, vco):
    """p90/p10 of per-face sqrt(UV area / 3D area), normalised by the median."""
    s = []
    for fc in faces:
        p3 = np.array([vco[l.vert.index] for l in fc.loops])
        pu = np.array([l[uvl].uv[:] for l in fc.loops])
        a3 = 0.5 * float(np.linalg.norm(sum(np.cross(p3[k], p3[(k + 1) % len(p3)]) for k in range(len(p3)))))
        au = 0.5 * abs(float(np.dot(pu[:, 0], np.roll(pu[:, 1], -1)) - np.dot(pu[:, 1], np.roll(pu[:, 0], -1))))
        if a3 > 1e-14 and au > 1e-16:
            s.append(math.sqrt(au / a3))
    if not s:
        return 0.0
    s = np.array(s) / np.median(s)
    return float(np.percentile(s, 90) / max(np.percentile(s, 10), 1e-12))


def _metrics(faces, uvl, vco):
    return {"rectangularity": round(_rectangularity(faces, uvl), 4), "stretch_p90_p10": round(_stretch(faces, uvl, vco), 3), "uv_area": round(_uv_area(faces, uvl), 6)}


# ---------------------------------------------------------------------------------------------------------------------------------- gridify
def _adjacent(f, v):
    vs = list(f.verts)
    i = vs.index(v)
    return vs[i - 1], vs[(i + 1) % len(vs)]


def grid_coords(faces):
    """{vertex index: (i, j)} for an island of quads that forms a regular grid; NotGrid names why it is not one."""
    tri = sum(1 for f in faces if len(f.verts) == 3)
    ngon = sum(1 for f in faces if len(f.verts) > 4)
    if any(len(f.verts) != 4 for f in faces):
        raise NotGrid(f"not a quad grid: {tri} triangles" + (f", {ngon} n-gons" if ngon else "") + " (use op=rectify, or lampway_retopo first)")
    fset = {f.index for f in faces}
    f0 = faces[0]
    v0 = list(f0.verts)
    coords = {v0[0].index: (0, 0), v0[1].index: (1, 0), v0[2].index: (1, 1), v0[3].index: (0, 1)}
    seen, queue = {f0.index}, [f0]
    while queue:
        f = queue.pop()
        for e in f.edges:
            for g in e.link_faces:
                if g.index == f.index or g.index not in fset or g.index in seen:
                    continue
                a, b = e.verts
                ca, cb = coords[a.index], coords[b.index]
                fa = next(v for v in _adjacent(f, a) if v.index != b.index)
                inside = (coords[fa.index][0] - ca[0], coords[fa.index][1] - ca[1])
                off = (-inside[0], -inside[1])
                da = next(v for v in _adjacent(g, a) if v.index != b.index)
                db = next(v for v in _adjacent(g, b) if v.index != a.index)
                for v, c in ((da, (ca[0] + off[0], ca[1] + off[1])), (db, (cb[0] + off[0], cb[1] + off[1]))):
                    if coords.get(v.index, c) != c:
                        raise NotGrid(f"not a regular grid: irregular vertex {v.index} (a pole or a T-junction)")
                    coords[v.index] = c
                seen.add(g.index)
                queue.append(g)
    if len(seen) != len(faces):
        raise NotGrid("not a quad grid: the island's faces are not connected by edges")
    if len(set(coords.values())) != len(coords):
        raise NotGrid("not a regular grid: two vertices land on the same grid point (the strip closes on itself: cut a seam)")
    for f in faces:
        cs = [coords[v.index] for v in f.verts]
        if sorted((abs(c[0] - cs[0][0]) + abs(c[1] - cs[0][1])) for c in cs) != [0, 1, 1, 2]:
            raise NotGrid("not a regular grid: a face is not a unit cell")
    mi = min(c[0] for c in coords.values())
    mj = min(c[1] for c in coords.values())
    return {k: (c[0] - mi, c[1] - mj) for k, c in coords.items()}


def _place(faces, uvl, uv_of, W, H, orient_like):
    """Write ``uv_of`` (vertex index -> (x, y) in a W x H rectangle) to the island's loops with the old UV area and bbox centre; the long side follows the old long side."""
    lo, hi = _bbox(faces, uvl)
    cx, cy = (lo + hi) / 2
    w0, h0 = hi - lo
    area = _uv_area(faces, uvl)
    swap = (W >= H) != (w0 >= h0)
    if swap:
        W, H = H, W
        uv_of = {k: (v[1], v[0]) for k, v in uv_of.items()}
    s = math.sqrt(max(area, 1e-18) / max(W * H, 1e-18))
    for fc in faces:
        for l in fc.loops:
            x, y = uv_of[l.vert.index]
            l[uvl].uv = (cx + (x - W / 2) * s, cy + (y - H / 2) * s)


def gridify(faces, uvl, vco, evenness, geometry_ratio):
    coords = grid_coords(faces)
    nu = max(c[0] for c in coords.values())
    nv = max(c[1] for c in coords.values())
    lu, lv = [[] for _ in range(nu)], [[] for _ in range(nv)]
    seen_edges = set()
    for fc in faces:
        for e in fc.edges:
            if e.index in seen_edges:
                continue
            seen_edges.add(e.index)
            a, b = e.verts
            ca, cb = coords[a.index], coords[b.index]
            ln = float(np.linalg.norm(vco[a.index] - vco[b.index]))
            if ca[1] == cb[1]:
                lu[min(ca[0], cb[0])].append(ln)
            else:
                lv[min(ca[1], cb[1])].append(ln)
    su = np.array([np.mean(x) for x in lu])
    sv = np.array([np.mean(x) for x in lv])
    su = (1 - evenness) * su + evenness * su.mean()
    sv = (1 - evenness) * sv + evenness * sv.mean()
    U = np.concatenate([[0.0], np.cumsum(su)])
    V = np.concatenate([[0.0], np.cumsum(sv)])
    r = geometry_ratio
    W = (1 - r) * nu / max(nu, nv) + r * U[-1] / max(U[-1], V[-1])
    H = (1 - r) * nv / max(nu, nv) + r * V[-1] / max(U[-1], V[-1])
    uv_of = {k: (float(U[i] / U[-1] * W), float(V[j] / V[-1] * H)) for k, (i, j) in coords.items()}
    _place(faces, uvl, uv_of, W, H, None)


# ---------------------------------------------------------------------------------------------------------------------------------- rectify
def _boundary_loop(faces):
    fset = {f.index for f in faces}
    edges = []
    for fc in faces:
        for e in fc.edges:
            if sum(1 for g in e.link_faces if g.index in fset) == 1:
                edges.append(e)
    adj = {}
    for e in edges:
        a, b = e.verts
        adj.setdefault(a.index, []).append(b.index)
        adj.setdefault(b.index, []).append(a.index)
    if not edges:
        raise NotGrid("the island has no boundary (a closed surface): cut a seam first")
    if any(len(v) != 2 for v in adj.values()):
        raise NotGrid("the island's boundary is not one simple loop (it pinches or has holes)")
    start = next(iter(adj))
    loop, prev, cur = [start], None, start
    while True:
        nxt = [n for n in adj[cur] if n != prev]
        nxt = nxt[0] if prev is not None else adj[cur][0]
        if nxt == start:
            break
        loop.append(nxt)
        prev, cur = cur, nxt
        if len(loop) > len(adj):
            break
    if len(loop) != len(adj):
        raise NotGrid(f"the island's boundary is {len(adj) // max(len(loop), 1) + 1} loops, not one: it has holes")
    return loop


def _corners(loop, vco):
    n = len(loop)
    turn = []
    for k in range(n):
        a, b, c = vco[loop[k - 1]], vco[loop[k]], vco[loop[(k + 1) % n]]
        u, v = b - a, c - b
        cs = float(np.dot(u, v) / max(np.linalg.norm(u) * np.linalg.norm(v), 1e-18))
        turn.append(math.acos(max(-1.0, min(1.0, cs))))
    picked = []
    for k in sorted(range(n), key=lambda i: -turn[i]):
        if all(min((k - p) % n, (p - k) % n) >= max(2, n // 8) for p in picked):
            picked.append(k)
        if len(picked) == 4:
            break
    if len(picked) < 4:
        picked = [int(round(i * n / 4)) % n for i in range(4)]
    return sorted(picked)


def _harmonic(nodes, edges, fixed):
    """Solve L x = 0 on the free nodes with ``fixed`` {node: (x, y)} pinned (uniform weights)."""
    free = [n for n in nodes if n not in fixed]
    if not free:
        return dict(fixed)
    if len(free) > MAX_FREE:
        raise NotGrid(f"island too large for a dense solve ({len(free)} free vertices > {MAX_FREE}): split it with lampway_segment_mesh or retopo it first")
    idx = {n: i for i, n in enumerate(free)}
    A = np.zeros((len(free), len(free)))
    B = np.zeros((len(free), 2))
    for a, b in edges:
        for p, q in ((a, b), (b, a)):
            if p in idx:
                A[idx[p], idx[p]] += 1.0
                if q in idx:
                    A[idx[p], idx[q]] -= 1.0
                else:
                    B[idx[p]] += np.array(fixed[q])
    sol = np.linalg.solve(A, B)
    out = dict(fixed)
    for n, i in idx.items():
        out[n] = (float(sol[i, 0]), float(sol[i, 1]))
    return out


def _island_edges(faces):
    es = set()
    for fc in faces:
        for e in fc.edges:
            es.add((e.verts[0].index, e.verts[1].index))
    return list(es)


def rectify(faces, uvl, vco):
    loop = _boundary_loop(faces)
    cs = _corners(loop, vco)
    n = len(loop)
    seg = []
    for k in range(4):
        a, b = cs[k], cs[(k + 1) % 4]
        idxs = [(a + t) % n for t in range(((b - a) % n) + 1)]
        seg.append(idxs)
    lens = [sum(float(np.linalg.norm(vco[loop[s[t]]] - vco[loop[s[t + 1]]])) for t in range(len(s) - 1)) for s in seg]
    Wd, Hd = (lens[0] + lens[2]) / 2, (lens[1] + lens[3]) / 2
    corners = [(0.0, 0.0), (Wd, 0.0), (Wd, Hd), (0.0, Hd)]
    fixed = {}
    for k, s in enumerate(seg):
        a, b = np.array(corners[k]), np.array(corners[(k + 1) % 4])
        cum = np.concatenate([[0.0], np.cumsum([float(np.linalg.norm(vco[loop[s[t]]] - vco[loop[s[t + 1]]])) for t in range(len(s) - 1)])])
        for t, i in enumerate(s):
            fixed[loop[i]] = tuple(a + (b - a) * (cum[t] / max(cum[-1], 1e-18)))
    nodes = sorted({v for e in _island_edges(faces) for v in e})
    uv_of = _harmonic(nodes, _island_edges(faces), fixed)
    _place(faces, uvl, uv_of, Wd, Hd, None)


# ---------------------------------------------------------------------------------------------------------------------------------- straighten
def _chain(bm, edges):
    pairs = []
    for e in edges:
        if not (isinstance(e, (list, tuple)) and len(e) == 2):
            raise C.FeatureError("edges is a list of [vertex, vertex] pairs")
        a, b = int(e[0]), int(e[1])
        if a >= len(bm.verts) or b >= len(bm.verts) or bm.edges.get((bm.verts[a], bm.verts[b])) is None:
            raise C.FeatureError("edges chain must be connected and inside one island: " + f"{a}-{b} is not an edge of the mesh")
        pairs.append((a, b))
    adj = {}
    for a, b in pairs:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    ends = [v for v, n in adj.items() if len(n) == 1]
    if any(len(n) > 2 for n in adj.values()) or len(ends) != 2:
        raise C.FeatureError("edges chain must be connected and inside one island: it must be one open path")
    chain, prev, cur = [ends[0]], None, ends[0]
    while len(chain) < len(adj):
        nxt = [n for n in adj[cur] if n != prev]
        if not nxt:
            break
        prev, cur = cur, nxt[0]
        chain.append(cur)
    if len(chain) != len(adj) or len(pairs) != len(chain) - 1:
        raise C.FeatureError("edges chain must be connected and inside one island: the pairs do not form one path")
    return chain


def straighten(faces, uvl, vco, chain, keep_length):
    node_uv = {}
    for fc in faces:
        for l in fc.loops:
            node_uv.setdefault(l.vert.index, np.array(l[uvl].uv[:]))
    if any(v not in node_uv for v in chain):
        raise C.FeatureError("edges chain must be connected and inside one island: some chain vertices are in another island")
    p0, pL = node_uv[chain[0]], node_uv[chain[-1]]
    d = pL - p0
    axis = np.array([math.copysign(1.0, d[0]), 0.0]) if abs(d[0]) >= abs(d[1]) else np.array([0.0, math.copysign(1.0, d[1])])
    uv_len = sum(float(np.linalg.norm(node_uv[chain[k + 1]] - node_uv[chain[k]])) for k in range(len(chain) - 1))
    seg = [float(np.linalg.norm(vco[chain[k + 1]] - vco[chain[k]])) for k in range(len(chain) - 1)] if keep_length else [1.0] * (len(chain) - 1)
    cum = np.concatenate([[0.0], np.cumsum(seg)])
    fixed = {chain[k]: tuple(p0 + axis * uv_len * (cum[k] / cum[-1])) for k in range(len(chain))}
    for v in _boundary_loop_safe(faces):
        fixed.setdefault(v, tuple(node_uv[v]))
    nodes = sorted(node_uv)
    uv_of = _harmonic(nodes, _island_edges(faces), fixed)
    for fc in faces:
        for l in fc.loops:
            l[uvl].uv = uv_of[l.vert.index]


def _boundary_loop_safe(faces):
    fset = {f.index for f in faces}
    out = set()
    for fc in faces:
        for e in fc.edges:
            if sum(1 for g in e.link_faces if g.index in fset) == 1:
                out.update(v.index for v in e.verts)
    return out


# ---------------------------------------------------------------------------------------------------------------------------------- the tool
def run(object, op="auto", islands=None, edges=None, evenness=0.0, geometry_ratio=0.5, keep_length=True, name="", discard_texture=False, root=""):
    ob = C.need_object(object)
    if op not in ("auto", "rectify", "gridify", "straighten"):
        raise C.FeatureError("op is auto | rectify | gridify | straighten")
    if not 0.0 <= float(evenness) <= 1.0:
        raise C.FeatureError("evenness must be in 0..1")
    if not 0.0 <= float(geometry_ratio) <= 1.0:
        raise C.FeatureError("geometry_ratio must be in 0..1")
    if not ob.data.uv_layers:
        raise C.FeatureError(f"no UV layer on {ob.name}: run lampway_uv_unwrap first")
    if _textured(ob) and not discard_texture:
        raise C.FeatureError(f"{ob.name} is textured; a UV change discards the texture. Run this on the pre-texture copy, or pass discard_texture=true")
    if op == "straighten" and not edges:
        raise C.FeatureError("edges is required for op=straighten: an ordered chain [[vertex, vertex], ...]")
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    bm.edges.ensure_lookup_table()
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    mw = ob.matrix_world
    vco = {v.index: np.array(mw @ v.co) for v in bm.verts}
    groups = _faces_by_island(bm, uvl)
    if islands in (None, "strips"):
        ids = sorted(groups)
    else:
        ids = [int(i) for i in islands]
        missing = [i for i in ids if i not in groups]
        if missing:
            bm.free()
            raise C.FeatureError(f"island ids {missing} do not exist; the mesh has {len(groups)} islands (0..{len(groups) - 1}, as lampway_uv_score reports)")
    ops, skipped = [], []
    chain = None
    if op == "straighten":
        try:
            chain = _chain(bm, edges)
        except C.FeatureError:
            bm.free()
            raise
        owner = {i for i, fs in groups.items() if any(v in {x.index for f in fs for x in f.verts} for v in chain[:1])}
        ids = [i for i in ids if i in owner]
        if not ids:
            bm.free()
            raise C.FeatureError("edges chain must be connected and inside one island: it is in an island that was not selected")
    for i in ids:
        faces = groups[i]
        before = _metrics(faces, uvl, vco)
        how = op
        try:
            if op == "straighten":
                straighten(faces, uvl, vco, chain, bool(keep_length))
            elif op == "gridify":
                gridify(faces, uvl, vco, float(evenness), float(geometry_ratio))
            elif op == "rectify":
                rectify(faces, uvl, vco)
            else:
                try:
                    gridify(faces, uvl, vco, float(evenness), float(geometry_ratio))
                    how = "gridify"
                except NotGrid as exc:
                    lo, hi = _bbox(faces, uvl)
                    w, h = hi - lo
                    if max(w, h) / max(min(w, h), 1e-12) > 3.0:
                        rectify(faces, uvl, vco)
                        how = "rectify"
                    else:
                        raise exc
        except NotGrid as exc:
            skipped.append({"island": i, "reason": str(exc)})
            continue
        after = _metrics(faces, uvl, vco)
        ops.append({"island": i, "op": how, "faces": len(faces), "rectangularity_before": before["rectangularity"], "rectangularity_after": after["rectangularity"],
                    "stretch_p90_p10_before": before["stretch_p90_p10"], "stretch_p90_p10_after": after["stretch_p90_p10"],
                    "uv_area_before": before["uv_area"], "uv_area_after": after["uv_area"]})
    new = C.duplicate(ob, "_rect")
    if name:
        new.name = name
        new.data.name = name
    bm.to_mesh(new.data)
    bm.free()
    new.data.update()
    out = {"object": new.name, "source": ob.name, "ops": ops, "skipped": skipped}
    if root:
        Path(root).mkdir(parents=True, exist_ok=True)
        (Path(root) / "uv_rectify.json").write_text(json.dumps(out, indent=1))
    return out
