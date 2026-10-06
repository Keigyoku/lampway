# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""choices_migration.md test 9, client half: an engine naming a Studio action id (a Choices option, ``studio:meshy.remesh``) answers with
that action for the owner's approval and clicks nothing."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src/scripts"))


def test_a_studio_action_id_answers_for_approval_and_clicks_nothing():
    from mixar.modules.lampway_tools.features import common as C
    out = C.studio_slot("retopo", "studio:meshy.remesh")
    assert out["ok"] is False and out["needs_approval"] is True and out["studio_action"] == "meshy.remesh" and out["studio"] == "meshy"
    assert "studio_plan" in out["how"]
    legacy = C.studio_slot("uv", "studio:tripo")
    assert legacy["studio_action"] == "tripo.uv.unwrap"
