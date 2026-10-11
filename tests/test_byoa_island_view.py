# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""B4 (docs/reports/agent-modes-spec.md): showing a BYOA session in the island, the Client's half.

- A tab in Your agent mode asks the server to observe its bound pane (``agent.byoa.observe``) when it switches, when the socket
  comes back, and on a file load; the observed turns arrive as Mode 1's own frames with ``observed: true``. They render with the
  same slot pipeline (bubbles, steps) but never take the tab's turn state: no BUSY, no open run, no executor turn, so a harness's
  MCP operation on the tab (R7, which needs the tab IDLE and sets BUSY itself) is never disturbed. Their end settles the bubbles,
  stores the transcript in the chat archive and keeps the file offset to resume from when the .blend is reopened.
- A pane with no readable session file is shown as its screen text, in one code-block bubble that a main-thread timer refreshes.
- In Your agent mode the composer types into the pane (``agent.byoa.send``): text only, no ``by`` field (the server decides who
  typed from the socket), the user's bubble at once, and the observed prompt that echoes it is not drawn twice.
``bpy`` is a MagicMock; the scenes are fakes; nothing reaches a socket."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from mixar.modules.space_mixie_chat.core import byoa_view as BV  # noqa: E402
from mixar.modules.space_mixie_chat.core import composer_send as CS  # noqa: E402
from mixar.modules.space_mixie_chat.core import session as S  # noqa: E402
from mixar.modules.space_mixie_chat.core import turn_events as TE  # noqa: E402

CHAT = SCRIPTS / "mixar" / "modules" / "space_mixie_chat"
CHAT_OPS_PY = (CHAT / "ui/operators/chat_ops.py").read_text(encoding="utf-8")
TURN_EVENTS_PY = (CHAT / "core/turn_events.py").read_text(encoding="utf-8")
HISTORY_PY = (CHAT / "core/chat_history.py").read_text(encoding="utf-8")
FILE_HANDLERS_PY = (CHAT / "core/file_handlers.py").read_text(encoding="utf-8")
BYOA_PY = (CHAT / "core/byoa_view.py").read_text(encoding="utf-8")

SID = "22222222-2222-4222-8222-222222222222"


class Items(list):
    def add(self):
        item = SimpleNamespace(label="", value="", style="")
        self.append(item)
        return item

    def clear(self):
        del self[:]


class Msgs(list):
    def add(self):
        m = SimpleNamespace(sender="", text="", content="", delivery_hint="", bubble_id="", action_items=Items(), attachments=Items())
        self.append(m)
        return m

    def remove(self, i):
        del self[i]

    def clear(self):
        del self[:]


class FakeScene(dict):
    def __bool__(self):           # a scene is truthy whatever its ID properties (an empty dict is not)
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
        self.lampway_agent_mode = "byoa"
        self.lampway_byoa_pane = "pane1"
        self.mixie_chat_is_busy = False
        self.mixie_chat_pending_attachments = Msgs()
        for k, v in kw.items():
            setattr(self, k, v)


@pytest.fixture
def world(monkeypatch):
    """One fake tab bound to the turn ingress; every side effect recorded instead of done."""
    scene = FakeScene()
    seen = {"states": [], "runs": [], "slots": [], "finalized": 0, "archived": 0, "executor": [], "calls": [], "commands": []}
    monkeypatch.setattr(S.SessionManager, "set_state", staticmethod(lambda sc, st: seen["states"].append(st)))
    monkeypatch.setattr(S.SessionManager, "set_run", staticmethod(lambda *a, **k: seen["runs"].append(a)))
    from mixar.modules.space_mixie_chat.core import slot_processor, chat_history, executor
    monkeypatch.setattr(slot_processor, "get_slot_processor",
                        lambda: SimpleNamespace(apply_event=lambda payload, sc: seen["slots"].append(payload), is_slot_event=lambda d: "bubble_id" in d))
    monkeypatch.setattr(slot_processor, "finalize_turn", lambda sc: seen.__setitem__("finalized", seen["finalized"] + 1))
    monkeypatch.setattr(chat_history, "archive_current", lambda sc: seen.__setitem__("archived", seen["archived"] + 1))
    monkeypatch.setattr(executor, "get_executor", lambda: SimpleNamespace(begin_agent_turn=lambda s: seen["executor"].append(("begin", s)),
                                                                           end_agent_turn=lambda s: seen["executor"].append(("end", s))))
    monkeypatch.setattr(TE, "_resolve", lambda sid: scene if sid == scene.mixie_session_id else None)
    from mixar.modules.common.agent_rpc import client as rpc
    monkeypatch.setattr(rpc, "call", lambda method, params, cb: seen["calls"].append((method, params, cb)))
    monkeypatch.setattr(rpc, "command", lambda method, payload, cb, command_id=None: seen["commands"].append((method, payload, cb, command_id)) or command_id)
    monkeypatch.setattr(TE, "_request_replay", lambda turn: None)
    TE.reset()
    BV.VIEWS.clear()
    BV.SCREENS.clear()
    BV.ACTIVITY.clear()
    yield scene, seen
    TE.reset()


