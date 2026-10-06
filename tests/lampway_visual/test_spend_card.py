# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 13 in the real build: the one spend card, waiting and in the five states a spend can end in."""

import pytest

import harness

WANT = {
    "waiting": ["Higgsfield video: a 5-second loop of the lantern, 720p", "planned by the agent, only your click spends", "18 credits",
                "quoted", "this job 18 of 40", "session 31.5 + 18 of 200", "Spend 18 credits", "Not now",
                "Only your click spends. Enter does nothing here."],
    "over_job_cap": ["Refused before sending: over the per-job cap"],
    "past_cap": ["Past the session cap"],
    "price_changed": ["The price changed: the old approval is void", "Spend 21 credits", "Spend at the new price"],
    "agent_tried": ["Agents can plan, never confirm"],
    "spent": ["Spent: job j9"],
}


@pytest.mark.parametrize("state", sorted(WANT))
def test_the_card(state, tmp_path):
    report = harness.run_state(f"spend_{state}", tmp_path)
    texts = report["facts"]["texts"]
    for text in WANT[state]:
        assert text in texts, (state, text, texts)
    if state not in ("waiting", "price_changed"):
        assert report["facts"]["spend"] == [], "a refused spend has no Spend button"
