# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""splat_world (the import half) and splat_collision_proxy (specs/mixar_docs/splat_world.md, specs/wiki/splat_collision_proxy.md).

Import: an SPZ goes through the Client's own pure-Python decoder (moodboard ``world_labs_spz.spz_to_ply``, GPL, in tree) to a 3DGS PLY beside it, then
``splat_import`` makes the point object; a PLY is imported as is. Generation is the server's (``lampway_splat_world``: a world model, a spend).

Collision proxy: "visually dense splats do not imply physics surfaces". The splat's points whose opacity is at least ``min_opacity`` are binned into a
voxel grid; a voxel with at least ``min_density`` of them is solid; the surface is the faces between solid and empty voxels, voxel-remeshed at half a voxel (closed and manifold), in a new collection ``<splat>_collision`` as ``<splat>_collision`` or, for Unreal, ``UCX_<splat>`` (the static-mesh collision prefix). The grid is
refused above MAX_VOXELS. Nothing of the splat changes."""

import os

import bmesh
import bpy
import numpy as np

from . import common as C
from . import splat as _splat

MAX_VOXELS = 50_000_000
_FACES = ((0, (-1, 0, 0)), (0, (1, 0, 0)), (1, (0, -1, 0)), (1, (0, 1, 0)), (2, (0, 0, -1)), (2, (0, 0, 1)))


def splat_world_import(root, path, max_points=200000, name="lw_world", resolve=None):
    full = resolve(path)
    if not os.path.isfile(full):
        raise C.FeatureError(f"{path} is not a file")
    ext = os.path.splitext(full)[1].lower()
    if ext == ".spz":
        from mixar.modules.moodboard.core.world_labs_spz import spz_to_ply
        ply = os.path.splitext(full)[0] + ".ply"
        with open(full, "rb") as fh:
            data = spz_to_ply(fh.read())
        with open(ply, "wb") as fh:
            fh.write(data)
        out = _splat.splat_import(ply, max_points, name)
        out["converted_from"] = os.path.relpath(full, root)
        out["ply"] = os.path.relpath(ply, root)
        return out
    if ext == ".ply":
        return _splat.splat_import(full, max_points, name)
    raise C.FeatureError(f"{path}: a splat is .spz or 3DGS .ply")


def _splat_object(name):
    ob = C.need_object(name, "")
    if ob.type != "MESH" or "splat_opacity" not in ob.data.attributes:
        raise C.FeatureError(f"{name} has no splat_opacity attribute: not an imported splat (splat_import or splat_world import first)")
    return ob


def splat_collision_proxy(object, voxel_m=0.1, min_opacity=0.5, min_density=8, name=None, export_for_ue=False, max_voxels=MAX_VOXELS):
    ob = _splat_object(object)
    if not 0.0 <= float(min_opacity) <= 1.0:
        raise C.FeatureError("min_opacity is 0..1")
    if not 0.02 <= float(voxel_m) <= 1.0:
        raise C.FeatureError("voxel_m is 0.02..1.0")
    if int(min_density) < 1:
        raise C.FeatureError("min_density is at least 1 point per voxel")
    cap = min(int(max_voxels), MAX_VOXELS)
    me = ob.data
    n = len(me.vertices)
    co = np.empty(n * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    m = np.array(ob.matrix_world)
    co = (m[:3, :3] @ co.T).T + m[:3, 3]
    op = np.empty(n, dtype=np.float64)
    me.attributes["splat_opacity"].data.foreach_get("value", op)
    keep = op >= float(min_opacity)
    if not keep.any():
        raise C.FeatureError(f"no point reaches min_opacity {min_opacity}: lower it")
    pts = co[keep]
    v = float(voxel_m)
    lo = pts.min(axis=0) - v
    dims = np.floor((pts.max(axis=0) + v - lo) / v).astype(np.int64) + 1
    if int(np.prod(dims)) > cap:
        raise C.FeatureError(f"{int(np.prod(dims)):,} voxels at {v} m (cap {cap:,}): raise voxel_m")
    idx = np.floor((pts - lo) / v).astype(np.int64)
    flat = np.ravel_multi_index(idx.T, dims)
    counts = np.bincount(flat, minlength=int(np.prod(dims))).reshape(dims)
    solid = counts >= int(min_density)
    mass_in = float(op[keep][solid.reshape(-1)[flat]].sum())
    coverage = mass_in / max(float(op.sum()), 1e-12)
    bm = bmesh.new()
    verts = {}

    def vert(i, j, k):
        key = (i, j, k)
        if key not in verts:
            verts[key] = bm.verts.new((lo[0] + i * v, lo[1] + j * v, lo[2] + k * v))
        return verts[key]

    for axis, d in _FACES:
        nb = np.zeros_like(solid)
        sl_dst, sl_src = [slice(None)] * 3, [slice(None)] * 3
        step = d[axis]
        if step < 0:
            sl_dst[axis], sl_src[axis] = slice(1, None), slice(None, -1)
        else:
            sl_dst[axis], sl_src[axis] = slice(None, -1), slice(1, None)
        nb[tuple(sl_dst)] = solid[tuple(sl_src)]
        exposed = solid & ~nb
        for i, j, k in zip(*np.nonzero(exposed)):
            c = [i, j, k]
            o = c[axis] + (1 if step > 0 else 0)
            a, b = [x for x in range(3) if x != axis]
            corners = []
            for da, db in ((0, 0), (1, 0), (1, 1), (0, 1)):
                p = [0, 0, 0]
                p[axis], p[a], p[b] = o, c[a] + da, c[b] + db
                corners.append(vert(*p))
            bm.faces.new(corners)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    oname = f"UCX_{ob.name}" if export_for_ue else (name or f"{ob.name}_collision")
    for old in [o for o in bpy.data.objects if o.name == oname]:
        if not old.get("lw_collision_of"):
            raise C.FeatureError(f"an object named {oname!r} exists and is not a collision proxy: rename it first")
        bpy.data.objects.remove(old)
    blocky = bpy.data.meshes.new(oname + "_blocks")
    bm.to_mesh(blocky)
    bm.free()
    proxy = bpy.data.objects.new(oname, blocky)
    bpy.context.scene.collection.objects.link(proxy)
    rem = proxy.modifiers.new("lw_remesh", "REMESH")                   # a voxel remesh of the blocks: closed and manifold where two voxels touch only at an edge
    rem.mode, rem.voxel_size, rem.adaptivity = "VOXEL", v * 0.5, 0.0
    dg = bpy.context.evaluated_depsgraph_get()
    mesh = bpy.data.meshes.new_from_object(proxy.evaluated_get(dg), depsgraph=dg)
    mesh.name = oname
    proxy.modifiers.remove(rem)
    proxy.data = mesh
    bpy.data.meshes.remove(blocky)
    bpy.context.scene.collection.objects.unlink(proxy)
    cbm = bmesh.new()
    cbm.from_mesh(mesh)
    boundary = sum(1 for e in cbm.edges if len(e.link_faces) == 1)
    non_manifold = sum(1 for e in cbm.edges if len(e.link_faces) > 2)
    cbm.free()
    proxy["lw_collision_of"] = ob.name
    cname = f"{ob.name}_collision"
    coll = bpy.data.collections.get(cname) or bpy.data.collections.new(cname)
    if cname not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    coll.objects.link(proxy)
    proxy.display_type = "WIRE"
    hi = lo + dims * v
    return {"object": proxy.name, "collection": cname, "faces": len(mesh.polygons), "manifold": boundary == 0 and non_manifold == 0,
            "solid_voxels": int(solid.sum()), "voxel_m": v, "bounds": [[round(float(x), 4) for x in lo], [round(float(x), 4) for x in hi]],
            "coverage_of_splat_mass": round(coverage, 4), "note": "check floors and doorways with traversal_check on this collection"}
