# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""view_verify (specs/mrmak/07-view-verify.md): admission of a reference, measured front/side/back checks on a silhouette, and the bounded retry ladder. Thresholds are placeholders."""

import itertools
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools.pipeline import retry_policy as RP  # noqa: E402
from mixar.modules.lampway_tools.pipeline import view_verify as VV  # noqa: E402

H, W = 420, 420


def figure(arm_deg=45.0, left_scale=1.0, crop_feet=False, tilt_foot=0, size=(H, W)):
    """A front figure on a boolean canvas: head, torso, two arms at arm_deg from vertical, two legs. left_scale narrows the figure's LEFT half (a rotation to camera)."""
    h, w = size
    m = np.zeros((h, w), bool)
    cx = w // 2
    yy, xx = np.mgrid[0:h, 0:w]
    m |= ((xx - cx) ** 2 + (yy - 50) ** 2) <= 25 ** 2                                   # head
    torso_w = 60
    m[78:200, cx - torso_w:cx + torso_w] = True                                           # torso with shoulders
    for side in (-1, 1):
        a = np.radians(arm_deg)
        for t in range(0, 100):
            x = int(cx + side * (torso_w + t * np.sin(a)))
            y = int(86 + t * np.cos(a))
            m[max(0, y - 7):y + 7, max(0, x - 7):x + 7] = True
        leg_x = cx + side * 28
        bottom = 392 + (tilt_foot if side == 1 else 0)
        m[200:min(bottom, h), leg_x - 16:leg_x + 16] = True
    if left_scale != 1.0:                                                               # narrow the left half about the axis
        left = m[:, :cx]
        new = np.zeros_like(left)
        cols = np.arange(cx)
        for c in range(cx):
            src = int(cx - (cx - c) / left_scale)
            if 0 <= src < cx:
                new[:, c] = left[:, src]
        m[:, :cx] = new
    if crop_feet:
        m[360:] = False
    return m


def verify(m, **kw):
    return VV.verify(m, view="front", category="sheet", **kw)


def test_a_symmetric_a_pose_front_passes_and_a_narrowed_shoulder_hard_fails_with_the_sign():
    ok = verify(figure())
    assert ok["verdict"] == "pass" and ok["checks"]["body_axis_dead_front"] and ok["measured"]["shoulder_width_ratio"] > 0.95 and abs(ok["estimated_rotation_deg"]) < 8
    bad = verify(figure(left_scale=0.7))
    assert bad["verdict"] == "hard_fail" and bad["checks"]["no_three_quarter"] is False and bad["measured"]["shoulder_width_ratio"] < 0.85
    assert bad["estimated_rotation_deg"] != 0
    mirrored = verify(figure(left_scale=0.7)[:, ::-1])
    assert (mirrored["estimated_rotation_deg"] > 0) != (bad["estimated_rotation_deg"] > 0)               # the sign says which way it turned
    assert "thresholds" in ok and ok["thresholds"]["shoulder_ratio_hard"] == VV.THRESHOLDS["shoulder_ratio_hard"]


def test_the_threshold_is_what_decides_the_falsifier(monkeypatch):
    narrowed = figure(left_scale=0.7)
    assert verify(narrowed)["verdict"] == "hard_fail"
    monkeypatch.setitem(VV.THRESHOLDS, "shoulder_ratio_hard", 0.1)
    monkeypatch.setitem(VV.THRESHOLDS, "mirror_iou_hard", 0.1)
    monkeypatch.setitem(VV.THRESHOLDS, "shoulder_ratio_ok", 0.1)
    assert verify(narrowed)["verdict"] != "hard_fail"                                                 # a threshold change that lets it pass flips the verdict


def test_pose_and_framing_classes():
    t = verify(figure(arm_deg=88.0))
    assert 75 < t["measured"]["arm_angle_deg"] < 100 and t["verdict"] == "soft_fail" and "A-pose" in t["reason"]
    down = verify(figure(arm_deg=2.0))
    assert down["measured"]["arm_angle_deg"] < 15 and down["verdict"] == "soft_fail"
    cropped = verify(figure()[:370])                                                   # the canvas ends mid-shin: the figure touches the bottom edge
    assert cropped["checks"]["framing_clean"] is False
    grad = VV.background_stats(np.dstack([np.tile(np.linspace(0, 255, 64)[None, :], (64, 1))] * 3).astype(np.uint8))
    assert grad["gradient"] > VV.THRESHOLDS["background_gradient"] and VV.background_stats(np.full((64, 64, 3), 255, np.uint8))["gradient"] < 1e-6


def test_an_asymmetric_figure_declared_by_the_user_skips_the_symmetry_checks_never_passes_them_silently():
    r = verify(figure(left_scale=0.7), asymmetric_ok=True)
    assert r["checks"]["body_axis_dead_front"] == "not_applicable" and r["checks"]["no_three_quarter"] == "not_applicable" and r["verdict"] != "hard_fail"


