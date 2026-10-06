# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_bind: bind a finished piece to the body's skeleton by the user's weight laws.

* A metal part is placed by ONE rigid transform: one bone, full weight; blending it is refused (a ruled cut, as original vertex ids, splits it). Leather, cloth and embroidery are weighted by POSITION
  (the body's own weights, restricted to the bones the plan allows), so a seam vertex's two copies move together.
* Parts that share a seam and one bone form a rigid group; two rigid parts of one shell on different bones OPEN the seam (``seam_opens``), and ``apply`` refuses unless the user accepts a gap.
* Every part needs a material role from the user or the recipe, never from a render's colour.
Stages: plan -> weights (a copy ``<piece>_fit``; the source is untouched) -> return (the rest residual against the original shell) -> apply (the seam gate) -> report.
The body's weights here come from a body OBJECT in the scene (an approximation: the native sidecar sampler is not built); the plan, the laws and the gates are the real thing."""

import difflib
import hashlib
import json
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import weights as WT
from .. import canon_geom as G
from ..pipeline import validate as V

ROLES = ("metal", "leather", "cloth", "embroidery")
RETURN_METAL_MAX_MM = 0.5               # canon 04 G: a metal part's returned rest is a similarity of its source within this (the adopted limit)
MODES = ("rigid", "restrict", "blend")
SEAM_EPS = 1e-5


def _state_path(root, out_dir):
    return Path(root) / out_dir / "bind_state.json"


def _load(root, out_dir):
    p = _state_path(root, out_dir)
    return json.loads(p.read_text()) if p.exists() else {}


def _save(root, out_dir, state):
    p = _state_path(root, out_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, indent=1))


def _parts(ob):
    return {g.name: np.array([v.index for v in ob.data.vertices if any(x.group == g.index and x.weight > 0 for x in v.groups)], dtype=int) for g in ob.vertex_groups}


def _hist(ob, arm, idx):
    bones = [b for b in arm.data.bones if b.use_deform]
    P = np.array([(ob.matrix_world @ ob.data.vertices[i].co)[:] for i in idx])
    seg = WT.bone_segments(arm)                                             # head -> continuation child (canon 01 C.1)
    D = np.stack([WT._seg_dist(P, *seg[b.name]) for b in bones], axis=1)
    near = D.argmin(axis=1)
    return {bones[k].name: float((near == k).mean()) for k in range(len(bones)) if (near == k).any()}


def _check_bones(names, arm):
    have = sorted(b.name for b in arm.data.bones)
    for n in names:
        if n not in have:
            raise C.FeatureError(f"bone {n!r} is not in the skeleton; the nearest names are: {difflib.get_close_matches(n, have, n=3, cutoff=0.4) or have[:6]}")


