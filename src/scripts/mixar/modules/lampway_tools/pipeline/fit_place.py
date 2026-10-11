# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_place: place a piece on the body by ENCLOSURE with ONE uniform scale, for all five kinds, and write the placement meta that maps later points back to the piece's frame.

Enclosure, not registration (memory armour-registration-bias): surface registration is biased toward the thick side (the fitted warrior sat 3-5 cm forward), so the piece is centred on its body
segment's own slice centres and scaled to a landmark width; never a per-region push (pose-not-push): ONE similarity (scale + translation, plus the rotation a gauntlet's axis needs, reported).
The body-side measures are the proportion scorer's (piece_ratios.py): helmet = the widest level above neck_02 (+2C), waist = the band at spine_01 + 3 cm, boots = shaft width / knee height /
foot length by ``scale_anchor`` (default shaft width, physically untested), gauntlets = the bracer's major axis at 35 % vs the forearm's middle. The chest keeps the audits' placement
(scripts/proportion/place_piece.py, byte for byte). Frame: Z up, -Y front, +X the wearer's left. Pure numpy."""

import importlib.util
import json
import re
from pathlib import Path

import numpy as np

from . import sections as S
from .. import canon_geom as G

KINDS = ("chest", "helmet", "waist", "boots", "gauntlets")
ANCHORS = ("width", "height", "foot")
SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "proportion"


class PlaceError(ValueError):
    pass


def _body(path):
    d = np.load(path)
    if "J" not in d.files or "names" not in d.files:
        raise PlaceError("body.npz has no joints: export with `mesh_to_npz ... body` (mode body)")
    return d["V"].astype(float), d["T"], {str(n): v for n, v in zip(d["names"], d["J"])}


TORSO = ("pelvis", "spine_01", "spine_02", "spine_03", "spine_04", "spine_05")
ARMS = tuple(f"{b}_{s}" for s in "lr" for b in ("upperarm", "lowerarm", "hand", *(f"{f}_0{k}" for f in ("thumb", "index", "middle", "ring", "pinky")
                                                                                   for k in (1, 2, 3))))
# The foot length is read on the sole band: 4 cm thick, measured from the foot's lowest point (it was z < 0.04 m, which assumed the
# body stands at z = 0). The band's THICKNESS is still absolute: needs_decision (canon 09 INV-09.4 asks for a joint-relative form;
# a ratio of the ankle height would need the native body's joints to calibrate, which are not in this repository).
SOLE_BAND_M = 0.04


# the main skeleton (canon 16's UE names): the bones a region is made of; every other joint (twist, corrective, helper, toe) lies inside them
MAIN = re.compile(r"^(pelvis|spine_0[1-5]|neck_0[12]|head|clavicle_[lr]|upperarm_[lr]|lowerarm_[lr]|hand_[lr]|thigh_[lr]|calf_[lr]|foot_[lr]|ball_[lr]"
                  r"|(thumb|index|middle|ring|pinky)_0[1-3]_[lr])$")


def _region(P, J, bones, missing_ok=False):
    """Mask of the points whose NEAREST bone segment (joint -> the next joint of its chain present in J; a last joint is a point) is
    one of ``bones`` - a body region from its joints, never an absolute coordinate (canon 09 INV-09.4)."""
    from .joints_views import _reaches
    names = [n for n in J if MAIN.match(n)]                    # twist, corrective, helper and toe bones would claim their limb's vertices
    segs = []
    for n in names:
        nxt = [k for k in names if k != n and _reaches(n, k)]
        end = min(nxt, key=lambda k: np.linalg.norm(np.asarray(J[k]) - np.asarray(J[n]))) if nxt else n
        segs.append((np.asarray(J[n], float), np.asarray(J[end], float)))
    A = np.array([a for a, _b in segs])
    D = np.array([b - a for a, b in segs])
    P = np.asarray(P, float)
    L2 = np.maximum((D * D).sum(1), 1e-18)
    t = np.clip(np.einsum("nkj,kj->nk", P[:, None, :] - A[None], D) / L2, 0.0, 1.0)
    d = np.linalg.norm(P[:, None, :] - (A[None] + t[..., None] * D[None]), axis=2)
    keep = np.array([n in bones for n in names])
    if not keep.any():
        if missing_ok:
            return np.zeros(len(P), bool)
        raise PlaceError(f"the body's joints include none of {', '.join(bones)}")
    return keep[d.argmin(1)]


