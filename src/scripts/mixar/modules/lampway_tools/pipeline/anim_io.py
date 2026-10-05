# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""File-level steps of the animation tools: read the keypoint and pose files, run the pure cores (anim_mv, anim_gates, anim_ref) and write the result files.
Image reading is injected (``load_gray``: path -> 2-D array) so the same code runs in Blender's python (bpy images) and on the host (PIL)."""

import json
import os
from pathlib import Path

import numpy as np

from . import anim_gates as AG
from . import anim_mv as MV
from . import anim_ref as AR

FEET = [MV.IDX["foot_l"], MV.IDX["foot_r"]]


class IOError_(ValueError):
    pass


def _write(path, data):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, sort_keys=True))
    return str(p)


def _kp(path, label):
    d = json.loads(Path(path).read_text())
    k = np.asarray(d["keypoints"], float)
    if k.ndim != 3 or k.shape[1] != len(MV.JOINTS) or k.shape[2] != 2:
        raise IOError_(f"{label} keypoints must be (frames, {len(MV.JOINTS)}, 2) in the order {MV.JOINTS}; got {list(k.shape)}")
    conf = np.asarray(d["conf"], float) if d.get("conf") is not None else None
    return k, conf


def multiview_fit(front, side, calibration=None, cameras=None, fps=24.0, single_view=False, grid_images=None, out="anim/multiview/fit.json"):
    F, fc = _kp(front, "front")
    S, sc = _kp(side, "side")
    if len(F) != len(S):
        raise IOError_(f"the two panels have {len(F)} and {len(S)} frames: they must be the same clip")
    if calibration:
        px = float(calibration["px_per_m"])
    elif cameras:
        cams = json.loads(Path(cameras).read_text())["cameras"]
        px = float(cams["front"]["px_per_m"])
    else:
        raise IOError_("calibration needs px_per_m (or the cameras.json of anim_reference_render): the panels are orthographic and the scale is the figure's, never guessed")
    pel = MV.IDX["pelvis"]
    Fr, Sr = F.copy(), S.copy()
    Fr[..., 0] -= F[:, pel:pel + 1, 0]
    Sr[..., 0] -= S[:, pel:pel + 1, 0]                     # pelvis-relative: the root motion comes from the grid parallax, not from the panels
    floor_f, floor_s = float(F[:, FEET, 1].max()), float(S[:, FEET, 1].max())
    Sr[..., 1] += floor_f - floor_s                        # one floor row for both panels
    cal = MV.Calibration(px_per_m=px, front_origin=(0.0, floor_f), side_origin=(0.0, floor_f))
    sync = MV.sync_score(Fr, Sr, cal)
    MV.check_sync(sync)
    res = MV.fit_single_view(Sr, cal) if single_view else MV.fit(Fr, Sr, cal, fc, sc)
    J = res["joints"]
    dup = MV.duplicate_frames(list(F), fps)
    speed = None
    if grid_images:
        px_frame = MV.grid_parallax_px_per_frame(grid_images)
        speed = MV.speed_mps(px_frame, px, fps)
        J = J.copy()
        J[:, :, 1] += (speed / fps) * np.arange(len(J))[:, None]
    doc = {"ok": True, "views": res["views"], "fps": fps, "joint_order": MV.JOINTS, "joints_m": np.round(J, 5).tolist(), "bone_dirs": np.round(res["bone_dirs"], 5).tolist(),
           "bones": [list(b) for b in MV.BONES], "leg_identity": res.get("leg_identity"), "sync_score": round(sync, 4), "px_per_m": px,
           "duplicate_frames": {k: dup[k] for k in ("held", "unique", "true_fps")}, "root_speed_mps": None if speed is None else round(speed, 4),
           "note": "world axes: X lateral, Y forward (relative to the pelvis unless a grid clip gave the root speed, whose direction is assumed forward), Z up, floor at 0"}
    if single_view:
        doc["warning"] = "single view: near and far legs cannot be told apart; the lateral axis is not measured. Use both panels."
    doc["file"] = _write(out, doc)
    return doc


