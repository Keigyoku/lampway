# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_pose preserves decisions for absent numerical DOF tables; the accepted complete helmet table and measured chest route are available."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))
from mixar.modules.lampway_tools import posing  # noqa: E402


def test_each_unruled_kind_is_a_named_decision_with_the_proposed_ranges_marked_unverified():
    for kind in ("waist", "boots", "gauntlets"):
        out = posing.fit_pose(kind)
        d = out["needs_decision"]
        assert out["ok"] is False and d["what"] == f"fit_pose degrees of freedom for {kind}" and d["proposal"] and "[UNVERIFIED]" in d["proposal_status"]
        assert "pose the body to the piece" in d["why"]


def test_the_chest_is_routed_to_pose_clearance_and_an_unknown_kind_is_refused():
    out = posing.fit_pose("chest")
    assert out["route"] == "pose_clearance" and "needs_decision" not in out
    try:
        posing.fit_pose("cape")
    except ValueError as e:
        assert "chest | helmet | waist | boots | gauntlets" in str(e)
    else:
        raise AssertionError("an unknown kind must be refused")


def test_helmet_uses_the_captain_accepted_complete_proposal():
    out = posing.fit_pose("helmet")
    assert out["ok"] and out["route"] == "pose_solve" and out["table"] == posing.HELMET
    assert "needs_decision" not in out