def started(tid="byoa-pane1-0", user_text="Add a cube", observed=True):
    return {"session_id": SID, "turn_id": tid, "run_id": tid, "observed": observed, "harness": "claude", "pane": "pane1", "user_text": user_text}


def event(seq, payload, tid="byoa-pane1-0"):
    return {"session_id": SID, "turn_id": tid, "seq": seq, "event": payload}


# ------------------------------------------------------------------------------------------------------------- observed turns
def test_an_observed_turn_renders_through_the_slot_pipeline_and_never_takes_the_tabs_turn_state(world):
    scene, seen = world
    TE._consume("agent.turn.started", started())
    assert TE._turns["byoa-pane1-0"].observed is True
    assert [m.sender for m in scene.mixie_chat_messages] == ["USER"] and scene.mixie_chat_messages[0].text == "Add a cube"
    TE._consume("agent.turn.event", event(0, {"type": "run_status", "run_id": "byoa-pane1-0", "status": "in_progress"}))
    TE._consume("agent.turn.event", event(1, {"bubble_id": "byoa-pane1-0:agent", "content": {"set": "Done."}}))
    TE._consume("agent.turn.event", event(2, {"type": "turn_end", "status": "completed", "run_id": "byoa-pane1-0", "offset": 812}))
    assert [p["content"]["set"] for p in seen["slots"]] == ["Done."]
    assert seen["finalized"] == 1 and seen["archived"] == 1                                            # the archive keeps the observed transcript
    assert scene["lampway_byoa_cursor"] == {"pane": "pane1", "offset": 812}
    assert seen["states"] == [] and seen["runs"] == [] and seen["executor"] == []                     # BUSY, runs and undo turns stay Mode 1's
    assert "mixie_ws_resume" not in scene                                                              # Mode 1's cursor is not touched


def test_an_observed_start_for_a_tab_in_lampway_agent_mode_is_ignored(world):
    scene, seen = world
    scene.lampway_agent_mode = "runtime"
    TE._consume("agent.turn.started", started())
    assert "byoa-pane1-0" not in TE._turns and len(scene.mixie_chat_messages) == 0


def test_the_prompt_the_island_just_sent_is_not_drawn_twice(world):
    scene, seen = world
    ok, why = BV.send(scene, "Add a cube")
    assert ok, why
    TE._consume("agent.turn.started", started(user_text="Add a cube"))
    TE._consume("agent.turn.started", started(tid="byoa-pane1-90", user_text="typed in the pane itself"))
    assert [m.text for m in scene.mixie_chat_messages if m.sender == "USER"] == ["Add a cube", "typed in the pane itself"]


def test_a_lost_observed_tail_never_sets_the_tab_idle(world):
    scene, seen = world
    scene.mixie_chat_state = "BUSY"                                                                     # an MCP operation holds the tab
    TE._consume("agent.turn.started", started())
    TE._consume("agent.turn.event", event(0, {"type": "resume_unavailable"}))
    assert seen["states"] == [] and seen["runs"] == [] and TE._turns["byoa-pane1-0"].complete is True


# ------------------------------------------------------------------------------------------------------------- composer
def test_in_your_agent_mode_the_composer_sends_whenever_the_socket_is_up(world):
    scene, _ = world
    for state in ("IDLE", "BUSY", "AWAITING_INPUT"):
        scene.mixie_chat_state = state
        assert CS.can_send(scene) == (True, ""), state
    scene.mixie_chat_state = "OFFLINE"
    assert CS.can_send(scene)[0] is False


def test_the_send_types_into_the_tabs_pane_with_no_origin_field_and_shows_the_bubble_at_once(world):
    scene, seen = world
    ok, _ = BV.send(scene, "  Add a torus  ")
    assert ok
    method, payload, cb, command_id = seen["commands"][-1]
    assert method == "byoa.send" and payload == {"session_id": SID, "text": "Add a torus"}             # no by / origin: the server decides
    assert scene.mixie_chat_messages[-1].sender == "USER" and scene.mixie_chat_messages[-1].text == "Add a torus"
    assert command_id in TE._commands


