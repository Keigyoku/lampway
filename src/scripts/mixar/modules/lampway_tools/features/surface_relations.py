# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only world-metre triangle queries (canon 15 / MCP precise relations).

BVH nearest/range and segment rays prune exact triangle features: vertex/face
and edge/edge minima, including crossings between vertices. Parity is used only
on closed two-manifold meshes, as required by the observation contract.
"""
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from ..canon_geom.inside import _closest_one


def check(budget):
    if budget is not None:
        budget.check()


class Surface:
    def __init__(self, ob, scale=1, budget=None):
        check(budget)
        if budget is not None: budget.admit_geometry(ob.data)
        mesh = ob.to_mesh()
        try:
            mesh.calc_loop_triangles()
            self.vertices = np.array([tuple(ob.matrix_world @ v.co) for v in mesh.vertices], float).reshape(-1, 3) * scale
            check(budget)
            self.tris = np.array([tuple(t.vertices) for t in mesh.loop_triangles], int).reshape(-1, 3)
        finally:
            ob.to_mesh_clear()
        check(budget)
        self.points = self.vertices[self.tris]
        self.used_vertices = self.vertices[np.unique(self.tris)]
        self.tree = BVHTree.FromPolygons(self.vertices.tolist(), self.tris.tolist(), all_triangles=True) if len(self.tris) else None
        edges = np.sort(np.concatenate([self.tris[:, [0, 1]], self.tris[:, [1, 2]], self.tris[:, [2, 0]]]), axis=1)
        self.edges, counts = np.unique(edges, axis=0, return_counts=True)
        self.closed = bool(len(self.tris) and np.all(counts == 2))

    def contains(self, points, budget=None):
        if not self.closed:
            return False
        direction = Vector((1, .3713906763541037, .529173829)).normalized()
        span = float(np.linalg.norm(np.ptp(self.vertices, axis=0)))
        eps = max(span * 1e-7, 1e-9)
        for p in points:
            check(budget)
            origin = Vector(p)
            hits = 0
            # Advance past a hit; shared triangle edges are counted only once.
            for _ in range(len(self.tris) + 1):
                hit, _, _, _ = self.tree.ray_cast(origin, direction)
                if hit is None:
                    break
                hits += 1
                origin = hit + direction * eps
            if hits % 2 == 0:
                return False
        return True


def segment_distance(p, q, r, s):
    """Ericson 2004 closest points of two closed line segments."""
    u, v, w = q-p, s-r, p-r
    a, b, c, d, e = float(u@u), float(u@v), float(v@v), float(u@w), float(v@w)
    if a <= 1e-30:
        x, y = 0., np.clip(e/c, 0, 1) if c else 0.
    elif c <= 1e-30:
        x, y = np.clip(-d/a, 0, 1), 0.
    else:
        den = a*c-b*b
        x = float(np.clip((b*e-c*d)/den, 0, 1)) if den > 1e-30 else 0.
        y = (b*x+e)/c
        if y < 0:
            y, x = 0., float(np.clip(-d/a, 0, 1))
        elif y > 1:
            y, x = 1., float(np.clip((b-d)/a, 0, 1))
    return float(np.linalg.norm(w+x*u-y*v))


def distance(a, b, budget=None):
    if a.tree is None or b.tree is None:
        return None, False
    best = float('inf')
    touched = False
    # Segment rays detect face-interior penetration missed by vertex minima.
    for source, target in ((a,b),(b,a)):
        for i,j in source.edges:
            check(budget)
            p,q = source.vertices[[i,j]]
            length = float(np.linalg.norm(q-p))
            if not length:
                continue
            hit = target.tree.ray_cast(Vector(p), Vector((q-p)/length), length)
            if hit[0] is not None:
                touched = True
                eps = max(length * 1e-7, 1e-9)
                if eps < hit[3] < length-eps and abs(float(Vector((q-p)/length).dot(hit[1]))) > 1e-7:
                    return 0., True
        for p in source.used_vertices:
            check(budget)
            best = min(best, float(target.tree.find_nearest(Vector(p))[3]))
    if touched:
        return 0., False
    # Any closer B triangle must intersect A's centroid sphere enlarged by best.
    for ta in a.points:
        check(budget)
        centre = ta.mean(axis=0)
        radius = float(np.linalg.norm(ta-centre, axis=1).max())
        candidates = b.tree.find_nearest_range(Vector(centre), radius+best+1e-7)
        for _,_,index,_ in candidates:
            check(budget)
            tb = b.points[index]
            for source,target in ((ta,tb),(tb,ta)):
                for p in source:
                    best = min(best, float(_closest_one(target[0:1], target[1:2], target[2:3], p)[0][0]))
            for i,j in ((0,1),(1,2),(2,0)):
                for k,l in ((0,1),(1,2),(2,0)):
                    best = min(best, segment_distance(ta[i],ta[j],tb[k],tb[l]))
    return best, False
