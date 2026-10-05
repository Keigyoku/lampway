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
import json
from pathlib import Path

import bpy
import numpy as np

from . import common as C
from . import weights as WT
from ..pipeline import validate as V

ROLES = ("metal", "leather", "cloth", "embroidery")
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
    D = np.stack([WT._seg_dist(P, np.array((arm.matrix_world @ b.head_local)[:]), np.array((arm.matrix_world @ b.tail_local)[:])) for b in bones], axis=1)
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
        out[name] = {"role": role, "mode": mode, "bones": bones, "group": name, "reason": reason, "vertices": int(len(idx))}
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
        wt = WT.transfer(ob.name, body_object, max_distance=0.5, max_normal_angle=180.0, flip_normals=True, limit_groups=0, name="__lw_fit_tmp")
        tmp = bpy.data.objects[wt["object"]]
        gnames, WT_ = WT._read(tmp, bones)
        bpy.data.objects.remove(tmp, do_unlink=True)
        T = np.zeros((n, len(names)))
        for k, g in enumerate(gnames):
            T[:, ix[g]] = WT_[:, k]
        for p in restrict:
            idx = parts[p]
            allow = [ix[b] for b in pl["parts"][p]["bones"] if b in ix]
            sub = np.zeros((len(idx), len(names)))
            sub[:, allow] = T[np.ix_(idx, allow)]
            sub = WT._normalize(sub)
            W[idx] = sub
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
    state["weights"] = {"object": fit.name, "body_object": body_object}
    _save(root, out_dir, state)
    return {"ok": True, "object": fit.name, "weights_source": f"{body_object} (a scene body: an approximation, not the native sidecar)", "groups": len(keep)}


def return_report(piece, armature, out_dir, root):
    state = _load(root, out_dir)
    if "weights" not in state:
        raise C.FeatureError("run stage weights first")
    ob = C.need_object(piece)
    fit = C.need_object(state["weights"]["object"])
    from . import rig as _rig
    bpy.context.view_layer.update()
    rest = _rig._evaluated(fit)
    O = np.array([(ob.matrix_world @ v.co)[:] for v in ob.data.vertices])
    parts = _parts(ob)
    res = {}
    for p, r in state["plan"]["parts"].items():
        if r["role"] == "metal":
            f = V.rigid_fit(O[parts[p]], rest[parts[p]], with_scale=True)
            res[p] = {"scale": round(f["scale"], 6), "rms_mm": round(f["rms_m"] * 1000, 5), "max_mm": round(f["max_m"] * 1000, 5)}
    state["return"] = {"rest_residual": res}
    _save(root, out_dir, state)
    return {"ok": True, "rest_residual": res, "note": "the metal parts' similarity to the ORIGINAL shell at rest (the bind is made at the fit pose and returned to rest; scale and residual recorded)"}


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
