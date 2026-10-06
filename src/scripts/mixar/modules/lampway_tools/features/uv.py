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
from .. import canon_geom as G

METHODS = ("smart", "angle", "conformal")
GRID = 1024                    # canon 13 B.2: the one raster resolution (the number Tripo's panel shows within ~1 point)
SIZES = (256, 512, 1024, 2048, 4096, 8192)
HIDE = {"+X": (1, 0, 0), "-X": (-1, 0, 0), "+Y": (0, 1, 0), "-Y": (0, -1, 0), "+Z": (0, 0, 1), "-Z": (0, 0, -1), "top": (0, 0, 1), "bottom": (0, 0, -1), "front": (0, -1, 0), "back": (0, 1, 0),
        "left": (-1, 0, 0), "right": (1, 0, 0)}                                  # the viewer's side: Blender's front view looks along +Y from -Y


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
    islands = int(_island_ids(me, uvs, loop_vert).max() + 1) if len(me.polygons) else 0
    grid = G.coverage(q, GRID)                                          # canon 13: the half-open raster, the one rule
    covered = int((grid >= 1).sum())
    overlapped = int((grid >= 2).sum())
    return {"islands": islands, "coverage": round(covered / float(GRID * GRID), 4),
            "overlap_fraction": round(overlapped / covered, 4) if covered else 0.0,
            "texel_density_cv": round(cv, 4), "uv_per_metre": round(mean_density, 6),
            "achieved_texel_density": round(mean_density * texture_size, 2),
            "uv_min": [round(float(uvs[:, 0].min()), 4), round(float(uvs[:, 1].min()), 4)],
            "uv_max": [round(float(uvs[:, 0].max()), 4), round(float(uvs[:, 1].max()), 4)]}


