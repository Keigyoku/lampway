# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""palette_fit, the numeric half: fit the per-class Hue/Saturation/Value correction of the studio colours to the mesh-paint albedo, and write the params file ``pbr_merge`` reads.

Per class: the median HSV of the studio base under the class mask against the median HSV of the albedo under the same mask; ``hue_shift`` is the wrapped difference of hue,
``sat_mul = S_target / S_studio``, ``val_mul = V_target / V_studio`` (the recorded fit's arithmetic: gold 0.726/0.742 = 0.978, 0.682/0.522 = 1.306). Measured on the user's chest (2026-10-05, p17 albedo vs the pbrA studio base, all six classes): the RECORDED fit is the MEDIAN in sRGB (plate 0.818/0.677 against the recorded 0.813/0.677, gold 1.311 against 1.308, worst class difference 0.19; linear-median misses by 4.0, sRGB-mean by 0.64) and its residual after applying the palette is lower than the linear fit's (gold 0.144 against 0.190). So sRGB median is the default; ``space="linear"`` stays for a consumer that applies the palette in linear light (``pbr_merge`` notes that Blender's node does). ``residual`` is new: the
mean |dRGB| over the class's texels, in linear, after the palette is applied to the studio colour, so "it fits" has a number. The fit is advice and the nudge is law. Pure numpy + PIL.
"""

import colorsys
import json
from pathlib import Path

import numpy as np
from PIL import Image

MIN_TEXELS = 1000            # a mask smaller than this is skipped with a reason, never silently
MAX_SAMPLE = 2_000_000       # texels per class used for the residual (a stride sample; the medians use every texel)
METAL_CLASSES = ("gold", "plate")        # the user's law: no metal on cloth or leather, so every other class must be listed in metal_zero_on
DEFAULT_CLASSES = ("gold", "plate", "red", "linen", "leather", "embroidery")


class PaletteError(ValueError):
    pass


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, np.power((c + 0.055) / 1.055, 2.4))


def linear_to_srgb(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * np.power(np.maximum(c, 0), 1 / 2.4) - 0.055)


def rgb_to_hsv(rgb):
    rgb = np.asarray(rgb, dtype=np.float64)
    mx, mn = rgb.max(-1), rgb.min(-1)
    d = mx - mn
    v = mx
    s = np.where(mx > 0, d / np.maximum(mx, 1e-12), 0.0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    dd = np.maximum(d, 1e-12)
    h = np.where(mx == r, ((g - b) / dd) % 6, np.where(mx == g, (b - r) / dd + 2, (r - g) / dd + 4)) / 6.0
    h = np.where(d == 0, 0.0, h)
    return np.stack([h % 1.0, s, v], -1)


def hsv_to_rgb(hsv):
    hsv = np.asarray(hsv, dtype=np.float64)
    h, s, v = hsv[..., 0] % 1.0, np.clip(hsv[..., 1], 0, 1), hsv[..., 2]
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p, q, t = v * (1 - s), v * (1 - f * s), v * (1 - (1 - f) * s)
    choices = [(v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v), (v, p, q)]
    out = np.zeros(hsv.shape)
    for k, (r, g, b) in enumerate(choices):
        m = i == k
        out[..., 0] = np.where(m, r, out[..., 0])
        out[..., 1] = np.where(m, g, out[..., 1])
        out[..., 2] = np.where(m, b, out[..., 2])
    return out


def apply_palette(rgb_linear, params):
    """Blender's Hue/Saturation/Value node on LINEAR rgb: params = (hue 0.5 = no shift, saturation x, value x)."""
    hsv = rgb_to_hsv(rgb_linear)
    hue, sat, val = params
    hsv[..., 0] = (hsv[..., 0] + hue - 0.5) % 1.0
    hsv[..., 1] = np.clip(hsv[..., 1] * sat, 0, 1)
    hsv[..., 2] = hsv[..., 2] * val
    return hsv_to_rgb(hsv)


def _load_rgb(path):
    return np.asarray(Image.open(path).convert("RGB"), dtype=np.float64) / 255.0


def _load_mask(path, size):
    im = Image.open(path).convert("L")
    if im.size != size:
        im = im.resize(size, Image.NEAREST)
    return np.asarray(im) > 127


