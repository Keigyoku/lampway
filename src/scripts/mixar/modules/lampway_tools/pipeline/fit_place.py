# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_place: place a piece on the body by ENCLOSURE with ONE uniform scale, for all five kinds, and write the placement meta that maps later points back to the piece's frame.

Enclosure, not registration (memory armour-registration-bias): surface registration is biased toward the thick side (the fitted warrior sat 3-5 cm forward), so the piece is centred on its body
segment's own slice centres and scaled to a landmark width; never a per-region push (pose-not-push): ONE similarity (scale + translation, plus the rotation a gauntlet's axis needs, reported).
The body-side measures are the proportion scorer's (piece_ratios.py): helmet = the widest level above neck_02 (+2C), waist = the band at spine_01 + 3 cm, boots = shaft width / knee height /
foot length by ``scale_anchor`` (REQUIRED: the user has not ruled which), gauntlets = the bracer's major axis at 35 % vs the forearm's middle. The chest keeps the audits' placement
(scripts/proportion/place_piece.py, byte for byte). Frame: Z up, -Y front, +X the wearer's left. Pure numpy."""

import importlib.util
import json
from pathlib import Path

import numpy as np

from . import sections as S

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


def _piece(path, turn):
    d = np.load(path)
    V, T = d["V"].astype(float), d["T"]
    th = np.radians(turn)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    return V @ R.T, T


def _xy(p, c):
    """A section's (side, front) centre as world x, y (axis Z, side X, front +Y)."""
    return np.array([c[0], c[1]])


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
    cb, cp = S.centre(bp[k]), S.centre(pp[j])
    return s, np.array([cp[0], cp[1], z[j]]), np.array([cb[0], cb[1], hz[k]]), {"anchor": "head width at its widest level above neck_02, + 2C (the crest is not measured)",
                                                                              "body_width_mm": round(1000 * (bw[k] + 2 * C), 1), "piece_width_mm": round(1000 * w[j], 1)}


def _waist(bV, bT, J, V, T, C):
    zw, zk = J["spine_01"][2] + 0.03, J["calf_l"][2]
    torso = np.abs(bV[:, 0]) < 0.27
    bt = bT[torso[bT].all(1)]
    Ww, Dw, bp = S.section(bV, bt, np.zeros(3), S.Z, S.X, zw)
    lo, hi = V[:, 2].min(), V[:, 2].max()
    L = hi - lo
    z = np.linspace(hi - 0.03 * L, lo + 0.01 * L, 80)
    w, d, pp = S.profile(V, T, np.zeros(3), S.Z, S.X, z)
    band = z >= hi - 0.06 * L
    Wband = float(np.nanmedian(w[band]))
    cps = np.array([S.centre(p) for p, b in zip(pp, band) if b and p is not None])
    cp = np.median(cps, axis=0)
    cb = S.centre(bp)
    zmid = float(np.median(z[band]))
    return (Ww + 2 * C) / Wband, np.array([cp[0], cp[1], zmid]), np.array([cb[0], cb[1], zw]), {
        "anchor": "waist band width at spine_01 + 3 cm, + 2C; the band's mid level on that height", "body_width_mm": round(1000 * (Ww + 2 * C), 1), "piece_width_mm": round(1000 * Wband, 1)}


def _boots(bV, bT, J, V, T, C, anchor, sides):
    rows = []
    for sgn, sfx in ((1, "l"), (-1, "r")):
        if sides not in ("both", sfx):
            continue
        k_, a_ = J[f"calf_{sfx}"], J[f"foot_{sfx}"]
        leg = bV[:, 0] * sgn > 0.02
        bt = bT[leg[bT].all(1)]
        zt = a_[2] + 0.6 * (k_[2] - a_[2])
        bw, bd, bp = S.section(bV, bt, np.zeros(3), S.Z, S.X, zt)
        foot = bV[leg & (bV[:, 2] < 0.04)]
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
        scale = {"width": (bw + 2 * C) / pw, "height": (k_[2] + C) / h, "foot": (fl + 2 * C) / pfl}
        rows.append({"side": sfx, "scales": scale, "bp": S.centre(bp), "pp": S.centre(pp), "sole_body": float(foot[:, 2].min()), "sole_piece": float(lo),
                     "foot_y_body": float((foot[:, 1].max() + foot[:, 1].min()) / 2), "foot_y_piece": float((ft[:, 1].max() + ft[:, 1].min()) / 2)})
    s = float(np.mean([r["scales"][anchor] for r in rows]))
    anchor_p = np.array([np.mean([r["pp"][0] * np.sign(1 if r["side"] == "l" else -1) for r in rows]) * (1 if sides != "r" else -1), np.mean([r["foot_y_piece"] for r in rows]),
                         np.mean([r["sole_piece"] for r in rows])])
    anchor_b = np.array([np.mean([r["bp"][0] * np.sign(1 if r["side"] == "l" else -1) for r in rows]) * (1 if sides != "r" else -1), np.mean([r["foot_y_body"] for r in rows]),
                         np.mean([r["sole_body"] for r in rows])])
    return s, anchor_p, anchor_b, {"anchor": f"boot {anchor}", "scales_by_anchor": {a: round(float(np.mean([r["scales"][a] for r in rows])), 4) for a in ANCHORS},
                                   "per_side": {r["side"]: {a: round(float(v), 4) for a, v in r["scales"].items()} for r in rows}}


