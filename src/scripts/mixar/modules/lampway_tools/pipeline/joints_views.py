# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 11 (IMPLEMENTATION_PLAN item 12): joints from orthographic views - the pure leg of ``lampway_joints_from_views``.

Inputs are files under the project root: the cameras ``{cameras: [{name, res, ortho, center, right, up, look}]}`` (pixels right and
DOWN) and the keypoints ``{keypoints_px: {joint: {view: [x, y] | [x, y, confidence]}}}`` (detector=keypoints_json). Each joint is
triangulated (``canon_geom.triangulate_robust``: exact for orthographic cameras; a view missing by more than ``max_px`` is dropped
while the rest still fix the point) and, for a RIG run, moved by the calibration offsets measured on a body with known joints in the
SAME cameras (INV-11.2). Refused: a joint fixed by fewer than two non-parallel views (INV-11.1), a rig run without a calibration, a
calibration made in a different camera framing, a joint the calibration has no offset for. The 2D detector is a model slot
(``detect``): no detector is installed, pending the captain's decision 11-H1."""

import hashlib
import json
import math
import re
from pathlib import Path

import numpy as np

from .. import canon_geom as G
from ..canon_geom.bones import CONTINUATION

project = G.project
MAX_PX = 4.0                                                    # canon 11 G: the robust drop's default miss (pixels)
# Two views that are the only ones fixing a direction cannot say which of them is wrong: dropping either leaves a consistent point.
# "refuse" names both (canon defect: golden C08's outlier is such a tie, dropped by the reference only by order); "drop_worst" is
# the canon reference's rule (needs_decision: the captain may rule the reference's tie-break instead).
AMBIGUOUS = "refuse"
DETECTORS = ("rtmw_wholebody", "rtmpose_hand")


class JointsError(ValueError):
    pass


def _read(root, rel):
    p = Path(rel) if Path(rel).is_absolute() else Path(root) / rel
    try:
        return json.loads(p.read_text())
    except FileNotFoundError:
        raise JointsError(f"{rel}: no such file under the project root") from None


def _cams_sha(cams):
    keep = [{k: c[k] for k in ("name", "res", "ortho", "center", "right", "up", "look") if k in c} for c in cams]
    return hashlib.sha256(json.dumps(keep, sort_keys=True).encode()).hexdigest()


def _cameras(root, cameras):
    cams = _read(root, cameras).get("cameras") or []
    if not cams:
        raise JointsError(f"{cameras}: no cameras ({{cameras: [{{name, res, ortho, center, right, up, look}}]}})")
    return {c["name"]: c for c in cams}, _cams_sha(cams)


def _triangulate(cams, kp, max_px, hidden=()):
    out = {}
    for joint, views in sorted(kp.items()):                    # the views in the file's order (the reference breaks ties by order)
        if joint in hidden:
            continue
        obs = []
        for v, xy in views.items():
            if v not in cams:
                raise JointsError(f"{joint}: keypoint in view {v!r}, which the cameras do not have ({', '.join(sorted(cams))})")
            obs.append((cams[v], float(xy[0]), float(xy[1]), float(xy[2]) if len(xy) > 2 else 1.0, v))
        used = [o for o in obs if o[3] > 0]
        try:
            q = G.triangulate([o[:4] for o in used])
        except ValueError as exc:
            raise JointsError(f"{joint}: {exc} (views: {', '.join(o[4] for o in used) or 'none'})") from None
        while len(used) > 2:                                    # canon_geom.triangulate_robust's rule, keeping the view names
            miss = [math.hypot(*np.subtract(project(o[0], q), o[1:3])) for o in used]
            k = int(np.argmax(miss))
            if miss[k] <= max_px:
                break
            alone = [i for i in range(len(used)) if miss[i] > max_px and _explains(used, i, max_px)]
            if AMBIGUOUS == "refuse" and len(alone) > 1:
                names = ", ".join(f"{used[i][4]} ({miss[i]:.1f} px)" for i in alone)
                raise JointsError(f"{joint}: the outlier is ambiguous - dropping any one of {names} leaves the rest consistent, so no view "
                                  f"can be blamed: fix the keypoint or add a view that fixes the same direction")
            rest = used[:k] + used[k + 1:]
            try:
                q2 = G.triangulate([o[:4] for o in rest])
            except ValueError:
                break
            used, q = rest, q2
        out[joint] = {"pos": q, "views_used": [o[4] for o in used],
                      "residual_px": {o[4]: round(math.hypot(*np.subtract(project(o[0], q), o[1:3])), 6) for o in obs}}
    return out


