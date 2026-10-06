# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""weight_audit, weight_cleanup and weight_transfer: look at skin weights, fix them on a copy, and carry them from a rigged body onto a piece.

* audit: a read-only report (unweighted, sums, influence cap, per-bone, rigid check, side check, competing-bone hotspots); plan recommends rigid or deforming from the bones the geometry spans.
* cleanup: a mutating counterpart on a COPY named ``<name>_wclean`` (normalize, limit, remove_influence, smooth, rigid); removing one bone from more than 40 % of the vertices is not a cleanup and is refused.
* transfer: vertices WELDED by position first (canon 07 B.1, ``weld_m`` 1e-5 m; 0 for an authored rig), closest-surface matching (distance and normal-angle gates) and, for every vertex with no trustworthy match, weight inpainting. engine "algorithmic" is a harmonic fill over the mesh graph (Blender's own
  python); engine "robust" is the paper's method (Abdrashitov et al., SIGGRAPH Asia 2023: robust Laplacian, Q = -L + L M^-1 L, constrained solve) in the science python (libigl, robust_laplacian, scipy)."""

import json
import re
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from .. import canon_geom as G

EPS = 1e-6
MASS_ZEROING = 0.4
LEFT = re.compile(r"(?:^|[_.\-])(l|left)$", re.I)
RIGHT = re.compile(r"(?:^|[_.\-])(r|right)$", re.I)
COMPETE = 0.2


def _bones(arm_ob):
    return {b.name: b for b in arm_ob.data.bones}


def _vertex_weights(ob, bones):
    """[ {bone: weight} ] per vertex, only for groups that are bones."""
    names = {g.index: g.name for g in ob.vertex_groups if g.name in bones}
    return [{names[g.group]: g.weight for g in v.groups if g.group in names and g.weight > 0} for v in ob.data.vertices]


def _side_of(name):
    if LEFT.search(name):
        return "left"
    if RIGHT.search(name):
        return "right"
    return None


def _inferred_side(ob):
    xs = [(ob.matrix_world @ v.co).x for v in ob.data.vertices]
    mid = float(np.mean(xs)) if xs else 0.0
    return "left" if mid > 0.05 else "right" if mid < -0.05 else None


def audit(object, armature, intended=None, max_influences=4, side=None):
    bpy.context.view_layer.update()
    ob = C.need_object(object)
    arm = C.need_object(armature, "ARMATURE")
    bones = _bones(arm)
    if not any(g.name in bones for g in ob.vertex_groups):
        groups = sorted(g.name for g in ob.vertex_groups)
        raise C.FeatureError(f"{ob.name} has no vertex groups named after the bones of {arm.name}: bind first (rig_armor / bind_to_armature); the groups found are: {groups}")
    if not any(m.type == "ARMATURE" for m in ob.modifiers):
        raise C.FeatureError(f"{ob.name} has no Armature modifier: bind first (rig_armor / bind_to_armature)")
    W = _vertex_weights(ob, bones)
    unweighted = sum(1 for w in W if not w)
    over = sum(1 for w in W if len(w) > int(max_influences))
    not_one = sum(1 for w in W if w and abs(sum(w.values()) - 1.0) > 1e-3)
    per_bone = {}
    for w in W:
        for b, x in w.items():
            d = per_bone.setdefault(b, [0, 0.0])
            d[0] += 1
            d[1] += x
    per_bone = {b: {"vertices": n, "mean_w": round(s / n, 4)} for b, (n, s) in sorted(per_bone.items())}
    rigid = {"expected_bone": (intended or {}).get("rigid_bone"), "other_influence_vertices": 0}
    if rigid["expected_bone"]:
        rigid["other_influence_vertices"] = sum(1 for w in W if any(b != rigid["expected_bone"] and x > EPS for b, x in w.items()))
    want = side or _inferred_side(ob)
    wrong = sorted({g.name for g in ob.vertex_groups if g.name in bones and want and _side_of(g.name) not in (None, want) and per_bone.get(g.name)})
    pairs = {}
    for w in W:
        strong = sorted(b for b, x in w.items() if x >= COMPETE)
        if len(strong) >= 2:
            pairs[tuple(strong)] = pairs.get(tuple(strong), 0) + 1
    hotspots = [{"region": "between " + " and ".join(k), "vertices": n, "competing_bones": list(k)} for k, n in sorted(pairs.items(), key=lambda kv: -kv[1])]
    ok = not unweighted and not over and not not_one and not rigid["other_influence_vertices"] and not wrong
    return {"ok": True, "unweighted_vertices": unweighted, "over_influence_vertices": over, "sums_not_one": not_one, "per_bone": per_bone, "rigid_check": rigid,
            "side_check": {"side": want, "groups_on_wrong_side": wrong}, "hotspots": hotspots, "pass": bool(ok), "max_influences": int(max_influences)}


