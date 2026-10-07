# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""scene_cleanup (specs/mixar_docs/scene_cleanup.md): report first, then clean in the documented order: apply transforms, delete loose geometry, merge by distance, fix non-manifold, recalculate normals,
n-gons, purge orphans, naming, material/UV sanity. "Merging vertices before deleting loose geometry means merging things you were about to throw away. Recalculating normals before fixing non-manifold geometry
gives you a confidently wrong result": the order is enforced in code, whatever order was asked for. The merge distance defaults to 1e-4 x the object's bounding diagonal (the docs' trap: a fixed 1e-4 is far too
small for a model made at another scale). Apply mode works on `<object>_clean` copies with the source hash recorded; the source is never changed unless copy is false."""

import re

import bmesh
import bpy
import numpy as np
from mathutils import Matrix

from . import common as C
from .workflows import mesh_hash

STEPS = ("apply_transforms", "loose", "merge_by_distance", "non_manifold", "normals", "ngons", "purge_orphans", "naming", "materials_uvs")
MAX_MERGE_FRACTION = 0.05
_NUM = re.compile(r"\.\d{3,}$")


def _targets(objects):
    if objects is None:
        obs = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    else:
        obs = [C.need_object(n) for n in objects]
    if not obs:
        raise C.FeatureError("no mesh objects to clean")
    editing = [o.name for o in obs if o.mode == "EDIT"]
    if editing:
        raise C.FeatureError(f"leave Edit Mode first: {editing} are being edited, and edit-mode changes are not in the mesh data yet")
    return obs


def _diag(me) -> float:
    n = len(me.vertices)
    if n == 0:
        return 0.0
    co = np.empty(n * 3)
    me.vertices.foreach_get("co", co)
    co = co.reshape(-1, 3)
    return float(np.linalg.norm(co.max(axis=0) - co.min(axis=0)))


def _resolve_distance(ob, merge_distance) -> float:
    if merge_distance in (None, "auto"):
        scale = float(max(abs(s) for s in ob.scale)) or 1.0
        return 1e-4 * _diag(ob.data) * scale
    d = float(merge_distance)
    if d < 0:
        raise C.FeatureError("merge_distance is 'auto' or a distance of zero or more")
    return d


def _shells(bm):
    """Face shells by edge adjacency: [(faces, closed)] where closed means every edge of the shell has exactly two faces."""
    seen, out = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, shell = [f], []
        while stack:
            cur = stack.pop()
            if cur.index in seen:
                continue
            seen.add(cur.index)
            shell.append(cur)
            for e in cur.edges:
                stack.extend(o for o in e.link_faces if o.index not in seen)
        closed = all(len(e.link_faces) == 2 for fc in shell for e in fc.edges)
        out.append((shell, closed))
    return out


def _flipped_faces(bm, dist) -> int:
    """Faces whose winding disagrees with the outward direction of their CLOSED shell, found on a welded copy (so doubled vertices do not hide a flip)."""
    work = bm.copy()
    try:
        d = bmesh.ops.find_doubles(work, verts=work.verts, dist=dist)["targetmap"]
        if d:
            bmesh.ops.weld_verts(work, targetmap=d)
        work.faces.ensure_lookup_table()
        work.faces.index_update()
        before = [tuple(f.normal) for f in work.faces]
        closed = [f for shell, ok in _shells(work) if ok for f in shell]
        if not closed:
            return 0
        bmesh.ops.recalc_face_normals(work, faces=closed)
        return sum(1 for f in closed if np.dot(before[f.index], tuple(f.normal)) < 0)
    finally:
        work.free()


def _non_manifold(bm) -> dict:
    wire = sum(1 for e in bm.edges if not e.link_faces)
    boundary = sum(1 for e in bm.edges if len(e.link_faces) == 1)
    multi = sum(1 for e in bm.edges if len(e.link_faces) > 2)
    return {"total": wire + boundary + multi, "wire": wire, "boundary": boundary, "multi": multi}


def _materials(me) -> dict:
    used = {p.material_index for p in me.polygons}
    names = [m.name if m else "" for m in me.materials]
    groups = {}
    for n in names:
        if n:
            groups.setdefault(_NUM.sub("", n), set()).add(n)
    return {"slots": len(names), "unused": sum(1 for i in range(len(names)) if i not in used), "duplicates": [sorted(g) for g in groups.values() if len(g) > 1]}


def _orphans() -> dict:
    return {k: sum(1 for x in getattr(bpy.data, k) if x.users == 0) for k in ("meshes", "materials", "images", "textures")}


def _report(ob, merge_distance) -> dict:
    me = ob.data
    bm = bmesh.new()
    bm.from_mesh(me)
    dist = _resolve_distance(ob, merge_distance)
    doubles = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=dist)["targetmap"]
    nm = _non_manifold(bm)
    rep = {"object": ob.name, "non_uniform_scale": bool(max(abs(s) for s in ob.scale) > min(abs(s) for s in ob.scale) * (1 + 1e-6)), "loose_verts": sum(1 for v in bm.verts if not v.link_edges),
           "doubles_at_distance": len(doubles), "merge_distance": dist, "non_manifold_edges": nm["total"], "non_manifold": nm, "flipped_faces": _flipped_faces(bm, dist),
           "ngons": sum(1 for f in bm.faces if len(f.verts) > 4), "materials": _materials(me), "uv_layers": len(me.uv_layers)}
    bm.free()
    return rep


def _convention_name(name, conv) -> str:
    n = name
    if conv.get("strip_numeric_suffix"):
        n = _NUM.sub("", n)
    if conv.get("replace_spaces") is not None:
        n = n.replace(" ", conv["replace_spaces"])
    if conv.get("lowercase"):
        n = n.lower()
    return f"{conv.get('prefix', '')}{n}{conv.get('suffix', '')}"


def _apply(ob, step, merge_distance, ngon_policy, conv, copy):
    me = ob.data
    if step == "apply_transforms":
        if not copy and me.users > 1:
            raise C.FeatureError(f"{me.users} objects share this mesh: applying scale would change them all (users count); work on a copy or make it single-user")
        m = ob.matrix_basis.copy()
        m.translation = (0.0, 0.0, 0.0)
        changed = int(max(abs(s) for s in ob.scale) > min(abs(s) for s in ob.scale) * (1 + 1e-6) or any(abs(r) > 1e-9 for r in ob.rotation_euler) or any(abs(s - 1) > 1e-9 for s in ob.scale))
        me.transform(m)
        if m.determinant() < 0:
            bm = bmesh.new()
            bm.from_mesh(me)
            bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
            bm.to_mesh(me)
            bm.free()
        ob.rotation_euler, ob.scale = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)
        me.update()
        return {"changed": changed}
    if step == "naming":
        old = ob.name
        ob.name = _convention_name(str(ob.get("lw_source") or old), conv)                   # from the SOURCE name: the `_clean` tag is a working label, not part of the user's convention
        ob.data.name = ob.name
        return {"changed": int(ob.name != old), "note": f"{old} -> {ob.name}"}
    if step == "purge_orphans":
        before = sum(_orphans().values())
        bpy.data.orphans_purge(do_local_ids=True, do_linked_ids=True, do_recursive=True)
        return {"changed": before - sum(_orphans().values())}
    if step == "materials_uvs":
        used = sorted({p.material_index for p in me.polygons})
        drop = [i for i in range(len(me.materials)) if i not in used]
        if drop:
            remap = {old: new for new, old in enumerate(i for i in range(len(me.materials)) if i not in drop)}
            for p in me.polygons:
                p.material_index = remap[p.material_index]
            for i in reversed(drop):
                me.materials.pop(index=i)
        return {"changed": len(drop), "note": "unused material slots removed; duplicates are reported, never merged"}
    bm = bmesh.new()
    bm.from_mesh(me)
    out = {"changed": 0}
    if step == "loose":
        wire = [e for e in bm.edges if not e.link_faces]
        bmesh.ops.delete(bm, geom=wire, context="EDGES")
        v = [v for v in bm.verts if not v.link_edges]
        bmesh.ops.delete(bm, geom=v, context="VERTS")
        out["changed"] = len(wire) + len(v)
    elif step == "merge_by_distance":
        dist = _resolve_distance(ob, merge_distance)
        tm = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=dist)["targetmap"]
        if len(bm.verts) and len(tm) / len(bm.verts) > MAX_MERGE_FRACTION:
            out["note"] = f"{len(tm)} of {len(bm.verts)} vertices would merge at {dist:g}: threshold likely wrong, nothing merged (the limit is {int(MAX_MERGE_FRACTION * 100)} % of the vertices)"
        else:
            n = len(bm.verts)
            bmesh.ops.weld_verts(bm, targetmap=tm)
            out["changed"] = n - len(bm.verts)
    elif step == "non_manifold":
        wire = [e for e in bm.edges if not e.link_faces]
        bmesh.ops.delete(bm, geom=wire, context="EDGES")
        nm = _non_manifold(bm)
        out.update(changed=len(wire), note=f"{nm['boundary']} open boundary edges and {nm['multi']} multi-face edges remain: reported, not filled (they may be intentional)")
    elif step == "normals":
        closed = [f for shell, ok in _shells(bm) if ok for f in shell]
        bm.faces.ensure_lookup_table()
        bm.faces.index_update()
        before = {f.index: tuple(f.normal) for f in closed}
        if closed:
            bmesh.ops.recalc_face_normals(bm, faces=closed)
        out["changed"] = sum(1 for f in closed if np.dot(before[f.index], tuple(f.normal)) < 0)
        out["note"] = "closed shells only: an open shell has no inside to orient from"
    elif step == "ngons":
        big = [f for f in bm.faces if len(f.verts) > 4]
        if ngon_policy == "triangulate":
            bmesh.ops.triangulate(bm, faces=big)
            out["changed"] = len(big)
        else:
            out["note"] = f"{len(big)} n-gons {'kept' if ngon_policy == 'keep' else 'reported'}: the policy is {ngon_policy}"
    bm.to_mesh(me)
    bm.free()
    me.update()
    return out


PAGE = 50                # audit F8: a 1,016-object plan answered 351-369 KB; rows come a page at a time, the totals cover every object
_TOTALS = ("loose_verts", "doubles_at_distance", "non_manifold_edges", "flipped_faces", "ngons")


def _paged(rows, limit, offset, full):
    if full:
        return rows, None
    limit, offset = max(1, int(limit)), max(0, int(offset))
    return rows[offset:offset + limit], (offset + limit if offset + limit < len(rows) else None)


def scene_cleanup(objects=None, steps=None, merge_distance="auto", ngon_policy="report", convention=None, plan_only=True, copy=True,
                  limit=PAGE, offset=0, full=False):
    if ngon_policy not in ("report", "triangulate", "keep"):
        raise C.FeatureError("ngon_policy is report | triangulate | keep")
    chosen = list(STEPS) if steps is None else list(steps)
    bad = [s for s in chosen if s not in STEPS]
    if bad:
        raise C.FeatureError(f"unknown step {bad}: the steps are {list(STEPS)}")
    ordered = [s for s in STEPS if s in chosen]                                       # the documented order, whatever order was asked
    if "naming" in ordered and not plan_only and not convention:
        raise C.FeatureError("I cannot invent your naming convention: pass convention (prefix, suffix, lowercase, replace_spaces, strip_numeric_suffix)")
    obs = _targets(objects)
    report = [_report(o, merge_distance) for o in obs]
    totals = {k: sum(int(r[k]) for r in report) for k in _TOTALS}
    totals["non_uniform_scale"] = sum(1 for r in report if r["non_uniform_scale"])
    page, nxt = _paged(report, limit, offset, full)
    out = {"ok": True, "plan_only": bool(plan_only), "steps": ordered, "object_count": len(report), "totals": totals, "report": page,
           "next_offset": nxt, "orphans": _orphans(), "applied": [], "branch": {}}
    if plan_only:
        return out
    work = {}
    for o in obs:
        if copy:
            b = C.duplicate(o, "_clean")
            b["lw_source"], b["lw_source_hash"] = o.name, mesh_hash(o)
        else:
            b = o
            b["lw_source"], b["lw_source_hash"] = o.name, mesh_hash(o)
        work[o.name] = b
    if not copy and "apply_transforms" in ordered:
        for o in obs:
            if o.data.users > 1:
                raise C.FeatureError(f"{o.data.users} objects share this mesh ({o.name}): applying scale would change them all (users count)")
    for step in ordered:
        for src_name, b in list(work.items()):
            res = _apply(b, step, merge_distance, ngon_policy, convention or {}, copy)
            out["applied"].append({"object": b.name, "step": step, **res})
    out["branch"] = {k: b.name for k, b in work.items()}
    out["applied_totals"] = {st: sum(int(a.get("changed") or 0) for a in out["applied"] if a["step"] == st) for st in ordered}
    out["applied_count"] = len(out["applied"])
    out["applied"], out["applied_next_offset"] = _paged(out["applied"], limit, offset, full)
    if not full and len(out["branch"]) > int(limit):
        out["branch"] = dict(list(out["branch"].items())[int(offset):int(offset) + int(limit)])
    return out
