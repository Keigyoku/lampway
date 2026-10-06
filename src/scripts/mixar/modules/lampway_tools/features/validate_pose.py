# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_validate, the scene half (engine "blender"): canon 05's receipts for a bound piece through poses, judged by pipeline/validate.py.

The original (pre-fit, own frame) is required: measuring against a baked rest hides a distortion. Per pose and part (role metal |
leather | cloth | embroidery from the user or the recipe, never from a render):
* the pose's ``expect`` is measured on the posed JOINTS first ({joint, along | closer_to, min_cm}); a wrong-sign pose is REFUSED and
  nothing is measured; an expectation on the commanded Euler angle cannot fail and is refused as such (INV-05.5);
* poses are named in the joint grammar ({bone, axis, deg}: canon_geom.resolve_axis, through the bone's joint, the axis given at
  rest and carried by the parents' motion) or by name from pipeline/armour_poses; Euler ``rotate`` poses stay as a stress set;
* rigid residual with the scale FIXED, edge strain as a fraction (p95, max), the SOURCE seam ledger measured in the pose (pairs at
  exactly equal source coordinates across parts; open over 2 mm, max), SURFACE crossings both ways (piece edges through the body,
  body edges through the piece) and inside vertices;
* rest fidelity of every metal part against its original (a similarity, scale recorded) and of the whole piece;
* the positive crossing control: the piece pushed into the skin where it is nearest, capped at half its extent along the push;
  a counter that sees no crossing makes the run UNPROVEN."""

import math

import bpy
import numpy as np
from mathutils import Matrix, Vector

from . import common as C
from . import rig as _rig
from .. import canon_geom as G
from ..pipeline import armour_poses as AP
from ..pipeline import validate as V

SCHEMA = "titan.armour-validation/1"
CONTROL_DEPTH_M = 0.01
SCALE_TO_CM = 100.0                     # the scene is in metres (canon 01 body frame); the recipes' minimums are cm


def _part_vertices(ob, name, roles):
    if len(roles) == 1 or name not in {g.name for g in ob.vertex_groups}:
        return np.arange(len(ob.data.vertices))
    vg = ob.vertex_groups[name]
    return np.array([v.index for v in ob.data.vertices if any(g.group == vg.index and g.weight > 0 for g in v.groups)], dtype=int)


def _joints(arm):
    bpy.context.view_layer.update()
    return {pb.name: tuple((arm.matrix_world @ pb.head)[:]) for pb in arm.pose.bones}


def _frame(rest):
    """Up +Z; forward = foot_l -> ball_l levelled when the rig has both, else the body frame's front (-Y) (canon 01, 09 B.1)."""
    fwd = (0.0, -1.0, 0.0)
    if "foot_l" in rest and "ball_l" in rest:
        d = np.subtract(rest["ball_l"], rest["foot_l"])
        d[2] = 0.0
        if np.linalg.norm(d) > 1e-9:
            fwd = tuple(d / np.linalg.norm(d))
    return {"up": (0.0, 0.0, 1.0), "forward": fwd}


def _entries(pose):
    if isinstance(pose, str):
        if pose not in AP.POSES:
            raise C.FeatureError(f"no pose named {pose!r}; the named poses are: {sorted(AP.POSES)}")
        pose = dict(AP.POSES[pose], name=pose)
    if "curl" in pose:
        return pose, G.expand_pose(pose, {"curl": AP.CURL})
    if pose.get("bones"):
        return pose, list(pose["bones"])
    if pose.get("bone"):
        return pose, [{"bone": pose["bone"], "rotate": pose.get("rotate", [0, 0, 0]), "scale": pose.get("scale")}]
    return pose, []


def _pose(arm, entries, rest, frame):
    """Apply the entries parent-first; returns what restores the rest."""
    saved = {pb.name: pb.matrix_basis.copy() for pb in arm.pose.bones}
    rest_rot = {pb.name: (arm.matrix_world @ pb.matrix).to_3x3() for pb in arm.pose.bones}
    order = {b.name: i for i, b in enumerate(arm.data.bones)}
    for b in sorted(entries, key=lambda e: order.get(e.get("bone"), -1)):
        pb = arm.pose.bones.get(b.get("bone"))
        if pb is None:
            raise C.FeatureError(f"no bone {b.get('bone')!r} in {arm.name!r}; the bones are: {sorted(x.name for x in arm.data.bones)[:30]}")
        if "axis" in b:                                                     # the joint grammar: about a world axis through the joint
            bpy.context.view_layer.update()
            Mw = arm.matrix_world @ pb.matrix
            carry = Mw.to_3x3() @ rest_rot[pb.name].inverted()                  # the parents' motion carries the rest axis
            axis = carry @ Vector(G.resolve_axis(b["axis"], rest, frame))
            head = Mw.translation.copy()
            R = Matrix.Translation(head) @ Matrix.Rotation(math.radians(float(b["deg"])), 4, axis.normalized()) @ Matrix.Translation(-head)
            pb.matrix = arm.matrix_world.inverted() @ (R @ Mw)
        else:                                                               # the Euler stress set (WIKI8): local axes, not portable
            pb.rotation_mode = "XYZ"
            pb.rotation_euler = [math.radians(float(a)) for a in b.get("rotate", [0, 0, 0])]
            if b.get("scale") is not None:
                pb.scale = [float(b["scale"])] * 3 if not isinstance(b["scale"], (list, tuple)) else b["scale"]
    bpy.context.view_layer.update()
    return saved


def _restore(arm, saved):
    for pb in arm.pose.bones:
        pb.matrix_basis = saved[pb.name]
    bpy.context.view_layer.update()


def _edges_of(T):
    e = np.sort(np.concatenate([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]]), axis=1)
    return np.unique(e, axis=0)


