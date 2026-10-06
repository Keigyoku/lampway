# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_join_boolean (specs/wiki/mesh_join_boolean.md): fuse, cut and connect parts, always on COPIES (the originals are kept).

join_remesh  the parts joined in world space, then a voxel remesh (Remesh modifier, applied): joining alone does not fuse surfaces. voxel_m 'coarse_first'
             remeshes at 4x the fine voxel first (the coarse result is reported), then at the fine voxel (the bounding diagonal / 100)
union        objects[0] + every other object, exact Boolean
difference   objects[0] - every other object, each cutter first INFLATED by clearance_mm (every vertex moved so each adjacent face plane moves out by the
             clearance: a box grows by exactly 2 x clearance)
connector    plug_socket | pin: a cylinder of size_mm diameter, 2 x size long, centred at ``at`` along ``axis`` (default +Z): united with objects[0] (the plug),
             and the same cylinder inflated by clearance_mm subtracted from objects[1] (the socket); the fit gap is MEASURED (plug surface to socket wall)
Every Boolean input must be closed (no open edges); a skinned mesh is never remeshed (the weights would be lost: bind afterwards)."""

import math

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import common as C

OPS = ("join_remesh", "union", "difference", "connector")


def _skinned(ob):
    return any(m.type == "ARMATURE" for m in ob.modifiers) or (ob.parent is not None and ob.parent.type == "ARMATURE")


def _world_bm(objs):
    bm = bmesh.new()
    for o in objs:
        tmp = bmesh.new()
        tmp.from_mesh(o.data)
        tmp.transform(o.matrix_world)
        me = bpy.data.meshes.new("lw_tmp")
        tmp.to_mesh(me)
        tmp.free()
        bm.from_mesh(me)
        bpy.data.meshes.remove(me)
    return bm


def _new_object(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.view_layer.update()
    return ob


def _apply(ob, mod):
    """Apply a modifier by evaluating the object (headless-safe) and swapping in the result."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg))
    old = ob.data
    ob.modifiers.remove(mod)
    ob.data = me
    if old.users == 0:
        bpy.data.meshes.remove(old)
    bpy.context.view_layer.update()


def _report(ob):
    rep = C.mesh_report(ob)
    return {"faces": rep["faces"], "shells": rep["shells"], "manifold": rep["non_manifold_edges"] == 0 and rep["open_boundary_edges"] == 0,
            "open_edges": rep["open_boundary_edges"]}


def _remesh(ob, voxel):
    m = ob.modifiers.new("lw_remesh", "REMESH")
    m.mode, m.voxel_size = "VOXEL", float(voxel)
    _apply(ob, m)


def _boolean(target, cutter, operation):
    m = target.modifiers.new("lw_bool", "BOOLEAN")
    m.operation, m.solver, m.object = operation, "EXACT", cutter
    cutter.hide_render = True
    _apply(target, m)


def _inflate(ob, c):
    """Move every vertex so each adjacent face plane moves out by ``c`` (a least-squares solve per vertex)."""
    if c == 0:
        return
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    for v in bm.verts:
        N = np.array([f.normal[:] for f in v.link_faces])
        if not len(N):
            continue
        off, *_ = np.linalg.lstsq(N, np.full(len(N), c), rcond=None)
        v.co += Vector(off)
    bm.to_mesh(ob.data)
    bm.free()
    ob.data.update()


def _cylinder(name, at, axis, radius, length, segments=64):
    bm = bmesh.new()
    rot = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized()).to_matrix().to_4x4()
    bmesh.ops.create_cone(bm, cap_ends=True, cap_tris=False, segments=segments, radius1=radius, radius2=radius, depth=length, matrix=Matrix.Translation(Vector(at)) @ rot)
    return _new_object(name, bm)


def _closed(objs):
    for o in objs:
        rep = C.mesh_report(o)
        if rep["open_boundary_edges"]:
            raise C.FeatureError(f"{o.name} has {rep['open_boundary_edges']} open edges: a Boolean needs closed meshes (cap them first: mesh_region_extract cap or fill holes)")


def _copy(ob, suffix):
    new = C.duplicate(ob, suffix)
    new.data.transform(new.matrix_world)
    new.matrix_world = Matrix.Identity(4)
    return new