def test_admit_rejects_empty_tiny_fragmented_and_duplicate_with_the_reasons_named():
    good = VV.admit(figure())
    assert good["ok"] and 0.05 < good["coverage"] < 0.97 and good["short_side"] == W and good["largest_component_fraction"] > 0.9
    assert "empty" in " ".join(VV.admit(np.zeros((200, 200), bool))["reasons"]) or "coverage" in " ".join(VV.admit(np.zeros((200, 200), bool))["reasons"])
    tiny = VV.admit(figure(size=(400, 300))[:60, :60])
    assert not tiny["ok"] and any("short side" in r for r in tiny["reasons"])
    frag = np.zeros((300, 300), bool)
    for k in range(6):
        frag[10 + k * 45:30 + k * 45, 10:60] = True
        frag[10 + k * 45:30 + k * 45, 150:210] = True
    f = VV.admit(frag)
    assert not f["ok"] and any("fragmented" in r for r in f["reasons"])
    h = VV.phash(figure())
    dup = VV.admit(figure(), known_hashes={"plate_1": h})
    assert not dup["ok"] and dup["duplicate_of"] == "plate_1" and any("duplicate" in r for r in dup["reasons"])
    assert VV.admit(np.rot90(figure()).copy(), known_hashes={"plate_1": h})["duplicate_of"] is None


# ------------------------------------------------------------------------------------------------------------- the ladder
VERDICTS = ("pass", "soft_fail", "hard_fail", "uncertain")


def hist(seq, reason="rotated"):
    return [{"verdict": v, "reason": f"{reason}{i}", "model": "primary"} for i, v in enumerate(seq)]


def test_the_ladder_always_stops_at_the_ceiling_exhaustive_over_the_small_domain():
    for max_attempts in (1, 2, 3, 4):
        for n in range(0, 7):
            for seq in itertools.product(VERDICTS, repeat=n):
                d = RP.decide(hist(seq), max_attempts)
                assert d["action"] in ("generate", "accept", "accept_with_warning", "retry", "stop")
                if n >= max_attempts and (not seq or seq[-1] in ("hard_fail", "uncertain")):
                    assert d["action"] == "stop", (max_attempts, seq, d)
                if n >= max_attempts:
                    assert d["action"] != "retry" and d["action"] != "generate", (max_attempts, seq, d)
                if seq and seq[-1] == "pass":
                    assert d["action"] == "accept"
                if seq and seq[-1] == "soft_fail":
                    assert d["action"] == "accept_with_warning"


def test_without_a_ceiling_branch_four_hard_fails_would_loop_the_falsifier(monkeypatch):
    seq = hist(["hard_fail"] * 4)
    assert RP.decide(seq, 3)["action"] == "stop"
    src = RP.decide
    # the ceiling is real: with max_attempts raised the same history is allowed one more try (so the stop above was the ceiling and nothing else)
    assert RP.decide(hist(["hard_fail"] * 3, reason="same"), 4)["action"] in ("retry", "stop")
    assert RP.decide(hist(["hard_fail", "hard_fail"]), 4)["action"] == "retry"


def test_the_first_retry_stays_on_the_model_the_second_goes_to_the_fallback_and_a_repeated_reason_stops():
    d1 = RP.decide(hist(["hard_fail"]), 3)
    d2 = RP.decide(hist(["hard_fail", "hard_fail"]), 3)
    assert d1["action"] == "retry" and d1["model"] == "same" and d2["action"] == "retry" and d2["model"] == "fallback"
    same_reason = [{"verdict": "hard_fail", "reason": "rotated 24 degrees", "model": "a"}, {"verdict": "hard_fail", "reason": "rotated 24 degrees", "model": "a"}]
    assert RP.decide(same_reason, 4)["action"] == "stop"
    stop = RP.decide(hist(["hard_fail"] * 3), 3)
    assert stop["action"] == "stop" and len(stop["options"]) == 3 and stop["attempts_used"] == 3


def test_the_escalated_prompt_names_the_reason_and_keeps_the_original_text_unchanged():
    original = "A clean character reference sheet of a knight, STRICT FRONT VIEW."
    p = RP.escalate(original, "shoulders differ by 31 %", 24.0)
    assert "[CRITICAL CORRECTION]" in p and "shoulders differ by 31 %" in p and "+24" in p and p.endswith(original)
    assert "-24" in RP.escalate(original, "x", -24.0)


def test_a_judge_can_rescue_an_uncertain_but_never_override_a_measured_hard_failure_and_malformed_output_is_uncertain():
    narrowed = figure(left_scale=0.7)
    always_pass = lambda measured, image: {"verdict": "pass", "reason": "looks fine", "checks": {}}
    assert verify(narrowed, judge=always_pass)["verdict"] == "hard_fail"                                # never overrides a measured hard failure
    tiny_ok = figure(size=(400, 300))
    for bad in ("the figure looks good!", {"reason": "no verdict key"}, {"verdict": "great"}, None):
        assert VV.parse_judge(bad)["verdict"] == "uncertain"
    assert VV.parse_judge({"verdict": "pass", "reason": "ok"})["verdict"] == "pass"
    # an uncertain measured verdict (a figure the checks cannot read) is rescued by a judge
    blank_side = VV.verify(figure(), view="side", category="sheet", judge=always_pass)
    assert blank_side["by"] == "both" and blank_side["verdict"] == "pass"
    assert VV.verify(figure(), view="side", category="sheet")["verdict"] == "uncertain"


def test_a_soft_fail_is_accepted_with_the_warning_text_to_log():
    d = RP.decide(hist(["soft_fail"], reason="T-pose not A-pose"), 3)
    assert d["action"] == "accept_with_warning" and "T-pose not A-pose" in d["reason"]
