# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_validate, the scene half (engine "blender"): measure a bound piece through poses against its ORIGINAL shell and judge it with pipeline/validate.py.

The original (pre-fit, own frame) is required: measuring against a baked rest hides a distortion. The piece is judged per part (role metal | leather | cloth | embroidery from the user or the recipe, never
from a render): rigid residual with the scale fixed, edge strain, the seam gap, crossings of the body. A pose with a failing ``expect`` is REFUSED and nothing is measured."""

import math

import bpy
import numpy as np
from mathutils import Vector

from . import common as C
from . import rig as _rig
from ..pipeline import validate as V


def _part_vertices(ob, name, roles):
    if len(roles) == 1 or name not in {g.name for g in ob.vertex_groups}:
        return np.arange(len(ob.data.vertices))
    vg = ob.vertex_groups[name]
    return np.array([v.index for v in ob.data.vertices if any(g.group == vg.index and g.weight > 0 for g in v.groups)], dtype=int)


def _pose(arm, pose):
    bones = pose.get("bones") or ([{"bone": pose["bone"], "rotate": pose.get("rotate", [0, 0, 0]), "scale": pose.get("scale")}] if pose.get("bone") else [])
    moved = []
    for b in bones:
        pb = arm.pose.bones.get(b["bone"])
        if pb is None:
            raise C.FeatureError(f"no bone {b['bone']!r} in {arm.name!r}; the bones are: {sorted(x.name for x in arm.data.bones)[:30]}")
        pb.rotation_mode = "XYZ"
        moved.append((pb, tuple(pb.rotation_euler)))
        pb.rotation_euler = [math.radians(float(a)) for a in b.get("rotate", [0, 0, 0])]
        if b.get("scale") is not None:
            moved[-1] = (*moved[-1], tuple(pb.scale))
            pb.scale = [float(b["scale"])] * 3 if not isinstance(b["scale"], (list, tuple)) else b["scale"]
    bpy.context.view_layer.update()
    return moved


def _restore(moved):
    for item in moved:
        item[0].rotation_euler = item[1]
        if len(item) > 2:
            item[0].scale = item[2]
    bpy.context.view_layer.update()


def measure(piece, bound, original, poses, roles, limits=None, body=None, armature=None):
    ob = C.need_object(bound)
    if not original:
        raise C.FeatureError("the original (the pre-fit source shell, in its own frame) is required: measuring against a baked rest hides the distortion the fit made")
    orig = C.need_object(original)
    if len(orig.data.vertices) != len(ob.data.vertices):
        raise C.FeatureError(f"the original has {len(orig.data.vertices)} vertices and the bound piece {len(ob.data.vertices)}: it must be the same mesh before the fit")
    if not roles:
        raise C.FeatureError("roles {part: metal|leather|cloth|embroidery} are required: a role comes from the user or the recipe, never from a render's colour")
    arms = [m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object]
    arm = C.need_object(armature, "ARMATURE") if armature else (arms[0] if arms else None)
    if arm is None:
        raise C.FeatureError(f"{ob.name} has no Armature modifier: bind it first (fit_bind / bind_to_armature)")
    bpy.context.view_layer.update()
    rest = _rig._evaluated(ob)
    O = np.array([(orig.matrix_world @ v.co)[:] for v in orig.data.vertices])
    fid = V.rigid_fit(O, rest, with_scale=True)
    me = ob.data
    edges = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", edges)
    edges = edges.reshape(-1, 2)
    pairs = _rig._seam_pairs(rest, edges, 0.02)
    rest_gap = np.linalg.norm(rest[pairs[:, 0]] - rest[pairs[:, 1]], axis=1) if len(pairs) else np.zeros(0)
    lim = limits or V.PROPOSED
    body_ob = C.need_object(body) if body else None
    judges, rows = [], []
    for pose in poses:
        name = pose.get("name") or "pose"
        moved = _pose(arm, pose)
        try:
            if pose.get("expect"):
                e = pose["expect"]
                pb = arm.pose.bones[e["bone"]]
                got = {e["bone"]: {f"{a}_deg": math.degrees(getattr(pb.rotation_euler, a)) for a in "xyz"}}
                chk = V.check_expect(e, got)
                if not chk["ok"]:
                    judges.append({"verdict": "REFUSED", "limits_status": lim.get("status", "proposed")})
                    rows.append({"name": name, "verdict": "REFUSED", "why": chk["why"], "pieces": {}})
                    continue
            cur = _rig._evaluated(ob)
            crossings = None
            if body_ob is not None:
                tree = _rig._body_tree(body_ob)
                crossings = 0
                for p in cur:
                    loc, nrm, _i, _d = tree.find_nearest(Vector(p))
                    if (Vector(p) - loc).dot(nrm) < -1e-6:
                        crossings += 1
        finally:
            _restore(moved)
        gap = float((np.linalg.norm(cur[pairs[:, 0]] - cur[pairs[:, 1]], axis=1) - rest_gap).max()) if len(pairs) else 0.0
        pieces = {}
        for part, role in roles.items():
            idx = _part_vertices(ob, part, roles)
            fit = V.rigid_fit(rest[idx], cur[idx], with_scale=False)
            sel = np.isin(edges[:, 0], idx) & np.isin(edges[:, 1], idx)
            remap = {int(v): k for k, v in enumerate(idx)}
            e2 = np.array([[remap[a], remap[b]] for a, b in edges[sel]]) if sel.any() else np.zeros((0, 2), int)
            st = V.edge_strain(rest[idx], cur[idx], e2) if len(e2) else {"p95_pct": 0.0, "max_pct": 0.0}
            metrics = {"rigid_residual_mm": fit["max_m"] * 1000, "strain_max_pct": st["max_pct"], "seam_gap_mm_max": max(gap, 0.0) * 1000, "crossings_body": crossings}
            j = V.judge(role, metrics, lim)
            judges.append(j)
            pieces[part] = {"role": role, "rigid_residual_mm": round(fit["max_m"] * 1000, 4), "rigid_rms_mm": round(fit["rms_m"] * 1000, 4), "strain_p95": round(st["p95_pct"], 4),
                            "strain_max": round(st["max_pct"], 4), "seam_gap_mm_max": round(max(gap, 0.0) * 1000, 4), "crossings_body": crossings, "judge": j}
        rows.append({"name": name, "pieces": pieces})
    control_ok = None
    if body_ob is not None:
        tree = _rig._body_tree(body_ob)
        nearest, normals = [], np.zeros_like(rest)
        for i, p in enumerate(rest):
            loc, nrm, _j, _d = tree.find_nearest(Vector(p))
            normals[i] = nrm[:]
            nearest.append((np.linalg.norm(np.array(loc[:]) - p), i))
        k = min(nearest)[1]
        pushed = V.control_shift(rest, normals, 0.01, [k])
        inside = sum(1 for p in pushed[[k]] if (Vector(p) - tree.find_nearest(Vector(p))[0]).dot(tree.find_nearest(Vector(p))[1]) < -1e-6)
        control_ok = inside > 0
    return {"ok": True, "schema": "lampway.armour-validation/1", "poses": rows, "rest_fidelity": {"scale": round(fid["scale"], 6), "rms_mm": round(fid["rms_m"] * 1000, 4), "max_mm": round(fid["max_m"] * 1000, 4)},
            "crossing_control": {"ok": control_ok}, "limits": lim, "summary": V.summarize(judges, True if control_ok is None else control_ok)}
