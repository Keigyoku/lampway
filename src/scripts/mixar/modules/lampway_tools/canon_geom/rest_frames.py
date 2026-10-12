# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Canon17 numerical rest-frame serialization; never edits authored matrices.

Blender's float32 vec_roll_to_mat3_normalized has a cancellation-sensitive
1/(1+y) branch above SAFE_THRESHOLD=6.1e-3 (blenkernel/intern/armature.cc).
eps32 / SAFE_THRESHOLD is a conservative *admission budget*, not a claim that
every possible hierarchy error is bounded by it. Larger errors still refuse.
The closest orthogonal matrix is the polar factor U@Vt; positive determinants
are required before and after it. Canon21's unchanged .01deg axis bar also holds.
"""
import numpy as np

FLOAT32_FRAME_BUDGET = float(np.finfo(np.float32).eps / 6.1e-3)
MAX_AXIS_CORRECTION_DEG = 0.01


def canonical_rest_frame(frame, proper):
    """Return (canonical rotation, diagnostics), retaining valid frames exactly."""
    source = np.asarray(frame, dtype=float)
    if source.shape != (3, 3) or not np.isfinite(source).all():
        raise ValueError("rest frame must be a finite 3x3 matrix")
    if proper(source):
        return source.copy(), None
    if np.linalg.det(source) <= 0:
        raise ValueError("rest frame reflection or singularity cannot be repaired")
    u, singular, vt = np.linalg.svd(source)
    correction = float(np.max(np.abs(singular - 1)))
    if correction > FLOAT32_FRAME_BUDGET:
        raise ValueError("rest frame shear/scale exceeds the float32 producer correction budget")
    rotation = u @ vt
    if not proper(rotation):
        raise ValueError("rest frame polar factor is not a proper rotation")
    norms = np.linalg.norm(source, axis=0)
    cosine = np.sum((source / norms) * rotation, axis=0)
    angles = np.degrees(np.arccos(np.clip(cosine, -1, 1)))
    angle = float(np.max(angles))
    if angle > MAX_AXIS_CORRECTION_DEG:
        raise ValueError("rest frame correction exceeds the unchanged export axis bar")
    return rotation, {"spectral_correction": correction, "max_axis_correction_deg": angle,
                      "budget": FLOAT32_FRAME_BUDGET, "method": "bounded_polar_float32"}
