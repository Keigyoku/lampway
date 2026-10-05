# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""anim_check and anim_loop_export gates (generation/anim_check.md, anim_loop_export.md), on synthetic walks with a known answer."""

import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import anim_gates as AG  # noqa: E402
from mixar.modules.lampway_tools.pipeline import anim_mv as MV  # noqa: E402

FPS = 24.0
PERIOD = 28          # frames per stride pair (one cycle of both legs)
SPEED = 1.04         # m/s


def _walk(n=PERIOD * 4 + 1, drag_cm=0.0, swap=False):
    """World joints (n, J, 3): feet planted for half the cycle with the root moving at SPEED, lifted and carried forward for the other half. drag_cm slides the planted left foot."""
    J = np.zeros((n, len(MV.JOINTS), 3))
    idx = MV.IDX
    v = SPEED / FPS                                              # metres per frame
    for t in range(n):
        pel_y = v * t
        J[t, idx["pelvis"]] = [0, pel_y, 1.0]
        for side, x, phase0 in (("l", 0.1, 0.0), ("r", -0.1, 0.5)):
            ph = ((t / PERIOD) + phase0) % 1.0
            stride = v * PERIOD
            cycle = int(np.floor(t / PERIOD + phase0))
            y0 = v * PERIOD * (cycle - phase0) + 0.25 * stride          # where this cycle's stance starts: a quarter stride ahead of the root
            if ph < 0.5:                                          # stance: the foot is fixed in the world while the root moves on
                y, z = y0, 0.0
                if side == "l" and drag_cm:
                    y += drag_cm / 100.0 * (ph / 0.5)
            else:                                                 # swing: carried forward one stride to the next stance point
                s_ = (ph - 0.5) / 0.5
                y, z = y0 + s_ * stride, 0.12 * np.sin(np.pi * s_)
            J[t, idx[f"foot_{side}"]] = [x, y, z]
    if swap:
        J[:, :, 1] = -(J[:, :, 1] - J[:, :1, 1]) + J[:, :1, 1]        # fore-aft mirror about the pelvis
    return J


def test_the_legs_metric_reads_about_100_percent_on_a_walk_and_about_0_on_its_fore_aft_swapped_copy():
    good = AG.legs_forward_share(_walk(), FPS)
    bad = AG.legs_forward_share(_walk(swap=True), FPS)
    assert good["share"] >= 0.95 and bad["share"] <= 0.05, (good, bad)
    assert good["lifted_frames"] > 20


def test_foot_slide_is_zero_for_a_planted_foot_and_a_dragging_foot_fails_the_gate():
    ok = AG.foot_slide(_walk(), FPS)
    assert ok["max_slide_cm"] < 0.5 and ok["phases"] >= 6
    dragged = AG.foot_slide(_walk(drag_cm=5.0), FPS)
    assert dragged["max_slide_cm"] > 3.0
    gates = AG.motion_gates(_walk(drag_cm=5.0), FPS)
    assert not gates["G-FOOT-SLIDE"]["passed"] and gates["G-FOOT-SLIDE"]["threshold"] == 1.0
    assert AG.motion_gates(_walk(), FPS)["G-FOOT-SLIDE"]["passed"]


def test_planted_foot_height_is_measured_against_the_floor():
    J = _walk()
    assert AG.foot_plant(J)["max_height_cm"] < 0.5
    J2 = J.copy(); J2[:, MV.IDX["foot_l"], 2] += 0.04
    assert AG.foot_plant(J2)["max_height_cm"] > 3.0 and not AG.motion_gates(J2, FPS)["G-FOOT-PLANT"]["passed"]


def test_outline_iou_is_one_against_its_own_mask_and_falls_when_the_mask_shifts():
    m = np.zeros((100, 60), bool); m[10:90, 20:40] = True
    assert AG.outline_iou([m, m], [m, m]) == 1.0
    assert AG.outline_iou([np.roll(m, 12, axis=1)], [m]) < 0.9


