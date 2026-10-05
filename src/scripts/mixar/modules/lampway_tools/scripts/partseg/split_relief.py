#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/split_relief.py, sha256 3357eb5eccdb) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): split a raised RELIEF (the lion heads on the pauldrons) out of its part as a new part, for MATERIAL only (it
# stays one rigid article with its plate). The relief is taken as whole Smart UV ISLANDS: Tripo's Smart UV segments by texture
# region, and its remesher spends polygons on relief, so the relief's islands are the DENSE ones - mean polygon area under
# --max-face-mm2 and at least --min-share of the part's area (smaller islands are rivets, studs and scrolls: left to the plate).
# Measured 2026-10-04 on chest seed 9c052d49 (texture critique round 2, fix 4). Rejected signals, each rendered:
#   - height above a Taubin low-pass (short or long pass): the lion's broad face reads level with the plate, so only the mane
#     tips and the rivets passed (the mottled r7b first try);
#   - smoothed polygon size, and normal spread within 6-16 mm: both light the mane outline only, and the outline never closes,
#     so a hole fill cannot recover the face;
#   - Smart UV islands, mean POLYGON (quad) area: lion face + mane 64 / 66 mm2 (right / left), beard 58 / 58, rivet-row scrolls
#     79-125, plates 160-740. At 70 the split is the whole head on both pauldrons and nothing else (rendered: lion_v2/isl70_*).
#     At 60 the lion islands (64-66) were missed. This is the rule.
# GROWTH (critique round 3): the crown spikes and jaw tufts are thin islands of their own (mean polygon 17-75 mm2, 0.8-6 cm2) on
# the lion's mesh shell. An island joins when it lies on a taken island's shell, shares at least --grow-min-touch welded vertices
# with the taken faces, its total area is under --grow-max-area-mm2, its median face centroid is within --grow-mm of the taken
# faces and its mean polygon is under --grow-max-face-mm2. Rivets are 24-triangle shells of their own: never joined.
# Round 4 (critique_v5b): at 15 mm / 90 mm2 with no touch test the crown spikes (islands 324, 480, 325, 95 at 20-27 mm) and the
# jaw tufts (309 at 94 mm2) were missed; touch >= 3 lets the distance go to 30 mm without taking plate island 342 (median 54 mm).
# Usage: <python with numpy+scipy> split_relief.py <out_prefix> <piece_uv.npz> <owner_tri.npy> <recipe.json> --split <part>:<new_part> [...]
#        [--max-face-mm2 70] [--min-share 0.01]
#   piece_uv.npz: mesh_to_npz 'piece_uv' export (V, T, UV per corner, POLY), in the owner's triangle order
# Writes <out_prefix>_owner_tri.npy, <out_prefix>_owner_poly.npy, <out_prefix>_recipe.json, <out_prefix>_split.json.
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
if __name__ == '__main__' and len(_A) < 6:
    if not _A: _ax.home(__file__, "Split a raised relief out of its part as a new material part: the part's dense Smart UV islands")
    else: print(f'error: {len(_A)} argument(s); at least 6 needed')
    _ax.helps(['python scripts/partseg/split_relief.py <out_prefix> <piece_uv.npz> <owner_tri.npy> <recipe.json> --split <part>:<new_part>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import argparse, copy, json, numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def uv_islands(T, UV):
    """island id per triangle: corners welded by (vertex, UV), as transfer_parts.py numbers them"""
    par = np.arange(len(T) * 3)
    def find(x):
        while par[x] != x: par[x] = par[par[x]]; x = par[x]
        return x
    key = {}
    for t in range(len(T)):
        for c in range(3):
            k = (int(T[t, c]), round(float(UV[t, c, 0]), 6), round(float(UV[t, c, 1]), 6)); q = t * 3 + c
            if k in key: par[find(q)] = find(key[k])
            else: key[k] = q
        par[find(t * 3 + 1)] = find(t * 3); par[find(t * 3 + 2)] = find(t * 3)
    return np.unique(np.array([find(t * 3) for t in range(len(T))]), return_inverse=True)[1]


def main():
    ap = argparse.ArgumentParser(); [ap.add_argument(k) for k in ('out', 'npz', 'owner', 'recipe')]
    ap.add_argument('--split', action='append', required=True)
    ap.add_argument('--max-face-mm2', type=float, default=70.0); ap.add_argument('--min-share', type=float, default=0.01)
    ap.add_argument('--grow-mm', type=float, default=30.0); ap.add_argument('--grow-max-face-mm2', type=float, default=100.0)
    ap.add_argument('--grow-min-touch', type=int, default=3); ap.add_argument('--grow-max-area-mm2', type=float, default=15000.0)
    a = ap.parse_args(); d = np.load(a.npz); V, T, UV, POLY = d['V'], d['T'], d['UV'], d['POLY']
    rec = json.load(open(a.recipe)); names = list(rec['parts']); own = np.load(a.owner)
    if len(own) != len(T): _ax.refuse(f'owner has {len(own)} labels for {len(T)} triangles', [])
    P = V[T]; area = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2
    pa = np.bincount(POLY, weights=area); pn = np.bincount(POLY, minlength=len(pa))
    _, w = np.unique(np.round(V / 1e-5).astype(np.int64), axis=0, return_inverse=True); Tw = w.ravel()[T]   # mesh shells, seams welded
    A = coo_matrix((np.ones(T.size), (np.repeat(np.arange(len(T)), 3), Tw.ravel())), shape=(len(T), Tw.max() + 1)).tocsr()
    shell = connected_components(A @ A.T, directed=False)[1]; Cen = P.mean(1)
    isl = uv_islands(T, UV); out_rec = copy.deepcopy(rec); new = own.copy(); rows = []; report = {'args': vars(a), 'splits': []}
    for sp in a.split:
        part, _, newp = sp.partition(':')
        if part not in names or not newp: _ax.refuse(f'bad --split {sp!r}: need <existing part>:<new part>', ['python scripts/partseg/split_relief.py (no args)'])
        if newp in out_rec['parts']: _ax.refuse(f'{newp} already in the recipe', [])
        tris = np.flatnonzero(own == names.index(part)); ids, inv = np.unique(isl[tris], return_inverse=True)
        ia = np.bincount(inv, weights=area[tris]); ip = [np.unique(POLY[tris[inv == k]]) for k in range(len(ids))]
        face_mm2 = np.array([pa[p].sum() / len(p) * 1e6 for p in ip]); share = ia / ia.sum()
        take = np.flatnonzero((face_mm2 < a.max_face_mm2) & (share >= a.min_share))
        if not len(take): _ax.refuse(f'{part}: no island under {a.max_face_mm2} mm2 per polygon with at least {a.min_share} of the area', [])
        sel = np.isin(inv, take); grown = []
        if a.grow_mm > 0:
            kd = cKDTree(Cen[tris[sel]]); lion_shells = set(np.unique(shell[tris[sel]]).tolist()); lion_v = np.zeros(Tw.max() + 1, bool); lion_v[Tw[tris[sel]].ravel()] = True
            for j in range(len(ids)):
                if j in take: continue
                m = tris[inv == j]
                if (face_mm2[j] < a.grow_max_face_mm2 and set(np.unique(shell[m]).tolist()) <= lion_shells and ia[j] * 1e6 < a.grow_max_area_mm2
                        and lion_v[np.unique(Tw[m].ravel())].sum() >= a.grow_min_touch and np.median(kd.query(Cen[m])[0]) * 1000 < a.grow_mm): grown.append(j)
            sel |= np.isin(inv, grown)
        k = len(out_rec['parts']); new[tris[sel]] = k
        out_rec['parts'][newp] = {'from': [f'{part}: Smart UV islands {ids[take].tolist()} (dense relief: polygon < {a.max_face_mm2} mm2, share >= {a.min_share}) + grown {ids[grown].tolist()} (same shell, touching >= {a.grow_min_touch} vertices, area < {a.grow_max_area_mm2} mm2, within {a.grow_mm} mm, polygon < {a.grow_max_face_mm2} mm2) by scripts/partseg/split_relief.py'],
                                  'class': rec['parts'][part]['class'], 'bind': f'as {part} (one rigid article with it; split for MATERIAL only)', 'added': 'split_relief.py'}
        isl_rows = [{'island': int(ids[j]), 'polys': int(len(ip[j])), 'face_mm2': round(float(face_mm2[j]), 1), 'share': round(float(share[j]), 3), 'taken': bool(j in take), 'grown': bool(j in grown)}
                    for j in np.argsort(-ia)[:12]]
        st = {'part': part, 'new_part': newp, 'islands_taken': len(take), 'islands_grown': len(grown), 'tris': int(sel.sum()), 'part_tris': len(tris), 'area_share': round(float(share[take].sum()), 3)}
        rows.append(st); report['splits'].append({**st, 'top_islands': isl_rows})
    names_b = list(out_rec['parts']); W = np.zeros((POLY.max() + 1, len(names_b))); np.add.at(W, (POLY, new), area)
    np.save(f'{a.out}_owner_tri.npy', new.astype(np.int32)); np.save(f'{a.out}_owner_poly.npy', W.argmax(1).astype(np.int32))
    json.dump(out_rec, open(f'{a.out}_recipe.json', 'w'), indent=1); json.dump(report, open(f'{a.out}_split.json', 'w'), indent=1)
    _ax.table('splits', rows, ['part', 'new_part', 'islands_taken', 'islands_grown', 'tris', 'part_tris', 'area_share'])
    _ax.helps([f'blender -b -P scripts/partseg/render_owner.py -- <mesh.fbx> {a.out}_owner_poly.npy {a.out}_recipe.json <render_prefix> --turn -90',
               f'read {a.out}_split.json for each part\'s top islands (polygon size, share, taken)'])


if __name__ == '__main__':
    main()