def _piece(path, turn):
    d = np.load(path)
    V, T = d["V"].astype(float), d["T"]
    th = np.radians(turn)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    return V @ R.T, T


def _xy(p, c):
    """A section's (side, front) centre as world x, y (axis Z, side X, front +Y)."""
    return np.array([c[0], c[1]])


def _local(V, origin, axis, side):
    """V in (side, front, along) coordinates of a frame at ``origin`` with ``axis`` along and ``side`` across."""
    front = np.cross(axis, side)
    P = np.asarray(V, float) - origin
    return np.stack([P @ side, P @ front, P @ axis], 1)


def _ring(V, T, origin, axis, side, t, start=None):
    """(centre (2,), resolved (x, y), width, depth) of the INNER wall of the section at ``t`` along ``axis`` (canon 09 B.4): the first
    harmonic of the first-hit radii of rays from ``start`` (default: the section's own mean), re-cast from the new centre; a ray
    through an opening is left out of the fit; the spans are the +-side and +-front first hits from the centre (NaN through an
    opening); None when too few rays meet a wall."""
    segs = G.slice_segments(_local(V, origin, axis, side), T, t)
    if len(segs) < 3:
        return None
    c0 = segs.reshape(-1, 2).mean(0) if start is None else np.asarray(start, float)
    try:
        c, _n = G.harmonic_centre(segs, c0)                             # the first harmonic of the inner wall's radii (canon 09 B.4)
    except ValueError:
        return None
    hits = [G.first_hit(segs, c, d) for d in (np.array([1.0, 0]), np.array([-1.0, 0]), np.array([0, 1.0]), np.array([0, -1.0]))]
    return c, (True, True), hits[0] + hits[1], hits[2] + hits[3]


def _inner_centre(V, T, z, section_points):
    """The (x, y) centre of the inner wall of the piece's horizontal section at ``z`` (rays from the section's own mean); an axis the
    wall leaves open keeps the extents' midpoint."""
    fallback = S.centre(section_points)
    r = _ring(V, T, np.zeros(3), S.Z, S.X, z)
    if r is None:
        return fallback
    return np.array([r[0][k] if r[1][k] else fallback[k] for k in range(2)])


def _enclose(bV, bT, V, T, origin, axis, side, t_body, ts_piece):
    """The inner-wall enclosure over ``ts_piece``: {body_centre, body_width, piece_centre (median per axis over the levels whose
    wall closes on that axis), piece_width, slices, resolved}; the piece's rays start from the body's centre so they meet its
    INNER wall first (a piece still in its own frame starts from its own sections)."""
    b = _ring(bV, bT, origin, axis, side, t_body)
    if b is None or not all(b[1]):
        raise PlaceError("the body has no closed section at the anchor level: check the body package and the joints")
    rows = []
    for t in ts_piece:                                     # per level and axis: from the body's centre, else (an opening on that ray,
        r1, r2 = _ring(V, T, origin, axis, side, t, b[0]), _ring(V, T, origin, axis, side, t)   # or a piece still in its own frame) its own
        cands = [r for r in (r1, r2) if r is not None]
        if cands:
            pick = [next((r for r in cands if r[1][k]), cands[0]) for k in range(2)]
            rows.append((np.array([pick[0][0][0], pick[1][0][1]]), (pick[0][1][0], pick[1][1][1]), pick[0][2], pick[1][3]))
    if not rows:
        raise PlaceError("no section of the piece encloses the body's centre: place it over the body (turn, sides) first")
    pc = np.zeros(2)
    for k in range(2):
        vals = [r[0][k] for r in rows if r[1][k]]
        if not vals:
            raise PlaceError(f"the piece's inner wall is open along {'xy'[k]} at every band level: it cannot be centred by enclosure")
        pc[k] = float(np.median(vals))
    widths = [r[2] for r in rows if r[1][0]]
    return {"body_centre": b[0], "body_width": b[2], "body_depth": b[3], "piece_centre": pc, "piece_width": float(np.median(widths)),
            "slices": len(rows), "resolved": [sum(1 for r in rows if r[1][k]) for k in range(2)]}


def _similarity(V, s, anchor_piece, anchor_body):
    return (V - anchor_piece) * s + anchor_body


