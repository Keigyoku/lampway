# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 12 in the real build: "What leaves this machine" with a route sending, a refusal and a confirm row open."""

import harness


def test_the_window_with_sending_refused_and_a_confirm_row(tmp_path):
    report = harness.run_state("privacy_face", tmp_path)
    facts = report["facts"]
    texts = [b[1] for b in facts["buttons"]] + facts["labels"]
    assert "Sending now: fal.ai" in texts, facts
    assert "Let data leave for openrouter.ai?" in texts and "Let it leave" in texts, facts
    for way in ("Use OpenRouter, zero retention", "Run it here instead", "Allow this asset once (logged)"):
        assert way in texts, facts
    assert "confirm_button" in report["surfaces"], facts
    assert "on_switch" in report["surfaces"], facts   # sampled against an unlit token: the confirm row is the only lit thing
    assert harness.token_failures(report) == [], report["surfaces"]
