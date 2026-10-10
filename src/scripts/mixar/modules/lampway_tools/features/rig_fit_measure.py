# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Own-rig measurement correction by canon11 B8, without fitting or scene writes.

The existing mapped REST heads are the canon20 B1(c) base measurement. This
helper applies the specified three projected hit-mean passes, not the undecided
harmonic alternative. An open ring retains its current base and records why;
the fit tool's independent six-axis inside gate remains authoritative.
"""
import numpy as np

FINGERS = frozenset(("thumb", "index", "middle", "ring", "pinky"))


def centre(point, along, ray_cast, *, finger=False, reach_m=None):
    """BVH callback adapter for the existing canon11 projected hit-mean engine."""
    from mixar.modules.lampway_tools.pipeline import joints_views as JV
    reach = (0.05 if finger else 0.15) if reach_m is None else reach_m
    return JV.centre_rays(point, along, ray_cast, reach, 10 if finger else 12)


def measure_own_rig(example, armature, *, hidden=("pelvis", "thigh_l", "thigh_r")):
    """Read-only REST adapter; geometry-bound titan.rig-joints/1 plus audit rows.

    Does not allocate scene objects, move joints or publish a candidate. Caller
    can write the returned document to a fresh file and pass the public fit door.
    Only an armature actually deforming this example can provide base heads.
    """
    import bpy
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    from .. import canon_io
    from ..rig_tools import core as RC
    from . import common as C
    if example.type != "MESH" or armature.type != "ARMATURE":
        raise C.FeatureError("measurement requires the example mesh and its armature")
    if not any(m.type == "ARMATURE" and m.object is armature for m in example.modifiers):
        raise C.FeatureError("measurement armature does not deform this example")
    heads = {b.name: list(armature.matrix_world @ b.head_local) for b in armature.data.bones}
    parents = {b.name: b.parent.name if b.parent else None for b in armature.data.bones}
    missing = sorted(set(RC.REQUIRED_JOINTS) - heads.keys())
    if missing:
        raise C.FeatureError("own-rig measurement missing required joints: " + ", ".join(missing))
    kids = {}
    for name, parent in parents.items():
        if parent is not None:
            kids.setdefault(parent, []).append(name)
    arms = {m.object for m in example.modifiers if m.type == "ARMATURE" and m.object is not None}
    poses = {arm: arm.data.pose_position for arm in arms}
    rows, joints = {}, {}
    try:
        for arm in arms:
            arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        evaluated = example.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            tree = BVHTree.FromPolygons([example.matrix_world @ v.co for v in mesh.vertices], [list(p.vertices) for p in mesh.polygons])
        finally:
            evaluated.to_mesh_clear()
        def ray_cast(origin, direction, reach):
            hit = tree.ray_cast(Vector(origin), Vector(direction), reach)[0]
            return tuple(hit) if hit is not None else None
        for name in RC.REQUIRED_JOINTS:
            base = heads[name]
            if name in hidden:
                joints[name] = base
                rows[name] = {"position": base, "passes": [], "skipped": "hidden joint: base own-rig measurement retained", "displacement_m": 0.0}
                continue
            end = RC._next_joint(name, heads, parents, kids, kids)
            if end is None:
                raise C.FeatureError(f"{name}: anatomical continuation is undefined")
            finger = name.split("_")[0] in FINGERS
            reach = 0.05 if finger else (0.08 if name.startswith(("hand_", "foot_", "ball_")) else 0.15)
            row = centre(base, np.asarray(end)-base, ray_cast, finger=finger, reach_m=reach)
            joints[name], rows[name] = row["position"], row
        return {"schema": "titan.rig-joints/1", "example_sha256": canon_io.geometry_sha256(example), "joints": joints,
                "measurement": {"source": "mapped existing own rig REST heads, canon20 B1(c)", "armature": armature.name,
                                "method": "canon11 B8 projected hit mean", "rays": 16, "iterations": 3,
                                "hidden": list(hidden), "rows": rows, "physical_review": "unreviewed"}}
    finally:
        for arm, pose in poses.items():
            arm.data.pose_position = pose
        bpy.context.view_layer.update()
