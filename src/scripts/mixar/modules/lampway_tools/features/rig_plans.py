# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""auto_rig's body plans, naming options and parts-as-one-character (specs/mixar_docs/auto_rig.md, wiki/auto_rig.md), on the same proven weighting as rig.py
(Blender heat map, proximity fallback for what heat cannot solve).

Plans, each placed from landmarks MEASURED on the mesh standing on Z, facing ``facing`` (default -Y: the head toward -Y):
humanoid / avian  rig.py's UE-named humanoid (avian: the arm chain named wing_*)
quadruped / hexapod / octopod   the ground band's feet clustered per side along the body (2 / 3 / 4 per side); each leg is upper, lower and foot from the
                  body's underside to the ground; a spine from the back to the front at the body's height, a head to the front-most point, a tail when the mesh
                  reaches past the body's back
serpentine / aquatic   a chain of ``chain_bones`` (10) along the mesh's principal axis through its slice centroids
auto              humanoid when it is taller than wide and long, serpentine when it is long and thin, else legged by its feet count (``kind_inferred``)
Naming (humanoid and avian only): ue (default), mixamo (mixamorig:*), metahuman (the UE5 names the MetaHuman body skeleton uses: spine_04/05 and neck_02 are not
created). Tripo's rig naming is not documented here, so naming tripo is refused. ``parts``: several meshes rigged as ONE character, one armature, the
landmarks measured on all of them together."""

import numpy as np
from mathutils import Vector

from . import common as C
from . import rig as RIG

KINDS = ("auto", "humanoid", "quadruped", "hexapod", "octopod", "avian", "serpentine", "aquatic")
LEGS = {"quadruped": 2, "hexapod": 3, "octopod": 4}
NAMINGS = ("ue", "mixamo", "metahuman")
_MIXAMO = {"pelvis": "Hips", "spine_01": "Spine", "spine_02": "Spine1", "spine_03": "Spine2", "neck_01": "Neck", "head": "Head"}
for _s, _S in (("l", "Left"), ("r", "Right")):
    _MIXAMO.update({f"clavicle_{_s}": f"{_S}Shoulder", f"upperarm_{_s}": f"{_S}Arm", f"lowerarm_{_s}": f"{_S}ForeArm", f"hand_{_s}": f"{_S}Hand",
                    f"thigh_{_s}": f"{_S}UpLeg", f"calf_{_s}": f"{_S}Leg", f"foot_{_s}": f"{_S}Foot"})
MIXAMO = {k: "mixamorig:" + v for k, v in _MIXAMO.items()}


def name_map(naming):
    if naming == "tripo":
        raise C.FeatureError("Tripo's rig naming is not documented in Lampway yet: naming tripo is not built (ue | mixamo | metahuman)")
    if naming not in NAMINGS:
        raise C.FeatureError(f"naming is one of {', '.join(NAMINGS)}")
    return MIXAMO if naming == "mixamo" else {}


def _rename(rows, m):
    return [(m.get(b, b), m.get(p, p) if p else None, h, t) for b, p, h, t in rows]


def _clusters_1d(vals, k):
    """k groups of sorted values split at the k-1 largest gaps."""
    v = np.sort(np.asarray(vals))
    if len(v) < k:
        raise C.FeatureError(f"found {len(v)} ground points on a side, fewer than its {k} legs: is the mesh standing on Z with its legs down?")
    gaps = np.argsort(np.diff(v))[::-1][:k - 1]
    cuts = sorted(int(g) + 1 for g in gaps)
    return [grp for grp in np.split(v, cuts)]


def _legged_rows(pts, n_side, facing):
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    h = float(hi[2] - lo[2])
    if h <= 0:
        raise C.FeatureError("the mesh has no height: a creature stands on Z")
    fwd = -1.0 if facing == "-Y" else 1.0                                          # the direction the head points along Y
    left = 1.0 if facing == "-Y" else -1.0
    cx = float((lo[0] + hi[0]) / 2)
    ground = pts[pts[:, 2] < lo[2] + 0.35 * h]
    upper = pts[pts[:, 2] > lo[2] + 0.4 * h]
    if not len(upper):
        raise C.FeatureError("no body above the legs: is the mesh standing on Z?")
    z_hip = float(upper[:, 2].min())
    band = upper[upper[:, 2] <= z_hip + 0.25 * h]                                 # the body proper: a raised head stays out of it
    z_sp = float(band[:, 2].mean())
    y_back, y_front = (float(band[:, 1].max()), float(band[:, 1].min())) if fwd < 0 else (float(band[:, 1].min()), float(band[:, 1].max()))
    rows = []
    spine = [("pelvis", None)] + [(f"spine_{i:02d}", None) for i in (1, 2, 3)]
    ys = np.linspace(y_back, y_front, len(spine) + 1)
    prev = None
    for (name, _), y0, y1 in zip(spine, ys[:-1], ys[1:]):
        rows.append((name, prev, (cx, y0, z_sp), (cx, y1, z_sp)))
        prev = name
    tip_y = float(pts[:, 1].min()) if fwd < 0 else float(pts[:, 1].max())
    front = pts[(pts[:, 1] - y_front) * fwd > 0]
    head_z = float(front[:, 2].max()) if len(front) else z_sp
    if abs(tip_y - y_front) > 0.02 * h:
        rows.append(("neck_01", prev, (cx, y_front, z_sp), (cx, (y_front + tip_y) / 2, (z_sp + head_z) / 2)))
        rows.append(("head", "neck_01", (cx, (y_front + tip_y) / 2, (z_sp + head_z) / 2), (cx, tip_y, head_z)))
    else:                                                                         # no head reaching past the body: its front fifth is the head
        name, par, hd, tl = rows[-1]
        cut = (hd[0], hd[1] + 0.6 * (tl[1] - hd[1]), hd[2])
        rows[-1] = (name, par, hd, cut)
        rows.append(("head", name, cut, tl))
    back_y = float(pts[:, 1].max()) if fwd < 0 else float(pts[:, 1].min())
    if abs(back_y - y_back) > 0.05 * h:
        rows.append(("tail_01", "pelvis", (cx, y_back, z_sp), (cx, back_y, z_sp)))
    for side, sgn in (("l", left), ("r", -left)):
        feet = ground[(ground[:, 0] - cx) * sgn > 0]
        groups = _clusters_1d(feet[:, 1], n_side)
        groups = sorted(groups, key=lambda g: float(np.mean(g)) * fwd, reverse=True)            # front leg first
        for i, g in enumerate(groups, 1):
            sel = feet[(feet[:, 1] >= g.min() - 1e-9) & (feet[:, 1] <= g.max() + 1e-9)]
            lx, ly = float(sel[:, 0].mean()), float(sel[:, 1].mean())
            knee = (z_hip + lo[2]) / 2
            parent = "spine_02" if i == 1 else "pelvis"
            rows += [(f"leg{i}_upper_{side}", parent, (lx, ly, z_hip), (lx, ly, knee)),
                     (f"leg{i}_lower_{side}", f"leg{i}_upper_{side}", (lx, ly, knee), (lx, ly, lo[2] + 0.06 * h)),
                     (f"leg{i}_foot_{side}", f"leg{i}_lower_{side}", (lx, ly, lo[2] + 0.06 * h), (lx, ly + fwd * 0.06 * h, lo[2] + 0.01 * h))]
    return rows


def _chain_rows(pts, n):
    c = pts.mean(axis=0)
    _u, _s, vt = np.linalg.svd(pts - c, full_matrices=False)
    axis = vt[0]
    if axis[np.argmax(np.abs(axis))] < 0:
        axis = -axis
    t = (pts - c) @ axis
    edges = np.linspace(t.min(), t.max(), n + 1)
    joints = []
    for k in range(n + 1):
        p = c + axis * edges[k]
        near = pts[np.abs(t - edges[k]) <= (edges[1] - edges[0]) / 2]
        if len(near):
            off = near.mean(axis=0) - (c + axis * float(((near - c) @ axis).mean()))
            p = p + off
        joints.append(p)
    rows, prev = [], None
    for k in range(n):
        name = f"spine_{k + 1:02d}"
        rows.append((name, prev, tuple(joints[k]), tuple(joints[k + 1])))
        prev = name
    return rows


def infer_kind(pts):
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    dx, dy, dz = (hi - lo)
    if dz > 1.2 * max(dx, dy):
        return "humanoid"
    long_, short = max(dx, dy, dz), min(dx, dy, dz)
    mid = sorted((dx, dy, dz))[1]
    if long_ > 3 * mid and long_ > 3 * short:
        return "serpentine"
    for kind, n in (("octopod", 4), ("hexapod", 3), ("quadruped", 2)):
        try:
            ground = pts[pts[:, 2] < lo[2] + 0.35 * dz]
            cx = (lo[0] + hi[0]) / 2
            side = ground[ground[:, 0] > cx][:, 1]
            g = _clusters_1d(side, n)
            gaps = [float(b.min() - a.max()) for a, b in zip(g[:-1], g[1:])]
            if gaps and min(gaps) > 0.05 * max(dy, dx):
                return kind
        except C.FeatureError:
            continue
    return "quadruped"


def auto_rig(object, kind="humanoid", naming="ue", parts=None, weights="auto", facing="-Y", copy=True, chain_bones=10):
    if kind not in KINDS:
        raise C.FeatureError(f"unknown kind {kind!r}; the kinds are {', '.join(KINDS)}")
    if weights not in ("auto", "proximity"):
        raise C.FeatureError("weights is auto (heat map, proximity fallback) | proximity")
    if facing not in ("-Y", "+Y"):
        raise C.FeatureError("facing is -Y | +Y")
    mapping = name_map(naming)
    srcs = [C.need_object(object)] + [C.need_object(p) for p in (parts or [])]
    meshes = [C.duplicate(s, "_rigged") if copy else s for s in srcs]
    pts = np.concatenate([RIG._world_points(m) for m in meshes])
    inferred = kind == "auto"
    if inferred:
        kind = infer_kind(pts)
    if naming != "ue" and kind not in ("humanoid", "avian"):
        raise C.FeatureError(f"naming {naming} is a humanoid skeleton's: a {kind} rig is named by its own plan (naming ue)")
    if kind in ("humanoid", "avian"):
        rows = RIG._bone_table(RIG.landmarks(pts, facing))
        if kind == "avian":
            wing = {}
            for s in ("l", "r"):
                wing.update({f"upperarm_{s}": f"wing_upper_{s}", f"lowerarm_{s}": f"wing_lower_{s}", f"hand_{s}": f"wing_tip_{s}"})
            rows = _rename(rows, wing)
        rows = _rename(rows, mapping)
    elif kind in LEGS:
        rows = _legged_rows(pts, LEGS[kind], facing)
    else:
        if not 3 <= int(chain_bones) <= 64:
            raise C.FeatureError("chain_bones is 3..64")
        rows = _chain_rows(pts, int(chain_bones))
    arm_ob = RIG._build_armature(meshes[0], f"{srcs[0].name}_rig", rows)
    heat_failed = unweighted = 0
    for m in meshes:
        RIG._parent(m, arm_ob, auto=(weights == "auto"))
        if weights == "proximity":
            RIG._proximity_weights(m, arm_ob)
        miss = RIG._unweighted(m)
        heat_failed += len(miss)
        if miss:
            RIG._proximity_weights(m, arm_ob, only=set(miss))
        unweighted += len(RIG._unweighted(m))
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    return {"armature": arm_ob.name, "source": srcs[0].name, "mesh": meshes[0].name, "meshes": [m.name for m in meshes], "kind": kind, "naming": naming,
            "report": {"bones": len(arm_ob.data.bones), "kind_inferred": inferred, "weights": "heat" if weights == "auto" else "proximity",
                       "heat_failed_vertices": heat_failed, "unweighted_vertices": unweighted, "height": round(float(hi[2] - lo[2]), 4), "facing": facing,
                       "note": "a rig is not a claim of deformation quality: run lampway_pose_test; no control rig, IK or corrective shapes"}}
