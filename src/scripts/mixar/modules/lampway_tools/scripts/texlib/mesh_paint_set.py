#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/mesh_paint_set.py, sha256 68b5de3c8809) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-05): assemble a projection plate set from mesh-paint results: for each view, the picked painted image gets the
# alpha of ITS clay render (exact by construction - the painted outline matched the clay at 0.92-0.99 IoU), saved as <view>.png
# for texlib/relief_project.py, which then runs with RP_COLOR_FULL=1 RP_NO_FLOW=1 (no relief warp: the plates are aligned already).
# The workflow (2026-10-05, the captain's "texture plates" question):
#   1. blender -b -P scripts/texlib/clay_view.py -- <mesh> <dir>/clay_<View>.png <View> 2048   (x4)
#   2. scripts/studios/tripo/tripo_image.py <run_dir> <prompt> --ref clay_<View>.png [--ref <a painted view, for consistency>]
#      --ref <V3 4K plate of that view>   (GPT Image 2.5, 4 variants, free quota; prompts: albedo_plates/prompt_meshpaint_v2*.txt)
#   3. pick the best of four per view (silhouette IoU vs the clay, plus the eye); this tool
#   4. RP_COLOR_FULL=1 RP_NO_FLOW=1 relief_project.py <mesh_uv_front-y.npz> <reliefs> <set_dir> <out> 4096; material_masks.py
# Usage: mesh_paint_set.py <dir with clay_<View>.png> <out_set_dir> Front=<img> Back=<img> Left=<img> Right=<img>
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); import axi_out as ax
if len(sys.argv) < 2:
    ax.home(__file__, 'Projection plate set from mesh-paint results: picked painted views with their clay-render alpha'); ax.helps(['python scripts/texlib/mesh_paint_set.py <clay_dir> <out_set_dir> Front=<img> Back=<img> Left=<img> Right=<img>']); raise SystemExit(0)
import numpy as np
from PIL import Image
ap = argparse.ArgumentParser(); ap.add_argument('clay_dir'); ap.add_argument('out'); ap.add_argument('picks', nargs='+')
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); picks = dict(p.split('=', 1) for p in a.picks); rows = []
for v, f in picks.items():
    im = Image.open(f).convert('RGB'); W = im.size[0]; cp = os.path.join(a.clay_dir, f'clay_{v}.png')
    if not os.path.exists(cp): ax.refuse(f'no clay render {cp}', [f'blender -b -P scripts/texlib/clay_view.py -- <mesh> {cp} {v} 2048'])
    clay = np.asarray(Image.open(cp).convert('RGB')).astype(float) / 255; bg = np.median(np.r_[clay[:16, :16].reshape(-1, 3), clay[-16:, -16:].reshape(-1, 3)], 0)
    m = (np.abs(clay - bg).max(-1) > 0.03).astype(np.uint8) * 255; out = im.copy(); out.putalpha(Image.fromarray(m).resize((W, W), Image.BILINEAR)); out.save(os.path.join(a.out, f'{v}.png'))
    small = lambda x: np.asarray(Image.fromarray(x).resize((512, 512))) > 127
    pa = np.asarray(im.resize((512, 512))).astype(float) / 255; pbg = np.median(np.r_[pa[:8, :8].reshape(-1, 3), pa[-8:, -8:].reshape(-1, 3)], 0); pm = np.abs(pa - pbg).max(-1) > 0.08; cm = small(m)
    rows.append({'view': v, 'source': f, 'size': W, 'silhouette_iou_vs_clay': round(float((pm & cm).sum() / max((pm | cm).sum(), 1)), 3)})
json.dump({'picks': picks, 'alpha': 'clay render silhouette (bg diff > 0.03)', 'rows': rows}, open(os.path.join(a.out, 'set.json'), 'w'), indent=1)
ax.table('views', rows, ['view', 'size', 'silhouette_iou_vs_clay', 'source']); ax.helps([f'RP_COLOR_FULL=1 RP_NO_FLOW=1 python scripts/texlib/relief_project.py <mesh_uv_front-y.npz> <reliefs_dir> {a.out} <out_dir> 4096'])
