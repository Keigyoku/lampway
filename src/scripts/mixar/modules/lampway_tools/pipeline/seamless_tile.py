# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
# Ported from the owner's tool shelf (tools/texlib/seamless_tile.py v1.7, sha256 46f81275791b, and its falsifier suite test_seamless_gate.py) on 2026-10-06:
# one tool for three contracts (specs/generation/image_tile.md, specs/shelf/seamless_tile.md, specs/wiki/seamless_tile.md). The shelf's header, with the
# measured rules behind the code:
# SPIKE (2026-10-03): make a generated material sheet into a seamless tile, deterministically, and gate it.
# Generated "tileable" sheets are not seamless (measured: wrap-edge error 20.5 vs interior 5.9), and asking the image
# model to repaint the seam cross changes tone and motif density. So tiles are made by rules, never by the model:
#   motif : the sheet has a true repeat (fundamental autocorrelation peak, prominence >= MOTIF_PROM). Generated
#           lattices are not perfectly even, so the crop is SEARCHED: per axis, the (offset, span) near a whole number
#           of periods where the sheet repeats best (min mean |g(x0) - g(x0 + span)|), then resampled to the tile size.
#           No blend unless that fails the gate; then a phase-aligned separable blend is tried.
#   grain : no true repeat (leather, grime). Separable variance-preserving cross-fade, narrowest passing band.
#   fibre : directional fibres (horsehair): as grain, named so the record says what it is.
# Blend: periodic sheets use a separable min-cut QUILT (no averaging, no ghosts; 1.6); grain/fibre use the cross-fade.
# Gate: see GATE_TEXT; every check is measured on the final tile before 8-bit rounding.
# Lampway additions (1.8): mode motif_cell (one motif cell resampled to cell_px and tiled exactly: periodic by construction, free and reproducible), the
# TONE SEAM check the image_tile contract names (the mean luminance of the 8 px bands either side of the wrap, as % of the mean; the half-tile band pair
# is reported beside it as the reference): the seam/step ratio passed two bake-off tiles a person saw tone seams in (FLUX 3, Ming: ratio 1.0). The
# threshold is DERIVED from the four bake-off tiles the contract names (max over the axes: Flare 2.05, Gemini 3.26 accepted; FLUX 8.59, Ming 9.37
# rejected; measured 2026-10-06) and stays [UNVERIFIED] beyond them. build() never overwrites, refuses a sheet under twice the tile size, and returns
# the verdict instead of an exit code (passed=false is a gate verdict, not a tool error).
import hashlib
import json
import os
import platform

import numpy as np
import PIL
from PIL import Image

VERSION = 'seamless_tile 1.8 (lampway port of 1.7)'
MOTIF_PROM = 0.12      # autocorrelation peak prominence marking a true repeat (calibrated: periodic 0.23-0.73, other <= 0.032)
RATIO_MAX = 1.35       # wrap-edge diff / interior neighbour diff
LINE_Z = 6.0           # robust z of the wrap line's diff vs every interior line, per channel
CHUNK_Z = 7.0          # robust z of each 128 px chunk of the wrap vs that chunk on interior lines (partial seams)
STEP_Z = 8.0           # robust z of the signed 16/64/128 px window step across the wrap vs elsewhere, per channel
TONE_REL_MAX = 1.25    # wrap strip step / largest interior 32 px strip step
SHARP_MIN = 0.85       # band and edge-strip fine detail vs core
TONE_MAX = 3.0         # band tone shift, % of mean luminance
LOWFREQ_MAX = 18.0     # low-frequency luminance range (sigma side/32), % of mean
SELF_CORR_MAX = 0.35   # non-periodic tile: correlation with its own half-tile shift
STRUCT_MAX = 6.0       # robust z (per 128 px chunk) of the wrap's blurred adjacent-line correlation drop vs the interior
STRUCT_MEAN_MAX = 1.9  # mean of those chunk z along the wrap (calibrated: good <= 1.35, shifted rows >= 2.21)
TONE_SEAM_MAX = 5.0    # 8 px bands either side of the wrap, |mean luminance difference| % of mean (lampway 1.8; [UNVERIFIED] beyond the bake-off)
SEAM_BAND = 8
MODES = ('motif', 'grain', 'fibre', 'motif_cell')
GATE_TEXT = (f'wrap ratio <= {RATIO_MAX}; at the wrap, per RGB and chroma (R-B, G-(R+B)/2) channel, vs the tile interior: line z <= {LINE_Z}, 128 px chunk z <= {CHUNK_Z}, '
             f'signed step z <= {STEP_Z}, blurred-structure correlation drop z <= {STRUCT_MAX} per 128 px chunk and mean z <= {STRUCT_MEAN_MAX}; wrap tone step <= {TONE_REL_MAX} x largest interior strip step; band and '
             f'edge-strip sharpness >= {SHARP_MIN} (band <= {1 / SHARP_MIN:.2f}); band tone shift <= {TONE_MAX}%; low-frequency '
             f'range <= {LOWFREQ_MAX}%; non-periodic half-tile self-correlation <= {SELF_CORR_MAX}; tone seam (8 px bands across the wrap) <= {TONE_SEAM_MAX}%; '
             f'plus human review of the full-res mosaic')


