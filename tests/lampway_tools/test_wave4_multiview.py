# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""anim_multiview_fit (generation/anim_multiview_fit.md section 10): motion from ONE split-screen clip, on a synthetic ground truth.

A known walk of a 14-joint skeleton is projected into two orthographic panels (front and side) with detector noise and the side view's near/far leg swaps. The fit must recover the bone directions within 5 degrees and
the leg identity in 100 % of frames; the single-view mode must FAIL leg identity on the same clip (the control that proves the second view matters)."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import anim_mv as MV  # noqa: E402

PX_PER_M = 400.0
FPS = 24


def _walk(n=48):
    """(n, J, 3) world joints: X lateral (+ = the character's left), Y forward, Z up. A walk cycle with arms counter-swinging."""
    rng = np.arange(n)
    ph = 2 * np.pi * rng / 24.0
    J = np.zeros((n, len(MV.JOINTS), 3))
    idx = {j: i for i, j in enumerate(MV.JOINTS)}
    for t in range(n):
        p = {"pelvis": (0, 0.05 * t * 0.02, 1.0), }
        root = np.array([0.0, 0.02 * t, 1.0])
        sw = 0.35 * np.sin(ph[t])
        def leg(side, s):
            lift = 0.12 * max(0.0, np.cos(ph[t] + (0.0 if side > 0 else np.pi)))        # the swing foot leaves the ground: the two legs' heights differ, which is what the front view tells the side view apart by
            x = 0.1 * side
            hip = root + np.array([x, 0, 0])
            knee = hip + np.array([0, 0.45 * np.sin(s), -0.45 * np.cos(s)])
            ank = knee + np.array([0, 0.45 * np.sin(s * 0.6), -0.45 * np.cos(s * 0.6)])
            return hip, knee + np.array([0, 0, 0.5 * lift]), ank + np.array([0, 0, lift])
        def arm(side, s):
            sh = root + np.array([0.2 * side, 0, 0.55])
            el = sh + np.array([0.02 * side, 0.3 * np.sin(s), -0.3 * np.cos(s)])
            wr = el + np.array([0, 0.25 * np.sin(s * 1.3), -0.25 * np.cos(s * 1.3)])
            return sh, el, wr
        J[t, idx["pelvis"]] = root
        J[t, idx["spine"]] = root + [0, 0, 0.35]
        J[t, idx["head"]] = root + [0, 0, 0.75]
        for side, name, s in ((1, "l", sw), (-1, "r", -sw)):
            hip, knee, ank = leg(side, s)
            J[t, idx[f"thigh_{name}"]], J[t, idx[f"calf_{name}"]], J[t, idx[f"foot_{name}"]] = hip, knee, ank
            sh, el, wr = arm(side, -s)
            J[t, idx[f"upperarm_{name}"]], J[t, idx[f"lowerarm_{name}"]], J[t, idx[f"hand_{name}"]] = sh, el, wr
    return J


def _panels(J, noise_px=0.7, swap_side_legs=True, seed=0):
    """Front: u from X, v from Z. Side (the character faces LEFT in the panel): u from -Y, v from Z. Detectors label legs/arms by left/right in the front but arbitrarily (near/far guess) in the side."""
    rng = np.random.default_rng(seed)
    n = len(J)
    cx_f, cx_s, cy = 200.0, 200.0, 560.0
    front = np.stack([cx_f + PX_PER_M * J[:, :, 0], cy - PX_PER_M * J[:, :, 2]], -1) + rng.normal(0, noise_px, (n, len(MV.JOINTS), 2))
    side = np.stack([cx_s - PX_PER_M * (J[:, :, 1] - J[:, :1, 1]), cy - PX_PER_M * J[:, :, 2]], -1) + rng.normal(0, noise_px, (n, len(MV.JOINTS), 2))
    if swap_side_legs:
        for t in range(n):
            if t % 2 == 0:                                      # the side view's near/far guess is wrong on alternating frames
                for a, b in MV.PAIRS:
                    side[t, [MV.IDX[a], MV.IDX[b]]] = side[t, [MV.IDX[b], MV.IDX[a]]]
    return front, side


def _bone_dirs(J):
    out = []
    for parent, child in MV.BONES:
        d = J[:, MV.IDX[child]] - J[:, MV.IDX[parent]]
        out.append(d / np.maximum(np.linalg.norm(d, axis=1, keepdims=True), 1e-9))
    return np.stack(out, 1)


def test_the_two_view_fit_recovers_the_bone_directions_within_5_degrees_and_the_leg_identity_in_every_frame():
    J = _walk()
    front, side = _panels(J)
    fit = MV.fit(front, side, MV.Calibration(px_per_m=PX_PER_M, front_origin=(200.0, 560.0), side_origin=(200.0, 560.0)))
    err = MV.bone_direction_error_deg(_bone_dirs(J), fit["bone_dirs"])
    assert err.max() < 5.0, err.max()
    assert fit["leg_identity"]["accuracy_vs_front"] > 0.99 and fit["leg_identity"]["frames_flipped"] == 0
    truth = MV.leg_identity_accuracy(J, fit["joints"])
    assert truth == 1.0