def test_a_refused_send_says_why_on_the_users_bubble_and_in_the_chat(world):
    scene, seen = world
    BV.send(scene, "Add a torus")
    _, _, cb, command_id = seen["commands"][-1]
    TE._consume("agent.command.result", {"session_id": SID, "command_id": command_id, "ok": False, "code": "not_bound",
                                        "message": "No running agent pane is bound to this scene tab", "help": ["Pick Your agent"]})
    assert scene.mixie_chat_messages[0].delivery_hint
    assert "No running agent pane" in scene.mixie_chat_messages[-1].text and "Pick Your agent" in scene.mixie_chat_messages[-1].text


def test_a_tab_with_no_pane_refuses_the_send_locally(world):
    scene, seen = world
    scene.lampway_byoa_pane = ""
    ok, why = BV.send(scene, "hello")
    assert ok is False and "Your agent" in why and seen["commands"] == []


def test_the_send_operator_turns_to_the_pane_before_the_providers_route_is_asked():
    execute = next(n for n in ast.walk(ast.parse(CHAT_OPS_PY)) if isinstance(n, ast.FunctionDef) and n.name == "execute"
                   and "chat_route.refusal" in ast.get_source_segment(CHAT_OPS_PY, n))
    body = ast.get_source_segment(CHAT_OPS_PY, execute)
    assert "is_byoa(" in body and body.index("is_byoa(") < body.index("chat_route.refusal")


# ------------------------------------------------------------------------------------------------------------- observe and the screen
def test_observe_asks_for_the_tabs_pane_from_the_offset_this_tab_rendered(world):
    scene, seen = world
    scene["lampway_byoa_cursor"] = {"pane": "pane1", "offset": 812}
    assert BV.observe(scene) is True
    method, params, _ = seen["calls"][-1]
    assert method == "agent.byoa.observe" and params == {"session_id": SID, "after_offset": 812}
    scene["lampway_byoa_cursor"] = {"pane": "another-pane", "offset": 99}                              # a cursor of another pane is not this one's
    BV.observe(scene)
    assert seen["calls"][-1][1] == {"session_id": SID}
    assert BV.observe(FakeScene(lampway_agent_mode="runtime")) is False


def test_a_screen_view_is_one_code_block_bubble_rewritten_only_when_the_screen_changes(world, monkeypatch):
    scene, seen = world
    monkeypatch.setattr(BV, "_ensure_screen_timer", lambda: None)
    BV.apply_view({"session_id": SID, "view": "screen", "pane": "pane1", "harness": "opencode", "screen": "$ opencode\n> ready"})
    BV.apply_view({"session_id": SID, "view": "screen", "pane": "pane1", "harness": "opencode", "screen": "$ opencode\n> ready"})
    assert len(seen["slots"]) == 1
    slot = seen["slots"][0]
    assert slot["bubble_id"] == "byoa-screen:pane1" and slot["content"]["set"].startswith("```") and "> ready" in slot["content"]["set"]
    BV.apply_view({"session_id": SID, "view": "screen", "pane": "pane1", "harness": "opencode", "screen": "$ opencode\n> done"})
    assert len(seen["slots"]) == 2 and BV.VIEWS[SID]["view"] == "screen"


def test_an_ended_or_unbound_pane_is_said_once(world):
    scene, seen = world
    for _ in range(2):
        BV.apply_view({"session_id": SID, "view": "ended", "pane": "pane1", "help": ["press Resume"], "resumable": True})
    assert [m.text for m in scene.mixie_chat_messages].count(scene.mixie_chat_messages[0].text) == 1
    assert "press Resume" in scene.mixie_chat_messages[0].text


# ------------------------------------------------------------------------------------------------------------- an ended pane (B2)
def test_an_ended_pane_offers_resume_and_unbind_as_buttons_and_one_without_a_session_id_only_unbind(world):
    scene, seen = world
    BV.apply_view({"session_id": SID, "view": "ended", "pane": "pane1", "help": ["press Resume"], "resumable": True})
    bubble = scene.mixie_chat_messages[-1]
    assert bubble.bubble_id == "byoa-ended:pane1" and [a.value for a in bubble.action_items] == [BV.RESUME_ACTION, BV.UNBIND_ACTION]
    assert seen["calls"] == []                                                       # reopening the file only shows: nothing resumes
    BV.VIEWS.clear()
    BV.apply_view({"session_id": SID, "view": "ended", "pane": "pane1", "help": ["cannot be resumed"], "resumable": False})
    assert [m.bubble_id for m in scene.mixie_chat_messages].count("byoa-ended:pane1") == 1             # replaced, not stacked
    assert [a.value for a in scene.mixie_chat_messages[-1].action_items] == [BV.UNBIND_ACTION]


