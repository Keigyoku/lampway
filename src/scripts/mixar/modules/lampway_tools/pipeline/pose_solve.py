# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 08 (IMPLEMENTATION_PLAN item 7): pose the body to the piece - the closest pose, found by a deterministic sweep.

* SIGN CHECK first (B.1): the first DOF at +20 deg must move its ``expect`` joint the expected way (``canon_geom.check_expect``);
  a failure refuses the run before any sweep ("the sweep would be meaningless").
* Axes in the joint-named grammar (B.2: 'up', 'forward', 'lateral', {'line'}, {'perp'}, a 3-vector), resolved AT REST and applied
  through the bone's joint with everything below it carried (``canon_geom.pose_cs``); never Euler angles on local axes.
* Penetration (B.3): each skin sample rides its bone rigidly; a ray from the projection of the sample onto its posed bone segment
  out to the sample; the first piece hit BEFORE the sample gives depth = |sample - origin| - hit. A REGION includes descendants
  of its seed bones up to the nearest other region, using the actual skeleton parents and retaining each sample's bone.
* Search (B.4): a grid over the first-order DOFs, then each chain link in turn holding the earlier best (coordinate descent).
  Selection: fewest samples over the threshold (summed over regions), then the smallest worst depth, then the smallest pose
  (``selection_key``; INV-08.2 prefers the natural pose).
* ``mirror`` (contract): one DOF turns both sides - the other side's entry is the reflection across x = 0, R(Ma, -deg).
* The ray caster is a seam: ``numpy_hits`` (Moller-Trumbore, the goldens) or a BVH (the Blender tool), same signature.
The receipt is ``pose.json`` (``lampway.fit-pose/1``): entries [{bone, axis (resolved, component space), deg}] replayable by
``pose_cs``, the A-pose and posed region numbers, ``pose_cost_deg``, the posed joints and every sweep row."""

import itertools
import math

import numpy as np

from .. import canon_geom as G
from ..canon_geom.bones import CONTINUATION

SIGN_DEG = 20.0
MAX_RANGE_DEG = 90.0
SCHEMA = "lampway.fit-pose/1"


class PoseError(ValueError):
    pass


def numpy_hits(origins, dirs, max_t, V, T, return_faces=False):
    """(n,) the distance along each unit ray to its first triangle hit within (1e-9, max_t), or inf (Moller-Trumbore)."""
    V, T = np.asarray(V, float), np.asarray(T, int)
    a, b, c = V[T[:, 0]], V[T[:, 1]], V[T[:, 2]]
    e1, e2 = b - a, c - a
    out = np.full(len(origins), np.inf)
    face_ids = np.full(len(origins), -1, dtype=int)
    for i, (o, d) in enumerate(zip(origins, dirs)):
        p = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, p)
        ok = np.abs(det) > 1e-15
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - a
        u = np.einsum("ij,ij->i", s, p) * inv
        q = np.cross(s, e1)
        v = (q @ d) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        m = ok & (u >= -1e-12) & (v >= -1e-12) & (u + v <= 1 + 1e-12) & (t > 1e-9) & (t < max_t[i])
        if m.any():
            face_ids[i] = np.flatnonzero(m)[np.argmin(t[m])]
            out[i] = t[face_ids[i]]
    return (out, face_ids) if return_faces else out


def _ends(ref):
    """{bone: child bone} - the bone's segment runs from its joint to that child's joint (canon 01 C.1); a last bone has none."""
    kids = {}
    for b, t in ref.items():
        if t["parent"] is not None:
            kids.setdefault(t["parent"], []).append(b)
    out = {}
    for b in ref:
        k = kids.get(b, [])
        out[b] = k[0] if len(k) == 1 else (CONTINUATION.get(b) if CONTINUATION.get(b) in k else None)
    return out


SAGITTAL = np.diag([-1.0, 1.0, 1.0])          # the body frame's left/right reflection (x = 0, canon 01)


def _other_side(bone):
    for a, b in (("_l", "_r"), ("_r", "_l")):
        if bone.endswith(a):
            return bone[: -len(a)] + b
    raise PoseError(f"{bone}: mirror needs a sided bone name (_l / _r)")


def _entries(dofs, degs, joints, frame):
    """Pose entries; a DOF with ``mirror`` also turns the other side's bone: R(a, deg) reflected across x = 0 is R(Ma, -deg)."""
    out = []
    for d, g in zip(dofs, degs):
        if g == 0:
            continue
        a = np.asarray(G.resolve_axis(d["axis"], joints, frame), float)
        out.append({"bone": d["bone"], "axis": [round(float(x), 12) for x in a], "deg": float(g)})
        if d.get("mirror"):
            out.append({"bone": _other_side(d["bone"]), "axis": [round(float(x), 12) + 0.0 for x in SAGITTAL @ a], "deg": -float(g)})
    return out


