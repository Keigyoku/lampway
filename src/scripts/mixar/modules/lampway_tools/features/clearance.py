# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""garment_clearance: how far a piece sits from the posed body (signed distance through the body's BVH), in rest and in named poses, so fit is a number before any weight is trusted.

With gap_classes {vertex group: class} the gap is measured on the piece's innermost layer per class (canon 15 B.5); with hideable_regions
{name: [bones]} each region's armour cover per standard view and whether it is hideable (B.6).
Positive is outside the body, negative inside; the sign is canon 15's (rig._signed: the angle-weighted pseudonormal of the nearest feature, never one face normal). Per pose: the smallest clearance, the penetrating vertices, the deepest penetration, where it is, and the body surfaces that block (clusters of the
penetrating vertices' nearest body triangles). A pose passes when every vertex clears its target (the default, or the target of the vertex group the vertex belongs to: rigid and cloth parts differ).
The body is posed by its own armature and every pose is reset afterwards."""

import math

import bpy
import numpy as np
from mathutils import Vector

from . import common as C
from . import rig as _rig
from . import workflows as _wf
from .. import canon_geom as G

TARGET_DEFAULT = 0.015           # the opening clearance of the user's runbook
SEG_EPS = 1e-5                   # a segment's own ends: a hit closer than this to either end is the end itself
HIDEABLE_PCT = 98.0              # canon 15 B.6: enclosed from every view at least this much
# the standard views, each as the direction from the body TOWARD the viewer (body frame: front -Y, the wearer's left +X)
VIEWS = {"front": (0.0, -1.0, 0.0), "back": (0.0, 1.0, 0.0), "left": (1.0, 0.0, 0.0), "right": (-1.0, 0.0, 0.0), "top": (0.0, 0.0, 1.0),
         "bottom": (0.0, 0.0, -1.0)}
MAX_PLACE_DISTANCE = 0.5
PEN_EPS = 1e-6


def _poses(pose_set):
    if pose_set in (None, "", "rest"):
        return [{"name": "rest"}]
    if pose_set == "wiki8":
        return [{"name": n, "bones": [{"bone": b, "rotate": r} for b, r in bones]} for n, bones in _wf.WIKI8]
    if isinstance(pose_set, str):
        raise C.FeatureError("pose_set is 'rest', 'wiki8' or a list of poses [{name, bone, rotate} | {name, bones: [{bone, rotate}]}]")
    return [dict(p) for p in pose_set]


def _opening(bd, band):
    """{boundary_edges, band_m, near (callable: points -> bool mask within ``band`` of an open boundary)}: canon 15 INV-15.2 -
    a sign near an opening is not a measurement (the winding number is fractional there)."""
    V, T = _rig._body_mesh(bd)
    e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
    u, c = np.unique(e, axis=0, return_counts=True)
    rim = np.unique(u[c == 1])
    return {"boundary_edges": int((c == 1).sum()), "band_m": band, "rim": rim}


def _dominant(ob, wanted):
    """{vertex index: the listed group of largest weight} for the groups named in ``wanted``."""
    names = {g.index: g.name for g in ob.vertex_groups}
    out = {}
    for v in ob.data.vertices:
        best = max(((g.weight, names.get(g.group)) for g in v.groups if names.get(g.group) in wanted and g.weight > 0), default=None)
        if best:
            out[v.index] = best[1]
    return out


def _gap(P, signed, Vb, Tb, Vp, Tp, cls):
    """canon 15 B.5: {class: {p50_m, p90_m, vertices, excluded_outer}} over the INNERMOST piece vertices - those whose segment to their
    nearest skin point crosses no piece surface (INV-15.3)."""
    from mathutils.bvhtree import BVHTree
    body = BVHTree.FromPolygons([tuple(v) for v in Vb], [tuple(int(i) for i in t) for t in Tb])
    pc = BVHTree.FromPolygons([tuple(v) for v in Vp], [tuple(int(i) for i in t) for t in Tp])
    rows = {}
    for i, c in cls.items():
        p = Vector(P[i])
        q, _n, _k, _d = body.find_nearest(p)
        r = rows.setdefault(c, {"gaps": [], "excluded_outer": 0})
        if q is None:
            continue
        d = q - p
        L = d.length
        hit = pc.ray_cast(p + d.normalized() * SEG_EPS, d.normalized(), max(L - 2 * SEG_EPS, 0.0))[0] if L > 2 * SEG_EPS else None
        if hit is None:
            r["gaps"].append(float(signed[i]))
        else:
            r["excluded_outer"] += 1
    return {c: {"p50_m": round(float(np.percentile(r["gaps"], 50)), 6) if r["gaps"] else None,
                "p90_m": round(float(np.percentile(r["gaps"], 90)), 6) if r["gaps"] else None,
                "vertices": len(r["gaps"]), "excluded_outer": r["excluded_outer"]} for c, r in sorted(rows.items())}


def _hideable(bd, Vb, Tb, Vp, Tp, regions):
    """canon 15 B.6: per region (its bones), per standard view, the share of the region's projected skin - the region rendered alone -
    that the armour covers; hideable when every view that shows the region is at least HIDEABLE_PCT."""
    from mathutils.bvhtree import BVHTree
    armour = BVHTree.FromPolygons([tuple(v) for v in Vp], [tuple(int(i) for i in t) for t in Tp])
    out = {}
    for name, bones in regions.items():
        dom = _dominant(bd, set(bones))
        tri = np.array([t for t in Tb if all(int(i) in dom for i in t)], int)
        if not len(tri):
            raise C.FeatureError(f"region {name!r}: no body triangle is weighted to {', '.join(bones)}")
        own = BVHTree.FromPolygons([tuple(v) for v in Vb], [tuple(int(i) for i in t) for t in tri])
        a, b, c = Vb[tri[:, 0]], Vb[tri[:, 1]], Vb[tri[:, 2]]
        n = np.cross(b - a, c - a)
        area2 = np.linalg.norm(n, axis=1)
        nrm = n / np.maximum(area2, 1e-18)[:, None]
        cen = (a + b + c) / 3
        views = {}
        for view, v in VIEWS.items():
            v = np.array(v)
            w = 0.5 * area2 * np.abs(nrm @ v)
            seen = covered = 0.0
            for k in np.nonzero(w > 1e-12)[0]:
                o = Vector(cen[k] + v * SEG_EPS)
                if own.ray_cast(o, Vector(v))[0] is not None:
                    continue                                   # hidden behind the region's own skin
                seen += w[k]
                if armour.ray_cast(o, Vector(v))[0] is not None:
                    covered += w[k]
            if seen > 1e-9 * float(area2.sum()):
                views[view] = round(float(100.0 * covered / seen), 3)
        out[name] = {"enclosed_pct_by_view": views, "hideable": bool(views and min(views.values()) >= HIDEABLE_PCT)}
    return out


def run(piece, body, armature, pose_set=None, clearance_target_m=TARGET_DEFAULT, classes=None, body_open_band_m=None, gap_classes=None,
        hideable_regions=None):
    ob = C.need_object(piece)
    bd = C.need_object(body)
    arm = C.need_object(armature, "ARMATURE")
    if not 0 <= float(clearance_target_m) <= 0.1:
        raise C.FeatureError("clearance_target_m is 0..0.1")
    if not any(m.type == "ARMATURE" for m in bd.modifiers):
        raise C.FeatureError("the body needs an armature: auto_rig or import the MetaHuman body (it has no Armature modifier)")
    bpy.context.view_layer.update()
    P0 = _rig._evaluated(ob)
    Bc = np.array([(bd.matrix_world @ Vector(c))[:] for c in bd.bound_box]).mean(axis=0)
    if float(np.linalg.norm(P0.mean(axis=0) - Bc)) > MAX_PLACE_DISTANCE:
        raise C.FeatureError(f"the piece is {np.linalg.norm(P0.mean(axis=0) - Bc):.2f} m from the body: run place_piece first (fit_place)")
    opening = _opening(bd, body_open_band_m)
    if opening["boundary_edges"] and body_open_band_m is None:
        raise C.FeatureError(f"the body is open ({opening['boundary_edges']} boundary edges, e.g. a headless body mesh): signs near the opening are not measurements "
                             "(canon 15). Use the closed full body, or declare body_open_band_m (metres) to leave the vertices within that band of the opening unsigned")
    if body_open_band_m is not None and not 0 <= float(body_open_band_m) <= 0.5:
        raise C.FeatureError("body_open_band_m is 0..0.5")
    targets = np.full(len(P0), float(clearance_target_m))
    if classes:
        names = {g.index: g.name for g in ob.vertex_groups}
        for v in ob.data.vertices:
            for g in v.groups:
                if names.get(g.group) in classes and g.weight > 0:
                    targets[v.index] = float(classes[names[g.group]])
    rows = []
    for pose in _poses(pose_set):
        moved = []
        bones = pose.get("bones") or ([{"bone": pose["bone"], "rotate": pose.get("rotate", [0, 0, 0])}] if pose.get("bone") else [])
        for b in bones:
            pb = arm.pose.bones.get(b["bone"])
            if pb is None:
                raise C.FeatureError(f"no bone {b['bone']!r} in {armature!r}; the bones are: {sorted(x.name for x in arm.data.bones)[:30]}")
            pb.rotation_mode = "XYZ"
            moved.append((pb, tuple(pb.rotation_euler)))
            pb.rotation_euler = [math.radians(float(a)) for a in b.get("rotate", [0, 0, 0])]
        bpy.context.view_layer.update()
        try:
            P = _rig._evaluated(ob)
            signed, nearest = _rig._signed(P, bd)
            unsigned = np.zeros(len(P), bool)
            if opening["boundary_edges"]:
                Vb, _Tb = _rig._body_mesh(bd)
                rim = Vb[opening["rim"]]
                unsigned = np.array([float(np.min(np.linalg.norm(rim - p, axis=1))) <= float(body_open_band_m) for p in P])
                signed = np.where(unsigned, np.abs(signed), signed)
            extra = {}
            if gap_classes or hideable_regions:
                Vb, Tb = _rig._body_mesh(bd)
                Vp, Tp = _rig._body_mesh(ob)
                if gap_classes:
                    cls = {i: gap_classes[g] for i, g in _dominant(ob, set(gap_classes)).items()}
                    extra["gap"] = _gap(P, signed, Vb, Tb, Vp, Tp, cls)
                if hideable_regions:
                    extra["hideable"] = _hideable(bd, Vb, Tb, Vp, Tp, hideable_regions)
        finally:
            for pb, before in moved:
                pb.rotation_euler = before
            bpy.context.view_layer.update()
        pen = signed < -PEN_EPS
        worst = int(signed.argmin())
        blocking = []
        if pen.any():
            ids, counts = np.unique(nearest[pen], return_counts=True)
            for k in np.argsort(-counts)[:3]:
                blocking.append({"body_triangle": int(ids[k]), "penetrating_vertices": int(counts[k])})
        rows.append({"name": pose.get("name") or "pose", "min_clearance_m": round(float(signed.min()), 6), "penetrating_vertices": int(pen.sum()),
                     "max_depth_m": round(float(max(0.0, -signed.min())), 6), "worst_region": [round(float(x), 5) for x in P[worst]], "blocking_surfaces": blocking,
                     "pass": bool((signed >= targets).all()), "unsigned_near_opening": int(unsigned.sum()), **extra})
    passed = [r for r in rows if r["pass"]]
    closest = max(rows, key=lambda r: r["min_clearance_m"])["name"]
    return {"ok": True, "poses": rows, "pass_pose_count": len(passed), "closest_pose": closest, "clearance_target_m": float(clearance_target_m),
            "body_open": {"boundary_edges": opening["boundary_edges"], "band_m": body_open_band_m}}
