# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The captain's annotation tags, read into faces, islands and loops.

He tags the mesh with three annotation layers, drawn with the Annotate tool's placement set to Surface (the points
lie on the mesh), so a stroke is read without the view:

    Red   layer "Delete"    - faces (or a whole floating shell) to delete
    Green layer "Mislabel"  - faces / Smart UV islands carrying the wrong part label (or the wrong material class)
    Yellow layer "Hole"     - an open loop that must be filled (a candidate it circles or runs along), or a hole the
                              candidate generator missed (an orphan: the most valuable row of the decision log)

How a stroke becomes data (the practice in the shelf's captain_marks/ scripts, 2026-10-04):

    faces   the faces nearest the stroke's points, in the order met, once each (points further than ``max_dist_m``
            from the mesh are off-surface and ignored). Measured against his own marks on the live chest: 20/20,
            36/37, 6/6, 5/5, 5/5, 5/5 and 3/3 faces per stroke.
    islands the Smart UV islands (UV-connected corners: a seam separates them even where the mesh is connected)
            holding those faces, with the share of each island the stroke touched.
    loops   for a Hole stroke: candidates whose boundary the stroke runs along (a quarter of the loop's segments
            within ``loop_tol_m`` of the stroke), or that it circles (plane fitted to the stroke, the candidate's
            centroid projected inside its outline - the shelf's qa_read_marks.py test).
"""

import numpy as np

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

# the captain's layer colours (read from his marks_*.json exports)
TAG_LAYERS = {"delete": ("Delete", (0.78, 0.074, 0.106)),
              "mislabel": ("Mislabel", (0.0, 0.78, 0.004)),
              "hole": ("Hole", (0.78, 0.738, 0.041))}
_NAMES = {"delete": "delete", "red": "delete", "mislabel": "mislabel", "green": "mislabel", "hole": "hole", "yellow": "hole"}
_MAX_FRAMES, _MAX_STROKES, _MAX_POINTS = 50, 2000, 20000                     # bounds: a runaway annotation cannot hang the app


class Stroke:
    def __init__(self, tag, layer, index, points):
        self.tag, self.layer, self.index, self.points = tag, layer, index, points


def tag_of_layer(info, color):
    """The tag a layer carries: by its name (Delete/Mislabel/Hole, or Red/Green/Yellow), else by its colour."""
    named = _NAMES.get((info or "").strip().lower())
    if named:
        return named
    r, g, b = (float(c) for c in color[:3])
    mx, mn = max(r, g, b), min(r, g, b)
    if mx < 0.4 or (mx - mn) < 0.35 * mx:                                    # dark or grey: not a tag colour
        return None
    if mx == r:
        h = ((g - b) / (mx - mn)) % 6
    elif mx == g:
        h = (b - r) / (mx - mn) + 2
    else:
        h = (r - g) / (mx - mn) + 4
    h *= 60
    if h < 20 or h >= 340:
        return "delete"
    if 40 <= h < 75:
        return "hole"
    if 90 <= h < 160:
        return "mislabel"
    return None


def _annotation(ann=None):
    if ann is not None:
        return ann
    scene = bpy.context.scene
    ann = getattr(scene, "annotation", None)
    if ann is None and len(bpy.data.annotations):
        ann = bpy.data.annotations[0]
    return ann


def read_tags(ann=None) -> dict:
    """{'delete': [Stroke], 'mislabel': [...], 'hole': [...]}; every key is present, in layer then stroke order."""
    out = {"delete": [], "mislabel": [], "hole": []}
    ann = _annotation(ann)
    if ann is None:
        return out
    for layer in ann.layers:
        tag = tag_of_layer(layer.info, layer.color)
        if tag is None:
            continue
        i = 0
        for frame in list(layer.frames)[:_MAX_FRAMES]:
            for s in list(frame.strokes)[:_MAX_STROKES]:
                pts = np.array([p.co[:] for p in list(s.points)[:_MAX_POINTS]], dtype=float).reshape(-1, 3)
                out[tag].append(Stroke(tag, layer.info, i, pts))
                i += 1
    return out


def create_tag_layers(ann=None):
    """The scene's annotation data with the three tag layers, in the captain's colours (existing layers are kept)."""
    if ann is None:
        ann = getattr(bpy.context.scene, "annotation", None) or bpy.data.annotations.new("Annotations")
        bpy.context.scene.annotation = ann
    for name, color in TAG_LAYERS.values():
        layer = ann.layers.get(name) or ann.layers.new(name)
        layer.color = color
    return ann


def export_marks(ann=None) -> dict:
    """His marks_*.json shape: {'layers': [{'gp', 'layer', 'color', 'n', 'strokes': [[[x, y, z], ...]]}]} (+ 'view'
    when a 3D viewport is open), every layer, tag or not."""
    ann = _annotation(ann)
    layers = []
    for layer in (ann.layers if ann else []):
        strokes = [[list(map(float, p.co[:])) for p in list(s.points)[:_MAX_POINTS]]
                   for f in list(layer.frames)[:_MAX_FRAMES] for s in list(f.strokes)[:_MAX_STROKES]]
        layers.append({"gp": ann.name, "layer": layer.info, "color": [round(float(c), 3) for c in layer.color[:3]],
                       "n": len(strokes), "strokes": strokes})
    out = {"layers": layers}
    for window in getattr(bpy.context.window_manager, "windows", []):
        for area in window.screen.areas:
            if area.type == "VIEW_3D":
                out["view"] = {"view_matrix": [list(row) for row in area.spaces.active.region_3d.view_matrix]}
                return out
    return out


class Surface:
    """The mesh of an object in world space, for nearest-face lookups."""

    def __init__(self, ob):
        me = ob.data
        m = ob.matrix_world
        verts = [m @ v.co for v in me.vertices]
        self.bvh = BVHTree.FromPolygons(verts, [tuple(p.vertices) for p in me.polygons])
        self.polygons = len(me.polygons)

    def faces_for(self, points, max_dist_m=0.02, with_misses=False):
        """Faces nearest the points, in the order first met, once each."""
        faces, seen, off = [], set(), 0
        for p in points:
            loc, _n, idx, dist = self.bvh.find_nearest(Vector(p), max_dist_m)
            if idx is None:
                off += 1
                continue
            if idx not in seen:
                seen.add(idx)
                faces.append(int(idx))
        return (faces, off) if with_misses else faces


def uv_islands(me) -> np.ndarray:
    """One island id per polygon: faces joined across an edge whose two corners share their UVs at both ends."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.faces.ensure_lookup_table()
    uvl = bm.loops.layers.uv.active
    par = list(range(len(bm.faces)))

    def find(x):
        while par[x] != x:
            par[x] = par[par[x]]
            x = par[x]
        return x

    if uvl is not None:
        for e in bm.edges:
            if len(e.link_loops) != 2:
                continue
            a, b = e.link_loops
            # the same edge seen from two faces: corner a.vert in face A is at b.link_loop_next.vert in face B when wound oppositely
            def uv_at(loop, vert):
                for l in loop.face.loops:
                    if l.vert == vert:
                        return l[uvl].uv
            ok = True
            for v in e.verts:
                ua, ub = uv_at(a, v), uv_at(b, v)
                if (ua - ub).length > 1e-6:
                    ok = False
                    break
            if ok:
                par[find(a.face.index)] = find(b.face.index)
    roots = np.array([find(i) for i in range(len(bm.faces))])
    bm.free()
    _, ids = np.unique(roots, return_inverse=True)
    # contiguous ids in first-face order
    order = {}
    out = np.empty(len(ids), dtype=int)
    for i, r in enumerate(ids):
        out[i] = order.setdefault(int(r), len(order))
    return out


def _inside(pt, poly):
    c, j = False, len(poly) - 1
    for i in range(len(poly)):
        (xi, yi), (xj, yj) = poly[i], poly[j]
        if (yi > pt[1]) != (yj > pt[1]) and pt[0] < (xj - xi) * (pt[1] - yi) / (yj - yi + 1e-12) + xi:
            c = not c
        j = i
    return c


def _dist_to_polyline(p, pts):
    if len(pts) == 1:
        return float(np.linalg.norm(p - pts[0]))
    a, b = pts[:-1], pts[1:]
    ab = b - a
    t = np.clip(np.einsum("ij,ij->i", p - a, ab) / np.maximum(np.einsum("ij,ij->i", ab, ab), 1e-18), 0, 1)
    return float(np.min(np.linalg.norm(a + ab * t[:, None] - p, axis=1)))


def _loops_for(stroke_pts, candidates, loop_tol_m, along_share, plane_m):
    hits = {}
    for c in candidates:
        if c.get("kind") != "open_loop":
            continue
        segs = c.get("segments_m") or []
        if segs:
            mids = [(np.array(p0) + np.array(p1)) / 2 for p0, p1 in segs]
            near = sum(1 for m in mids if _dist_to_polyline(m, stroke_pts) <= loop_tol_m)
            if near >= max(1, int(np.ceil(along_share * len(mids)))):
                hits[c["id"]] = "along"
                continue
        if len(stroke_pts) >= 8 and c.get("centroid_m") is not None:         # the shelf's qa_read_marks.py circle test
            ctr = stroke_pts.mean(0)
            _u, _s, vt = np.linalg.svd(stroke_pts - ctr)
            ax, ay, nz = vt[0], vt[1], vt[2]
            poly = np.c_[(stroke_pts - ctr) @ ax, (stroke_pts - ctr) @ ay]
            p = np.array(c["centroid_m"])
            if abs((p - ctr) @ nz) <= plane_m and _inside(((p - ctr) @ ax, (p - ctr) @ ay), poly):
                hits[c["id"]] = "circled"
    return hits


def interpret(tags, ob, candidates=None, max_dist_m=0.02, loop_tol_m=0.004, along_share=0.25, plane_m=0.06) -> dict:
    """Per tag, one row per stroke: faces, islands (+ the share of each island touched), centre, and for Hole strokes
    the candidate loops it names (``{id: 'along'|'circled'}``) or ``orphan``."""
    surf = Surface(ob)
    isl = uv_islands(ob.data)
    sizes = np.bincount(isl) if len(isl) else np.array([])
    out = {"delete": [], "mislabel": [], "hole": []}
    for tag, strokes in tags.items():
        for s in strokes:
            faces, off = surf.faces_for(s.points, max_dist_m, with_misses=True)
            ids = sorted({int(isl[f]) for f in faces})
            touch = {str(i): round(sum(1 for f in faces if isl[f] == i) / int(sizes[i]), 4) for i in ids}
            row = {"layer": s.layer, "stroke": s.index, "n_points": int(len(s.points)), "off_surface": off,
                   "faces": faces, "islands": ids, "island_touch": touch,
                   "centre_m": [round(float(x), 4) for x in (s.points.mean(0) if len(s.points) else (0, 0, 0))]}
            if tag == "hole":
                row["loops"] = _loops_for(s.points, candidates or [], loop_tol_m, along_share, plane_m) if len(s.points) else {}
                row["orphan"] = not row["loops"]
            out[tag].append(row)
    return out
