# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 11 in the real build: a blind set of four opens in its own window, one view per model in local view, in Wire,
each overlay carrying its alias and "name hidden" only."""

import harness


def test_four_views_in_their_own_window(tmp_path):
    facts = harness.run_state("compare_window", tmp_path)["facts"]
    assert facts["window"] and facts["scene"] == "LW_Compare", facts
    views = [v for v in facts["views"] if v["overlay"]]
    assert len(views) == 4, facts
    assert all(v["local"] and v["wire"] for v in views), facts
    assert sorted(v["overlay"][0] for v in views) == ["A", "B", "C", "D"] and all(v["overlay"][1] == "name hidden" for v in views), facts
    widths = [v["width"] for v in views]
    assert max(widths) - min(widths) <= 2, f"one column each: {widths}"
