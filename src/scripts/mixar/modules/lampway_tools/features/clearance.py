# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""garment_clearance: how far a piece sits from the posed body (signed distance through the body's BVH), in rest and in named poses, so fit is a number before any weight is trusted.

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


def run(piece, body, armature, pose_set=None, clearance_target_m=TARGET_DEFAULT, classes=None, body_open_band_m=None):
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
                     "pass": bool((signed >= targets).all()), "unsigned_near_opening": int(unsigned.sum())})
    passed = [r for r in rows if r["pass"]]
    closest = max(rows, key=lambda r: r["min_clearance_m"])["name"]
    return {"ok": True, "poses": rows, "pass_pose_count": len(passed), "closest_pose": closest, "clearance_target_m": float(clearance_target_m),
            "body_open": {"boundary_edges": opening["boundary_edges"], "band_m": body_open_band_m}}
