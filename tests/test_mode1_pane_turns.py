# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1's pane in the island (docs/reports/agent-modes-spec.md A2, A3, Q15), the Client's half.

The server (``server/lampway_server/engine/front.py``) announces a turn the user typed in Lampway Agent's pane as
``agent.turn.started {origin: "pane", user_text}`` with a ``pane_<hex>`` turn id and a run of its own, streams it as ordinary
``agent.turn.event`` frames and ends it with ``agent.turn.ended``; its Blender calls are ``blender.execute_script`` with that turn
id in ``agent_ctx``. ``/new`` in the pane moves the unit to a new Hermes session: the tab's session id stays (it is the unit), and
the server says so with ``agent.pane.new_conversation {session_id, origin: "pane"}``.

What the Client does with them, driven through the real ``turn_events`` ingress, ``mode1_pane``, ``chat_history`` and
``checkpoint_store``, the real main-thread executor and the real socket dispatch, with the server's own frame shapes:

- a pane turn into a Mode 1 tab that is not in a turn of its own is the tab's turn, like an island turn: the user's bubble from
  ``user_text``, the run, BUSY, the executor's undo turn, the slots, the end; a stale one (a tab in Your agent mode, a tab already
  in a turn, an MCP operation) is ignored with a log line;
- a script whose turn id is a pane turn's runs only while that turn is live in the tab; an unknown or ended one is refused and
  nothing runs;
- the pane's ``/new`` files the old chat (its transcript and its checkpoints) in History under a new id, empties the island for the
  tab's same session id, fences the old conversation's late frames and adds one line saying so.

``bpy`` is a MagicMock; the scenes are fakes."""
import ast
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from mixar.modules.space_mixie_chat.core import mode1_pane as MP  # noqa: E402
from mixar.modules.space_mixie_chat.core import session as S  # noqa: E402
from mixar.modules.space_mixie_chat.core import turn_events as TE  # noqa: E402
from test_preview_deferral import deferral, executor, _fake_client  # noqa: E402,F401 - the main-thread executor's harness

CHAT = SCRIPTS / "mixar" / "modules" / "space_mixie_chat"
SID = "33333333-3333-4333-8333-333333333333"
TID = "pane_0123456789ab"
RUN = "7c1f8f2e-0d7e-4c55-9f0e-2c5e9a6b1d10"


# ------------------------------------------------------------------------------------------------ the server's frames (front.py)
def pane_started(tid=TID, run_id=RUN, user_text="tui says hi"):
    """``HermesFront._pane_turn``: ``agent.turn.started`` for a turn the island did not start."""
    return {"session_id": SID, "turn_id": tid, "run_id": run_id, "origin": "pane", "user_text": user_text}


def pane_events(tid=TID, run_id=RUN, text="Hello from the pane."):
    """The pane turn's journal, as ``TurnStream`` numbers it: run status, loader, a delta, the reply, ``_finish``'s tail."""
    bubble = f"{tid}:agent"
    return [
        {"type": "run_status", "run_id": run_id, "status": "in_progress"},
        {"bubble_id": bubble, "loader": {"visible": True, "texts": ["Thinking..."], "rotate_ms": 2000}},
        {"bubble_id": bubble, "ephemeral": {"append": text}},
        {"bubble_id": bubble, "content": {"set": text}},
        {"bubble_id": bubble, "loader": {"visible": False}, "ephemeral": {"clear": True}},
        {"type": "turn_end", "status": "completed", "run_id": run_id},
    ]


def event(seq, payload, tid=TID):
    return {"session_id": SID, "turn_id": tid, "seq": seq, "event": payload}


def script_ctx(tid=TID):
    """``AgentHub._blender_script``'s agent context for a call made in that turn (``HermesFront.call_tool``)."""
    return {"chat_session_id": SID, "turn_id": tid, "call_id": "eng_0123456789ab"}


NEW_CONVERSATION = {"session_id": SID, "origin": "pane"}


