# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""anim_multiview_fit, the pure core: motion from ONE split-screen (front + side) clip, orthographic.

Front gives (x, height), side gives (forward, height); the height is shared. Left and right legs (and arms) are identified from the FRONT view (unambiguous) and the side view's near/far labels are put right
by matching heights, with the previous frame breaking ties. A single view cannot do this (the flat-video blind axis): ``fit_single_view`` is the control that fails identity on the same clip.
The 2D keypoint detector and the Blender silhouette renderer are slots: this module takes keypoints and a cost callback. World axes: X lateral (+ = the character's left), Y forward, Z up; the side panel
shows the character facing LEFT (forward = decreasing u) and is relative to the pelvis (root motion comes from the grid parallax, not from the panels).
Panel split, orthographic calibration, held-frame detection, grid-parallax speed, the panel-sync score and the silhouette refinement are here too. Numpy and PIL only."""

from dataclasses import dataclass

import numpy as np

JOINTS = ["pelvis", "spine", "head", "thigh_l", "calf_l", "foot_l", "thigh_r", "calf_r", "foot_r", "upperarm_l", "lowerarm_l", "hand_l", "upperarm_r", "lowerarm_r", "hand_r"]
IDX = {j: i for i, j in enumerate(JOINTS)}
PAIRS = [("thigh_l", "thigh_r"), ("calf_l", "calf_r"), ("foot_l", "foot_r"), ("upperarm_l", "upperarm_r"), ("lowerarm_l", "lowerarm_r"), ("hand_l", "hand_r")]
LEG = [("thigh_l", "thigh_r"), ("calf_l", "calf_r"), ("foot_l", "foot_r")]
ARM = [("upperarm_l", "upperarm_r"), ("lowerarm_l", "lowerarm_r"), ("hand_l", "hand_r")]
BONES = [("pelvis", "spine"), ("spine", "head"), ("thigh_l", "calf_l"), ("calf_l", "foot_l"), ("thigh_r", "calf_r"), ("calf_r", "foot_r"),
         ("upperarm_l", "lowerarm_l"), ("lowerarm_l", "hand_l"), ("upperarm_r", "lowerarm_r"), ("lowerarm_r", "hand_r")]
SYNC_MIN = 0.8                  # [UNVERIFIED] the two panels must show the same instant
CHARACTER_IOU_MIN = 0.9         # [UNVERIFIED]
HEIGHT_AGREE_PX = 6.0           # [UNVERIFIED] detector noise allowance when the two views' heights are compared
DIVIDER_MIN_JUMP = 8.0          # grey levels of step between a divider and its panel


class MultiviewError(ValueError):
    pass


@dataclass
class Calibration:
    px_per_m: float
    front_origin: tuple          # (u, v) of the world origin (pelvis, feet-level height 0 at v) in the front panel
    side_origin: tuple


def px_per_m_from_mask(mask, height_m):
    rows = np.flatnonzero(np.asarray(mask).any(axis=1))
    if not len(rows):
        raise MultiviewError("an empty silhouette: nothing to calibrate from")
    return float(rows.max() - rows.min() + 1) / float(height_m)


def triangulate(front, side, cal, front_conf=None, side_conf=None):
    """front, side: (n, J, 2) pixel keypoints; returns (n, J, 3) world joints (X lateral, Y forward relative to the pelvis column, Z up)."""
    front, side = np.asarray(front, float), np.asarray(side, float)
    s = cal.px_per_m
    fc = np.ones(front.shape[:2]) if front_conf is None else np.asarray(front_conf, float)
    sc = np.ones(side.shape[:2]) if side_conf is None else np.asarray(side_conf, float)
    X = (front[..., 0] - cal.front_origin[0]) / s
    Y = (cal.side_origin[0] - side[..., 0]) / s
    zf = (cal.front_origin[1] - front[..., 1]) / s
    zs = (cal.side_origin[1] - side[..., 1]) / s
    Z = (zf * fc + zs * sc) / np.maximum(fc + sc, 1e-9)
    return np.stack([X, Y, Z], -1)


def _swap_pairs(a, pairs):
    out = a.copy()
    for p, q in pairs:
        out[..., [IDX[p], IDX[q]], :] = out[..., [IDX[q], IDX[p]], :]
    return out


def _height(a, pairs, which):
    return np.stack([a[:, IDX[n], 1] for n in (p[which] for p in pairs)], 1)


def fix_side_labels(front, side, cal, tie_px=6.0):
    """Put the side view's left/right labels right from the front view. Per limb group and frame, the labelling whose heights match the front's wins; when the heights cannot tell (both feet on the ground, both hands level),
    the labelling that moves least from the previous, already corrected frame wins. Returns (side_fixed, corrected_frames)."""
    out = side.copy()
    corrected = 0
    for t in range(front.shape[0]):
        for group in (LEG, ARM):
            keep = sum(abs(front[t, IDX[a], 1] - out[t, IDX[a], 1]) + abs(front[t, IDX[b], 1] - out[t, IDX[b], 1]) for a, b in group)
            swap = sum(abs(front[t, IDX[a], 1] - out[t, IDX[b], 1]) + abs(front[t, IDX[b], 1] - out[t, IDX[a], 1]) for a, b in group)
            if abs(keep - swap) < tie_px * len(group) and t > 0:
                pred = lambda n: out[t - 1, IDX[n]] + (out[t - 1, IDX[n]] - out[t - 2, IDX[n]] if t > 1 else 0.0)     # constant-velocity prediction, so crossing limbs keep their tracks
                keep = sum(np.linalg.norm(out[t, IDX[a]] - pred(a)) + np.linalg.norm(out[t, IDX[b]] - pred(b)) for a, b in group)
                swap = sum(np.linalg.norm(out[t, IDX[b]] - pred(a)) + np.linalg.norm(out[t, IDX[a]] - pred(b)) for a, b in group)
            if swap < keep:
                out[t] = _swap_pairs(out[t][None], group)[0]
                corrected += 1
    return out, corrected


def bone_dirs(joints):
    out = []
    for parent, child in BONES:
        d = joints[:, IDX[child]] - joints[:, IDX[parent]]
        out.append(d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9))
    return np.stack(out, 1)


def bone_direction_error_deg(true_dirs, rec_dirs):
    dot = np.clip((true_dirs * rec_dirs).sum(-1), -1, 1)
    return np.degrees(np.arccos(dot))


def leg_identity_accuracy(true_joints, rec_joints, indistinct_m=0.02):
    """Per frame: is the recovered LEFT foot closer to the true left foot than to the true right one? Frames where the true feet coincide cannot be told apart and count as right."""
    rel = lambda J, n: J[:, IDX[n]] - J[:, IDX["pelvis"]]          # the panels carry no root motion: compare relative to the pelvis
    tl, tr = rel(true_joints, "foot_l"), rel(true_joints, "foot_r")
    rl = rel(rec_joints, "foot_l")
    ok = np.linalg.norm(rl - tl, axis=1) <= np.linalg.norm(rl - tr, axis=1)
    ok |= np.linalg.norm(tl - tr, axis=1) < indistinct_m
    return float(ok.mean())


def fit(front, side, cal, front_conf=None, side_conf=None):
    front, side = np.asarray(front, float), np.asarray(side, float)
    fixed, corrected = fix_side_labels(front, side, cal)
    J = triangulate(front, fixed, cal, front_conf, side_conf)
    legs = [IDX[n] for pair in LEG for n in pair]
    agree = float((np.abs(front[:, legs, 1] - fixed[:, legs, 1]).max(axis=1) < HEIGHT_AGREE_PX).mean())      # frames whose corrected side legs match the front's heights
    return {"joints": J, "bone_dirs": bone_dirs(J), "leg_identity": {"corrected_frames": int(corrected), "source": "front view (left/right), side labels matched by height", "accuracy_vs_front": agree, "frames_flipped": int(round((1.0 - agree) * len(J)))}, "views": 2}


def fit_single_view(side, cal, lateral_m=0.1):
    """The control: a profile view alone. Near/far labels cannot be corrected (nothing says which leg is the left), so they are taken as detected; the lateral offset is the rest hips', not measured."""
    side = np.asarray(side, float)
    s = cal.px_per_m
    Y = (cal.side_origin[0] - side[..., 0]) / s
    Z = (cal.side_origin[1] - side[..., 1]) / s
    X = np.zeros_like(Y)
    for j in JOINTS:
        if j.endswith("_l"):
            X[:, IDX[j]] = lateral_m
        elif j.endswith("_r"):
            X[:, IDX[j]] = -lateral_m
    J = np.stack([X, Y, Z], -1)
    return {"joints": J, "bone_dirs": bone_dirs(J), "views": 1}


def sync_score(front, side, cal):
    """1 when the two panels show the same instant: the heights of every joint agree frame by frame (the side's labels are matched first)."""
    fixed, _ = fix_side_labels(np.asarray(front, float), np.asarray(side, float), cal)
    d = np.abs(np.asarray(front, float)[..., 1] - fixed[..., 1])
    return float(np.clip(1.0 - d.mean() / (0.02 * cal.px_per_m), 0.0, 1.0))


def check_sync(score, minimum=SYNC_MIN):
    if score < minimum:
        raise MultiviewError(f"panels out of sync; re-generate (sync score {score:.2f} < {minimum})")


def check_character(iou, minimum=CHARACTER_IOU_MIN):
    if iou < minimum:
        raise MultiviewError(f"the clip's character differs from the rig (rest-pose silhouette IoU {iou:.2f} < {minimum})")


def split_panels(frame):
    """Find the divider between two panels and crop them. Refused when there is none: re-generate with the split-screen template."""
    f = np.asarray(frame, float)
    g = f if f.ndim == 2 else f.mean(axis=2)
    W = g.shape[1]
    d = np.abs(np.diff(g, axis=1)).mean(axis=0)
    lo, hi = int(W * 0.3), int(W * 0.7)
    window = d[lo:hi]
    if window.max() < DIVIDER_MIN_JUMP:
        raise MultiviewError("no panel divider found: the clip is not a front + side split screen; re-generate with template anim-split-front-side")
    peaks = np.flatnonzero(window > 0.5 * window.max()) + lo
    c0, c1 = int(peaks.min()) + 1, int(peaks.max())
    left, right = np.asarray(frame)[:, :c0], np.asarray(frame)[:, c1 + 1:]
    return left, right, (c0 + c1) // 2


def duplicate_frames(frames, nominal_fps=24.0, eps=1e-3):
    held = [i for i in range(1, len(frames)) if np.abs(np.asarray(frames[i], float) - np.asarray(frames[i - 1], float)).mean() <= eps * 255]
    unique = len(frames) - len(held)
    return {"held": held, "unique": unique, "true_fps": nominal_fps * unique / len(frames) if frames else 0.0}


def grid_parallax_px_per_frame(frames):
    """Horizontal floor shift per frame by circular cross-correlation of the column profiles of consecutive frames."""
    shifts = []
    for a, b in zip(frames, frames[1:]):
        pa, pb = np.asarray(a, float).mean(axis=0), np.asarray(b, float).mean(axis=0)
        pa, pb = pa - pa.mean(), pb - pb.mean()
        corr = np.fft.ifft(np.fft.fft(pa) * np.conj(np.fft.fft(pb))).real
        k = int(corr.argmax())
        W = len(pa)
        shifts.append(min(k, W - k))
    return float(np.median(shifts))


def speed_mps(px_per_frame, px_per_m, fps):
    return px_per_frame / px_per_m * fps


def bone_rotations(rest_dirs, dirs):
    """Shortest-arc quaternions (w, x, y, z) taking each rest bone direction to the fitted one. Twist about the bone is not observable from two silhouettes and is left at zero."""
    a = np.asarray(rest_dirs, float)
    b = np.asarray(dirs, float)
    a = np.broadcast_to(a, b.shape)
    w = 1.0 + (a * b).sum(-1)
    xyz = np.cross(a, b)
    q = np.concatenate([w[..., None], xyz], -1)
    flip = w < 1e-9
    if flip.any():
        q[flip] = np.concatenate([np.zeros((int(flip.sum()), 1)), np.broadcast_to(np.array([1.0, 0, 0]), (int(flip.sum()), 3))], -1)
    return q / np.maximum(np.linalg.norm(q, axis=-1, keepdims=True), 1e-12)


# ------------------------------------------------------------------------------------------------------------ silhouette refinement
def pose_from_joints(joints):
    d = bone_dirs(joints[None])[0]
    return np.stack([np.arctan2(d[:, 1], d[:, 0]), np.arcsin(np.clip(d[:, 2], -1, 1))], -1)


def joints_from_pose(pose, ref_joints):
    """Rebuild a skeleton from bone angles (azimuth, elevation), keeping the reference bone lengths and the reference's hip/shoulder offsets."""
    J = ref_joints.copy()
    done = {"pelvis"}
    # children placed from their parent in BONES order; roots of limbs keep their reference offset from the pelvis/spine
    for k, (parent, child) in enumerate(BONES):
        length = np.linalg.norm(ref_joints[IDX[child]] - ref_joints[IDX[parent]])
        az, el = pose[k]
        d = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])
        if parent not in done:
            anchor = "pelvis" if parent.startswith("thigh") else "spine"
            J[IDX[parent]] = J[IDX[anchor]] + (ref_joints[IDX[parent]] - ref_joints[IDX[anchor]])
            done.add(parent)
        J[IDX[child]] = J[IDX[parent]] + d * length
        done.add(child)
    return J


