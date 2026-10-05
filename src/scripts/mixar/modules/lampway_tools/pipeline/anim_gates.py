# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The measurable gates of a motion take (generation/anim_check.md, anim_loop_export.md): outline overlap, leg identity, stance-foot slide and plant, twist, and the loop and export gates.

Thresholds are PROPOSED (the specs say so) and live in ``THRESHOLDS``; a gate that was not measured is listed under ``unverified`` and is never a pass. World axes: X lateral, Y forward, Z up, metres;
the floor is Z = 0. Rotations are quaternions (w, x, y, z). Numpy only."""

import numpy as np

from . import anim_mv as MV

THRESHOLDS = {"G-OUT-front": 0.80, "G-OUT-side": 0.85, "G-LEGS": 0.85, "G-TWIST": 5.0, "G-FOOT-SLIDE": 1.0, "G-FOOT-PLANT": 1.0,
              "G-LOOP": 1.0, "G-LOOP-ROOT": 1.0, "G-LOOP-WRAP": 1.5, "G-SPEED": 0.05, "G-STRIDES": 4}
STANCE_HEIGHT_M = 0.015          # a foot this close to the floor is in stance [proposed]
LIFT_HEIGHT_M = 0.02             # a foot this far above the floor is lifted [proposed]


class GateError(ValueError):
    pass


def _gate(gid, value, passed, message="", **extra):
    return {"id": gid, "value": value, "threshold": THRESHOLDS.get(gid), "passed": passed, "message": message, **extra}


# ---------------------------------------------------------------------------------------------------------------- motion
def outline_iou(rendered, masks) -> float:
    """Mean intersection over union of the posed silhouette against the clip's mask, over the frames given."""
    vals = []
    for a, b in zip(rendered, masks):
        a, b = np.asarray(a, bool), np.asarray(b, bool)
        union = (a | b).sum()
        vals.append(1.0 if union == 0 else (a & b).sum() / union)
    return float(np.mean(vals)) if vals else 0.0


def _feet(J):
    return {s: J[:, MV.IDX[f"foot_{s}"]] for s in ("l", "r")}


def legs_forward_share(J, fps) -> dict:
    """Of the frames where a foot is lifted, the share in which that foot travels FORWARD relative to the pelvis (a treadmill walk). A fore-aft swapped skeleton reads about 0."""
    J = np.asarray(J, float)
    pel = J[:, MV.IDX["pelvis"], 1]
    lifted = forward = 0
    for foot in _feet(J).values():
        rel = foot[:, 1] - pel
        dy = np.diff(rel)
        up = foot[1:, 2] > LIFT_HEIGHT_M
        lifted += int(up.sum())
        forward += int((up & (dy > 0)).sum())
    return {"share": forward / lifted if lifted else 0.0, "lifted_frames": lifted}


def _phases(mask):
    out, start = [], None
    for i, m in enumerate(list(mask) + [False]):
        if m and start is None:
            start = i
        if not m and start is not None:
            out.append((start, i))
            start = None
    return out


def foot_slide(J, fps, stance_height_m=STANCE_HEIGHT_M) -> dict:
    """Per stance phase of each foot, the largest horizontal distance (cm) between the foot and where the phase began."""
    worst, phases = 0.0, 0
    for foot in _feet(np.asarray(J, float)).values():
        for a, b in _phases(foot[:, 2] <= stance_height_m):
            if b - a < 2:
                continue
            d = np.linalg.norm(foot[a:b, :2] - foot[a, :2], axis=1).max() * 100.0
            worst = max(worst, float(d))
            phases += 1
    return {"max_slide_cm": worst, "phases": phases}


def foot_plant(J) -> dict:
    """The stance foot is the lower one at each frame; its height above the floor (Z = 0), worst case in cm."""
    J = np.asarray(J, float)
    lower = np.minimum(J[:, MV.IDX["foot_l"], 2], J[:, MV.IDX["foot_r"], 2])
    return {"max_height_cm": float(np.abs(lower).max() * 100.0)}


def twist_deg(yaw_a, yaw_b) -> float:
    d = np.abs(np.degrees(np.asarray(yaw_a, float) - np.asarray(yaw_b, float)))
    d = np.abs((d + 180.0) % 360.0 - 180.0)
    return float(d.max())


