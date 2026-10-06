# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scale_to_measure (specs/wiki/scale_to_measure.md): one uniform factor that puts an object's dimension on ``axis`` (x | y | z | max) at a measured length
(``target.length_m``, or the same dimension of ``reference_object``), in scene units of ``unit_scale`` metres (0.01 for a centimetre FBX). The scale is then
applied into the mesh (``apply``), never on a skinned mesh, an armature or a mesh with shape keys. The transform before the change is kept on the object as
``lw_prev_scale`` so ``rollback`` puts it back. Children follow the parent (``children`` include) or keep their world placement (skip)."""

import json

import bpy
from mathutils import Matrix

from . import common as C

AXES = {"x": 0, "y": 1, "z": 2}
PROP = "lw_prev_scale"


def _skinned(ob) -> bool:
    if any(m.type == "ARMATURE" for m in getattr(ob, "modifiers", [])):
        return True
    return ob.parent is not None and ob.parent.type == "ARMATURE" and ob.parent_type in ("ARMATURE", "BONE")


def _dim(ob, axis):
    d = list(ob.dimensions)
    return max(d) if axis == "max" else d[AXES[axis]]


def _keep_world(objs):
    saved = [(o, o.matrix_world.copy()) for o in objs]

    def restore():
        bpy.context.view_layer.update()
        for o, m in saved:
            o.matrix_world = m
        bpy.context.view_layer.update()
    return restore


def _bake(ob, diag):
    """Move the object's scale ``diag`` into its mesh (the world shape is unchanged; its children keep their world placement)."""
    restore = _keep_world(ob.children)
    ob.data.transform(Matrix.Diagonal((diag[0], diag[1], diag[2], 1.0)))
    ob.data.update()
    ob.scale = (ob.scale[0] / diag[0], ob.scale[1] / diag[1], ob.scale[2] / diag[2])
    restore()


def _guard_apply(ob):
    if ob.type == "ARMATURE" or _skinned(ob):
        raise C.FeatureError(f"applying scale to a skinned mesh or armature breaks the rig ({ob.name!r}): scale the armature object only or pass apply=false")
    if ob.type == "MESH" and ob.data.shape_keys is not None:
        raise C.FeatureError(f"shape keys present on {ob.name!r}: applying the scale would not scale them; bake the keys first or pass apply=false")
    if ob.type != "MESH":
        raise C.FeatureError(f"{ob.name!r} is a {ob.type}: only a mesh's scale can be applied here; pass apply=false")
    if ob.data.users > 1:
        raise C.FeatureError(f"{ob.name!r} shares its mesh with {ob.data.users - 1} other object(s): applying would scale them too; pass apply=false")


def rollback(ob) -> dict:
    raw = ob.get(PROP)
    if not raw:
        raise C.FeatureError(f"{ob.name!r} has no {PROP}: there is nothing to roll back (only a scale_to_measure change records one)")
    prev = json.loads(raw)
    before = [round(v, 6) for v in ob.dimensions]
    skip = prev.get("children") == "skip"
    if prev.get("applied"):
        total = prev["total"]
        restore = _keep_world(ob.children)
        ob.data.transform(Matrix.Diagonal((1.0 / total[0], 1.0 / total[1], 1.0 / total[2], 1.0)))
        ob.data.update()
        ob.scale = tuple(total)
        restore()
    restore = _keep_world(ob.children) if skip else (lambda: None)
    ob.scale = tuple(prev["scale"])
    restore()
    bpy.context.view_layer.update()
    del ob[PROP]
    return {"object": ob.name, "rolled_back": True, "dimensions_before": before, "dimensions_after": [round(v, 6) for v in ob.dimensions], "scale": list(ob.scale)}


def scale_to_measure(object, target=None, reference_object="", apply=True, unit_scale=1.0, children="include", rollback_=False):
    ob = bpy.data.objects.get(object)
    if ob is None:
        raise C.FeatureError(f"no object named {object!r}; the objects are: {sorted(o.name for o in bpy.data.objects)}")
    if rollback_:
        return rollback(ob)
    if children not in ("include", "skip"):
        raise C.FeatureError("children is include | skip")
    us = float(unit_scale)
    if not 0.0 < us <= 1000.0:
        raise C.FeatureError("unit_scale is the length of one scene unit in metres (1.0, or 0.01 for a centimetre FBX)")
    t = dict(target or {})
    axis = str(t.get("axis", "max"))
    if axis not in ("x", "y", "z", "max"):
        raise C.FeatureError("target.axis is x | y | z | max")
    if reference_object:
        ref = bpy.data.objects.get(reference_object)
        if ref is None:
            raise C.FeatureError(f"no reference object named {reference_object!r}")
        length = _dim(ref, axis) * us
        length_src = f"reference_object {ref.name} ({axis})"
    else:
        if t.get("length_m") is None:
            raise C.FeatureError("give target {axis, length_m} or a reference_object to measure (the length is measured, never guessed)")
        length = float(t["length_m"])
        length_src = "target.length_m"
    if not 0.001 <= length <= 1000.0:
        raise C.FeatureError(f"length_m {length} is outside 0.001..1000 metres")
    if apply:
        _guard_apply(ob)
    current = _dim(ob, axis)
    if current <= 0:
        raise C.FeatureError(f"{ob.name!r} has no extent on {axis}: nothing to scale")
    factor = (length / us) / current
    before = [round(v, 6) for v in ob.dimensions]
    prev = {"scale": [round(v, 9) for v in ob.scale], "factor": factor, "applied": bool(apply), "children": children}
    restore = _keep_world(ob.children) if children == "skip" else (lambda: None)
    ob.scale = (ob.scale[0] * factor, ob.scale[1] * factor, ob.scale[2] * factor)
    bpy.context.view_layer.update()
    restore()
    if apply:
        total = list(ob.scale)
        _bake(ob, total)
        prev["total"] = total
    bpy.context.view_layer.update()
    ob[PROP] = json.dumps(prev)
    return {"object": ob.name, "axis": axis, "length_m": length, "length_source": length_src, "dimensions_before": before,
            "dimensions_after": [round(v, 6) for v in ob.dimensions], "factor": round(factor, 9), "applied": bool(apply), "unit_scale": us,
            "children": children, "rollback": f"scale_to_measure(object={ob.name!r}, rollback=true) restores the transform from {PROP}"}
