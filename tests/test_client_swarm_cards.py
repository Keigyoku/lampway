# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""S3 card turns render independently of the unit's Hermes or observed pane turn."""
import pytest

from test_byoa_island_view import world, started, event, SID  # noqa: F401 - shared client ingress harness
from mixar.modules.space_mixie_chat.core import byoa_view as BV
from mixar.modules.space_mixie_chat.core import turn_events as TE

CARD = "swarm_fake_1234"
BUBBLE = "swarm-fake-workers"
ROWS = [{"id": "worker1", "text": "Build a chair", "status": "failed"}]
RETRY = [{"label": "Retry failed tasks", "value": "continue", "style": "primary"}]


def start_card():
    TE._consume("agent.turn.started", {"session_id": SID, "turn_id": CARD, "run_id": CARD,
                                      "observed": True, "swarm": "fake", "pane": "pane1", "user_text": ""})


def card_event(seq, payload):
    TE._consume("agent.turn.event", event(seq, payload, CARD))


def finish_card():
    card_event(2, {"bubble_id": BUBBLE, "todo": ROWS, "actions": RETRY})
    card_event(3, {"type": "turn_end", "status": "completed", "run_id": CARD})
    TE._consume("agent.turn.ended", {"session_id": SID, "turn_id": CARD, "last_seq": 3})


def assert_no_turn_side_effects(scene, seen, saved):
    assert seen["states"] == [] and seen["runs"] == [] and seen["executor"] == []
    assert scene["mixie_ws_resume"] == saved
    assert scene["lampway_byoa_cursor"] == {"pane": "pane1", "offset": 812}


def saved_cursors(scene):
    saved = {"session_id": SID, "turn_id": "old-hermes", "cursor": 7, "complete": True,
             "run_id": "open-run", "run_open": True, "state": "IDLE"}
    scene["mixie_ws_resume"] = saved.copy()
    scene["lampway_byoa_cursor"] = {"pane": "pane1", "offset": 812}
    return saved


def test_mode1_between_hermes_turns_renders_cards_and_retry_without_taking_the_run(world):
    scene, seen = world
    scene.lampway_agent_mode = "runtime"
    scene.mixie_run_open, scene.mixie_run_id = True, "open-run"
    saved = saved_cursors(scene)
    start_card()
    assert CARD in TE._turns, "a Mode 1 tab must accept the observed swarm card turn"
    card_event(0, {"type": "run_status", "run_id": CARD, "status": "in_progress"})
    # End arrives before its rows: ordered rendering waits for the missing slot.
    card_event(3, {"type": "turn_end", "status": "completed", "run_id": CARD})
    assert not TE._turns[CARD].complete
    card_event(1, {"bubble_id": BUBBLE, "todo": ROWS})
    finish_card()
    assert seen["slots"] == [{"bubble_id": BUBBLE, "todo": ROWS},
                              {"bubble_id": BUBBLE, "todo": ROWS, "actions": RETRY}]
    assert TE._turns[CARD].complete and TE._turns[CARD].cursor == 3
    card_event(2, {"bubble_id": BUBBLE, "actions": RETRY})
    assert len(seen["slots"]) == 2, "duplicate delivery does not render again"
    assert_no_turn_side_effects(scene, seen, saved)
    assert (scene.mixie_run_open, scene.mixie_run_id, scene.mixie_chat_state) == (True, "open-run", "IDLE")
    assert scene.mixie_chat_is_busy is False and SID not in BV.ACTIVITY
    assert not scene.mixie_chat_messages and seen["finalized"] == 0


@pytest.mark.parametrize("pane_finishes_first", [False, True])
def test_mode2_card_activity_never_overwrites_interleaved_pane_activity(world, pane_finishes_first):
    scene, seen = world
    saved = saved_cursors(scene)
    TE._consume("agent.turn.started", started())
    assert scene.mixie_chat_is_busy and BV.ACTIVITY[SID] == "working"
    start_card()
    card_event(0, {"type": "run_status", "run_id": CARD, "status": "in_progress"})
    card_event(1, {"bubble_id": BUBBLE, "todo": ROWS})
    if pane_finishes_first:
        TE._consume("agent.turn.event", event(0, {"type": "turn_end", "status": "completed", "offset": 900}))
        assert not scene.mixie_chat_is_busy and BV.ACTIVITY[SID] == "idle"
        card_event(2, {"type": "run_status", "run_id": CARD, "status": "in_progress"})
        assert not scene.mixie_chat_is_busy, "a late card update cannot relight an idle pane"
        # The terminal card event follows the extra status frame.
        card_event(3, {"bubble_id": BUBBLE, "todo": ROWS, "actions": RETRY})
        card_event(4, {"type": "turn_end", "status": "completed"})
    else:
        finish_card()
        assert scene.mixie_chat_is_busy and BV.ACTIVITY[SID] == "working", "card completion must leave the pane working"
        assert seen["finalized"] == 0, "card completion must not finalize the pane's live steps or loaders"
        assert_no_turn_side_effects(scene, seen, saved)
        TE._consume("agent.turn.event", event(0, {"type": "turn_end", "status": "completed", "offset": 900}))
    assert not scene.mixie_chat_is_busy and BV.ACTIVITY[SID] == "idle"
    assert seen["finalized"] == 1 and scene["lampway_byoa_cursor"]["offset"] == 900
    assert scene["mixie_ws_resume"] == saved and seen["states"] == [] and seen["runs"] == []