def plan(piece, armature, roles, bind_overrides, out_dir, root):
    ob = C.need_object(piece)
    arm = C.need_object(armature, "ARMATURE")
    roles = roles or {}
    parts = _parts(ob)
    if not parts:
        raise C.FeatureError(f"{ob.name} has no vertex groups naming its parts: label the parts (a vertex group per part) before binding")
    out = {}
    for name, idx in parts.items():
        role = roles.get(name)
        if role not in ROLES:
            raise C.FeatureError(f"part {name} has no material role: the user or the recipe says metal | leather | cloth | embroidery, never the render's colour")
        ov = (bind_overrides or {}).get(name, {})
        mode = ov.get("mode") or ("rigid" if role == "metal" else "restrict")
        if mode not in MODES:
            raise C.FeatureError(f"part {name}: mode is rigid | restrict | blend")
        if role == "metal" and mode == "blend":
            raise C.FeatureError(f"part {name} is metal: metal is placed by one rigid transform; ask for a ruled cut (original vertex ids) to split it")
        _check_bones(ov.get("bones", []), arm)
        h = _hist(ob, arm, idx)
        if mode == "rigid":
            bones = ov.get("bones") or [max(h, key=h.get)]
            if len(bones) != 1:
                raise C.FeatureError(f"part {name} is rigid: exactly one bone (got {bones})")
            reason = ov.get("reason") or f"{h[bones[0]]:.0%} of its vertices are nearest {bones[0]}"
        else:
            bones = ov.get("bones") or sorted(b for b, f in h.items() if f >= 0.1)
            reason = ov.get("reason") or "weighted by position from the body's own weights, restricted to the bones its geometry spans"
        fallback = ov.get("fallback")
        if fallback is not None and fallback not in bones:
            raise C.FeatureError(f"part {name}: the fallback {fallback!r} must be one of its bones {bones}")
        out[name] = {"role": role, "mode": mode, "bones": bones, "group": name, "reason": reason, "vertices": int(len(idx)), "fallback": fallback}
    names = sorted(out)
    seams, opens = [], []
    P = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            shared = np.intersect1d(parts[a], parts[b])
            if not len(shared):
                A, B = parts[a], parts[b]
                if len(A) and len(B):
                    from mathutils import kdtree
                    kd = kdtree.KDTree(len(B))
                    for k, j in enumerate(B):
                        kd.insert(P[j], k)
                    kd.balance()
                    shared = np.array([x for x in A if kd.find_range(P[x], SEAM_EPS)])
            if len(shared):
                row = {"parts": [a, b], "vertices": int(len(shared)), "bones": [out[a]["bones"][0] if out[a]["mode"] == "rigid" else None, out[b]["bones"][0] if out[b]["mode"] == "rigid" else None]}
                seams.append(row)
                if out[a]["mode"] == "rigid" and out[b]["mode"] == "rigid" and out[a]["bones"] != out[b]["bones"]:
                    opens.append({"parts": [a, b], "bones": sorted({out[a]["bones"][0], out[b]["bones"][0]}), "vertices": int(len(shared)),
                                  "why": "two rigid parts of one shell on different bones: the seam opens when the bones move"})
    parent = {n: n for n in names}
    def find(x):
        while parent[x] != x:
            x = parent[x]
        return x
    for s in seams:
        a, b = s["parts"]
        if out[a]["mode"] == "rigid" and out[b]["mode"] == "rigid" and out[a]["bones"] == out[b]["bones"]:
            parent[find(a)] = find(b)
    groups = {}
    for n in names:
        if out[n]["mode"] == "rigid":
            groups.setdefault(find(n), []).append(n)
    rigid_groups = sorted(sorted(g) for g in groups.values() if len(g) > 1)
    d = Path(root) / out_dir
    d.mkdir(parents=True, exist_ok=True)
    (d / "bind_plan.json").write_text(json.dumps({"piece": ob.name, "parts": out, "rigid_groups": rigid_groups}, indent=1))
    (d / "seams.json").write_text(json.dumps({"seams": seams, "seam_opens": opens}, indent=1))
    state = _load(root, out_dir)
    state["plan"] = {"piece": ob.name, "armature": arm.name, "parts": out, "seam_opens": opens, "rigid_groups": rigid_groups, "roles": roles}
    _save(root, out_dir, state)
    return {"ok": True, "parts": out, "seams": seams, "seam_opens": opens, "rigid_groups": rigid_groups, "files": ["bind_plan.json", "seams.json"]}


MATCH_MAX_DISTANCE = 0.5                # m: the reach of a part's match on its own body region (receipt states it)
MATCH_MAX_ANGLE = 30.0                  # deg, with the flip for single-sided shells (canon 07 B.2)


def _body_regions(body, arm, names):
    """The posed body as triangles with their weights: (W per body vertex over ``names``, V, T, the dominant bone of each
    triangle - the bone with most summed weight over its corners: the triangle's REGION)."""
    from . import rig as _rig
    V, T = _rig._body_mesh(body)
    gn, Wg = WT._read(body, {b.name for b in arm.data.bones})
    if len(Wg) != len(V):
        raise C.FeatureError(f"{body.name}: its evaluated mesh has {len(V)} vertices and its data {len(Wg)}: the body must carry only its Armature modifier")
    ix = {b: i for i, b in enumerate(names)}
    Wb = np.zeros((len(V), len(names)))
    for k, g in enumerate(gn):
        Wb[:, ix[g]] = Wg[:, k]
    dom = Wb[T].sum(axis=1).argmax(axis=1)
    has = Wb[T].sum(axis=(1, 2)) > 0
    return Wb, V, T, np.where(has, dom, -1)


