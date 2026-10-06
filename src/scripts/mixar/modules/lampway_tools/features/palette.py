# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""material_palette: an image to named dominant AND accent colours (alpha-aware), optional Principled materials, and a CIELAB palette distance
(specs/resources/material_palette.md). Pure numpy + Pillow; ``bpy`` only for make_materials.

notable (default): the opaque pixels (alpha above alpha_min) are sampled on a uniform grid to max_pixels; 5-bit RGB bins are the AREA candidates, scored by
presence^0.38 x (0.2 + chroma) x (0.2 + tone); saturated pixels grouped into twelve 30-degree hue families are the ACCENT candidates (a small, vivid colour
that matters though it covers little). Greedy selection takes the best score whose CIELAB distance to every colour already taken is at least 8, after the
locked colours. kmeans: seeded k-means++ in RGB with the locked colours as fixed centroids (it may merge a small accent into a neighbour). Coverage assigns
every sampled opaque pixel to its nearest palette colour in LAB, so it sums to 1. Names: a hue family and a tone prefix. The LAB conversion is the standard
D65 sRGB -> XYZ -> Lab, distances are delta E 1976.

The algorithms follow the description of Img2Mat_Pro (stevewarner, GPL-3.0-or-later) in the contract; its source is not in this tree, so this is a fresh
implementation of that description, not a port, and the contract's parity test against it was not run [UNVERIFIED]. Pantone matching is refused."""

import hashlib
import json
import math
import os

import numpy as np

PANTONE = ("Pantone matching is not supported: Img2Mat_Pro does it only from the user's own licensed Adobe Color Book .acb files and ships none (it \"does not "
           "include or redistribute proprietary Pantone libraries\"); Lampway has none either")
HUES = ("Red", "Orange", "Yellow", "Lime", "Green", "Spring", "Cyan", "Azure", "Blue", "Violet", "Magenta", "Rose")
FLOOR_LAB = 8.0
FORMATS = (".png", ".jpg", ".jpeg", ".webp", ".tga", ".bmp", ".tif", ".tiff")


class PaletteError(ValueError):
    pass


def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_lab(rgb):
    lin = srgb_to_linear(rgb)
    M = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > (6 / 29) ** 3, np.cbrt(xyz), xyz / (3 * (6 / 29) ** 2) + 4 / 29)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], axis=-1)


def _hsv(rgb):
    mx, mn = rgb.max(axis=-1), rgb.min(axis=-1)
    d = mx - mn
    s = np.where(mx > 0, d / np.maximum(mx, 1e-12), 0.0)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    h = np.where(d == 0, 0.0, np.where(mx == r, ((g - b) / np.maximum(d, 1e-12)) % 6, np.where(mx == g, (b - r) / np.maximum(d, 1e-12) + 2, (r - g) / np.maximum(d, 1e-12) + 4)))
    return h * 60.0, s, mx


