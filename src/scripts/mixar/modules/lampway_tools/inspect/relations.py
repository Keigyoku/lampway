# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T1's specified world-AABB relations; pure numpy, with no scene writes."""
import numpy as np


def classify(a, b, tolerance_m=0.005):
    a, b = np.asarray(a, dtype=float).reshape(2, 3), np.asarray(b, dtype=float).reshape(2, 3)
    sa, sb = a[1] - a[0], b[1] - b[0]
    overlap = np.maximum(0, np.minimum(a[1], b[1]) - np.maximum(a[0], b[0]))
    gap = float(np.linalg.norm(np.maximum(0, np.maximum(a[0] - b[1], b[0] - a[1]))))
    xy = float(np.prod(overlap[:2]))
    footprint_a, footprint_b = float(np.prod(sa[:2])), float(np.prod(sb[:2]))
    if np.all(a[0] >= b[0]) and np.all(a[1] <= b[1]):
        relation = 'inside'
    elif abs(a[0, 2] - b[1, 2]) <= tolerance_m and footprint_a > 0 and xy >= .25 * footprint_a:
        relation = 'on_top_of'
    elif abs(b[0, 2] - a[1, 2]) <= tolerance_m and footprint_b > 0 and xy >= .25 * footprint_b:
        relation = 'under'
    elif np.all(np.minimum(a[1], b[1]) > np.maximum(a[0], b[0])):
        relation = 'overlaps'
    elif gap <= tolerance_m:
        relation = 'touching'
    elif gap <= .1 * max(float(np.linalg.norm(sa)), float(np.linalg.norm(sb))):
        relation = 'near'
    else:
        relation = 'apart'
    diag_b = float(np.linalg.norm(sb))
    return {'relation': relation, 'gap_m': round(gap, 4),
            'size_ratio': round(float(np.linalg.norm(sa)) / diag_b, 4) if diag_b else None,
            'height_ratio': round(float(sa[2] / sb[2]), 4) if sb[2] else None,
            'overlap_fraction': round(float(np.prod(overlap) / np.prod(sa)), 4) if np.prod(sa) else 0,
            'aligned_axes': [axis for axis in range(3) if abs(float((a[0, axis] + a[1, axis] - b[0, axis] - b[1, axis]) / 2)) <= tolerance_m]}