def _helmet(bV, bT, J, V, T, C):
    nz, crown = J["neck_02"][2], bV[:, 2].max()
    hz = np.linspace(nz, crown - 0.005, 40)
    bw, bd, bp = S.profile(bV, bT, np.zeros(3), S.Z, S.X, hz)
    k = int(np.nanargmax(bw))
    lo, hi = V[:, 2].min(), V[:, 2].max()
    z = np.linspace(lo + 0.005 * (hi - lo), hi - 0.005 * (hi - lo), 80)
    w, d, pp = S.profile(V, T, np.zeros(3), S.Z, S.X, z)
    j = int(np.nanargmax(w))
    s = (bw[k] + 2 * C) / w[j]
    cb, cp = _inner_centre(bV, bT, hz[k], bp[k]), _inner_centre(V, T, z[j], pp[j])  # canon 09 B.4: both centred the same way, the piece by its INNER wall
    return s, np.array([cp[0], cp[1], z[j]]), np.array([cb[0], cb[1], hz[k]]), {"anchor": "head width at its widest level above neck_02, + 2C (the crest is not measured)",
                                                                              "body_width_mm": round(1000 * (bw[k] + 2 * C), 1), "piece_width_mm": round(1000 * w[j], 1)}


def _waist(bV, bT, J, V, T, C):
    zw = J["spine_01"][2] + 0.03
    torso = ~_region(bV, J, ARMS, missing_ok=True)                           # INV-09.4: the arms by bone excluded, not |x| < 0.27 m
    bt = bT[torso[bT].all(1)]
    lo, hi = V[:, 2].min(), V[:, 2].max()
    L = hi - lo
    band = np.linspace(hi - 0.06 * L, hi - 0.005 * L, 7)
    e = _enclose(bV, bt, V, T, np.zeros(3), S.Z, S.X, zw, band)
    zmid = float(np.median(band))
    return (e["body_width"] + 2 * C) / e["piece_width"], np.array([e["piece_centre"][0], e["piece_centre"][1], zmid]), np.array([e["body_centre"][0], e["body_centre"][1], zw]), {
        "anchor": "waist band's INNER wall width (top 6 %) vs the body's width at spine_01 + 3 cm, + 2C; centred by inner-wall enclosure (canon 09)",
        "body_width_mm": round(1000 * (e["body_width"] + 2 * C), 1), "piece_width_mm": round(1000 * e["piece_width"], 1),
        "inner_wall_shift_m": [round(float(x), 6) for x in (e["body_centre"] - e["piece_centre"])], "slices": e["slices"]}


def _boots(bV, bT, J, V, T, C, anchor, sides):
    rows = []
    for sgn, sfx in ((1, "l"), (-1, "r")):
        if sides not in ("both", sfx):
            continue
        k_, a_ = J[f"calf_{sfx}"], J[f"foot_{sfx}"]
        leg = _region(bV, J, tuple(f"{b}_{sfx}" for b in ("thigh", "calf", "foot", "ball")))
        bt = bT[leg[bT].all(1)]
        zt = a_[2] + 0.6 * (k_[2] - a_[2])
        bw, bd, bp = S.section(bV, bt, np.zeros(3), S.Z, S.X, zt)
        lv = bV[leg]                                                                 # INV-09.4: that leg by bone, not "x > 0, z < 0.04 m"
        foot = lv[lv[:, 2] < lv[:, 2].min() + SOLE_BAND_M]                          # its sole band from its own lowest point
        fl = foot[:, 1].max() - foot[:, 1].min()
        pv = V[:, 0] * sgn > 0
        pt = T[pv[T].all(1)]
        if len(pt) < 50:
            raise PlaceError(f"no {sfx} boot found (split at x = 0): centre the pair on x = 0 or run with sides=l and r separately")
        sub = V[np.unique(pt)]
        lo, hi = sub[:, 2].min(), sub[:, 2].max()
        h = hi - lo
        pw, pd, pp = S.section(V, pt, np.zeros(3), S.Z, S.X, lo + 0.6 * h)
        ft = sub[sub[:, 2] < lo + 0.04 * h]
        pfl = ft[:, 1].max() - ft[:, 1].min()
        scale = {"width": (bw + 2 * C) / pw, "height": (k_[2] - foot[:, 2].min() + C) / h, "foot": (fl + 2 * C) / pfl}
        rows.append({"side": sfx, "scales": scale, "bp": S.centre(bp), "pp": _inner_centre(V, pt, lo + 0.6 * h, pp), "sole_body": float(foot[:, 2].min()), "sole_piece": float(lo),
                     "foot_y_body": float((foot[:, 1].max() + foot[:, 1].min()) / 2), "foot_y_piece": float((ft[:, 1].max() + ft[:, 1].min()) / 2)})
    s = float(np.mean([r["scales"][anchor] for r in rows]))
    anchor_p = np.array([np.mean([r["pp"][0] * np.sign(1 if r["side"] == "l" else -1) for r in rows]) * (1 if sides != "r" else -1), np.mean([r["foot_y_piece"] for r in rows]),
                         np.mean([r["sole_piece"] for r in rows])])
    anchor_b = np.array([np.mean([r["bp"][0] * np.sign(1 if r["side"] == "l" else -1) for r in rows]) * (1 if sides != "r" else -1), np.mean([r["foot_y_body"] for r in rows]),
                         np.mean([r["sole_body"] for r in rows])])
    return s, anchor_p, anchor_b, {"anchor": f"boot {anchor}", "scales_by_anchor": {a: round(float(np.mean([r["scales"][a] for r in rows])), 4) for a in ANCHORS},
                                   "per_side": {r["side"]: {a: round(float(v), 4) for a, v in r["scales"].items()} for r in rows}}