def _gauntlets(bV, bT, J, V, T, C, sides):
    rows = []
    for sgn, sfx in ((1, "l"), (-1, "r")):
        if sides not in ("both", sfx):
            continue
        el, wr, tip = J[f"lowerarm_{sfx}"], J[f"hand_{sfx}"], J[f"middle_03_{sfx}"]
        ax_ = (tip - el) / np.linalg.norm(tip - el)
        side = np.cross(ax_, S.Z)
        side /= np.linalg.norm(side)
        fa = np.linalg.norm(wr - el)
        arm = bV[:, 0] * sgn > 0.25
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
        rows.append({"scale": fmaj / pmaj, "angle": ang, "pt": c0 + (t35 - 0.0) * a, "bt": el + 0.5 * fa * ax_, "sfx": sfx, "bp": p.mean(0), "pp": pp.mean(0), "axis_b": ax_, "axis_p": a, "c0": c0, "t35": t35})
    s = float(np.mean([r["scale"] for r in rows]))
    ap_, ab_ = np.mean([r["pt"] for r in rows], axis=0), np.mean([r["bt"] for r in rows], axis=0)
    return s, ap_, ab_, {"anchor": "bracer major axis at 35 % of the piece vs the forearm's middle, + 2C", "axis_error_deg": {r["sfx"]: round(r["angle"], 2) for r in rows},
                         "scales": {r["sfx"]: round(float(r["scale"]), 4) for r in rows}}


def place(kind, body_npz, piece_npz, turn=0.0, clear_mm=15.0, scale_anchor=None, sides="both"):
    if kind not in KINDS:
        raise PlaceError(f"kind is one of {', '.join(KINDS)}")
    if not 0 <= float(clear_mm) <= 40:
        raise PlaceError("clear_mm is 0 to 40 (the wear clearance in millimetres)")
    if sides not in ("both", "l", "r"):
        raise PlaceError("sides is both | l | r")
    for f in (body_npz, piece_npz):
        if not Path(f).exists():
            raise PlaceError(f"{f} not found: run mesh_to_npz first")
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
    if kind == "boots" and scale_anchor not in ANCHORS:
        raise PlaceError("boots have no ruled scale anchor: pick width (shaft), height (knee) or foot (foot length); the user has not ruled which")
    if kind == "helmet":
        s, ap, ab, rep = _helmet(bV, bT, J, V, T, C)
    elif kind == "waist":
        s, ap, ab, rep = _waist(bV, bT, J, V, T, C)
    elif kind == "boots":
        s, ap, ab, rep = _boots(bV, bT, J, V, T, C, scale_anchor, sides)
    else:
        s, ap, ab, rep = _gauntlets(bV, bT, J, V, T, C, sides)
    Vp = _similarity(V, s, ap, ab)
    t = ab - s * ap
    meta = {"kind": kind, "scale": float(s), "translation": [float(x) for x in t], "anchor_shift": [float(x) for x in (ab - ap)], "tz": float(t[2]), "y_shift": float(t[1]), "x_shift": float(t[0]), "turn_deg": float(turn),
            "sides": sides, "clear_mm": float(clear_mm), "scale_anchor": scale_anchor, "uniform_scale": True,
            "norm_lo": [float(x) for x in V.min(0)], "norm_hi": [float(x) for x in V.max(0)]}
    return Vp, T, meta, rep


def run(root, kind, piece, body, out="placed.npz", turn=0.0, clear_mm=15.0, scale_anchor=None, sides="both"):
    root = Path(root)
    V, T, meta, rep = place(kind, root / body, root / piece, turn, clear_mm, scale_anchor, sides)
    o = root / out
    o.parent.mkdir(parents=True, exist_ok=True)
    np.savez(o, V=V, T=T)
    (Path(str(o) + ".json")).write_text(json.dumps(meta, indent=1))
    return {"kind": kind, "scale": meta["scale"], "placed": str(o), "meta": meta, "report": rep}
