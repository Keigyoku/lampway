#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/partseg/apply_part_fixes.py, sha256 807a28584d25) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): apply an auditor's machine-readable part fixes (fixes.json) to a transferred owner map. Each fix relabels to
# "target_part" either whole Smart UV islands ("islands": ids in the transfer's islands.json numbering) or every triangle whose
# centroid lies in a box ("bbox_fbx": [[x0,y0,z0],[x1,y1,z1]] in the mesh's import frame), optionally only triangles currently
# owned by "only_from_parts". Polygons then take their triangles' area majority. Writes a NEW owner map; never overwrites.
# Usage: python apply_part_fixes.py <transfer_dir> <piece_uv.npz> <recipe.json> <fixes.json> <out_owner_poly.npy>
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
if __name__ == '__main__' and len(_A) < 5:
    if not _A: _ax.home(__file__, "Apply an auditor's part fixes (island or bbox relabels) to a transferred owner map; writes a new map")
    else: print(f'error: {len(_A)} argument(s); at least 5 needed')
    _ax.helps(['python scripts/partseg/apply_part_fixes.py <transfer_dir> <piece_uv.npz> <recipe.json> <fixes.json> <out_owner_poly.npy>']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import json, os, numpy as np
TD, NPZ, REC, FIX, OUT = _A[:5]
if os.path.exists(OUT): _ax.refuse(f'{OUT} exists; never overwritten', [])
names = list(json.load(open(REC))['parts']); d = np.load(NPZ); P = d['V'][d['T']]; POLY = d['POLY']
tri = np.load(os.path.join(TD, 'owner_tri.npy')).copy(); isl = np.load(os.path.join(TD, 'island_tri.npy'))
area = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2; cen = P.mean(1)
fixes = json.load(open(FIX)); fixes = fixes.get('fixes', fixes) if isinstance(fixes, dict) else fixes; log = []
for k, f in enumerate(fixes):
    t = f.get('target_part')
    if t not in names: log.append({'fix': k, 'error': f'unknown target_part {t!r}'}); continue
    m = np.zeros(len(tri), bool)
    if f.get('islands'): m |= np.isin(isl, f['islands'])
    if f.get('bbox_fbx'):
        lo, hi = np.array(f['bbox_fbx'][0]), np.array(f['bbox_fbx'][1]); m |= np.all((cen >= lo) & (cen <= hi), axis=1)
    if f.get('only_from_parts'): m &= np.isin(tri, [names.index(n) for n in f['only_from_parts'] if n in names])
    before = np.unique(tri[m], return_counts=True); tri[m] = names.index(t)
    log.append({'fix': k, 'target': t, 'triangles': int(m.sum()), 'from': {names[int(a)]: int(b) for a, b in zip(*before)}})
W = np.zeros((POLY.max() + 1, len(names))); np.add.at(W, (POLY, tri), area); poly = W.argmax(1).astype(np.int32)
np.save(OUT, poly); np.save(OUT.replace('.npy', '_tri.npy'), tri.astype(np.int32)); json.dump(log, open(OUT.replace('.npy', '.json'), 'w'), indent=1)
_ax.kv({'fixes': len(fixes), 'applied': sum('error' not in l for l in log), 'errors': sum('error' in l for l in log), 'parts_present': int(len(np.unique(poly))), 'out': OUT})
_ax.table('fixes', [{'fix': l['fix'], 'target': l.get('target', '-'), 'tris': l.get('triangles', 0), 'error': l.get('error')} for l in log], ['fix', 'target', 'tris', 'error'])
_ax.helps(['blender -b -P scripts/partseg/render_owner.py -- <mesh.fbx> <out_owner_poly.npy> <recipe.json> <out_prefix> --turn -90'])
