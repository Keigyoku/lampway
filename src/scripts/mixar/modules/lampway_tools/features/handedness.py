# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Handedness: side_label_check and mirror_pair (specs/wiki/side_label_check.md, mirror_pair.md).

side_label_check is read-only. The lateral axis is world X; the FIGURE's left is +X while it faces -Y (Blender's front) and -X while it faces +Y, the
convention ``features/rig.py`` names (``_l`` is +X with the default facing). The side is the sign of the piece's area-weighted surface centroid against
the body midline (``body_midline_x``, or the mean of an armature's paired ``_l``/``_r`` bone heads); a piece whose lateral extent holds the midline and
whose centroid lies within a quarter of that extent of it is ``center``. Mirror asymmetry is the symmetric mean surface distance (BVH nearest) of the
mesh to its own copy mirrored across its bounding-box centre plane, as a fraction of its bounding diagonal; the pair test mirrors the pair across the
midline and measures the same distance to this piece. Thumb side and palm side are not deterministic from a mesh: that is the vision slot's, never here.

mirror_pair makes the opposite piece on a COPY, only after the typed decision ``design_symmetric`` (a decision row is appended); a measured own
asymmetry above the threshold is refused unless ``force``."""

import json
import re
import time
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from ..meshqa import decisions as D

SIDES = ("left", "right", "center", "paired")
FACINGS = ("-Y", "+Y")
_NAME_SIDE = ((re.compile(r"(?:[_.\- ](?:l|L)|[_.\- ]?[Ll]eft)$"), "left"), (re.compile(r"(?:[_.\- ](?:r|R)|[_.\- ]?[Rr]ight)$"), "right"))
_PAIR_RE = re.compile(r"^(.*?)([_.])([lLrR])$")


def side_from_name(name: str):
    base = re.sub(r"\.\d{3}$", "", name)
    for rx, side in _NAME_SIDE:
        if rx.search(base):
            return side
    return None


def _world_geometry(ob):
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world)
    pts = (m[:3, :3] @ co.reshape(-1, 3).T).T + m[:3, 3]
    polys = [tuple(p.vertices) for p in me.polygons]
    return pts, polys


def _transform_applied(ob) -> bool:
    m3 = np.array(ob.matrix_world)[:3, :3]
    return bool(np.allclose(m3, np.eye(3), atol=1e-6))


def _centroid(pts, polys):
    """Area-weighted surface centroid (vertex mean for a mesh without faces)."""
    if not polys:
        return pts.mean(axis=0)
    tot, acc = 0.0, np.zeros(3)
    for p in polys:
        a = pts[p[0]]
        for i in range(1, len(p) - 1):
            b, c = pts[p[i]], pts[p[i + 1]]
            area = 0.5 * float(np.linalg.norm(np.cross(b - a, c - a)))
            tot += area
            acc += area * (a + b + c) / 3.0
    return acc / tot if tot > 0 else pts.mean(axis=0)


def _tree(pts, polys):
    return BVHTree.FromPolygons([Vector(p) for p in pts], polys, all_triangles=False) if polys else None


def _mean_nearest(points, tree, fallback):
    if tree is None:
        d = np.sqrt(((points[:, None, :] - fallback[None, :, :]) ** 2).sum(-1)).min(axis=1)
        return float(d.mean())
    total = 0.0
    for p in points:
        hit = tree.find_nearest(Vector(p))
        total += hit[3] if hit[0] is not None else 0.0
    return total / max(1, len(points))


def _sym_distance(pa, fa, pb, fb) -> float:
    """Symmetric mean nearest-surface distance between two meshes (each vertex set to the other's surface)."""
    return 0.5 * (_mean_nearest(pa, _tree(pb, fb), pb) + _mean_nearest(pb, _tree(pa, fa), pa))


def _mirror_x(pts, plane_x):
    out = pts.copy()
    out[:, 0] = 2.0 * plane_x - out[:, 0]
    return out


def _flip(polys):
    return [tuple(reversed(p)) for p in polys]


def own_asymmetry(pts, polys) -> float:
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    diag = max(1e-9, float(np.linalg.norm(hi - lo)))
    mid = 0.5 * float(lo[0] + hi[0])
    return _sym_distance(pts, polys, _mirror_x(pts, mid), _flip(polys)) / diag


def _armature_midline(name):
    arm = C.need_object(name, "ARMATURE")
    mw = arm.matrix_world
    heads = {b.name: (mw @ b.head_local) for b in arm.data.bones}
    mids = []
    for n, h in heads.items():
        m = _PAIR_RE.match(n)
        if m and m.group(3) in "lL":
            other = f"{m.group(1)}{m.group(2)}{'r' if m.group(3) == 'l' else 'R'}"
            if other in heads:
                mids.append(0.5 * (h.x + heads[other].x))
    if not mids:
        raise C.FeatureError(f"armature {name!r} has no paired _l/_r bones to measure the midline from: give body_midline_x")
    return float(np.mean(mids))


def _midline(armature, body_midline_x, needed):
    if body_midline_x is not None:
        return round(float(body_midline_x), 6), "body_midline_x"
    if armature:
        return round(_armature_midline(armature), 6), "armature"
    if needed:
        raise C.FeatureError("give body_midline_x or an armature so the side can be measured (the figure's left is not the camera's)")
    return 0.0, "world_origin"


def _side_of(pts, polys, mid, facing):
    c = _centroid(pts, polys)
    offset = float(c[0] - mid)
    lo, hi = float(pts[:, 0].min()), float(pts[:, 0].max())
    extent = max(1e-9, hi - lo)
    if lo <= mid <= hi and abs(offset) <= 0.25 * extent:
        return "center", offset
    left_sign = 1.0 if facing == "-Y" else -1.0
    return ("left" if offset * left_sign > 0 else "right"), offset


def side_label_check(object, declared_side=None, facing="-Y", armature="", body_midline_x=None, pair="", asym_threshold=0.02):
    ob = C.need_object(object)
    if facing not in FACINGS:
        raise C.FeatureError(f"facing is one of {FACINGS} (the direction the figure looks)")
    declared = declared_side or side_from_name(ob.name)
    if declared is None:
        raise C.FeatureError(f"no declared_side and the name {ob.name!r} carries no side (_l/_r, Left/Right): pass declared_side left|right|center|paired")
    if declared not in SIDES:
        raise C.FeatureError(f"declared_side is one of {SIDES}, got {declared!r}")
    thr = float(asym_threshold)
    if not 0.0 < thr <= 1.0:
        raise C.FeatureError("asym_threshold is a fraction of the bounding diagonal in (0, 1]")
    if not _transform_applied(ob):
        raise C.FeatureError(f"{ob.name!r} has an unapplied rotation or scale: apply transform first: orientation is measured in world space")
    mid, mid_src = _midline(armature, body_midline_x, declared in ("left", "right") or bool(pair))
    pts, polys = _world_geometry(ob)
    if len(pts) == 0:
        raise C.FeatureError(f"{ob.name!r} has no vertices")
    reasons = []
    if declared == "paired":
        halves = {"left": 0, "right": 0}
        left_sign = 1.0 if facing == "-Y" else -1.0
        for x in pts[:, 0]:
            halves["left" if (x - mid) * left_sign > 0 else "right"] += 1
        measured = "paired" if min(halves.values()) > 0.2 * len(pts) else max(halves, key=halves.get)
        offset = float(_centroid(pts, polys)[0] - mid)
        if measured != "paired":
            reasons.append(f"declared paired but {halves} vertices lie on each side of the midline: one side only")
    else:
        measured, offset = _side_of(pts, polys, mid, facing)
        if measured != declared:
            reasons.append(f"declared {declared} but the piece sits on the figure's {measured} (centroid {offset:+.4f} m from the midline, facing {facing})")
    asym = own_asymmetry(pts, polys)
    out = {"declared_side": declared, "measured_side": measured, "facing": facing, "midline_x": mid, "midline_source": mid_src,
           "centroid_offset_m": round(offset, 6), "mirror_asymmetry": round(asym, 6), "asym_threshold": thr, "asym_threshold_status": "UNVERIFIED"}
    if pair:
        po = C.need_object(pair)
        if not _transform_applied(po):
            raise C.FeatureError(f"pair {po.name!r} has an unapplied rotation or scale: apply transform first")
        qp, qf = _world_geometry(po)
        diag = max(1e-9, float(np.linalg.norm(pts.max(axis=0) - pts.min(axis=0))))
        d = _sym_distance(pts, polys, _mirror_x(qp, mid), _flip(qf)) / diag
        is_mirror = d <= thr
        pmeasured, _ = _side_of(qp, qf, mid, facing)
        out["pair"] = {"object": po.name, "measured_side": pmeasured, "is_mirror_of": bool(is_mirror), "chamfer_to_mirrored_pair": round(d, 6)}
        if is_mirror:
            reasons.append(f"{po.name!r} is a mirrored copy of {ob.name!r} (distance {d:.4f} of the diagonal <= {thr}): the pair is not its own design")
        if pmeasured == measured and measured in ("left", "right"):
            reasons.append(f"the pair {po.name!r} sits on the same side ({measured})")
    out["pass"] = not reasons
    out["reasons"] = reasons
    out["not_checked"] = ["thumb side, palm versus back and finger count (gloves): the vision slot's, never a mesh measurement"]
    return out


# ---- mirror_pair

PLANES = {"x": 0, "y": 1, "z": 2}
WEIGHTS = ("swap", "drop")
_TMP = "__lw_mirror__"


def _swap_side(name: str, frm: str, to: str) -> str:
    """The other side's name: the rename pair first (either way round), then a trailing _l/_r/.L/.R; unchanged when the name has no side."""
    if frm and name.endswith(frm):
        return name[: -len(frm)] + to
    if to and name.endswith(to):
        return name[: -len(to)] + frm
    m = _PAIR_RE.match(name)
    if m:
        return f"{m.group(1)}{m.group(2)}{ {'l': 'r', 'r': 'l', 'L': 'R', 'R': 'L'}[m.group(3)] }"
    return name


def _plane_origin(origin, pts, axis, armature, body_midline_x):
    if isinstance(origin, str) and "," in origin:
        origin = origin.split(",")
    if isinstance(origin, (list, tuple)):
        if len(origin) != 3:
            raise C.FeatureError("origin is [x, y, z] | 'bounds_centre' | 'body_midline'")
        return [float(v) for v in origin], "given"
    if origin == "bounds_centre":
        return [float(v) for v in 0.5 * (pts.min(axis=0) + pts.max(axis=0))], "bounds_centre"
    if origin == "body_midline":
        if axis != 0:
            raise C.FeatureError("origin body_midline is the lateral (x) plane: use plane x, or give the origin as [x, y, z]")
        mid, src = _midline(armature, body_midline_x, True)
        return [mid, 0.0, 0.0], src
    raise C.FeatureError("origin is [x, y, z] | 'bounds_centre' | 'body_midline'")


def _swap_groups(ob, frm, to) -> list:
    """Rename every sided vertex group to its other side in two passes (so hand_l and hand_r trade names without a collision)."""
    plan = {g.name: _swap_side(g.name, frm, to) for g in ob.vertex_groups}
    plan = {k: v for k, v in plan.items() if v != k}
    for g in ob.vertex_groups:
        if g.name in plan:
            g.name = _TMP + g.name
    out = []
    for g in ob.vertex_groups:
        if g.name.startswith(_TMP):
            old = g.name[len(_TMP):]
            g.name = plan[old]
            out.append([old, plan[old]])
    return out


def mirror_pair(object, root, design_symmetric=None, plane="x", origin="bounds_centre", rename=None, mirror_uv=False, weights="swap", force=False,
                body_midline_x=None, armature="", asym_threshold=0.02, piece="", by="agent", captain_words=""):
    ob = C.need_object(object)
    if design_symmetric is None:
        raise C.FeatureError("record the symmetry decision: this tool never assumes it (design_symmetric=true only when the user says the design is symmetric)")
    if design_symmetric is not True:
        raise C.FeatureError("the design is not symmetric: model the other side, never mirror it (wearer-left/right asymmetry must survive)")
    if plane not in PLANES:
        raise C.FeatureError(f"plane is one of {tuple(PLANES)}")
    if weights not in WEIGHTS:
        raise C.FeatureError(f"weights is one of {WEIGHTS}")
    if by not in ("agent", "captain"):
        raise C.FeatureError("by is agent | captain (who made the symmetry decision)")
    axis = PLANES[plane]
    pts, polys = _world_geometry(ob)
    if len(pts) == 0:
        raise C.FeatureError(f"{ob.name!r} has no vertices")
    o, origin_src = _plane_origin(origin, pts, axis, armature, body_midline_x)
    lo, hi = pts.min(axis=0), pts.max(axis=0)
    diag = max(1e-9, float(np.linalg.norm(hi - lo)))
    own = pts.copy()
    own[:, axis] = (lo[axis] + hi[axis]) - own[:, axis]
    asym = _sym_distance(pts, polys, own, _flip(polys)) / diag
    if asym > float(asym_threshold) and not force:
        raise C.FeatureError(f"measured asymmetry {asym:.4f} of the diagonal (> {asym_threshold}): this piece is not its own mirror. Model the other side; if the user "
                             "confirms the design is symmetric anyway, confirm with force=true")
    rn = rename or {}
    frm, to = str(rn.get("from", "_l")), str(rn.get("to", "_r"))
    target = _swap_side(ob.name, frm, to)
    new = C.duplicate(ob, "")
    new.name = target if target != ob.name else ob.name + "_mirror"
    new.data.name = new.name
    me = new.data
    me.transform(ob.matrix_world)
    refl = Matrix.Identity(4)
    refl[axis][axis] = -1.0
    refl[axis][3] = 2.0 * float(o[axis])
    me.transform(refl)
    me.flip_normals()
    new.parent = None
    new.matrix_world = Matrix.Identity(4)
    if weights == "drop":
        new.vertex_groups.clear()
        renamed = []
    else:
        renamed = _swap_groups(new, frm, to)
    uv_done = False
    if mirror_uv and me.uv_layers:
        for layer in me.uv_layers:
            uv = np.empty(len(layer.data) * 2, dtype=np.float64)
            layer.data.foreach_get("uv", uv)
            uv = uv.reshape(-1, 2)
            uv[:, 0] = 1.0 - uv[:, 0]
            layer.data.foreach_set("uv", uv.ravel())
        uv_done = True
    me.update()
    row = D.row(session=time.strftime("%Y%m%d"), source=ob.name,
                descriptor={"kind": "mirror_pair", "object": ob.name, "result": new.name, "plane": plane, "origin": [round(v, 6) for v in o], "measured_asymmetry": round(asym, 6)},
                question="design_symmetric", options=["true", "false"], answer="true", decider="captain" if by == "captain" else "model",
                how="typed design_symmetric" + (" + force" if force else ""), captain_words=captain_words or None)
    dec = Path(root) / (piece or ob.name) / "decisions.jsonl"
    D.append_rows(dec, [row])
    return {"object": new.name, "source": ob.name, "mirrored_vertices": len(me.vertices), "normals_recalculated": True, "plane": plane,
            "origin": [round(v, 6) for v in o], "origin_source": origin_src, "measured_asymmetry": round(asym, 6), "forced": bool(force),
            "renamed_groups": renamed, "weights": weights, "uv_mirrored": uv_done, "decision_file": str(dec)}