# ------------------------------------------------------------------------------------------------ fakes
_PROPS = {"sender": None, "text": None, "bubble_id": None, "content": None}


class Msg(SimpleNamespace):
    bl_rna = SimpleNamespace(properties=_PROPS)


class Msgs(list):
    def add(self):
        m = Msg(sender="", text="", bubble_id="", content="", delivery_hint="")
        self.append(m)
        return m

    def clear(self):
        del self[:]

    def remove(self, index):
        del self[index]


class FakeScene(dict):
    def __bool__(self):
        return True

    def __init__(self, **kw):
        super().__init__()
        self.name = "Scene"
        self.mixie_chat_state = "IDLE"
        self.mixie_run_open = False
        self.mixie_run_id = ""
        self.mixie_session_id = SID
        self.mixie_chat_messages = Msgs()
        self.mixie_chat_input = ""
        self.mixie_chat_user_id = ""
        self.lampway_agent_mode = "runtime"
        self.lampway_byoa_pane = ""
        for k, v in kw.items():
            setattr(self, k, v)


class Processor:
    """``queue_processor``'s event processor, recording what the ingress asks of it."""

    def __init__(self, seen):
        self.seen = seen

    def _handle_typed_payload(self, payload, scene):
        self.seen["typed"].append(payload)

    def _handle_agent_complete_internal(self, scene):
        self.seen["completed"] += 1

    def _clear_loader_bubbles(self, scene):
        self.seen["cleared"] += 1

    def _handle_agent_event_internal(self, event, scene):
        self.seen["slots"].append(event.data)

    def _redraw_ui(self):
        pass


@pytest.fixture
def world(monkeypatch, tmp_path):
    """One Mode 1 tab bound to the turn ingress; History and checkpoints on disk under tmp_path; side effects recorded."""
    scene = FakeScene()
    seen = {"states": [], "runs": [], "slots": [], "typed": [], "completed": 0, "cleared": 0, "executor": [], "placeholders": 0,
            "calls": [], "finalized": 0, "flushed": []}

    def set_state(sc, st):
        seen["states"].append(st)
        sc.mixie_chat_state = getattr(st, "name", str(st))

    def set_run(sc, run_id, open_, **_kw):
        seen["runs"].append((run_id, open_))
        sc.mixie_run_id, sc.mixie_run_open = run_id, bool(open_)

    monkeypatch.setattr(S.SessionManager, "set_state", staticmethod(set_state))
    monkeypatch.setattr(S.SessionManager, "set_run", staticmethod(set_run))
    from mixar.modules.space_mixie_chat.core import executor, message_helpers, queue_processor, slot_processor
    monkeypatch.setattr(executor, "get_executor", lambda: SimpleNamespace(
        begin_agent_turn=lambda s: seen["executor"].append(("begin", s)),
        end_agent_turn=lambda s=None: seen["executor"].append(("end", s))))

    def placeholder(sc):
        seen["placeholders"] += 1
        m = sc.mixie_chat_messages.add()
        m.sender, m.bubble_id = "AGENT", "temp_placeholder"

    monkeypatch.setattr(message_helpers, "add_turn_placeholder", placeholder)
    processor = Processor(seen)
    monkeypatch.setattr(queue_processor, "get_event_processor", lambda: processor)
    monkeypatch.setattr(slot_processor, "finalize_turn", lambda sc: seen.__setitem__("finalized", seen["finalized"] + 1))
    from mixar.modules.space_mixie_chat.core import main_thread_executor
    monkeypatch.setattr(main_thread_executor, "cleanup", lambda shutdown=False, session_id=None: seen["flushed"].append(session_id))
    monkeypatch.setattr(TE, "_resolve", lambda sid: scene if sid == scene.mixie_session_id else None)
    from mixar.modules.common.agent_rpc import client as rpc
    monkeypatch.setattr(rpc, "call", lambda method, params, cb: seen["calls"].append((method, params)))
    monkeypatch.setattr(TE, "_request_replay", lambda turn: None)
    import bpy
    monkeypatch.setattr(bpy.data, "filepath", "", raising=False)
    from mixar.modules.space_mixie_chat.core import chat_history, checkpoint_store
    monkeypatch.setattr(chat_history, "_mixar_home", lambda: str(tmp_path / "home"))
    monkeypatch.setattr(checkpoint_store, "checkpoints_root", lambda: str(tmp_path / "home" / "checkpoints"))
    chat_history.invalidate_cache()
    TE.reset()
    yield scene, seen
    TE.reset()
    chat_history.invalidate_cache()


