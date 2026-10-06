# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_geom: the ONE source of the algorithm canon's shared geometry (specs/canon, IMPLEMENTATION_PLAN item 1).

Every Lampway tool that fits, weights, poses, places, measures UVs or signs a distance imports these primitives instead of
re-deriving them. numpy only (Blender ships numpy, not scipy); no bpy. The names below are the stable interface
(``API_VERSION``); a breaking change bumps it and is recorded in the canon lane's report with migration notes.

Frames and units: canon 01 (``conventions``). Each primitive names its canon page in its module docstring.
"""

from .axes import check_expect, control_shift, expand_pose, pose_cs, qaxis, qinv, qmul, qrot, resolve_axis, segment_box_overlap
from .bones import CONTINUATION, MAIN_CHILD, bone_segments, chain_ends, curl_delta, finger_axis, flex_axis
from .conventions import BODY_FRAME, BONE_AXIS_EXPORT, BONE_DIRECTION, conventions_block
from .enclosure import enclosure_shift, first_hit, harmonic_centre, inner_wall_centre, slice_segments
from .identity import WELD_M, components, weld_keys
from .inside import PseudoNormals, boundary_edges, closest_points, signed_distance, winding_numbers
from .lbs import SINGULAR_DET_MIN, SingularBlendError, blended, lbs, lbs_inverse, round_trip_error
from .masks import fit_masks_true_aspect, mask_iou
from .rigid import apply_similarity, rotation_angle_axis, similarity_fit, similarity_receipt
from .seams import SEAM_OPEN_M, seam_gaps, seam_ledger, segment_crossings
from .skinweights import ZeroWeightError, band_weights, dress, falloff_weights, inpaint_harmonic, remap_rows, remap_table
from .uvmeasure import coverage, raster_half_open, uv_island_ids, uv_metrics
from .views import apply_offsets, calibrate, project, triangulate, triangulate_robust

API_VERSION = 1

__all__ = [
    "API_VERSION", "BODY_FRAME", "BONE_AXIS_EXPORT", "BONE_DIRECTION", "CONTINUATION", "MAIN_CHILD", "SEAM_OPEN_M", "SINGULAR_DET_MIN", "WELD_M",
    "PseudoNormals", "SingularBlendError", "ZeroWeightError", "band_weights", "dress", "falloff_weights", "inpaint_harmonic",
    "fit_masks_true_aspect", "mask_iou", "remap_rows", "remap_table", "seam_gaps", "seam_ledger", "segment_crossings", "apply_offsets", "apply_similarity", "blended", "bone_segments", "boundary_edges",
    "calibrate", "chain_ends", "check_expect", "closest_points", "components", "control_shift", "conventions_block", "coverage",
    "curl_delta", "enclosure_shift", "expand_pose", "finger_axis", "first_hit", "flex_axis", "harmonic_centre", "inner_wall_centre", "lbs",
    "lbs_inverse", "pose_cs", "project", "qaxis", "qinv", "qmul", "qrot", "raster_half_open", "resolve_axis", "rotation_angle_axis",
    "round_trip_error", "segment_box_overlap", "signed_distance", "similarity_fit", "similarity_receipt", "slice_segments",
    "triangulate", "triangulate_robust", "uv_island_ids", "uv_metrics", "weld_keys", "winding_numbers",
]
