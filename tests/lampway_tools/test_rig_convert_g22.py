# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Canon 22's golden G22.2 on the ported converter: a canonical retarget between two profiles whose references are R04's source and target rests
reproduces canon 19's rule W_t = W_s R_s^-1 R_t on every R04 frame (the same rule, in canonical space), and the local copy (the falsifier) misses by
R04's 55.7 deg. G22.3 (a non-uniform scale refused) and G22.4 (1.05 s = 32 samples ending on the exact terminal 21/20) ride along."""

import json
import sys
from pathlib import Path

import numpy as np
import pytest

RC = Path(__file__).resolve().parents[2] / "src/scripts/mixar/modules/lampway_tools/rig_convert"
sys.path.insert(0, str(RC))
import animation_canon as ac  # noqa: E402

R04 = json.loads((Path(__file__).resolve().parents[2] / "docs" / "canon" / "goldens" / "R04_retarget" / "case.json").read_text())


def q_of(R):
    R = np.asarray(R, float)
    w = np.sqrt(max(0.0, 1 + np.trace(R))) / 2
    if w > 1e-6:
        return [(R[2, 1] - R[1, 2]) / (4 * w), (R[0, 2] - R[2, 0]) / (4 * w), (R[1, 0] - R[0, 1]) / (4 * w), w]
    i = int(np.argmax(np.diag(R)))
    j, k = (i + 1) % 3, (i + 2) % 3
    s = np.sqrt(max(0.0, 1 + R[i, i] - R[j, j] - R[k, k])) * 2
    q = [0.0, 0.0, 0.0, (R[k, j] - R[j, k]) / s]
    q[i], q[j], q[k] = s / 4, (R[j, i] + R[i, j]) / s, (R[k, i] + R[i, k]) / s
    return q


def tf(p, R):
    return {"translation": list(p), "rotation": q_of(R), "scale": [1, 1, 1]}


def profile(name, rests):
    bones = [{"name": "root", "parent": None, "bind": tf([0, 0, 0], np.eye(3)), "reference": tf([0, 0, 0], np.eye(3))},
             {"name": "A", "parent": "root", "bind": tf([0, 0, 1], rests["A"]), "reference": tf([0, 0, 1], rests["A"])},
             {"name": "B", "parent": "A", "bind": tf([0, 0, 1.3], rests["B"]), "reference": tf([0, 0, 1.3], rests["B"])}]
    return ac.make_profile(name, bones, basis=[0, 0, 0, 1], centimeters_per_unit=1)


def test_g22_2_canonical_retarget_equals_the_canon_19_rule_and_the_local_copy_misses():
    src, tgt = profile("source", R04["input"]["Rs_rest"]), profile("target", R04["input"]["Rt_rest"])
    frames = R04["expected"]["frames"]
    times = ac.sample_times(f"{(len(frames) - 1) / 30:.10f}")
    assert len(times) == len(frames)
    samples = [{"time": t, "pose": {"root": tf([0, 0, 0], np.eye(3)), "A": tf([0, 0, 1], f["Ws"]["A"]), "B": tf([0, 0, 1.3], f["Ws"]["B"])}}
               for t, f in zip(times, frames)]
    packet = ac.normalize(samples, src, duration=f"{(len(frames) - 1) / 30:.10f}", channels={})
    rules = {"map": {"root": "root", "A": "A", "B": "B"}, "reference_follow": [], "translation_scales": {"root": 1, "A": 1, "B": 1}, "anchors": {}}
    out = ac.adapt(ac.retarget(packet, tgt, rules), tgt)
    worst = 0.0
    for f, s in zip(frames, out):
        for b in ("A", "B"):
            want = np.asarray(f["Ws"][b]) @ np.asarray(R04["input"]["Rs_rest"][b]).T @ np.asarray(R04["input"]["Rt_rest"][b])
            assert np.allclose(want, f["Wt"][b], atol=1e-6), "the golden's own W_t is the canon 19 rule"
            got = ac.compare([{"time": [0, 1], "pose": {b: tf([0, 0, 0], want)}}], [{"time": [0, 1], "pose": {b: dict(s["pose"][b], translation=[0, 0, 0])}}])
            worst = max(worst, got["rotation_max_degrees"])
    assert worst < 1e-5, worst
    Rs, Rt = np.asarray(R04["input"]["Rs_rest"]["B"]), np.asarray(R04["input"]["Rt_rest"]["B"])
    local = max(np.degrees(np.arccos(np.clip((np.trace((Rt @ (Rs.T @ np.asarray(f["Ws"]["B"]))).T @ np.asarray(f["Wt"]["B"])) - 1) / 2, -1, 1)))
                for f in frames)                                                     # the golden measures the falsifier on bone B
    assert local == pytest.approx(R04["falsifier"]["local_copy_max_error_deg"], abs=1e-3)


def test_g22_3_a_non_uniform_scale_is_refused_and_g22_4_the_schedule_ends_on_the_exact_terminal():
    with pytest.raises(ValueError, match="non-uniform"):
        ac._transform({"translation": [0, 0, 0], "rotation": [0, 0, 0, 1], "scale": [1, 1.2, 1]})
    times = ac.sample_times("1.05")
    assert len(times) == 33 and times[-2] == [31, 30] and times[-1] == [21, 20] and times[0] == [0, 1]