def bone_segments(arm):
    """{bone: (head, end)} in world space for every bone of ``arm``: head -> the head of its continuation child (canon 01
    C.1, canon_geom.chain_ends with the UE limb continuations), never the bone's tail - Blender's glTF import lays a UE
    bone's tail 90 deg off its limb."""
    mw = arm.matrix_world
    lone = {b.name for b in arm.data.bones if b.parent is None and not b.children}      # a one-bone rig: no joint to run to
    heads = {b.name: tuple((mw @ b.head_local)[:]) for b in arm.data.bones if b.name not in lone}
    parents = {b.name: (b.parent.name if b.parent else None) for b in arm.data.bones if b.name not in lone}
    out = G.bone_segments(heads, parents, main_child=G.CONTINUATION) if heads else {}
    for b in arm.data.bones:
        if b.name in lone:
            out[b.name] = (np.array((mw @ b.head_local)[:]), np.array((mw @ b.tail_local)[:]))
    return out


def _seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / max(float(ab @ ab), 1e-12), 0, 1)
    return np.linalg.norm(P - (a + np.outer(t, ab)), axis=1)


def plan(object, armature):
    bpy.context.view_layer.update()
    ob = C.need_object(object)
    arm = C.need_object(armature, "ARMATURE")
    bones = [b for b in arm.data.bones if b.use_deform]
    if not bones:
        raise C.FeatureError(f"{arm.name} has no deforming bones")
    P = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    seg = bone_segments(arm)
    D = np.stack([_seg_dist(P, *seg[b.name]) for b in bones], axis=1)
    near = D.argmin(axis=1)
    hist = {bones[i].name: int((near == i).sum()) for i in range(len(bones)) if (near == i).any()}
    total = len(P)
    ranked = sorted(hist.items(), key=lambda kv: -kv[1])
    dom, dom_n = ranked[0]
    span = [b for b, n in ranked if n / total >= 0.1]
    rigid = dom_n / total >= 0.9
    reason = (f"{dom_n / total:.0%} of the vertices are nearest to {dom}: one bone, a rigid piece" if rigid else
              f"the geometry spans {', '.join(span)} ({', '.join(f'{b} {n / total:.0%}' for b, n in ranked[:4])}): bones that rotate against each other, so it must deform")
    return {"ok": True, "recommendation": "rigid" if rigid else "deforming", "bone": dom if rigid else None, "bones": span if not rigid else [dom], "joint_span": len(span), "reason": reason,
            "histogram": hist}


# ------------------------------------------------------------------------------------------------------------------ cleanup
def _read(ob, bones):
    """(names list, W matrix n_verts x n_groups) for the bone groups of ``ob``."""
    gs = [g for g in ob.vertex_groups if g.name in bones]
    idx = {g.index: i for i, g in enumerate(gs)}
    W = np.zeros((len(ob.data.vertices), len(gs)))
    for v in ob.data.vertices:
        for g in v.groups:
            if g.group in idx:
                W[v.index, idx[g.group]] = g.weight
    return [g.name for g in gs], W


def _write(ob, names, W):
    for g in list(ob.vertex_groups):
        if g.name in names:
            ob.vertex_groups.remove(g)
    groups = [ob.vertex_groups.new(name=n) for n in names]
    for v in range(W.shape[0]):
        for k, g in enumerate(groups):
            if W[v, k] > EPS:
                g.add([v], float(W[v, k]), "REPLACE")


