# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Retopology. Proven code: Blender's QuadriFlow (all-quad, field-aligned), voxel remesh as the fallback; the result is a NEW
object ``<name>_retopo`` and the original is never touched (the docs: keep it until the replacement passes your checks)."""

import math

import bpy
import bmesh

from . import common as C


def _surface_area(ob) -> float:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    area = sum(f.calc_area() for f in bm.faces)
    bm.free()
    return area


def retopo(object, target_faces=2000, method="quadriflow", engine="algorithmic", symmetry=False, keep_original_visible=True):
    if engine != "algorithmic":
        return C.studio_slot("retopo", engine)
    if method not in ("quadriflow", "voxel"):
        raise C.FeatureError(f"unknown method {method!r}; the methods are quadriflow and voxel")
    target_faces = int(target_faces)
    if target_faces < 50:
        raise C.FeatureError(f"target_faces {target_faces} is too small (at least 50)")
    src = C.need_object(object)
    new = C.duplicate(src, "_retopo")
    used = method
    if method == "quadriflow":
        C.activate(new)
        try:
            bpy.ops.object.quadriflow_remesh(mode="FACES", target_faces=target_faces, use_mesh_symmetry=bool(symmetry),
                                             use_preserve_sharp=False, use_preserve_boundary=True, seed=0)
        except RuntimeError:
            used = "voxel"                                   # QuadriFlow refuses a non-manifold input: the voxel remesh does not
    if used == "voxel":
        size = math.sqrt(max(_surface_area(new), 1e-12) / target_faces)
        new.data.remesh_voxel_size = size
        new.data.remesh_voxel_adaptivity = 0.0
        C.activate(new)
        bpy.ops.object.voxel_remesh()
        new.data.update()
    bpy.context.view_layer.update()
    if not keep_original_visible:
        src.hide_set(True)
    return {"object": new.name, "source": src.name, "method": used, "requested_method": method, "target_faces": target_faces,
            "report": C.mesh_report(new, ref=src), "source_faces": len(src.data.polygons)}