def feed(turn_frames, tid=TID):
    for seq, payload in enumerate(turn_frames):
        TE._consume("agent.turn.event", event(seq, payload, tid))
    TE._consume("agent.turn.ended", {"session_id": SID, "turn_id": tid, "last_seq": len(turn_frames) - 1})


def users(scene):
    return [m.text for m in scene.mixie_chat_messages if m.sender == "USER"]


# ------------------------------------------------------------------------------------------------ a turn typed in the pane
def test_a_turn_typed_in_the_pane_is_the_tabs_turn_with_the_users_text_its_run_its_slots_and_its_end(world):
    scene, seen = world
    TE._consume("agent.turn.started", pane_started())
    assert users(scene) == ["tui says hi"], "the user's bubble, from the server's user_text"
    assert [m.sender for m in scene.mixie_chat_messages] == ["USER", "AGENT"] and seen["placeholders"] == 1
    assert seen["runs"] == [(RUN, True)] and [s.name for s in seen["states"]] == ["BUSY"]
    assert seen["executor"] == [("begin", SID)], "the executor's undo turn, as an island turn's"
    assert TE._turns[TID].pane is True and not TE._turns[TID].observed
    feed(pane_events())
    assert [p.get("content", {}).get("set") for p in seen["slots"] if p.get("content")] == ["Hello from the pane."]
    assert seen["completed"] == 1 and TE._turns[TID].complete
    assert scene["mixie_ws_resume"]["turn_id"] == TID, "the rendered cursor is kept like any Mode 1 turn's"


def test_a_resumed_pane_turn_with_no_user_text_adds_no_empty_bubble(world):
    scene, seen = world
    TE._consume("agent.turn.started", pane_started(user_text=""))
    assert users(scene) == [] and TID in TE._turns


def test_the_rest_of_a_turn_whose_question_the_pane_answered_joins_the_open_run_without_a_user_bubble(world):
    """``_open_pane_turn(close=q)``: the same run, so the island takes it as its continuation (already a wake-up)."""
    scene, seen = world
    scene.mixie_run_open, scene.mixie_run_id = True, RUN
    TE._consume("agent.turn.started", pane_started(tid="pane_continued0001", user_text=""))
    assert "pane_continued0001" in TE._turns and TE._turns["pane_continued0001"].pane is True
    assert users(scene) == []


@pytest.mark.parametrize("why", ["byoa", "busy", "turn_running"])
def test_a_stale_pane_turn_is_ignored_with_a_log_line_and_never_touches_the_tab(world, caplog, why):
    scene, seen = world
    if why == "byoa":
        scene.lampway_agent_mode, scene.lampway_byoa_pane = "byoa", "pane1"
    elif why == "busy":
        scene.mixie_chat_state = "BUSY"                 # an island send in flight, or an MCP operation (it sets BUSY)
    else:
        TE._turns["island-turn"] = TE.Turn(SID, "island-turn", "run-island")
    caplog.set_level(logging.INFO)
    TE._consume("agent.turn.started", pane_started())
    assert TID not in TE._turns and users(scene) == []
    assert seen["runs"] == [] and seen["states"] == [] and seen["executor"] == []
    assert any(TID in r.getMessage() and "ignored" in r.getMessage() for r in caplog.records), caplog.text