def _turn(a, b):
    """The proper rotation taking unit ``a`` onto unit ``b`` by the shortest arc."""
    v, c = np.cross(a, b), float(a @ b)
    if np.linalg.norm(v) < 1e-12:
        return np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K / (1 + c)


def _gauntlets(bV, bT, J, V, T, C, sides):
    rows = []
    V = V.copy()
    for sgn, sfx in ((1, "l"), (-1, "r")):
        if sides not in ("both", sfx):
            continue
        el, wr, tip = J[f"lowerarm_{sfx}"], J[f"hand_{sfx}"], J[f"middle_03_{sfx}"]
        ax_ = (tip - el) / np.linalg.norm(tip - el)
        side = np.cross(ax_, S.Z)
        side /= np.linalg.norm(side)
        fa = np.linalg.norm(wr - el)
        arm = _region(bV, J, tuple(f"{b}_{sfx}" for b in ("lowerarm", "hand")))   # INV-09.4: by bone, not |x| > 0.25 m
        bt = bT[arm[bT].all(1)]
        _, _, p = S.section(bV, bt, el, ax_, side, 0.5 * fa)
        ext = np.percentile(p - p.mean(0), 99, 0) - np.percentile(p - p.mean(0), 1, 0)
        u, s_, vt = np.linalg.svd(p - p.mean(0), full_matrices=False)
        q = (p - p.mean(0)) @ vt.T
        e = np.percentile(q, 99, 0) - np.percentile(q, 1, 0)
        fmaj = float(max(e)) + 2 * C
        pv = V[:, 0] * sgn > 0
        pt = T[pv[T].all(1)]
        if len(pt) < 50:
            raise PlaceError(f"no {sfx} gauntlet found (split at x = 0): centre the pair on x = 0 or run with sides=l and r separately")
        sub = V[np.unique(pt)]
        c0 = sub.mean(0)
        _, _, pvt = np.linalg.svd(sub - c0, full_matrices=False)
        a = pvt[0]
        w = (sub - c0) @ a
        if (c0 + w.min() * a)[2] < (c0 + w.max() * a)[2]:
            a = -a
            w = -w
        L = w.max() - w.min()
        sd = np.cross(a, S.Z)
        sd /= max(np.linalg.norm(sd), 1e-9)
        t35 = w.min() + 0.35 * L
        _, _, pp = S.section(V, pt, c0, a, sd, t35)
        qq = (pp - pp.mean(0))
        _, _, vv = np.linalg.svd(qq, full_matrices=False)
        ee = np.percentile(qq @ vv.T, 99, 0) - np.percentile(qq @ vv.T, 1, 0)
        pmaj = float(max(ee))
        ang = float(np.degrees(np.arccos(np.clip(abs(a @ ax_), -1, 1))))
        if ang > 25:
            raise PlaceError(f"the {sfx} gauntlet's axis is {ang:.0f} degrees off the forearm's: the turn or orientation is wrong")
        Rk = _turn(a, ax_ if a @ ax_ >= 0 else -ax_)                          # canon 09 B.2: the residual angle corrected rigidly, never left
        idx = np.unique(pt)
        V[idx] = (V[idx] - c0) @ Rk.T + c0
        a = Rk @ a
        sub = V[idx]
        w = (sub - c0) @ a
        sd = np.cross(a, S.Z)
        sd /= max(np.linalg.norm(sd), 1e-9)
        _, _, pp = S.section(V, pt, c0, a, sd, t35)
        qq = (pp - pp.mean(0))
        _, _, vv = np.linalg.svd(qq, full_matrices=False)
        ee = np.percentile(qq @ vv.T, 99, 0) - np.percentile(qq @ vv.T, 1, 0)
        pmaj = float(max(ee))
        rows.append({"scale": fmaj / pmaj, "angle": ang, "pt": c0 + (t35 - 0.0) * a, "bt": el + 0.5 * fa * ax_, "sfx": sfx, "bp": p.mean(0), "pp": pp.mean(0), "axis_b": ax_, "axis_p": a, "c0": c0, "t35": t35})
    s = float(np.mean([r["scale"] for r in rows]))
    ap_, ab_ = np.mean([r["pt"] for r in rows], axis=0), np.mean([r["bt"] for r in rows], axis=0)
    return s, ap_, ab_, {"anchor": "bracer major axis at 35 % of the piece vs the forearm's middle, + 2C", "axis_error_deg": {r["sfx"]: round(r["angle"], 2) for r in rows},
                         "scales": {r["sfx"]: round(float(r["scale"]), 4) for r in rows}, "axis_corrected": True, "_V": V}