def capsule_masks(joints, shape, px_per_m, width_m=0.1, origin=(200.0, 560.0)):
    """Front and side silhouettes of a skeleton drawn as thick bones (the stand-in renderer for tests; the Blender Workbench renderer is the real one)."""
    from PIL import Image, ImageDraw
    H, W = shape
    out = {}
    for name in ("front", "side"):
        im = Image.new("L", (W, H), 0)
        dr = ImageDraw.Draw(im)
        for parent, child in BONES:
            pts = []
            for j in (parent, child):
                X, Y, Z = joints[IDX[j]]
                u = origin[0] + px_per_m * (X if name == "front" else -(Y - joints[IDX["pelvis"]][1]))
                v = origin[1] - px_per_m * Z
                pts.append((u, v))
            dr.line(pts, fill=255, width=max(2, int(width_m * px_per_m)))
        out[name] = np.asarray(im) > 0
    return out


def silhouette_cost(masks, target):
    cost = 0.0
    for k in ("front", "side"):
        a, b = masks[k], target[k]
        inter, union = (a & b).sum(), (a | b).sum()
        cost += 1.0 - (inter / union if union else 1.0)
    return float(cost)


def refine(pose, cost_fn, step_deg=4.0, rounds=6):
    """Coordinate descent on the bone angles: each round tries +/- step on every angle and keeps what lowers the cost; the step halves each round. The history never rises."""
    p = np.array(pose, float)
    best = cost_fn(p)
    hist = [best]
    step = np.radians(step_deg)
    for _ in range(rounds):
        for k in range(p.shape[0]):
            for c in range(2):
                for sgn in (1, -1):
                    q = p.copy()
                    q[k, c] += sgn * step
                    v = cost_fn(q)
                    if v < best - 1e-12:
                        p, best = q, v
        hist.append(best)
        step /= 2
    return p, hist
