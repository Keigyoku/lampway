# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""vehicle_wheel_rig: each wheel's origin at its centre, a named bone per wheel, the axles checked parallel, so an engine vehicle template can drive a
generated car (specs/wiki/vehicle_wheel_rig.md). Handling, wheel physics and collision stay engine-side; the vehicle add-on is not used.

The axle is the wheel's thinnest principal direction (PCA). The rim ring is the vertices within 85 % of the largest distance from the axle line, and it must go round (six of eight 45-degree sectors:
a rectangle's four corners lie on a circle too); a least-squares
circle (Kasa) through it in the plane across the axle gives the centre and the radius, and a fit residual above RESIDUAL_MAX of the radius refuses
("this does not look like a wheel"). Each wheel is COPIED to ``<name>`` with its origin at the centre and parented to its bone; the originals keep their
origins. Bone names are the wheel names given (the engine template's naming is not in the wiki [UNVERIFIED])."""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import common as C

NAMES = ("wheel_fl", "wheel_fr", "wheel_rl", "wheel_rr")
RESIDUAL_MAX = 0.05            # [UNVERIFIED] of the radius
PARALLEL_DEG = 2.0             # [UNVERIFIED]


def _fit(P, axis_hint):
    c0 = P.mean(axis=0)
    w, V = np.linalg.eigh(np.cov((P - c0).T))
    axle = V[:, 0]
    if np.dot(axle, axis_hint) < 0:
        axle = -axle
    u = V[:, 2]
    v = np.cross(axle, u)
    rel = P - c0
    d_axle = rel @ axle
    radial = rel - np.outer(d_axle, axle)
    dist = np.linalg.norm(radial, axis=1)
    ring = rel[dist >= 0.85 * dist.max()]
    x, y = ring @ u, ring @ v
    octants = len(set((np.floor((np.arctan2(y, x) + np.pi) / (np.pi / 4)).astype(int) % 8).tolist()))
    if octants < 6:                                                        # a rectangle's corners are concyclic: a rim goes all the way round
        return c0, 0.0, math.inf, axle
    A = np.stack([x, y, np.ones_like(x)], axis=1)
    sol, *_ = np.linalg.lstsq(A, x * x + y * y, rcond=None)
    cx, cy = sol[0] / 2, sol[1] / 2
    r = math.sqrt(max(sol[2] + cx * cx + cy * cy, 0.0))
    resid = float(np.sqrt(np.mean((np.hypot(x - cx, y - cy) - r) ** 2))) if r > 0 else math.inf
    centre = c0 + cx * u + cy * v + axle * float(d_axle.mean())
    return centre, r, resid, axle


def vehicle_wheel_rig(body, wheels, axis="x", armature=None):
    C.need_object(body)
    if axis not in ("x", "y"):
        raise C.FeatureError("axis is x | y (the axle direction)")
    given = {w.get("name"): w for w in wheels or []}
    if sorted(given) != sorted(NAMES) or len(wheels) != 4:
        raise C.FeatureError(f"four wheels named {', '.join(NAMES)} (got {sorted(n for n in given if n)})")
    hint = np.array([1.0, 0, 0]) if axis == "x" else np.array([0, 1.0, 0])
    fits = {}
    for n in NAMES:
        ob = C.need_object(given[n].get("object", ""))
        if any(abs(s - 1) > 1e-4 for s in ob.scale) or any(abs(a) > 1e-4 for a in ob.rotation_euler):
            raise C.FeatureError(f"{ob.name}: apply its rotation and scale first (Ctrl+A); a fit on unapplied transforms is in the wrong frame")
        P = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
        centre, r, resid, axle = _fit(P, hint)
        if r <= 0 or resid > RESIDUAL_MAX * r:
            raise C.FeatureError(f"{n} ({ob.name}): this does not look like a wheel (rim fit residual {resid:.4f} m over a {r:.3f} m radius, more than {RESIDUAL_MAX:.0%})")
        fits[n] = (ob, centre, r, resid, axle)
    worst = max(math.degrees(math.acos(min(1.0, abs(float(np.dot(fits[a][4], fits[b][4])))))) for a in NAMES for b in NAMES)
    if armature:
        arm = C.need_object(armature, "ARMATURE")
    else:
        arm_name = f"{body}_wheels"
        for o in [o for o in bpy.data.objects if o.name == arm_name]:
            if not o.get("lw_vehicle_of"):
                raise C.FeatureError(f"an object named {arm_name!r} exists: pass it as armature or rename it")
            bpy.data.objects.remove(o)
        arm = bpy.data.objects.new(arm_name, bpy.data.armatures.new(arm_name))
        arm["lw_vehicle_of"] = body
        bpy.context.scene.collection.objects.link(arm)
    clash = [n for n in NAMES if n in arm.data.bones]
    if clash:
        raise C.FeatureError(f"{arm.name} already has bones {clash}")
    inv = arm.matrix_world.inverted()
    prev = bpy.context.view_layer.objects.active
    C.activate(arm)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        root = arm.data.edit_bones.get("root") or arm.data.edit_bones.new("root")
        if root.length < 1e-6:
            root.head, root.tail = (0, 0, 0), (0, 0.5, 0)
        for n in NAMES:
            _ob, centre, r, _res, axle = fits[n]
            b = arm.data.edit_bones.new(n)
            b.head = inv @ Vector(centre.tolist())
            b.tail = inv @ Vector((centre + axle * max(r * 0.5, 0.05)).tolist())
            b.parent = root
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if prev is not None:
            bpy.context.view_layer.objects.active = prev
    out = []
    for n in NAMES:
        src, centre, r, resid, axle = fits[n]
        for o in [o for o in bpy.data.objects if o.name == n]:
            if o.get("lw_vehicle_of") != body:
                raise C.FeatureError(f"an object named {n!r} exists: rename it (the rigged wheel copies take the wheel names)")
            bpy.data.objects.remove(o)
        cp = C.duplicate(src, "")
        cp.name = cp.data.name = n
        cp["lw_vehicle_of"] = body
        c = Vector(centre.tolist())
        local = src.matrix_world.inverted() @ c
        cp.data.transform(Matrix.Translation(-local))
        cp.matrix_world = Matrix.Translation(c)
        bpy.context.view_layer.update()
        cp.parent, cp.parent_type, cp.parent_bone = arm, "BONE", n
        bpy.context.view_layer.update()
        cp.matrix_world = Matrix.Translation(c)
        out.append({"name": n, "object": cp.name, "source": src.name, "centre": [round(float(x), 5) for x in centre], "radius_m": round(r, 5),
                    "fit_residual_m": round(resid, 6), "axle_dir": [round(float(x), 5) for x in axle],
                    "origin_error_m": round(float((src.matrix_world.translation - c).length), 5)})
    return {"wheels": out, "armature": arm.name, "axle_alignment_pass": worst <= PARALLEL_DEG, "axle_worst_deg": round(worst, 3),
            "note": "handling, wheel physics and collision are the engine template's; the bone naming follows the wheel names [UNVERIFIED for the template]"}