# ------------------------------------------------------------------------------------------------ its Blender calls
def test_a_script_runs_only_for_a_live_pane_turn_of_its_own_tab(world, caplog):
    scene, seen = world
    caplog.set_level(logging.INFO)
    unknown = MP.script_refusal(SID, script_ctx("pane_neverannounced"))
    assert unknown and unknown["success"] is False and unknown["error_type"] == "unknown_turn"
    assert any("pane_neverannounced" in r.getMessage() for r in caplog.records)
    TE._consume("agent.turn.started", pane_started())
    assert MP.script_refusal(SID, script_ctx()) is None
    assert MP.script_refusal("44444444-4444-4444-8444-444444444444", script_ctx()) is not None, "another tab's id"
    feed(pane_events())
    ended = MP.script_refusal(SID, script_ctx())
    assert ended and ended["error_type"] == "unknown_turn", "an ended turn runs nothing"
    assert MP.script_refusal(SID, {"chat_session_id": SID, "turn_id": "island-command-id", "call_id": "c"}) is None, \
        "an island turn's script keeps today's gates"


def test_a_swarm_workers_script_carrying_its_parents_pane_turn_id_keeps_the_workers_own_gates(world):
    """``SwarmManager`` hands a worker's scripts the parent turn's id (``harness.run_script``), routed by the worker's constant
    ``agent:<connection>`` session on the worker's own headless Lampway, which never saw the pane turn: not this check's to refuse."""
    worker = {"chat_session_id": "agent:conn-7", "turn_id": TID, "call_id": "w1-import"}
    assert MP.pane_turn_id(worker) == ""
    assert MP.script_refusal("agent:conn-7", worker) is None
    lane = {"chat_session_id": "agentlane:" + SID + ":1", "turn_id": TID, "call_id": "w1-stage"}
    assert MP.script_refusal("agentlane:" + SID + ":1", lane) is None


def test_a_script_that_overtakes_its_turns_start_waits_for_the_start_in_the_inbox(world):
    """The receive thread queues the start for the main thread; the script may reach the executor first. The check renders the
    tab's queued frames before it decides."""
    scene, seen = world
    TE.handle_turn_notification("agent.turn.started", pane_started())
    assert TID not in TE._turns
    assert MP.script_refusal(SID, script_ctx()) is None
    assert users(scene) == ["tui says hi"]


def test_the_main_thread_executor_refuses_an_unknown_pane_turns_script(executor, monkeypatch):
    """The real main-thread executor (the preview-deferral harness: the session active, routing and history stubbed)."""
    import importlib
    from unittest.mock import MagicMock
    from mixar.modules.common.agent_execution.request import ExecutionRequest
    client = _fake_client(monkeypatch)
    gate = importlib.import_module("mixar.modules.space_mixie_chat.core.render_gate")
    monkeypatch.setattr(gate.render_slot, "native_render_kind", lambda: None)
    ran = MagicMock(return_value={"success": True})
    monkeypatch.setattr(executor.pump, "execute_request", ran)
    TE.reset()
    TE._turns["pane_live00000001"] = TE.Turn(SID, "pane_live00000001", RUN, pane=True)
    for rid, tid in (("unknown", "pane_neverannounced"), ("live", "pane_live00000001")):
        executor.lanes.enqueue(ExecutionRequest(request_id=rid, script="print(1)", tool_name="scene_summary", session_id=SID,
                                                agent_ctx=script_ctx(tid)))
    executor._process_one_request()
    executor._process_one_request()
    TE.reset()
    replies = {call.args[0]: call.args[1] for call in client.queue_response.call_args_list}
    assert replies["unknown"]["success"] is False and replies["unknown"]["error_type"] == "unknown_turn"
    assert replies["live"]["success"] is True
    assert ran.call_count == 1, "the unknown turn's script never ran"