def _hits(A, B, V_, T):
    """(k,) bool: segment A-B crosses a triangle of (V, T) - a BVH ray cast over its length."""
    from mathutils.bvhtree import BVHTree
    if not len(A) or not len(T):
        return np.zeros(len(A), bool)
    tree = BVHTree.FromPolygons([tuple(v) for v in V_], [tuple(t) for t in T])
    out = np.zeros(len(A), bool)
    for k, (a, b) in enumerate(zip(A, B)):
        d = Vector(b) - Vector(a)
        L = d.length
        if L > 1e-12:
            loc, _n, _i, dist = tree.ray_cast(Vector(a), d / L, L)
            out[k] = loc is not None and dist < L
    return out


def _crossings(P, idx, piece_T, piece_E, body):
    """{surface, inside} for one part posed at P: its edges through the body + body edges through its triangles, and its vertices
    inside the body (canon 15 sign)."""
    Vb, Tb = body
    sel = np.isin(piece_E, idx).all(axis=1)
    E = piece_E[sel]
    out_edges = int(_hits(P[E[:, 0]], P[E[:, 1]], Vb, Tb).sum())
    Tp = piece_T[np.isin(piece_T, idx).all(axis=1)]
    lo, hi = P[idx].min(0) - 1e-9, P[idx].max(0) + 1e-9
    Eb = _edges_of(Tb)
    a, b = Vb[Eb[:, 0]], Vb[Eb[:, 1]]
    near = np.all((np.maximum(a, b) >= lo) & (np.minimum(a, b) <= hi), axis=1)
    in_edges = int(_hits(a[near], b[near], P, Tp).sum())
    return {"surface": out_edges + in_edges, "piece_edges": out_edges, "body_edges": in_edges}


def _ledger(ob, orig_P, roles):
    """The source seam ledger from the ORIGINAL shell's exact coordinates and the parts (a vertex group per part), or None."""
    names = [p for p in roles if p in {g.name for g in ob.vertex_groups}]
    if len(names) < 2:
        return None
    gid = {ob.vertex_groups[p].index: p for p in names}
    label = []
    for v in ob.data.vertices:
        own = [gid[g.group] for g in v.groups if g.group in gid and g.weight > 0]
        label.append(own[0] if own else None)
    if any(x is None for x in label):
        return None
    return np.array(G.seam_ledger(orig_P, label), int).reshape(-1, 2)


