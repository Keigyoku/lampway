# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_defect_scan: a read-only clay inspection. Typed defect candidates (open loops, floating shells, self-intersections, thin features, flipped shells, degenerate faces, isolated
triangles), each with a descriptor (faces, area, centroid, bbox, normal, rim length) and a rule verdict (keep | delete | hole | ambiguous), for the user's typed decisions; the agent
or a model only PROPOSES. It never edits the mesh. Everything is bmesh + BVH, so cost is bounded (intersection and thin use the BVH, never an all-pairs loop)."""

import math

import bmesh
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from . import workflows as W

KINDS = ("open_loop", "floating_shell", "intersection", "thin", "flipped_shell", "degenerate", "isolated_tri")
FLOAT_MM = 3.0
MAX_SHELL_TRIS = 400
RAY_EPS_FRAC = 1e-4      # the ray origin offset, as a fraction of the bounding-box diagonal (scale-free: a model 100x larger gets a 100x larger epsilon)
MIN_RIM_M = 0.0          # report every open loop; the user's rules decide which are intended


def _rim_length(edges, budget=None):
    """Canonical boundary length in metres, rounded once after the complete sum.

    Tool candidates and inspection use the same four-decimal metre presentation;
    rounding through five decimals can move a rim across a half-step (bunny).
    """
    length = 0.0
    for edge in edges:
        if budget:
            budget.check()
        length += edge.calc_length()
    return round(length, 4)


def _descriptor(faces, extra=None, budget=None) -> dict:
    pts = []
    for face in faces:
        if budget:
            budget.check()
        pts.extend(v.co for v in face.verts)
    pts = pts or [Vector()]
    lo = [min(p[i] for p in pts) for i in range(3)]
    hi = [max(p[i] for p in pts) for i in range(3)]
    n = sum((f.normal * f.calc_area() for f in faces), Vector())
    d = {"faces": len(faces), "area_m2": round(sum(f.calc_area() for f in faces), 6), "centroid": [round((a + b) / 2, 5) for a, b in zip(lo, hi)],
         "bbox": [round(x, 5) for x in lo + hi], "normal": [round(x, 4) for x in (n.normalized() if n.length > 1e-12 else n)], "rim_length_m": 0.0}
    d.update(extra or {})
    return d


def _components(faces, budget=None):
    """Connected components (by shared edges) of a set of faces."""
    pool, comps = set(faces), []
    while pool:
        if budget: budget.check()
        seed = pool.pop()
        comp, stack = [seed], [seed]
        while stack:
            if budget: budget.check()
            f = stack.pop()
            for e in f.edges:
                for nb in e.link_faces:
                    if nb in pool:
                        pool.discard(nb)
                        comp.append(nb)
                        stack.append(nb)
        comps.append(comp)
    return comps


def _shells(bm, budget=None):
    pool, shells = set(bm.faces), []
    while pool:
        if budget: budget.check()
        seed = pool.pop()
        shell, stack = [seed], [seed]
        while stack:
            if budget: budget.check()
            f = stack.pop()
            for e in f.edges:
                for nb in e.link_faces:
                    if nb in pool:
                        pool.discard(nb)
                        shell.append(nb)
                        stack.append(nb)
        shells.append(shell)
    return shells


def _open_loops(bm, budget=None):
    out, seen = [], set()
    for e in bm.edges:
        if budget: budget.check()
        if len(e.link_faces) == 1 and e not in seen:
            loop, stack = [], [e]
            seen.add(e)
            while stack:
                if budget: budget.check()
                cur = stack.pop()
                loop.append(cur)
                for v in cur.verts:
                    for nb in v.link_edges:
                        if len(nb.link_faces) == 1 and nb not in seen:
                            seen.add(nb)
                            stack.append(nb)
            faces = list({f for ed in loop for f in ed.link_faces})
            out.append((loop, faces))
    return out


def run(object, piece="", kinds=None, thin_threshold_m=0.002, max_candidates=100):
    ob = C.need_object(object)
    kinds = list(kinds or KINDS)
    bad = [k for k in kinds if k not in KINDS]
    if bad:
        raise C.FeatureError(f"unknown kind {bad[0]!r}; the kinds are {', '.join(KINDS)}")
    if not 0.0001 <= float(thin_threshold_m) <= 0.05:
        raise C.FeatureError("thin_threshold_m is 0.0001..0.05 metres")
    if not 1 <= int(max_candidates) <= 500:
        raise C.FeatureError("max_candidates is 1..500")
    if not len(ob.data.polygons):
        raise C.FeatureError(f"{ob.name} has no faces: nothing to scan; import the piece first")
    bm = bmesh.new()
    try:
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        if ob.matrix_world.to_3x3().determinant() < 0:
            bmesh.ops.reverse_faces(bm, faces=list(bm.faces))
        bm.faces.ensure_lookup_table()
        bm.edges.ensure_lookup_table()
        bm.normal_update()
        return scan_bmesh(bm, piece=piece or ob.name, kinds=kinds,
                          thin_threshold_m=thin_threshold_m, max_candidates=max_candidates)
    finally:
        bm.free()


def scan_bmesh(bm, *, piece="", kinds=None, thin_threshold_m=0.002,
               max_candidates=None, budget=None):
    """Read a caller-owned metric bmesh; never resolve an object or alter its data.

    This is the same scanner used by run(), with optional cooperative cancellation.
    None returns all candidates so inspection aggregates are never capped silently.
    """
    kinds = list(kinds or KINDS)
    bm.faces.ensure_lookup_table()
    bm.faces.index_update()
    bm.edges.ensure_lookup_table()
    found = []
    rays = None

    def add(kind, faces, verdict, rule, severity, extra=None):
        check()
        found.append({"kind": kind, "descriptor": _descriptor(faces, extra, budget=budget), "rule_verdict": verdict, "rule": rule, "severity": severity})

    check = budget.check if budget else lambda: None
    check()
    shells = sorted(_shells(bm, budget=budget),
                    key=lambda group: min(face.index for face in group))
    if "open_loop" in kinds:
        for loop, faces in _open_loops(bm, budget=budget):
            rim = _rim_length(loop, budget=budget)
            if rim >= MIN_RIM_M:
                add("open_loop", faces, "ambiguous", "a boundary loop: a hole or an intended opening is the user's call (opening_gasket decides what to do with it)",
                    "medium", {"rim_length_m": rim, "edges": len(loop)})
    if "floating_shell" in kinds and len(shells) > 1:
        big = max(shells, key=len)
        bigv = np.array([v.co[:] for f in big for v in f.verts])
        from mathutils import kdtree
        kd = kdtree.KDTree(len(bigv))
        for i, p in enumerate(bigv):
            kd.insert(Vector(p), i)
        kd.balance()
        for sh in shells:
            if sh is big or len(sh) > MAX_SHELL_TRIS:
                continue
            gap = min(kd.find(v.co)[2] for f in sh for v in f.verts)
            if gap > FLOAT_MM / 1000:
                add("floating_shell", sh, "delete" if len(sh) < 50 else "ambiguous", f"a small shell {gap * 1000:.0f} mm from the body: it floats", "medium", {"gap_m": round(gap, 5)})
    if "isolated_tri" in kinds:
        for sh in shells:
            if len(sh) == 1:
                add("isolated_tri", sh, "delete", "a lone triangle", "low")
    if "degenerate" in kinds:
        for f in bm.faces:
            if f.calc_area() < 1e-10:
                add("degenerate", [f], "delete", "a face with no area", "low")
    if "flipped_shell" in kinds:
        orientation = W.shell_orientation_bmesh(bm, budget=budget)
        idx = W._shell_faces(bm, budget=budget)
        for row in orientation:
            if row["outward_fraction"] < W.FLIPPED_BELOW:
                add("flipped_shell", [bm.faces[i] for i in idx[row["shell"]]], "ambiguous", "the shell points into itself (an open piece has no volume to tell: this is its outward-ray vote)", "high")
    if len(bm.faces) and ("intersection" in kinds or "thin" in kinds):
        check()
        tree = BVHTree.FromBMesh(bm)
        check()
        if "intersection" in kinds:
            shell_of = {f.index: k for k, sh in enumerate(shells) for f in sh}
            groups = {}
            overlaps = tree.overlap(tree)
            check()
            for i, j in overlaps:
                check()
                if i < j and not ({v for v in bm.faces[i].verts} & {v for v in bm.faces[j].verts}):
                    groups.setdefault(tuple(sorted((shell_of[i], shell_of[j]))), set()).update((i, j))
            for pair, ids in sorted(groups.items()):                                  # one candidate per pair of shells that cross (or per self-crossing shell)
                add("intersection", [bm.faces[i] for i in sorted(ids)], "ambiguous", "faces that cross other faces", "high", {"shells": list(pair)})
        if "thin" in kinds:
            thin = []
            pts = np.array([v.co[:] for v in bm.verts])
            diag = float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0)))
            eps = RAY_EPS_FRAC * diag
            cast = hits = 0
            for f in bm.faces:
                check()
                c, n = f.calc_center_median(), f.normal
                hit = tree.ray_cast(c - n * eps, -n)
                cast += 1
                if hit[0] is not None:
                    hits += 1
                if hit[0] is not None and hit[3] < float(thin_threshold_m):
                    thin.append(f)
            rays = {"faces_cast": cast, "hit": hits, "miss": cast - hits, "hit_fraction": round(hits / max(cast, 1), 4), "epsilon_m": eps, "epsilon_frac_of_diagonal": RAY_EPS_FRAC,
                    "bbox_diagonal_m": round(diag, 6),
                    "note": ("an open mesh: many inward rays escape, so the thin candidates are a lower bound" if hits < 0.9 * max(cast, 1) else "inward rays hit the far wall: the thin scan has coverage")}
            for comp in _components(thin, budget=budget):
                check()
                add("thin", comp, "ambiguous", f"thinner than {thin_threshold_m} m inward", "medium")
    for i, c in enumerate(found):
        c["id"] = f"{c['kind']}-{i}"
    counts = {}
    for c in found:
        counts[c["kind"]] = counts.get(c["kind"], 0) + 1
    out = found if max_candidates is None else found[:int(max_candidates)]
    res = {"piece": piece, "candidates": out, "counts": counts, "truncated": len(found) > len(out), "total": len(found)}
    if rays is not None:
        res["rays"] = rays
    return res


def _plain(ob):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.faces.ensure_lookup_table()
    return bm