def test_the_receive_thread_leaves_a_pane_turns_script_to_the_main_threads_check():
    """``on_script_execute`` refuses a script with no active session at once; a pane turn's start may still be in the inbox (the
    tab is IDLE until the main thread renders it), so its scripts are decided on the main thread instead (``script_refusal``),
    after the executor drained the turn frames."""
    src = (CHAT / "core/connection_manager.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.FunctionDef) and n.name == "on_script_execute")
    body = ast.get_source_segment(src, fn)
    assert "pane_turn_id" in body and body.index("pane_turn_id") < body.index("has_active_session"), body
    executor_src = (CHAT / "core/main_thread_executor.py").read_text(encoding="utf-8")
    fn = next(n for n in ast.walk(ast.parse(executor_src)) if isinstance(n, ast.FunctionDef) and n.name == "_execute_dequeued_request")
    body = ast.get_source_segment(executor_src, fn)
    assert "script_refusal" in body and body.index("script_refusal") < body.index("has_active_session"), body


# ------------------------------------------------------------------------------------------------ /new in the pane (Q15)
def _old_chat(scene):
    for sender, text in (("USER", "Make a chair"), ("AGENT", "Done: one chair.")):
        m = scene.mixie_chat_messages.add()
        m.sender, m.text = sender, text


def _checkpoint(session_id):
    from mixar.modules.space_mixie_chat.core import checkpoint_store as CS
    directory = CS.session_dir(session_id)
    Path(directory, "c1.mixar").write_bytes(b"BLENDER")
    CS._write_index(session_id, [{"id": "c1", "session_id": session_id, "file": "c1.mixar", "kind": "turn", "turn": 1,
                                  "created_at": "2026-10-07T10:00:00+00:00", "seq": 1}])


def test_slash_new_in_the_pane_files_the_old_chat_in_history_and_starts_a_new_one_for_the_same_tab(world):
    from mixar.modules.space_mixie_chat.core import chat_history as CH, checkpoint_store as CS
    scene, seen = world
    _old_chat(scene)
    assert CH.archive_current(scene), "the turn end's upsert, under the tab's session id"
    _checkpoint(SID)
    TE._consume("agent.pane.new_conversation", NEW_CONVERSATION)
    assert scene.mixie_session_id == SID, "the tab keeps the unit's id: the next chat goes to the same pane"
    assert [(m.sender, m.text) for m in scene.mixie_chat_messages] == [
        ("AGENT", "Lampway Agent's pane started a new conversation (/new). The previous chat is in History.")]
    rows = CH.list_sessions()
    assert len(rows) == 1 and rows[0]["session_id"] != SID and rows[0]["title"] == "Make a chair"
    filed = rows[0]["session_id"]
    record = CH.load_session(filed)
    assert [m["text"] for m in record["messages"]] == ["Make a chair", "Done: one chair."]
    assert CS.list_checkpoints(filed) and [c["id"] for c in CS.list_checkpoints(filed)] == ["c1"]
    assert CS.list_checkpoints(SID) == [], "the new chat starts its own timeline"
    assert seen["runs"][-1] == ("", False) and seen["states"][-1].name == "IDLE"
    assert seen["flushed"] == [SID], "the old conversation's queued scripts are answered, not run"
    CH.archive_current(scene)
    assert {r["session_id"] for r in CH.list_sessions()} == {filed}, "a chat with no prompt of the user's is not filed"


def test_slash_new_during_a_turn_fences_the_old_turns_late_frames(world):
    scene, seen = world
    TE._consume("agent.turn.started", pane_started())
    TE._consume("agent.turn.event", event(0, pane_events()[0]))
    TE._consume("agent.pane.new_conversation", NEW_CONVERSATION)
    assert TE._turns[TID].complete and ("end", SID) in seen["executor"]
    before = (len(seen["slots"]), seen["completed"])
    feed(pane_events()[1:])                                             # the cancelled turn's tail, after the frame
    assert (len(seen["slots"]), seen["completed"]) == before, "nothing of the old turn lands in the new chat"
    assert [m.sender for m in scene.mixie_chat_messages] == ["AGENT"]


def test_slash_new_for_a_tab_in_your_agent_mode_is_ignored_with_a_log_line(world, caplog):
    scene, seen = world
    scene.lampway_agent_mode, scene.lampway_byoa_pane = "byoa", "pane1"
    _old_chat(scene)
    caplog.set_level(logging.INFO)
    TE._consume("agent.pane.new_conversation", NEW_CONVERSATION)
    assert users(scene) == ["Make a chair"] and seen["states"] == []
    assert any("new_conversation" in r.getMessage() or "/new" in r.getMessage() for r in caplog.records), caplog.text


# ------------------------------------------------------------------------------------------------ /new while Lampway was away
CONV = "mixie_pane_conversation"


def test_a_reconnect_that_learns_the_pane_moved_to_a_new_conversation_files_the_old_chat(world):
    """The pane's /new happened while Lampway was closed: the frame reached nobody. On reconnect ``agent.status`` names the
    conversation the pane shows (``conversations``); one other than the tab's last files the old chat, as the frame would have."""
    from mixar.modules.space_mixie_chat.core import chat_history as CH
    scene, seen = world
    scene[CONV] = "20261007_100000_aaaaaa"
    _old_chat(scene)
    CH.archive_current(scene)
    MP.note_conversation(SID, "20261007_110000_bbbbbb")
    assert [(m.sender, m.text) for m in scene.mixie_chat_messages] == [("AGENT", MP.NEW_CONVERSATION_NOTICE)]
    assert len(CH.list_sessions()) == 1 and CH.list_sessions()[0]["title"] == "Make a chair"
    assert scene[CONV] == "20261007_110000_bbbbbb"
    MP.note_conversation(SID, "20261007_110000_bbbbbb")
    assert len(scene.mixie_chat_messages) == 1, "the same conversation again changes nothing"


def test_the_first_conversation_a_tab_learns_is_only_recorded(world):
    scene, seen = world
    _old_chat(scene)
    MP.note_conversation(SID, "20261007_100000_aaaaaa")
    assert users(scene) == ["Make a chair"] and scene[CONV] == "20261007_100000_aaaaaa"


def test_the_frames_that_carry_the_conversation_keep_the_tab_current(world):
    """``agent.pane.new_conversation`` and ``agent.turn.started`` name the conversation; the tab keeps the last one, so a later
    reconnect compares against it. A turn's start only records (it never files a chat)."""
    from mixar.modules.space_mixie_chat.core import chat_history as CH
    scene, seen = world
    TE._consume("agent.turn.started", {**pane_started(), "conversation_id": "20261007_100000_aaaaaa"})
    feed(pane_events())
    assert scene[CONV] == "20261007_100000_aaaaaa"
    TE._consume("agent.pane.new_conversation", {**NEW_CONVERSATION, "conversation_id": "20261007_110000_bbbbbb"})
    assert scene[CONV] == "20261007_110000_bbbbbb" and len(CH.list_sessions()) == 1, "filed once, by the frame"


def test_the_status_reply_on_reconnect_hands_each_tabs_conversation_to_the_pane_check(world, monkeypatch):
    from mixar.modules.space_mixie_chat.core import main_thread_executor, turn_resume
    scene, seen = world
    scene[CONV] = "20261007_100000_aaaaaa"
    _old_chat(scene)
    monkeypatch.setattr(main_thread_executor, "run_on_main_thread", lambda fn: fn())
    turn_resume.note_conversations({"turns": {}, "conversations": {SID: "20261007_110000_bbbbbb"}})
    assert scene[CONV] == "20261007_110000_bbbbbb" and users(scene) == []


def test_the_socket_hands_the_new_conversation_frame_to_the_turn_ingress():
    from mixar.modules.space_mixie_chat.core.socket_dispatch import SocketDispatch
    got = []
    dispatch = SocketDispatch()
    dispatch._on_turn_event = lambda method, params: got.append((method, params))
    dispatch._handle_message({"jsonrpc": "2.0", "method": "agent.pane.new_conversation", "params": NEW_CONVERSATION})
    assert got == [("agent.pane.new_conversation", NEW_CONVERSATION)]
