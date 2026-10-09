# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_bind: bind a finished piece to the body's skeleton by the user's weight laws.

* A metal part is placed by ONE rigid transform: one bone, full weight; blending it is refused (a ruled cut, as original vertex ids, splits it). Leather, cloth and embroidery are weighted by POSITION
  (the body's own weights, restricted to the bones the plan allows), so a seam vertex's two copies move together.
* Parts that share a seam and one bone form a rigid group; two rigid parts of one shell on different bones OPEN the seam (``seam_opens``), and ``apply`` refuses unless the user accepts a gap.
* Every part needs a material role from the user or the recipe, never from a render's colour.
Stages: plan -> weights (a copy ``<piece>_fit``; the source is untouched) -> return (the rest residual against the original shell) -> apply (the seam gate) -> report.
The body's weights come from the body PACKAGE's native sidecar (``body``: canon 03 F.6, 07 INV-07.3) - the engine's weights, all
influences, skinned to the armature's current pose (the fit pose) and sampled region- and normal-constrained; a scene body OBJECT
(``body_object``) is still accepted and labelled what it is, an approximation. A cloth/leather vertex within PLATE_FADE_M of a
rigid part takes that part's bone by canon 07 B.5 (rigid_blend, strict): at a seam (the weld tolerance) the bone alone."""

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


def _hist(ob, arm, idx, segments=None):
    from ..canon_geom import native_topology as NT
    native = {b.name for b in arm.data.bones} == set(NT.PARENTS)
    # Canon 07 D: native correctives are authored drivers, not fit bones.
    # Their full graph/endpoints are still validated before sampling distances.
    bones = [b for b in arm.data.bones if b.use_deform and (not native or b.name not in NT.AUXILIARY)]
    P = np.array([(ob.matrix_world @ ob.data.vertices[i].co)[:] for i in idx])
    seg = segments if segments is not None else WT.bone_segments(arm, native_raw=True, posed=True)
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
    segments = None
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
        if segments is None:
            segments = WT.bone_segments(arm, native_raw=True, posed=True)
        h = _hist(ob, arm, idx, segments)
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
PLATE_FADE_M = 0.005                    # canon 07 B.5 / G plate_fade_m: a rigid part's rigidity fades over this from its surface
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


def _sidecar_regions(package, arm, names, root):
    """The NATIVE body as triangles with their weights over ``names``: the package's sidecar skinned to the armature's current
    pose with every influence (canon 05 B: never the GLB's 4), plus the package's sha256 - same shape as _body_regions."""
    from . import fit_body as _FBODY
    from . import native_sidecar as NS
    pkg = Path(package) if Path(package).is_absolute() else Path(root) / package
    rec = _FBODY.need_weights(str(pkg))
    try:
        nb = NS.read(str(pkg / "sidecar.json"))
        maps = _bone_maps(arm, names)
        V, _N = NS.skin(nb, {n: maps[i] for i, n in enumerate(names)})
    except NS.SidecarError as e:
        raise C.FeatureError(f"the body package's sidecar: {e}")
    ix = {b: i for i, b in enumerate(names)}
    Wb = np.zeros((len(V), len(names)))
    for j, b in enumerate(nb.names):
        if b in ix:
            Wb[:, ix[b]] = nb.W[:, j]
    T = nb.T
    dom = Wb[T].sum(axis=1).argmax(axis=1)
    has = Wb[T].sum(axis=(1, 2)) > 0
    return Wb, V, T, np.where(has, dom, -1), rec["package_sha256"]


def _rigid_fade(ob, parts, plan_parts, W, names):
    """canon 07 B.5: every non-rigid vertex within PLATE_FADE_M of a rigid part's surface blends toward that part's bone
    (canon_geom.rigid_blend, strict); a distance within the weld tolerance is the seam itself (distance 0: the bone alone).
    Returns the number of rows changed; two different rigid bones anchoring one vertex are refused by vertex."""
    from mathutils import Vector
    from mathutils.bvhtree import BVHTree
    by_bone = {}
    for p, r in plan_parts.items():
        if r["mode"] == "rigid":
            by_bone.setdefault(r["bones"][0], set()).update(int(i) for i in parts[p])
    soft = sorted({int(i) for p, r in plan_parts.items() if r["mode"] != "rigid" for i in parts[p]} - set().union(*by_bone.values())) if by_bone else []
    if not soft:
        return 0
    mw = ob.matrix_world
    P = [tuple(mw @ v.co) for v in ob.data.vertices]
    ob.data.calc_loop_triangles()
    trees = {}
    for bone, vs in by_bone.items():
        tris = [tuple(t.vertices) for t in ob.data.loop_triangles if all(v in vs for v in t.vertices)]
        if tris:
            trees[bone] = BVHTree.FromPolygons(P, tris)
    ix = {b: i for i, b in enumerate(names)}
    changed = 0
    for i in soft:
        near = {}
        for bone, tree in trees.items():
            hit = tree.find_nearest(Vector(P[i]), PLATE_FADE_M)
            if hit[0] is not None:
                near[bone] = 0.0 if hit[3] <= G.WELD_M else float(hit[3])
        if not near:
            continue
        field = {names[j]: float(W[i, j]) for j in np.flatnonzero(W[i] > WT.EPS)}
        try:
            w = G.rigid_blend(field, near, PLATE_FADE_M)
        except ValueError as e:
            raise C.FeatureError(f"vertex {i} of {ob.name}: {e} - two rigid parts on different bones meet here; rebind one of them")
        W[i] = 0
        for b, x in w.items():
            W[i, ix[b]] = x
        changed += 1
    return changed


def _allowed_ancestor(bone, allowed, parents):
    seen = set()
    while bone is not None and bone not in allowed and bone not in seen:
        seen.add(bone)
        bone = parents.get(bone)
    return bone if bone in allowed else None


def _nearest_compatible(tree, point, normal, distance, cos_limit):
    """Canon07 B.2: an incompatible nearer face cannot hide a valid region match."""
    hit = tree.find_nearest(point, distance)
    if hit[0] is None:
        return None
    compatible = abs(float(normal @ np.asarray(hit[1]))) >= cos_limit
    if compatible:
        # BVH distances/radii are float32. The reported sqrt can round inward:
        # discover through its next representable radius, bounded by the caller,
        # then accept only hits <= the original measured nearest distance.
        radius = min(distance, float(np.nextafter(np.float32(hit[3]), np.float32(np.inf))))
        candidates = [h for h in tree.find_nearest_range(point, radius) if h[3] <= hit[3]]
        candidates.append(hit)
    else:
        candidates = [h for h in tree.find_nearest_range(point, distance) if h[3] <= distance]
    if not candidates:
        return None
    dots = np.abs(np.asarray([h[1][:] for h in candidates]) @ normal)
    good = np.flatnonzero(dots >= cos_limit)
    if not len(good):
        return None
    k = min(good, key=lambda i: (candidates[i][3], candidates[i][2]))
    return candidates[k]


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
        n = Nw[k] / max(float(np.linalg.norm(Nw[k])), 1e-12)
        hit = _nearest_compatible(tree, Vector(P[k]), n, MATCH_MAX_DISTANCE, cos_lim)
        if hit is None:
            continue
        loc, nor, fi, dist = hit
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


def weights(piece, armature, out_dir, body_object, root, body=""):
    state = _load(root, out_dir)
    if "plan" not in state:
        raise C.FeatureError("run stage plan first: the weights follow the plan")
    pl = state["plan"]
    ob = C.need_object(piece)
    arm = C.need_object(armature, "ARMATURE")
    if body and body_object:
        raise C.FeatureError("give body (the fit_body package: its native sidecar) or body_object (a scene body, an approximation), not both")
    if not body and not body_object:
        raise C.FeatureError("name body: the fit_body package whose native sidecar holds the engine's weights (canon 07 INV-07.3); "
                             "a scene body_object is accepted as an approximation")
    parts = _parts(ob)
    bones = {b.name for b in arm.data.bones}
    n = len(ob.data.vertices)
    covered = np.zeros(n, dtype=bool)
    for part in pl["parts"]:
        covered[parts.get(part, [])] = True
    uncovered = np.flatnonzero(~covered)
    if len(uncovered):
        raise C.FeatureError(f"{len(uncovered)} vertices of {ob.name} have no positive membership in a planned part group "
                             f"(vertex IDs {uncovered[:20].tolist()}): assign them to an explicit part group and re-run stage plan; "
                             "for proven loose source geometry, review lampway_scene_cleanup(objects=[<piece>], steps=['loose'], "
                             "plan_only=true) before its copy cleanup. No weights copy was created")
    names = sorted(bones)
    W = np.zeros((n, len(names)))
    ix = {b: i for i, b in enumerate(names)}
    restrict = [p for p, r in pl["parts"].items() if r["mode"] != "rigid"]
    source, pkg_sha = f"{body_object} (a scene body: an approximation, not the native sidecar)", None
    if body and not restrict:
        from . import fit_body as _FBODY
        pkg_sha = _FBODY.need_weights(str(Path(body) if Path(body).is_absolute() else Path(root) / body))["package_sha256"]
        source = f"none sampled: every part is rigid (one bone each); the package {body} carries its native sidecar (package {pkg_sha[:12]})"
    faded = 0
    if restrict:
        if body:
            tri_W, tri_V, tri_T, tri_bone, pkg_sha = _sidecar_regions(body, arm, names, root)
            source = f"the native sidecar of {body} (package {pkg_sha[:12]})"
        else:
            tri_W, tri_V, tri_T, tri_bone = _body_regions(C.need_object(body_object), arm, names)
        parents = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones}
        for p in restrict:
            W[parts[p]] = _restrict_part(ob, parts[p], pl["parts"][p], p, parents, names, tri_W, tri_V, tri_T, tri_bone)
        faded = _rigid_fade(ob, parts, pl["parts"], W, names)
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
    state["weights"] = {"object": fit.name, "body_object": body_object or None, "body": body or None, "body_package_sha256": pkg_sha,
                        "pose": _pose_record(arm)}
    _save(root, out_dir, state)
    return {"ok": True, "object": fit.name, "weights_source": source, "groups": len(keep), "rigid_fade_m": PLATE_FADE_M, "faded_vertices": faded,
            "body_package_sha256": pkg_sha}


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