def _explains(obs, i, max_px):
    """True when the views without ``obs[i]`` still fix the point and all reproject within ``max_px``."""
    rest = obs[:i] + obs[i + 1:]
    try:
        q = G.triangulate([o[:4] for o in rest])
    except ValueError:
        return False
    return all(math.hypot(*np.subtract(project(o[0], q), o[1:3])) <= max_px for o in rest)


def calibrate(cameras, keypoints, known, root, out, max_px=MAX_PX):
    """{offsets, cameras_sha256, sha256, out}: per joint true - triangulated on a body with KNOWN joints (``known``:
    {joints_m: {joint: [x, y, z]}}) seen in these cameras; written to ``out`` for later rig runs."""
    cams, csha = _cameras(root, cameras)
    tri = _triangulate(cams, _read(root, keypoints).get("keypoints_px") or {}, max_px)
    true = _read(root, known).get("joints_m") or {}
    missing = sorted(set(tri) - set(true))
    if missing:
        raise JointsError(f"the known body has no joint for {', '.join(missing)}: calibrate on a body whose joints are all known")
    offsets = G.calibrate(true, {j: r["pos"] for j, r in tri.items()})
    doc = {"schema": "lampway.joints-calibration/1", "cameras_sha256": csha, "max_px": max_px,
           "offsets": {j: [float(x) for x in o] for j, o in sorted(offsets.items())}}
    text = json.dumps(doc, indent=2, sort_keys=True)
    p = Path(out) if Path(out).is_absolute() else Path(root) / out
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return {"offsets": doc["offsets"], "cameras_sha256": csha, "sha256": hashlib.sha256(text.encode()).hexdigest(), "out": out}


def run(cameras, keypoints, root, rig=True, calibration="", max_px=MAX_PX, hidden=(), mesh=None):
    """{joints: {name: {pos_m, views_used, residual_px, calibrated, centred_cm}}, cameras_sha256, calibrated, calibration_sha256,
    hidden, detector}. ``rig=True`` needs ``calibration`` (INV-11.2); ``hidden`` joints (read off a skirt or cloak) are left out.
    ``mesh`` = (V, T) of the example in the cameras' frame: each joint is then centred in its limb's cross-section (canon 11 B.8)."""
    cams, csha = _cameras(root, cameras)
    offsets, cal_sha = None, None
    if calibration:
        p = Path(calibration) if Path(calibration).is_absolute() else Path(root) / calibration
        text = p.read_text() if p.exists() else None
        if text is None:
            raise JointsError(f"{calibration}: no such calibration under the project root")
        cal = json.loads(text)
        if cal.get("cameras_sha256") != csha:
            raise JointsError(f"{calibration} was measured in a different camera framing than {cameras}: calibrate again in these cameras "
                              f"(offsets are a property of the detector in ONE framing)")
        offsets, cal_sha = {j: np.asarray(o, float) for j, o in cal["offsets"].items()}, hashlib.sha256(text.encode()).hexdigest()
    elif rig:
        raise JointsError("a rig run needs a calibration (calibration.json from the MetaHuman in the same cameras; INV-11.2), "
                          "or pass rig=false for uncalibrated joints")
    tri = _triangulate(cams, _read(root, keypoints).get("keypoints_px") or {}, max_px, set(hidden))
    if offsets is not None:
        missing = sorted(set(tri) - set(offsets))
        if missing:
            raise JointsError(f"the calibration has no offset for {', '.join(missing)}: calibrate on a body with those joints")
    pos = {j: r["pos"] + offsets[j] if offsets is not None else r["pos"] for j, r in tri.items()}
    joints = {}
    for j, r in tri.items():
        q, row = pos[j], {"centred": False, "centred_cm": None}
        if mesh is not None:
            d = bone_direction(j, pos)
            if d is None:
                row["centre_skip"] = "no bone direction: neither the next nor the previous joint of its chain is in the set"
            else:
                reach, need = reach_of(j)
                c, hits, why = centre_joint(mesh[0], mesh[1], q, d, reach, need)
                if why:
                    row["centre_skip"] = why
                else:
                    row.update(centred=True, centred_cm=round(float(np.linalg.norm(c - q)) * 100, 6), ring_hits=hits)
                    q = c
        joints[j] = {"pos_m": [float(x) for x in q], "views_used": r["views_used"], "residual_px": r["residual_px"],
                     "calibrated": offsets is not None, **row}
    return {"joints": joints, "cameras_sha256": csha, "calibrated": offsets is not None, "calibration_sha256": cal_sha,
            "hidden": sorted(hidden), "detector": "keypoints_json", "max_px": max_px}


