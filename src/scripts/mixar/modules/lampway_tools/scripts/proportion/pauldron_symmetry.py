#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/proportion/pauldron_symmetry.py, sha256 4751aab78c4d) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): is one pauldron sunken? Matcap views hide depth, so measure it. For each mesh{i}.npz written by
# mesh_compare.py (triangles, height-normalised to the reference, centred on x/y, z 0..H): sample points on every
# triangle in proportion to its area; on an x/y grid of CELL x H keep the highest z (the top surface seen from above) and
# the lowest z (the underside seen from below). Each shoulder region (|x| >= X0 x H) is compared with the OTHER shoulder
# mirrored about x = 0: a dent on one side shows as a signed L - mirror(R) difference in mm (at the reference's 1 m
# height). Also the per-shoulder mean height against the reference mesh (mesh0). Writes sym.json and sym_<view>.png sheets
# (rows = meshes; columns = left, mirrored right, L - R difference). sym_side.png: the outward depth of each shoulder seen from
# its own side (|x| of the outermost surface per y/z cell; the right view mirrored to read like the left), L - R +-30 mm.
# Usage: <python with numpy+PIL> pauldron_symmetry.py <compare_dir> [labels...]
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['python scripts/proportion/pauldron_symmetry.py <compare_dir> [labels...]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 1:
    if not _A: _ax.home(__file__, "Is one pauldron sunken? Left vs mirrored right height maps from mesh_compare's npz")
    else: print(f'error: {len(_A)} argument(s); at least 1 needed')
    _ax.helps(['python scripts/proportion/pauldron_symmetry.py <compare_dir> [labels...]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import json, os, sys, numpy as np
from PIL import Image

CELL, X0, N = 0.004, 0.20, 3_000_000


def surfaces(P, H):
    a = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2
    rng = np.random.default_rng(0); k = rng.choice(len(P), N, p=a / a.sum())
    r1, r2 = rng.random(N), rng.random(N); s = np.sqrt(r1)
    pts = P[k, 0] * (1 - s)[:, None] + P[k, 1] * (s * (1 - r2))[:, None] + P[k, 2] * (s * r2)[:, None]
    nx, ny = int(1.2 / CELL), int(0.8 / CELL)
    ix = np.clip(((pts[:, 0] / H + 0.6) / CELL).astype(int), 0, nx - 1); iy = np.clip(((pts[:, 1] / H + 0.4) / CELL).astype(int), 0, ny - 1)
    top = np.full((ny, nx), -np.inf); bot = np.full((ny, nx), np.inf)
    np.maximum.at(top, (iy, ix), pts[:, 2] / H); np.minimum.at(bot, (iy, ix), pts[:, 2] / H)
    top[~np.isfinite(top)] = np.nan; bot[~np.isfinite(bot)] = np.nan
    return top, bot


def lateral(P, H):
    """side views: per (y, z) cell the outermost |x| of each shoulder (left x > 0, right x < 0), in H units"""
    a = np.linalg.norm(np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]), axis=1) / 2
    rng = np.random.default_rng(1); k = rng.choice(len(P), N, p=a / a.sum())
    r1, r2 = rng.random(N), rng.random(N); s = np.sqrt(r1)
    pts = P[k, 0] * (1 - s)[:, None] + P[k, 1] * (s * (1 - r2))[:, None] + P[k, 2] * (s * r2)[:, None]
    ny, nz = int(0.8 / CELL), int(1.0 / CELL)
    iy = np.clip(((pts[:, 1] / H + 0.4) / CELL).astype(int), 0, ny - 1); iz = np.clip((pts[:, 2] / H / CELL).astype(int), 0, nz - 1)
    out = {}
    for sd, sg in (('left', 1), ('right', -1)):
        m = sg * pts[:, 0] > 0; A = np.full((nz, ny), -np.inf); np.maximum.at(A, (iz[m], iy[m]), sg * pts[m, 0] / H)
        A[~np.isfinite(A)] = np.nan; out[sd] = A[::-1]                 # rows top-down
    return out


def colour(d, lim):
    d = np.clip(np.nan_to_num(d) / lim, -1, 1); img = np.ones(d.shape + (3,))
    img[..., 0] = np.where(d < 0, 1 + d, 1); img[..., 1] = 1 - np.abs(d); img[..., 2] = np.where(d > 0, 1 - d, 1)
    return img


def main(cdir, *labels):
    files = sorted(f for f in os.listdir(cdir) if f.startswith('mesh') and f.endswith('.npz'))
    H = 1.0; res = []; sheets = {'top': [], 'bottom': []}
    nx = int(1.2 / CELL); xc = (np.arange(nx) + 0.5) * CELL - 0.6; side = np.abs(xc) >= X0
    ref = None
    for i, f in enumerate(files):
        P = np.load(os.path.join(cdir, f))['P'].astype(np.float64); H = P[..., 2].max() - P[..., 2].min()
        top, bot = surfaces(P, H); lab = labels[i] if i < len(labels) else f
        row = {'mesh': lab}
        for name, S in (('top', top), ('bottom', bot)):
            M = S[:, ::-1]                                             # mirrored about x = 0 (grid symmetric)
            L = np.where(side & (xc > 0), S, np.nan); Rm = np.where(side & (xc > 0), M, np.nan)
            d = (L - Rm) * 1000                                        # mm at 1 m height; + = left higher
            both = np.isfinite(d)
            row[name] = {'L_minus_mirrorR_mean_mm': round(float(np.nanmean(d)), 1), 'abs_mean_mm': round(float(np.nanmean(np.abs(d))), 1),
                         'p05_mm': round(float(np.nanpercentile(d, 5)), 1), 'p95_mm': round(float(np.nanpercentile(d, 95)), 1),
                         'cells_compared': int(both.sum()),
                         'left_mean_z_mm': round(float(np.nanmean(np.where(side & (xc > 0), S, np.nan))) * 1000, 1),
                         'right_mean_z_mm': round(float(np.nanmean(np.where(side & (xc < 0), S, np.nan))) * 1000, 1)}
            if ref is not None:
                for sd, msk in (('left', side & (xc > 0)), ('right', side & (xc < 0))):
                    dd = (np.where(msk, S, np.nan) - np.where(msk, ref[name], np.nan)) * 1000
                    row[name][f'{sd}_vs_ref_mean_mm'] = round(float(np.nanmean(dd)), 1)
            crop = lambda A: A[:, xc > X0 - 0.02]
            lim = 60.0
            zimg = lambda A: np.dstack([np.nan_to_num((crop(A) - 0.55) / 0.45, nan=0)] * 3).clip(0, 1) if name == 'top' else np.dstack([np.nan_to_num(1 - crop(A) / 0.6, nan=0)] * 3).clip(0, 1)
            panel = np.concatenate([zimg(S), np.ones((S.shape[0], 4, 3)), zimg(M), np.ones((S.shape[0], 4, 3)), colour(crop(d), lim)], 1)
            sheets[name].append((lab, panel))
        lat = lateral(P, H); L, R = lat['left'], lat['right']
        sh = np.zeros(L.shape, bool); sh[int(0.0 / CELL):int(0.45 / CELL)] = True   # z from 1.0 H down to 0.55 H: the shoulder band
        d = (L - R) * 1000; d[~sh] = np.nan; half = L.shape[0] // 2
        upper = np.zeros(L.shape, bool); upper[:int(0.2 / CELL)] = True; lower = sh & ~upper
        row['side'] = {'L_minus_R_outermost_mm': round(float(np.nanmean(d)), 1), 'abs_mean_mm': round(float(np.nanmean(np.abs(d))), 1),
                       'upper_band_L_minus_R_mm': round(float(np.nanmean(np.where(upper, d, np.nan))), 1),
                       'lower_band_L_minus_R_mm': round(float(np.nanmean(np.where(lower, d, np.nan))), 1)}
        if ref is not None:
            for sd in ('left', 'right'):
                dd = (lat[sd] - ref['lat'][sd]) * 1000; dd[~sh] = np.nan
                row['side'][f'{sd}_vs_ref_upper_mm'] = round(float(np.nanmean(np.where(upper, dd, np.nan))), 1)
                row['side'][f'{sd}_vs_ref_lower_mm'] = round(float(np.nanmean(np.where(lower, dd, np.nan))), 1)
        g = lambda A: np.dstack([np.nan_to_num((A[:int(0.5 / CELL)] - 0.25) / 0.25, nan=0)] * 3).clip(0, 1)
        sheets.setdefault('side', []).append((lab, np.concatenate([g(L), np.ones((g(L).shape[0], 4, 3)), g(R), np.ones((g(L).shape[0], 4, 3)), colour(d[:int(0.5 / CELL)], 30.0)], 1)))
        if ref is None: ref = {'top': top, 'bottom': bot, 'lat': lat}
        res.append(row); print(json.dumps(row))
    for name, rows in sheets.items():
        img = np.concatenate([np.concatenate([p, np.ones((6,) + p.shape[1:])], 0) for _, p in rows], 0)
        im = Image.fromarray((img * 255).astype(np.uint8)); im = im.resize((im.width * 3, im.height * 3), Image.NEAREST)
        im.save(os.path.join(cdir, f'sym_{name}.png'))
    json.dump({'method': 'area-sampled points; per-cell max z (top) / min z (bottom) on a %.3f H grid; shoulders |x| >= %.2f H; '
               'L minus mirrored R in mm at 1 m height; sheet columns: left, mirrored right, difference (red = left lower, blue = left higher, +-60 mm)' % (CELL, X0),
               'rows': res}, open(os.path.join(cdir, 'sym.json'), 'w'), indent=1)


if __name__ == '__main__':
    main(*sys.argv[1:])
