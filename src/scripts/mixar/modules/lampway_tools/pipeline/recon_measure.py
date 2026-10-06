# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The reconstruction instrument's remainder (STATUS O39), ported from the astra-1 shelf's spike measure.py and made exact:

* silhouettes are orthographic rasters of the mesh (anim_ref.raster_mask: a pixel is set when its centre is inside a triangle), on the WEARER's axes in the
  canonical frame (front -Y, wearer's left +X, +Z up; top and bottom views have the wearer's front at the image top);
* the 24 proper axis-aligned orientations are searched for the best mean IoU against the front, left and top plates (the shelf's search views). Every
  orientation's view is a flip or transpose of one of three base projections, so the search rasterises three times, not 72 (pinned against direct
  rasters for all 24 x 6);
* IoU compares the two silhouettes cropped to their bounds and resized to one size (bicubic, then > 127), as the shelf did: it measures shape, not scale;
* cavity: one ray up through the crown centre (the centroid of the top silhouette) from below the mesh; cavity_ratio = floor to first surface over height
  (~0 solid, high for a hollow crown), shell_ratio = first to second surface over height;
* crest fin from the top view: the rows narrower than 35 % of the widest row (the shelf's comment says "of the helmet width"; its code divided by the
  longest column, a front-to-back length, which is corrected here);