def motion_gates(J, fps) -> dict:
    legs, slide, plant = legs_forward_share(J, fps), foot_slide(J, fps), foot_plant(J)
    return {"G-LEGS": _gate("G-LEGS", round(legs["share"], 4), legs["share"] >= THRESHOLDS["G-LEGS"], f"{legs['share']:.0%} of {legs['lifted_frames']} lifted frames travel forward"),
            "G-FOOT-SLIDE": _gate("G-FOOT-SLIDE", round(slide["max_slide_cm"], 3), slide["max_slide_cm"] <= THRESHOLDS["G-FOOT-SLIDE"], f"worst stance slide {slide['max_slide_cm']:.2f} cm over {slide['phases']} phases"),
            "G-FOOT-PLANT": _gate("G-FOOT-PLANT", round(plant["max_height_cm"], 3), plant["max_height_cm"] <= THRESHOLDS["G-FOOT-PLANT"], f"stance foot {plant['max_height_cm']:.2f} cm above the floor")}


def controls(J, fps) -> dict:
    """Run the measures against known-bad copies of THIS take: a fore-aft mirrored skeleton must read near 0 on the leg-identity metric, and a stance foot dragged 5 cm must fail the slide gate.
    A take with no lifted foot cannot show the leg measure discriminates: that is reported as not ok, never as a pass."""
    J = np.asarray(J, float)
    swapped = J.copy()
    pel = J[:, MV.IDX["pelvis"], 1:2]
    swapped[:, :, 1] = -(J[:, :, 1] - pel) + pel
    sw = legs_forward_share(swapped, fps)
    dragged = J.copy()
    for s_ in ("l", "r"):
        i = MV.IDX[f"foot_{s_}"]
        for a, b in _phases(J[:, i, 2] <= STANCE_HEIGHT_M):
            if b - a >= 2:
                dragged[a:b, i, 1] += np.linspace(0.0, 0.05, b - a)
    sl = foot_slide(dragged, fps)
    return {"leg_swap_share": round(sw["share"], 4), "leg_swap_ok": bool(sw["lifted_frames"] > 0 and sw["share"] <= 0.5),
            "slide_falsifier_cm": round(sl["max_slide_cm"], 3), "slide_falsifier_ok": bool(sl["max_slide_cm"] > THRESHOLDS["G-FOOT-SLIDE"])}


def check(J, fps, masks=None, rendered=None, twist=None, claims=None) -> dict:
    """Every motion gate with its number. Needs BOTH views' masks; the outline gates need the posed silhouettes. twist = (tracker yaw, refined yaw) arrays; claims = [{text, measurement}]."""
    masks = masks or {}
    if not masks.get("side"):
        raise GateError("no side-view mask: a single view cannot settle which leg is in front (the flat-video blind axis); provide both")
    if not masks.get("front"):
        raise GateError("no front-view mask: provide both views")
    if not rendered or not rendered.get("front") or not rendered.get("side"):
        raise GateError("the posed silhouettes (rendered from the recorded cameras) are needed for the outline gates")
    gates, unverified = [], []
    for view, gid in (("front", "G-OUT-front"), ("side", "G-OUT-side")):
        v = outline_iou(rendered[view], masks[view])
        gates.append(_gate(gid, round(v, 4), v >= THRESHOLDS[gid], f"mean outline IoU {v:.3f}"))
    gates += list(motion_gates(J, fps).values())
    if twist is None:
        unverified.append("G-TWIST")
    else:
        t = twist_deg(*twist)
        gates.append(_gate("G-TWIST", round(t, 3), t <= THRESHOLDS["G-TWIST"], f"largest twist {t:.1f} deg"))
    unverified.append("G-TOE")                                   # the toe rule is recorded, not measured: no toe joint in the recorded take
    if claims is not None:
        share = sum(1 for c in claims if c.get("measurement") is not None) / len(claims) if claims else 1.0
        gates.append(_gate("G-CLAIMS", round(share, 3), share >= 1.0, "every claim carries a measurement" if share >= 1.0 else
                           "advisory claims not counted: no measurement attached: " + "; ".join(c["text"] for c in claims if c.get("measurement") is None)))
    ctl = controls(J, fps)
    controls_ok = ctl["leg_swap_ok"] and ctl["slide_falsifier_ok"]
    return {"gates": gates, "controls": ctl, "controls_ok": controls_ok, "passed": all(g["passed"] for g in gates) and controls_ok, "unverified": unverified, "complete": not unverified}


