#!/usr/bin/env python3
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/relief_project.py, sha256 0b6fa16d4501) on 2026-10-05. The header below, with the
# measured rules behind the code, is the original's; paths and interpreters now come from Lampway's configuration.
# SPIKE (2026-10-04): project view reliefs (scripts/studios/tripo/relief_gen.py: one 8-bit depth PNG per V3 turnaround view, in the view's own
# frame) onto a UV-mapped mesh and write a DETAIL height map in the mesh's UV atlas (the user: "I want to see what
# this buys us for quality").
#   1. rasterize the mesh in UV space: every texel gets its 3D point and the face's normal (face id kept)
#   2. per view, an orthographic camera (front = -Y, back = +Y, left = +X, right = -X, up = +Z); the mesh's silhouette is
#      registered to the V3 plate's alpha (bounding boxes, then an IoU search over scale and shift) and z-buffered
#   3. the relief exaggerates local depth (fitted to the mesh's overall depth one 8-bit step is ~2 mm and ornaments come out
#      centimetres deep - measured 2026-10-04), so only its SHAPE is used: detail = relief - gaussian(relief, SIGMA) on a
#      0.7 px pre-blur (8-bit terraces), divided by its robust spread inside the garment (1.4826 x median |d|), clipped
#      to +-CLIP spreads, times STRENGTH_M (a look parameter, judged in renders and recorded)
#   2b. (2026-10-04, the doubled contours of the first renders) the plates do not match the mesh's proportions everywhere
#      (side silhouettes overlap 0.88), so no global scale+shift fits - a global search made the side views WORSE
#      (measured in renders). Instead dense optical flow (OpenCV DIS) aligns the relief's mid-scale detail (DoG 2..10 px)
#      to the mesh's own depth detail in that view; the flow is smoothed (FLOW_SMOOTH px) and capped (FLOW_MAX px), and
#      kept only if it raises the masked correlation
#   4b. multi-scale (relief_tiles.py): when <View>.fine.npy (the stitched FINE band from plate tiles, normalised units,
#      in a frame k x the relief frame) is in fine_dir, the texel adds FINE_W x its fine sample, taken through the same
#      alignment flow as the coarse relief
#   4c. the V3 plate's COLOUR goes through the same registration and flow (plate and relief share a frame) into a colour
#      atlas with the same view weights - a classification source for material masks, never final albedo (V3 has lighting
#      painted in); the texel -> face map is saved so a texel's part is known
#   5. each texel takes the views that see it, with a soft depth test (full weight within EPS, fading to 0 at 2 EPS) and
#      weight |n . view|^POWER so the best-facing view dominates (hard view handovers drew straight lines across plates);
#      texels no view sees get 0; a gutter is filled from the nearest covered texel
# Usage (python with numpy, scipy, pillow): relief_project.py <mesh.npz> <views_dir> <v3_dir> <out_dir> [res] [strength_m] [preblur_px] [fine_dir] [fine_w]
#   mesh.npz from a Blender dump: P (faces,3,3) world positions, UV (faces,3,2); views_dir holds <View>.relief.png
# --- AXI prelude (tools/AXI.md): no args shows what this is; too few args or an unknown flag refuses on stdout (script runs only, never on import) ---
import sys as _sys, os as _os
_sys.path.insert(0, _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), '..')); import axi_out as _ax
_A = _sys.argv[1:]
_bad = [] if __name__ != '__main__' else [x for x in _A if x.startswith('--') and x.split('=')[0] not in []]
if _bad: print(f'error: unknown flag(s) {_bad}'); _ax.helps(['python scripts/texlib/relief_project.py <mesh.npz> <views_dir> <v3_dir> <out_dir> [res] [strength_m] [preblur_px] [fine_dir] [fine_w]']); _sys.stdout.flush(); raise SystemExit(2)
if __name__ == '__main__' and len(_A) < 4:
    if not _A: _ax.home(__file__, 'Project the view reliefs (relief_gen.py depth PNGs) onto a UV atlas as a detail height map')
    else: print(f'error: {len(_A)} argument(s); at least 4 needed')
    _ax.helps(['python scripts/texlib/relief_project.py <mesh.npz> <views_dir> <v3_dir> <out_dir> [res] [strength_m] [preblur_px] [fine_dir] [fine_w]']); _sys.stdout.flush(); raise SystemExit(0 if not _A else 1)