def test_a_missing_side_mask_is_refused_a_single_view_cannot_tell_which_leg_is_in_front():
    with pytest.raises(AG.GateError, match="no side-view mask: a single view cannot settle which leg is in front"):
        AG.check(_walk(), FPS, masks={"front": [np.zeros((4, 4), bool)]}, rendered=None)


def test_twist_is_the_largest_yaw_difference_wrapped_into_180():
    a = np.radians(np.array([[0.0, 179.0], [10.0, -179.0]]))
    b = np.radians(np.array([[3.0, -179.0], [10.0, 179.0]]))
    assert AG.twist_deg(a, b) == pytest.approx(3.0, abs=1e-6)


def test_the_check_names_every_gate_with_its_number_and_leaves_unmeasured_ones_unverified():
    m = np.zeros((100, 60), bool); m[10:90, 20:40] = True
    out = AG.check(_walk(), FPS, masks={"front": [m] * 3, "side": [m] * 3}, rendered={"front": [m] * 3, "side": [m] * 3})
    ids = {g["id"] for g in out["gates"]}
    assert {"G-OUT-front", "G-OUT-side", "G-LEGS", "G-FOOT-SLIDE", "G-FOOT-PLANT"} <= ids
    assert "G-TWIST" in out["unverified"] and "G-TOE" in out["unverified"] and out["passed"] is True
    assert out["complete"] is False


# ---------------------------------------------------------------------------------------------------------- loop and export
def _quat(axis_deg):
    a = np.radians(axis_deg) / 2
    return np.array([np.cos(a), 0.0, np.sin(a), 0.0])


def _take(strides=4, drift_deg=0.0, bones=3):
    """Per-frame bone quaternions with a periodic swing, optionally drifting by drift_deg per stride."""
    n = PERIOD * strides + 1
    q = np.zeros((n, bones, 4))
    for t in range(n):
        for b in range(bones):
            q[t, b] = _quat(25 * np.sin(2 * np.pi * t / PERIOD + b) + drift_deg * t / PERIOD)
    return q


def test_period_detection_finds_the_stride_period_from_the_pose_signal():
    q = _take()
    assert AG.detect_period(q) == pytest.approx(PERIOD, abs=0.3)


def test_phase_averaging_makes_a_periodic_loop_whose_last_frame_leads_into_the_first():
    q = _take(drift_deg=0.0)
    loop = AG.phase_average_loop(q, PERIOD, n_frames=PERIOD)
    assert loop["strides"] == 4 and loop["frames"].shape == (PERIOD, 3, 4)
    wrap = AG.rotation_delta_deg(loop["frames"][-1], loop["frames"][0])
    step = np.median([AG.rotation_delta_deg(a, b).max() for a, b in zip(loop["frames"], loop["frames"][1:])])
    assert wrap.max() <= step * 1.5


def test_loop_gates_a_clean_take_passes_and_a_drifting_one_fails_g_loop_with_the_number():
    ok = AG.loop_gates(_take(), PERIOD, root_y_m=[SPEED / FPS * t for t in range(PERIOD * 4 + 1)], fps=FPS, planted_foot_speed_mps=SPEED,
                       skeleton={"bones": ["a", "b", "c"], "reference": ["a", "b", "c"]})
    assert ok["gates"]["G-LOOP"]["passed"] and ok["gates"]["G-SPEED"]["passed"] and ok["gates"]["G-STRIDES"]["passed"] and ok["gates"]["G-SKEL"]["passed"]
    bad = AG.loop_gates(_take(drift_deg=3.4), PERIOD, root_y_m=[SPEED / FPS * t for t in range(PERIOD * 4 + 1)], fps=FPS, planted_foot_speed_mps=SPEED,
                        skeleton={"bones": ["a", "b", "c"], "reference": ["a", "b", "c"]})
    g = bad["gates"]["G-LOOP"]
    assert not g["passed"] and g["value"] == pytest.approx(3.4, abs=0.2) and "use more strides" in g["message"]


