# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stefan's wiki workflows as Client tools. Each is the wiki's checklist turned into measured gates on real data, composed from
the proven feature code: ``mesh_prep`` (geometry-game-mesh-preparation: branch the source, hash it, report and repair only the
defects found), ``asset_acceptance`` (engine-asset-acceptance: identity / orientation / geometry / materials gates against an
optional reference) and ``rig_armor`` (rigging-existing-armor: fit a COPY of the piece, rigid on one bone or weights transferred
from the aligned body, then measure stretch in a pose set). No model is called."""

import hashlib
import math

import bmesh
import bpy
import numpy as np

from . import common as C
from . import rig as _rig

_DEFAULT_POSES = [("shoulders_up", "upperarm_l", [0, 0, 80]), ("elbow_flex", "lowerarm_l", [0, 0, -90]),
                  ("hip_flex", "thigh_l", [60, 0, 0]), ("torso_twist", "spine_03", [0, 0, 40])]


def mesh_hash(ob) -> str:
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    loops = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    h = hashlib.sha256()
    h.update(co.tobytes())
    h.update(loops.tobytes())
    return h.hexdigest()


def _signed_volume(ob) -> float:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol


def _bounds(ob):
    pts = np.array([ob.matrix_world @ v.co for v in ob.data.vertices], dtype=np.float64).reshape(-1, 3)
    return pts.min(axis=0), pts.max(axis=0)


def _pivot_offset(ob) -> float:
    lo, hi = _bounds(ob)
    return round(float(np.linalg.norm(np.asarray(ob.matrix_world.translation) - (lo + hi) / 2)), 6)


def mesh_prep(object, merge_distance=1e-5):
    src = C.need_object(object)
    before = C.mesh_report(src)
    digest = mesh_hash(src)
    branch = C.duplicate(src, "_prep")
    branch["lw_source"] = src.name
    branch["lw_source_hash"] = digest
    bm = bmesh.new()
    bm.from_mesh(branch.data)
    doubles = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=merge_distance)["targetmap"]
    found = {"loose_vertices": before["loose_vertices"], "doubled_vertices": len(doubles),
             "inverted": _signed_volume(src) < 0 and before["open_boundary_edges"] == 0}
    if doubles:
        bmesh.ops.weld_verts(bm, targetmap=doubles)
    loose = [v for v in bm.verts if not v.link_edges]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if found["inverted"]:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(branch.data)
    bm.free()
    after = C.mesh_report(branch)
    return {"object": branch.name, "source": src.name, "source_hash": digest, "before": before, "after": after, "found": found,
            "dimensions": [round(float(d), 6) for d in branch.dimensions], "pivot_offset_from_bounds_centre": _pivot_offset(branch),
            "note": "the source is untouched; only loose vertices, doubled vertices and inverted normals are repaired"}


def asset_acceptance(object, reference="", tolerance=0.1):
    ob = C.need_object(object)
    ref = C.need_object(reference) if reference else None
    digest = mesh_hash(ob)
    rep = C.mesh_report(ob)
    gates = {}
    ident = [f"hash {digest[:12]}"]
    if ob.get("lw_source_hash"):
        ident.append(f"derived from {ob.get('lw_source')} ({str(ob['lw_source_hash'])[:12]})")
    if ref is not None and mesh_hash(ref) == digest:
        ident.append("identical to the reference")
    gates["identity"] = {"pass": True, "reasons": ident, "hash": digest}
    reasons, ok = [f"dimensions {[round(float(d), 4) for d in ob.dimensions]}", f"pivot {_pivot_offset(ob)} from the bounds centre"], True
    if ref is not None:
        lo, hi = _bounds(ob)
        rlo, rhi = _bounds(ref)
        diag = max(1e-9, float(np.linalg.norm(rhi - rlo)))
        shift = float(np.linalg.norm((lo + hi) / 2 - (rlo + rhi) / 2)) / diag
        size = float(np.max(np.abs((hi - lo) - (rhi - rlo)))) / diag
        if shift > tolerance:
            ok = False
            reasons.append(f"bounds centre moved {shift:.2f} of the reference diagonal (> {tolerance})")
        if size > tolerance:
            ok = False
            reasons.append(f"extent differs by {size:.2f} of the reference diagonal (> {tolerance})")
    scale = max(abs(s - 1.0) for s in ob.scale)
    if scale > 1e-4:
        ok = False
        reasons.append(f"object scale {tuple(round(s, 4) for s in ob.scale)} is not applied")
    gates["orientation"] = {"pass": ok, "reasons": reasons}
    geo, ok = [], True
    if rep["non_manifold_edges"]:
        ok = False
        geo.append(f"{rep['non_manifold_edges']} non-manifold edges")
    if rep["loose_vertices"]:
        ok = False
        geo.append(f"{rep['loose_vertices']} loose vertices")
    if rep["open_boundary_edges"] == 0 and _signed_volume(ob) < 0:
        ok = False
        geo.append("inverted normals (negative signed volume)")
    gates["geometry"] = {"pass": ok, "reasons": geo or ["closed, outward, no loose geometry"], "report": rep}
    mat, ok = [], True
    empty = [i for i, s in enumerate(ob.material_slots) if s.material is None]
    if empty:
        ok = False
        mat.append(f"empty material slots {empty}")
    if ob.material_slots and not ob.data.uv_layers:
        ok = False
        mat.append("materials but no UV layer")
    gates["materials"] = {"pass": ok, "reasons": mat or [f"{len(ob.material_slots)} slots, {len(ob.data.uv_layers)} UV layers"]}
    return {"object": ob.name, "reference": ref.name if ref else None, "gates": gates,
            "accepted": all(g["pass"] for g in gates.values()),
            "not_checked": ["engine import settings", "collision", "skeleton in the target engine"]}


def rig_armor(object, armature, bone="", body="", poses=None, max_stretch=None):
    src = C.need_object(object)
    arm_ob = C.need_object(armature, "ARMATURE")
    if bone:
        mode, kw = "rigid", {"bone": bone}
    elif body:
        mode, kw = "transfer", {"source": body}
    else:
        mode, kw = "auto", {}
    fit = C.duplicate(src, "_fit")
    bound = _rig.bind_to_armature(fit.name, arm_ob.name, mode, **kw)
    if poses is None:
        poses = [{"name": n, "bone": b, "rotate": r} for n, b, r in _DEFAULT_POSES if b in arm_ob.data.bones]
    tested = _rig.pose_test(arm_ob.name, fit.name, poses)["poses"]
    limit = float(max_stretch) if max_stretch is not None else (1.001 if mode == "rigid" else 1.35)
    worst = max((p["max_edge_stretch"] for p in tested), default=1.0)
    return {"object": fit.name, "source": src.name, "armature": arm_ob.name, "mode": mode, "bind": bound, "poses": tested,
            "max_stretch_limit": limit, "worst_stretch": worst, "accepted": bool(tested) and worst < limit,
            "note": "the original is never bound; a new geometry stage invalidates this test"}