def _seams_by_rule(ob, rule, angle_limit):
    """Seams hidden from a direction, deterministic: every edge is scored by how visible it is from the viewer (the best dot of an adjacent face's world normal with the viewer direction); a minimum
    spanning cut of the vertex graph (Kruskal on the visibility, then the sharper dihedral first) opens a closed mesh into one disk through the least visible edges; along='sharp' also seams every sharp
    edge that is not visible. avoid_faces raise the score of their edges so cuts prefer to stay off them."""
    from mathutils import Vector
    hide = rule.get("hide_from")
    if hide not in HIDE:
        raise C.FeatureError(f"seam_rule.hide_from {hide!r} is not one of {list(HIDE)}")
    along = rule.get("along", "sharp")
    if along not in ("sharp", "panel_lines"):
        raise C.FeatureError("seam_rule.along is sharp | panel_lines")
    viewer = Vector(HIDE[hide])
    rot = ob.matrix_world.to_3x3()
    avoid = set(int(i) for i in rule.get("avoid_faces") or [])
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.edges.ensure_lookup_table()
    limit = math.radians(angle_limit)

    def vis(e):
        v = max(((rot @ f.normal).normalized().dot(viewer) for f in e.link_faces), default=1.0)
        return v + (2.0 if any(f.index in avoid for f in e.link_faces) else 0.0)

    def ang(e):
        return e.link_faces[0].normal.angle(e.link_faces[1].normal, 0.0) if len(e.link_faces) == 2 else math.pi
    scored = sorted(bm.edges, key=lambda e: (round(vis(e), 6), -ang(e), e.index))
    parent = list(range(len(bm.verts)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    seams = set()
    for e in scored:
        a, b = find(e.verts[0].index), find(e.verts[1].index)
        if a != b:
            parent[a] = b
            seams.add(e.index)
    if along == "sharp":
        for e in bm.edges:
            if len(e.link_faces) == 2 and ang(e) > limit and vis(e) <= 1e-6:
                seams.add(e.index)
    visible = 0
    for e in bm.edges:
        e.seam = e.index in seams
        visible += int(e.seam and vis(e) > 0.01)
    bm.to_mesh(ob.data)
    bm.free()
    return len(seams), visible


def worst_stretch(ob) -> dict:
    """Per-triangle stretch of the UV map from the singular values of the UV Jacobian (J = [uv edges] x [3D edges in the triangle's own plane]^-1): angle = the largest s1 / s2 (conformal distortion),
    area = the largest deviation of s1 * s2 from the mean (>= 1). Reports the worst triangle's polygon, island and world location, so it can be clicked."""
    me, uvs, tris = _uv_arrays(ob)
    verts = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", verts)
    verts = verts.reshape(-1, 3)
    loop_vert = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loop_vert)
    p = verts[loop_vert[tris]]
    q = uvs[tris]
    e1, e2 = p[:, 1] - p[:, 0], p[:, 2] - p[:, 0]
    x = e1 / np.maximum(np.linalg.norm(e1, axis=1, keepdims=True), 1e-18)
    nrm = np.cross(e1, e2)
    y = np.cross(nrm, x)
    y = y / np.maximum(np.linalg.norm(y, axis=1, keepdims=True), 1e-18)
    B = np.stack([np.stack([(e1 * x).sum(1), (e2 * x).sum(1)], axis=1), np.stack([(e1 * y).sum(1), (e2 * y).sum(1)], axis=1)], axis=1)      # (T, 2, 2): columns are the 3D edges in plane coords
    U = np.stack([q[:, 1] - q[:, 0], q[:, 2] - q[:, 0]], axis=2)                                                                         # (T, 2, 2): columns are the UV edges
    det = B[:, 0, 0] * B[:, 1, 1] - B[:, 0, 1] * B[:, 1, 0]
    ok = np.abs(det) > 1e-18
    inv = np.zeros_like(B)
    inv[ok, 0, 0], inv[ok, 1, 1] = B[ok, 1, 1] / det[ok], B[ok, 0, 0] / det[ok]
    inv[ok, 0, 1], inv[ok, 1, 0] = -B[ok, 0, 1] / det[ok], -B[ok, 1, 0] / det[ok]
    J = U @ inv
    sv = np.linalg.svd(J, compute_uv=False)
    s1, s2 = sv[:, 0], np.maximum(sv[:, 1], 1e-12)
    angle = np.where(ok, s1 / s2, 1.0)
    dens = s1 * s2
    mean = float(dens[ok].mean()) if ok.any() else 1.0
    r = np.where(ok, dens / max(mean, 1e-18), 1.0)
    area = np.maximum(r, 1.0 / np.maximum(r, 1e-12))
    worst = int(np.argmax(np.where(ok, angle, 0)))
    poly = int(me.loop_triangles[worst].polygon_index)
    loc = ob.matrix_world @ __import__("mathutils").Vector(p[worst].mean(axis=0).tolist())
    return {"angle": round(float(angle.max()), 6), "area": round(float(area.max()), 6), "face": poly, "island": int(_island_ids(me, uvs, loop_vert)[poly]), "location": [round(float(c), 5) for c in loc]}


def _island_ids(me, uvs, loop_vert):
    """Per polygon its island: canon 13's one definition (canon_geom.uv_island_ids) - faces joined by a corner with the same (vertex,
    UV rounded to 6 places), as lampway_uv_score measures."""
    F = [[int(loop_vert[li]) for li in range(p.loop_start, p.loop_start + p.loop_total)] for p in me.polygons]
    FUV = [list(range(p.loop_start, p.loop_start + p.loop_total)) for p in me.polygons]
    return G.uv_island_ids(F, FUV, uvs)


def _checker(new):
    img = bpy.data.images.new("lw_uv_checker", 1024, 1024)
    img.generated_type = "UV_GRID"
    mat = bpy.data.materials.new("lw_checker_" + new.name)
    mat.use_nodes = True
    nt = mat.node_tree
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    nt.links.new(tex.outputs["Color"], nt.nodes["Principled BSDF"].inputs["Base Color"])
    new.data.materials.clear()
    new.data.materials.append(mat)
    return mat.name


def uv_unwrap(object, method="smart", angle_limit=66.0, margin=None, texel_density=None, texture_size=2048,
              engine="algorithmic", margin_px=None, seam_rule=None, checker=False):
    if engine != "algorithmic":
        return C.studio_slot("uv", engine)
    if method not in METHODS:
        raise C.FeatureError(f"unknown method {method!r}; the methods are {', '.join(METHODS)}")
    if int(texture_size) not in SIZES:
        raise C.FeatureError(f"texture_size is a power of two from 256 to 8192, not {texture_size}")
    if margin is None:                                                              # 1 px of margin per 256 px of map: 4 at 1K, 8 at 2K, 16 at 4K
        margin_px = int(margin_px) if margin_px is not None else int(texture_size) // 256
        margin = margin_px / int(texture_size)
    else:
        margin_px = round(float(margin) * int(texture_size), 2)
    src = C.need_object(object)
    sc = np.array(src.scale)
    if sc.max() / max(sc.min(), 1e-12) > 1 + 1e-3 and not np.allclose(sc, sc[0]):
        raise C.FeatureError(f"{src.name} has an unapplied non-uniform scale {tuple(round(x, 3) for x in src.scale)}: apply scale first (lampway_scene_cleanup)")
    note_method = ""
    if seam_rule and method == "smart":
        method, note_method = "angle", "seam_rule needs seams, which smart project ignores: the angle-based solver was used"
    new = C.duplicate(src, "_uv")
    for layer in list(new.data.uv_layers):
        new.data.uv_layers.remove(layer)
    new.data.uv_layers.new(name="UVMap")
    seams, rule_info = 0, None
    if method == "smart":
        _mode(new, "EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(float(angle_limit)), island_margin=float(margin), correct_aspect=True)
        bpy.ops.object.mode_set(mode="OBJECT")
    else:
        if seam_rule:
            seams, visible = _seams_by_rule(new, dict(seam_rule), float(angle_limit))
            rule_info = {"hide_from": seam_rule.get("hide_from"), "along": seam_rule.get("along", "sharp"), "visible_seam_edges": visible}
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
    if texel_density:
        want, got = float(texel_density), report["achieved_texel_density"]
        fit_limit = got / max(max(report["uv_max"]), 1e-9)                          # the densest layout that still fits the 0..1 square
        if want > fit_limit * 1.0001:
            data = new.data
            bpy.data.objects.remove(new)
            bpy.data.meshes.remove(data)
            raise C.FeatureError(f"the requested texel density {want:g} texels per metre cannot fit at {texture_size} px: the layout allows at most {fit_limit:.1f}: raise texture_size or lower texel_density")
        me, uvs, _tris = _uv_arrays(new)
        uvs *= want / got                                                           # one uniform scale of the whole layout keeps every island's relative size
        new.data.uv_layers.active.uv.foreach_set("vector", uvs.ravel())
        new.data.update()
        report = uv_report(new, int(texture_size))
    report["seam_edges"] = seams
    if rule_info:
        report["seam_rule"] = rule_info
    report["worst_stretch"] = worst_stretch(new)
    out = {"object": new.name, "source": src.name, "method": method, "report": report, "margin_used": margin, "margin_px_used": margin_px}
    if note_method:
        out["note"] = note_method
    if texel_density:
        out["requested_texel_density"] = float(texel_density)
    if checker:
        out["checker_material"] = _checker(new)
    return out
