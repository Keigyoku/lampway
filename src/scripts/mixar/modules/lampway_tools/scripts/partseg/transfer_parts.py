#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/transfer_parts.py, sha256 d69947f8bdfa) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): carry an APPROVED part set (its ruled part definitions, motion classes and binds) onto a new seed of the same
# design, instead of segmenting from scratch. Both meshes are placed on the MetaHuman the same way (scripts/proportion/place_piece.py:
# chest width + 40 mm, axilla aligned, chest-slice y centre), so they share the body frame. Each new triangle takes the label of
# the nearest old triangle (centroid kd-tree, distance kept); then every Smart UV ISLAND (UV-connected corners; texture regions)
# takes its area-weighted majority label, and every polygon its triangles' majority. Islands whose vote is weak or whose transfer
# distance is large are FLAGGED for review (never silently relabelled) - the new seed draws some parts differently.
# Usage: <python with numpy+scipy> transfer_parts.py <out_dir> <body.npz> <old.npz> <old_owner.npy> <recipe.json> <new_piece_uv.npz>
#        [--old-turn 0] [--new-turn -90] [--weak 0.6] [--far-mm 30]
#   old.npz: mesh_to_npz 'piece' export of the approved set's repaired mesh (triangles in the owner's face order)
#   new_piece_uv.npz: mesh_to_npz 'piece_uv' export (V, T, UV, POLY)
# Writes owner_tri.npy, owner_poly.npy (indices into the recipe's part list), islands.json, transfer.json.
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
if __name__ == '__main__' and len(_A) < 6:
    if not _A: _ax.home(__file__, 'Carry an approved part set onto a new seed: body-frame nearest-label transfer, Smart UV island vote, weak islands flagged')
    else: print(f'error: {len(_A)} argument(s); at least 6 needed')
    _ax.helps(['python scripts/partseg/transfer_parts.py <out_dir> <body.npz> <old.npz> <old_owner.npy> <recipe.json> <new_piece_uv.npz>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, json, os, sys, numpy as np
from scipy.spatial import cKDTree
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'proportion')); import place_piece


def main():
    ap = argparse.ArgumentParser(); [ap.add_argument(k) for k in ('out', 'body', 'old', 'old_owner', 'recipe', 'new')]
    ap.add_argument('--old-turn', type=float, default=0.0); ap.add_argument('--new-turn', type=float, default=-90.0)
    ap.add_argument('--weak', type=float, default=0.6); ap.add_argument('--far-mm', type=float, default=30.0)
    a = ap.parse_args(); os.makedirs(a.out, exist_ok=True)
    names = list(json.load(open(a.recipe))['parts']); rec = json.load(open(a.recipe))['parts']
    own = np.load(a.old_owner); oV, oT, om = place_piece.build(a.body, a.old, a.old_turn); nV, nT, nm = place_piece.build(a.body, a.new, a.new_turn)
    if len(own) != len(oT): _ax.refuse(f'old owner has {len(own)} labels for {len(oT)} triangles (face order must match)', [])
    oc = oV[oT].mean(1); nc = nV[nT].mean(1); dist, j = cKDTree(oc).query(nc); lab = own[j]
    d = np.load(a.new); UV = d['UV']; POLY = d['POLY']; P = nV[nT]
    area = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2
    key = {}; par = list(range(len(nT) * 3))
    def find(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    for t in range(len(nT)):                                            # islands: corners welded by (vertex, UV)
        for c in range(3):
            k = (int(nT[t, c]), round(float(UV[t, c, 0]), 6), round(float(UV[t, c, 1]), 6)); q = t * 3 + c
            if k in key: par[find(q)] = find(key[k])
            else: key[k] = q
        par[find(t * 3 + 1)] = find(t * 3); par[find(t * 3 + 2)] = find(t * 3)
    isl = np.unique(np.array([find(t * 3) for t in range(len(nT))]), return_inverse=True)[1]; NI = isl.max() + 1; NP = len(names)
    W = np.zeros((NI, NP)); np.add.at(W, (isl, lab), area)
    ilab = W.argmax(1); iconf = W.max(1) / np.maximum(W.sum(1), 1e-12)
    idist = np.bincount(isl, weights=dist * area, minlength=NI) / np.maximum(np.bincount(isl, weights=area, minlength=NI), 1e-12)
    tri = ilab[isl]
    NPo = POLY.max() + 1; Wp = np.zeros((NPo, NP)); np.add.at(Wp, (POLY, tri), area); poly = Wp.argmax(1)
    np.save(os.path.join(a.out, 'owner_tri.npy'), tri.astype(np.int32)); np.save(os.path.join(a.out, 'owner_poly.npy'), poly.astype(np.int32))
    np.save(os.path.join(a.out, 'island_tri.npy'), isl.astype(np.int32))      # islands.json numbering, per triangle (for fixes)
    flag = (iconf < a.weak) | (idist * 1000 > a.far_mm)
    isl_rows = [{'island': int(i), 'part': names[ilab[i]], 'confidence': round(float(iconf[i]), 3), 'mean_dist_mm': round(float(idist[i] * 1000), 1),
                 'area_m2': round(float(W[i].sum()), 5), 'runner_up': names[int(np.argsort(W[i])[-2])] if NP > 1 else None, 'flag': bool(flag[i])} for i in range(NI)]
    json.dump(isl_rows, open(os.path.join(a.out, 'islands.json'), 'w'), indent=1)
    parts = []
    for k, n in enumerate(names):
        new_f = int((poly == k).sum()); old_f = int((own == k).sum())
        m = tri == k; fl = flag[np.unique(isl[m])].sum() if m.any() else 0
        parts.append({'part': n, 'class': rec[n]['class'], 'old_tris': old_f, 'new_polys': new_f, 'new_area_m2': round(float(area[m].sum()), 4),
                      'flagged_islands': int(fl), 'mean_dist_mm': round(float((dist[m] * area[m]).sum() / max(area[m].sum(), 1e-12) * 1000), 1) if m.any() else None})
    rep = {'old_placement': om, 'new_placement': nm, 'triangles_new': int(len(nT)), 'islands': int(NI), 'islands_flagged': int(flag.sum()),
           'flagged_area_share': round(float(W[flag].sum() / W.sum()), 4), 'transfer_dist_mm_median_p95': [round(float(np.median(dist) * 1000), 1), round(float(np.percentile(dist, 95) * 1000), 1)],
           'parts_present': int(sum(p['new_polys'] > 0 for p in parts)), 'parts_total': NP, 'parts': parts, 'weak': a.weak, 'far_mm': a.far_mm}
    json.dump(rep, open(os.path.join(a.out, 'transfer.json'), 'w'), indent=1)
    _ax.kv({k: rep[k] for k in ('triangles_new', 'islands', 'islands_flagged', 'flagged_area_share', 'transfer_dist_mm_median_p95', 'parts_present', 'parts_total')})
    _ax.table('parts', [{'part': p['part'], 'class': p['class'], 'old': p['old_tris'], 'new': p['new_polys'], 'dist_mm': p['mean_dist_mm'], 'flagged': p['flagged_islands']} for p in parts],
              ['part', 'class', 'old', 'new', 'dist_mm', 'flagged'])
    _ax.helps([f'blender -b -P scripts/partseg/render_owner.py -- <new.fbx> {a.out}/owner_poly.npy <recipe.json> <out_prefix>'])


if __name__ == '__main__':
    main()
