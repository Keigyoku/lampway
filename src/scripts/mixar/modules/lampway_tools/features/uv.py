# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""UV unwrap. Proven code: seams by dihedral angle, Blender's smart-project / angle-based / conformal solvers, the island
packer. The result is a NEW object ``<name>_uv`` (the original keeps its UVs) with a report measured on the result:
islands, coverage, overlap (rasterised), texel-density spread and the density actually achieved."""

import math

import bmesh
import bpy
import numpy as np

from . import common as C

METHODS = ("smart", "angle", "conformal")
GRID = 512


def _mode(ob, mode):
    C.activate(ob)
    bpy.ops.object.mode_set(mode=mode)


def _mark_seams(ob, angle_limit):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    limit = math.radians(angle_limit)
    count = 0
    for e in bm.edges:
        faces = e.link_faces
        seam = len(faces) != 2 or faces[0].normal.angle(faces[1].normal, 0.0) > limit
        e.seam = seam
        count += int(seam)
    bm.to_mesh(ob.data)
    bm.free()
    return count


def _uv_arrays(ob):
    me = ob.data
    me.calc_loop_triangles()
    uv = me.uv_layers.active
    n = len(me.loops)
    uvs = np.empty(n * 2, dtype=np.float64)
    uv.uv.foreach_get("vector", uvs)
    uvs = uvs.reshape(-1, 2)
    tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
    me.loop_triangles.foreach_get("loops", tris)
    return me, uvs, tris.reshape(-1, 3)


def uv_report(ob, texture_size=2048) -> dict:
    me, uvs, tris = _uv_arrays(ob)
    if not len(tris):
        return {"islands": 0, "coverage": 0.0, "overlap_fraction": 0.0, "texel_density_cv": 0.0}
    verts = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", verts)
    verts = verts.reshape(-1, 3)
    loop_vert = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loop_vert)
    p = verts[loop_vert[tris]]                                          # (T, 3, 3)
    area3 = 0.5 * np.linalg.norm(np.cross(p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]), axis=1)
    q = uvs[tris]                                                       # (T, 3, 2)
    area2 = 0.5 * np.abs((q[:, 1, 0] - q[:, 0, 0]) * (q[:, 2, 1] - q[:, 0, 1]) - (q[:, 2, 0] - q[:, 0, 0]) * (q[:, 1, 1] - q[:, 0, 1]))
    ok = area3 > 1e-12
    density = np.sqrt(area2[ok] / area3[ok])                            # uv units per metre
    mean_density = float(density.mean()) if ok.any() else 0.0
    cv = float(density.std() / mean_density) if mean_density > 0 else 0.0
    # islands: union-find over faces sharing an edge whose two loops carry the same UV on both ends
    parent = list(range(len(me.polygons)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    edge_loops = {}
    for poly in me.polygons:
        for li in range(poly.loop_start, poly.loop_start + poly.loop_total):
            nxt = poly.loop_start + (li - poly.loop_start + 1) % poly.loop_total
            a, b = int(loop_vert[li]), int(loop_vert[nxt])
            key = (min(a, b), max(a, b))
            edge_loops.setdefault(key, []).append((poly.index, li, nxt, a))
    for key, items in edge_loops.items():
        if len(items) != 2:
            continue
        (pa, la, na, va), (pb, lb, nb, vb) = items
        ua = {va: tuple(np.round(uvs[la], 5)), key[0] ^ key[1] ^ va: tuple(np.round(uvs[na], 5))}
        ub = {vb: tuple(np.round(uvs[lb], 5)), key[0] ^ key[1] ^ vb: tuple(np.round(uvs[nb], 5))}
        if ua == ub:
            parent[find(pa)] = find(pb)
    islands = len({find(i) for i in range(len(parent))})
    # coverage and overlap by rasterising every UV triangle into a GRIDxGRID counter
    grid = np.zeros((GRID, GRID), dtype=np.int32)
    for t in q:
        xs, ys = t[:, 0] * GRID, t[:, 1] * GRID
        x0, x1 = int(max(0, math.floor(xs.min()))), int(min(GRID - 1, math.ceil(xs.max())))
        y0, y1 = int(max(0, math.floor(ys.min()))), int(min(GRID - 1, math.ceil(ys.max())))
        if x1 < x0 or y1 < y0:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        d = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(d) < 1e-12:
            continue
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        inside = (w0 >= 0) & (w1 >= 0) & (w0 + w1 <= 1)
        grid[y0:y1 + 1, x0:x1 + 1] += inside
    covered = int((grid >= 1).sum())
    overlapped = int((grid >= 2).sum())
    return {"islands": islands, "coverage": round(covered / float(GRID * GRID), 4),
            "overlap_fraction": round(overlapped / covered, 4) if covered else 0.0,
            "texel_density_cv": round(cv, 4), "uv_per_metre": round(mean_density, 6),
            "achieved_texel_density": round(mean_density * texture_size, 2),
            "uv_min": [round(float(uvs[:, 0].min()), 4), round(float(uvs[:, 1].min()), 4)],
            "uv_max": [round(float(uvs[:, 0].max()), 4), round(float(uvs[:, 1].max()), 4)]}


def uv_unwrap(object, method="smart", angle_limit=66.0, margin=0.005, texel_density=None, texture_size=2048,
              engine="algorithmic"):
    if engine != "algorithmic":
        return C.studio_slot("uv", engine)
    if method not in METHODS:
        raise C.FeatureError(f"unknown method {method!r}; the methods are {', '.join(METHODS)}")
    src = C.need_object(object)
    new = C.duplicate(src, "_uv")
    for layer in list(new.data.uv_layers):
        new.data.uv_layers.remove(layer)
    new.data.uv_layers.new(name="UVMap")
    seams = 0
    if method == "smart":
        _mode(new, "EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(float(angle_limit)), island_margin=float(margin), correct_aspect=True)
        bpy.ops.object.mode_set(mode="OBJECT")
    else:
        seams = _mark_seams(new, float(angle_limit))
        _mode(new, "EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.unwrap(method="ANGLE_BASED" if method == "angle" else "CONFORMAL", margin=float(margin))
        bpy.ops.uv.select_all(action="SELECT")
        bpy.ops.uv.pack_islands(margin=float(margin))
        bpy.ops.object.mode_set(mode="OBJECT")
    new.data.update()
    report = uv_report(new, int(texture_size))
    report["seam_edges"] = seams
    out = {"object": new.name, "source": src.name, "method": method, "report": report}
    if texel_density:
        out["requested_texel_density"] = float(texel_density)
        out["note"] = ("the packer fits every island into 0..1, so the density achieved is what the island layout allows at "
                       f"{texture_size}px; raise texture_size or lower the request to match")
    return out
