# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 05: one vocabulary for agent state (DESIGN.md 7 and 13) drawn by one painter, and Parallel Agents cards that show the
clock they keep instead of a simulated progress light. The ring is the state, not the worker; nothing animates for working."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EDITORS = ROOT / "src/source/blender/editors"
SPARK = EDITORS / "space_agent_bubble/agent_ui_pill_cat.cc"
DRAW = EDITORS / "space_view3d/view3d_agent_panel_draw.cc"
SYNC = EDITORS / "space_view3d/view3d_agent_panel_sync.cc"
HEADER = EDITORS / "space_view3d/view3d_agent_panel.hh"


def test_card_statuses_cover_the_seven_states_in_the_order_cpp_reads():
    from mixar.modules.agent_panel.core import cards
    assert cards.STATUSES == ("PENDING", "RUNNING", "DONE", "FAILED", "BLOCKED", "PAUSED")
    enum = re.search(r"enum class AgentCardStatus \{(.*?)\};", HEADER.read_text(encoding="utf-8"), re.S)[1]
    assert re.findall(r"(\w+) = (\d)", enum) == [("Pending", "0"), ("Running", "1"), ("Done", "2"), ("Failed", "3"),
                                                  ("Blocked", "4"), ("Paused", "5")]


def test_a_todo_item_carries_what_it_needs_and_why():
    from mixar.modules.agent_panel.core import cards
    recs = cards._normalize([
        {"id": "a", "text": "Texture the lantern", "status": "IN_PROGRESS", "needs": "answer"},
        {"id": "b", "text": "Bake", "status": "IN_PROGRESS", "waiting_on": "OpenRouter quota"},
        {"id": "c", "text": "Retopo", "status": "FAILED", "reason": "OpenRouter refused: session cap $3.00 reached"},
        {"id": "d", "text": "Rig", "status": "DONE"},
    ])
    assert [r["status"] for r in recs] == ["BLOCKED", "PAUSED", "FAILED", "DONE"]
    assert recs[0]["needs"] == "answer" and recs[1]["waiting_on"] == "OpenRouter quota"
    assert recs[2]["reason"].startswith("OpenRouter refused") and recs[3]["reason"] == ""


def test_overflow_label_counts_by_state():
    from mixar.modules.agent_panel.core import cards
    statuses = ["BLOCKED", "RUNNING", "FAILED", "RUNNING", "RUNNING", "DONE", "PAUSED"]
    assert cards.overflow_label(statuses, visible=3) == "4 more: 2 working, 1 done, 1 waiting"
    assert cards.overflow_label(statuses[:3], visible=3) == ""


def test_cards_never_draw_simulated_progress():
    draw = DRAW.read_text(encoding="utf-8")
    assert "progress" not in draw.split("void draw_card", 1)[1].split("\nvoid draw_chevron", 1)[0]
    assert "progress_tint" not in draw
    assert "card.progress =" not in SYNC.read_text(encoding="utf-8")


def test_the_card_draws_its_clock_and_a_reason_when_it_failed():
    body = DRAW.read_text(encoding="utf-8").split("void draw_card", 1)[1].split("\nvoid draw_chevron", 1)[0]
    assert "seen_running_at" in body, "the clock the mirror keeps is drawn"
    assert 'IFACE_("failed: no reason given")' in body, "a failed card is never blank"


def test_the_spark_reads_the_theme_and_never_animates():
    body = SPARK.read_text(encoding="utf-8").split("static void draw_spark(", 1)[1].split("\n}\n", 1)[0]
    assert not re.search(r"\b0\.\d{3}f\s*,\s*0\.\d{3}f\s*,\s*0\.\d{3}f", body), "colours come from the theme, not literals"
    assert "BLI_time_now_seconds" not in body, "only egress moves: the working flame is retired (F10)"
    assert "style.ring" not in body, "the ring is the state, not the worker (F9)"