# --- end AXI prelude ---
import json, os, sys, time, numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, distance_transform_edt, map_coordinates

VIEWS = {'Front': ((1, 0, 0), (0, 0, 1), (0, -1, 0)), 'Back': ((-1, 0, 0), (0, 0, 1), (0, 1, 0)),
         'Left': ((0, 1, 0), (0, 0, 1), (1, 0, 0)), 'Right': ((0, -1, 0), (0, 0, 1), (-1, 0, 0))}   # (image right, image up, toward camera)
F = 1024           # relief frame
SIGMA = 6.0        # px in the relief frame (~8 mm): forms larger than this are the mesh's own
CLIP = 3.0         # robust spreads
PREBLUR = 1.5      # px: the relief's finest texels are 8-bit steps and noise; a band-pass keeps PREBLUR..SIGMA
STRENGTH_M = 0.0015   # metres per robust spread of detail
EPS = 0.004        # m: z-buffer tolerance (soft to 2 EPS)
POWER = 4          # view weight |n . view|^POWER
FLOW_SMOOTH = 8.0  # px
FLOW_MAX = 16.0    # px
FINE_W = 0.6       # weight of the tile fine band against the whole-view band
# 2026-10-04 (the user: "are you projecting the upscaled plates?"): the 4K plates were shrunk to the 1024 relief frame before
# sampling. RP_COLOR_FULL=1 samples the colour from the plate at its own resolution at the flow-warped frame position (alignment
# stays in the 1024 frame, scaled by plate/F). RP_MESH_HEIGHT=<iters> also writes mesh_height_m.npy: each texel's signed offset
# from a Taubin-smoothed copy of the MESH (the mesh's own raised detail, aligned by construction) for gold-on-relief masks.
NO_FLOW = os.environ.get('RP_NO_FLOW', '0') == '1'   # plates painted over the mesh's own render are aligned already: no relief warp
COLOR_FULL = os.environ.get('RP_COLOR_FULL', '0') == '1'; MESH_HEIGHT_IT = int(os.environ.get('RP_MESH_HEIGHT', '0'))


def raster(T, attr, W, H, zbuf=None):
    """T (n,3,2) pixel coords, attr (n,3,k); returns (W*H,k) interpolated attr and face id (-1 empty).
    zbuf: if given, attr[...,0] is depth and the nearest (largest) wins"""
    k = attr.shape[2]; out = np.zeros((H, W, k), np.float32); fid = -np.ones((H, W), np.int64)
    best = np.full((H, W), -np.inf, np.float32)
    for i in range(len(T)):
        t = T[i]; x0, y0 = np.floor(t.min(0)).astype(int); x1, y1 = np.ceil(t.max(0)).astype(int)
        x0, y0 = max(x0, 0), max(y0, 0); x1, y1 = min(x1, W - 1), min(y1, H - 1)
        if x1 < x0 or y1 < y0: continue
        gx, gy = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        (ax, ay), (bx, by), (cx, cy) = t; d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12: continue
        l0 = ((by - cy) * (gx - cx) + (cx - bx) * (gy - cy)) / d; l1 = ((cy - ay) * (gx - cx) + (ax - cx) * (gy - cy)) / d; l2 = 1 - l0 - l1
        m = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
        if not m.any(): continue
        val = l0[..., None] * attr[i, 0] + l1[..., None] * attr[i, 1] + l2[..., None] * attr[i, 2]
        ys, xs = np.nonzero(m); ys += y0; xs += x0; v = val[m]
        if zbuf is None:
            out[ys, xs] = v; fid[ys, xs] = i
        else:
            closer = v[:, 0] > best[ys, xs]
            ys, xs, v = ys[closer], xs[closer], v[closer]; best[ys, xs] = v[:, 0]; out[ys, xs] = v; fid[ys, xs] = i
    return out.reshape(-1, k), fid.reshape(-1)


