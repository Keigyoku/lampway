# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 10 B (silhouette instruments): compare two masks at their TRUE aspect.

A plate carries no camera, so two masks are put in one frame by subject-height framing: each is scaled about its bounding box
so its height is the same, the larger aspect fitting the canvas, and centred - never cropped to its own box and stretched to a
square (golden C11: a 2:1 rectangle against a 1:1 square reads IoU 0.5 at the true aspect and 1.0 when stretched)."""

import numpy as np


def mask_iou(a, b):
    a, b = np.asarray(a, bool), np.asarray(b, bool)
    return float((a & b).sum() / max((a | b).sum(), 1))


def _place(mask, h_out, size):
    ys, xs = np.nonzero(mask)
    out = np.zeros((size, size), bool)
    if not len(ys):
        return out
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    k = h_out / (y1 - y0)
    w_out = max(1, int(round((x1 - x0) * k)))
    hh = max(1, int(round(h_out)))
    yi = np.clip(y0 + ((np.arange(hh) + 0.5) / k).astype(int), y0, y1 - 1)
    xi = np.clip(x0 + ((np.arange(w_out) + 0.5) / k).astype(int), x0, x1 - 1)
    patch = mask[np.ix_(yi, xi)]
    oy, ox = (size - hh) // 2, (size - w_out) // 2
    out[oy:oy + hh, ox:ox + w_out] = patch
    return out


def fit_masks_true_aspect(a, b, size, fill=0.9):
    """(a', b'): both masks on one ``size`` x ``size`` canvas at one subject height, aspect kept, centred."""
    asp = []
    for m in (a, b):
        ys, xs = np.nonzero(m)
        if len(ys):
            asp.append((xs.max() - xs.min() + 1) / (ys.max() - ys.min() + 1))
    h_out = fill * size / max([1.0] + asp)
    return _place(np.asarray(a, bool), h_out, size), _place(np.asarray(b, bool), h_out, size)
