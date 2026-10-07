# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0 (docs/reports/agent-modes-spec.md): one agent mode per scene tab, the Client's half.

- Two saved scene properties: ``Scene.lampway_agent_mode`` (``runtime`` by default, or ``byoa``) and ``Scene.lampway_byoa_pane``
  (the herdr session bound to the tab). Saved, so a tab reopens in the mode it was left in.
- The island's switch is the top of the agent picker the Model chip opens (``MIXIE_CHAT_MT_agent_model``): "Lampway Agent" and
  "Your agent: <harness>" for each harness the server lists (``GET /app/workbench/harnesses``). The menu's draw reads a cache and
  never the network; in Your agent mode the model rows give way to a note (the model is the harness's own).
- Switching is refused while the tab is BUSY, MODIFYING or AWAITING_INPUT, holds an open run, or holds an MCP operation:
  ``code: scene_busy`` with a help line. A switch starts a fresh chat (the old one goes to History) and says that the conversation
  does not carry across. The server binds or unbinds the tab's pane (``POST /app/workbench/mode``); if it refuses, nothing changes.
- Every ``agent.chat`` carries the tab's mode, so the server can refuse a Mode 1 turn into a Your agent tab (``wrong_mode``).

``bpy`` is a MagicMock here: the property registration, the menu and the operator are pinned at source level; the decisions live in
``core/agent_mode.py`` and are driven directly with fake scenes and a fake server client."""
import ast
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src" / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from mixar.modules.space_mixie_chat.core import agent_mode as AM  # noqa: E402
from mixar.modules.space_mixie_chat.core import session as S  # noqa: E402

CHAT = SCRIPTS / "mixar" / "modules" / "space_mixie_chat"
PROPS_PY = (CHAT / "ui/properties/chat_props.py").read_text(encoding="utf-8")
MENU_PY = (SCRIPTS / "mixar/modules/byok/ui/menus/agent_model_menu.py").read_text(encoding="utf-8")
OPS_PY = CHAT / "ui/operators/agent_mode_ops.py"
TRANSPORT_PY = (CHAT / "core/turn_transport.py").read_text(encoding="utf-8")
SESSION_OPS_PY = (CHAT / "ui/operators/session_ops.py").read_text(encoding="utf-8")
WB_CLIENT_PY = (SCRIPTS / "mixar/modules/lampway_tools/workbench_client.py").read_text(encoding="utf-8")
AGENT_MODE_PY = (CHAT / "core/agent_mode.py").read_text(encoding="utf-8")


class Msgs(list):
    def add(self):
        m = SimpleNamespace(sender="", text="", delivery_hint="", bubble_id="")
        self.append(m)
        return m

    def clear(self):
        del self[:]


class FakeScene(dict):
    """A scene tab: attributes like the RNA properties, item access like the ID properties."""

    def __bool__(self):           # a scene is truthy whatever its ID properties (an empty dict is not)
        return True

    def __init__(self, **kw):
        super().__init__()
        self.name = "Scene"
        self.mixie_chat_state = "IDLE"
        self.mixie_run_open = False
        self.mixie_run_id = ""
        self.mixie_session_id = "11111111-1111-4111-8111-111111111111"
        self.mixie_chat_messages = Msgs()
        self.lampway_agent_mode = "runtime"
        self.lampway_byoa_pane = ""
        for k, v in kw.items():
            setattr(self, k, v)


class FakeClient:
    def __init__(self, answer=None, error=None):
        self.calls, self.answer, self.error = [], answer, error

    def set_mode(self, scene_session_id, mode, harness=None, pane=None, previous=None, name=None):
        self.calls.append({"scene_session_id": scene_session_id, "mode": mode, "harness": harness, "pane": pane, "previous": previous})
        if self.error:
            from mixar.modules.lampway_tools.studio_client import StudioError
            raise StudioError(self.error)
        return self.answer


@pytest.fixture(autouse=True)
def quiet(monkeypatch):
    """No archive on disk, no MCP lease, no state writes beyond the scene itself."""
    from mixar.modules.space_mixie_chat.core import chat_history
    monkeypatch.setattr(chat_history, "archive_current", lambda scene: True)
    from mixar.modules.mcp_bridge.core import lease
    monkeypatch.setattr(lease, "has_active_operation", lambda sid: False)
    monkeypatch.setattr(S.SessionManager, "set_run", staticmethod(lambda *a, **k: None))
    AM.HARNESSES.update(rows=[], enabled=False, loaded=False, error="")


# ------------------------------------------------------------------------------------------------------------- the properties
def test_the_two_scene_properties_are_registered_saved_and_removed():
    assert "bpy.types.Scene.lampway_agent_mode = EnumProperty(" in PROPS_PY
    block = PROPS_PY[PROPS_PY.index("bpy.types.Scene.lampway_agent_mode = EnumProperty("):]
    block = block[:block.index("\n    )\n")]
    assert "('runtime'," in block and "('byoa'," in block and "default='runtime'" in block
    assert "SKIP_SAVE" not in block                                                                     # saved with the .blend
    pane = PROPS_PY[PROPS_PY.index("bpy.types.Scene.lampway_byoa_pane = StringProperty("):]
    assert "SKIP_SAVE" not in pane[:pane.index("\n    )\n")]
    tail = PROPS_PY[PROPS_PY.index("def unregister"):]
    assert "'lampway_agent_mode'" in tail and "'lampway_byoa_pane'" in tail


def test_the_mode_reads_runtime_unless_the_tab_says_byoa():
    assert AM.get_mode(FakeScene()) == "runtime" and AM.is_byoa(FakeScene()) is False
    assert AM.get_mode(FakeScene(lampway_agent_mode="byoa")) == "byoa" and AM.is_byoa(FakeScene(lampway_agent_mode="byoa"))
    assert AM.get_mode(FakeScene(lampway_agent_mode="sideways")) == "runtime"
    assert AM.get_mode(SimpleNamespace()) == "runtime"                                                 # an old file without the property


# ------------------------------------------------------------------------------------------------------------- scene_busy
@pytest.mark.parametrize("state", ["BUSY", "MODIFYING", "AWAITING_INPUT"])
def test_switching_is_refused_while_the_tab_is_working(state):
    r = AM.switch_refusal(FakeScene(mixie_chat_state=state))
    assert r["ok"] is False and r["code"] == "scene_busy" and r["help"] and r["error"]


def test_switching_is_refused_while_a_run_is_open_or_an_mcp_operation_holds_the_tab(monkeypatch):
    assert AM.switch_refusal(FakeScene(mixie_run_open=True))["code"] == "scene_busy"
    from mixar.modules.mcp_bridge.core import lease
    scene = FakeScene()
    monkeypatch.setattr(lease, "has_active_operation", lambda sid: sid == scene.mixie_session_id)
    assert AM.switch_refusal(scene)["code"] == "scene_busy"


def test_an_idle_or_offline_tab_may_switch():
    assert AM.switch_refusal(FakeScene()) is None and AM.switch_refusal(FakeScene(mixie_chat_state="OFFLINE")) is None


# ------------------------------------------------------------------------------------------------------------- the switch
def test_a_switch_to_your_agent_binds_a_pane_starts_a_fresh_chat_and_says_the_chat_does_not_carry_across():
    scene = FakeScene()
    scene.mixie_chat_messages.add().sender = "USER"
    old = scene.mixie_session_id
    client = FakeClient({"mode": "byoa", "pane": {"id": "pane1", "harness": "claude"}, "view": "transcript"})
    out = AM.switch(scene, "byoa", "claude", client)
    assert out["ok"] is True and out["view"] == "transcript"
    call = client.calls[0]
    assert call["mode"] == "byoa" and call["harness"] == "claude" and call["previous"] == old
    assert call["scene_session_id"] == scene.mixie_session_id != old                                   # a fresh chat session
    assert scene.lampway_agent_mode == "byoa" and scene.lampway_byoa_pane == "pane1" and scene["lampway_byoa_harness"] == "claude"
    assert [m.sender for m in scene.mixie_chat_messages] == ["AGENT"]
    note = scene.mixie_chat_messages[0].text
    assert "does not carry across" in note and "History" in note


def test_a_switch_back_to_lampway_agent_unbinds_and_clears_the_pane():
    scene = FakeScene(lampway_agent_mode="byoa", lampway_byoa_pane="pane1")
    scene["lampway_byoa_cursor"] = {"pane": "pane1", "offset": 10}
    old = scene.mixie_session_id
    client = FakeClient({"mode": "runtime", "unbound": ["pane1"]})
    out = AM.switch(scene, "runtime", None, client)
    assert out["ok"] is True and client.calls[0]["mode"] == "runtime" and client.calls[0]["previous"] == old
    assert scene.lampway_agent_mode == "runtime" and scene.lampway_byoa_pane == "" and "lampway_byoa_cursor" not in scene
    assert "does not carry across" in scene.mixie_chat_messages[-1].text


def test_a_busy_tab_is_refused_before_the_server_is_asked():
    scene = FakeScene(mixie_chat_state="BUSY")
    client = FakeClient({"mode": "byoa"})
    out = AM.switch(scene, "byoa", "claude", client)
    assert out["code"] == "scene_busy" and client.calls == [] and scene.lampway_agent_mode == "runtime"


def test_a_switch_the_server_refuses_changes_nothing_and_says_why():
    scene = FakeScene()
    scene.mixie_chat_messages.add().sender = "USER"
    sid = scene.mixie_session_id
    out = AM.switch(scene, "byoa", "claude", FakeClient(error="the byoa:claude route is off"))
    assert out["ok"] is False and "byoa:claude" in out["error"] and out["help"]
    assert scene.lampway_agent_mode == "runtime" and scene.mixie_session_id == sid and len(scene.mixie_chat_messages) == 1


def test_choosing_the_mode_the_tab_is_already_in_is_a_no_op():
    scene = FakeScene()
    client = FakeClient({"mode": "runtime"})
    assert AM.switch(scene, "runtime", None, client) == {"ok": True, "unchanged": True} and client.calls == []
    scene = FakeScene(lampway_agent_mode="byoa", lampway_byoa_pane="pane1")
    scene["lampway_byoa_harness"] = "claude"
    assert AM.switch(scene, "byoa", "claude", client)["unchanged"] is True and client.calls == []


def test_a_new_chat_in_your_agent_mode_hands_the_pane_to_the_new_chat_session():
    scene = FakeScene(lampway_agent_mode="byoa", lampway_byoa_pane="pane1", mixie_session_id="")
    client = FakeClient({"mode": "byoa", "pane": {"id": "pane1", "harness": "claude"}, "view": "transcript"})
    out = AM.after_new_chat(scene, "old-session", client)
    assert out["ok"] is True and scene.mixie_session_id
    assert client.calls == [{"scene_session_id": scene.mixie_session_id, "mode": "byoa", "harness": None, "pane": "pane1", "previous": "old-session"}]
    runtime = FakeScene(mixie_session_id="")
    assert AM.after_new_chat(runtime, "old-session", client) is None and len(client.calls) == 1
    assert "after_new_chat" in SESSION_OPS_PY


# ------------------------------------------------------------------------------------------------------------- the menu
def _rows(scene):
    return [(r.kind, r.label, r.enabled, r.active, r.mode, r.harness) for r in AM.menu_rows(scene)]


def test_before_the_harnesses_are_known_the_menu_offers_to_look_for_them():
    rows = _rows(FakeScene())
    assert rows[0] == ("MODE", "Lampway Agent", True, True, "runtime", "")
    assert rows[1][0] == "REFRESH" and "Your agent" in rows[1][1]


def test_each_listed_harness_is_a_your_agent_row_and_a_missing_one_is_greyed_with_how_to_install_it():
    AM.HARNESSES.update(loaded=True, enabled=True, rows=[
        {"id": "claude", "label": "Claude Code", "installed": True, "install": None},
        {"id": "codex", "label": "Codex CLI", "installed": False, "install": "npm install -g @openai/codex"}])
    rows = AM.menu_rows(FakeScene())
    claude = next(r for r in rows if r.harness == "claude")
    codex = next(r for r in rows if r.harness == "codex")
    assert claude.kind == "MODE" and claude.mode == "byoa" and claude.enabled and claude.label == "Your agent: Claude Code"
    assert codex.enabled is False and "not installed" in codex.label and "npm install" in codex.tip


def test_with_the_switch_for_your_own_agents_off_every_harness_is_greyed_and_a_note_says_why():
    AM.HARNESSES.update(loaded=True, enabled=False, rows=[{"id": "claude", "label": "Claude Code", "installed": True, "install": None}])
    rows = AM.menu_rows(FakeScene())
    assert next(r for r in rows if r.harness == "claude").enabled is False
    assert any(r.kind == "NOTE" and "off" in r.label for r in rows)


def test_in_your_agent_mode_the_active_row_is_the_harness_and_a_note_replaces_the_model_list():
    AM.HARNESSES.update(loaded=True, enabled=True, rows=[{"id": "claude", "label": "Claude Code", "installed": True, "install": None}])
    scene = FakeScene(lampway_agent_mode="byoa", lampway_byoa_pane="pane1")
    scene["lampway_byoa_harness"] = "claude"
    rows = AM.menu_rows(scene)
    assert next(r for r in rows if r.harness == "claude").active is True
    assert next(r for r in rows if r.mode == "runtime").active is False
    assert any(r.kind == "NOTE" and "model" in r.label.lower() for r in rows)


def test_the_picker_draws_the_mode_rows_first_and_skips_the_models_in_your_agent_mode():
    draw = next(n for n in ast.walk(ast.parse(MENU_PY)) if isinstance(n, ast.ClassDef) and n.name == "MIXIE_CHAT_MT_agent_model")
    body = ast.get_source_segment(MENU_PY, draw)
    assert "draw_rows(" in body and body.index("draw_rows(") < body.index("model_menu.build_rows(")
    assert "if AM.draw_rows(" in body or "if agent_mode.draw_rows(" in body


def test_no_draw_path_reaches_the_network():
    for source in (MENU_PY, AGENT_MODE_PY):
        for banned in ("WorkbenchClient", "urllib", "requests", "StudioClient", "_call("):
            assert banned not in source, banned


# ------------------------------------------------------------------------------------------------------------- operator and wire
def test_the_switch_operator_is_a_users_click_and_asks_the_refusal_first():
    src = OPS_PY.read_text(encoding="utf-8")
    tree = ast.parse(src)
    op = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == "MIXIE_CHAT_OT_agent_mode_set")
    body = ast.get_source_segment(src, op)
    assert 'bl_idname = "mixie_chat.agent_mode_set"' in body
    assert "script_running()" in body and body.index("script_running()") < body.index("AM.prepare(") < body.index("_run(")
    assert "classes = (" in src and "MIXIE_CHAT_OT_agent_mode_refresh" in src
    # the server's half (a harness start can take seconds) runs on a worker thread; a main-thread timer applies the answer
    assert "threading.Thread(" in src and "bpy.app.timers.register(_apply_answers" in src and "AM.apply(" in src
    worker = ast.get_source_segment(src, next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "_ask"))
    assert "AM.ask_server(" in worker and "scene" not in worker.replace("scene_name", "")             # no bpy on the worker


def test_the_server_answer_is_not_applied_to_a_tab_that_moved_on():
    scene = FakeScene()
    plan = AM.prepare(scene, "byoa", "claude")
    asked = AM.ask_server(plan, FakeClient({"mode": "byoa", "pane": {"id": "pane1", "harness": "claude"}}))
    scene.mixie_session_id = "33333333-3333-4333-8333-333333333333"                                   # a New Chat meanwhile
    out = AM.apply(scene, plan, asked)
    assert out["ok"] is False and scene.lampway_agent_mode == "runtime"


def test_the_workbench_client_names_the_two_routes():
    assert '"/app/workbench/harnesses"' in WB_CLIENT_PY and '"/app/workbench/mode"' in WB_CLIENT_PY


def test_every_chat_carries_the_tabs_mode():
    send = next(n for n in ast.walk(ast.parse(TRANSPORT_PY)) if isinstance(n, ast.FunctionDef) and n.name == "_send")
    body = ast.get_source_segment(TRANSPORT_PY, send)
    assert "payload['agent_mode']" in body and "lampway_agent_mode" in body
