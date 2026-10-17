# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Mesh segmentation. Proven code: connected shells, region growing across smooth edges (dihedral angle) and UV islands; regions
under ``min_faces`` merge into the neighbour they share the longest border with. The parts are real mesh objects in the
collection ``<name>_parts`` (UVs and materials kept); the original is hidden, never deleted. The slot for a part-detection model
(Tripo Segment, P3-SAM) is the same tool with engine="studio:tripo"."""

import math

import bmesh
import bpy

from . import common as C

METHODS = ("shells", "sharp", "uv_islands")


def _labels(bm, method, angle, uv_layer, budget=None):
    """face index -> region label, by flood fill across the edges the method lets through."""
    check = budget.check if budget else lambda: None
    limit = math.radians(angle)
    label = {}
    next_label = 0
    for seed in bm.faces:
        check()
        if seed.index in label:
            continue
        label[seed.index] = next_label
        stack = [seed]
        while stack:
            check()
            f = stack.pop()
            for e in f.edges:
                for g in e.link_faces:
                    if g is f or g.index in label:
                        continue
                    if method == "sharp" and f.normal.angle(g.normal, 0.0) > limit:
                        continue
                    if method == "uv_islands" and not _uv_connected(e, f, g, uv_layer):
                        continue
                    label[g.index] = next_label
                    stack.append(g)
        next_label += 1
    return label


def _uv_connected(edge, f, g, uv_layer) -> bool:
    ends = (edge.verts[0], edge.verts[1])
    for v in ends:
        lf = next(loop for loop in f.loops if loop.vert is v)
        lg = next(loop for loop in g.loops if loop.vert is v)
        if (lf[uv_layer].uv - lg[uv_layer].uv).length > 1e-5:
            return False
    return True


def _gather_isolated(label, min_faces):
    """Regions still under ``min_faces`` after merging have no neighbour (isolated shells): they become ONE remainder region."""
    counts = {}
    for lab in label.values():
        counts[lab] = counts.get(lab, 0) + 1
    small = {lab for lab, n in counts.items() if n < min_faces}
    if len(small) > 1:
        target = min(small)
        for k, v in label.items():
            if v in small:
                label[k] = target


def _merge_small(bm, label, min_faces):
    """Merge every region below ``min_faces`` into the neighbouring region it shares the most edges with (repeat until stable)."""
    while True:
        counts = {}
        for lab in label.values():
            counts[lab] = counts.get(lab, 0) + 1
        small = [lab for lab, n in counts.items() if n < min_faces]
        if not small or len(counts) == 1:
            return
        moved = False
        for lab in sorted(small, key=lambda l: counts[l]):
            border = {}
            for f in bm.faces:
                if label[f.index] != lab:
                    continue
                for e in f.edges:
                    for g in e.link_faces:
                        if label[g.index] != lab:
                            border[label[g.index]] = border.get(label[g.index], 0) + 1
            if border:
                target = max(border, key=border.get)
                for k, v in label.items():
                    if v == lab:
                        label[k] = target
                moved = True
                break
        if not moved:
            return                                      # an isolated small shell has no neighbour: it stays a part


MAX_PARTS = 200          # audit F15: ~900 shells became ~900 objects in 52 s and slowed every later tool


def segment_mesh(object, method="shells", angle=40.0, min_faces=1, engine="algorithmic", hide_original=True, max_parts=MAX_PARTS):
    if engine != "algorithmic":
        return C.studio_slot("segment", engine)
    if method not in METHODS:
        raise C.FeatureError(f"unknown method {method!r}; the methods are {', '.join(METHODS)}")
    src = C.need_object(object)
    if method == "uv_islands" and not src.data.uv_layers:
        raise C.FeatureError(f"{object!r} has no UV layer: unwrap it first (lampway_uv_unwrap) or pick another method")
    bm = bmesh.new()
    bm.from_mesh(src.data)
    bm.faces.ensure_lookup_table()
    uv_layer = bm.loops.layers.uv.active if method == "uv_islands" else None
    label = _labels(bm, method, float(angle), uv_layer)
    if int(min_faces) > 1:
        _merge_small(bm, label, int(min_faces))
        _gather_isolated(label, int(min_faces))
    bm.free()
    groups = {}
    for fi, lab in label.items():
        groups.setdefault(lab, []).append(fi)
    ordered = sorted(groups.values(), key=len, reverse=True)
    if len(ordered) > int(max_parts):                  # refused before any object is made
        keep = len(ordered[int(max_parts) - 2]) if int(max_parts) >= 2 else len(ordered[0])
        raise C.FeatureError(f"{len(ordered)} parts is more than max_parts={int(max_parts)}: gather the small ones with min_faces={keep} "
                             f"(regions under it merge into a neighbour, isolated ones into one remainder part), weld a seam-split import "
                             f"first (lampway_normalize_mesh), or raise max_parts")
    coll = bpy.data.collections.get(f"{src.name}_parts") or bpy.data.collections.new(f"{src.name}_parts")
    if coll.name not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    parts = []
    for k, face_ids in enumerate(ordered):
        keep = set(face_ids)
        pbm = bmesh.new()
        pbm.from_mesh(src.data)
        pbm.faces.ensure_lookup_table()
        drop = [f for f in pbm.faces if f.index not in keep]
        bmesh.ops.delete(pbm, geom=drop, context="FACES")
        for v in [v for v in pbm.verts if not v.link_faces]:
            pbm.verts.remove(v)
        area = sum(f.calc_area() for f in pbm.faces)
        me = bpy.data.meshes.new(f"{src.name}_part_{k}")
        pbm.to_mesh(me)
        pbm.free()
        me.materials.clear()
        for m in src.data.materials:
            me.materials.append(m)
        ob = bpy.data.objects.new(me.name, me)
        ob.matrix_world = src.matrix_world
        ob["lw_segment"] = k
        coll.objects.link(ob)
        bpy.context.view_layer.update()
        corners = [ob.matrix_world @ v.co for v in me.vertices]
        lo = [min(c[i] for c in corners) for i in range(3)]
        hi = [max(c[i] for c in corners) for i in range(3)]
        parts.append({"object": ob.name, "faces": len(face_ids), "area": round(area, 6),
                      "center": [round((a + b) / 2, 4) for a, b in zip(lo, hi)], "size": [round(b - a, 4) for a, b in zip(lo, hi)]})
    if hide_original:
        src.hide_set(True)
    return {"source": src.name, "collection": coll.name, "method": method, "parts": parts}
