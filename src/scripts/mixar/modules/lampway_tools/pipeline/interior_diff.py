# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The interior-difference number: outline IoU reads only the cells on the silhouette's edge, so a finished face and the same model with its face deleted can score alike. This reads the rest
(specs/mrmak/05-model-compare.md section 6.7). Both renders are cropped to their mask's bounding box, resampled onto a LATTICE x LATTICE grid, and compared (mean absolute luminance) ONLY on
cells that are figure in both; ``cells_compared`` says how many, so a number over a handful of cells cannot pass as evidence. Ten height bands locate the difference. Bounding boxes are
half-open (x0, y0, x1, y1) throughout: mixing conventions gives confident garbage rather than an error. Numpy only; the idea follows the vendored img2threejs gate, the code is new."""

import numpy as np

LATTICE = 192
BANDS = 10
MIN_CELLS = 50


class InteriorError(ValueError):
    pass


def bbox(mask) -> tuple:
    """(x0, y0, x1, y1), x1 and y1 EXCLUSIVE."""
    ys, xs = np.nonzero(np.asarray(mask, bool))
    if not len(ys):
        raise InteriorError("no figure in the mask: nothing to compare")
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _lattice(lum, mask, n):
    x0, y0, x1, y1 = bbox(mask)
    ys = np.minimum(((np.arange(n) + 0.5) / n * (y1 - y0)).astype(int) + y0, y1 - 1)
    xs = np.minimum(((np.arange(n) + 0.5) / n * (x1 - x0)).astype(int) + x0, x1 - 1)
    return np.asarray(lum, float)[np.ix_(ys, xs)], np.asarray(mask, bool)[np.ix_(ys, xs)]


def enclosed_holes(mask) -> dict:
    """Background regions NOT connected to the image border (a hole inside the figure): {count, area_frac of the bounding box}."""
    m = np.asarray(mask, bool)
    x0, y0, x1, y1 = bbox(m)
    sub = ~m[y0:y1, x0:x1]
    h, w = sub.shape
    seen = np.zeros_like(sub)
    holes, area = 0, 0
    for sy in range(h):
        for sx in range(w):
            if not sub[sy, sx] or seen[sy, sx]:
                continue
            stack, cells, touches = [(sy, sx)], 0, False
            seen[sy, sx] = True
            while stack:
                y, x = stack.pop()
                cells += 1
                if y in (0, h - 1) or x in (0, w - 1):
                    touches = True
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and sub[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True
                        stack.append((ny, nx))
            if not touches:
                holes += 1
                area += cells
    return {"count": holes, "area_frac": round(area / (w * h), 6)}


def interior_diff(lum_a, mask_a, lum_b, mask_b, lattice: int = LATTICE, bands: int = BANDS) -> dict:
    la, ma = _lattice(lum_a, mask_a, lattice)
    lb, mb = _lattice(lum_b, mask_b, lattice)
    both = ma & mb
    cells = min(int(both.sum()), int(np.asarray(mask_a, bool).sum()), int(np.asarray(mask_b, bool).sum()))      # the lattice resamples, so the evidence is capped by the real figure pixels
    diff = np.abs(la - lb)
    out = {"interior_diff": round(float(diff[both].mean()), 6) if cells else 0.0, "cells_compared": cells, "evidence": "ok" if cells >= MIN_CELLS else "insufficient"}
    edges = np.linspace(0, lattice, bands + 1).astype(int)
    out["interior_bands"] = [round(float(diff[edges[i]:edges[i + 1]][both[edges[i]:edges[i + 1]]].mean()), 6) if both[edges[i]:edges[i + 1]].any() else 0.0 for i in range(bands)]
    ha, hb = enclosed_holes(mask_a), enclosed_holes(mask_b)
    out.update(hole_count_a=ha["count"], hole_count_b=hb["count"], hole_area_frac_a=ha["area_frac"], hole_area_frac_b=hb["area_frac"])
    return out
