#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/piece_ratios.py, sha256 169bdac7c006) on 2026-10-05. The header below, with the measured rules behind the code, is
# the original's; paths and interpreters now come from Lampway's configuration. Lampway's change: a gauntlet that is not cuff-up (the finger end the upper end) is
# REFUSED instead of silently scored (the shelf only assumed it; see the gauntlets() comment on axis_sign).
# SPIKE (2026-10-05): proportion scores for the NON-torso pieces (helmet, waist, boots, gauntlets) against the MetaHuman body - the
# chest method (proportion_ratios.py) generalised: scale-free landmark ratios, piece vs body+clearance, score = RMS log deviation
# (0 = the body's proportions plus a uniform wear clearance C). Sections are taken perpendicular to a part axis; widths are the
# extents of the section's outer outline (all edges cut by the plane), in the part's own (side, front) frame.
#   helmet  : body = head above neck_02 (crown = top vertex). Ratios: D/W at the widest level; H/W where H = shell height (crest
#             trimmed: from the top down to where the section width first exceeds 45 % of the max) vs head-above-neck_02 + C.
#             Report: crest height / shell height.
#   waist   : body = pelvis region. Band = top 6 % of the piece; hips = widest level in the top 45 %. Ratios: band D/W vs body
#             waist (spine_01 + 3 cm) D/W; hip/band width vs body hip/waist width. Report: length in band widths and where the hem
#             falls on the body (fraction from waist to knee) after scaling by band width.
#   boots   : one boot per side (split at x = 0); body = leg below the knee (calf_* joint). Ratios: shaft D/W at 60 % height vs the
#             body leg at the same fraction of ankle..knee; foot length / shaft width; boot height / foot length vs knee height /
#             foot length. Both boots scored, the worse one counts.
#   gauntlets: one per side (split at x = 0); axis = the piece's longest principal axis, oriented cuff -> fingers (the cuff end is
#             the ROUNDER end: section minor/major near 1; the finger end is flat). Body = lowerarm -> middle_03 chain. Ratios (roll-free: section major/minor via
#             PCA): bracer minor/major at 35 % vs forearm mid; hand length (wrist..tip) / bracer major vs body; length / bracer
#             major vs body (elbow..fingertip). Wrist = the narrowest section between 45 % and 75 % of the length.
# Every kind is NEW (2026-10-05) and unvalidated: an auditor falsification is owed before its ranking is trusted (PIECE_PIPELINE).
# KNOWN BIASES (seed audits 2026-10-05, seed_audit/<piece>/audit.json): helmet D includes a crest swept down the back (+~39 % DW on
# every Helmet1 seed - equal across seeds, so the ranking holds); waist scores the design flare; boots score the knee-high height and
# the lion relief; gauntlets cannot see collapsed or slotted plates. Proportions did not separate any piece's 4 seeds - the audit did.
# SELF-TEST (the falsifier the method owes; scratch/.../proportion/piece_selftest/): the MetaHuman's own region, offset 15 mm along
# its normals, must score ~0. Measured: helmet 0.032, waist 0.022, boots 0.030, gauntlets 0.055 (residual = the test cut starting
# above the elbow). Gauntlets first scored 0.28: axis flipped ('wider end', then 'rounder end' both wrong) and the wrist detector
# sat mid-forearm - fixed (cuff = upper end; wrist = where the section flattens; body fingertip = farthest arm vertex).
# Usage: <python with numpy> piece_ratios.py <kind> <out.json> <body.npz> <name>=<piece.npz>:<turn_deg> [...] [--clear-mm 15]
#   body.npz from mesh_to_npz.py 'body' (with joints, -Y front); turn_deg brings the piece to -Y front, +Z up (Tripo FBX: -90).
import argparse, json, os, sys, warnings, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); import axi_out as ax
warnings.filterwarnings('ignore')
KINDS = ('helmet', 'waist', 'boots', 'gauntlets')
CUFF_UP_MARGIN = 0.3        # [UNVERIFIED threshold] roundness gap above which a gauntlet is called upside down: real seeds read 0.55-0.6 right-way-up, the body self-test (cut arm end) 0.2


