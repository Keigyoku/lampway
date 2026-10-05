#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/proportion_ratios.py, sha256 d9e4890b6728) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): PRIMARY proportion measure for a torso piece (chest) against the MetaHuman body - the method the proportion
# auditor built and validated (scratch/scratch-tmp/proportion/audit/: prof2.py, bodyprof.py, indep.py; report.md), folded
# into one tool so every seed is scored the same way. No clearance fit: scale-free landmark ratios.
#   Per height slice (piece normalised to z 0..1; body in metres) the first hit of 36 horizontal rays from the slice's front/back
#   centre gives width W (left+right) and depth D (front+back). Landmarks: axilla = where W first exceeds a threshold above the
#   waist (the arm openings flare out); chest = a window just below the axilla; neck = the collar band; the collar rim = where W
#   falls halfway from chest width to neck width above the axilla; arm span = W just above the axilla.
#   Ratios vs the body's: chest D/W, neck W / chest W, axilla-to-collar / chest W, arm span / chest W. Score = RMS of their log
#   deviations (0 = the body's proportions). Placement report: scaled by chest width (+40 mm budget), axilla aligned.
# Usage: <python with numpy> proportion_ratios.py <out.json> <body.npz> <name>=<piece.npz>:<turn_deg> [...]
#   npz from mesh_to_npz.py; turn_deg brings the piece to face -Y with wearer's left at +X (Tripo FBX / Triangle glb: -90).
import argparse, json, os, sys, warnings, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); import axi_out as ax
ME = 'scripts/proportion/proportion_ratios.py'
TIGHT_FRONT_MM = 20.0          # chest depth over body+40 mm below this: the front plate likely meets the chest (tri v1: 7 mm, 23 % of rays through)
warnings.filterwarnings('ignore')
AZ = np.radians(np.arange(0, 360, 10))


def slice_segs(V, T, z):
    Z = V[T, 2]; s = Z > z; Tm = T[s.any(1) & ~s.all(1)]; segs = []
    for t in Tm:
        pts = []
        for a, b in ((0, 1), (1, 2), (2, 0)):
            pa, pb = V[t[a]], V[t[b]]
            if (pa[2] > z) != (pb[2] > z): u = (z - pa[2]) / (pb[2] - pa[2]); pts.append(pa[:2] + u * (pb[:2] - pa[:2]))
        if len(pts) == 2: segs.append(pts)
    return np.array(segs)


def first_hits(segs, c):
    d = np.stack([np.cos(AZ), np.sin(AZ)], 1); p = segs[:, 0] - c; e = segs[:, 1] - segs[:, 0]; out = []
    for dv in d:
        den = dv[0] * (-e[:, 1]) + e[:, 0] * dv[1]; ok = np.abs(den) > 1e-12
        t = np.where(ok, (p[:, 0] * (-e[:, 1]) + e[:, 0] * p[:, 1]) / np.where(ok, den, 1), -1)
        u = np.where(ok, (dv[0] * p[:, 1] - dv[1] * p[:, 0]) / np.where(ok, den, 1), -1)
        m = ok & (t > 0) & (u >= 0) & (u <= 1); out.append(t[m].min() if m.any() else np.nan)
    return np.array(out)


def WD(first):                                                          # az index: 0 = +X, 9 = +Y (back), 18 = -X, 27 = -Y (front)
    L = np.nanmedian(first[:, [35, 0, 1]], 1); R = np.nanmedian(first[:, [17, 18, 19]], 1)
    F = np.nanmedian(first[:, [25, 26, 27, 28, 29]], 1); B = np.nanmedian(first[:, [7, 8, 9, 10, 11]], 1)
    return L + R, F + B


def piece_profile(V, T, NZ=96):
    zs = np.linspace(0.02, 0.98, NZ); first = np.full((NZ, 36), np.nan)
    for k, z in enumerate(zs):
        sg = slice_segs(V, T, z)
        if len(sg) == 0: continue
        c = np.zeros(2)
        for _ in range(3):                                              # centre front/back
            f = first_hits(sg, c); fr = np.nanmedian(f[[25, 26, 27, 28, 29]]); bk = np.nanmedian(f[[7, 8, 9, 10, 11]])
            if np.isnan(fr) or np.isnan(bk): break
            c = c + np.array([0, (bk - fr) / 2])
        first[k] = f
    return zs, first