def fit_view(P, R, U, Fw, alpha, it=12):
    """similarity (s, tx, ty) taking (p.R, p.U) to relief-frame pixels so the mesh silhouette best matches alpha"""
    x = P[..., :] @ R; y = P @ U
    from PIL import ImageDraw
    def sil(s, tx, ty, W=256):
        T = np.stack([x * s + tx, F - (y * s + ty)], -1) * (W / F)
        im = Image.new('L', (W, W), 0); d = ImageDraw.Draw(im)
        for t in T: d.polygon([tuple(q) for q in t], fill=255)
        return np.asarray(im) > 127
    A = np.asarray(Image.fromarray(alpha.astype(np.uint8) * 255).resize((256, 256), Image.BILINEAR)) > 127
    ys, xs = np.nonzero(alpha); bx = (xs.min(), xs.max()); by = (F - 1 - ys.max(), F - 1 - ys.min())   # alpha box, y up
    s = ((bx[1] - bx[0]) / (x.max() - x.min()) + (by[1] - by[0]) / (y.max() - y.min())) / 2
    tx = bx[0] - x.min() * s; ty = by[0] - y.min() * s
    iou = lambda m: (m & A).sum() / max((m | A).sum(), 1)
    best = (iou(sil(s, tx, ty)), s, tx, ty)
    for step in (0.02, 0.01, 0.005):
        for _ in range(it):
            improved = False
            for ds, dx, dy in ((1 + step, 0, 0), (1 - step, 0, 0), (1, step * F, 0), (1, -step * F, 0), (1, 0, step * F), (1, 0, -step * F)):
                c = (best[1] * ds, best[2] + dx + (1 - ds) * (F / 2), best[3] + dy + (1 - ds) * (F / 2))
                v = iou(sil(*c))
                if v > best[0] + 1e-5: best = (v,) + c; improved = True
            if not improved: break
    return best


def dog(a, s1=2.0, s2=10.0): return gaussian_filter(a, s1) - gaussian_filter(a, s2)


def ncorr(A, B, m):
    a = A[m] - A[m].mean(); b = B[m] - B[m].mean(); return float((a * b).sum() / (np.sqrt((a * a).sum() * (b * b).sum()) + 1e-12))


def align_dense(rel, zb, mask):
    """warp the relief onto the mesh view by smoothed, capped DIS optical flow between their DoG details"""
    import cv2
    zf = np.where(mask, zb, 0.0); zf = gaussian_filter(zf, 1.0) / np.maximum(gaussian_filter(mask.astype(float), 1.0), 1e-6)
    A, B = dog(rel), dog(zf)
    to8 = lambda X: np.clip((X - np.median(X[mask])) / (4 * np.std(X[mask]) + 1e-12) * 127 + 128, 0, 255).astype(np.uint8)
    dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    fl = dis.calc(to8(B), to8(A), None).astype(np.float64)               # B(x) ~ A(x + fl(x))
    wm = gaussian_filter(mask.astype(float), FLOW_SMOOTH)
    for k in (0, 1): fl[..., k] = gaussian_filter(fl[..., k] * mask, FLOW_SMOOTH) / np.maximum(wm, 1e-6)
    mag = np.hypot(fl[..., 0], fl[..., 1]); fl *= np.minimum(1, FLOW_MAX / np.maximum(mag, 1e-9))[..., None]
    yy, xx = np.mgrid[0:F, 0:F].astype(float)
    W = map_coordinates(rel, [yy + fl[..., 1], xx + fl[..., 0]], order=1, mode='nearest')
    c0, c1 = ncorr(A, B, mask), ncorr(dog(W), B, mask)
    keep = c1 > c0
    return (W if keep else rel), c0, c1, float(np.percentile(np.hypot(fl[..., 0], fl[..., 1])[mask], 95)), (fl if keep else np.zeros_like(fl))