def section(V, T, origin, axis, side, t):
    """outer extents of the cross-section at distance t along axis: (W along side, D along front=axis x side), point cloud"""
    front = np.cross(axis, side); P = V - origin; w = P @ axis; e = P @ side; f = P @ front
    s = w[T] > t; m = s.any(1) & ~s.all(1); pts = []
    for tri in T[m]:
        for a, b in ((0, 1), (1, 2), (2, 0)):
            ia, ib = tri[a], tri[b]
            if (w[ia] > t) != (w[ib] > t):
                u = (t - w[ia]) / (w[ib] - w[ia]); pts.append((e[ia] + u * (e[ib] - e[ia]), f[ia] + u * (f[ib] - f[ia])))
    if len(pts) < 6: return np.nan, np.nan, None
    p = np.array(pts); lo, hi = np.percentile(p, 1, 0), np.percentile(p, 99, 0)
    return hi[0] - lo[0], hi[1] - lo[1], p


def pca_extent(p):
    if p is None: return np.nan, np.nan
    c = p - p.mean(0); u, s, vt = np.linalg.svd(c, full_matrices=False); q = c @ vt.T
    ext = np.percentile(q, 99, 0) - np.percentile(q, 1, 0); return float(max(ext)), float(min(ext))


def load_piece(f, turn):
    d = np.load(f); V = d['V'].astype(float); T = d['T']; th = np.radians(turn)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]]); return V @ R.T, T


Z, X, NEGY = np.array([0., 0, 1]), np.array([1., 0, 0]), np.array([0., -1, 0])


def profile(V, T, origin, axis, side, ts):
    out = [section(V, T, origin, axis, side, t) for t in ts]; return np.array([o[0] for o in out]), np.array([o[1] for o in out]), [o[2] for o in out]


def helmet(body, V, T, C):
    BV, BT, J = body; nz = J['neck_02'][2]; crown = BV[:, 2].max()
    hz = np.linspace(nz, crown - 0.005, 40); bw, bd, _ = profile(BV, BT, np.array([0, 0, 0.]), Z, X, hz)
    k = np.nanargmax(bw); Wb, Db, Hb = bw[k] + 2 * C, bd[k] + 2 * C, (crown - nz) + C
    lo, hi = V[:, 2].min(), V[:, 2].max(); z = np.linspace(lo + 0.005 * (hi - lo), hi - 0.005 * (hi - lo), 80); w, d, _ = profile(V, T, np.zeros(3), Z, X, z)
    kmax = np.nanargmax(w); top = hi
    for j in range(kmax, len(z)):                                        # from the widest level UP: the first level narrower than 45 % of the
        if w[j] < 0.45 * w[kmax]: top = z[j]; break                      # max is the crest's base (scanning down from the top stopped inside
                                                                         # frilly crests - auditor, Helmet1 v1/v3, 2026-10-05)
    H = top - lo; r = {'DW': d[kmax] / w[kmax], 'HW': H / w[kmax]}; b = {'DW': Db / Wb, 'HW': Hb / Wb}
    return r, b, {'crest_over_shell': round(float((hi - top) / H), 3), 'shell_w_to_head_w_scale_mm': round(1000 * Wb, 1)}


