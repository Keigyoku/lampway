# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04 in the real build: in the chat window, the question that waits for you has its primary choice lit in
the accent (the one flame on screen)."""

import harness


def test_the_waiting_question_lights_its_primary_choice(tmp_path):
    report = harness.run_state("chat_face", tmp_path)
    assert report["facts"]["island"], report["facts"]
    assert "primary_choice" in report["surfaces"], report["facts"]
    assert harness.token_failures(report) == [], report["surfaces"]