def test_resume_and_unbind_ask_the_server_and_its_answer_rebinds_the_tab_on_the_main_thread(world, monkeypatch):
    scene, seen = world
    BV.apply_view({"session_id": SID, "view": "ended", "pane": "pane1", "help": [], "resumable": True})
    assert BV.resume(scene) is True
    method, params, cb = seen["calls"][-1]
    assert method == "agent.byoa.resume" and params["session_id"] == SID
    assert all(len(m.action_items) == 0 for m in scene.mixie_chat_messages)          # the buttons go once pressed
    cb({"state": "complete", "result": {"ok": True, "pane": "pane2", "harness": "claude", "resumed": "pane1"}})
    BV.apply_control({"session_id": SID, "method": "agent.byoa.resume", "ok": True, "pane": "pane2", "harness": "claude"})
    assert scene.lampway_byoa_pane == "pane2" and scene["lampway_byoa_harness"] == "claude"
    assert seen["calls"][-1][0] == "agent.byoa.observe"                              # the new pane is watched at once
    assert BV.unbind(scene) is True and seen["calls"][-1][0] == "agent.byoa.unbind"
    BV.apply_control({"session_id": SID, "method": "agent.byoa.unbind", "ok": True, "unbound": ["pane2"]})
    assert scene.lampway_byoa_pane == ""
    BV.apply_control({"session_id": SID, "method": "agent.byoa.resume", "ok": False, "message": "no session id", "help": ["Unbind it"]})
    assert "no session id" in scene.mixie_chat_messages[-1].text and scene.lampway_byoa_pane == ""


def test_the_answer_travels_the_turn_ingress_and_the_buttons_are_the_users_click():
    assert "'agent.byoa.control'" in TURN_EVENTS_PY
    special = (CHAT / "ui/operators/chat_special_ops.py").read_text(encoding="utf-8")
    assert "byoa_view.execute_pane_action(" in special and "byoa_view.RESUME_ACTION" in special
    gate = BYOA_PY[BYOA_PY.index("def execute_pane_action"):]
    assert gate.index("script_running()") < gate.index("resume(scene)")


# ------------------------------------------------------------------------------------------------------------- Stop (B4)
def test_an_observed_turn_lights_running_and_its_end_puts_it_out(world):
    scene, seen = world
    TE._consume("agent.turn.started", started())
    assert scene.mixie_chat_is_busy is True and seen["states"] == []                 # display only: the turn state stays IDLE
    TE._consume("agent.turn.event", event(0, {"type": "run_status", "run_id": "byoa-pane1-0", "status": "in_progress"}))
    TE._consume("agent.turn.event", event(1, {"type": "turn_end", "status": "cancelled", "run_id": "byoa-pane1-0", "offset": 9}))
    assert scene.mixie_chat_is_busy is False and seen["states"] == []


def test_an_mcp_operation_keeps_its_own_busy_when_the_observed_turn_ends(world):
    scene, seen = world
    TE._consume("agent.turn.started", started())
    scene.mixie_chat_state = "BUSY"                                                  # the harness's MCP operation holds the tab
    TE._consume("agent.turn.event", event(0, {"type": "turn_end", "status": "completed", "run_id": "byoa-pane1-0", "offset": 9}))
    assert scene.mixie_chat_is_busy is True


def test_a_screen_shown_pane_is_running_while_herdr_reads_it_working(world, monkeypatch):
    scene, seen = world
    monkeypatch.setattr(BV, "_ensure_screen_timer", lambda: None)
    BV.apply_view({"session_id": SID, "view": "screen", "pane": "pane1", "screen": "> working", "agent_status": "working"})
    assert scene.mixie_chat_is_busy is True
    BV.apply_view({"session_id": SID, "view": "screen", "pane": "pane1", "screen": "> done", "agent_status": "idle"})
    assert scene.mixie_chat_is_busy is False