def waist(body, V, T, C):
    BV, BT, J = body; zw = J['spine_01'][2] + 0.03; zk = J['calf_l'][2]
    torso = np.abs(BV[:, 0]) < 0.27; bt = BT[torso[BT].all(1)]               # the A-pose arms hang beside the hips: never in the waist
    bz = np.linspace(zk + 0.05, zw, 40); bw, bd, _ = profile(BV, bt, np.zeros(3), Z, X, bz)  # width (measured 2026-10-05: +143 % on every skirt)
    Ww, Dw = bw[-1] + 2 * C, bd[-1] + 2 * C; Wh = np.nanmax(bw[bz > zw - 0.30]) + 2 * C
    lo, hi = V[:, 2].min(), V[:, 2].max(); L = hi - lo; z = np.linspace(hi - 0.03 * L, lo + 0.01 * L, 80); w, d, _ = profile(V, T, np.zeros(3), Z, X, z)
    band = z >= hi - 0.06 * L; Wband, Dband = np.nanmedian(w[band]), np.nanmedian(d[band]); top45 = z >= hi - 0.45 * L
    r = {'DW': Dband / Wband, 'flare': np.nanmax(w[top45]) / Wband}; b = {'DW': Dw / Ww, 'flare': Wh / Ww}
    s = Ww / Wband; hem = zw - s * L
    return r, b, {'length_in_band_widths': round(float(L / Wband), 3), 'hem_fraction_waist_to_knee': round(float((zw - hem) / (zw - zk)), 3), 'scale_from_band': round(float(s), 4)}


def boots(body, V, T, C):
    BV, BT, J = body; res = []
    for sgn, sfx in ((1, 'l'), (-1, 'r')):
        k_, a_ = J[f'calf_{sfx}'], J[f'foot_{sfx}']; leg = BV[:, 0] * sgn > 0.02
        bt = BT[leg[BT].all(1)]; zt = a_[2] + 0.6 * (k_[2] - a_[2]); bw, bd, _ = section(BV, bt, np.zeros(3), Z, X, zt)
        foot = BV[leg & (BV[:, 2] < 0.04)]; fl = foot[:, 1].max() - foot[:, 1].min()
        b = {'DW': (bd + 2 * C) / (bw + 2 * C), 'foot_over_shaft': (fl + 2 * C) / (bw + 2 * C), 'height_over_foot': (k_[2] + C) / (fl + 2 * C)}
        pv = V[:, 0] * sgn > 0; pt = T[pv[T].all(1)]
        if len(pt) < 50: return None, None, {'error': f'no {sfx} boot found (split at x = 0)'}
        sub = V[np.unique(pt)]; lo, hi = sub[:, 2].min(), sub[:, 2].max(); h = hi - lo
        pw, pd, _ = section(V, pt, np.zeros(3), Z, X, lo + 0.6 * h); ft = sub[sub[:, 2] < lo + 0.04 * h]; pfl = ft[:, 1].max() - ft[:, 1].min()
        r = {'DW': pd / pw, 'foot_over_shaft': pfl / pw, 'height_over_foot': h / pfl}
        res.append((r, b, sfx))
    devs = [np.sqrt(np.mean([np.log(r[k] / b[k]) ** 2 for k in r])) for r, b, _ in res]; i = int(np.argmax(devs)); r, b, sfx = res[i]
    return r, b, {'worse_side': sfx, 'per_side_rms': [round(float(x), 4) for x in devs]}


