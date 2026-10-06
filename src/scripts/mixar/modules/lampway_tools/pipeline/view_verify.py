# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""view_verify (specs/mrmak/07-view-verify.md): is this generated image really the view that was asked for?

admit   rejects an empty, tiny, fragmented or duplicate reference with the reason, before any model is paid (the four intake tests, upstream's defaults, all reported)
verify  measured checks on the figure's silhouette first (shoulder widths and mirror IoU about the figure's own axis, feet baseline, arm angle, framing, background), a vision judge second;
        the judge may RESCUE an ``uncertain`` and may never override a measured hard failure; malformed judge output is ``uncertain``, never ``pass``
Every threshold in THRESHOLDS is a PLACEHOLDER until calibrated on labelled shelf images; it is reported with every result. Numpy only."""

import math

import numpy as np

THRESHOLDS = {"coverage_min": 0.05, "coverage_max": 0.97, "short_side_min": 64, "largest_component_min": 0.60, "phash_distance_max": 6,
              "shoulder_ratio_ok": 0.90, "shoulder_ratio_hard": 0.80, "mirror_iou_ok": 0.92, "mirror_iou_hard": 0.85, "foot_baseline_delta_max": 0.03,
              "arm_angle_min": 30.0, "arm_angle_max": 60.0, "margin_min": 0.02, "background_gradient": 8.0, "background_corner_delta": 12.0}
VERDICTS = ("pass", "soft_fail", "hard_fail", "uncertain")
GRID = 96


def to_mask(img) -> np.ndarray:
    """A boolean figure mask from a bool array, an RGBA image (alpha) or an RGB image on a flat background."""
    a = np.asarray(img)
    if a.dtype == bool and a.ndim == 2:
        return a
    if a.ndim == 3 and a.shape[2] == 4 and a[..., 3].min() < 255:
        return a[..., 3] > 127
    rgb = a[..., :3].astype(float)
    corners = np.concatenate([rgb[:8, :8].reshape(-1, 3), rgb[-8:, -8:].reshape(-1, 3)])
    return np.abs(rgb - np.median(corners, axis=0)).max(-1) > 20


def _components(grid):
    h, w = grid.shape
    seen = np.zeros_like(grid)
    best = 0
    for sy in range(h):
        for sx in range(w):
            if not grid[sy, sx] or seen[sy, sx]:
                continue
            stack, n = [(sy, sx)], 0
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                n += 1
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and grid[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            best = max(best, n)
    return best


def phash(mask) -> int:
    """64-bit difference hash of the mask's coverage on a 9 x 8 lattice (the intake duplicate test)."""
    m = np.asarray(mask, float)
    ys = np.linspace(0, m.shape[0], 9).astype(int)
    xs = np.linspace(0, m.shape[1], 10).astype(int)
    cells = np.array([[m[ys[i]:ys[i + 1], xs[j]:xs[j + 1]].mean() for j in range(9)] for i in range(8)])
    bits = (cells[:, 1:] > cells[:, :-1]).flatten()
    return int("".join("1" if b else "0" for b in bits), 2)


