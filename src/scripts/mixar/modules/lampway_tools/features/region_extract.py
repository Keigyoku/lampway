# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_region_extract (specs/wiki/mesh_region_extract.md): a chosen region of a mesh as its own object, from COPIES (the source is never changed).

region  {bbox: [x0, y0, z0, x1, y1, z1]} (face centres, world) | {polygon_2d: [[h, v], ...], view} (an X-ray lasso in a cardinal view's plane: Front h=x,
        Back h=-x, Left h=-y, Right h=y, v=z; every face whose centre falls inside, seen or not) | {vertex_group} (faces whose vertices all belong) |
        {material_slot: index or material name} | {zone, by} (a zone_sheet number)
cap     none | fill_holes (each open loop filled by one face) | fan (filled, then poked to a fan of triangles) | flat (filled; refused when a loop is not planar)
The remainder (keep_in_source=false) is a second copy with the region removed and its hole left open, for a later join. Each new object records its source's
geometry hash and the region (``lw_region``); identity anchors are the user's (asset_lineage record), never invented here."""

import json

import bmesh
import numpy as np

from . import common as C
from . import workflows as W
from . import zones as Z

CAPS = ("none", "fill_holes", "fan", "flat")
H_AXES = {"Front": (0, 1.0), "Back": (0, -1.0), "Left": (1, -1.0), "Right": (1, 1.0)}


def _inside(pts, poly):
    """Even-odd rule, vectorised over points."""
    x, y = pts[:, 0], pts[:, 1]
    inside = np.zeros(len(pts), bool)
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        cond = ((y1 > y) != (y2 > y))
        with np.errstate(divide="ignore", invalid="ignore"):
            xin = (x2 - x1) * (y - y1) / ((y2 - y1) if y2 != y1 else 1e-30) + x1
        inside ^= cond & (x < xin)
    return inside


def select_faces(ob, region, recipe="") -> list:
    r = dict(region or {})
    me = ob.data
    mw = np.array(ob.matrix_world)
    cen = np.array([p.center[:] for p in me.polygons], dtype=np.float64).reshape(-1, 3)
    wc = (mw[:3, :3] @ cen.T).T + mw[:3, 3] if len(cen) else cen
    if "bbox" in r:
        b = [float(v) for v in r["bbox"]]
        if len(b) != 6:
            raise C.FeatureError("bbox is [x0, y0, z0, x1, y1, z1] in world metres")
        lo, hi = np.minimum(b[:3], b[3:]), np.maximum(b[:3], b[3:])
        return np.nonzero(np.all((wc >= lo) & (wc <= hi), axis=1))[0].tolist()
    if "polygon_2d" in r:
        view = r.get("view", "Front")
        if view not in H_AXES:
            raise C.FeatureError(f"polygon_2d needs view {' | '.join(H_AXES)}")
        poly = [(float(p[0]), float(p[1])) for p in r["polygon_2d"]]
        if len(poly) < 3:
            raise C.FeatureError("polygon_2d needs at least three [h, v] points")
        ax, sgn = H_AXES[view]
        pts = np.stack([wc[:, ax] * sgn, wc[:, 2]], axis=1)
        return np.nonzero(_inside(pts, poly))[0].tolist()
    if "vertex_group" in r:
        g = ob.vertex_groups.get(str(r["vertex_group"]))
        if g is None:
            raise C.FeatureError(f"no vertex group {r['vertex_group']!r} on {ob.name}: the groups are {[x.name for x in ob.vertex_groups]}")
        return dict(Z.zones(ob, "vertex_group")).get(g.name, [])
    if "material_slot" in r:
        s = r["material_slot"]
        names = [m.material.name if m.material else "" for m in ob.material_slots]
        i = int(s) if isinstance(s, int) or str(s).isdigit() else (names.index(s) if s in names else None)
        if i is None or not 0 <= i < len(names):
            raise C.FeatureError(f"no material slot {s!r}: the slots are {names}")
        idx = np.empty(len(me.polygons), dtype=np.int64)
        me.polygons.foreach_get("material_index", idx)
        return np.nonzero(idx == i)[0].tolist()
    if "zone" in r:
        return list(Z.zone_faces(ob, r.get("by", "material_slot"), r["zone"], recipe)[1])
    raise C.FeatureError("region is {bbox} | {polygon_2d, view} | {vertex_group} | {material_slot} | {zone, by}")