def test_stop_in_your_agent_mode_asks_the_server_to_interrupt_the_pane(world, monkeypatch):
    scene, seen = world
    from mixar.modules.lampway_tools import human_gate
    monkeypatch.setattr(human_gate, "script_running", lambda: False)
    op = SimpleNamespace(reports=[], report=lambda kind, text: op.reports.append((kind, text)))
    assert BV.execute_stop(op, SimpleNamespace(scene=scene)) == {'FINISHED'}
    method, params, cb = seen["calls"][-1]
    assert method == "agent.byoa.interrupt" and params == {"session_id": SID}
    cb({"state": "complete", "result": {"ok": False, "code": "pane_refused", "message": "herdr is down", "help": ["Stop it in its own pane"]}})
    monkeypatch.setattr(human_gate, "script_running", lambda: True)
    assert BV.execute_stop(op, SimpleNamespace(scene=scene)) == {'CANCELLED'} and "script" in op.reports[-1][1]


def test_the_stop_operator_turns_to_the_pane_before_tearing_down_a_mode_1_turn():
    ops = (CHAT / "ui/operators/session_ops.py").read_text(encoding="utf-8")
    execute = ops[ops.index("class MIXIE_CHAT_OT_abort_session"):]
    execute = execute[execute.index("def execute"):]
    assert execute.index("is_byoa(") < execute.index("cleanup_turn_handler(") and "byoa_view.execute_stop(" in execute


# ------------------------------------------------------------------------------------------------------------- images (B4)
def test_images_go_with_the_text_encoded_as_mode_1_encodes_them(world, monkeypatch):
    scene, seen = world
    from mixar.modules.space_mixie_chat.core import image_utils
    monkeypatch.setattr(image_utils, "encode_attachment_for_upload", lambda path, source: (f"b64:{path}", "image/jpeg"))
    att = scene.mixie_chat_pending_attachments.add()
    att.image_path, att.image_source, att.display_name = "/renders/a.png", "FILE", "a.png"
    model = scene.mixie_chat_pending_attachments.add()
    model.image_path, model.image_source = "/models/chair.glb", "MODEL_FILE"
    scene.mixie_chat_input = "what is wrong here?"
    op = SimpleNamespace(reports=[], report=lambda kind, text: op.reports.append((kind, text)), message_override="")
    assert BV.execute_send(op, SimpleNamespace(scene=scene)) == {'FINISHED'}
    method, payload, cb, command_id = seen["commands"][-1]
    assert payload == {"session_id": SID, "text": "what is wrong here?", "images": [{"data": "b64:/renders/a.png"}]}
    assert len(scene.mixie_chat_pending_attachments) == 0 and scene.mixie_chat_messages[-1].attachments[0].image_path == "/renders/a.png"
    assert any("model files" in t for _, t in op.reports)


def test_a_harness_that_takes_no_image_is_refused_before_anything_leaves_and_the_attachments_stay(world, monkeypatch):
    scene, seen = world
    from mixar.modules.space_mixie_chat.core import agent_mode as AM
    monkeypatch.setitem(AM.HARNESSES, "rows", [{"id": "cursor", "images": False, "images_note": "Cursor's agent CLI documents no way to take an image"}])
    scene["lampway_byoa_harness"] = "cursor"
    att = scene.mixie_chat_pending_attachments.add()
    att.image_path, att.image_source = "/renders/a.png", "FILE"
    op = SimpleNamespace(reports=[], report=lambda kind, text: op.reports.append((kind, text)), message_override="look")
    assert BV.execute_send(op, SimpleNamespace(scene=scene)) == {'CANCELLED'}
    assert op.reports == [({'ERROR'}, "Cursor's agent CLI documents no way to take an image")]
    assert seen["commands"] == [] and len(scene.mixie_chat_pending_attachments) == 1


def test_the_echo_of_a_send_with_images_is_not_drawn_twice(world):
    scene, seen = world
    BV.send(scene, "what is wrong here?", [{"data": "x"}])
    TE._consume("agent.turn.started", started(user_text="/proj/.lampway/panes/pane1/images/image-1.png what is wrong here?"))
    assert [m.text for m in scene.mixie_chat_messages if m.sender == "USER"] == ["what is wrong here?"]


def test_the_view_rides_the_turn_ingress_and_is_asked_again_on_reconnect_and_file_load():
    assert "'agent.byoa.view'" in TURN_EVENTS_PY and "observe_all()" in TURN_EVENTS_PY
    assert "observe_all" in FILE_HANDLERS_PY


def test_the_archive_record_says_which_mode_the_chat_was_in():
    archive = HISTORY_PY[HISTORY_PY.index("def archive_current"):]
    assert '"agent_mode": _agent_mode(scene)' in archive[:archive.index("_atomic_write_json")]
    from mixar.modules.space_mixie_chat.core import chat_history
    assert chat_history._agent_mode(FakeScene()) == "byoa" and chat_history._agent_mode(SimpleNamespace()) == "runtime"
