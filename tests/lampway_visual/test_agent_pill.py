# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The floating agent pill is a preference, off by default (the captain; facelift 04/05), in the real build."""

import harness


def test_the_pill_is_off_by_default_the_chip_brings_the_chat_back_and_the_preference_restores_it(tmp_path):
    facts = harness.run_state("agent_pill", tmp_path)["facts"]
    steps = {s["tag"]: s for s in facts["steps"]}
    island = lambda s: [c for c in s["children"] if c[2] == 1]   # noqa: E731  the chat's window has its body
    pill = lambda s: [c for c in s["children"] if c[2] == 0]     # noqa: E731  the pill's window is a header only
    start = steps["startup, pill off"]
    assert island(start) and not pill(start), facts
    closed = steps["after Ctrl+Shift+B (closes)"]
    assert closed["children"] == [] and closed["topbar_chip"], facts
    reopened = steps["after Ctrl+Shift+B again (opens)"]
    assert island(reopened) and not pill(reopened) and not reopened["topbar_chip"], facts
    on = steps["pill turned on, chat open"]
    assert island(on) and pill(on), facts
    assert pill(steps["pill on, minimised"]), facts
    assert not facts.get("exc"), facts
