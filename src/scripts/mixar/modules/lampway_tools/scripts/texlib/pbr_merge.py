#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/pbr_merge.py, sha256 cde228924c20) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; the AXI output module is the one beside these scripts.
# SPIKE (2026-10-05): one engine-ready PBR texture set for a PATCHED mesh from a studio PBR set (Tripo Texture + PBR on the Smart UV
# clone) plus our own projection. The studio maps share the clone's UV layout, and patch_holes.py/uv_patches.py never move an
# original island (measured: max UV move 0), so the studio texels are kept as they are; only the patch islands (faces with
# orig_poly < 0, which the studio never saw) are filled - base colour from our projected albedo atlas (mesh-paint plates),
# roughness/metallic from the median of their material class on the original faces, normal flat - and dilated into the gutters.
# The live Blender fixes are BAKED IN, so the engine gets plain maps: the per-material palette (Hue/Saturation/Value per mask in
# the given order, as Blender's Hue/Saturation node computes it, mask = factor), metallic forced to 0 on non-metal classes, and the
# normal map's strength (lerp toward flat). ORM: R = occlusion (1 when no AO map is given), G = roughness, B = metallic (UE order).
# Usage: pbr_merge.py <out_dir> --base B --normal N --rough R --metal M --masks <dir with mask_*.png + texel_face.npy>
#        --albedo <v3_colour_atlas.png> --mesh-npz <piece_uv npz> --orig-poly <orig_poly.npy> --params <live_material_params.json>
#        [--res 4096] [--base-res 8192] [--ao <ao.png>] [--dilate 16]
# Writes BaseColor (sRGB), Normal_GL and Normal_DX (UE: DirectX, green flipped), ORM, Roughness, Metallic, and merge.json.
import argparse, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..')); import axi_out as ax  # noqa: E702
if len(sys.argv) < 2:
    ax.home(__file__, 'Engine-ready PBR set for a patched mesh: studio PBR maps kept, patch islands filled, live palette and metal fixes baked in')
    ax.helps(['python scripts/texlib/pbr_merge.py <out_dir> --base B --normal N --rough R --metal M --masks <dir> --albedo <atlas> --mesh-npz <npz> --orig-poly <npy> --params <json>']); raise SystemExit(0)
import numpy as np
from PIL import Image
from scipy.ndimage import distance_transform_edt, zoom
Image.MAX_IMAGE_PIXELS = None
ap = argparse.ArgumentParser(); ap.add_argument('out')
for k in ('base', 'normal', 'rough', 'metal', 'masks', 'albedo', 'mesh_npz', 'orig_poly', 'params'): ap.add_argument('--' + k.replace('_', '-'), required=True)
ap.add_argument('--res', type=int, default=4096); ap.add_argument('--base-res', type=int, default=8192); ap.add_argument('--ao'); ap.add_argument('--dilate', type=int, default=16)
a = ap.parse_args(); os.makedirs(a.out, exist_ok=True); R, RB = a.res, a.base_res; P = json.load(open(a.params)); rep = {'args': vars(a)}
def load(p, mode, res):
    im = Image.open(p).convert(mode)
    if im.size != (res, res): im = im.resize((res, res), Image.LANCZOS)
    return np.asarray(im).astype(np.float32) / 255
def up(x, res):                                                        # mask/field resample to res (bilinear)
    return x if x.shape[0] == res else zoom(x, res / x.shape[0], order=1)
tf = np.load(os.path.join(a.masks, 'texel_face.npy'))                   # triangle id per texel (-1 empty), this mesh's UVs
d = np.load(a.mesh_npz); POLY = d['POLY']; orig = np.load(a.orig_poly)
if POLY.max() + 1 != len(orig): ax.refuse(f'orig_poly has {len(orig)} rows for {POLY.max() + 1} polygons', [])
patch_tri = orig[POLY] < 0; cov = tf >= 0; patch = cov & patch_tri[np.maximum(tf, 0)]
if tf.shape[0] != R: ax.refuse(f'texel_face is {tf.shape[0]}, --res is {R}: run the projection at the output resolution', [])
masks = {k: np.asarray(Image.open(os.path.join(a.masks, f'mask_{k}.png')).convert('L')).astype(np.float32) / 255 for k in ('gold', 'plate', 'red', 'linen', 'embroidery', 'leather')}
rep['patch_texels'] = int(patch.sum()); rep['covered_texels'] = int(cov.sum())
def fill(img, where, res):
    """dilate: every texel in `where`'s complement keeps its value; texels outside coverage take the nearest covered texel"""
    idx = distance_transform_edt(~where, return_distances=False, return_indices=True); return img[idx[0], idx[1]]