def name_of(rgb) -> str:
    h, s, v = (float(a[0]) for a in _hsv(np.asarray(rgb, float)[None]))
    if s < 0.15:
        return "White" if v > 0.85 else "Black" if v < 0.15 else ("Light Grey" if v > 0.65 else "Dark Grey" if v < 0.35 else "Grey")
    base = HUES[int(((h + 15) % 360) // 30)]
    return ("Dark " if v < 0.4 else "Light " if v > 0.85 and s < 0.5 else "") + base


def _hex(rgb) -> str:
    return "#" + "".join(f"{int(round(float(x) * 255)):02x}" for x in rgb)


def _from_hex(h) -> np.ndarray:
    h = str(h).lstrip("#")
    if len(h) != 6:
        raise PaletteError(f"a locked colour is a #rrggbb hex (got {h!r})")
    return np.array([int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4)])


def _pixels(path, alpha_min, max_pixels):
    from PIL import Image
    if os.path.splitext(path)[1].lower() not in FORMATS:
        raise PaletteError(f"{os.path.basename(path)}: the formats are {', '.join(FORMATS)}")
    img = Image.open(path).convert("RGBA")
    a = np.asarray(img, dtype=np.float64) / 255.0
    h, w = a.shape[:2]
    step = max(1, int(math.ceil(math.sqrt(h * w / float(max_pixels)))))
    a = a[::step, ::step].reshape(-1, 4)
    a = a[a[:, 3] > float(alpha_min)]
    if not len(a):
        raise PaletteError(f"{os.path.basename(path)} has no pixels above alpha_min {alpha_min}: lower alpha_min")
    return a[:, :3]


def _candidates(px):
    keys = (np.round(px * 31).astype(np.int64) * np.array([1024, 32, 1])).sum(axis=1)
    uniq, inv, counts = np.unique(keys, return_inverse=True, return_counts=True)
    means = np.zeros((len(uniq), 3))
    np.add.at(means, inv, px)
    means /= counts[:, None]
    presence = counts / float(len(px))
    _h, s, v = _hsv(means)
    chroma = means.max(axis=1) - means.min(axis=1)
    tone = 1.0 - np.abs(2 * v - 1)
    out = [(float(p ** 0.38 * (0.2 + c) * (0.2 + t)), m, float(p), "area") for p, c, t, m in zip(presence, chroma, tone, means)]
    hh, ss, vv = _hsv(px)
    vivid = (ss > 0.5) & (vv > 0.2)
    fam = ((hh + 15) % 360 // 30).astype(int)
    for f in np.unique(fam[vivid]):
        sel = px[vivid & (fam == f)]
        p = len(sel) / float(len(px))
        m = sel.mean(axis=0)
        c = float(m.max() - m.min())
        out.append((float(max(p, 1e-4) ** 0.38 * (0.2 + c) * 1.5), m, float(p), "accent"))
    out.sort(key=lambda r: (-r[0], tuple(np.round(r[1], 6))))
    return out


def _notable(px, n, locked):
    chosen = [(np.asarray(c, float), "locked") for c in locked]
    for score, m, p, kind in _candidates(px):
        if len(chosen) >= n:
            break
        lab = to_lab(m)
        if all(float(np.linalg.norm(lab - to_lab(c))) >= FLOOR_LAB for c, _k in chosen):
            chosen.append((m, kind if kind == "accent" or p >= 0.1 else ("accent" if float(m.max() - m.min()) > 0.5 else "area")))
    return chosen


def _kmeans(px, n, locked, seed, iters=30):
    rng = np.random.default_rng(int(seed))
    cents = [np.asarray(c, float) for c in locked]
    while len(cents) < n:
        if not cents:
            cents.append(px[rng.integers(len(px))])
            continue
        d = np.min(np.stack([((px - c) ** 2).sum(axis=1) for c in cents]), axis=0)
        if d.sum() <= 0:
            break
        cents.append(px[rng.choice(len(px), p=d / d.sum())])
    C = np.stack(cents)
    fixed = len(locked)
    for _ in range(iters):
        lab = np.argmin(((px[:, None, :] - C[None]) ** 2).sum(axis=2), axis=1)
        for k in range(fixed, len(C)):
            if (lab == k).any():
                C[k] = px[lab == k].mean(axis=0)
    return [(C[k], "locked" if k < fixed else "area") for k in range(len(C))]


def _assign(px, cols):
    L = to_lab(px)
    P = to_lab(np.stack(cols))
    idx = np.argmin(((L[:, None, :] - P[None]) ** 2).sum(axis=2), axis=1)
    return np.bincount(idx, minlength=len(cols)) / float(len(px))


def _palette(px, n, locked, method, seed):
    lockc = [_from_hex(c["hex"]) for c in locked]
    picks = _notable(px, n, lockc) if method == "notable" else _kmeans(px, n, lockc, seed)
    cov = _assign(px, [c for c, _k in picks])
    out, seen = [], {}
    for i, ((c, kind), share) in enumerate(zip(picks, cov)):
        nm = locked[i]["name"] if kind == "locked" else name_of(c)
        if kind != "locked":
            seen[nm] = seen.get(nm, 0) + 1
            nm = nm if seen[nm] == 1 else f"{nm} {seen[nm]}"
        out.append({"name": nm, "hex": locked[i]["hex"].lower() if kind == "locked" else _hex(c), "srgb": [round(float(x), 4) for x in c],
                    "linear": [round(float(x), 4) for x in srgb_to_linear(c)], "coverage": round(float(share), 6), "kind": kind})
    total = sum(r["coverage"] for r in out)
    if out and total:
        out[0]["coverage"] = round(out[0]["coverage"] + (1.0 - total), 6)
    return out


def distance(a, b) -> dict:
    A, B = to_lab(np.array([c["srgb"] for c in a])), to_lab(np.array([c["srgb"] for c in b]))
    wa, wb = np.array([c["coverage"] for c in a]), np.array([c["coverage"] for c in b])
    D = np.linalg.norm(A[:, None, :] - B[None], axis=2)
    da, db = D.min(axis=1), D.min(axis=0)
    allv = np.concatenate([da, db])
    mean = float((da * wa).sum() / max(wa.sum(), 1e-12) + (db * wb).sum() / max(wb.sum(), 1e-12)) / 2
    return {"mean_lab": round(mean, 4), "max_lab": round(float(allv.max()), 4), "p90_lab": round(float(np.percentile(allv, 90)), 4),
            "pairs": [[int(i), int(D[i].argmin()), round(float(D[i].min()), 3)] for i in range(len(A))]}


def extract(image, n=9, locked=None, method="notable", alpha_min=0.05, max_pixels=262144, seed=0, compare_to=None, pms=False):
    if pms:
        raise PaletteError(PANTONE)
    if not 2 <= int(n) <= 24:
        raise PaletteError("n must be 2..24")
    locked = list(locked or [])
    if len(locked) > int(n):
        raise PaletteError(f"locked has more than n ({n}) colours")
    if method not in ("notable", "kmeans"):
        raise PaletteError("method is notable | kmeans")
    if not 10000 <= int(max_pixels) <= 4000000:
        raise PaletteError("max_pixels is 10000..4000000")
    px = _pixels(image, alpha_min, int(max_pixels))
    pal = _palette(px, int(n), locked, method, seed)
    out = {"image": os.path.basename(image), "method": method, "n": int(n), "palette": pal, "sampled_pixels": int(len(px))}
    if compare_to:
        other = _palette(_pixels(compare_to, alpha_min, int(max_pixels)), int(n), locked, method, seed)
        out["distance"] = distance(pal, other)
        out["compare_to"] = os.path.basename(compare_to)
    out["sha256"] = hashlib.sha256(json.dumps(pal, sort_keys=True).encode()).hexdigest()
    return out


def write(out, out_dir, stem):
    from PIL import Image
    os.makedirs(out_dir, exist_ok=True)
    jp = os.path.join(out_dir, f"{stem}.palette.json")
    with open(jp, "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=1, sort_keys=True)
    sw = np.zeros((32, 32 * len(out["palette"]), 3), dtype=np.uint8)
    for i, c in enumerate(out["palette"]):
        sw[:, i * 32:(i + 1) * 32] = np.round(np.array(c["srgb"]) * 255).astype(np.uint8)
    sp = os.path.join(out_dir, f"{stem}.swatch.png")
    Image.fromarray(sw, "RGB").save(sp)
    return jp, sp


def make_materials(out, stem):
    import bpy
    names = []
    for i, c in enumerate(out["palette"]):
        base = f"PAL_{stem}_{i}"
        name, k = base, 1
        while name in bpy.data.materials:
            name, k = f"{base}.{k:03d}", k + 1
        m = bpy.data.materials.new(name)
        m.use_nodes = True
        bsdf = m.node_tree.nodes.get("Principled BSDF")
        if bsdf is not None:
            bsdf.inputs["Base Color"].default_value = (*c["linear"], 1.0)
        m.diffuse_color = (*c["linear"], 1.0)
        names.append(m.name)
    return names