def _region_mask(ob, region):
    n = len(ob.data.vertices)
    if not region:
        return np.ones(n, bool)
    if isinstance(region, dict) and "bbox" in region:
        lo, hi = np.array(region["bbox"][0], float), np.array(region["bbox"][1], float)
        P = np.array([v.co[:] for v in ob.data.vertices])
        return np.all((P >= lo) & (P <= hi), axis=1)
    name = region.get("vertex_group") if isinstance(region, dict) else region
    vg = ob.vertex_groups.get(name)
    if vg is None:
        raise C.FeatureError(f"no vertex group {name!r} for the region; the groups are: {sorted(g.name for g in ob.vertex_groups)}")
    m = np.zeros(n, bool)
    for v in ob.data.vertices:
        if any(g.group == vg.index and g.weight > 0 for g in v.groups):
            m[v.index] = True
    return m


def _normalize(W):
    s = W.sum(axis=1, keepdims=True)
    return np.where(s > EPS, W / np.maximum(s, EPS), W)


def _limit(W, k):
    out = W.copy()
    for i in range(W.shape[0]):
        nz = np.flatnonzero(out[i] > EPS)
        if len(nz) > k:
            drop = nz[np.argsort(out[i, nz])[:-k]]
            out[i, drop] = 0
    return _normalize(out)


def cleanup(object, armature, ops, mirror_from=None):
    src = C.need_object(object)
    arm = C.need_object(armature, "ARMATURE")
    bones = _bones(arm)
    if not ops:
        raise C.FeatureError("name the ops: normalize | limit | remove_influence | smooth | rigid")
    if mirror_from:
        raise C.FeatureError("mirror_from is not built yet: mirroring weights on a piece needs a verified symmetric mesh, which this tool cannot yet check")
    names, W = _read(src, bones)
    if not names:
        raise C.FeatureError(f"{src.name} has no bone vertex groups: bind first (rig_armor / bind_to_armature)")
    n = W.shape[0]
    applied = []
    for op in ops:
        kind = op.get("op")
        before = W.copy()
        if kind == "normalize":
            W = _normalize(W)
        elif kind == "limit":
            W = _limit(W, int(op.get("max_influences", 4)))
        elif kind == "remove_influence":
            b = op.get("bone")
            if b not in names:
                raise C.FeatureError(f"no group {b!r} to remove; the groups are: {names}")
            mask = _region_mask(src, op.get("region")) & (W[:, names.index(b)] > EPS)
            if mask.sum() > MASS_ZEROING * n:
                raise C.FeatureError(f"removing {b} from {int(mask.sum())} of {n} vertices ({mask.sum() / n:.0%}) is not a cleanup: rebind instead (the cap is {MASS_ZEROING:.0%})")
            W[mask, names.index(b)] = 0
            if (W[mask].sum(axis=1) <= EPS).any():
                raise C.FeatureError(f"removing {b} would leave vertices with no weight at all: a cleanup never zeroes a vertex's skinning")
            W[mask] = _normalize(W[mask])
        elif kind == "smooth":
            iters, f = int(op.get("iterations", 2)), float(op.get("factor", 0.5))
            nb = [[] for _ in range(n)]
            for e in src.data.edges:
                a, b = e.vertices
                nb[a].append(b); nb[b].append(a)
            mask = _region_mask(src, op.get("region"))
            for _ in range(iters):
                new = W.copy()
                for i in np.flatnonzero(mask):
                    if nb[i]:
                        new[i] = (1 - f) * W[i] + f * W[nb[i]].mean(axis=0)
                W = new
            W = _normalize(W)
        elif kind == "rigid":
            b = op.get("bone")
            if b not in bones:
                raise C.FeatureError(f"no bone {b!r}; the bones are: {sorted(bones)[:30]}")
            if b not in names:
                names.append(b)
                W = np.hstack([W, np.zeros((n, 1))])
            mask = _region_mask(src, op.get("region"))
            W[mask] = 0
            W[mask, names.index(b)] = 1.0
        else:
            raise C.FeatureError(f"unknown op {kind!r}; normalize | limit | remove_influence | smooth | rigid")
        applied.append({"op": kind, "vertices_changed": int((np.abs(W - before).max(axis=1) > 1e-9).sum())})
    dup = C.duplicate(src, "_wclean")
    for m in dup.modifiers:
        if m.type == "ARMATURE":
            m.object = arm
    _write(dup, names, W)
    return {"ok": True, "object": dup.name, "ops_applied": applied, "audit_after": audit(dup.name, armature)}