def body_profile(V, T):
    zs = np.linspace(0.85, 1.75, 91); first = np.full((len(zs), 36), np.nan)
    for k, z in enumerate(zs):
        sg = slice_segs(V, T, z); s2 = sg[np.abs(sg[:, :, 0]).max(1) < 0.17]
        if len(s2) == 0: continue
        first[k] = first_hits(sg, np.array([0, (s2[:, :, 1].min() + s2[:, :, 1].max()) / 2]))
    return zs, first


def cross_up(z, w, lvl, start):
    for k in range(start, len(z) - 1):
        if w[k] < lvl <= w[k + 1] or w[k] > lvl >= w[k + 1]: return z[k] + (lvl - w[k]) / (w[k + 1] - w[k]) * (z[k + 1] - z[k])
    return np.nan


def main(out, body_npz, *pieces, cw=(0.04, 0.12), nw=(1.60, 1.64), nwu=(0.90, 0.94), aw=(0.03, 0.09), thrB=0.42, thrP=0.60, s0=0.72):
    b = np.load(body_npz); bz, bf = body_profile(b['V'].astype(float), b['T']); bW, bD = WD(bf)
    zA = cross_up(bz, bW, thrB, int(np.argmin(abs(bz - 1.3)))); m = (bz >= zA - cw[1]) & (bz <= zA - cw[0])
    Wc, Dc = np.nanmedian(bW[m]), np.nanmedian(bD[m]); Wn = np.nanmedian(bW[(bz >= nw[0]) & (bz <= nw[1])]); mid = (Wc + Wn) / 2; zN = np.nan
    for k in range(int(np.argmin(abs(bz - 1.45))), len(bz) - 1):
        if bW[k] > mid >= bW[k + 1]: zN = bz[k] + (mid - bW[k]) / (bW[k + 1] - bW[k]) * (bz[k + 1] - bz[k]); break
    Wa = np.nanmedian(bW[(bz >= zA + aw[0]) & (bz <= zA + aw[1])])
    body = dict(zA=zA, Wc=Wc, Dc=Dc, Wn=Wn, zN=zN, Wa=Wa, DW=Dc / Wc, WnWc=Wn / Wc, LenWc=(zN - zA) / Wc, WaWc=Wa / Wc)
    rows = {}
    for spec in pieces:
        name, rest = spec.split('=', 1); f, turn = rest.rsplit(':', 1); d = np.load(f); V = d['V'].astype(float); T = d['T']
        th = np.radians(float(turn)); R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]]); V = V @ R.T
        lo, hi = V.min(0), V.max(0); V = (V - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) / (hi[2] - lo[2])
        z, first = piece_profile(V, T); W, D = WD(first)
        zA_ = cross_up(z, W, thrP, int(np.argmin(abs(z - 0.40)))); sw = (z >= zA_ - cw[1] / s0) & (z <= zA_ - cw[0] / s0)
        Wc_, Dc_ = np.nanmedian(W[sw]), np.nanmedian(D[sw]); Wn_ = np.nanmedian(W[(z >= nwu[0]) & (z <= nwu[1])]); mid_ = (Wc_ + Wn_) / 2; zN_ = np.nan
        for k in range(int(np.argmin(abs(z - zA_))) + 3, len(z) - 1):
            if W[k - 1] > mid_ >= W[k]: zN_ = z[k - 1] + (mid_ - W[k - 1]) / (W[k] - W[k - 1]) * (z[k] - z[k - 1]); break
        Wa_ = np.nanmedian(W[(z >= zA_ + aw[0] / s0) & (z <= zA_ + aw[1] / s0)])
        r = dict(DW=Dc_ / Wc_, WnWc=Wn_ / Wc_, LenWc=(zN_ - zA_) / Wc_, WaWc=Wa_ / Wc_)
        dev = {k: float(np.log(r[k] / body[k])) for k in r}; sW = (Wc + 0.04) / Wc_; tz = zA - sW * zA_
        rows[name] = {'file': f, 'turn': float(turn), 'ratios': {k: round(float(v), 4) for k, v in r.items()},
                      'dev_pct': {k: round(100 * (np.exp(v) - 1), 1) for k, v in dev.items()}, 'rms_logdev': round(float(np.sqrt(np.mean(np.square(list(dev.values()))))), 4),
                      'placed': {'scale_from_chest_width': round(float(sW), 4), 'collar_rim_vs_body_neck_mm': round(1000 * (tz + sW * zN_ - zN), 1),
                                 'chest_depth_excess_mm': round(1000 * (Dc_ * sW - (Dc + 0.04)), 1), 'neck_opening_mm': round(1000 * Wn_ * sW, 1),
                                 'arm_span_mm': round(1000 * Wa_ * sW, 1), 'axilla_to_collar_mm': round(1000 * (zN_ - zA_) * sW, 1)}}
        rows[name]['tight_front'] = bool(rows[name]['placed']['chest_depth_excess_mm'] < TIGHT_FRONT_MM)
    order = sorted(rows, key=lambda n: rows[n]['rms_logdev'])
    json.dump({'method': 'scripts/proportion/proportion_ratios.py header', 'body': {k: round(float(v), 4) for k, v in body.items()},
               'body_reference_mm': {'chest_w': round(1000 * Wc), 'chest_d': round(1000 * Dc), 'neck_w': round(1000 * Wn), 'axilla_to_neck': round(1000 * (zN - zA)), 'arm_span': round(1000 * Wa)},
               'ranking': order, 'pieces': rows}, open(out, 'w'), indent=1)
    ax.kv({'pieces_scored': len(rows), 'body_chest_mm': f"{round(1000 * Wc)} x {round(1000 * Dc)}", 'out': out})
    ax.table('ranking', [dict(name=n, rms=rows[n]['rms_logdev'], neck=rows[n]['dev_pct']['WnWc'], length=rows[n]['dev_pct']['LenWc'], arms=rows[n]['dev_pct']['WaWc'],
                              collar_mm=rows[n]['placed']['collar_rim_vs_body_neck_mm'], tight_front=rows[n]['tight_front']) for n in order],
             ['name', 'rms', 'neck', 'length', 'arms', 'collar_mm', 'tight_front'])
    ax.helps([f'python3 scripts/studios/tripo/seed_db.py ingest-scores {out}', 'python3 scripts/studios/tripo/seed_db.py'])


