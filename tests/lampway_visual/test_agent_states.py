# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 05 in the window: the Spark's ring is the state's colour (not the worker's), from the theme; the chevron counts the hidden cards
by state."""

import harness


def test_needs_you_working_and_failed_rings(tmp_path):
    report = harness.run_state("agent_cards_a", tmp_path)
    assert harness.token_failures(report) == [], report["surfaces"]
    assert report["facts"]["chevron"] == "4 more: 2 working, 1 done, 1 waiting", report["facts"]
    assert report["facts"]["visible"] == ["Lantern texture", "Brass frame", "Glass shader"]


def test_paused_done_and_queued_rings(tmp_path):
    report = harness.run_state("agent_cards_b", tmp_path)
    assert harness.token_failures(report) == [], report["surfaces"]