# ------------------------------------------------------------------------------------------------------------------ transfer
MAX_DISTANCE_LIMIT = 0.5


def _source_arrays(src, bones):
    """Evaluated (deformed) world vertices, loop triangles, normals and the weight matrix of the bone groups."""
    from mathutils.bvhtree import BVHTree
    ev = src.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    m = ev.matrix_world
    me.calc_loop_triangles()
    V = [m @ v.co for v in me.vertices]
    tris = [tuple(t.vertices) for t in me.loop_triangles]
    tree = BVHTree.FromPolygons(V, tris)
    ev.to_mesh_clear()
    names, W = _read(src, bones)
    return tree, np.array([v[:] for v in V]), np.array(tris), names, W


def transfer(object, source, max_distance=0.05, max_normal_angle=30.0, flip_normals=True, inpaint_mode="point", limit_groups=4, deform_only=True, name="", engine="algorithmic", root=None, weld_m=G.WELD_M):
    import math
    ob = C.need_object(object)
    src = C.need_object(source)
    if not 0 < float(max_distance) <= MAX_DISTANCE_LIMIT:
        raise C.FeatureError(f"max_distance {max_distance} is out of range: > 0 and at most {MAX_DISTANCE_LIMIT} m")
    if engine not in ("algorithmic", "robust"):
        raise C.FeatureError("engine is algorithmic (harmonic fill, Blender's python) or robust (biharmonic, the science python)")
    bpy.context.view_layer.update()
    if not src.vertex_groups:
        raise C.FeatureError(f"{src.name} has no vertex group: there are no weights to transfer")
    arms = [m for m in src.modifiers if m.type == "ARMATURE" and m.object]
    if len(arms) != 1:
        raise C.FeatureError(f"{src.name} must carry exactly one Armature modifier (it has {len(arms)}): the weights are the body's skin")
    arm = arms[0].object
    bones = {b.name: b for b in arm.data.bones if (b.use_deform or not deform_only)}
    if not [g for g in src.vertex_groups if g.name in bones]:
        raise C.FeatureError(f"{src.name} has no vertex group named after a deforming bone of {arm.name}: there are no weights to transfer")
    topo = {"ARRAY", "BEVEL", "BOOLEAN", "DECIMATE", "MIRROR", "REMESH", "SOLIDIFY", "SUBSURF", "TRIANGULATE", "WELD"}
    bad = [m.type for m in ob.modifiers if m.type in topo]
    if bad:
        raise C.FeatureError(f"{ob.name} carries topology modifiers {bad}: apply them first, the weights are per vertex")
    tree, Vs, Ts, gnames, Ws = _source_arrays(src, bones)
    me = ob.data
    me.calc_loop_triangles()
    mw = ob.matrix_world
    Vt = np.array([(mw @ v.co)[:] for v in me.vertices])
    Nt = np.array([(mw.to_3x3() @ v.normal).normalized()[:] for v in me.vertices])
    n = len(Vt)
    matched = np.zeros(n, bool)
    Wt = np.zeros((n, len(gnames)))
    cos_lim = math.cos(math.radians(float(max_normal_angle)))
    from mathutils import Vector
    keys = G.weld_keys(Vt, float(weld_m)) if weld_m else np.arange(n)          # canon 07 B.1: one match per welded vertex
    first = {}
    for i, k in enumerate(keys):
        first.setdefault(int(k), i)
    Nw = np.zeros_like(Nt)
    np.add.at(Nw, keys, Nt)                                                    # the welded vertex's normal: its copies' sum
    for i in range(n):
        if first[int(keys[i])] != i:
            continue
        nrm = Nw[keys[i]]
        Nt[i] = nrm / max(float(np.linalg.norm(nrm)), 1e-12)
        loc, nor, fi, dist = tree.find_nearest(Vector(Vt[i]))
        if loc is None or dist > float(max_distance):
            continue
        c = float(np.dot(Nt[i], np.array(nor[:])))
        if c >= cos_lim or (flip_normals and -c >= cos_lim):
            a, b, cc = Vs[Ts[fi]]
            p = np.array(loc[:])
            v0, v1, v2 = b - a, cc - a, p - a
            d00, d01, d11, d20, d21 = v0 @ v0, v0 @ v1, v1 @ v1, v2 @ v0, v2 @ v1
            den = d00 * d11 - d01 * d01
            u = (d11 * d20 - d01 * d21) / den if abs(den) > 1e-18 else 1 / 3
            w = (d00 * d21 - d01 * d20) / den if abs(den) > 1e-18 else 1 / 3
            bary = np.array([1 - u - w, u, w])
            Wt[i] = bary @ Ws[Ts[fi]]
            matched[i] = True
    rep = np.array([first[int(k)] for k in keys])
    Wt, matched = Wt[rep], matched[rep]                                         # every copy takes its welded vertex's row
    inpainted = int((~matched).sum())
    if inpainted and matched.any():
        if engine == "robust":
            Wt = _robust_fill(ob, Vt, matched, Wt, inpaint_mode)
        else:
            Wt = _harmonic_fill(me, matched, Wt, weld_m)
    if limit_groups:
        Wt = _limit(Wt, int(limit_groups))
    else:
        Wt = _normalize(Wt)
    dup = C.duplicate(ob, "_wt") if not name else C.duplicate(ob, "_tmp")
    if name:
        dup.name = dup.data.name = name
    for g in list(dup.vertex_groups):
        dup.vertex_groups.remove(g)
    for m in [m for m in dup.modifiers if m.type == "ARMATURE"]:
        dup.modifiers.remove(m)
    _write(dup, gnames, Wt)
    mod = dup.modifiers.new("Armature", "ARMATURE")
    mod.object = arm
    unweighted = int((Wt.sum(axis=1) <= EPS).sum())
    hist = {str(k): int(((Wt > EPS).sum(axis=1) == k).sum()) for k in range(1, 5)}
    return {"ok": True, "object": dup.name, "source": src.name, "engine": engine, "matched_fraction": round(float(matched.mean()), 6), "inpainted_vertices": inpainted, "groups_written": len(gnames),
            "max_influences": int(limit_groups), "influence_histogram": hist, "unweighted_vertices": unweighted}