def fit(studio_base, albedo, masks_dir, classes=DEFAULT_CLASSES, statistic="median", space="srgb", min_texels=MIN_TEXELS):
    if statistic not in ("median", "mean"):
        raise PaletteError("statistic must be median or mean")
    if space not in ("linear", "srgb"):
        raise PaletteError("space must be linear or srgb")
    classes = list(classes)
    for c in classes:
        if not (Path(masks_dir) / f"mask_{c}.png").exists():
            raise PaletteError(f"no mask_{c}.png: run material_masks")
    notes = []
    s_img, a_img = Image.open(studio_base).convert("RGB"), Image.open(albedo).convert("RGB")
    if s_img.size != a_img.size:
        size = max(s_img.size, a_img.size, key=lambda sz: sz[0] * sz[1])
        notes.append(f"studio_base {s_img.size} and albedo {a_img.size} differ in size: both resampled to {size}")
        s_img, a_img = s_img.resize(size, Image.BILINEAR), a_img.resize(size, Image.BILINEAR)
    studio, alb = np.asarray(s_img, dtype=np.float64) / 255.0, np.asarray(a_img, dtype=np.float64) / 255.0
    size = s_img.size
    stat = np.median if statistic == "median" else np.mean
    palette, residual, skipped = {}, {}, {}
    s_lin, a_lin = srgb_to_linear(studio), srgb_to_linear(alb)
    for c in classes:
        m = _load_mask(Path(masks_dir) / f"mask_{c}.png", size)
        n = int(m.sum())
        if n < min_texels:
            skipped[c] = f"{n} texels < {min_texels}: too few to fit"
            continue
        s_meas, a_meas = (s_lin[m], a_lin[m]) if space == "linear" else (studio[m], alb[m])
        s_hsv, a_hsv = rgb_to_hsv(stat(s_meas, axis=0)), rgb_to_hsv(stat(a_meas, axis=0))
        dh = (a_hsv[0] - s_hsv[0] + 0.5) % 1.0 - 0.5
        sat = a_hsv[1] / s_hsv[1] if s_hsv[1] > 1e-9 else 1.0
        val = a_hsv[2] / s_hsv[2] if s_hsv[2] > 1e-9 else 1.0
        palette[c] = {"tripo_hsv": [round(float(x), 4) for x in s_hsv], "target_hsv": [round(float(x), 4) for x in a_hsv], "hue_shift": round(float(dh), 4),
                      "sat_mul": round(float(sat), 4), "val_mul": round(float(val), 4), "texels": n}
        step = max(1, n // MAX_SAMPLE)
        ss, aa = s_lin[m][::step], a_lin[m][::step]
        residual[c] = round(float(np.abs(apply_palette(ss, (0.5 + dh, sat, val)) - aa).mean()), 6)
    return {"ok": True, "palette": palette, "residual": residual, "skipped": skipped, "notes": notes, "statistic": statistic, "space": space}


def write_params(palette, order, params_out, metal_zero_on=("red", "linen", "leather", "embroidery"), normal_strength_live=1.0):
    """The file ``pbr_merge`` consumes: {palette_hsv: {class: [hue (0.5 = none), sat_mul, val_mul]}, order, normal_strength_live, metal_zero_on}."""
    order = list(order)
    for c in order:
        if c not in METAL_CLASSES and c not in metal_zero_on:
            raise PaletteError(f"{c} is cloth: metallic must be 0 there (add it to metal_zero_on)")
    missing = [c for c in order if c not in palette]
    if missing:
        raise PaletteError(f"no palette for {missing}: fit or read_live first")
    data = {"palette_hsv": {c: [round(0.5 + float(palette[c]["hue_shift"]), 4), float(palette[c]["sat_mul"]), float(palette[c]["val_mul"])] for c in order},
            "order": order, "normal_strength_live": normal_strength_live, "metal_zero_on": list(metal_zero_on)}
    Path(params_out).parent.mkdir(parents=True, exist_ok=True)
    Path(params_out).write_text(json.dumps(data, indent=1))
    return {"ok": True, "params": str(params_out), "palette_hsv": data["palette_hsv"]}