* luminance: the mean albedo luminance on the wearer's left (+X) over the wearer's right (-X); a baked directional light makes one side brighter.
Pure numpy (PIL for the resize)."""

import itertools

import numpy as np

from . import anim_ref as AR

VIEWS = {"front": ((1, 0, 0), (0, 0, 1)), "right": ((0, -1, 0), (0, 0, 1)), "back": ((-1, 0, 0), (0, 0, 1)),
         "left": ((0, 1, 0), (0, 0, 1)), "top": ((-1, 0, 0), (0, -1, 0)), "bottom": ((1, 0, 0), (0, -1, 0))}
SEARCH_VIEWS = ("front", "left", "top")
FIN_FRACTION = 0.35


def rotations():
    for p in itertools.permutations(range(3)):
        for s in itertools.product((1, -1), repeat=3):
            R = np.zeros((3, 3))
            for i, (j, sg) in enumerate(zip(p, s)):
                R[i, j] = sg
            if np.linalg.det(R) > 0:
                yield R


def normalise(v):
    """Bounding-box centre at the origin, the longest side 1: every view then fits a unit square."""
    v = np.asarray(v, float)
    lo, hi = v.min(0), v.max(0)
    return (v - (lo + hi) / 2) / float((hi - lo).max())


def _cam(right, up, size):
    return {"size": [size, size], "center": [0.0, 0.0, 0.0], "right": list(map(float, right)), "up": list(map(float, up)), "px_per_m": float(size)}


def raster(v, t, view, size):
    right, up = VIEWS[view]
    return AR.raster_mask(np.asarray(v, float), np.asarray(t), _cam(right, up, size))


def base_masks(v, t, size):
    e = np.eye(3)
    return {(i, j): AR.raster_mask(np.asarray(v, float), np.asarray(t), _cam(e[i], e[j], size)) for i, j in ((0, 1), (0, 2), (1, 2))}


def view_mask(base, R, view):
    """The view of the mesh turned by R, from the three base projections: columns follow +e_a, rows -e_b."""
    right, up = (np.asarray(x, float) for x in VIEWS[view])
    ro, uo = R.T @ right, R.T @ up
    a, b = int(np.argmax(np.abs(ro))), int(np.argmax(np.abs(uo)))
    if a < b:
        m = base[(a, b)]
    else:
        m = base[(b, a)][::-1, ::-1].T
    if ro[a] < 0:
        m = m[:, ::-1]
    if uo[b] < 0:
        m = m[::-1, :]
    return m


def crop(mask):
    ys, xs = np.nonzero(mask)
    return mask[ys.min():ys.max() + 1, xs.min():xs.max() + 1] if len(ys) else mask


def iou(a, b) -> float:
    from PIL import Image
    a, b = crop(np.asarray(a, bool)), crop(np.asarray(b, bool))
    if not a.any() or not b.any():
        return 0.0
    h, w = max(a.shape[0], b.shape[0]), max(a.shape[1], b.shape[1])
    rs = lambda m: np.asarray(Image.fromarray(m.astype(np.uint8) * 255).resize((w, h), Image.Resampling.BICUBIC)) > 127
    ra, rb = rs(a), rs(b)
    u = (ra | rb).sum()
    return float((ra & rb).sum() / u) if u else 0.0


def plate_mask(path):
    from PIL import Image
    im = Image.open(path)
    if "A" not in im.getbands():
        raise ValueError(f"{path}: a plate needs alpha (the matte); key it first (lampway_image_matte)")
    m = np.asarray(im.getchannel("A")) > 127
    if not m.any():
        raise ValueError(f"{path}: the plate's alpha is empty")
    return crop(m)


def _ray_hits(v, t, origin, direction):
    """Every distance along the ray where it meets a triangle (Moller-Trumbore, all triangles at once), sorted and de-duplicated at shared edges."""
    tri = np.asarray(v, float)[np.asarray(t)]
    e1, e2 = tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]
    p = np.cross(direction, e2)
    det = (e1 * p).sum(1)
    ok = np.abs(det) > 1e-12
    inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
    s = origin - tri[:, 0]
    u = (s * p).sum(1) * inv
    q = np.cross(s, e1)
    w = (np.asarray(direction) * q).sum(1) * inv
    d = (e2 * q).sum(1) * inv
    hit = ok & (u >= 0) & (w >= 0) & (u + w <= 1) & (d > 0)
    out = []
    for x in np.sort(d[hit]):
        if not out or x - out[-1] > 1e-9:
            out.append(float(x))
    return out


def cavity(v, t, size=128):
    v = np.asarray(v, float)
    lo, hi = v.min(0), v.max(0)
    scale = float((hi - lo).max())
    top = raster(normalise(v), t, "top", size)
    ys, xs = np.nonzero(top)
    if not len(xs):
        return {"ray_hits": 0, "cavity_ratio": None, "shell_ratio": None}
    u, w = (xs.mean() + 0.5) / size - 0.5, 0.5 - (ys.mean() + 0.5) / size        # along the top view's right (-X) and up (-Y)
    cx, cy = -u * scale + (lo[0] + hi[0]) / 2, -w * scale + (lo[1] + hi[1]) / 2
    hits = _ray_hits(v, t, np.array([cx, cy, lo[2] - 1.0]), np.array([0.0, 0.0, 1.0]))
    zs = [lo[2] - 1.0 + d for d in hits]
    hgt = float(hi[2] - lo[2])
    return {"ray_hits": len(zs), "crown_xy": [round(float(cx), 6), round(float(cy), 6)],
            "cavity_ratio": round((zs[0] - lo[2]) / hgt, 4) if zs else None, "shell_ratio": round((zs[1] - zs[0]) / hgt, 4) if len(zs) >= 2 else None}


def crest(top_mask):
    rows = np.asarray(top_mask, bool).sum(1)
    if not rows.any():
        return {"crest_fin_width_ratio": None, "crest_fin_length_ratio": 0.0}
    width = rows.max()
    fin = rows[(rows > 0) & (rows < FIN_FRACTION * width)]
    return {"crest_fin_width_ratio": round(float(fin.mean() / width), 4) if len(fin) else None,
            "crest_fin_length_ratio": round(float(len(fin) / max(1, (rows > 0).sum())), 4)}


def lum_ratio(x, lum):
    x, lum = np.asarray(x, float), np.asarray(lum, float)
    left, right = lum[x > 0], lum[x < 0]
    if not len(left) or not len(right) or right.mean() <= 0:
        return None
    return round(float(left.mean() / right.mean()), 4)


def measure(v, t, plates, size=256):
    """plates: {view: cropped bool mask}; the front, left and top plates drive the orientation search."""
    missing = [s for s in SEARCH_VIEWS if s not in plates]
    if missing:
        raise ValueError(f"the orientation search needs the {', '.join(missing)} plate(s) ({', '.join(SEARCH_VIEWS)})")
    vn, t = normalise(v), np.asarray(t)
    base = base_masks(vn, t, size)
    best = None
    for R in rotations():
        score = float(np.mean([iou(view_mask(base, R, s), plates[s]) for s in SEARCH_VIEWS]))
        if best is None or score > best[0] + 1e-12:
            best = (score, R)
    score, R = best
    ious = {s: round(iou(view_mask(base, R, s), plates[s]), 4) for s in VIEWS if s in plates}
    oriented = vn @ R.T
    out = {"orientation": R.astype(int).tolist(), "orientation_is_identity": bool(np.allclose(R, np.eye(3))), "iou": ious,
           "iou_mean_search": round(score, 4), "iou_mean_all": round(float(np.mean(list(ious.values()))), 4), "size": size}
    out.update(cavity(oriented, t, size=min(size, 256)))
    out.update(crest(raster(oriented, t, "top", size)))
    return out