def capsule_masks_cam(joints_frame, cams, width_m=0.1):
    """The skeleton drawn as thick bones through each recorded camera (pixel-centre rule, numpy): a stand-in for the skinned silhouette."""
    out = {}
    for view, cam in cams.items():
        w, h = cam["size"]
        mask = np.zeros((h, w), bool)
        rad = max(1.0, width_m * cam["px_per_m"] / 2)
        for parent, child in MV.BONES:
            a, b = AR.project(np.array([joints_frame[MV.IDX[parent]], joints_frame[MV.IDX[child]]]), cam)
            x0, x1 = int(max(0, np.floor(min(a[0], b[0]) - rad))), int(min(w - 1, np.ceil(max(a[0], b[0]) + rad)))
            y0, y1 = int(max(0, np.floor(min(a[1], b[1]) - rad))), int(min(h - 1, np.ceil(max(a[1], b[1]) + rad)))
            if x1 < x0 or y1 < y0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
            d = b - a
            t = np.clip(((gx - a[0]) * d[0] + (gy - a[1]) * d[1]) / max(float(d @ d), 1e-12), 0.0, 1.0)
            dist = np.hypot(gx - (a[0] + t * d[0]), gy - (a[1] + t * d[1]))
            mask[y0:y1 + 1, x0:x1 + 1] |= dist <= rad
        out[view] = mask
    return out


def _load_dir(path, load_gray, limit=None):
    names = sorted(n for n in os.listdir(path) if n.lower().endswith(".png"))
    return [load_gray(os.path.join(path, n)) > 0.5 for n in names[:limit]]


def check(poses, masks=None, rendered=None, cameras=None, twist=None, claims=None, load_gray=None, out="anim/check.json"):
    doc = json.loads(Path(poses).read_text())
    J = np.asarray(doc["joints_m"], float)
    fps = float(doc.get("fps", 24.0))
    m = {k: _load_dir(v, load_gray) for k, v in (masks or {}).items() if v}
    if not m.get("side"):
        raise AG.GateError("no side-view mask: a single view cannot settle which leg is in front (the flat-video blind axis); provide both")
    if not m.get("front"):
        raise AG.GateError("no front-view mask: provide both views")
    standin = False
    if rendered:
        r = {k: _load_dir(v, load_gray) for k, v in rendered.items() if v}
    else:
        if not cameras:
            raise AG.GateError("the posed silhouettes are needed: pass rendered (dirs of PNG) or the cameras.json of anim_reference_render (a capsule stand-in is drawn)")
        cams = json.loads(Path(cameras).read_text())["cameras"]
        r = {"front": [], "side": []}
        for i in range(min(len(J), len(m["front"]), len(m["side"]))):
            mk = capsule_masks_cam(J[i], {v: cams[v] for v in ("front", "side")})
            r["front"].append(mk["front"]); r["side"].append(mk["side"])
        standin = True
    n = min(len(m["front"]), len(m["side"]), len(r["front"]), len(r["side"]))
    result = AG.check(J, fps, {"front": m["front"][:n], "side": m["side"][:n]}, {"front": r["front"][:n], "side": r["side"][:n]}, twist, claims)
    result["silhouette_source"] = "capsule stand-in drawn from the recorded cameras (the skinned render is not wired)" if standin else "rendered silhouettes supplied"
    result["frames"] = int(n)
    result["file"] = _write(out, result)
    return result


def loop_export(take, fps=30.0, cycle="auto", skeleton="metahuman_base_skel", loop_tolerance_deg=None, check_result=None, strides_note="", reference_bones=None, out="anim/loop"):
    AG.check_target_skeleton(skeleton)
    if check_result:
        AG.require_check(json.loads(Path(check_result).read_text()))
    d = json.loads(Path(take).read_text())
    q = np.asarray(d["quats"], float)
    bones = d["bones"]
    root = d["root_y_m"]
    take_fps = float(d.get("fps", 24.0))
    if cycle == "auto":
        period = AG.detect_period(q)
    elif str(cycle).startswith("strides:"):
        period = (len(q) - 1) / int(str(cycle).split(":")[1])
    else:
        raise IOError_("cycle is auto or strides:N")
    speed_planted = d.get("planted_foot_speed_mps")
    if speed_planted is None:
        raise IOError_("the take needs planted_foot_speed_mps (from the planted foot's treadmill slide)")
    g = AG.loop_gates(q, period, root, take_fps, float(speed_planted), {"bones": bones, "reference": reference_bones}, strides_note or None, loop_tolerance_deg)
    loop = AG.phase_average_loop(q, period)
    doc = {"ok": g["passed"], "period_frames": round(period, 3), "strides": loop["strides"], "frames": int(len(loop["frames"])), "fps": fps, "gates": g["gates"], "unverified": g["unverified"],
           "skeleton": skeleton, "sequence": None,
           "export": {"state": "not_run", "reason": "the AnimSequence is published through the user's UE editor leg (the shelf's anim-import publisher); no editor is driven from here. The phase-averaged loop is in loop.json."}}
    os.makedirs(out, exist_ok=True)
    _write(os.path.join(out, "loop.json"), {"bones": bones, "quats": np.round(loop["frames"], 6).tolist(), "period_frames": period, "fps": fps, "speed_mps": float(speed_planted)})
    doc["file"] = _write(os.path.join(out, "loop_check.json"), doc)
    return doc