def require_check(result) -> None:
    if not result.get("passed"):
        failed = [g["id"] for g in result.get("gates", []) if g.get("passed") is False]
        raise GateError(f"run anim_check; {', '.join(failed) or 'a gate'} failed: a take that failed the check is not looped or exported")


# --------------------------------------------------------------------------------------------------------- loop and export
def _strides(n, period):
    """Whole strides in n frames; half a frame of tolerance (a period found to a hundredth of a frame must not lose its last stride to rounding)."""
    return int(np.floor((n - 1 + 0.5) / period))


def _fix(q):
    q = np.asarray(q, float)
    ref = q[0]
    sign = np.sign((q * ref).sum(axis=-1, keepdims=True))
    sign[sign == 0] = 1
    return q * sign


def _at(q, t):
    """The pose at fractional frame t (nlerp of the two neighbours)."""
    i = int(np.floor(t))
    i = min(max(i, 0), len(q) - 2)
    f = t - i
    a, b = q[i], q[i + 1]
    b = b * np.sign((a * b).sum(axis=-1, keepdims=True) + 1e-12)
    out = (1 - f) * a + f * b
    return out / np.maximum(np.linalg.norm(out, axis=-1, keepdims=True), 1e-12)


def rotation_delta_deg(qa, qb):
    d = np.clip(np.abs((np.asarray(qa, float) * np.asarray(qb, float)).sum(axis=-1)), 0, 1)
    return np.degrees(2 * np.arccos(d))