# canon 11 B.8 (grt rig_axi/centre.py): 16 rays in the plane across the bone, reach 5 cm fingers / 8 cm hand and foot / 15 cm else,
# the hits' mean, 3 passes; a ring with fewer than 12 of 16 hits (10 for fingers) is not closed and the joint is left where it is.
CENTRE_RAYS, CENTRE_ITERS = 16, 3
_FINGER = re.compile(r"^(thumb|index|middle|ring|pinky)_0(\d)_(l|r)$")
_SPINE = {"spine_01": "spine_02", "spine_02": "spine_03", "spine_03": "spine_04", "spine_04": "spine_05", "spine_05": "neck_01"}


def reach_of(joint):
    """(reach m, rays that must hit) for ``joint``."""
    if _FINGER.match(joint):
        return 0.05, 10
    if joint.split("_")[0] in ("hand", "foot", "ball"):
        return 0.08, 12
    return 0.15, 12


def _next(joint):
    m = _FINGER.match(joint)
    if m:
        return f"{m[1]}_0{int(m[2]) + 1}_{m[3]}"
    return CONTINUATION.get(joint) or _SPINE.get(joint)


def _reaches(a, b, steps=8):
    """True when b lies on a's continuation chain within ``steps`` bones (intermediate joints may be absent from the set)."""
    for _ in range(steps):
        a = _next(a)
        if a is None:
            return False
        if a == b:
            return True
    return False


def bone_direction(joint, joints):
    """The unit direction of ``joint``'s bone: towards the next joint of the set on its chain, or - a last joint - continuing the line
    from the joint before it; None when the set gives neither."""
    p = np.asarray(joints[joint], float)
    nxt = [k for k in joints if k != joint and _reaches(joint, k)]
    if nxt:
        k = min(nxt, key=lambda k: np.linalg.norm(np.asarray(joints[k], float) - p))
        d = np.asarray(joints[k], float) - p
    else:
        prv = [k for k in joints if k != joint and _reaches(k, joint)]
        if not prv:
            return None
        k = min(prv, key=lambda k: np.linalg.norm(np.asarray(joints[k], float) - p))
        d = p - np.asarray(joints[k], float)
    n = np.linalg.norm(d)
    return d / n if n > 1e-9 else None


def centre_joint(V, T, p, d, reach, min_hits=12, rays=CENTRE_RAYS, iters=CENTRE_ITERS):
    """(point, hits, why): ``p`` moved to the mean of the first surface hits of ``rays`` rays in the plane across ``d`` (``iters``
    passes); ``why`` names a ring that is not closed (fewer than ``min_hits`` hits within ``reach``), and then ``p`` is returned as is."""
    p, d = np.asarray(p, float), np.asarray(d, float) / np.linalg.norm(d)
    u = np.cross(d, [1.0, 0, 0] if abs(d[0]) < 0.9 else [0, 1.0, 0])
    u /= np.linalg.norm(u)
    v = np.cross(d, u)
    L = (np.asarray(V, float) - p) @ np.stack([u, v, d], 1)
    segs = G.slice_segments(L, T, 0.0, axis=2)
    th = 2 * math.pi * np.arange(rays) / rays
    dirs = np.stack([np.cos(th), np.sin(th)], 1)
    c = np.zeros(2)
    hits = 0
    for _ in range(iters):
        t = np.array([G.first_hit(segs, c, e) for e in dirs])
        ok = ~np.isnan(t) & (t <= reach)
        hits = int(ok.sum())
        if hits < min_hits:
            return p, hits, f"the ring is not closed: {hits} of {rays} rays meet the surface within {reach * 100:.0f} cm (needs {min_hits})"
        c = (c + t[ok, None] * dirs[ok]).mean(0)
    return p + c[0] * u + c[1] * v, hits, None


def detect(mesh, detector):
    """The 2D detector slot. None is installed: the canon's RTMW whole-body / RTMPose hand (rtmlib, ONNX, CPU) wait on the captain's
    decision 11-H1 (local or subscription); until then keypoints come from a file (detector=keypoints_json)."""
    if detector not in DETECTORS:
        raise JointsError(f"unknown detector {detector!r} ({', '.join(DETECTORS)}, or keypoints_json with a keypoints file)")
    raise JointsError(f"the {detector} detector is not installed: it is a model slot pending the captain's decision 11-H1 (rtmlib ONNX "
                      f"locally or a subscription); pass detector=keypoints_json with a keypoints file meanwhile")
