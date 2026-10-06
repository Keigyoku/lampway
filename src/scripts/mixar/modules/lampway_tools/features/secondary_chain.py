# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""secondary_chain_rig: a bone chain for a tail, hair, cape or coat under an existing bone, weighted, with damped-track preview constraints and capsule
collider proxies (specs/wiki/secondary_chain_rig.md). It does not simulate and emits no numeric physics presets (the wiki forbids copying them).

Works on COPIES: ``<armature>_chain`` and ``<object>_chain`` (the mesh copy's armature modifier points at the armature copy); a re-run replaces only this
tool's copies. The chain runs along the region's principal axis (PCA of the region's vertices), from the end nearer the parent bone outward, in ``bones``
equal connected segments. Region weights interpolate between control points (the parent bone at the root, each chain bone at its middle), so a region
vertex is weighted to the chain and the parent only; every other influence it had is removed and counted. Colliders: one capsule per deform bone that
dominates part of the body outside the region, radius = the farthest such vertex from the bone segment, parented to that bone."""

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import common as C
from . import weights as _w

TAG = "lw_secondary_chain_of"
MAX_BONES = 24


def _copy_armature(arm):
    name = f"{arm.name}_chain"
    for o in [o for o in bpy.data.objects if o.name == name]:
        if o.get(TAG) != arm.name:
            raise C.FeatureError(f"an object named {name!r} exists and is not this tool's copy: rename it first")
        bpy.data.objects.remove(o)
    new = arm.copy()
    new.data = arm.data.copy()
    new.name = new.data.name = name
    new[TAG] = arm.name
    for coll in (arm.users_collection or [bpy.context.scene.collection]):
        coll.objects.link(new)
    return new


def _copy_mesh(ob, arm_copy):
    name = f"{ob.name}_chain"
    for o in [o for o in bpy.data.objects if o.name == name]:
        if o.get(TAG) != ob.name:
            raise C.FeatureError(f"an object named {name!r} exists and is not this tool's copy: rename it first")
        bpy.data.objects.remove(o)
    new = C.duplicate(ob, "_chain")
    new[TAG] = ob.name
    for m in new.modifiers:
        if m.type == "ARMATURE":
            m.object = arm_copy
    if new.parent is not None and new.parent.type == "ARMATURE":
        mw = new.matrix_world.copy()
        new.parent = arm_copy
        new.matrix_world = mw
    return new


def _region(ob, region) -> np.ndarray:
    P = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    if isinstance(region, str):
        g = ob.vertex_groups.get(region)
        if g is None:
            raise C.FeatureError(f"no vertex group {region!r} on {ob.name}; the groups are {sorted(x.name for x in ob.vertex_groups)}")
        idx = sorted({v.index for v in ob.data.vertices for e in v.groups if e.group == g.index and e.weight > 0})
    elif isinstance(region, list) and len(region) == 2:
        lo, hi = np.array(region[0], float), np.array(region[1], float)
        idx = [int(i) for i in np.flatnonzero(np.all((P >= lo) & (P <= hi), axis=1))]
    else:
        raise C.FeatureError("region is a bounding box [[x, y, z], [x, y, z]] (world) or a vertex group name")
    if len(idx) < 4:
        raise C.FeatureError(f"the region holds {len(idx)} vertices of {ob.name}: give a region around the tail, hair, cape or coat geometry")
    return np.array(idx), P


def _capsule(name, r, length, coll):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=r)
    for v in bm.verts:
        if v.co.y > 1e-9:
            v.co.y += length
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.display_type = "WIRE"
    coll.objects.link(ob)
    return ob


def _colliders(arm, ob, region_idx, chain):
    names = {g.index: g.name for g in ob.vertex_groups}
    in_region = set(int(i) for i in region_idx)
    owned = {}
    for v in ob.data.vertices:
        if v.index in in_region or not v.groups:
            continue
        g = max(v.groups, key=lambda e: e.weight)
        owned.setdefault(names.get(g.group), []).append(ob.matrix_world @ v.co)
    cname = f"{arm.name}_colliders"
    coll = bpy.data.collections.get(cname) or bpy.data.collections.new(cname)
    if cname not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for o in list(coll.objects):
        bpy.data.objects.remove(o)
    out = []
    for b in arm.data.bones:
        if b.name in chain or not b.use_deform or b.name not in owned:
            continue
        h, t = arm.matrix_world @ b.head_local, arm.matrix_world @ b.tail_local
        ab = t - h
        r = 0.0
        for p in owned[b.name]:
            s = max(0.0, min(1.0, (p - h).dot(ab) / max(ab.length_squared, 1e-12)))
            r = max(r, (p - (h + ab * s)).length)
        r = r * 1.0001 + 1e-6
        proxy = _capsule(f"COL_{b.name}", r, ab.length, coll)
        proxy.parent, proxy.parent_type, proxy.parent_bone = arm, "BONE", b.name
        bpy.context.view_layer.update()
        proxy.matrix_world = arm.matrix_world @ b.matrix_local
        out.append({"bone": b.name, "radius_m": round(r, 6), "length_m": round(ab.length, 6), "proxy": proxy.name})
    return out


def secondary_chain_rig(object, armature, parent_bone, bones=4, naming="tail_", region=None, preview_constraint="damped_track", colliders=True):
    ob = C.need_object(object)
    arm = C.need_object(armature, "ARMATURE")
    n = int(bones)
    if n > MAX_BONES:
        raise C.FeatureError(f"{n} bones: at most {MAX_BONES} per chain; split into several chains")
    if n < 2:
        raise C.FeatureError("a chain has at least 2 bones")
    if parent_bone not in arm.data.bones:
        raise C.FeatureError(f"no bone {parent_bone!r} in {arm.name}; the bones are: {sorted(b.name for b in arm.data.bones)}")
    if not isinstance(naming, str) or not naming.endswith("_") or not naming[:-1].isalpha():
        raise C.FeatureError("naming is a prefix such as tail_, cape_ or hair_")
    if preview_constraint not in ("damped_track", "none"):
        raise C.FeatureError("preview_constraint is damped_track | none")
    if region is None:
        raise C.FeatureError("give the region the chain drives: a bounding box [[x, y, z], [x, y, z]] or a vertex group")
    audit = _w.audit(ob.name, arm.name)
    if not audit["pass"]:
        raise C.FeatureError(f"the base rig must pass weight_audit first ({ob.name} on {arm.name} fails): run lampway_weight_audit and fix it")
    idx, P = _region(ob, region)
    R = P[idx]
    c = R.mean(axis=0)
    w, V = np.linalg.eigh(np.cov((R - c).T))
    u = V[:, int(np.argmax(w))]
    t = (R - c) @ u
    ptail = np.array((arm.matrix_world @ arm.data.bones[parent_bone].tail_local)[:])
    a_end, b_end = c + u * t.min(), c + u * t.max()
    if np.linalg.norm(b_end - ptail) < np.linalg.norm(a_end - ptail):
        u, t = -u, -t
    t0, t1 = float(t.min()), float(t.max())
    joints = [Vector((c + u * (t0 + (t1 - t0) * k / n)).tolist()) for k in range(n + 1)]
    arm_c = _copy_armature(arm)
    ob_c = _copy_mesh(ob, arm_c)
    chain = [f"{naming}{k + 1:02d}" for k in range(n)]
    clash = [b for b in chain if b in arm_c.data.bones]
    if clash:
        raise C.FeatureError(f"the armature already has bones named {clash}: pick another naming")
    inv = arm_c.matrix_world.inverted()
    prev_active, prev_mode = bpy.context.view_layer.objects.active, arm_c.mode
    C.activate(arm_c)
    bpy.ops.object.mode_set(mode="EDIT")
    try:
        eb = arm_c.data.edit_bones
        last = eb[parent_bone]
        for k, name in enumerate(chain):
            b = eb.new(name)
            b.head, b.tail = inv @ joints[k], inv @ joints[k + 1]
            b.parent = last
            b.use_connect = k > 0
            b.use_deform = True
            last = b
    finally:
        bpy.ops.object.mode_set(mode="OBJECT")
        if prev_active is not None:
            bpy.context.view_layer.objects.active = prev_active
    # weights: control points at s = 0 (the parent) and s = k + 0.5 (chain bone k), linear between neighbours
    s = (t - t0) / max(t1 - t0, 1e-12) * n
    ctrl = [(0.0, parent_bone)] + [(k + 0.5, chain[k]) for k in range(n)]
    keep = set(chain) | {parent_bone}
    groups = {g.name: g for g in ob_c.vertex_groups}
    for name in chain:
        groups[name] = ob_c.vertex_groups.new(name=name)
    if parent_bone not in groups:
        groups[parent_bone] = ob_c.vertex_groups.new(name=parent_bone)
    removed = 0
    by_index = {g.index: g for g in ob_c.vertex_groups}
    for vi, sv in zip(idx, s):
        v = ob_c.data.vertices[int(vi)]
        for e in list(v.groups):
            g = by_index[e.group]
            if g.name not in keep:
                g.remove([int(vi)])
                removed += 1
            else:
                g.remove([int(vi)])
        j = next((k for k in range(len(ctrl) - 1) if ctrl[k][0] <= sv <= ctrl[k + 1][0]), None)
        if j is None:
            groups[chain[-1]].add([int(vi)], 1.0, "REPLACE")
            continue
        f = (sv - ctrl[j][0]) / max(ctrl[j + 1][0] - ctrl[j][0], 1e-12)
        if 1.0 - f > 1e-9:
            groups[ctrl[j][1]].add([int(vi)], float(1.0 - f), "REPLACE")
        if f > 1e-9:
            groups[ctrl[j + 1][1]].add([int(vi)], float(f), "REPLACE")
    cons = []
    if preview_constraint == "damped_track":
        for a, b in zip(chain, chain[1:]):
            con = arm_c.pose.bones[a].constraints.new("DAMPED_TRACK")
            con.target, con.subtarget, con.head_tail = arm_c, b, 1.0
            con.name = "lw_preview"
            cons.append({"bone": a, "type": "DAMPED_TRACK", "subtarget": b, "head_tail": 1.0})
    bpy.context.view_layer.update()
    cols = _colliders(arm_c, ob_c, idx, chain) if colliders else []
    return {"armature": arm_c.name, "object": ob_c.name, "chain": chain, "parent_bone": parent_bone, "axis": [round(float(x), 5) for x in u],
            "weights": {"vertices": int(len(idx)), "competing_removed": removed}, "colliders": cols, "preview_constraints": cons,
            "physics_notes": "numeric presets are not provided",
            "note": "a preview rig on copies: masses, damping and angular limits are tuned per appendage in the engine; test each joint in Pose Mode"}