def gauntlets(body, V, T, C):
    BV, BT, J = body; res = []
    for sgn, sfx in ((1, 'l'), (-1, 'r')):
        el, wr, tip = J[f'lowerarm_{sfx}'], J[f'hand_{sfx}'], J[f'middle_03_{sfx}']; ax_ = (tip - el) / np.linalg.norm(tip - el)
        side = np.cross(ax_, Z); side /= np.linalg.norm(side); Lb = np.linalg.norm(tip - el) + 0.02; arm = (BV[:, 0] * sgn) > 0.25
        bt = BT[arm[BT].all(1)]; fa = np.linalg.norm(wr - el)
        _, _, p = section(BV, bt, el, ax_, side, 0.5 * fa); fmaj, fmin = pca_extent(p); fmaj += 2 * C; fmin += 2 * C
        hv = BV[arm]; tipd = float(((hv - el) @ ax_).max())                    # the real fingertip: the arm's farthest vertex along the axis
        b = {'bracer_minor_over_major': fmin / fmaj, 'hand_over_bracer': (tipd - fa + C) / fmaj, 'length_over_bracer': (tipd + C) / fmaj}
        pv = V[:, 0] * sgn > 0; pt = T[pv[T].all(1)]
        if len(pt) < 50: return None, None, {'error': f'no {sfx} gauntlet found (split at x = 0)'}
        sub = V[np.unique(pt)]; c0 = sub.mean(0); u, s, vt = np.linalg.svd(sub - c0, full_matrices=False); a = vt[0]
        w = (sub - c0) @ a; L = w.max() - w.min()
        def width_at(frac, sign):
            t = (w.min() if sign > 0 else w.max()) + sign * frac * L; sd = np.cross(sign * a, Z); sd = sd / max(np.linalg.norm(sd), 1e-9)
            _, _, p_ = section(V, pt, c0, sign * a, sd, t - (c0 @ (sign * a)) + (c0 @ (sign * a)))
            return pca_extent(p_)
        # orient: the cuff end is the ROUNDER one (minor/major of its section near 1); the finger end is flat (palm). Measured
        # 2026-10-05: "the wider end" flipped on the body self-test (a flat palm is as wide as a forearm) and scored 0.28.
        sd0 = np.cross(a, Z); sd0 /= max(np.linalg.norm(sd0), 1e-9)
        def roundness(t):
            mj, mn_ = pca_extent(section(V, pt, c0, a, sd0, t)[2]); return mn_ / mj if mj == mj and mj > 0 else 0.0
        r_lo = np.nanmean([roundness(w.min() + f * L) for f in (0.08, 0.12, 0.16)]); r_hi = np.nanmean([roundness(w.max() - f * L) for f in (0.08, 0.12, 0.16)])
        up_is_min = (c0 + w.min() * a)[2] >= (c0 + w.max() * a)[2]
        r_up, r_dn = (r_lo, r_hi) if up_is_min else (r_hi, r_lo)
        if r_dn > r_up + CUFF_UP_MARGIN:          # Lampway's guard (the shelf only assumed it): the finger end (flat) is the upper end - measured on Gauntlets1: cuff end 0.90-0.95, finger end 0.33-0.39
            return None, None, {'error': f'gauntlet is not cuff-up: the turn or orientation is wrong (upper end roundness {r_up:.2f}, lower {r_dn:.2f}; the cuff is the round end and stands on top)', 'axis': 'finger end up'}
        sgn_ax = 1 if (c0 + w.min() * a)[2] >= (c0 + w.max() * a)[2] else -1   # the cuff is the UPPER end: the V3/Tripo gauntlets stand
        # fingers-down (measured 2026-10-05: roundness flipped on the body self-test too - a cut arm end and a finger cluster both read round)
        a2 = sgn_ax * a; sd2 = np.cross(a2, Z); sd2 /= max(np.linalg.norm(sd2), 1e-9); w2 = (sub - c0) @ a2; t0 = w2.min()
        meas = [pca_extent(section(V, pt, c0, a2, sd2, t0 + f * L)[2]) for f in np.linspace(0.05, 0.95, 37)]; fr = np.linspace(0.05, 0.95, 37)
        maj = np.array([m[0] for m in meas]); mn = np.array([m[1] for m in meas]); k35 = int(np.argmin(abs(fr - 0.35)))
        rr = mn / maj; cand = np.flatnonzero((fr >= 0.40) & (fr <= 0.85) & (rr < 0.8 * rr[k35]))   # the wrist: where the section first
        kw = int(cand[0]) if len(cand) else int(np.flatnonzero((fr >= 0.45) & (fr <= 0.75))[0])        # flattens into the hand (measured: the
                                                                                                # narrowest section sat mid-forearm, +47 % hand)
        r = {'bracer_minor_over_major': mn[k35] / maj[k35], 'hand_over_bracer': ((1 - fr[kw]) * L) / maj[k35], 'length_over_bracer': L / maj[k35]}
        res.append((r, b, sfx, {'wrist_frac': round(float(fr[kw]), 3), 'L_mm': round(1000 * float(L), 1), 'axis_sign': int(sgn_ax), 'r': {k: round(float(v), 3) for k, v in r.items()}, 'b': {k: round(float(v), 3) for k, v in b.items()}}))
    devs = [np.sqrt(np.mean([np.log(r[k] / b[k]) ** 2 for k in r])) for r, b, _, _ in res]; i = int(np.argmax(devs)); r, b, sfx, _ = res[i]
    return r, b, {'worse_side': sfx, 'per_side_rms': [round(float(x), 4) for x in devs], 'sides': {x[2]: x[3] for x in res}}