def place(kind, body_npz, piece_npz, turn=0.0, clear_mm=15.0, scale_anchor=None, sides="both", pair_scale_group=None):
    if kind not in KINDS:
        raise PlaceError(f"kind is one of {', '.join(KINDS)}")
    if not 0 <= float(clear_mm) <= 40:
        raise PlaceError("clear_mm is 0 to 40 (the wear clearance in millimetres)")
    if sides not in ("both", "l", "r"):
        raise PlaceError("sides is both | l | r")
    for f in (body_npz, piece_npz):
        if not Path(f).exists():
            raise PlaceError(f"{f} not found: run mesh_to_npz first")
    from ..canon_asset import SETTINGS
    from copy import deepcopy
    defaults = {}
    if pair_scale_group is None and kind in ("boots", "gauntlets"):
        defaults["pair_scale_group"] = deepcopy(SETTINGS["pair_scale_group"])
        pair_scale_group = defaults["pair_scale_group"]["value"]
    if scale_anchor is None and kind == "boots":
        defaults["boots_scale_anchor"] = deepcopy(SETTINGS["boots_scale_anchor"])
        scale_anchor = defaults["boots_scale_anchor"]["value"]
    C = float(clear_mm) / 1000
    if kind == "chest":
        spec = importlib.util.spec_from_file_location("lw_place_piece", SCRIPTS / "place_piece.py")
        import sys
        sys.path.insert(0, str(SCRIPTS))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        V, T, meta = mod.build(str(body_npz), str(piece_npz), float(turn))
        return V, T, dict(meta, kind="chest", sides="both"), {"note": "the audits' chest placement, unchanged (chest width + 40 mm, axilla aligned)"}
    bV, bT, J = _body(body_npz)
    V, T = _piece(piece_npz, float(turn))
    source_turned = V.copy()
    if pair_scale_group not in (None, "common", "per_side"):
        raise PlaceError("pair_scale_group is common | per_side")
    if kind == "boots" and scale_anchor not in ANCHORS:
        raise PlaceError("boots scale_anchor is width (shaft) | height (knee) | foot (foot length)")
    if kind in ("boots", "gauntlets") and sides == "both" and pair_scale_group == "per_side":
        placed, transforms, reports = V.copy(), {}, {}
        masks = {side: V[:, 0]*sign > 0 for side, sign in (("l", 1), ("r", -1))}
        if any(not mask[T].all(1).any() for mask in masks.values()) or not (masks['l']|masks['r'])[T].all():
            raise PlaceError("independent pair scales need two sides separated at x=0 with no unassigned vertices")
        if not np.all(masks['l'][T].all(1)|masks['r'][T].all(1)):
            raise PlaceError("independent pair scales refuse triangles crossing x=0: split the pair first")
        for side, mask in masks.items():
            pv, _, sm, sr = place(kind, body_npz, piece_npz, turn, clear_mm, scale_anchor, side, "common")
            ids = np.flatnonzero(mask)
            placed[ids] = pv[ids]
            fit = G.similarity_fit(V[ids], pv[ids])
            if fit['max'] > 1e-9:
                raise PlaceError(f"the {side} placement is not one rigid similarity")
            transforms[side] = {"vertex_ids": ids.tolist(), "scale": float(fit['s']),
                                "rotation": np.asarray(fit['R']).tolist(), "translation": np.asarray(fit['t']).tolist()}
            reports[side] = sr
        meta = {"kind": kind, "scale": None, "pair_scale_group": "per_side", "side_transforms": transforms,
                "turn_deg": float(turn), "sides": sides, "clear_mm": float(clear_mm), "scale_anchor": scale_anchor,
                "uniform_scale": True, "uniform_scale_scope": "per_side", "defaults": defaults, "norm_lo": V.min(0).tolist(), "norm_hi": V.max(0).tolist()}
        recovered = undo_placement(placed, meta)
        return placed, T, meta, {"per_side": reports, "round_trip_m": float(np.abs(recovered-V).max())}
    if kind == "helmet":
        s, ap, ab, rep = _helmet(bV, bT, J, V, T, C)
    elif kind == "waist":
        s, ap, ab, rep = _waist(bV, bT, J, V, T, C)
    elif kind == "boots":
        s, ap, ab, rep = _boots(bV, bT, J, V, T, C, scale_anchor, sides)
    else:
        s, ap, ab, rep = _gauntlets(bV, bT, J, V, T, C, sides)
    V = rep.pop("_V", V)                                                         # a gauntlet's rigid axis correction, already applied
    Vp = _similarity(V, s, ap, ab)
    t = ab - s * ap
    meta = {"kind": kind, "scale": float(s), "translation": [float(x) for x in t], "anchor_shift": [float(x) for x in (ab - ap)], "tz": float(t[2]), "y_shift": float(t[1]), "x_shift": float(t[0]), "turn_deg": float(turn),
            "sides": sides, "clear_mm": float(clear_mm), "scale_anchor": scale_anchor, "uniform_scale": True,
            "pair_scale_group": pair_scale_group, "pair_scale_needs_decision": False, "defaults": defaults,
            "norm_lo": [float(x) for x in V.min(0)], "norm_hi": [float(x) for x in V.max(0)]}
    if kind == 'gauntlets':
        # Residual axis corrections are independent rigid maps even when both
        # sides share one scale. Retain them for scene replay and blocker inversion.
        transforms = {}
        covered = np.zeros(len(Vp), dtype=bool)
        for side, sign in (('l', 1), ('r', -1)):
            ids = np.flatnonzero(source_turned[:, 0] * sign > 0)
            if not len(ids):
                continue
            covered[ids] = True
            fit = G.similarity_fit(source_turned[ids], Vp[ids])
            if fit['max'] > 1e-9:
                raise PlaceError(f'the {side} gauntlet placement is not one proper rigid similarity')
            transforms[side] = {'vertex_ids': ids.tolist(), 'scale': float(fit['s']),
                                'rotation': np.asarray(fit['R']).tolist(), 'translation': np.asarray(fit['t']).tolist()}
        if not covered.all() or not np.all(np.logical_or.reduce([np.isin(T, tr['vertex_ids']).all(1) for tr in transforms.values()])):
            raise PlaceError('gauntlet placement maps require separated sides with no unassigned vertices or crossing triangles')
        meta['side_transforms'] = transforms
    return Vp, T, meta, rep


def undo_placement(vertices, meta):
    """Invert recorded placement maps in the turned piece frame, preserving native vertex ids."""
    result = np.asarray(vertices, float).copy()
    if meta.get("side_transforms"):
        for tr in meta["side_transforms"].values():
            ids = tr["vertex_ids"]
            result[ids] = ((result[ids]-tr["translation"])/tr["scale"]) @ np.asarray(tr["rotation"])
        return result
    return (result-np.asarray(meta["translation"]))/meta["scale"]


def run(root, kind, piece, body, out="placed.npz", turn=0.0, clear_mm=15.0, scale_anchor=None, sides="both", pair_scale_group=None):
    root = Path(root)
    V, T, meta, rep = place(kind, root / body, root / piece, turn, clear_mm, scale_anchor, sides, pair_scale_group)
    o = root / out
    o.parent.mkdir(parents=True, exist_ok=True)
    np.savez(o, V=V, T=T)
    (Path(str(o) + ".json")).write_text(json.dumps(meta, indent=1))
    return {"kind": kind, "scale": meta["scale"], "placed": str(o), "meta": meta, "report": rep}
