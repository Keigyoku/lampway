# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 13 in the real build: the one spend card, waiting and in the five states a spend can end in."""

import pytest

import harness

WANT = {
    "waiting": ["Higgsfield video: a 5-second loop of the lantern, 720p", "planned by the agent, only your click spends",
                "18 credits\x1fquoted", "this job 18 of 40\x1f0.0000\x1f0.4500\x1f0", "spent today 31.5 + 18 of 200\x1f0.1575\x1f0.0900\x1f0",
                "Spend 18 credits", "Not now", "Only your click spends. Enter does nothing here."],
    "over_job_cap": ["Refused before sending: over the per-job cap"],
    "past_cap": ["Past today's cap"],
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
    if state == "waiting":
        assert report["facts"]["variants"] == ["ACCENT"], report["facts"]
    assert harness.token_failures(report) == [], report["surfaces"]


def test_spend_in_the_tab_opens_the_card(tmp_path):
    report = harness.run_state("spend_from_tab", tmp_path)
    assert "Spend 18 credits" in report["facts"]["texts"], report["facts"]
