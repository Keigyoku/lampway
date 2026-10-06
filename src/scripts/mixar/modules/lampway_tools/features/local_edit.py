# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""mesh_local_edit and edit_locality_check (specs/wiki/mesh_local_edit.md, edit_locality_check.md).

mesh_local_edit  one bounded edit of a derivative that has a lineage, on a COPY ``<object>_edit``. engine deform (default): the region's vertices (a bbox in
                 object space, a vertex group or face ids) move / rotate / scale by ``delta``, the rest by a smooth falloff of their distance to the region
                 (``falloff_m``), no topology change, so counts and UVs survive; then edit_locality_check runs on the region grown by the falloff. engine
                 studio:tripo is the exact-box Edit Mesh retry (tripo.regen.region: free, the user's confirm is its approval flag): a plan, nothing clicked.
                 Rodin and Modddif have no driver. A region over 60 % of the vertices is a regeneration, refused.
edit_locality_check  what changed OUTSIDE the region: moved vertices (by index when the topology is the same, else the distance to the other mesh's
                 surface), faces added or removed outside, open edges (all, and outside), UVs and UV islands, materials, dimensions and vertex-group
                 weights. pass = nothing moved or changed outside, and UVs, materials and weights unchanged."""

import math

import bmesh
import numpy as np
from mathutils import Euler, Vector
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree

from . import common as C
from . import uv_islands as UI
from . import workflows as W

OPS = ("move", "rotate", "scale")
MAX_SHARE = 0.6


def _co(ob):
    v = np.empty(len(ob.data.vertices) * 3, dtype=np.float64)
    ob.data.vertices.foreach_get("co", v)
    return v.reshape(-1, 3)


def _bbox(region):
    b = [float(x) for x in region]
    if len(b) != 6:
        raise C.FeatureError("region is a bbox [x0, y0, z0, x1, y1, z1] in object space")
    return np.minimum(b[:3], b[3:]), np.maximum(b[:3], b[3:])


def _members(ob, region) -> np.ndarray:
    co = _co(ob)
    r = dict(region or {})
    if "bbox" in r:
        lo, hi = _bbox(r["bbox"])
        return np.all((co >= lo - 1e-9) & (co <= hi + 1e-9), axis=1)
    m = np.zeros(len(co), bool)
    if "vertex_group" in r:
        g = ob.vertex_groups.get(str(r["vertex_group"]))
        if g is None:
            raise C.FeatureError(f"no vertex group {r['vertex_group']!r} on {ob.name}")
        for v in ob.data.vertices:
            if any(e.group == g.index and e.weight > 0 for e in v.groups):
                m[v.index] = True
        return m
    if "face_ids" in r:
        for i in r["face_ids"]:
            m[list(ob.data.polygons[int(i)].vertices)] = True
        return m
    raise C.FeatureError("region is {bbox} | {vertex_group} | {face_ids}")


def _weights(co, members, falloff):
    w = members.astype(np.float64)
    if falloff <= 0 or members.all():
        return w
    kd = KDTree(int(members.sum()))
    for i in np.nonzero(members)[0]:
        kd.insert(Vector(co[i]), int(i))
    kd.balance()
    for i in np.nonzero(~members)[0]:
        _p, _j, d = kd.find(Vector(co[i]))
        if d < falloff:
            t = 1.0 - d / falloff
            w[i] = t * t * (3 - 2 * t)                                   # smoothstep
    return w


def _region_box(co, w):
    sel = co[w > 0]
    return sel.min(axis=0), sel.max(axis=0)


def mesh_local_edit(object, region, root, engine="deform", op="move", delta=None, falloff_m=0.01, instruction="", side="", anchors=None):
    ob = C.need_object(object)
    if not ob.get("lw_lineage"):
        raise C.FeatureError(f"{ob.name} has no lineage: record the lineage first (lampway_asset_lineage action=record with three identity anchors)")
    falloff = float(falloff_m)
    if not 0.0 <= falloff <= 0.2:
        raise C.FeatureError("falloff_m is 0..0.2 metres")
    co = _co(ob)
    members = _members(ob, region)
    w = _weights(co, members, falloff)
    n_reg = int((w > 0).sum())
    if n_reg == 0:
        raise C.FeatureError("the region is empty: no vertex of the mesh falls inside it")
    if n_reg > MAX_SHARE * len(co):
        raise C.FeatureError(f"the region and its falloff hold {n_reg} of {len(co)} vertices (> 60 %): an edit region this large is a regeneration; use the smallest region")
    if engine != "deform":
        if not side or len(list(anchors or [])) != 3:
            raise C.FeatureError("a Studio region edit needs side (the anatomical left | right | center the piece is worn on) and the three asset_lineage anchors")
        if engine != "studio:tripo":
            raise C.FeatureError(f"there is no {engine} driver (Rodin Partial Edit and the Modddif Geometry Editor have none; only studio:tripo Edit Mesh exists)")
        lo, hi = _bbox(region["bbox"]) if "bbox" in (region or {}) else _region_box(co, members.astype(float))       # the exact box asked for, else the members' bounds
        slot = C.studio_slot("local_edit", engine)
        slot["plan_args"] = {"faces": len(ob.data.polygons), "bbox_blender": [round(float(x), 6) for x in (*lo, *hi)], "pad_m": 0.0}
        slot["instruction"] = instruction
        slot["side"] = side
        slot["note"] = "Edit Mesh exists on the Tripo ORIGINAL only; the box is in the object's (the Blender-import) frame; edit_locality_check runs on the import"
        return slot
    if op not in OPS:
        raise C.FeatureError("op is move | rotate | scale")
    d = [float(x) for x in (delta or [])]
    if len(d) != 3:
        raise C.FeatureError("delta is [x, y, z]: metres (move), degrees (rotate) or factors (scale)")
    lo, hi = _region_box(co, members.astype(float))
    c = (lo + hi) / 2
    out = co.copy()
    for i in np.nonzero(w > 0)[0]:
        wi = w[i]
        if op == "move":
            out[i] = co[i] + wi * np.array(d)
        elif op == "rotate":
            R = Euler([math.radians(x) * wi for x in d]).to_matrix()
            out[i] = c + np.array(R @ Vector(co[i] - c))
        else:
            out[i] = c + (1 + wi * (np.array(d) - 1)) * (co[i] - c)
    new = C.duplicate(ob, "_edit")
    new.data.vertices.foreach_set("co", out.ravel())
    new.data.update()
    moved = float(np.linalg.norm(out - co, axis=1).max())
    glo, ghi = _region_box(co, w)
    loc = edit_locality_check(ob.name, new.name, [*glo, *ghi], margin_m=0.0)
    res = {"object": new.name, "source": ob.name, "engine": "deform", "op": op, "region_vertices": int(members.sum()), "falloff_vertices": n_reg - int(members.sum()),
           "moved_max_m": round(moved, 6), "topology_changed": False, "locality": loc}
    try:
        from . import lineage as LG
        res["lineage_verify"] = LG.run("verify", new.name, root)
    except Exception as exc:  # noqa: BLE001 - reported, the edit stands
        res["lineage_verify"] = {"error": str(exc)}
    return res


# ---- edit_locality_check

def _open_edges(ob, lo, hi):
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    total, outside = 0, 0
    for e in bm.edges:
        if len(e.link_faces) == 1:
            total += 1
            mid = (np.array(e.verts[0].co) + np.array(e.verts[1].co)) / 2
            if not (np.all(mid >= lo) and np.all(mid <= hi)):
                outside += 1
    bm.free()
    return total, outside


def _faces_outside(ob, lo, hi):
    c = np.array([p.center[:] for p in ob.data.polygons], dtype=np.float64).reshape(-1, 3)
    return int((~np.all((c >= lo) & (c <= hi), axis=1)).sum()) if len(c) else 0


def _uv_islands(ob):
    if not ob.data.uv_layers:
        return 0
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    uvl = bm.loops.layers.uv.active
    n = int(UI.island_ids(bm, uvl).max() + 1) if len(bm.faces) else 0
    bm.free()
    return n


def _weights_sig(ob):
    sums = {g.name: 0.0 for g in ob.vertex_groups}
    names = {g.index: g.name for g in ob.vertex_groups}
    for v in ob.data.vertices:
        for e in v.groups:
            if e.group in names:
                sums[names[e.group]] += e.weight
    return sums


def edit_locality_check(before, after, region=None, margin_m=0.005, tolerance_m=0.0005):
    a, b = C.need_object(before), C.need_object(after)
    if region is None:
        raise C.FeatureError("give the region the edit was allowed to touch (a bbox [x0, y0, z0, x1, y1, z1] in object space)")
    lo, hi = _bbox(region)
    margin, tol = float(margin_m), float(tolerance_m)
    if not 0 <= margin <= 0.1 or not 1e-6 <= tol <= 0.01:
        raise C.FeatureError("margin_m is 0..0.1 and tolerance_m 1e-6..0.01 metres")
    if not np.allclose(np.array(a.matrix_world), np.array(b.matrix_world), atol=1e-6):
        raise C.FeatureError("the two meshes are in different frames: align them with the asset_lineage anchors first")
    if a.data.uv_layers and not b.data.uv_layers:
        raise C.FeatureError(f"{b.name} has no UV layer while {a.name} has one: the edit dropped the UVs")
    lo_m, hi_m = lo - margin, hi + margin
    ca, cb = _co(a), _co(b)
    same = len(ca) == len(cb) and len(a.data.polygons) == len(b.data.polygons)
    if same:
        out_mask = ~np.all((ca >= lo_m) & (ca <= hi_m), axis=1)
        disp = np.linalg.norm(cb - ca, axis=1)
        mv = disp[out_mask]
    else:
        tree = BVHTree.FromPolygons([Vector(p) for p in ca], [tuple(p.vertices) for p in a.data.polygons])
        out_mask = ~np.all((cb >= lo_m) & (cb <= hi_m), axis=1)
        mv = np.array([tree.find_nearest(Vector(p))[3] or 0.0 for p in cb[out_mask]])
    moved = int((mv > tol).sum())
    fa, fb = (0, 0) if same else (_faces_outside(a, lo_m, hi_m), _faces_outside(b, lo_m, hi_m))          # same topology: no face can be added or removed
    oa, ob_ = _open_edges(a, lo_m, hi_m), _open_edges(b, lo_m, hi_m)
    uv_changed = W.uv_hash(a) != W.uv_hash(b)
    mat_changed = W.material_hash(a) != W.material_hash(b)
    wa, wb = _weights_sig(a), _weights_sig(b)
    w_changed = set(wa) != set(wb) or any(abs(wa[k] - wb[k]) > 1e-6 for k in wa)
    reasons = []
    if moved:
        reasons.append(f"{moved} vertices outside the region moved (max {float(mv.max()):.5f} m > {tol} m)")
    if fa != fb:
        reasons.append(f"faces outside the region changed: {fa} -> {fb}")
    if oa[1] != ob_[1]:
        reasons.append(f"open edges outside the region changed: {oa[1]} -> {ob_[1]}")
    if uv_changed:
        reasons.append("the UVs changed")
    if mat_changed:
        reasons.append("the materials changed")
    if w_changed:
        reasons.append("the vertex-group weights changed")
    return {"before": a.name, "after": b.name, "same_topology": bool(same),
            "outside": {"moved_vertices": moved, "max_move_m": round(float(mv.max()) if len(mv) else 0.0, 6), "new_faces": max(0, fb - fa), "removed_faces": max(0, fa - fb)},
            "open_edges": {"before": oa[0], "after": ob_[0], "outside_before": oa[1], "outside_after": ob_[1]},
            "uv_changed": bool(uv_changed), "uv_islands": {"before": _uv_islands(a), "after": _uv_islands(b)}, "material_changed": bool(mat_changed),
            "dimensions_delta": [round(float(x), 6) for x in (np.array(b.dimensions) - np.array(a.dimensions))], "weights_changed": bool(w_changed),
            "pass": not reasons, "reasons": reasons, "region": [*map(float, lo), *map(float, hi)], "margin_m": margin, "tolerance_m": tol}
