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

SID = "22222222-2222-4222-8222-222222222222"


class Msgs(list):
    def add(self):
        m = SimpleNamespace(sender="", text="", delivery_hint="", bubble_id="")
        self.append(m)
        return m

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
        BV.apply_view({"session_id": SID, "view": "ended", "pane": "pane1", "help": ["resume it from the cockpit"]})
    assert [m.text for m in scene.mixie_chat_messages].count(scene.mixie_chat_messages[0].text) == 1
    assert "resume it from the cockpit" in scene.mixie_chat_messages[0].text


def test_the_view_rides_the_turn_ingress_and_is_asked_again_on_reconnect_and_file_load():
    assert "'agent.byoa.view'" in TURN_EVENTS_PY and "observe_all()" in TURN_EVENTS_PY
    assert "observe_all" in FILE_HANDLERS_PY


def test_the_archive_record_says_which_mode_the_chat_was_in():
    archive = HISTORY_PY[HISTORY_PY.index("def archive_current"):]
    assert '"agent_mode": _agent_mode(scene)' in archive[:archive.index("_atomic_write_json")]
    from mixar.modules.space_mixie_chat.core import chat_history
    assert chat_history._agent_mode(FakeScene()) == "byoa" and chat_history._agent_mode(SimpleNamespace()) == "runtime"
