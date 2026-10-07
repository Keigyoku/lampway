# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cloud audit F23 in the real build: the first-run setup walked by real clicks on Continue. Every step's words are whole
(no label cut to an ellipsis); Continue stays where it was, so the click that pressed it never lands on Back; and only the
current step is on screen."""

import harness


def _overlap(a, b):
    return a and b and a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]


def test_setup_keeps_continue_in_place_and_its_words_whole(tmp_path):
    steps = harness.run_state("onboarding_steps", tmp_path)["facts"]["steps"]
    assert [s["step"] for s in steps] == [2, 3, 4], steps
    for s in steps:
        assert s["shown"] == [s["step"]], ("only the current step is drawn", s["step"], s["shown"])
        cut = [t for t, _rect, _w in s["labels"] if t.endswith("…")]
        assert cut == [], ("a label cut short", s["step"], cut)
    assert steps[0]["continue"] == steps[1]["continue"] == steps[2]["continue"], [s["continue"] for s in steps]
    for before, after in zip(steps, steps[1:]):
        assert not _overlap(before["continue"], after["back"]), ("Back sits where Continue was", before["continue"], after["back"])
