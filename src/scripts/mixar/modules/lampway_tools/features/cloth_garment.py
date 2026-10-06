# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""cloth_garment_sim: drape a COPY of a garment on a posed body with Blender cloth (a pinned zone, body collision, thickness), bake the last frame to a static
shape and write a Max-Distance-style map for engine cloth (specs/wiki/cloth_garment_sim.md). Metal is never simulated.

Bounded: 10..250 frames and a wall-clock budget (TIMEOUT_S); a run past the budget stops and says how far it got. The body gets a Collision modifier for the
bake only (removed afterwards, whatever happens); the cloth modifier and its cache are removed from the copy; the scene frame is restored. The map is a
vertex group ``max_distance``: 0 at the pinned vertices (the vertex stays at its animated position, as Epic documents Max Distance 0), rising linearly with
the rest-pose distance to the nearest pinned vertex and reaching 1 at ``max_distance_m``. Every numeric default here is a placeholder: the source captions
give no usable numbers [UNVERIFIED]."""

import time

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from . import rig as _rig

TIMEOUT_S = 120.0
PEN_EPS_M = 1e-3


def _check(garment, frames, thickness_m, material_class):
    cls = material_class or garment.get("lw_material_class")
    if str(cls or "").lower() == "metal":
        raise C.FeatureError("metal parts are not cloth: rigid or segmented binding (bind_to_armature rigid, or segment it)")
    if not 10 <= int(frames) <= 250:
        raise C.FeatureError("frames is 10..250 (a bounded bake)")
    if not 0.0005 <= float(thickness_m) <= 0.02:
        raise C.FeatureError("thickness_m is 0.0005..0.02")
    if any(m.type == "ARMATURE" for m in garment.modifiers):
        raise C.FeatureError(f"{garment.name} has an Armature modifier: bind after the drape (the bake needs an unbound garment)")


def _pins(ob, group):
    g = ob.vertex_groups.get(group)
    if g is None:
        raise C.FeatureError(f"no vertex group {group!r} on {ob.name}; the groups are {sorted(x.name for x in ob.vertex_groups)}: paint the pinned zone first")
    idx = [v.index for v in ob.data.vertices for e in v.groups if e.group == g.index and e.weight > 0]
    if not idx:
        raise C.FeatureError(f"the pin group {group!r} is empty: a drape with nothing pinned falls off the body")
    return idx


def _body_tree(body):
    ev = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    me.calc_loop_triangles()
    tree = BVHTree.FromPolygons([ev.matrix_world @ v.co for v in me.vertices], [tuple(t.vertices) for t in me.loop_triangles])
    ev.to_mesh_clear()
    return tree


def cloth_garment_sim(garment, body, pin_group, frames=60, thickness_m=0.005, max_distance_map=True, max_distance_m=0.1, material_class=None):
    src = C.need_object(garment)
    bd = C.need_object(body)
    _check(src, frames, thickness_m, material_class)
    pins = _pins(src, pin_group)
    if not 0.001 <= float(max_distance_m) <= 10:
        raise C.FeatureError("max_distance_m is 0.001..10")
    name = f"{src.name}_draped"
    for o in [o for o in bpy.data.objects if o.name == name]:
        if o.get("lw_draped_from") != src.name:
            raise C.FeatureError(f"an object named {name!r} exists and is not this tool's drape: rename it first")
        bpy.data.objects.remove(o)
    sc = bpy.context.scene
    frame0 = sc.frame_current
    rest = np.array([(src.matrix_world @ v.co)[:] for v in src.data.vertices])
    dr = C.duplicate(src, "_draped")
    dr["lw_draped_from"] = src.name
    col = bd.modifiers.new("lw_cloth_collision", "COLLISION")
    bd.collision.thickness_outer = float(thickness_m)
    cloth = dr.modifiers.new("lw_cloth", "CLOTH")
    s = cloth.settings
    s.vertex_group_mass = pin_group
    s.pin_stiffness = 1.0
    cloth.collision_settings.use_collision = True
    cloth.collision_settings.distance_min = float(thickness_m)
    cache = cloth.point_cache
    cache.frame_start, cache.frame_end = 1, int(frames)
    done, started = 0, time.monotonic()
    try:
        for f in range(1, int(frames) + 1):
            sc.frame_set(f)
            done = f
            if time.monotonic() - started > TIMEOUT_S:
                raise C.FeatureError(f"the cloth bake passed its {TIMEOUT_S:.0f} s budget at frame {f} of {frames}: fewer frames or a lighter garment")
        dg = bpy.context.evaluated_depsgraph_get()
        baked = bpy.data.meshes.new_from_object(dr.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    finally:
        dr.modifiers.remove(cloth)
        bd.modifiers.remove(col)
        sc.frame_set(frame0)
    old = dr.data
    dr.data = baked
    baked.name = name
    bpy.data.meshes.remove(old)
    bpy.context.view_layer.update()
    P = _rig._evaluated(dr)
    tree = _body_tree(bd)
    pen = 0
    for p in P:
        loc, nrm, _i, dist = tree.find_nearest(Vector(p.tolist()))
        if loc is not None and (Vector(p.tolist()) - loc).dot(nrm) < -PEN_EPS_M:
            pen += 1
    disp = np.linalg.norm(P - rest, axis=1)
    out = {"draped_object": dr.name, "source": src.name, "stats": {"max_displacement_m": round(float(disp.max()), 6), "penetrations": int(pen),
           "pinned_vertices": len(pins), "pinned_max_displacement_m": round(float(disp[pins].max()), 6), "frames_simulated": done},
           "note": "a shape reference: the numeric defaults are placeholders [UNVERIFIED]; bind the drape after, metal stays rigid"}
    if max_distance_map:
        pin_pts = rest[pins]
        d = np.array([float(np.min(np.linalg.norm(pin_pts - p, axis=1))) for p in rest])
        w = np.clip(d / float(max_distance_m), 0.0, 1.0)
        w[pins] = 0.0
        g = dr.vertex_groups.get("max_distance") or dr.vertex_groups.new(name="max_distance")
        for i, x in enumerate(w):
            g.add([i], float(x), "REPLACE")
        out.update(vertex_group="max_distance", max_distance_m=float(max_distance_m))
    return out
