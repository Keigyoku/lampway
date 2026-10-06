# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The review-render camera for a mesh-QA candidate (the PIECE_PIPELINE known gap: 'the QA candidate renders need a thicker highlight and cameras past
occluders'). The crop camera sits ``distance`` along the candidate's facing; a ray from the candidate toward it finds the nearest surface in front of the
candidate (another plate, a strap, a pauldron), and the camera's near clip starts beyond it, halfway between that occluder and the candidate, so the
crop shows the candidate itself. The highlight is sized in PIXELS of the render: at least ``min_px`` wide whatever the crop's scale."""

from mathutils import Vector

MIN_PX = 4.0
SELF_M = 0.004          # hits closer than this to the candidate are its own surface (a rim, a hem), not an occluder


def review_camera(centroid, facing, extent, tree=None, res=640, distance=1.2, min_px=MIN_PX) -> dict:
    """{location, target, ortho_scale_m, clip_start_m, occluder_m, highlight_radius_m} for the crop render of one candidate."""
    c, n = Vector(centroid), Vector(facing).normalized()
    scale = max(max(extent) * 1.7, 0.08)
    occluder = None
    if tree is not None:
        origin = c + n * SELF_M
        hit = tree.ray_cast(origin, n, distance)
        if hit[0] is not None:
            occluder = SELF_M + hit[3]
    clip = 0.001 if occluder is None else max(0.001, distance - occluder * 0.5)
    radius = max(0.0015, min_px * 0.5 * scale / float(res))
    return {"location": list(c + n * distance), "target": list(c), "ortho_scale_m": round(scale, 6), "clip_start_m": round(clip, 6),
            "occluder_m": None if occluder is None else round(occluder, 6), "highlight_radius_m": round(radius, 6)}