def selection_key(metrics, cost):
    over = sum(m["over"] for m in metrics.values())
    worst = max((m["worst_m"] for m in metrics.values()), default=0.0)
    return (over, round(worst, 9), round(cost, 9))


def _region_members(ref, bones, regions):
    """Partition samples by their nearest configured ancestor without changing skin identity."""
    ancestry = {}
    for bone in sorted(ref):
        chain, seen, current = [], set(), bone
        while current is not None:
            if current not in ref:
                raise PoseError(f"{bone}: missing skeleton parent {current!r}")
            if current in seen:
                raise PoseError(f"{bone}: skeleton parent cycle at {current!r}")
            chain.append(current)
            seen.add(current)
            current = ref[current]['parent']
        ancestry[bone] = chain
    seeds = {}
    for name in sorted(regions):
        for bone in regions[name]['bones']:
            if bone not in ref:
                raise PoseError(f"region {name!r} names unknown skeleton bone {bone!r}")
            if bone in seeds and seeds[bone] != name:
                raise PoseError(f"ambiguous region membership for seed bone {bone!r}: {seeds[bone]!r}, {name!r}")
            seeds[bone] = name
    owners = []
    for bone in bones:
        if bone not in ancestry:
            raise PoseError(f"sample names unknown skeleton bone {bone!r}")
        owners.append(next((seeds[b] for b in ancestry[bone] if b in seeds), None))
    member = {name: np.array([owner == name for owner in owners], dtype=bool) for name in regions}
    empty = sorted(name for name, mask in member.items() if not mask.any())
    if empty:
        raise PoseError("no weighted skin samples in requested regions: " + ', '.join(empty) + "; bind the body or correct the anatomical region seeds before solving")
    return member