def _allowed_ancestor(bone, allowed, parents):
    seen = set()
    while bone is not None and bone not in allowed and bone not in seen:
        seen.add(bone)
        bone = parents.get(bone)
    return bone if bone in allowed else None


def _restrict_part(ob, idx, plan, part, parents, names, Wb, V, T, tri_bone):
    """One restrict part's rows over ``names`` (canon 07 B.1-B.4): welded vertices; the nearest point on the body's OWN
    REGION for the part (triangles whose dominant bone is an allowed bone or descends from one) within MATCH_MAX_DISTANCE
    and MATCH_MAX_ANGLE (or flipped); barycentric body weights moved to their nearest allowed ancestor, else the part's
    fallback; the unmatched inpainted over the welded part; a bone with neither ancestor nor fallback is refused by name,
    and so is any vertex left with no weight."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    allowed = set(plan["bones"])
    region = np.array([b >= 0 and _allowed_ancestor(names[b], allowed, parents) is not None for b in tri_bone], bool)
    sel = np.flatnonzero(region)
    if not len(sel):
        raise G.ZeroWeightError([int(i) for i in idx[:50]], int(len(idx)), f"part {part} (the body has no surface on its bones {sorted(allowed)})")
    tree = BVHTree.FromPolygons([tuple(v) for v in V], [tuple(t) for t in T[sel]])
    mw = ob.matrix_world
    P = np.array([(mw @ ob.data.vertices[i].co)[:] for i in idx])
    N = np.array([(mw.to_3x3() @ ob.data.vertices[i].normal).normalized()[:] for i in idx])
    keys = G.weld_keys(P)
    Nw = np.zeros_like(N)
    np.add.at(Nw, keys, N)
    cos_lim = np.cos(np.radians(MATCH_MAX_ANGLE))
    rows = np.zeros((len(idx), len(names)))
    matched = np.zeros(len(idx), bool)
    for k in np.unique(keys):
        loc, nor, fi, dist = tree.find_nearest(Vector(P[k]), MATCH_MAX_DISTANCE)
        if loc is None:
            continue
        n = Nw[k] / max(float(np.linalg.norm(Nw[k])), 1e-12)
        if abs(float(n @ np.array(nor[:]))) < cos_lim:
            continue
        a, b, c = V[T[sel[fi]]]
        nrm = np.cross(b - a, c - a)
        q = np.array(loc[:])
        area2 = float(nrm @ nrm)
        l1 = float(np.cross(c - b, q - b) @ nrm) / area2 if area2 > 0 else 1 / 3
        l2 = float(np.cross(a - c, q - c) @ nrm) / area2 if area2 > 0 else 1 / 3
        rows[k] = np.array([l1, l2, 1 - l1 - l2]) @ Wb[T[sel[fi]]]
        matched[k] = True
    rows, matched = rows[keys], matched[keys]
    present = [names[j] for j in np.flatnonzero(rows.max(axis=0) > WT.EPS)]
    table = {}
    for b in present:                                   # canon 07 B.4 (Titan weight_profile.remap_table) over the bones that carry weight
        t = _allowed_ancestor(b, allowed, parents) or plan.get("fallback")
        if t is None:
            raise C.FeatureError(f"part {part}: bone {b!r} carries weight here and has no allowed ancestor and there is no fallback: name its "
                                 f"fallback (bind_overrides {{{part!r}: {{'fallback': <one of {sorted(allowed)}>}}}}) or widen its bones")
        table[b] = t
    out = np.zeros_like(rows)
    for j, b in enumerate(names):
        if b in table and rows[:, j].any():
            out[:, names.index(table[b])] += rows[:, j]
    if (~matched).any():
        local = {int(v): k for k, v in enumerate(idx)}
        edges = [(local[e.vertices[0]], local[e.vertices[1]]) for e in ob.data.edges if e.vertices[0] in local and e.vertices[1] in local]
        out = G.inpaint_harmonic(len(idx), edges, matched & (out.sum(axis=1) > WT.EPS), out, keys=keys)
    s = out.sum(axis=1)
    bad = np.flatnonzero(s <= WT.EPS)
    if len(bad):
        raise G.ZeroWeightError([int(idx[i]) for i in bad[:50]], int(len(bad)), f"part {part}")
    return out / s[:, None]


def weights(piece, armature, out_dir, body_object, root):
    state = _load(root, out_dir)
    if "plan" not in state:
        raise C.FeatureError("run stage plan first: the weights follow the plan")
    pl = state["plan"]
    ob = C.need_object(piece)
    arm = C.need_object(armature, "ARMATURE")
    if not body_object:
        raise C.FeatureError("name body_object (a skinned body in the scene): the native sidecar sampler is not built, so the body's weights come from an object (an approximation)")
    parts = _parts(ob)
    bones = {b.name for b in arm.data.bones}
    n = len(ob.data.vertices)
    names = sorted(bones)
    W = np.zeros((n, len(names)))
    ix = {b: i for i, b in enumerate(names)}
    restrict = [p for p, r in pl["parts"].items() if r["mode"] != "rigid"]
    if restrict:
        body = C.need_object(body_object)
        tri_W, tri_V, tri_T, tri_bone = _body_regions(body, arm, names)
        parents = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        for p in restrict:
            W[parts[p]] = _restrict_part(ob, parts[p], pl["parts"][p], p, parents, names, tri_W, tri_V, tri_T, tri_bone)
    for p, r in pl["parts"].items():
        if r["mode"] == "rigid":
            idx = parts[p]
            W[idx] = 0
            W[idx, ix[r["bones"][0]]] = 1.0                      # metal is never blended: a rigid part wins on any vertex it shares
    fit = C.duplicate(ob, "_fit")
    for g in list(fit.vertex_groups):
        fit.vertex_groups.remove(g)
    for m in [m for m in fit.modifiers if m.type == "ARMATURE"]:
        fit.modifiers.remove(m)
    keep = [i for i in range(len(names)) if W[:, i].max() > WT.EPS]
    WT._write(fit, [names[i] for i in keep], W[:, keep])
    mod = fit.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    state["weights"] = {"object": fit.name, "body_object": body_object, "pose": _pose_record(arm)}
    _save(root, out_dir, state)
    return {"ok": True, "object": fit.name, "weights_source": f"{body_object} (a scene body: an approximation, not the native sidecar)", "groups": len(keep)}


def _pose_record(arm):
    """The armature's pose as data (every pose bone's matrix_basis, rounded) and its sha256: the fit pose the weights were sampled at."""
    rows = {pb.name: [round(float(x), 9) for row in pb.matrix_basis for x in row] for pb in arm.pose.bones}
    return {"sha256": hashlib.sha256(json.dumps(rows, sort_keys=True).encode()).hexdigest(), "basis": rows}


def _bone_maps(arm, names):
    """(b, 4, 4): per bone the world map from rest to the current pose, M_b = Posed_b Rest_b^-1 (canon 04 B)."""
    bpy.context.view_layer.update()
    mw = np.array(arm.matrix_world)
    return np.array([mw @ np.array(arm.pose.bones[n].matrix) @ np.linalg.inv(mw @ np.array(arm.data.bones[n].matrix_local)) for n in names])


def return_report(piece, armature, out_dir, root):
    """Return the piece bound at the fit pose to the native REST pose by the exact inverse of its blended transform (canon 04):
    a new object ``<piece>_rest`` whose forward skinning by the fit pose reproduces the fit geometry; refused when the pose has
    changed since the weights were sampled, when a vertex's blend is singular (named), or when a metal part's rest is not a
    similarity of its source within RETURN_METAL_MAX_MM."""
    state = _load(root, out_dir)
    if "weights" not in state:
        raise C.FeatureError("run stage weights first")
    ob = C.need_object(piece)
    arm = C.need_object(armature, "ARMATURE")
    fit = C.need_object(state["weights"]["object"])
    if (state["weights"].get("pose") or {}).get("sha256") != _pose_record(arm)["sha256"]:
        raise C.FeatureError("the weights were sampled at another pose: put the armature back in the fit pose, or re-run stage weights at it")
    names, W = WT._read(fit, {b.name for b in arm.data.bones})
    if not names:
        raise C.FeatureError(f"{fit.name} has no bone weights: run stage weights")
    s = W.sum(axis=1)
    if (s <= WT.EPS).any():
        raise C.FeatureError(f"{int((s <= WT.EPS).sum())} vertices of {fit.name} have no weight: re-run stage weights")
    W = W / s[:, None]
    mw = np.array(fit.matrix_world)
    co = np.empty(len(fit.data.vertices) * 3)
    fit.data.vertices.foreach_get("co", co)
    P = co.reshape(-1, 3) @ mw[:3, :3].T + mw[:3, 3]
    mats = _bone_maps(arm, names)
    try:
        rest = G.lbs_inverse(P, W, mats)                                    # the inverse OF THE BLEND, never the blend of inverses
    except G.SingularBlendError as e:
        rows = [dict(v, bones={names[j]: round(float(W[v["vertex"], j]), 4) for j in np.flatnonzero(W[v["vertex"]] > WT.EPS)}) for v in e.vertices[:10]]
        raise C.FeatureError(f"{e}: {rows}")
    parts = _parts(ob)
    metal = {}
    for p, r in state["plan"]["parts"].items():
        if r["role"] == "metal" and len(parts.get(p, [])) >= 3:
            f = V.rigid_fit(P[parts[p]], rest[parts[p]], with_scale=True)
            metal[p] = {"scale": round(f["scale"], 6), "rms_mm": round(f["rms_m"] * 1000, 5), "max_mm": round(f["max_m"] * 1000, 5)}
            if f["max_m"] * 1000 > RETURN_METAL_MAX_MM:
                raise C.FeatureError(f"metal part {p}'s returned rest is {f['max_m'] * 1000:.3f} mm from a similarity of its source: a metal part was blended (canon 03 INV-03.2); bind it to one bone")
    name = ob.name + "_rest"
    if bpy.data.objects.get(name) is not None:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    out = C.duplicate(fit, "_tmp_rest")
    out.name = out.data.name = name
    local = (rest - mw[:3, 3]) @ np.linalg.inv(mw[:3, :3]).T
    out.data.vertices.foreach_set("co", local.astype(np.float32).ravel())
    out.data.update()
    bpy.context.view_layer.update()
    from . import rig as _rig
    posed = _rig._evaluated(out)                                            # Blender's own skinning of the rest by the fit pose
    trip = float(np.linalg.norm(posed - P, axis=1).max()) if len(P) else 0.0
    body = {"object": out.name, "round_trip_max_m": round(trip, 9), "vertices": int(len(P)), "singular": [], "rest_residual": metal,
            "per_metal_part": metal, "pose_sha256": state["weights"]["pose"]["sha256"],
            "note": "the exact inverse of each vertex's blended transform (canon 04); the round trip is Blender's own skinning of the rest by the fit pose"}
    state["return"] = {k: v for k, v in body.items() if k != "note"}
    _save(root, out_dir, state)
    return {"ok": True, **body}


def apply(piece, armature, out_dir, accept_seam_gap_mm, root):
    state = _load(root, out_dir)
    if "weights" not in state:
        raise C.FeatureError("run stage weights first")
    opens = state["plan"]["seam_opens"]
    if opens and accept_seam_gap_mm is None:
        raise C.FeatureError(f"{len(opens)} seam(s) open ({opens[0]['parts']} on {opens[0]['bones']}): two rigid parts of one shell on different bones tear it; rebind them to one bone, or pass accept_seam_gap_mm to accept a gap")
    fit = C.need_object(state["weights"]["object"])
    fit["lw_bound"] = True
    state["apply"] = {"accepted_seam_gap_mm": accept_seam_gap_mm}
    _save(root, out_dir, state)
    return {"ok": True, "object": fit.name, "accepted_seam_gap_mm": accept_seam_gap_mm, "seam_opens": opens}


def report(out_dir, root):
    state = _load(root, out_dir)
    d = Path(root) / out_dir
    return {"ok": True, "stages_done": sorted(k for k in state), "files": sorted(p.name for p in d.iterdir()) if d.exists() else [], "state": state}
