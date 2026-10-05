#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/place_piece.py, sha256 04a999487d74) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): place a torso piece on the MetaHuman body the way the audits do (from the 9c052d49 auditor's place.py):
# normalised z 0..1, scaled so its chest width = body chest width + 40 mm, axilla aligned, y by the chest slice's front/back centre
# (the pauldrons skew a bounding-box centre). Writes the placed triangles (body frame: Z up, faces -Y, wearer's left +X).
# Usage: <python with numpy> place_piece.py <placed.npz> <body.npz> <piece.npz> [--turn -90]
import argparse, json, os, sys, warnings, numpy as np
warnings.filterwarnings('ignore')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__))); import proportion_ratios as P
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); import axi_out as ax


def build(body_npz, piece_npz, turn=-90.0):
    b = np.load(body_npz); bV = b['V'].astype(float); bT = b['T']
    bz, bf = P.body_profile(bV, bT); bW, bD = P.WD(bf)
    zA = P.cross_up(bz, bW, 0.42, int(np.argmin(abs(bz - 1.3)))); m = (bz >= zA - 0.12) & (bz <= zA - 0.04); Wc = np.nanmedian(bW[m])
    d = np.load(piece_npz); V = d['V'].astype(float); T = d['T']
    th = np.radians(turn); R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]]); V = V @ R.T
    lo, hi = V.min(0), V.max(0); V = (V - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) / (hi[2] - lo[2])
    z, first = P.piece_profile(V, T); W, D = P.WD(first)
    zA_ = P.cross_up(z, W, 0.60, int(np.argmin(abs(z - 0.40)))); sw = (z >= zA_ - 0.12 / 0.72) & (z <= zA_ - 0.04 / 0.72)
    sW = (Wc + 0.04) / np.nanmedian(W[sw]); tz = zA - sW * zA_; Vp = V * sW; Vp[:, 2] += tz
    sg = P.slice_segs(bV, bT, zA - 0.08); s2 = sg[np.abs(sg[:, :, 0]).max(1) < 0.17]; byc = (s2[:, :, 1].min() + s2[:, :, 1].max()) / 2
    sgp = P.slice_segs(Vp, T, zA - 0.08); c = np.zeros(2)
    for _ in range(3):
        f = P.first_hits(sgp, c); c = c + np.array([0, (np.nanmedian(f[[7, 8, 9, 10, 11]]) - np.nanmedian(f[[25, 26, 27, 28, 29]])) / 2])
    Vp[:, 1] += byc - c[1]
    return Vp, T, {'scale': float(sW), 'tz': float(tz), 'y_shift': float(byc - c[1]), 'axilla_z': float(zA), 'turn_deg': float(turn),
                   'norm_lo': [float(x) for x in lo], 'norm_hi': [float(x) for x in hi]}   # to map placed points back to the piece's own frame


if __name__ == '__main__':
    if len(sys.argv) == 1:
        ax.home(__file__, 'Place a torso piece on the MetaHuman body (chest width + 40 mm, axilla aligned, chest-slice y centre) for clearance work')
        ax.helps([f'python3 scripts/proportion/place_piece.py <placed.npz> <body.npz> <piece.npz> [--turn -90]']); sys.exit(0)
    ap = argparse.ArgumentParser(); ap.add_argument('out'); ap.add_argument('body'); ap.add_argument('piece'); ap.add_argument('--turn', type=float, default=-90.0)
    a = ap.parse_args()
    for f in (a.body, a.piece):
        if not os.path.exists(f): ax.refuse(f'{f} not found', ['blender -b -P scripts/proportion/mesh_to_npz.py -- <out.npz> piece|body <mesh>'])
    V, T, meta = build(a.body, a.piece, a.turn); np.savez(a.out, V=V, T=T); json.dump(meta, open(a.out + '.json', 'w'), indent=1)
    ax.kv({**meta, 'out': a.out}); ax.helps([f'blender -b -P scripts/proportion/pose_clearance.py -- <out_dir> <body.glb> {a.out}'])
