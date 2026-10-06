# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/relief_tiles.py, sha256 41d076936717) on 2026-10-06 (specs/shelf/relief_map.md, second stage). The shelf
# header, with the measured rules behind the code:
# SPIKE (2026-10-04): multi-scale relief - tile each V3 view so the relief generator sees ornament at full scale (the
# captain: "Go for the crops"). Measured on the right pauldron lion: a 200 px plate crop upscaled to 1024 gives rivet
# rows, plate star engravings, eyes and mane strands that the whole-view relief does not have, while the whole view keeps
# the better big form - so the tiles supply only the FINE band, added on top of the whole-view detail.
#   make    tiles of TILE plate px, stride STRIDE, over each view's alpha box; a tile with < MIN_ALPHA covered is skipped; each tile is upscaled to 1024
#           (Lanczos) and its box recorded in tiles.json (plate frame, exact). (Run the Studio action tripo.relief on the tiles.)
#   stitch  per view: each tile's fine band = gaussian(PRE) - gaussian(SIG) in the tile frame, divided by its robust spread over the tile's alpha, clipped
#           to +-CLIP, resampled into the view's fine frame (default 3072 = 3x the 1024 relief frame) with a raised-cosine window, normalised by the summed
#           window; writes <View>.fine.npy (float32) and a preview.
# Lampway: the gaussian is pipeline.imgops.gaussian (scipy.ndimage.gaussian_filter's defaults, written in numpy: the app's python has no scipy); errors
# raise ReliefTileError instead of printing; a missing tile relief is reported, not printed.
import json
import os

import numpy as np
from PIL import Image

from .imgops import gaussian

TILE, STRIDE, MIN_ALPHA, UP = 200, 150, 0.05, 1024
PRE, CLIP = 1.5, 3.0
PLATE = 704
VIEWS = ('Front', 'Back', 'Left', 'Right')


class ReliefTileError(ValueError):
    pass


def make(v3, tdir, views=None):
    os.makedirs(tdir, exist_ok=True)
    rec = {'tile': TILE, 'stride': STRIDE, 'upscale_to': UP, 'plate': PLATE, 'tiles': []}
    for v in (views or VIEWS):
        p = os.path.join(v3, f'{v}.png')
        if not os.path.exists(p):
            raise FileNotFoundError(f'no plate {v}.png in {v3}')
        im = Image.open(p).convert('RGBA')
        if im.size != (PLATE, PLATE):
            raise ReliefTileError(f'{v}: the plate is {im.size}, expected {PLATE} x {PLATE} (the V3 plate frame)')
        a = np.asarray(im)[..., 3] > 127
        if not a.any():
            raise ReliefTileError(f'{v}: the plate has no opaque pixel')
        ys, xs = np.nonzero(a)
        x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
        nx = max(1, int(np.ceil((x1 - x0 + 1 - TILE) / STRIDE)) + 1)
        ny = max(1, int(np.ceil((y1 - y0 + 1 - TILE) / STRIDE)) + 1)
        for j in range(ny):
            for i in range(nx):
                bx = int(min(x0 + i * STRIDE, max(x1 + 1 - TILE, 0)))
                by = int(min(y0 + j * STRIDE, max(y1 + 1 - TILE, 0)))
                cov = a[by:by + TILE, bx:bx + TILE].mean()
                if cov < MIN_ALPHA:
                    continue
                name = f'{v}_t{j:02d}{i:02d}'
                tp = os.path.join(tdir, name + '.png')
                if not os.path.exists(tp):
                    im.crop((bx, by, bx + TILE, by + TILE)).resize((UP, UP), Image.LANCZOS).save(tp)
                rec['tiles'].append({'view': v, 'name': name, 'box_plate': [bx, by, TILE, TILE], 'alpha_cover': round(float(cov), 3)})
    with open(os.path.join(tdir, 'tiles.json'), 'w') as fh:
        json.dump(rec, fh, indent=1)
    rec['counts'] = {v: sum(t['view'] == v for t in rec['tiles']) for v in (views or VIEWS)}
    return rec


def stitch(v3, tdir, out, fine=3072):
    fine = int(fine)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(tdir, 'tiles.json')) as fh:
        rec = json.load(fh)
    report, missing = {}, []
    for v in sorted({t['view'] for t in rec['tiles']}):
        acc = np.zeros((fine, fine), np.float64)
        ws = np.zeros((fine, fine), np.float64)
        used = 0
        for t in [t for t in rec['tiles'] if t['view'] == v]:
            rp = os.path.join(tdir, t['name'] + '.relief.png')
            if not os.path.exists(rp):
                missing.append(t['name'])
                continue
            r = np.asarray(Image.open(rp).convert('RGB'))[..., 0].astype(np.float64)
            k = UP / TILE                                              # tile px per plate px
            sig = 1.5 * k * PLATE / 1024                               # 1.5 whole-view relief px, in tile px
            ta = np.asarray(Image.open(os.path.join(tdir, t['name'] + '.png')).convert('RGBA'))[..., 3] > 127
            d = gaussian(r, PRE) - gaussian(r, sig)
            spread = 1.4826 * np.median(np.abs(d[ta])) if ta.any() else 1.0
            d = np.clip(d / max(spread, 1e-9), -CLIP, CLIP) * ta
            bx, by, bw, bh = t['box_plate']
            s = fine / PLATE
            X0, Y0, W = int(round(bx * s)), int(round(by * s)), int(round(bw * s))
            dd = np.asarray(Image.fromarray(d.astype(np.float32)).resize((W, W), Image.BILINEAR))
            win1 = np.sin(np.linspace(0, np.pi, W)) ** 2 + 1e-3
            win = np.outer(win1, win1)
            ys, xs = slice(max(Y0, 0), min(Y0 + W, fine)), slice(max(X0, 0), min(X0 + W, fine))
            sy, sx = slice(ys.start - Y0, ys.stop - Y0), slice(xs.start - X0, xs.stop - X0)
            acc[ys, xs] += dd[sy, sx] * win[sy, sx]
            ws[ys, xs] += win[sy, sx]
            used += 1
        fd = np.where(ws > 0, acc / np.maximum(ws, 1e-12), 0).astype(np.float32)
        np.save(os.path.join(out, f'{v}.fine.npy'), fd)
        Image.fromarray((np.clip(fd / 6 + 0.5, 0, 1) * 255).astype(np.uint8)).resize((1024, 1024), Image.BILINEAR).save(os.path.join(out, f'{v}.fine_preview.png'))
        report[v] = {'tiles_used': used, 'fine_frame': fine}
    summary = {'pre_px_tile': PRE, 'clip': CLIP, 'band_top': '1.5 whole-view relief px', 'views': report, 'missing': missing}
    with open(os.path.join(out, 'fine.json'), 'w') as fh:
        json.dump(summary, fh, indent=1)
    return summary