# ---------- base colour (base-res): studio base -> palette -> patches from our albedo -> gutters
B = load(a.base, 'RGB', RB)
def hsv(X):
    mx, mn = X.max(-1), X.min(-1); dl = mx - mn; r, g, b = X[..., 0], X[..., 1], X[..., 2]; safe = np.where(dl > 0, dl, 1)
    h = np.where(dl == 0, 0, np.where(mx == r, ((g - b) / safe) % 6, np.where(mx == g, (b - r) / safe + 2, (r - g) / safe + 4))) / 6
    return h, np.where(mx > 0, dl / np.where(mx > 0, mx, 1), 0), mx
def rgb(h, s, v):
    i = np.floor(h * 6).astype(int) % 6; f = h * 6 - np.floor(h * 6); p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return np.stack([np.choose(i, [v, q, p, p, t, v]), np.choose(i, [t, v, v, q, p, p]), np.choose(i, [p, p, t, v, v, q])], -1)
to_lin = lambda c: np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
to_srgb = lambda c: np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)
B = to_lin(B)                                                            # Blender's node works on LINEAR colour (measured 2026-10-05: the
for k in P['order']:                                                     # first set, adjusted in sRGB, came out pale - V 1.31 overshot)
    H_, S_, V_ = P['palette_hsv'][k]; h, s, v = hsv(B); adj = rgb((h + H_ - 0.5) % 1, np.clip(s * S_, 0, 1), v * V_)
    f = up(masks[k], RB)[..., None]; B = B * (1 - f) + adj * f
B = to_srgb(np.clip(B, 0, 1))
Al = load(a.albedo, 'RGB', RB); pB = up(patch.astype(np.float32), RB) > 0.5; B[pB] = Al[pB]
covB = up(cov.astype(np.float32), RB) > 0.5; B = fill(B, covB, RB)
Image.fromarray((np.clip(B, 0, 1) * 255).round().astype(np.uint8)).save(os.path.join(a.out, f'BaseColor_{RB}.png'))
del B, Al
# ---------- roughness / metallic (res): studio maps, class fixes, patch fill by class medians
Rg = load(a.rough, 'L', R); Mt = load(a.metal, 'L', R)
nonmetal = np.clip(sum(masks[k] for k in P['metal_zero_on']), 0, 1); Mt = Mt * (1 - nonmetal)
orig_cov = cov & ~patch; cls = np.argmax(np.stack([masks[k] for k in masks]), 0); names = list(masks); med = {}
for i, k in enumerate(names):
    m = orig_cov & (cls == i)
    if m.sum() > 100: med[k] = (float(np.median(Rg[m])), float(np.median(Mt[m])))
for i, k in enumerate(names):
    m = patch & (cls == i)
    if k in med: Rg[m], Mt[m] = med[k]
rep['class_rough_metal_medians'] = {k: [round(x, 3) for x in v] for k, v in med.items()}
Rg, Mt = fill(Rg, cov, R), fill(Mt, cov, R)
AO = load(a.ao, 'L', R) if a.ao else np.ones((R, R), np.float32)
Image.fromarray((Rg * 255).round().astype(np.uint8)).save(os.path.join(a.out, f'Roughness_{R}.png'))
Image.fromarray((Mt * 255).round().astype(np.uint8)).save(os.path.join(a.out, f'Metallic_{R}.png'))
Image.fromarray((np.stack([AO, Rg, Mt], -1) * 255).round().astype(np.uint8)).save(os.path.join(a.out, f'ORM_{R}.png'))
# ---------- normal (res): studio normal at the live strength (lerp toward flat), patches flat, OpenGL + DirectX
Nm = load(a.normal, 'RGB', R) * 2 - 1; s = float(P.get('normal_strength_live', 1.0)); flat = np.array([0, 0, 1], np.float32)
Nm = Nm * s + flat * (1 - s); Nm[patch] = flat; Nm /= np.maximum(np.linalg.norm(Nm, axis=-1, keepdims=True), 1e-6); Nm = fill(Nm, cov, R)
gl = ((Nm * 0.5 + 0.5) * 255).round().astype(np.uint8); Image.fromarray(gl).save(os.path.join(a.out, f'Normal_GL_{R}.png'))
dx = gl.copy(); dx[..., 1] = 255 - dx[..., 1]; Image.fromarray(dx).save(os.path.join(a.out, f'Normal_DX_{R}.png'))
rep['ao'] = 'given' if a.ao else 'none (R channel = 1)'; rep['normal_strength_baked'] = s
json.dump(rep, open(os.path.join(a.out, 'merge.json'), 'w'), indent=1)
ax.kv({'out': a.out, 'patch_texels': rep['patch_texels'], 'base': f'{RB}', 'maps': f'{R}', 'ao': rep['ao']})
