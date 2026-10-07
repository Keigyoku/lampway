# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 03 in the window: the status bar in its three wire states, with and without a decision waiting, read from the build's own
QA dump of what it drew (the bar is fed a fake server answer; nothing reaches the network)."""

import pytest

import harness

CASES = {
    "status_local": {"wire": "local", "spend": "spent today $0.31 of $5.00"},
    "status_open": {"wire": "2 routes open", "spend": "spent today $0.31 of $5.00", "waiting": "1 waiting for you"},
    "status_sending": {"wire": "Sending to OpenRouter", "spend": "spent today $0.31 of $5.00", "waiting": "1 waiting for you"},
}


@pytest.mark.parametrize("state", sorted(CASES))
def test_the_status_bar_says_what_the_server_says(state, tmp_path):
    report = harness.run_state(state, tmp_path)
    assert report["facts"] == CASES[state], report["facts"]
    assert harness.token_failures(report) == [], report["surfaces"]
