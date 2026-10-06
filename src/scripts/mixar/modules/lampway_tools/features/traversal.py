# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""traversal_check: sweep a player capsule along a route over a blockout and say where it cannot go (specs/wiki/traversal_check.md). Read-only, BVH rays only.

Each route leg is sampled every half capsule radius. At every sample, in this order: the ceiling (a ray up from the ground; lower than the capsule height =
low_ceiling), the ground (a ray down from above the current ground: none within reach = a gap, whose edges are refined by bisection), the slope (the
ground's normal against max_slope_deg = too_steep), the step (a rise above max_step_m between samples = blocked; drops are allowed) and the walls (rays
along the motion at knee height, just above max_step_m, and at mid capsule height, plus sideways rays one radius long = blocked). A gap is ok when it is no
wider than jump_gap_m and its far side is no higher than jump_height_m. Each route point reports the first problem on the leg that reaches it. Sightlines
are straight rays. The capsule values are the project's: none is built in (the contract's numbers are placeholders)."""

import math

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C

KEYS = ("capsule_radius_m", "capsule_height_m", "max_step_m", "max_slope_deg", "jump_height_m", "jump_gap_m")
FALL_M = 50.0
EPS = 1e-4


def _player(player) -> dict:
    p = player if isinstance(player, dict) else {}
    missing = [k for k in KEYS if not isinstance(p.get(k), (int, float)) or isinstance(p.get(k), bool) or p.get(k) <= 0]
    if missing:
        raise C.FeatureError(f"the project's capsule values are required (the capsule decides what is traversable): missing or not positive {missing}")
    return {k: float(p[k]) for k in KEYS}


def _tree(collection):
    coll = bpy.data.collections.get(collection)
    if coll is None:
        raise C.FeatureError(f"no collection {collection!r}; the collections are {sorted(c.name for c in bpy.data.collections)}")
    dg = bpy.context.evaluated_depsgraph_get()
    V, T, lo, hi = [], [], Vector((math.inf,) * 3), Vector((-math.inf,) * 3)
    for ob in coll.all_objects:
        if ob.type != "MESH":
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        base = len(V)
        for v in me.vertices:
            w = ev.matrix_world @ v.co
            V.append(w)
            lo = Vector(map(min, lo, w))
            hi = Vector(map(max, hi, w))
        T += [tuple(base + i for i in t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
    if not T:
        raise C.FeatureError(f"collection {collection!r} holds no mesh: the walkable and obstacle sets go in it")
    return BVHTree.FromPolygons(V, T), lo, hi


class _Walker:
    def __init__(self, tree, p):
        self.t, self.p = tree, p

    def ground(self, xy, z_from):
        hit = self.t.ray_cast(Vector((xy[0], xy[1], z_from)), Vector((0, 0, -1)), FALL_M)
        if hit[0] is None:
            return None, None
        return hit[0].z, hit[1]

    def ceiling(self, xy, z):
        hit = self.t.ray_cast(Vector((xy[0], xy[1], z + 0.01)), Vector((0, 0, 1)), self.p["capsule_height_m"])
        return None if hit[0] is None else hit[0].z - z

    def wall(self, a, b, z):
        d = (b - a)
        if d.length < 1e-9:
            return None
        d.normalize()
        side = Vector((-d.y, d.x, 0))
        r = self.p["capsule_radius_m"]
        for h in (self.p["max_step_m"] + 0.05, self.p["capsule_height_m"] * 0.5):
            o = Vector((a.x, a.y, z + h))
            for direction, length in ((d, (b - a).length + r), (side, r), (-side, r)):
                hit = self.t.ray_cast(o, direction, length)
                if hit[0] is not None:
                    return round(h, 3), hit[0], direction
        return None

    def supported(self, xy, cur):
        z, n = self.ground(xy, cur + self.p["jump_height_m"] + 0.01)
        return z is not None and n is not None and n.z > 0

    def edge(self, a, b, cur, a_supported):
        """Bisect between a (support = a_supported) and b (the opposite) for the support edge."""
        for _ in range(16):
            m = (a + b) / 2
            if self.supported(m, cur) == a_supported:
                a = m
            else:
                b = m
        return (a + b) / 2


def _leg(w, a, b, cur):
    """Walk a -> b on the ground; (state, detail, ground z at b)."""
    p = w.p
    dist = (Vector((b.x, b.y)) - Vector((a.x, a.y))).length
    n = max(1, math.ceil(dist / (p["capsule_radius_m"] / 2)))
    prev = Vector((a.x, a.y))
    gap_from = None
    for k in range(1, n + 1):
        xy = Vector((a.x, a.y)).lerp(Vector((b.x, b.y)), k / n)
        z, nrm = w.ground(xy, cur + max(p["max_step_m"], p["jump_height_m"]) + 0.01)
        if z is None or nrm.z <= 0:
            if gap_from is None:
                gap_from = w.edge(prev, xy, cur, True)
            prev = xy
            continue
        if gap_from is not None:
            gap_to = w.edge(prev, xy, cur, False)
            width = (gap_to - gap_from).length
            if width > p["jump_gap_m"] + EPS or z - cur > p["jump_height_m"] + EPS:
                return "gap", f"a {width:.1f} m gap at {[round(gap_from.x, 2), round(gap_from.y, 2)]}; the jump covers {p['jump_gap_m']} m and {p['jump_height_m']} m up", z
            gap_from = None
        ceil = w.ceiling(xy, z)
        if ceil is not None and ceil < p["capsule_height_m"] - EPS:
            return "low_ceiling", f"{ceil:.2f} m of headroom at {[round(xy.x, 2), round(xy.y, 2)]}; the capsule is {p['capsule_height_m']} m", z
        slope = math.degrees(math.acos(max(-1.0, min(1.0, nrm.z))))
        if slope > p["max_slope_deg"] + EPS:
            return "too_steep", f"a {slope:.0f} degree slope at {[round(xy.x, 2), round(xy.y, 2)]}; max_slope_deg is {p['max_slope_deg']}", z
        if z - cur > p["max_step_m"] + EPS:
            return "blocked", f"a step of {z - cur:.2f} m at {[round(xy.x, 2), round(xy.y, 2)]}; max_step_m is {p['max_step_m']}", z
        hit = w.wall(Vector((prev.x, prev.y, 0)), Vector((xy.x, xy.y, 0)), cur)
        if hit is not None:
            h, at, d = hit
            top, _n = w.ground((at + d * 0.02).xy, cur + p["capsule_height_m"])        # what stands there: a step the capsule could stand on, or a wall
            if top is not None and top - cur < p["capsule_height_m"]:
                return "blocked", f"a step of {top - cur:.2f} m at {[round(at.x, 2), round(at.y, 2)]}; max_step_m is {p['max_step_m']}", z
            return "blocked", f"a wall at {h} m above the ground at {[round(at.x, 2), round(at.y, 2)]}", z
        cur, prev = z, xy
    if gap_from is not None:
        return "gap", f"no ground from {[round(gap_from.x, 2), round(gap_from.y, 2)]} to the route point", cur
    return "ok", "", cur


def traversal_check(route, collection, player, sightlines=None):
    p = _player(player)
    pts = [Vector([float(c) for c in r]) for r in (route or [])]
    if len(pts) < 2 or any(len(r) != 3 for r in route):
        raise C.FeatureError("route is at least two [x, y, z] points")
    tree, lo, hi = _tree(collection)
    for i, q in enumerate(pts):
        if not (lo.x - 1 <= q.x <= hi.x + 1 and lo.y - 1 <= q.y <= hi.y + 1):
            raise C.FeatureError(f"route point {i} {list(q)} lies outside the blockout's bounds: check the route or the collection")
    w = _Walker(tree, p)
    steps = []
    z0, n0 = w.ground(pts[0].xy, pts[0].z + p["capsule_height_m"])
    if z0 is None:
        steps.append({"index": 0, "point": list(pts[0]), "state": "gap", "detail": "no ground under the start"})
        cur = pts[0].z
    else:
        ceil = w.ceiling(pts[0].xy, z0)
        low = ceil is not None and ceil < p["capsule_height_m"] - EPS
        steps.append({"index": 0, "point": list(pts[0]), "state": "low_ceiling" if low else "ok", "detail": f"{ceil:.2f} m of headroom" if low else ""})
        cur = z0
    for i in range(1, len(pts)):
        state, detail, cur = _leg(w, pts[i - 1], pts[i], cur)
        steps.append({"index": i, "point": [round(x, 4) for x in pts[i]], "state": state, "detail": detail})
    lines = []
    for s in sightlines or []:
        a, b = Vector(s["from"]), Vector(s["to"])
        d = b - a
        hit = tree.ray_cast(a, d.normalized(), d.length) if d.length > 0 else (None,)
        lines.append({"from": s["from"], "to": s["to"], "ok": hit[0] is None, "blocked_at": None if hit[0] is None else [round(x, 3) for x in hit[0]]})
    return {"steps": steps, "blocked_count": sum(1 for s in steps if s["state"] != "ok"), "sightlines": lines, "player": p,
            "note": "the capsule values are the project's; repair one cause at a time and run again"}
