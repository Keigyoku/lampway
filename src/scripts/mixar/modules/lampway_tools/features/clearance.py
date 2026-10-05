# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""garment_clearance: how far a piece sits from the posed body (signed distance through the body's BVH), in rest and in named poses, so fit is a number before any weight is trusted.

Positive is outside the body, negative inside. Per pose: the smallest clearance, the penetrating vertices, the deepest penetration, where it is, and the body surfaces that block (clusters of the
penetrating vertices' nearest body triangles). A pose passes when every vertex clears its target (the default, or the target of the vertex group the vertex belongs to: rigid and cloth parts differ).
The body is posed by its own armature and every pose is reset afterwards."""

import math

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from . import rig as _rig
from . import workflows as _wf

TARGET_DEFAULT = 0.015           # the opening clearance of the user's runbook
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


def _body_arrays(body):
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    m = ev.matrix_world
    V = [m @ v.co for v in me.vertices]
    me.calc_loop_triangles()
    T = [tuple(t.vertices) for t in me.loop_triangles]
    tree = BVHTree.FromPolygons(V, T)
    ev.to_mesh_clear()
    return tree


def run(piece, body, armature, pose_set=None, clearance_target_m=TARGET_DEFAULT, classes=None):
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
            tree = _body_arrays(bd)
            P = _rig._evaluated(ob)
            signed = np.empty(len(P))
            nearest = np.empty(len(P), dtype=int)
            for i, p in enumerate(P):
                v = Vector(p)
                loc, nrm, fi, dist = tree.find_nearest(v)
                signed[i] = dist if (v - loc).dot(nrm) >= 0 else -dist
                nearest[i] = fi
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
                     "pass": bool((signed >= targets).all())})
    passed = [r for r in rows if r["pass"]]
    closest = max(rows, key=lambda r: r["min_clearance_m"])["name"]
    return {"ok": True, "poses": rows, "pass_pose_count": len(passed), "closest_pose": closest, "clearance_target_m": float(clearance_target_m)}