def main():
    if len(sys.argv) == 1:
        ax.home(__file__, 'Proportion scores for helmet / waist / boots / gauntlets vs the MetaHuman (scale-free ratios, RMS log deviation; NEW, unvalidated)')
        ax.helps(['python3 tools/proportion/piece_ratios.py <helmet|waist|boots|gauntlets> <out.json> <body.npz> <name>=<piece.npz>:<turn_deg> ...']); sys.exit(0)
    ap = argparse.ArgumentParser(); ap.add_argument('kind', choices=KINDS); ap.add_argument('out'); ap.add_argument('body'); ap.add_argument('pieces', nargs='+')
    ap.add_argument('--clear-mm', type=float, default=15.0); a = ap.parse_args(); C = a.clear_mm / 1000
    if not 0 <= a.clear_mm <= 40: ax.refuse(f'--clear-mm {a.clear_mm} is out of range: use 0 to 40 (a wear clearance in millimetres)', [])
    if not os.path.exists(a.body): ax.refuse(f'{a.body} not found', ['blender -b -P tools/proportion/mesh_to_npz.py -- <out.npz> body'])
    bd = np.load(a.body)
    if 'J' not in bd.files or 'names' not in bd.files: ax.refuse('body.npz has no joints: export with `mesh_to_npz ... body` (mode body)', ['blender -b -P tools/proportion/mesh_to_npz.py -- <out.npz> body'])
    J = {str(n): v for n, v in zip(bd['names'], bd['J'])}; body = (bd['V'].astype(float), bd['T'], J)
    fn = {'helmet': helmet, 'waist': waist, 'boots': boots, 'gauntlets': gauntlets}[a.kind]; rows = {}
    for spec in a.pieces:
        name, rest = spec.split('=', 1); f, turn = rest.rsplit(':', 1)
        if not os.path.exists(f): ax.refuse(f'{f} not found', ['blender -b -P tools/proportion/mesh_to_npz.py -- <out.npz> piece <mesh>'])
        V, T = load_piece(f, float(turn)); r, b, info = fn(body, V, T, C)
        if r is None: rows[name] = {'file': f, 'error': info.get('error')}; continue
        dev = {k: float(np.log(r[k] / b[k])) for k in r}
        rows[name] = {'file': f, 'turn': float(turn), 'ratios': {k: round(float(v), 4) for k, v in r.items()}, 'body': {k: round(float(v), 4) for k, v in b.items()},
                      'dev_pct': {k: round(100 * (np.exp(v) - 1), 1) for k, v in dev.items()}, 'rms_logdev': round(float(np.sqrt(np.mean(np.square(list(dev.values()))))), 4), 'info': info}
    order = sorted([n for n in rows if 'rms_logdev' in rows[n]], key=lambda n: rows[n]['rms_logdev'])
    json.dump({'kind': a.kind, 'clearance_mm': a.clear_mm, 'method': 'tools/proportion/piece_ratios.py header', 'validated': False, 'ranking': order, 'pieces': rows}, open(a.out, 'w'), indent=1)
    ax.kv({'kind': a.kind, 'scored': len(order), 'out': a.out, 'validated': False})
    ax.table('ranking', [dict(name=n, rms=rows[n]['rms_logdev'], devs=json.dumps(rows[n]['dev_pct'])) for n in order], ['name', 'rms', 'devs'])
    ax.helps([f'python3 tools/studios/tripo/seed_db.py ingest-scores {a.out}'])


if __name__ == '__main__':
    main()