def main(npz, views_dir, v3_dir, out, res=2048, strength=STRENGTH_M, preblur=PREBLUR, fine_dir='', fine_w=FINE_W):
    res = int(res); strength = float(strength); preblur = float(preblur); fine_w = float(fine_w); os.makedirs(out, exist_ok=True); t0 = time.time()
    M = np.load(npz); P = M['P'].astype(np.float64); UV = M['UV'].astype(np.float64)
    N = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0]); N /= np.linalg.norm(N, axis=1, keepdims=True) + 1e-12
    Tuv = np.stack([UV[..., 0] * res, (1 - UV[..., 1]) * res], -1)
    tex, tfid = raster(Tuv, P.astype(np.float32), res, res); cov = tfid >= 0
    tn = np.zeros((res * res, 3), np.float32); tn[cov] = N[tfid[cov]]
    print('uv raster', round(time.time() - t0, 1), 's, covered', round(cov.mean(), 4))
    acc = np.zeros(res * res, np.float64); wsum = np.zeros(res * res, np.float64); report = {}
    cacc = np.zeros((res * res, 3), np.float32); facc = np.zeros(res * res, np.float32)
    for view, (R, U, D) in VIEWS.items():
        R, U, D = (np.array(v, float) for v in (R, U, D))
        rel = np.asarray(Image.open(os.path.join(views_dir, f'{view}.relief.png')).convert('RGB'))[..., 0].astype(np.float64)
        alpha = np.asarray(Image.open(os.path.join(v3_dir, f'{view}.png')).convert('RGBA').resize((F, F), Image.BILINEAR))[..., 3] > 127
        iou, s, tx, ty = fit_view(P, R, U, F, alpha)
        T = np.stack([(P @ R) * s + tx, F - ((P @ U) * s + ty)], -1); depth = (P @ D)[..., None].astype(np.float32)
        zb, zfid = raster(T, depth, F, F, zbuf=True); zcov = (zfid >= 0).reshape(F, F); zb = zb.reshape(F, F)
        both = zcov & alpha
        rel, c0, c1, f95, flow = align_dense(rel, zb, both)
        if NO_FLOW: flow = np.zeros_like(flow)
        if COLOR_FULL:
            colF = np.asarray(Image.open(os.path.join(v3_dir, f'{view}.png')).convert('RGB')).astype(np.float32) / 255; kc = colF.shape[0] / F
        else:
            col = np.asarray(Image.open(os.path.join(v3_dir, f'{view}.png')).convert('RGB').resize((F, F), Image.LANCZOS)).astype(np.float32) / 255
            yy, xx = np.mgrid[0:F, 0:F].astype(float)
            col = np.stack([map_coordinates(col[..., c], [yy + flow[..., 1], xx + flow[..., 0]], order=1, mode='nearest') for c in range(3)], -1)
        rel = gaussian_filter(rel, preblur); det = rel - gaussian_filter(rel, SIGMA)
        spread = 1.4826 * np.median(np.abs(det[both])); det = np.clip(det / spread, -CLIP, CLIP) * strength * alpha
        a = spread; lo, hi = -CLIP * strength, CLIP * strength
        # texels: project, visibility against the z-buffer, weight by facing
        px = (tex @ R) * s + tx; py = F - ((tex @ U) * s + ty); dt = tex @ D
        inb = cov & (px >= 0) & (px < F - 1) & (py >= 0) & (py < F - 1)
        zt = map_coordinates(zb, [py[inb] - 0.5, px[inb] - 0.5], order=0, mode='nearest')
        soft = np.zeros(res * res); soft[np.flatnonzero(inb)] = np.clip(1 - (zt - EPS - dt[inb]) / EPS, 0, 1)
        vis = soft > 0
        w = soft * np.abs(tn @ D) ** POWER
        hv = np.zeros(res * res); hv[vis] = map_coordinates(det, [py[vis] - 0.5, px[vis] - 0.5], order=1, mode='nearest')
        fp = os.path.join(fine_dir, f'{view}.fine.npy') if fine_dir else None
        if fp and os.path.exists(fp):
            fine = np.load(fp).astype(np.float64); kf = fine.shape[0] / F
            fy = map_coordinates(flow[..., 1], [py[vis] - 0.5, px[vis] - 0.5], order=1, mode='nearest')
            fx = map_coordinates(flow[..., 0], [py[vis] - 0.5, px[vis] - 0.5], order=1, mode='nearest')
            fs = map_coordinates(fine, [(py[vis] + fy) * kf - 0.5, (px[vis] + fx) * kf - 0.5], order=1, mode='nearest')
            fsc = np.clip(fs, -CLIP, CLIP) * map_coordinates(alpha.astype(float), [py[vis] - 0.5, px[vis] - 0.5], order=1)
            hv[vis] += fine_w * fsc * strength; facc[vis] += (w[vis] * fsc).astype(np.float32)
            report_fine = True
        else: report_fine = False
        acc += w * hv; wsum += w
        if COLOR_FULL:                                                   # the plate at full resolution, at the flow-warped position
            gy = map_coordinates(flow[..., 1], [py[vis] - 0.5, px[vis] - 0.5], order=1, mode='nearest'); gx = map_coordinates(flow[..., 0], [py[vis] - 0.5, px[vis] - 0.5], order=1, mode='nearest')
            for c in range(3): cacc[vis, c] += (w[vis] * map_coordinates(colF[..., c], [(py[vis] + gy) * kc - 0.5, (px[vis] + gx) * kc - 0.5], order=1, mode='nearest')).astype(np.float32)
        else:
            for c in range(3): cacc[vis, c] += (w[vis] * map_coordinates(col[..., c], [py[vis] - 0.5, px[vis] - 0.5], order=1, mode='nearest')).astype(np.float32)
        report[view] = {'iou': round(float(iou), 4), 'scale_px_per_m': round(float(s), 2), 'robust_spread_relief_units': float(a),
                        'detail_mm_p0.5_p99.5': [round(float(lo) * 1000, 3), round(float(hi) * 1000, 3)], 'texels_seen': int(vis.sum()), 'detail_corr_before_after_flow': [round(c0, 4), round(c1, 4)], 'flow_p95_px': round(f95, 2), 'flow_kept': c1 > c0, 'fine_band': report_fine}
        print(view, report[view], round(time.time() - t0, 1), 's')
    h = np.where(wsum > 0, acc / np.maximum(wsum, 1e-12), 0.0).reshape(res, res).astype(np.float32)
    seen = (wsum > 0).reshape(res, res)
    idx = distance_transform_edt(~seen, return_distances=False, return_indices=True)   # gutter: nearest seen texel
    h = h[idx[0], idx[1]] * (distance_transform_edt(~seen) <= 8)
    np.save(os.path.join(out, 'detail_height_m.npy'), h)
    C = np.where((wsum > 0)[:, None], cacc / np.maximum(wsum, 1e-12)[:, None], 0).reshape(res, res, 3)
    C = C[idx[0], idx[1]]; Image.fromarray((np.clip(C, 0, 1) * 255).astype(np.uint8)).save(os.path.join(out, 'v3_colour_atlas.png'))
    np.save(os.path.join(out, 'texel_face.npy'), tfid.reshape(res, res).astype(np.int32))
    if MESH_HEIGHT_IT:                                                   # the mesh's own raised detail per texel
        from scipy.sparse import coo_matrix, diags
        Vf = P.reshape(-1, 3); _, w_ = np.unique(np.round(Vf / 1e-5).astype(np.int64), axis=0, return_inverse=True); w_ = w_.ravel(); Tw = w_.reshape(-1, 3)
        nv = w_.max() + 1; Vw = np.zeros((nv, 3)); Vw[w_] = Vf
        e = np.sort(np.concatenate([Tw[:, [0, 1]], Tw[:, [1, 2]], Tw[:, [2, 0]]]), 1); u_, cnt = np.unique(e, axis=0, return_counts=True)
        border = np.zeros(nv, bool); border[u_[cnt == 1].ravel()] = True
        A = coo_matrix((np.ones(len(u_) * 2), (np.r_[u_[:, 0], u_[:, 1]], np.r_[u_[:, 1], u_[:, 0]])), shape=(nv, nv)).tocsr()
        Lp = diags(1 / np.maximum(np.asarray(A.sum(1)).ravel(), 1)) @ A; Sm = Vw.copy(); fr = ~border[:, None]
        for _ in range(MESH_HEIGHT_IT):
            for lam in (0.5, -0.53): Sm = Sm + lam * (Lp @ Sm - Sm) * fr
        fn = np.cross(Sm[Tw[:, 1]] - Sm[Tw[:, 0]], Sm[Tw[:, 2]] - Sm[Tw[:, 0]]); vn = np.zeros_like(Sm)
        for k in range(3): np.add.at(vn, Tw[:, k], fn)
        vn /= np.maximum(np.linalg.norm(vn, axis=1, keepdims=True), 1e-12)
        hv_ = ((Vw - Sm) * vn).sum(1)                                     # per welded vertex, metres
        th, _ = raster(Tuv, hv_[Tw][..., None].astype(np.float32), res, res)
        mh = np.where(cov, th[:, 0], 0).reshape(res, res).astype(np.float32); np.save(os.path.join(out, 'mesh_height_m.npy'), mh)
        report['mesh_height'] = {'taubin_iters': MESH_HEIGHT_IT, 'mm_p5_p50_p95': [round(float(np.percentile(mh[cov.reshape(res, res)], q)) * 1000, 2) for q in (5, 50, 95)]}
    np.save(os.path.join(out, 'texel_seen.npy'), seen)
    Fa = np.where(wsum > 0, facc / np.maximum(wsum, 1e-12), 0).reshape(res, res).astype(np.float32)
    np.save(os.path.join(out, 'fine_atlas.npy'), Fa)                      # the tile fine band alone (robust spreads): the raised line work
    rng = CLIP * strength * (1 + fine_w)                                    # exact 16-bit carrier for Blender: h = (v / 65535 - 0.5) * 2 * rng
    Image.fromarray(np.round((np.clip(h / (2 * rng), -0.5, 0.5) + 0.5) * 65535).astype(np.uint16)).save(os.path.join(out, 'detail_height_u16.png'))
    report['u16_png_range_m'] = rng
    vis8 = np.clip(h / max(abs(h).max(), 1e-9) * 0.5 + 0.5, 0, 1)
    Image.fromarray((vis8 * 255).astype(np.uint8)).save(os.path.join(out, 'detail_height_preview.png'))
    report.update({'color_full_res': COLOR_FULL, 'res': res, 'sigma_px': SIGMA, 'clip_spreads': CLIP, 'preblur_px': preblur, 'view_weight_power': POWER, 'flow_smooth_px': FLOW_SMOOTH, 'flow_max_px': FLOW_MAX, 'fine_dir': fine_dir, 'fine_w': fine_w, 'strength_m_per_spread': strength, 'eps_m': EPS, 'texels_covered': int(cov.sum()), 'texels_seen_by_any_view': int(seen.sum()),
                   'height_m_min_max': [float(h.min()), float(h.max())], 'seconds': round(time.time() - t0, 1)})
    json.dump(report, open(os.path.join(out, 'relief_project.json'), 'w'), indent=1); print('done', report['seconds'], 's')


if __name__ == '__main__':
    main(*sys.argv[1:])