def measure(piece, bound, original, poses, roles, limits=None, body=None, armature=None):
    ob = C.need_object(bound)
    if not original:
        raise C.FeatureError("the original (the pre-fit source shell, in its own frame) is required: measuring against a baked rest hides the distortion the fit made")
    orig = C.need_object(original)
    if len(orig.data.vertices) != len(ob.data.vertices):
        raise C.FeatureError(f"the original has {len(orig.data.vertices)} vertices and the bound piece {len(ob.data.vertices)}: it must be the same mesh before the fit")
    if not roles:
        raise C.FeatureError("roles {part: metal|leather|cloth|embroidery} are required: a role comes from the user or the recipe, never from a render's colour")
    arms = [m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object]
    arm = C.need_object(armature, "ARMATURE") if armature else (arms[0] if arms else None)
    if arm is None:
        raise C.FeatureError(f"{ob.name} has no Armature modifier: bind it first (fit_bind / bind_to_armature)")
    bpy.context.view_layer.update()
    rest = _rig._evaluated(ob)
    O = np.array([(orig.matrix_world @ v.co)[:] for v in orig.data.vertices])
    _V, piece_T = _rig._body_mesh(ob)
    piece_E = _edges_of(piece_T)
    labels = ob if any(p in {g.name for g in ob.vertex_groups} for p in roles) else orig     # a bound copy carries bone groups only: the parts are the source's
    parts = {p: _part_vertices(labels, p, roles) for p in roles}
    whole = V.rigid_fit(O, rest, with_scale=True)
    fidelity = {"scale": round(whole["scale"], 6), "rms_mm": round(whole["rms_m"] * 1000, 4), "max_mm": round(whole["max_m"] * 1000, 4),
                "per_part": {p: G.similarity_receipt(G.similarity_fit(O[idx], rest[idx])) for p, idx in parts.items() if roles[p] == "metal"}}
    ledger = _ledger(labels, O, roles)
    lim = limits or V.DEFAULT_LIMITS
    body_ob = C.need_object(body) if body else None
    joints0 = _joints(arm)
    frame = _frame(joints0)
    judges, rows = [], []
    for raw in poses:
        pose, entries = _entries(raw)
        name = pose.get("name") or "pose"
        exp = pose.get("expect")
        if exp and "joint" not in exp:
            judges.append({"verdict": "REFUSED", "limits_status": lim.get("status", "proposed")})
            rows.append({"name": name, "verdict": "REFUSED", "pieces": {}, "expect": exp,
                         "why": "an expectation on the commanded angle cannot fail (canon 05 INV-05.5): state {joint, along | closer_to, min_cm}, measured on the posed joints"})
            continue
        saved = _pose(arm, entries, joints0, frame)
        try:
            row = {"name": name}
            if exp:
                ok, got = G.check_expect(exp, joints0, _joints(arm), frame, scale_to_cm=SCALE_TO_CM)
                row["expect"] = dict(exp, measured_cm=round(got, 4), ok=ok)
                if not ok:
                    judges.append({"verdict": "REFUSED", "limits_status": lim.get("status", "proposed")})
                    rows.append(dict(row, verdict="REFUSED", pieces={}, why=f"expect failed: {exp['joint']} measured {got:.2f} cm, wanted at least {exp.get('min_cm', 0)} (a wrong-sign pose is refused, not measured)"))
                    continue
            cur = _rig._evaluated(ob)
            bodies = _rig._body_mesh(body_ob) if body_ob is not None else None
            signed = _rig._signed(cur, body_ob)[0] if body_ob is not None else None
        finally:
            _restore(arm, saved)
        pieces = {}
        for part, role in roles.items():
            idx = parts[part]
            fit = V.rigid_fit(rest[idx], cur[idx], with_scale=False)
            sel = np.isin(piece_E, idx).all(axis=1)
            st = V.edge_strain(rest, cur, piece_E[sel])
            if ledger is None:
                seam = {"verdict": "UNVERIFIED", "reason": "no source seam ledger: label every vertex with its part (a vertex group per part, two or more parts)"}
            else:
                mine = ledger[np.isin(ledger, idx).any(axis=1)]
                g = G.seam_gaps(cur, mine, G.SEAM_OPEN_M)
                seam = {"pairs": g["pairs"], "open_over_2mm": g["open"], "max_cm": None if g["max"] is None else round(g["max"] * 100, 5)}
            cross = _crossings(cur, idx, piece_T, piece_E, bodies) if bodies is not None else None
            metrics = {"rigid_max_mm": fit["max_m"] * 1000, "strain_p95": st["p95"], "crossings": None if cross is None else cross["surface"]}
            j = V.judge(role, metrics, lim)
            judges.append(j)
            pieces[part] = {"role": role, "rigid_max_mm": round(fit["max_m"] * 1000, 4), "rigid_residual_mm": round(fit["max_m"] * 1000, 4),
                            "rigid_rms_mm": round(fit["rms_m"] * 1000, 4), "strain_p95": round(st["p95"], 6), "strain_max": round(st["max"], 6), "seam": seam,
                            "surface_crossings": None if cross is None else cross["surface"], "crossings_detail": cross,
                            "inside_vertices": None if signed is None else int((signed[idx] < -1e-6).sum()), "judge": j}
        rows.append(dict(row, pieces=pieces))
    control = {"ok": None, "why": "no body: crossings were not measured"}
    if body_ob is not None:
        Vb, Tb = _rig._body_mesh(body_ob)
        _d, loc, _t = G.closest_points(Vb, Tb, rest) if len(Tb) * len(rest) <= 4_000_000 else _bvh_nearest(rest, Vb, Tb)
        shift = np.array(G.control_shift(list(zip(map(tuple, rest), map(tuple, loc))), CONTROL_DEPTH_M))
        c = _crossings(rest + shift, np.arange(len(rest)), piece_T, piece_E, (Vb, Tb))
        control = {"ok": c["surface"] > 0, "push_m": round(float(np.linalg.norm(shift)), 6), "depth_cap_m": CONTROL_DEPTH_M, "surface_crossings": c["surface"],
                   "why": "the piece pushed into the skin where it is nearest by its distance plus min(1 cm, half its extent along the push)"}
    return {"ok": True, "schema": SCHEMA, "poses": rows, "rest_fidelity": fidelity, "crossing_control": control, "limits": lim,
            "seam_ledger": None if ledger is None else {"origin": "source-exact-coordinate-groups", "pairs": int(len(ledger))},
            "conventions": G.conventions_block(turn_deg="n/a", weld_m="n/a", source_frame="the scene (body frame, metres)"),
            "summary": V.summarize(judges, True if control["ok"] is None else control["ok"])}


def _bvh_nearest(P, Vb, Tb):
    from mathutils.bvhtree import BVHTree
    tree = BVHTree.FromPolygons([tuple(v) for v in Vb], [tuple(t) for t in Tb])
    loc = np.array([tree.find_nearest(Vector(p))[0][:] for p in P])
    return None, loc, None
