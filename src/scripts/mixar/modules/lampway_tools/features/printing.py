# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""print_check and print_prep: printability measured, and a physical-print derivative kept apart from the game assets (specs/wiki/print_check.md,
print_prep.md).

print_check (read-only, millimetres): manifold (no boundary and no non-manifold edge), self-intersections (face pairs that overlap in the BVH and share no
vertex), isolated triangles (faces with no neighbour), wall thickness (a ray from every face centre inward, along -normal: the distance to the next
surface; at most MAX_FACES faces are sampled), the overhang area fraction (faces whose normal points down within ``90 - overhang_deg`` of straight down,
not counting the faces on the build plate), floating parts (shells beyond the first) and whether the bounding box fits the printer (axis-aligned, any
order of axes). The units: ``units_per_mm`` or the scene's unit scale. The 3D-Print Toolbox extension is not required (a cross-check only).

print_prep: a COPY with modifiers applied (an armature is refused: pose it and apply first), an optional shared base unioned by Blender's exact boolean,
repaired (merge by distance, normals), decimated to max_faces, scaled so its height is target_height_mm and written in millimetres as STL per part under
out_dir; print_check gates it (walls thinner than min_wall_mm, an open shell: refused, nothing written). The copies are removed. No slicer code."""

import hashlib
import math
import os

import bmesh
import bpy
import numpy as np
from mathutils import Matrix
from mathutils.bvhtree import BVHTree

from . import common as C

MAX_FACES = 20000
PLATE_EPS_MM = 0.01


def _mm_per_unit(units_per_mm):
    if units_per_mm:
        return 1.0 / float(units_per_mm)
    return float(bpy.context.scene.unit_settings.scale_length) * 1000.0


def _world_bm(ob):
    bm = bmesh.new()
    dg = bpy.context.evaluated_depsgraph_get()
    bm.from_object(ob, dg)
    bm.transform(ob.matrix_world)
    bm.normal_update()
    bm.faces.ensure_lookup_table()
    return bm


def check_bm(bm, mm, min_wall_mm, overhang_deg=45.0, printer_volume_mm=None) -> dict:
    tree = BVHTree.FromBMesh(bm)
    non_manifold = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    isolated = sum(1 for f in bm.faces if all(len(e.link_faces) == 1 for e in f.edges))
    pairs = set()
    for a, b in tree.overlap(tree):
        if a < b and not ({v.index for v in bm.faces[a].verts} & {v.index for v in bm.faces[b].verts}):
            pairs.add((a, b))
    thin, n_thin = [], 0
    faces = bm.faces if len(bm.faces) <= MAX_FACES else [bm.faces[i] for i in np.linspace(0, len(bm.faces) - 1, MAX_FACES).astype(int)]
    for f in faces:
        c, n = f.calc_center_median(), f.normal
        if n.length < 1e-12:
            continue
        hit = tree.ray_cast(c - n * 1e-7, -n, (min_wall_mm / mm) * 1.0001)
        if hit[0] is not None and hit[2] != f.index:
            n_thin += 1
            thin.append({"face": f.index, "centre_mm": [round(x * mm, 3) for x in c], "thickness_mm": round(hit[3] * mm, 4)})
    thin.sort(key=lambda t: t["thickness_mm"])
    zmin = min((v.co.z for v in bm.verts), default=0.0)
    lim = math.sin(math.radians(float(overhang_deg)))
    total = over = 0.0
    for f in bm.faces:
        a = f.calc_area()
        total += a
        on_plate = all(abs(v.co.z - zmin) * mm <= PLATE_EPS_MM for v in f.verts)
        if not on_plate and -f.normal.z > lim:
            over += a
    seen, shells = set(), 0
    for v in bm.verts:
        if v.index in seen:
            continue
        shells += 1
        stack = [v]
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            stack.extend(e.other_vert(cur) for e in cur.link_edges)
    co = np.array([v.co[:] for v in bm.verts]) if bm.verts else np.zeros((1, 3))
    size = [round(float(x) * mm, 4) for x in (co.max(axis=0) - co.min(axis=0))]
    fits = None if not printer_volume_mm else all(s <= p for s, p in zip(sorted(size), sorted(float(x) for x in printer_volume_mm)))
    manifold = non_manifold == 0 and boundary == 0
    out = {"manifold": manifold, "non_manifold_edges": non_manifold, "open_boundary_edges": boundary, "intersections": len(pairs), "isolated_triangles": isolated,
           "thin": thin[:50], "thin_faces": n_thin, "min_wall_mm": float(min_wall_mm), "overhang_area_fraction": round(over / total, 4) if total else 0.0,
           "overhang_deg": float(overhang_deg), "floating_parts": max(0, shells - 1), "size_mm": size, "fits_volume": fits,
           "faces_sampled": len(faces), "faces": len(bm.faces)}
    out["pass"] = bool(manifold and not pairs and not isolated and not n_thin and shells <= 1 and fits is not False)
    return out


def print_check(object, min_wall_mm=None, overhang_deg=45.0, units_per_mm=None, printer_volume_mm=None):
    ob = C.need_object(object)
    if min_wall_mm is None or float(min_wall_mm) <= 0:
        raise C.FeatureError("min_wall_mm is required: the printer's minimum wall in millimetres")
    if not 30 <= float(overhang_deg) <= 80:
        raise C.FeatureError("overhang_deg is 30..80 (the printer's; 45 is a common default [UNVERIFIED])")
    bm = _world_bm(ob)
    try:
        return dict(check_bm(bm, _mm_per_unit(units_per_mm), float(min_wall_mm), overhang_deg, printer_volume_mm), object=ob.name)
    finally:
        bm.free()


def _armature(ob):
    return any(m.type == "ARMATURE" for m in ob.modifiers) or (ob.parent is not None and ob.parent.type == "ARMATURE")


def print_prep(root, object, target_height_mm, min_wall_mm=None, base=None, max_faces=1000000, out_dir="print", split=None, units="mm"):
    if min_wall_mm is None or float(min_wall_mm) <= 0:
        raise C.FeatureError("the wall limit is the printer's: give it (min_wall_mm)")
    if units != "mm":
        raise C.FeatureError("units is mm (STL coordinates are written in millimetres)")
    if not 5 <= float(target_height_mm) <= 500:
        raise C.FeatureError("target_height_mm is 5..500")
    if not 10000 <= int(max_faces) <= 5000000:
        raise C.FeatureError("max_faces is 10000..5000000 (1000000 is the video's example, not a slicer limit)")
    parts = [C.need_object(object)] + [C.need_object(s) for s in (split or [])]
    for ob in parts:
        if _armature(ob):
            raise C.FeatureError(f"{ob.name} has an armature: print derivatives are static: pose it first and apply")
    base_ob = C.need_object(base) if base else None
    mm0 = _mm_per_unit(None)
    bm = _world_bm(parts[0])
    height_units = max(v.co.z for v in bm.verts) - min(v.co.z for v in bm.verts)
    bm.free()
    if height_units <= 0:
        raise C.FeatureError(f"{object} has no height")
    factor = float(target_height_mm) / (height_units * mm0)                 # one scale for every part: they keep their relative sizes
    files, reports = [], []
    os.makedirs(out_dir, exist_ok=True)
    staged = []
    try:
        for i, ob in enumerate(parts):
            bm = _world_bm(ob)
            if base_ob is not None and i == 0:
                bb = _world_bm(base_ob)
                tmp = bpy.data.meshes.new("lw_print_base")
                bb.to_mesh(tmp)
                bb.free()
                staged.append(tmp)
                me = bpy.data.meshes.new("lw_print_union")
                bm.to_mesh(me)
                staged.append(me)
                a, b = bpy.data.objects.new("lw_print_a", me), bpy.data.objects.new("lw_print_b", tmp)
                bpy.context.scene.collection.objects.link(a)
                bpy.context.scene.collection.objects.link(b)
                staged += [a, b]
                mod = a.modifiers.new("lw_union", "BOOLEAN")
                mod.operation, mod.solver, mod.object = "UNION", "EXACT", b
                bm.free()
                bm = _world_bm(a)
            bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6 / max(mm0, 1e-12))
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
            if len(bm.faces) > int(max_faces):
                bmesh.ops.triangulate(bm, faces=bm.faces)
            bm.transform(Matrix.Scale(mm0 * factor, 4))                           # coordinates in millimetres from here on
            bm.normal_update()
            bm.faces.ensure_lookup_table()
            if len(bm.faces) > int(max_faces):
                me = bpy.data.meshes.new("lw_print_dec")
                bm.to_mesh(me)
                staged.append(me)
                o = bpy.data.objects.new("lw_print_dec", me)
                bpy.context.scene.collection.objects.link(o)
                staged.append(o)
                d = o.modifiers.new("lw_dec", "DECIMATE")
                d.ratio = int(max_faces) / len(bm.faces)
                bm.free()
                bm = _world_bm(o)
            rep = check_bm(bm, 1.0, float(min_wall_mm))
            reports.append(dict(rep, part=ob.name))
            if rep["open_boundary_edges"] or rep["non_manifold_edges"]:
                raise C.FeatureError(f"{ob.name}: not a closed manifold after repair ({rep['open_boundary_edges']} open and {rep['non_manifold_edges']} non-manifold edges): "
                                     "fill the holes first (mesh_prep, a remesh), nothing was written")
            if rep["thin_faces"]:
                w = rep["thin"][0]
                raise C.FeatureError(f"{ob.name}: walls thinner than min_wall_mm ({w['thickness_mm']} mm < {min_wall_mm} mm at {w['centre_mm']} mm, {rep['thin_faces']} faces) "
                                     "at this size: thicken them or print larger; nothing was written")
            me = bpy.data.meshes.new(f"lw_print_{ob.name}")
            bm.to_mesh(me)
            bm.free()
            o = bpy.data.objects.new(f"{ob.name}", me)
            staged += [me, o]
            files.append((o, os.path.join(out_dir, f"{ob.name}.stl")))
        for o, path in files:
            bpy.context.scene.collection.objects.link(o)
        written = []
        for o, path in files:
            for x in bpy.context.view_layer.objects:
                x.select_set(False)
            o.select_set(True)
            bpy.context.view_layer.objects.active = o
            bpy.ops.wm.stl_export(filepath=path, export_selected_objects=True, global_scale=1.0, use_scene_unit=False, apply_modifiers=True, ascii_format=False)
            z = [v.co.z for v in o.data.vertices]
            written.append({"part": o.name.split(".")[0], "path": os.path.relpath(path, root), "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest(),
                            "height_mm": round(max(z) - min(z), 4)})
    finally:
        for x in staged:
            try:
                if isinstance(x, bpy.types.Object):
                    bpy.data.objects.remove(x)
            except ReferenceError:
                pass
        for x in staged:
            try:
                if isinstance(x, bpy.types.Mesh) and x.users == 0:
                    bpy.data.meshes.remove(x)
            except ReferenceError:
                pass
    return {"files": written, "report": reports[0] if len(reports) == 1 else {"parts": reports, "pass": all(r["pass"] for r in reports)},
            "scale": {"from_height_mm": round(height_units * mm0, 4), "to_height_mm": float(target_height_mm), "factor": round(factor, 9)},
            "note": "a print derivative, separate from the game asset; slicer, supports and curing stay manual"}