def _harmonic_fill(me, matched, W, weld_m=G.WELD_M):
    """Unmatched vertices take the harmonic fill of their mesh neighbours, matched vertices fixed - over POSITION-WELDED
    vertices (canon 07 B.1, canon_geom.inpaint_harmonic): a smart mesh split at its UV seams is one surface, its duplicates
    carry bit-identical rows and an island with no match of its own is reached through them (golden C04). ``weld_m`` 0
    fills over vertex indices (an authored rig: a weld can invent identity across independent topology, canon 01 D.2)."""
    co = np.empty(len(me.vertices) * 3)
    me.vertices.foreach_get("co", co)
    keys = G.weld_keys(co.reshape(-1, 3), weld_m) if weld_m else None
    edges = np.empty(len(me.edges) * 2, dtype=np.int64)
    me.edges.foreach_get("vertices", edges)
    return G.inpaint_harmonic(len(matched), edges.reshape(-1, 2), matched, W, keys=keys)


def _robust_fill(ob, Vt, matched, W, mode):
    import subprocess  # noqa: F401  (the runner owns the process)
    from .. import runner as RUN
    from .. import settings as S
    import tempfile
    me = ob.data
    me.calc_loop_triangles()
    F = np.array([t.vertices[:] for t in me.loop_triangles], dtype=np.int64)
    with tempfile.TemporaryDirectory() as tmp:
        i, o = Path(tmp) / "in.npz", Path(tmp) / "out.npz"
        np.savez(i, V=Vt, F=F, matched=matched, W=W)
        r = RUN.run("robust_weight_transfer", [str(i), str(o), "surface" if mode == "surface" else "point"], S.load(), timeout=900)
        if r.rc != 0 or not o.exists():
            raise C.FeatureError("the robust engine failed: " + re.sub(r"\s+", " ", r.stdout)[-300:] + " (it needs the science python: LAMPWAY_PYTHON_SCIENCE with numpy scipy libigl robust_laplacian)")
        return np.load(o)["W"]