def run(op, objects, voxel_m="coarse_first", clearance_mm=None, connector=None, name=""):
    if op not in OPS:
        raise C.FeatureError("op is " + " | ".join(OPS))
    objs = [C.need_object(n) for n in (objects or [])]
    if len(objs) < 2:
        raise C.FeatureError("objects names at least two meshes")
    clear = None if clearance_mm is None else float(clearance_mm)
    if clear is not None and not 0.0 <= clear <= 2.0:
        raise C.FeatureError("clearance_mm is 0..2 (a printer / paint tolerance)")
    if op == "join_remesh":
        sk = [o.name for o in objs if _skinned(o)]
        if sk:
            raise C.FeatureError(f"{sk[0]} is skinned: remesh destroys weights; bind afterwards")
        ob = _new_object(name or objs[0].name + "_joined", _world_bm(objs))
        diag = float(np.linalg.norm(np.array(ob.dimensions)))
        if voxel_m == "coarse_first":
            fine = diag / 100.0
            coarse_ob = _new_object(ob.name + "_coarse", _world_bm(objs))
            _remesh(coarse_ob, fine * 4)
            coarse = {"voxel_m": round(fine * 4, 6), **_report(coarse_ob)}
            me = coarse_ob.data
            bpy.data.objects.remove(coarse_ob)
            bpy.data.meshes.remove(me)
        else:
            fine, coarse = float(voxel_m), None
            if not 1e-5 <= fine <= diag:
                raise C.FeatureError("voxel_m is a positive size smaller than the parts, or 'coarse_first'")
        _remesh(ob, fine)
        return {"op": op, "object": ob.name, "voxel_m": round(fine, 6), "coarse": coarse, **_report(ob)}
    _closed(objs)
    if op in ("union", "difference"):
        if op == "difference" and clear is None:
            raise C.FeatureError("difference needs clearance_mm (0 for an exact cut): the cutter is enlarged by it")
        base = _copy(objs[0], "_" + op)
        if name:
            base.name = name
        cutters = []
        for o in objs[1:]:
            cut = _copy(o, "_cutter")
            if op == "difference":
                _inflate(cut, clear / 1000.0)
            _boolean(base, cut, "UNION" if op == "union" else "DIFFERENCE")
            cutters.append(cut)
        for cut in cutters:
            me = cut.data
            bpy.data.objects.remove(cut)
            bpy.data.meshes.remove(me)
        return {"op": op, "object": base.name, "clearance_mm": clear, **_report(base)}
    # connector
    spec = dict(connector or {})
    if clear is None:
        raise C.FeatureError("clearance is a printer/paint tolerance: give it (clearance_mm, e.g. 0.35 measured on the user's printer)")
    if spec.get("kind", "plug_socket") not in ("plug_socket", "pin"):
        raise C.FeatureError("connector.kind is plug_socket | pin (dovetail is not built)")
    at = [float(v) for v in spec.get("at") or []]
    if len(at) != 3:
        raise C.FeatureError("connector.at is the [x, y, z] the connector is centred on (the joint plane)")
    size = float(spec.get("size_mm") or 0) / 1000.0
    if size <= 0:
        raise C.FeatureError("connector.size_mm is the plug diameter in millimetres")
    axis = spec.get("axis") or [0, 0, 1]
    r, length, c = size / 2, size * 2, clear / 1000.0
    plug_obj = _copy(objs[0], "_plug")
    sock_obj = _copy(objs[1], "_socket")
    plug = _cylinder("lw_plug", at, axis, r, length)
    sock = _cylinder("lw_socket_cutter", Vector(at) + Vector(axis).normalized() * (c / 2), axis, r + c, length + c)
    _boolean(sock_obj, sock, "DIFFERENCE")
    # the gap: plug wall vertices in the socket half, away from both ends, to the socket's surface
    n = Vector(axis).normalized()
    tree = BVHTree.FromPolygons([v.co.copy() for v in sock_obj.data.vertices], [tuple(p.vertices) for p in sock_obj.data.polygons])
    d = []
    for v in plug.data.vertices:                                           # the wall's corner lines, sampled along the socket half of the plug
        t = (v.co - Vector(at)).dot(n)
        rad = v.co - Vector(at) - n * t
        if abs(rad.length - r) > 1e-6 or t > 0:
            continue
        for k in range(1, 4):
            p = Vector(at) + rad + n * (length * (0.1 + 0.1 * k))
            hit = tree.find_nearest(p)
            if hit[0] is not None:
                d.append(hit[3])
    gap_mm = float(np.median(d)) * 1000.0 if d else None
    _boolean(plug_obj, plug, "UNION")
    for o in (plug, sock):
        me = o.data
        bpy.data.objects.remove(o)
        bpy.data.meshes.remove(me)
    return {"op": op, "kind": spec.get("kind", "plug_socket"), "plug_object": plug_obj.name, "socket_object": sock_obj.name, "clearance_mm": clear,
            "gap_mm_measured": None if gap_mm is None else round(gap_mm, 4), "gap_samples": len(d), "plug": _report(plug_obj), "socket": _report(sock_obj),
            "object": plug_obj.name, "faces": _report(plug_obj)["faces"], "manifold": _report(plug_obj)["manifold"] and _report(sock_obj)["manifold"]}