def test_speed_from_the_planted_foot_must_match_the_root_displacement_within_5_percent():
    root = [SPEED / FPS * t for t in range(PERIOD * 4 + 1)]
    off = AG.loop_gates(_take(), PERIOD, root_y_m=root, fps=FPS, planted_foot_speed_mps=SPEED * 1.2, skeleton={"bones": ["a"], "reference": ["a"]})
    assert not off["gates"]["G-SPEED"]["passed"]


def test_one_stride_is_refused_and_two_need_the_users_note():
    root = [SPEED / FPS * t for t in range(PERIOD * 2 + 1)]
    with pytest.raises(AG.GateError, match="a one-stride cycle hitches at the loop: need >= 2, 4 recommended"):
        AG.loop_gates(_take(strides=1), PERIOD, root_y_m=[SPEED / FPS * t for t in range(PERIOD + 1)], fps=FPS, planted_foot_speed_mps=SPEED, skeleton={"bones": ["a"], "reference": ["a"]})
    two = AG.loop_gates(_take(strides=2), PERIOD, root_y_m=root, fps=FPS, planted_foot_speed_mps=SPEED, skeleton={"bones": ["a"], "reference": ["a"]})
    assert not two["gates"]["G-STRIDES"]["passed"]
    ok = AG.loop_gates(_take(strides=2), PERIOD, root_y_m=root, fps=FPS, planted_foot_speed_mps=SPEED, skeleton={"bones": ["a"], "reference": ["a"]}, strides_note="the user accepted two strides")
    assert ok["gates"]["G-STRIDES"]["passed"]


def test_the_skeleton_gate_names_the_missing_bones_and_manny_is_refused_outright():
    root = [SPEED / FPS * t for t in range(PERIOD * 4 + 1)]
    g = AG.loop_gates(_take(), PERIOD, root_y_m=root, fps=FPS, planted_foot_speed_mps=SPEED, skeleton={"bones": ["a", "b"], "reference": ["a", "b", "c"]})["gates"]["G-SKEL"]
    assert not g["passed"] and "1 of 3 bones missing from the take (c)" in g["message"]
    unknown = AG.loop_gates(_take(), PERIOD, root_y_m=root, fps=FPS, planted_foot_speed_mps=SPEED, skeleton={"bones": ["a"]})["gates"]["G-SKEL"]
    assert unknown["passed"] is None and "UNVERIFIED" in unknown["message"]
    with pytest.raises(AG.GateError, match="Manny animations stay on Manny-based rigs"):
        AG.check_target_skeleton("SK_Mannequin")
    AG.check_target_skeleton("metahuman_base_skel")


def test_a_take_that_failed_the_check_is_refused_before_any_loop_work():
    with pytest.raises(AG.GateError, match="run anim_check; G-LEGS failed"):
        AG.require_check({"passed": False, "gates": [{"id": "G-LEGS", "passed": False}]})
    AG.require_check({"passed": True, "gates": []})


def test_the_controls_prove_the_measures_can_fail_on_this_very_take():
    good = AG.controls(_walk(), FPS)
    assert good["leg_swap_share"] <= 0.05 and good["leg_swap_ok"] is True
    assert good["slide_falsifier_cm"] > 1.0 and good["slide_falsifier_ok"] is True
    flat = np.zeros((40, len(MV.JOINTS), 3)); flat[:, :, 2] = 0.0
    assert AG.controls(flat, FPS)["leg_swap_ok"] is False                    # a take with no lifted foot cannot show the measure discriminates: not a pass


def test_a_check_whose_controls_cannot_fail_does_not_pass_even_when_every_gate_number_does(monkeypatch):
    m = np.zeros((100, 60), bool); m[10:90, 20:40] = True
    args = dict(masks={"front": [m], "side": [m]}, rendered={"front": [m], "side": [m]})
    assert AG.check(_walk(), FPS, **args)["passed"] is True
    monkeypatch.setattr(AG, "controls", lambda J, fps: {"leg_swap_ok": False, "slide_falsifier_ok": True, "leg_swap_share": 0.9, "slide_falsifier_cm": 5.0})
    out = AG.check(_walk(), FPS, **args)
    assert out["controls_ok"] is False and out["passed"] is False and all(g["passed"] for g in out["gates"])