def test_the_single_view_mode_fails_leg_identity_on_the_same_clip_the_control_that_proves_the_second_view_matters():
    J = _walk()
    front, side = _panels(J)
    cal = MV.Calibration(px_per_m=PX_PER_M, front_origin=(200.0, 560.0), side_origin=(200.0, 560.0))
    single = MV.fit_single_view(side, cal)
    acc = MV.leg_identity_accuracy(J, single["joints"])
    assert acc < 0.9, acc                                      # a profile view cannot tell near from far: identity is a coin toss on the alternately swapped labels
    two = MV.fit(front, side, cal)
    assert MV.leg_identity_accuracy(J, two["joints"]) == 1.0


def test_triangulation_takes_x_from_the_front_z_from_the_side_and_the_confidence_weighted_height_from_both():
    front = np.array([[[300.0, 160.0]]]); side = np.array([[[100.0, 180.0]]])
    cal = MV.Calibration(px_per_m=100.0, front_origin=(200.0, 560.0), side_origin=(200.0, 560.0))
    j = MV.triangulate(front, side, cal, front_conf=np.array([[1.0]]), side_conf=np.array([[3.0]]))
    assert j[0, 0, 0] == pytest.approx(1.0) and j[0, 0, 1] == pytest.approx(1.0)       # X from the front u, Y (forward, facing left) from the side u
    assert j[0, 0, 2] == pytest.approx((4.0 * 1 + 3.8 * 3) / 4)                         # Z = confidence-weighted mean of the two heights


def test_the_panel_divider_is_found_and_a_clip_with_no_divider_is_refused():
    f = np.full((200, 400, 3), 120, np.uint8); f[:, :200] += 30; f[:, 199:201] = 255
    left, right, col = MV.split_panels(f)
    assert abs(col - 200) <= 2 and left.shape[1] == 199 and right.shape[1] == 199
    with pytest.raises(MV.MultiviewError, match="re-generate with template anim-split-front-side"):
        MV.split_panels(np.full((200, 400, 3), 128, np.uint8))


def test_calibration_fits_one_orthographic_scale_from_the_head_to_sole_height():
    mask = np.zeros((600, 200), bool); mask[100:580, 80:120] = True               # 480 px tall figure
    assert MV.px_per_m_from_mask(mask, 1.2) == pytest.approx(400.0, rel=0.01)


def test_held_frames_are_detected_and_the_true_motion_rate_is_resampled_out():
    base = [np.full((8, 8), v, np.uint8) for v in (10, 40, 70, 100)]
    clip = [f for f in base for _ in range(2)]                                      # every frame held twice: 48 fps pretending, 24 of motion
    d = MV.duplicate_frames(clip)
    assert d["held"] == [1, 3, 5, 7] and d["true_fps"] == pytest.approx(12.0) and d["unique"] == 4
    assert MV.duplicate_frames(base)["held"] == []


def test_the_grid_parallax_gives_the_floor_speed_in_pixels_per_frame_and_metres_per_second():
    rng = np.random.default_rng(2)
    row = rng.random(512)
    frames = [np.tile(np.roll(row, 16 * t)[None, :], (40, 1)) for t in range(6)]
    px = MV.grid_parallax_px_per_frame(frames)
    assert px == pytest.approx(16.0, abs=0.3)
    assert MV.speed_mps(px, px_per_m=400.0, fps=24.0) == pytest.approx(16.0 / 400.0 * 24.0, rel=1e-6)


def test_the_silhouette_refine_pulls_a_perturbed_pose_back_and_never_makes_the_cost_worse():
    J = _walk(1)[0]
    truth = MV.pose_from_joints(J)
    start = truth + np.random.default_rng(1).normal(0, np.radians(8), truth.shape)
    target = MV.capsule_masks(MV.joints_from_pose(truth, J), (600, 400), PX_PER_M)
    cost = lambda p: MV.silhouette_cost(MV.capsule_masks(MV.joints_from_pose(p, J), (600, 400), PX_PER_M), target)
    refined, hist = MV.refine(start, cost, step_deg=4.0, rounds=6)
    assert hist[-1] < hist[0] * 0.5 and all(b <= a + 1e-12 for a, b in zip(hist, hist[1:]))
    assert cost(refined) < cost(start)


def test_a_clip_whose_panels_are_out_of_sync_or_whose_character_differs_is_refused():
    J = _walk(24)
    front, side = _panels(J)
    cal = MV.Calibration(px_per_m=PX_PER_M, front_origin=(200.0, 560.0), side_origin=(200.0, 560.0))
    ok = MV.sync_score(front, side, cal)
    shifted = MV.sync_score(front, np.roll(side, 7, axis=0), cal)
    assert ok > 0.9 and shifted < 0.5
    with pytest.raises(MV.MultiviewError, match="panels out of sync; re-generate"):
        MV.check_sync(shifted, 0.8)
    with pytest.raises(MV.MultiviewError, match="the clip's character differs from the rig"):
        MV.check_character(0.5, 0.9)