class TileRefused(ValueError):
    pass


def tone_seam(g):
    """The luminance step across the wrap: |mean of the last SEAM_BAND columns (rows) - mean of the first| as % of the tile's mean, the larger of the two
    axes; the same band pair at half the tile is the reference (a tile whose interior has a bigger step is a different defect, low-frequency or band)."""
    mu = g.mean() + 1e-6
    out = {}
    for name, G in (('x', g), ('y', g.T)):
        n = G.shape[1]; b = SEAM_BAND
        out[name] = (abs(G[:, -b:].mean() - G[:, :b].mean()) / mu * 100, abs(G[:, n // 2 - b:n // 2].mean() - G[:, n // 2:n // 2 + b].mean()) / mu * 100)
    return {'tone_seam_pct': round(float(max(out['x'][0], out['y'][0])), 3), 'tone_seam_half_tile_pct': round(float(max(out['x'][1], out['y'][1])), 3)}


def sha(p):
    return hashlib.sha256(open(p, 'rb').read()).hexdigest()


def lum(a):
    return a.astype(np.float64).mean(2)


def autocorr(a, axis):
    g = lum(a); g = g - g.mean()
    p = np.abs(np.fft.ifft(np.abs(np.fft.fft(g, axis=axis)) ** 2, axis=axis)).mean(axis=1 - axis)
    return p / p[0]


def true_period(a, axis, lo=6):
    """FUNDAMENTAL repeat: the smallest-lag autocorrelation peak whose prominence (peak minus the lowest value before
    it) is >= 0.8 x the most prominent one (critique-2 N3: picking the most prominent peak returned 2x or 4x the period).
    Returns (sub-pixel period, prominence) or (None, 0.0)."""
    h = autocorr(a, axis)[:a.shape[axis] // 2]
    peaks = [k for k in range(lo, len(h) - 1) if h[k] > h[k - 1] and h[k] >= h[k + 1]]
    if not peaks: return None, 0.0
    prom = {k: h[k] - h[:k].min() for k in peaks}; best = max(prom.values())
    k = min(p for p in peaks if prom[p] >= 0.8 * best)
    y0, y1, y2 = h[k - 1], h[k], h[k + 1]; den = y0 - 2 * y1 + y2
    pf = k + (0.5 * (y0 - y2) / den if den != 0 else 0.0)
    return round(float(pf), 3), round(float(prom[k]), 3)


def search_span(g, axis, period, s):
    """(offset, span) with span within +-3 px of the largest whole number of periods that fits, minimising the mean
    |line(x0) - line(x0 + span)| - where the sheet itself repeats best."""
    G = g if axis == 1 else g.T
    k = int((s - 1) // period); best = None
    for span in range(int(round(k * period)) - 3, int(round(k * period)) + 4):
        if span >= s or span < 8: continue
        for x0 in range(0, s - span, 1):
            e = float(np.abs(G[:, x0] - G[:, x0 + span]).mean())
            if best is None or e < best[0]: best = (e, x0, span)
    return best[1], best[2], k, round(best[0], 3)


def _min_cut(err):
    """Vertical minimum-error path through err (rows x cols) by dynamic programming; returns the column per row."""
    h, w = err.shape; cost = err.copy(); back = np.zeros((h, w), np.int64)
    for i in range(1, h):
        prev = np.stack([np.r_[np.inf, cost[i - 1, :-1]], cost[i - 1], np.r_[cost[i - 1, 1:], np.inf]])
        k = prev.argmin(0); back[i] = k - 1; cost[i] += prev[k, np.arange(w)]
    path = np.zeros(h, np.int64); path[-1] = int(cost[-1].argmin())
    for i in range(h - 1, 0, -1): path[i - 1] = path[i] + back[i, path[i]]
    return np.clip(path, 0, w - 1)


def crossfade_blend(a, band):
    """Separable variance-preserving cross-fade with a half-tile roll (v1.5; judged READY on the grain/fibre tiles in
    critique round 3). Grain textures need the mixing: a quilt copies content outright and lifted the half-tile
    self-correlation to 0.37-0.57 (measured 2026-10-03), so grain/fibre keep this blend."""
    n, m = a.shape[:2]
    def ramp(L):
        d = np.abs(np.linspace(-1, 1, L)); t = np.clip((d - (1 - 2 * band)) / (2 * band), 0, 1)
        return t * t * (3 - 2 * t)
    def vp(x, y, w):
        mu = 0.5 * (x.mean((0, 1)) + y.mean((0, 1)))
        return (w * x + (1 - w) * y - mu) / np.sqrt(w ** 2 + (1 - w) ** 2) + mu
    a = vp(np.roll(a, m // 2, 1), a, ramp(m)[None, :, None])
    a = vp(np.roll(a, n // 2, 0), a, ramp(n)[:, None, None])
    return a, [m // 2, n // 2]


def separable_blend(a, band, period=None):
    """Separable QUILT blend (1.6, critique-3 M1/N2): per axis, a copy rolled by about half the tile (phase-aligned for
    periodic sheets) replaces the content near the wrap; inside each overlap zone the switch follows the minimum-error
    path between the two copies with a 2 px feather - nothing is averaged, so nothing ghosts and weave phases meet
    where they already agree. The rolled copy's own seam lies in the centre, where the original is kept."""
    n, m = a.shape[:2]; shifts = []
    for axis, L in ((1, m), (0, n)):
        A = a if axis == 1 else a.transpose(1, 0, 2)
        sh = L // 2
        if period:
            pp = period[0] if axis == 1 else period[1]
            zone = max(4, int(band * L)); mask = np.zeros(L); mask[:zone] = 1; mask[-zone:] = 1
            cands = range(L // 2 - int(np.ceil(pp)), L // 2 + int(np.ceil(pp)) + 1)
            sh = min(cands, key=lambda c: float((np.abs(np.roll(A, c, 1) - A).sum(2) * mask[None, :]).sum()))
        R = np.roll(A, sh, 1); out = A.copy(); rows = A.shape[0]
        zone = max(4, int(band * L)); inner = int(band * L * 2)       # overlap zone [zone, inner) on each side
        err = np.abs(R - A).sum(2)
        wmap = np.zeros((rows, L))
        # left side: columns [0, zone) take the rolled copy; switch to the original along the cut in [zone, inner)
        cut = _min_cut(err[:, zone:inner]) + zone
        cols = np.arange(L)[None, :]
        wl = np.clip((cut[:, None] - cols + 1.5) / 3.0, 0, 1) * (cols < inner)
        # right side, mirrored
        cutr = _min_cut(err[:, L - inner:L - zone][:, ::-1]); cutr = L - zone - 1 - cutr
        wr = np.clip((cols - cutr[:, None] + 1.5) / 3.0, 0, 1) * (cols >= L - inner)
        wmap = np.maximum(wl, wr)
        out = wmap[..., None] * R + (1 - wmap[..., None]) * A
        a = out if axis == 1 else out.transpose(1, 0, 2); shifts.append(int(sh))
    return a, shifts


def metrics(t, band, periodic):
    t = t.astype(np.float64); g = lum(t); n, m = g.shape; mu = g.mean() + 1e-6
    wx, wy = np.abs(g[:, 0] - g[:, -1]).mean(), np.abs(g[0] - g[-1]).mean()
    ix, iy = np.abs(np.diff(g, axis=1)).mean(), np.abs(np.diff(g, axis=0)).mean()
    def robust_max(d):
        med = np.median(d); mad = np.median(np.abs(d - med)) * 1.4826 + 1e-6
        return float(np.abs((d - med) / mad).max())
    # Seam checks look AT THE WRAP, scored against the tile's own interior lines (1.1: scoring every line made a
    # perfect lattice's own grid lines outliers - a false reject - while diluting partial seams). Per channel.
    line_z = chunk_z = step_z = struct = struct_mean = 0.0
    # R, G, B plus two chroma channels: fibres vary in brightness far more than in hue, so a hue step hidden in the
    # RGB channels of horsehair shows in R-B (1.4, 2026-10-03)
    chans = [t[..., 0], t[..., 1], t[..., 2], t[..., 0] - t[..., 2], t[..., 1] - 0.5 * (t[..., 0] + t[..., 2])]
    for C in chans:
        for axis in (1, 0):
            A = C if axis == 1 else C.T                       # columns are lines across the x-wrap
            W = np.concatenate([A, A[:, :1]], axis=1)         # append the wrapped first column
            D = np.abs(np.diff(W, axis=1))                    # D[:, j] = |line j+1 - line j|; j = last is the wrap
            per_line = D.mean(0); wrap = per_line[-1]; inner = per_line[:-1]
            med = np.median(inner); mad = np.median(np.abs(inner - med)) * 1.4826 + 1e-6
            line_z = max(line_z, float((wrap - med) / mad))
            ch = D[:D.shape[0] // 128 * 128].reshape(-1, 128, D.shape[1]).mean(1)   # chunks x lines
            for r_ in range(ch.shape[0]):                     # each chunk of the wrap vs that chunk on every interior line
                row = ch[r_, :-1]; med = np.median(row); mad = np.median(np.abs(row - med)) * 1.4826 + 1e-6
                chunk_z = max(chunk_z, float((ch[r_, -1] - med) / mad))
            cm = np.concatenate([A, A, A], axis=1).mean(0); cs = np.concatenate([[0], np.cumsum(cm)]); L = A.shape[1]
            for w in (16, 64, 128):
                k = np.arange(w, len(cm) - w); d = (cs[k + w] - cs[k]) / w - (cs[k] - cs[k - w]) / w
                at = np.abs(d[(k == L) | (k == 2 * L)]).max(); others = d[(k != L) & (k != 2 * L)]
                med = np.median(others); mad = np.median(np.abs(others - med)) * 1.4826 + 1e-6
                step_z = max(step_z, float((at - abs(med)) / mad))
            # structure continuity: correlation of blurred adjacent lines across the wrap vs interior adjacent lines
            Bk = np.cumsum(np.concatenate([np.zeros((1, W.shape[1])), W[-2:], W, W[:2]], axis=0), axis=0); Bl = (Bk[5:] - Bk[:-5]) / 5   # 5-tap box, n rows
            Bl = Bl - Bl.mean(0)
            zs = []
            for r0 in range(0, Bl.shape[0] - 64, 128):           # per 128 px chunk (the last may be short): a partial break is not diluted
                Bc = Bl[r0:min(r0 + 128, Bl.shape[0])]; Bc = Bc - Bc.mean(0)
                cor = (Bc[:, :-1] * Bc[:, 1:]).sum(0) / (np.sqrt((Bc[:, :-1] ** 2).sum(0) * (Bc[:, 1:] ** 2).sum(0)) + 1e-9)
                inner = cor[:-1]; med = np.median(inner); mad = np.median(np.abs(inner - med)) * 1.4826 + 1e-6
                zs.append(float((med - cor[-1]) / mad)); struct = max(struct, zs[-1])   # robust z of the wrap's drop in this chunk
            struct_mean = max(struct_mean, float(np.mean(zs)))       # a break along the whole wrap lifts every chunk a little
    s = 32
    def tone(G):
        strips = G.reshape(G.shape[0], -1, s).mean(axis=(0, 2)); inner = np.abs(np.diff(strips))
        return abs(strips[-1] - strips[0]) / max(inner.max(), 1e-6)
    tone_all = max(max(tone(C), tone(C.T)) for C in chans)   # per channel incl. chroma: hue steps too
    lap = np.abs(4 * g[1:-1, 1:-1] - g[:-2, 1:-1] - g[2:, 1:-1] - g[1:-1, :-2] - g[1:-1, 2:])
    yy = np.abs(np.linspace(-1, 1, n - 2))[:, None]; xx = np.abs(np.linspace(-1, 1, m - 2))[None, :]
    d = np.maximum(xx, yy); edge = (d > 1 - 2 * band) & (d < 1 - 0.5 * band); core = d < 0.5
    gy = np.abs(np.linspace(-1, 1, n))[:, None]; gx = np.abs(np.linspace(-1, 1, m))[None, :]; gd = np.maximum(gx, gy)
    core_e = lap[core].mean()
    edge_min = min(lap[:, :30].mean(), lap[:, -30:].mean(), lap[:30].mean(), lap[-30:].mean()) / max(core_e, 1e-6)
    # blend-zone sharpness PER SIDE over the zone the blend actually touched (critique-3 M4: a blurred band on one side
    # was diluted by pooling all four sides): min over the four sides of [band/2, 3 x band] of the side
    lo, hi = max(1, int(0.5 * band * n)), max(2, int(3 * band * n))
    band_min = min(lap[:, lo:hi].mean(), lap[:, -hi:-lo].mean(), lap[lo:hi].mean(), lap[-hi:-lo].mean()) / max(core_e, 1e-6)
    sg = min(n, m) / 32; fy = np.fft.fftfreq(n)[:, None]; fx = np.fft.fftfreq(m)[None, :]
    low = np.real(np.fft.ifft2(np.fft.fft2(g) * np.exp(-2 * np.pi ** 2 * sg ** 2 * (fx ** 2 + fy ** 2))))
    gz = g - g.mean(); den = (gz * gz).sum() + 1e-9
    self_corr = max(float((gz * np.roll(gz, n // 2, 0)).sum() / den), float((gz * np.roll(gz, m // 2, 1)).sum() / den))
    r = lambda v: round(float(v), 3)
    return {'ratio_x': r(wx / max(ix, 1e-6)), 'ratio_y': r(wy / max(iy, 1e-6)), 'wrap_line_z': r(line_z), 'wrap_chunk_z': r(chunk_z),
            'wrap_step_z': r(step_z), 'wrap_structure_drop': r(struct), 'wrap_structure_mean_z': r(struct_mean), 'wrap_tone_step_over_max_interior': r(tone_all),
            'band_sharpness_over_core': r(band_min), 'edge_strip_sharpness_min': r(edge_min),
            'band_tone_shift_pct': r(abs(g[(gd > 1 - 2 * band) & (gd < 1 - 0.5 * band)].mean() - g[gd < 0.5].mean()) / mu * 100),
            'lowfreq_range_pct': r((np.percentile(low, 99) - np.percentile(low, 1)) / mu * 100),
            'half_shift_self_corr': r(self_corr), 'periodic': bool(periodic), **tone_seam(g)}


def gate(mt):
    f = []
    if mt['ratio_x'] > RATIO_MAX or mt['ratio_y'] > RATIO_MAX: f.append('wrap ratio')
    if mt['wrap_line_z'] > LINE_Z: f.append('hard line at the wrap')
    if mt['wrap_chunk_z'] > CHUNK_Z: f.append('partial seam / patch at the wrap')
    if mt['wrap_step_z'] > STEP_Z: f.append('tone or hue step across the wrap')
    if mt['wrap_structure_drop'] > STRUCT_MAX: f.append('structure breaks across part of the wrap')
    if mt['wrap_structure_mean_z'] > STRUCT_MEAN_MAX: f.append('structure breaks along the whole wrap')
    if mt['wrap_tone_step_over_max_interior'] > TONE_REL_MAX: f.append('tone step across wrap')
    if not (SHARP_MIN <= mt['band_sharpness_over_core'] <= 1 / SHARP_MIN): f.append('band sharpness (per side)')
    if mt['edge_strip_sharpness_min'] < SHARP_MIN: f.append('soft edge strip')
    if mt['band_tone_shift_pct'] > TONE_MAX: f.append('band tone shift')
    if mt['lowfreq_range_pct'] > LOWFREQ_MAX: f.append('low-frequency tone variation (step or blotch)')
    if not mt['periodic'] and mt['half_shift_self_corr'] > SELF_CORR_MAX: f.append('repeats at half the tile (blend band too wide)')
    if mt.get('tone_seam_pct', 0.0) > TONE_SEAM_MAX: f.append('tone seam at the wrap')
    return f


def flatten(a, sigma_frac=1 / 6):
    """Remove very-low-frequency variation PER CHANNEL (blotches, painted light, hue drift): divide each channel by a
    wide periodic Gaussian of itself and restore that channel's mean. Per channel since 1.1: a luminance-only flatten
    left a green/blue hue step in the horsehair blend band (step z 11.6 at rows 999-1008, 2026-10-03)."""
    n, m = a.shape[:2]; sg = sigma_frac * min(n, m)
    fy = np.fft.fftfreq(n)[:, None]; fx = np.fft.fftfreq(m)[None, :]
    G = np.exp(-2 * np.pi ** 2 * sg ** 2 * (fx ** 2 + fy ** 2)); out = np.empty_like(a, dtype=np.float64)
    for c in range(a.shape[2]):
        ch = a[..., c].astype(np.float64); low = np.real(np.fft.ifft2(np.fft.fft2(ch) * G))
        out[..., c] = ch * (ch.mean() / np.maximum(low, 1e-3))
    return out


def to_tile(img, size):
    return np.asarray(Image.fromarray(np.clip(np.round(img), 0, 255).astype(np.uint8)).resize((size, size), Image.LANCZOS)).astype(np.float64)




def motif_cell_tile(cell, cell_px, size):
    """One motif cell resampled to cell_px and repeated to the tile: exact by construction (size must be a whole number of cells)."""
    if size % cell_px:
        raise TileRefused(f'size {size} is not a whole number of {cell_px} px cells: choose cell_px dividing the size')
    c = np.asarray(Image.fromarray(np.clip(np.round(cell), 0, 255).astype(np.uint8)).resize((cell_px, cell_px), Image.LANCZOS)).astype(np.float64)
    k = size // cell_px
    return np.tile(c, (k, k, 1))


def _check_lattice(n=1024, kx=9, ky=8):
    y, x = np.mgrid[0:n, 0:n].astype(float)
    px, py = n / kx, n / ky
    dx = (x % px) - px / 2; dy = (y % py) - py / 2
    bead = np.exp(-(dx ** 2 + dy ** 2) / (2 * 6.0 ** 2))
    lines = np.exp(-(((x / px + y / py) % 1) - 0.5) ** 2 / 0.0008) + np.exp(-(((x / px - y / py) % 1) - 0.5) ** 2 / 0.0008)
    base = np.stack([120 + 60 * bead - 25 * np.clip(lines, 0, 1), 12 + 20 * bead, 16 + 18 * bead], -1)
    rng = np.random.default_rng(0); base += rng.normal(0, 2.0, base.shape)
    return np.clip(base, 0, 255)


def is_periodic(img):
    (px, sx), (py, sy) = true_period(img, 1), true_period(img, 0)
    return bool((px and sx >= MOTIF_PROM) or (py and sy >= MOTIF_PROM))


def falsifier_cases(t, raw):
    """The shelf's test_seamless_gate.py cases on a built tile ``t`` and its raw sheet: every defect is visibly NOT seamless and must fail; the two
    controls must pass. Lampway adds 'tone seam across the wrap' (an 8 % luminance ramp across x)."""
    n = t.shape[0]; P = is_periodic(t)
    step = t.copy(); step[:, n // 2:] *= 1.25
    inner = np.roll(t, n // 3, 1).copy(); inner[:, :n // 3] = raw[:, :n // 3]
    blur = t.copy(); blur[:, :64] = np.asarray(Image.fromarray(t[:, :64].astype(np.uint8)).resize((16, n)).resize((64, n))).astype(float)
    hue = t.copy(); hue[:, n // 2:, 0] += 12; hue[:, n // 2:, 2] -= 12
    part = t.copy(); r0, r1 = n // 4, n // 4 + int(0.4 * n); part[r0:r1, -60:] = raw[r0:r1, -60:]
    patch = t.copy(); a0 = min(200, n // 4); patch[a0:a0 + n // 3, n - 150:] = raw[a0:a0 + n // 3, n - 150:]
    shift = t.copy(); shift[-40:] = np.roll(t[-40:], 37, 1)
    z = int(0.06 * n)
    bandblur = t.copy(); bb = bandblur[:, z:3 * z]; bandblur[:, z:3 * z] = np.asarray(Image.fromarray(np.clip(bb, 0, 255).astype(np.uint8)).resize((max(1, bb.shape[1] // 4), n)).resize((bb.shape[1], n))).astype(float)
    bandtone = t.copy(); bandtone[:, :3 * z] *= 1.08; bandtone[:, -3 * z:] *= 1.08; bandtone[:3 * z] *= 1.08; bandtone[-3 * z:] *= 1.08
    yy = np.arange(n)[:, None]; stripe = t * (1 + 0.25 * (np.abs(((yy / n * 3) % 1) - 0.5) < 0.12))[..., None]
    ramp = t * np.linspace(0.92, 1.0, n)[None, :, None]
    cases = {'control: the tile (must PASS)': (t, P), 'control: perfect 9x8 bead lattice (must PASS)': (_check_lattice(n), True),
             'raw sheet resized': (raw, is_periodic(raw)), '25% tone step': (step, P), 'hard internal seam': (inner, P),
             'blurred edge strip': (blur, P), 'hue step at constant luminance': (hue, P), 'partial seam on 40% of the wrap': (part, P),
             'hard patch touching the wrap': (patch, P), 'last 40 rows shifted 37 px': (shift, P),
             'blurred blend band': (bandblur, P), 'band tone shift +8 %': (bandtone, P), '25 % low-frequency stripes': (stripe, P),
             'tone seam across the wrap': (ramp, P)}
    if not P:
        selfcopy = t.copy(); selfcopy[:, n // 2:] = t[:, :n // 2]
        cases['half-tile self-copy (non-periodic)'] = (selfcopy, P)
    return cases


def build(src, out, mode, size=1024, flatten_=False, cell_px=None):
    """src sheet -> <out>.png, <out>_mosaic.png, <out>.qa.json; returns {passed, failures, metrics, params, files}. Refused (TileRefused): an unknown mode,
    an existing output, a sheet under twice the tile size (motif_cell excepted), motif on a sheet without a true repeat, grain/fibre on a periodic sheet."""
    if mode not in MODES:
        raise TileRefused(f'mode is one of {", ".join(MODES)}')
    size = int(size)
    if not 256 <= size <= 4096:
        raise TileRefused('size is 256..4096')
    out = os.path.splitext(out)[0]
    png, mos, qaf = out + '.png', out + '_mosaic.png', out + '.qa.json'
    for f in (png, mos, qaf):
        if os.path.exists(f):
            raise TileRefused(f'{os.path.basename(f)} exists: outputs are never overwritten; choose a new out')
    img = np.asarray(Image.open(src).convert('RGB')).astype(np.float64)
    h, w = img.shape[:2]; s = min(h, w)
    params = {'mode': mode, 'size': size, 'resample': 'PIL LANCZOS', 'blend': None}
    if mode == 'motif_cell':
        cp = int(cell_px or 0)
        if not 16 <= cp <= size:
            raise TileRefused('motif_cell needs cell_px 16..size: the cell is resampled to it and repeated exactly')
        tile = motif_cell_tile(img[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s], cp, size)
        params.update({'cell_px': cp, 'cells': size // cp})
        band, mt = 0.10, metrics(tile, 0.10, True); fails = gate(mt); tried = [('none (exact repeat)', fails)]
    else:
        if s < 2 * size:
            raise TileRefused(f'the sheet is {s} px: a {size} px tile needs a sheet of at least {2 * size} px (crop room for the repeat search and the blend)')
        img = img[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]
        (px, sx), (py, sy) = true_period(img, 1), true_period(img, 0)
        periodic = bool((px and sx >= MOTIF_PROM) or (py and sy >= MOTIF_PROM))
        params.update({'period_px': [px if periodic else None, py if periodic else None], 'period_prominence': [sx, sy]})
        if mode == 'motif' and not (px and py and min(sx, sy) >= MOTIF_PROM):
            raise TileRefused(f'no true repeat found (prominence {sx}, {sy} < {MOTIF_PROM}): use mode grain or fibre')
        if mode in ('grain', 'fibre') and periodic:
            raise TileRefused(f'the sheet has a true period ({px}@{sx}, {py}@{sy}); blending ghosts motifs: use mode motif')
        if flatten_:
            img = flatten(img); params['flatten'] = 'per channel: channel / periodic Gaussian(sigma = side/6), channel mean kept'
        g = lum(img)
        if mode == 'motif':
            x0, cw, kx, ex = search_span(g, 1, px, s); y0, chh, ky, ey = search_span(g, 0, py, s)
            img = img[y0:y0 + chh, x0:x0 + cw]
            params.update({'crop_xywh': [x0, y0, cw, chh], 'periods_in_span': [kx, ky], 'span_repeat_error': [ex, ey]})
        chh, cw = img.shape[:2]
        params['scale_xy'] = [round(size / cw, 5), round(size / chh, 5)]
        base = to_tile(img, size); tried = []
        if mode == 'motif':
            tile, band = base, 0.25; mt = metrics(tile, band, True); fails = gate(mt); tried.append(('none', fails))
            if fails:
                per = (px * size / cw, py * size / chh)
                for b in (0.06, 0.10, 0.15, 0.25):
                    bl, shifts = separable_blend(base, b, per); mb = metrics(bl, b, True); fb = gate(mb); tried.append((f'aligned {b}', fb))
                    if len(fb) < len(fails): tile, mt, fails, band = bl, mb, fb, b; params['blend'] = f'separable quilt (min-cut seam), phase-aligned (shifts {shifts}), band {b}'
                    if not fb: break
        else:
            tile = mt = fails = None; band = None
            for b in (0.06, 0.10, 0.15, 0.25):
                bl, shifts = crossfade_blend(base, b); mb = metrics(bl, b, False); fb = gate(mb); tried.append((f'band {b}', fb))
                if fails is None or len(fb) < len(fails): tile, mt, fails, band = bl, mb, fb, b; params['blend'] = f'separable variance-preserving cross-fade, half-tile roll, band {b}'
                if not fb: break
    params['band'] = band; params['attempts'] = [{'blend': t_, 'failures': f_} for t_, f_ in tried]
    os.makedirs(os.path.dirname(png) or '.', exist_ok=True)
    tile8 = np.clip(np.round(tile), 0, 255).astype(np.uint8)
    Image.fromarray(tile8).save(png)
    n = size; T = Image.fromarray(tile8); P = Image.new('RGB', (3 * n, 3 * n))
    for dx in (0, n, 2 * n):
        for dy in (0, n, 2 * n): P.paste(T, (dx, dy))
    P.crop((n // 2, n // 2, n // 2 + 2 * n, n // 2 + 2 * n)).save(mos)
    qa = {'tool': VERSION, 'id': os.path.basename(out), 'role': 'seamless tile candidate (derived, deterministic)',
          'parents': [{'file': os.path.basename(src), 'sha256': sha(src)}], 'output': os.path.basename(png), 'output_sha256': sha(png),
          'params': params, 'metrics': mt, 'gate_failures': fails, 'gate_passed': not fails, 'gate': GATE_TEXT,
          'mosaic_fullres': os.path.basename(mos), 'mosaic_layout': f'2N x 2N crop of a 3x3 tiling; tile centre at the mosaic centre; wrap lines at {n // 2} and {3 * n // 2} px',
          'status': 'SEAMLESS_GATE_PASSED_CANDIDATE' if not fails else 'GATE_FAILED',
          'software': {'python': platform.python_version(), 'numpy': np.__version__, 'pillow': PIL.__version__},
          'color_space': 'sRGB base colour (declared, uncalibrated)', 'intended_physical_width_mm': None}
    with open(qaf, 'w') as fh:
        json.dump(qa, fh, indent=1)
    return {'passed': not fails, 'failures': fails, 'metrics': mt, 'params': {k: v for k, v in params.items() if k != 'attempts'}, 'attempts': params['attempts'],
            'files': {'tile': png, 'mosaic': mos, 'qa': qaf}, 'status': qa['status']}