def solve(ref, frame, samples, piece, dofs, chain=(), regions=None, hits=numpy_hits, curl_side="", curl_fractions=None, placement_meta=None, classes=None):
    """The closest pose (module docstring). ``ref`` {bone: {parent, rot (x,y,z,w), pos}} at rest; ``samples`` [(point, bone)] at
    rest; ``piece`` (V, T); ``dofs`` / ``chain`` [{bone, axis, range [lo, hi], step, expect?}]; ``regions`` {name: {bones,
    threshold_m}}."""
    from . import pose_receipt as PR
    V,T=piece
    try:
        maps=PR.prepare(placement_meta,V,T) if placement_meta is not None else None
        class_labels=PR.labels(classes,T)
        if classes is not None and maps is None:
            raise ValueError('placement metadata is required with classes')
    except ValueError as error:
        raise PoseError(str(error)) from error
    if not dofs:
        raise PoseError("no degrees of freedom: pass the kind's DOF table (the ranges are a ruling, not a default)")
    for d in list(dofs) + list(chain):
        lo, hi = d["range"]
        if hi - lo > MAX_RANGE_DEG:
            raise PoseError(f"{d['bone']}: a range of {hi - lo:g} deg is wider than {MAX_RANGE_DEG:g}: not 'closest' - split the piece or ask")
        if d["bone"] not in ref or (d.get("mirror") and _other_side(d["bone"]) not in ref):
            raise PoseError(f"the DOF names bone {d['bone']!r} (or its mirror), which the skeleton does not have")
    P = np.array([p for p, _b in samples], float)
    B = [b for _p, b in samples]
    regions = regions or {"all": {"bones": sorted(set(B)), "threshold_m": 0.01}}
    member = _region_members(ref, B, regions)
    rest_joints = {b: t["pos"] for b, t in ref.items()}
    first = dofs[0]
    if "expect" not in first:
        raise PoseError(f"the first DOF ({first['bone']}) needs an expect for the sign check (B.1): which joint moves which way at +{SIGN_DEG:g} deg")
    probe = G.pose_cs(ref, _entries([first], [SIGN_DEG], rest_joints, frame))
    ok, got = G.check_expect(first["expect"], rest_joints, {b: t["pos"] for b, t in probe.items()}, frame, scale_to_cm=100.0)
    if not ok:
        raise PoseError(f"the sign check failed: {first['bone']} at +{SIGN_DEG:g} deg moved {first['expect']['joint']} {got:.2f} cm along "
                        f"{first['expect'].get('along', first['expect'].get('closer_to'))} (needs {first['expect'].get('min_cm', 0)}): the axis is "
                        f"reversed or wrong, and the sweep would be meaningless")
    ends = _ends(ref)
    V, T = piece

    def evaluate(entries, receipt=False):
        posed = G.pose_cs(ref, entries)
        X = np.empty_like(P)
        O = np.empty_like(P)
        for i, (p, b) in enumerate(zip(P, B)):
            r0, r1 = ref[b], posed[b]
            local = G.qrot(G.qinv(r0["rot"]), tuple(p - np.asarray(r0["pos"])))
            X[i] = np.asarray(r1["pos"]) + np.asarray(G.qrot(r1["rot"], local))
            h = np.asarray(r1["pos"])
            e = ends.get(b)
            if e is not None:
                seg = np.asarray(posed[e]["pos"]) - h
                t = float(np.clip((X[i] - h) @ seg / max(seg @ seg, 1e-18), 0.0, 1.0))
                O[i] = h + t * seg
            else:
                O[i] = h
        R = X - O
        L = np.linalg.norm(R, axis=1)
        D = R / np.where(L > 1e-12, L, 1.0)[:, None]
        if receipt:
            t, face_ids = hits(O, D, L, V, T, return_faces=True)
        else:
            t = hits(O, D, L, V, T)
        depth = np.where(np.isfinite(t) & (t < L), L - t, 0.0)
        metrics = {}
        for name, r in regions.items():
            dm = depth[member[name]]
            metrics[name] = {"over": int((dm > r["threshold_m"]).sum()), "fraction": round(float((dm > r["threshold_m"]).mean()) if len(dm) else 0.0, 6),
                             "worst_m": round(float(dm.max()) if len(dm) else 0.0, 9), "samples": int(len(dm))}
        if receipt:
            residual=np.zeros(len(P),bool)
            for name,r in regions.items():residual|=member[name]&(depth>r['threshold_m'])
            return metrics,posed,PR.blocking(O,D,t,face_ids,residual,B,maps,class_labels)
        return metrics, posed

    def grid(d):
        lo, hi = d["range"]
        n = int(round((hi - lo) / d["step"]))
        return [lo + k * d["step"] for k in range(n + 1)]

    a_pose, _ = evaluate([])
    sweeps, best = [], None
    for degs in itertools.product(*(grid(d) for d in dofs)):
        m, _ = evaluate(_entries(dofs, degs, rest_joints, frame))
        cost = sum(abs(g) for g in degs)
        sweeps.append({"stage": "dofs", "deg": list(degs), "metrics": m})
        key = selection_key(m, cost)
        if best is None or key < best[0]:
            best = (key, list(degs), m)
    chosen = list(zip(dofs, best[1]))
    for link in chain:
        row = None
        for g in grid(link):
            trial = chosen + [(link, g)]
            m, _ = evaluate(_entries([d for d, _g in trial], [x for _d, x in trial], rest_joints, frame))
            sweeps.append({"stage": link["bone"], "deg": g, "metrics": m})
            key = selection_key(m, sum(abs(x) for _d, x in trial))
            if row is None or key < row[0]:
                row = (key, g, m)
        chosen.append((link, row[1]))
        best = (row[0], None, row[2])
    entries = _entries([d for d, _g in chosen], [g for _d, g in chosen], rest_joints, frame)
    if curl_side:
        from . import finger_pose
        row = None
        fractions = finger_pose.FRACTIONS if curl_fractions is None else tuple(curl_fractions)
        if not fractions:
            raise PoseError("curl_fractions must contain at least one fraction")
        for fraction in fractions:
            trial = entries + finger_pose.entries(ref, curl_side, fraction)
            metrics, _ = evaluate(trial)
            key = selection_key(metrics, sum(abs(e["deg"]) for e in trial))
            sweeps.append({"stage": "finger_curl_to", "side": curl_side, "fraction": fraction, "metrics": metrics})
            if row is None or key < row[0]:
                row = (key, trial, fraction)
        entries = row[1]
    posed_metrics, posed = evaluate(entries)
    blocking={}
    if maps is not None:
        posed_metrics,posed,blocking=evaluate(entries,receipt=True)
    result={"schema": SCHEMA, "entries": entries, "a_pose": a_pose, "posed": posed_metrics,
            "pose_cost_deg": float(sum(abs(e["deg"]) for e in entries)), "joints_m": {b: [float(x) for x in t["pos"]] for b, t in posed.items()},
            "sign_check": {"dof": first["bone"], "deg": SIGN_DEG, "moved_cm": round(got, 6)}, "sweeps": sweeps}
    if maps is not None:
        result.update(blocking=blocking,body_sha256=PR.source_hash(ref,samples),placed_sha256=PR.geometry_hash(V,T))
    return result