if __name__ == '__main__':
    if len(sys.argv) == 1:
        ax.home(__file__, 'Primary proportion score of a torso piece against the MetaHuman body: scale-free landmark ratios (0 = the body)')
        ax.kv({'method': 'chest D/W, neck/chest W, axilla-to-collar/chest W, arm span/chest W; RMS log deviation', 'validated': 'auditor 2026-10-04 (scratch/scratch-tmp/proportion/audit/report.md)',
               'known_flaw': f'depth is compared with the bare body, so a too-shallow piece scores well; tight_front flags chest depth < {TIGHT_FRONT_MM:.0f} mm over body+40 mm'})
        ax.helps([f'python3 {ME} <out.json> <body.npz> <name>=<piece.npz>:<turn_deg> ...', 'blender -b -P scripts/proportion/mesh_to_npz.py -- <out.npz> piece|body <mesh>']); sys.exit(0)
    ap = argparse.ArgumentParser(description='Primary proportion score vs the MetaHuman body (AXI: no args shows the method).')
    ap.add_argument('out'); ap.add_argument('body_npz'); ap.add_argument('pieces', nargs='+', help='<name>=<piece.npz>:<turn_deg>')
    a = ap.parse_args()
    for f in [a.body_npz] + [x.split('=', 1)[-1].rsplit(':', 1)[0] for x in a.pieces]:
        if not os.path.exists(f): ax.refuse(f'{f} not found', ['blender -b -P scripts/proportion/mesh_to_npz.py -- <out.npz> piece <mesh>'])
    main(a.out, a.body_npz, *a.pieces)