def detect_period(q) -> float:
    q = np.asarray(q, float)
    n = len(q)
    x = _fix(q).reshape(n, -1)
    x = x - x.mean(axis=0)
    ac = np.zeros(n)
    for c in range(x.shape[1]):
        f = np.fft.rfft(x[:, c], 2 * n)
        ac += np.fft.irfft(f * np.conj(f))[:n]
    ac /= np.maximum(ac[0], 1e-12)
    lag = 2
    while lag < n - 1 and ac[lag] > 0:
        lag += 1
    best = lag + int(np.argmax(ac[lag:n // 2 + 1])) if lag < n // 2 else lag
    if 0 < best < n - 1:
        y0, y1, y2 = ac[best - 1], ac[best], ac[best + 1]
        den = y0 - 2 * y1 + y2
        best = best + (0.5 * (y0 - y2) / den if den else 0.0)
    return _refine_period(q, float(best))


def _refine_period(q, p0, span=0.6, steps=121, phases=16):
    """Fine search around the autocorrelation peak: the period at which each stride matches the next one best (least squares over phases)."""
    n = len(q)
    best_p, best_c = p0, None
    for p in np.linspace(p0 - span, p0 + span, steps):
        strides = _strides(n, p)
        if strides < 2:
            continue
        c = 0.0
        for k in range(strides - 1):
            for ph in range(phases):
                t = ph * p / phases
                a, b = _at(q, k * p + t), _at(q, (k + 1) * p + t)
                c += float(((a - b * np.sign((a * b).sum(axis=-1, keepdims=True) + 1e-12)) ** 2).sum())
        if best_c is None or c < best_c:
            best_p, best_c = float(p), c
    return best_p


def phase_average_loop(q, period, n_frames=None) -> dict:
    """Average the strides by PHASE into one loop (periodic by construction). Returns {frames: (N, B, 4), strides, period}."""
    q = np.asarray(q, float)
    strides = _strides(len(q), period)
    if strides < 1:
        raise GateError("the take is shorter than one period")
    n = int(n_frames or round(period))
    frames = []
    for p in range(n):
        poses = [_at(q, k * period + p * period / n) for k in range(strides)]
        poses = _fix(np.stack(poses))
        poses = poses * np.sign((poses * poses[0]).sum(axis=-1, keepdims=True) + 1e-12)
        m = poses.mean(axis=0)
        frames.append(m / np.maximum(np.linalg.norm(m, axis=-1, keepdims=True), 1e-12))
    return {"frames": np.stack(frames), "strides": strides, "period": float(period)}


def check_target_skeleton(name: str) -> None:
    if "manny" in name.lower() or "mannequin" in name.lower():
        raise GateError("Manny animations stay on Manny-based rigs; MetaHuman bodies require animations converted to their own unchanged rig")


def loop_gates(q, period, root_y_m, fps, planted_foot_speed_mps, skeleton, strides_note=None, loop_tolerance_deg=None) -> dict:
    q = np.asarray(q, float)
    root = np.asarray(root_y_m, float)
    strides = _strides(len(q), period)
    if strides < 2:
        raise GateError("a one-stride cycle hitches at the loop: need >= 2, 4 recommended")
    tol = THRESHOLDS["G-LOOP"] if loop_tolerance_deg is None else loop_tolerance_deg
    gates, unverified = {}, []
    delta = max(float(rotation_delta_deg(_at(q, k * period), _at(q, (k + 1) * period)).max()) for k in range(strides))
    speed_root = float((root[-1] - root[0]) / ((len(root) - 1) / fps))
    expected = speed_root * period / fps
    root_delta_cm = float(abs((root[int(round(period))] - root[0]) - expected) * 100.0) if len(root) > period else 0.0
    ok = delta <= tol and root_delta_cm <= THRESHOLDS["G-LOOP-ROOT"]
    gates["G-LOOP"] = _gate("G-LOOP", round(delta, 3), ok, "periodic" if ok else f"loop max joint delta {delta:.1f} deg > {tol}: the take is not periodic enough; use more strides", threshold=tol, root_delta_cm=round(root_delta_cm, 3))
    loop = phase_average_loop(q, period)["frames"]
    steps = [float(rotation_delta_deg(a, b).max()) for a, b in zip(loop, loop[1:])]
    wrap = float(rotation_delta_deg(loop[-1], loop[0]).max())
    med = float(np.median(steps)) if steps else 0.0
    gates["G-LOOP-WRAP"] = _gate("G-LOOP-WRAP", round(wrap / med, 3) if med else 0.0, wrap <= THRESHOLDS["G-LOOP-WRAP"] * max(med, 1e-9), f"wrap change {wrap:.2f} deg against a median step of {med:.2f}")
    rel = abs(speed_root - planted_foot_speed_mps) / max(abs(speed_root), 1e-9)
    gates["G-SPEED"] = _gate("G-SPEED", round(rel, 4), rel <= THRESHOLDS["G-SPEED"], f"planted-foot speed {planted_foot_speed_mps:.3f} m/s against {speed_root:.3f} m/s from the root")
    gates["G-STRIDES"] = _gate("G-STRIDES", strides, strides >= THRESHOLDS["G-STRIDES"] or (strides >= 2 and bool(strides_note)),
                               f"{strides} strides" + (f" (accepted: {strides_note})" if strides < 4 and strides_note else " (>= 4, or >= 2 with the user's note)"))
    bones, ref = skeleton.get("bones") or [], skeleton.get("reference")
    if ref is None:
        gates["G-SKEL"] = _gate("G-SKEL", None, None, "UNVERIFIED: no reference bone list (names_from) given for metahuman_base_skel")
        unverified.append("G-SKEL")
    else:
        missing, extra = sorted(set(ref) - set(bones)), sorted(set(bones) - set(ref))
        gates["G-SKEL"] = _gate("G-SKEL", {"missing": missing, "extra": extra}, not missing and not extra,
                                "same bone set" if not missing and not extra else f"skeleton mismatch: {len(missing)} of {len(ref)} bones missing from the take ({', '.join(missing)})" + (f"; extra: {', '.join(extra)}" if extra else ""))
    for gid in ("G-FIDELITY", "G-ENGINE"):
        gates[gid] = _gate(gid, None, None, "UNVERIFIED: needs the user's UE editor leg (headless import and verify)")
        unverified.append(gid)
    return {"gates": gates, "passed": all(g["passed"] is not False for g in gates.values()), "unverified": unverified, "complete": not unverified}