def hamming(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def admit(img, known_hashes=None, thresholds=None) -> dict:
    t = dict(THRESHOLDS, **(thresholds or {}))
    m = to_mask(img)
    h, w = m.shape
    cov = float(m.mean())
    reasons = []
    if m.sum() == 0:
        reasons.append("empty: the cut found no figure")
    elif cov < t["coverage_min"] or cov > t["coverage_max"]:
        reasons.append(f"coverage {cov:.3f} is outside {t['coverage_min']}..{t['coverage_max']}")
    if min(h, w) < t["short_side_min"]:
        reasons.append(f"short side {min(h, w)} px is under {int(t['short_side_min'])}")
    frac = 0.0
    if m.sum():
        ys = np.minimum((np.arange(GRID) * h / GRID).astype(int), h - 1)
        xs = np.minimum((np.arange(GRID) * w / GRID).astype(int), w - 1)
        cell = np.array([[m[ys[i]:max(ys[i] + 1, int((i + 1) * h / GRID)), xs[j]:max(xs[j] + 1, int((j + 1) * w / GRID))].any() for j in range(GRID)] for i in range(GRID)])
        frac = _components(cell) / max(int(cell.sum()), 1)
        if frac < t["largest_component_min"]:
            reasons.append(f"fragmented: the largest piece is {frac:.2f} of the figure (needs {t['largest_component_min']})")
    dup = None
    if m.sum() and known_hashes:
        hh = phash(m)
        for name, other in known_hashes.items():
            if hamming(hh, other) <= t["phash_distance_max"]:
                dup = name
                reasons.append(f"duplicate of {name} (perceptual-hash distance <= {int(t['phash_distance_max'])})")
                break
    return {"ok": not reasons, "coverage": round(cov, 4), "short_side": int(min(h, w)), "largest_component_fraction": round(frac, 4), "duplicate_of": dup, "reasons": reasons,
            "thresholds": {k: t[k] for k in ("coverage_min", "coverage_max", "short_side_min", "largest_component_min", "phash_distance_max")}}


def background_stats(rgb) -> dict:
    a = np.asarray(rgb, float)[..., :3]
    k = max(2, min(a.shape[0], a.shape[1]) // 10)
    patches = [a[:k, :k], a[:k, -k:], a[-k:, :k], a[-k:, -k:]]
    means = np.array([p.reshape(-1, 3).mean(0) for p in patches])
    corner_delta = max(float(np.abs(means[i] - means[j]).max()) for i in range(4) for j in range(i + 1, 4))
    horiz = float(np.abs(a[:, :k].reshape(-1, 3).mean(0) - a[:, -k:].reshape(-1, 3).mean(0)).max())
    vert = float(np.abs(a[:k].reshape(-1, 3).mean(0) - a[-k:].reshape(-1, 3).mean(0)).max())
    return {"corner_delta": round(corner_delta, 3), "gradient": round(max(horiz, vert), 3)}


def _extent(m, axis_x):
    """(per-row distance from the axis to the outermost figure pixel on the left, on the right); 0 on rows with none."""
    left = np.zeros(m.shape[0])
    right = np.zeros(m.shape[0])
    for y in range(m.shape[0]):
        xs = np.flatnonzero(m[y])
        if len(xs):
            left[y] = max(0.0, axis_x - xs.min())
            right[y] = max(0.0, xs.max() - axis_x)
    return left, right


def _measure(m):
    ys, xs = np.nonzero(m)
    y0, y1, x0, x1 = int(ys.min()), int(ys.max()) + 1, int(xs.min()), int(xs.max()) + 1       # half-open
    height = y1 - y0
    head = m[y0:y0 + max(2, int(0.12 * height))]
    axis = float(np.nonzero(head)[1].mean())                          # the figure's own vertical axis: the head's column centre (a turned body shifts its mass, its head stays on the neck)
    left, right = _extent(m, axis)
    band = slice(y0 + int(0.12 * height), y0 + int(0.22 * height) + 1)
    wl, wr = float(left[band].mean()), float(right[band].mean())
    ratio = min(wl, wr) / max(wl, wr, 1e-9)
    cols = np.arange(m.shape[1])
    flip = np.zeros_like(m)
    src = np.round(2 * axis - cols).astype(int)
    ok = (src >= 0) & (src < m.shape[1])
    flip[:, ok] = m[:, src[ok]]
    mirror = float((m & flip).sum() / max((m | flip).sum(), 1))
    mid = int(round(axis))
    foot_l = np.flatnonzero(m[:, :mid].any(axis=1)).max() if m[:, :mid].any() else y1
    foot_r = np.flatnonzero(m[:, mid:].any(axis=1)).max() if m[:, mid:].any() else y1
    # arm angle: the outermost reach (12-70 % of the height) against the torso half width (the narrowest reach between 16 and 30 %, where an arm is thin or absent), measured from where
    # the reach first leaves the torso: A-pose is about 45 degrees, a T-pose about 90, arms down about 0
    out = np.maximum(left, right)
    seg = out[y0 + int(0.12 * height): y0 + int(0.70 * height)]
    sh = out[y0 + int(0.16 * height): y0 + int(0.30 * height) + 1]
    torso_half = float(np.min(sh[sh > 0])) if (sh > 0).any() else 0.0
    tip = int(np.argmax(seg))
    dx = float(seg[tip] - torso_half)
    if dx < 0.03 * height:
        angle = 0.0
    else:
        first = int(np.argmax(seg > torso_half + 2))
        angle = math.degrees(math.atan2(dx, max(tip - first, 0) + 1.0))
    margins = [y0 / m.shape[0], (m.shape[1] - x1) / m.shape[1], (m.shape[0] - y1) / m.shape[0], x0 / m.shape[1]]
    rot = math.degrees(math.asin(min(1.0, 1.0 - ratio)))
    return {"shoulder_width_ratio": round(ratio, 4), "mirror_iou": round(mirror, 4), "foot_baseline_delta_frac": round(abs(int(foot_l) - int(foot_r)) / height, 4), "arm_angle_deg": round(angle, 1),
            "margins_frac": [round(v, 4) for v in margins], "estimated_rotation_deg": round(rot if wl < wr else -rot, 1), "height_px": height, "bbox": [x0, y0, x1, y1]}


def parse_judge(out) -> dict:
    """The judge's answer, or ``uncertain``: prose, a missing key and an unknown verdict are never a pass."""
    if not isinstance(out, dict) or out.get("verdict") not in VERDICTS or not isinstance(out.get("reason", ""), str):
        return {"verdict": "uncertain", "reason": "the judge's answer was not valid JSON with a known verdict", "checks": {}}
    return {"verdict": out["verdict"], "reason": out.get("reason", ""), "checks": out.get("checks") if isinstance(out.get("checks"), dict) else {}}


def verify(mask, view="front", category="sheet", approved_front=None, asymmetric_ok=False, judge=None, image=None, thresholds=None) -> dict:
    if view not in ("front", "side", "back"):
        raise ValueError("view is front | side | back")
    t = dict(THRESHOLDS, **(thresholds or {}))
    m = to_mask(mask)
    base = {"thresholds": t, "view": view, "category": category}
    if not m.any():
        return {**base, "verdict": "uncertain", "checks": {}, "measured": {}, "estimated_rotation_deg": None, "reason": "no figure found in the mask", "by": "measured", "judge_cost_usd": None}
    me = _measure(m)
    if image is not None:
        me["background"] = background_stats(image)
    if approved_front is not None:
        a = to_mask(approved_front)
        ya, xa = np.nonzero(a)
        bx = [int(xa.min()), int(ya.min()), int(xa.max()) + 1, int(ya.max()) + 1]
        me["part_fit"] = {"aspect_drift_frac": round(abs((me["bbox"][2] - me["bbox"][0]) / me["height_px"] - (bx[2] - bx[0]) / (bx[3] - bx[1])), 4)}
    sym = "not_applicable" if asymmetric_ok else None
    checks = {"body_axis_dead_front": None, "no_three_quarter": None, "no_body_twist": None, "no_hero_angle": "not_measured", "no_partial_back": "not_applicable" if view != "back" else None,
              "framing_clean": not any(v < t["margin_min"] for v in me["margins_frac"])}
    reasons, hard, soft = [], False, False
    if view == "side":
        for k in ("body_axis_dead_front", "no_three_quarter", "no_body_twist", "no_partial_back"):
            checks[k] = "not_measured"
        verdict, reason = "uncertain", "a profile cannot be read from the silhouette alone: the measured checks are not defined for a side view (use the vision judge or look)"
        by, estimated = "measured", None
    else:
        if sym:
            checks.update(body_axis_dead_front=sym, no_three_quarter=sym, no_body_twist=sym)
        else:
            r, mi = me["shoulder_width_ratio"], me["mirror_iou"]
            checks["body_axis_dead_front"] = bool(r >= t["shoulder_ratio_ok"] and mi >= t["mirror_iou_ok"])
            checks["no_three_quarter"] = bool(r >= t["shoulder_ratio_ok"])
            checks["no_body_twist"] = bool(me["foot_baseline_delta_frac"] <= t["foot_baseline_delta_max"])
            if r < t["shoulder_ratio_hard"] or mi < t["mirror_iou_hard"]:
                hard = True
                reasons.append(f"the shoulders differ by {(1 - r) * 100:.0f} % (mirror IoU {mi:.2f}): the body is turned, estimated {me['estimated_rotation_deg']:+.0f}° off dead-front")
            elif not checks["body_axis_dead_front"]:
                soft = True
                reasons.append(f"slightly off dead-front: shoulder ratio {r:.2f}, mirror IoU {mi:.2f}")
            if not checks["no_body_twist"]:
                soft = True
                reasons.append(f"the feet baselines differ by {me['foot_baseline_delta_frac'] * 100:.1f} % of the height")
        if category == "sheet" and not (t["arm_angle_min"] <= me["arm_angle_deg"] <= t["arm_angle_max"]):
            soft = True
            reasons.append(f"not A-pose: the arms are at about {me['arm_angle_deg']:.0f}° (A-pose is 30 to 60)")
        if not checks["framing_clean"]:
            soft = True
            reasons.append("the figure is cropped or too close to the frame edge")
        bg = me.get("background")
        if bg and (bg["gradient"] > t["background_gradient"] or bg["corner_delta"] > t["background_corner_delta"]):
            soft = True
            reasons.append(f"the background is not flat (gradient {bg['gradient']:.1f})")
        verdict = "hard_fail" if hard else "soft_fail" if soft else "pass"
        reason = "; ".join(reasons) if reasons else "measured checks pass"
        by, estimated = "measured", me["estimated_rotation_deg"]
    out = {**base, "verdict": verdict, "checks": checks, "measured": me, "estimated_rotation_deg": estimated, "reason": reason, "by": by, "judge_cost_usd": None}
    if judge is not None and verdict == "uncertain":                    # never consulted on a measured hard failure; rescues an uncertain only
        j = parse_judge(judge({k: v for k, v in me.items() if k != "bbox"}, image))
        out.update(verdict=j["verdict"], reason=j["reason"] or reason, by="both")
    return out