@pytest.mark.parametrize("saved_run", [False, True])
def test_reconnect_discovers_a_missed_card_start_even_without_a_scene_turn_cursor(world, monkeypatch, saved_run):
    import bpy
    from mixar.modules.space_mixie_chat.core import turn_resume
    scene, seen = world
    scene.lampway_agent_mode = "runtime"
    if saved_run:
        saved_cursors(scene)
    monkeypatch.setattr(bpy.data, "scenes", [scene])
    monkeypatch.setattr(turn_resume, "check_orphaned_turns", lambda: None)
    monkeypatch.setattr(BV, "observe_all", lambda: None)
    attaches = []
    monkeypatch.setattr(TE, "_request_replay", lambda turn: attaches.append((turn.turn_id, turn.cursor)))
    TE.reconnect()
    status_calls = [(params, cb) for method, params, cb in seen["calls"] if method == "agent.status"]
    assert status_calls and status_calls[-1][0] == {"session_ids": [SID]}, "cards must be discoverable on an idle fresh tab"
    start = {"session_id": SID, "turn_id": CARD, "run_id": CARD, "observed": True,
             "swarm": "fake", "pane": "pane1", "user_text": ""}
    status_calls[-1][1]({"turns": {}, "swarm_cards": {SID: [start]}})
    assert CARD not in TE._turns, "the callback queues metadata; scene work stays on the main thread"
    TE.drain_session(SID)
    assert CARD in TE._turns and attaches == [(CARD, -1)]
    assert seen["states"] == [] and seen["runs"] == [] and not scene.mixie_chat_is_busy
    card_event(0, {"type": "run_status", "status": "in_progress", "run_id": CARD})
    card_event(1, {"bubble_id": BUBBLE, "todo": ROWS})
    finish_card()
    assert TE._turns[CARD].complete
    status_calls[-1][1]({"turns": {}, "swarm_cards": {SID: [start]}})
    TE.drain_session(SID)
    assert attaches == [(CARD, -1)], "a completed card is not replayed again on the same client"


def test_a_live_card_does_not_block_a_new_hermes_turn_or_finish_it(world, monkeypatch):
    scene, seen = world
    scene.lampway_agent_mode = "runtime"
    saved = saved_cursors(scene)
    start_card()
    card_event(0, {"type": "run_status", "status": "in_progress", "run_id": CARD})
    card_event(1, {"bubble_id": BUBBLE, "todo": ROWS})

    def begin(target, run_id):
        target.mixie_chat_state = "BUSY"
        target.mixie_run_id, target.mixie_run_open = run_id, True
    monkeypatch.setattr(TE, "_begin_scene_turn", begin)
    TE._consume("agent.turn.started", {"session_id": SID, "turn_id": "pane_new-hermes", "run_id": "hermes-run",
                                      "origin": "pane", "user_text": "Continue the chair"})
    assert "pane_new-hermes" in TE._turns and not TE._turns["pane_new-hermes"].observed
    finish_card()
    assert not TE._turns["pane_new-hermes"].complete
    assert (scene.mixie_chat_state, scene.mixie_run_id, scene.mixie_run_open) == ("BUSY", "hermes-run", True)
    assert_no_turn_side_effects(scene, seen, saved)
    assert seen["finalized"] == 0


@pytest.mark.parametrize("working", [False, True])
def test_cards_leave_a_screen_shown_panes_working_indicator_to_herdr(world, monkeypatch, working):
    scene, seen = world
    monkeypatch.setattr(BV, "_ensure_screen_timer", lambda: None)
    BV.apply_view({"session_id": SID, "view": "screen", "pane": "pane1", "screen": "> agent",
                   "agent_status": "working" if working else "idle"})
    start_card()
    card_event(0, {"type": "run_status", "status": "in_progress"})
    assert scene.mixie_chat_is_busy is working
    card_event(1, {"bubble_id": BUBBLE, "todo": ROWS})
    finish_card()
    assert scene.mixie_chat_is_busy is working and BV.ACTIVITY[SID] == ("working" if working else "idle")
    assert seen["finalized"] == 0


def test_a_lost_card_tail_does_not_finalize_or_stop_the_panes_live_turn(world):
    scene, seen = world
    saved = saved_cursors(scene)
    TE._consume("agent.turn.started", started())
    start_card()
    card_event(0, {"type": "resume_unavailable"})
    assert TE._turns[CARD].complete and not TE._turns["byoa-pane1-0"].complete
    assert scene.mixie_chat_is_busy and BV.ACTIVITY[SID] == "working"
    assert_no_turn_side_effects(scene, seen, saved)
    assert seen["finalized"] == 0
