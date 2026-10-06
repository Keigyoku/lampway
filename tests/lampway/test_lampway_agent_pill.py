# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The captain (contracts 04 and 05): "get rid of the separate floating agent-pill ... toggleable, off by default or
just combined into the chat window". Both: the minimised floating pill is a preference, "Floating agent pill", off by
default (existing users too, told once in the chat header), and what it showed lives in the chat window's header and,
while the chat is closed, in the top bar's agent chip (docs/reports/facelift/pill_parity.md lists every datum)."""

import sys
from types import SimpleNamespace

import pytest

from mixar.modules.agent_bubble.core import pill_pref


@pytest.fixture(autouse=True)
def stubs(monkeypatch):
    """The host's bpy stand-in: preview collections, and Operator / Header as plain classes (the brand-gate tests do
    the same) so the operators and header import as real classes."""
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "bpy.utils.previews", MagicMock())
    for name in ("Operator", "Header", "Panel", "Menu"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    for mod in ("mixar.modules.agent_bubble.ui.operators.bubble_close_op", "mixar.modules.agent_bubble.ui.header",
                "mixar.modules.agent_bubble.ui.glance"):
        monkeypatch.delitem(sys.modules, mod, raising=False)


@pytest.fixture
def config(monkeypatch):
    store = {}
    monkeypatch.setattr(pill_pref, "get_config", lambda: store)
    monkeypatch.setattr(pill_pref, "add_config", lambda k, v: store.__setitem__(k, v) or True)
    return store


def test_the_pill_is_not_shown_by_default(config, monkeypatch):
    assert pill_pref.enabled() is False
    from mixar.modules.agent_bubble.core import bubble_autoshow as A
    calls = []
    monkeypatch.setattr(A, "find_target_context", lambda: calls.append("looked") or None)
    assert A.try_invoke_bubble(start_minimised=True) is True, "a pill-only show is done: there is nothing to show"
    assert calls == [], "it never even looks for a window to put a pill in"


def test_turning_the_pref_on_shows_it(config, monkeypatch):
    pill_pref.set_enabled(True)
    assert pill_pref.enabled() is True
    from mixar.modules.agent_bubble.core import bubble_autoshow as A
    calls = []
    monkeypatch.setattr(A, "find_target_context", lambda: calls.append("looked") or None)
    assert A.try_invoke_bubble(start_minimised=True) is False
    assert calls == ["looked"], "with the pill on, the minimised show goes ahead as before"


def test_the_workspace_switch_and_the_tour_work_with_the_pill_off(config, monkeypatch):
    """Lamplight / Workshop bounce the workspace; a chat the user closed stays closed (no pill reappears), an open one
    is kept, and the tour still owns the chat while it runs."""
    import mixar.bootstrap.agent_bubble_module as M
    armed = []
    monkeypatch.setattr(M, "_arm_autoshow", lambda **kw: armed.append(kw))
    monkeypatch.setattr(M, "_has_agent_bubble_windows", lambda: False)
    monkeypatch.setattr(M, "tour_running", lambda: False)
    M._st.user_explicitly_closed = True
    M._on_workspace_change()
    assert armed == [], "closed with the pill off: the switch does not bring a pill back"
    M._st.user_explicitly_closed = False
    M._on_workspace_change()
    assert armed == [{"reset": True}], "a chat that was open comes back open"
    armed.clear()
    monkeypatch.setattr(M, "tour_running", lambda: True)
    M._on_workspace_change()
    assert armed == []


def test_closing_the_chat_with_the_pill_off_closes_it(config, monkeypatch):
    """Minimise (Escape, the yellow light, Ctrl+Shift+B) closes the chat instead of leaving a pill; the shortcut opens it
    again."""
    import bpy
    import importlib
    B = importlib.import_module("mixar.modules.agent_bubble.ui.operators.bubble_close_op")
    closed, opened, minimised = [], [], []
    monkeypatch.setattr(B, "_close_island", lambda: closed.append(1) or 1)
    monkeypatch.setattr(B, "_open_island", lambda: opened.append(1) or {'FINISHED'})
    monkeypatch.setattr(B, "_tour_wants_exit_dialog", lambda: False)
    monkeypatch.setattr(bpy.ops.mixar, "bubble_minimise", lambda: minimised.append(1) or {'FINISHED'}, raising=False)
    op = SimpleNamespace(report=lambda *a: None)
    ctx = SimpleNamespace(space_data=SimpleNamespace(type='AGENT_BUBBLE'))
    assert B.MIXAR_OT_bubble_close.execute(op, ctx) == {'FINISHED'} and closed == [1] and minimised == []
    monkeypatch.setattr(B, "_island_open", lambda: True)
    B.MIXAR_OT_bubble_toggle_minimise.execute(op, ctx)
    assert closed == [1, 1] and minimised == []
    monkeypatch.setattr(B, "_island_open", lambda: False)
    B.MIXAR_OT_bubble_toggle_minimise.execute(op, ctx)
    assert opened == [1]


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.alignment = None
        self.scale_x = 1.0

    def row(self, **_kw):
        return Recorder(self.log)

    def label(self, text="", icon="NONE", icon_value=0, **_kw):
        self.log.append(("label", text, icon, icon_value))

    def operator(self, idname, text="", icon="NONE", icon_value=0, **_kw):
        self.log.append(("op", idname, text, icon, icon_value))
        return SimpleNamespace()

    def separator(self, **_kw):
        pass

    def texts(self):
        return [e[2] if e[0] == "op" else e[1] for e in self.log]


def test_the_chat_header_shows_every_pill_datum(config, monkeypatch):
    """Parity: the agent's state (its Spark glyph and words), how many agents run, the queue's clock, and the way back in
    (the top bar chip, while the chat is closed). The pill's last-prompt preview and sketch draft are the chat's own
    transcript and composer, which are on screen whenever the header is."""
    import importlib
    glance = importlib.import_module("mixar.modules.agent_bubble.ui.glance")
    header = sys.modules["mixar.modules.agent_bubble.ui.header"]
    monkeypatch.setattr(header, "_transport_down", lambda: False)   # a live connection
    monkeypatch.setattr(header, "_queue_activity", lambda: None)
    monkeypatch.setattr(header, "get_running_text_suffix", lambda: "", raising=False)
    monkeypatch.setattr(glance, "preview", lambda name: {"agent_working": 11, "agent_idle": 12, "agent_blocked": 13}.get(name, 9))
    scene = SimpleNamespace(mixie_chat_state="BUSY", mixie_run_open=False)
    wm = SimpleNamespace(mixar_agent_cards=[SimpleNamespace(status="WORKING"), SimpleNamespace(status="WORKING"),
                                            SimpleNamespace(status="DONE")])
    # In the chat, the native header paints the cues (the island's header band is drawn in C++).
    from pathlib import Path
    draw = (Path(__file__).resolve().parents[2] / "src/source/blender/editors/space_agent_bubble/agent_ui_draw.cc").read_text()
    glance_cc = draw[draw.index("static void agent_ui_draw_header_glance("):draw.index("void agent_ui_draw_island(")]
    for datum in ("agent_ui_draw_spark(", "mixie_cat_activity_name(", "status_text", "agents running", "queue_count",
                  "pill_note"):
        assert datum in glance_cc, datum
    assert "agent_ui_draw_header_glance(layout, state, u);" in draw
    # closed chat, pill off: the top bar carries the same cues and opens the chat
    bar = Recorder()
    glance.draw_topbar(bar, scene, wm, island_open=False, unread=1)
    ops = [e for e in bar.log if e[0] == "op"]
    assert ops and ops[0][1] == "mixar.agent_bubble_open_window" and ops[0][4] == 11
    assert ops[0][2] == "Running \u00b7 2 agents running \u00b7 1 unread"
    nothing = Recorder()
    glance.draw_topbar(nothing, scene, wm, island_open=True, unread=0)
    assert nothing.log == [], "with the chat open its header carries the cues"


def test_existing_users_are_told_once(config):
    assert pill_pref.note_pending() is True
    pill_pref.mark_note_seen()
    assert pill_pref.note_pending() is False
    config.clear()
    pill_pref.set_enabled(True)
    assert pill_pref.note_pending() is False, "someone who turned the pill on needs no note"