def _boundary_loops(bm) -> list:
    edges = [e for e in bm.edges if len(e.link_faces) == 1]
    seen, loops = set(), []
    for e in edges:
        if e in seen:
            continue
        comp, stack = [], [e]
        while stack:
            c = stack.pop()
            if c in seen:
                continue
            seen.add(c)
            comp.append(c)
            for v in c.verts:
                stack += [x for x in v.link_edges if len(x.link_faces) == 1 and x not in seen]
        loops.append(comp)
    return loops


def _keep(new, faces_to_keep):
    bm = bmesh.new()
    bm.from_mesh(new.data)
    bm.faces.ensure_lookup_table()
    keep = set(faces_to_keep)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.index not in keep], context="FACES")
    return bm


def _cap(bm, cap):
    loops = _boundary_loops(bm)
    if cap == "none" or not loops:
        return len(loops), 0
    before = set(bm.faces)
    bmesh.ops.holes_fill(bm, edges=[e for lp in loops for e in lp], sides=0)
    new = [f for f in bm.faces if f not in before]
    if cap == "flat":
        for f in new:
            pts = np.array([v.co[:] for v in f.verts])
            c = pts.mean(axis=0)
            nrm = np.array(f.normal[:])
            span = max(1e-9, float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))))
            if np.abs((pts - c) @ nrm).max() > 0.01 * span:
                raise C.FeatureError("an open loop is not planar: a flat cap would not close it truthfully; use cap=fan or fill_holes")
    if cap == "fan":
        bmesh.ops.poke(bm, faces=new)
    return len(loops), len(new)


def run(object, region, cap="fill_holes", keep_in_source=True, name="", recipe=""):
    import bpy
    ob = C.need_object(object)
    if cap not in CAPS:
        raise C.FeatureError("cap is " + " | ".join(CAPS))
    faces = select_faces(ob, region, recipe)
    n = len(ob.data.polygons)
    if not faces:
        raise C.FeatureError("the region is empty: no face of the mesh falls inside it")
    if len(faces) > 0.9 * n:
        raise C.FeatureError(f"the region holds {len(faces)} of {n} faces (> 90 %): that is the whole mesh; work on a copy of it instead")
    src_hash = W.mesh_hash(ob)
    record = json.dumps({"source": ob.name, "source_geometry_hash": src_hash, "transform": "region extract", "region": region, "faces": len(faces)}, default=str)
    ext = C.duplicate(ob, "_region")
    if name:
        ext.name = name
        ext.data.name = name
    bm = _keep(ext, faces)
    try:
        loops, capped = _cap(bm, cap)
    except C.FeatureError:
        bm.free()
        me = ext.data
        bpy.data.objects.remove(ext)
        bpy.data.meshes.remove(me)
        raise
    bm.to_mesh(ext.data)
    bm.free()
    ext.data.update()
    ext["lw_region"] = record
    out = {"extracted": ext.name, "source": ob.name, "faces": len(faces), "open_loops_before_cap": loops, "capped": capped, "cap": cap,
           "remainder": None, "lineage_updated": True, "lineage": {"source_geometry_hash": src_hash, "transform": "region extract",
                                                                    "note": "identity anchors are the user's: asset_lineage record on the extracted part"}}
    if not keep_in_source:
        rem = C.duplicate(ob, "_remainder")
        bmr = _keep(rem, [i for i in range(n) if i not in set(faces)])
        bmr.to_mesh(rem.data)
        bmr.free()
        rem.data.update()
        rem["lw_region"] = record
        out["remainder"] = rem.name
    return out
