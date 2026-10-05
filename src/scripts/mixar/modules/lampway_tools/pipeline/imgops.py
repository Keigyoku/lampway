# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The few scipy.ndimage operations the plate tools need, in numpy (Blender's python has numpy and PIL, not scipy). Definitions follow scipy's defaults: a gaussian
with reflect borders truncated at 4 sigma, a 4-connected (cross) structuring element, erosion with the outside taken as empty, holes = background not 4-connected
to the border."""

import numpy as np


def gaussian(a: np.ndarray, sigma: float) -> np.ndarray:
    """A separable gaussian filter, mode 'reflect', truncated at 4 sigma (scipy.ndimage.gaussian_filter's defaults)."""
    a = np.asarray(a, dtype=np.float64)
    if sigma <= 0:
        return a.copy()
    r = int(4.0 * sigma + 0.5)
    x = np.arange(-r, r + 1, dtype=np.float64)
    k = np.exp(-0.5 * (x / sigma) ** 2)
    k /= k.sum()
    out = a
    for axis in range(a.ndim):
        pad = [(0, 0)] * a.ndim
        pad[axis] = (r, r)
        p = np.pad(out, pad, mode="symmetric")                 # scipy 'reflect' = numpy 'symmetric'
        acc = np.zeros_like(out)
        n = out.shape[axis]
        for i, w in enumerate(k):
            sl = [slice(None)] * a.ndim
            sl[axis] = slice(i, i + n)
            acc += w * p[tuple(sl)]
        out = acc
    return out


def _shift_or(m: np.ndarray) -> np.ndarray:
    """m dilated by the cross."""
    o = m.copy()
    o[1:, :] |= m[:-1, :]
    o[:-1, :] |= m[1:, :]
    o[:, 1:] |= m[:, :-1]
    o[:, :-1] |= m[:, 1:]
    return o


def _shift_and(m: np.ndarray) -> np.ndarray:
    """m eroded by the cross; the outside counts as empty."""
    o = m.copy()
    o[1:, :] &= m[:-1, :]
    o[0, :] = False
    o[:-1, :] &= m[1:, :]
    o[-1, :] = False
    o[:, 1:] &= m[:, :-1]
    o[:, 0] = False
    o[:, :-1] &= m[:, 1:]
    o[:, -1] = False
    return o


def binary_opening(mask: np.ndarray, iterations: int = 1) -> np.ndarray:
    m = np.asarray(mask, dtype=bool)
    for _ in range(int(iterations)):
        m = _shift_and(m)
    for _ in range(int(iterations)):
        m = _shift_or(m)
    return m


def label_background(mask: np.ndarray) -> np.ndarray:
    """Labels of the False (background) pixels, 4-connected, by run-length union-find (0 = foreground). Fast on large plates: work is per run, not per pixel."""
    h, w = mask.shape
    parent = [0]

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    labels = np.zeros(mask.shape, dtype=np.int32)
    prev = []                                                  # [(start, end, label)] of the previous row
    for y in range(h):
        bg = ~mask[y]
        d = np.diff(np.concatenate(([0], bg.astype(np.int8), [0])))
        starts, ends = np.nonzero(d == 1)[0], np.nonzero(d == -1)[0]
        cur, j = [], 0
        for s, e in zip(starts, ends):
            lab = 0
            while j < len(prev) and prev[j][1] <= s:
                j += 1
            k = j
            while k < len(prev) and prev[k][0] < e:
                other = prev[k][2]
                if lab == 0:
                    lab = find(other)
                else:
                    ra, rb = find(lab), find(other)
                    if ra != rb:
                        parent[rb] = ra
                k += 1
            if lab == 0:
                parent.append(len(parent))
                lab = len(parent) - 1
            cur.append((int(s), int(e), lab))
            labels[y, s:e] = lab
        prev = cur
    roots = np.array([find(i) for i in range(len(parent))], dtype=np.int32)
    return roots[labels] * (labels > 0)


def fill_holes(mask: np.ndarray) -> np.ndarray:
    """The mask with every hole filled: background regions that do not touch the border (4-connectivity, scipy.ndimage.binary_fill_holes)."""
    m = np.asarray(mask, dtype=bool)
    lab = label_background(m)
    border = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    outside = np.isin(lab, border[border > 0])
    return ~outside
