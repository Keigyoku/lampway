# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 03, the status bar: spend and egress always in view, a decision that waits for you in front.

draw() reads a cache a timer fills and never the network; the wire chip has three states and the server is the truth about
sending; only live egress animates, and never under reduced motion."""

import sys
import urllib.request
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from mixar.modules.lampway_tools import statusbar_state as S


class Recorder:
    """A recording layout: every label, operator button and icon it was asked to draw, in order."""

    def __init__(self, log=None):
        self.log = [] if log is None else log

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
        return [entry[2] if entry[0] == "op" else entry[1] for entry in self.log]


EGRESS_IDLE = {"routes": [{"id": "openrouter", "label": "OpenRouter", "enabled": False}], "indicator": {"over_the_wire": False, "active": [], "last": None}}
SPEND = {"scope": "session", "providers": [{"provider": "openrouter", "unit": "USD", "spent": 0.31, "session_cap": 5.0, "job_cap": 1.0, "click": "above", "above": 0.25},
                                           {"provider": "higgsfield", "unit": "credits", "spent": 0.0, "session_cap": None, "job_cap": None, "click": "always", "above": None}]}
WAITING = {"approvals": [{"id": "a1", "state": "pending", "settings": {"unit": "credits"}}], "jobs": []}


@pytest.fixture(autouse=True)
def fresh_state():
    S.reset()
    yield
    S.reset()


@pytest.fixture
def statusbar(monkeypatch):
    monkeypatch.setattr(sys.modules["bpy.types"], "Operator", object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.statusbar", raising=False)
    from mixar.modules.lampway_tools.ui import statusbar
    monkeypatch.setattr(statusbar, "preview", lambda name: 7)
    return statusbar


def test_statusbar_draw_is_pure(statusbar, monkeypatch):
    calls = []
    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: calls.append(a) or (_ for _ in ()).throw(AssertionError("draw went to the network")))
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio=WAITING)
    layout = Recorder()
    statusbar.draw(SimpleNamespace(layout=layout), SimpleNamespace())
    texts = layout.texts()
    assert "1 waiting for you" in texts
    assert "$0.31 of $5.00" in texts
    assert "local" in texts
    assert calls == []


def test_a_stopped_server_says_so_and_never_shows_a_stale_number(statusbar):
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio=WAITING)
    S.fail("the server could not be reached: [Errno 111] Connection refused")
    layout = Recorder()
    statusbar.draw(SimpleNamespace(layout=layout), SimpleNamespace())
    texts = layout.texts()
    assert "spend unknown: server not running" in texts and "egress unknown" in texts
    assert not [t for t in texts if "$0.31" in t or "waiting" in t]


def test_wire_chip_states():
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio={})
    assert S.wire_chip()[:2] == ("local", "lamp")
    two_on = {"routes": [{"id": "openrouter", "label": "OpenRouter", "enabled": True}, {"id": "fal", "label": "fal.ai", "enabled": True}],
              "indicator": {"over_the_wire": False, "active": [], "last": None}}
    S.update(egress=two_on, spend=SPEND, studio={})
    assert S.wire_chip()[:2] == ("2 routes open", "wire")
    sending = dict(two_on, indicator={"over_the_wire": True, "active": ["openrouter"], "last": None})
    S.update(egress=sending, spend=SPEND, studio={})
    assert S.wire_chip()[:2] == ("Sending to OpenRouter", "wire_dot")
    # the server is the truth: lit with no route named still reads Sending
    S.update(egress=dict(EGRESS_IDLE, indicator={"over_the_wire": True, "active": [], "last": None}), spend=SPEND, studio={})
    assert S.wire_chip()[0].startswith("Sending")


def test_spend_gauge_steps_and_the_cap_it_falls_under():
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio={})
    text, step, tip = S.spend_line()
    assert (text, step) == ("$0.31 of $5.00", 1)
    assert "this server session" in tip and "Providers" in tip
    near = {"scope": "session", "providers": [dict(SPEND["providers"][0], spent=4.6)]}
    S.update(egress=EGRESS_IDLE, spend=near, studio={})
    assert S.spend_line()[1] == 9
    no_cap = {"scope": "session", "providers": [dict(SPEND["providers"][0], session_cap=None), dict(SPEND["providers"][1], spent=18)]}
    S.update(egress=EGRESS_IDLE, spend=no_cap, studio={})
    assert S.spend_line()[:2] == ("$0.31 + 18 credits", None)


def test_wire_animation_only_while_sending(statusbar, monkeypatch):
    timers = SimpleNamespace(registered=set())
    timers.register = lambda fn, first_interval=0.0, **_k: timers.registered.add(fn)
    timers.is_registered = lambda fn: fn in timers.registered
    timers.unregister = lambda fn: timers.registered.discard(fn)
    monkeypatch.setattr(statusbar, "_timers", lambda: timers)
    monkeypatch.setattr(statusbar, "_redraw_statusbar", lambda: None)
    statusbar.REDUCE_MOTION["on"] = False
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio={})
    statusbar.sync_animation()
    assert timers.registered == set(), "only egress moves: nothing animates while nothing is sent"
    S.update(egress=dict(EGRESS_IDLE, indicator={"over_the_wire": True, "active": ["openrouter"], "last": None}), spend=SPEND, studio={})
    statusbar.sync_animation()
    assert timers.registered == {statusbar._wire_frame}
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio={})
    assert statusbar._wire_frame() is None, "the frame timer ends itself within one tick after sending stops"
    statusbar.REDUCE_MOTION["on"] = True
    timers.registered.clear()
    S.update(egress=dict(EGRESS_IDLE, indicator={"over_the_wire": True, "active": ["openrouter"], "last": None}), spend=SPEND, studio={})
    statusbar.sync_animation()
    assert timers.registered == set(), "reduced motion holds one frame"
    statusbar.REDUCE_MOTION["on"] = False


def test_the_redraw_reaches_the_status_bar(statusbar, monkeypatch):
    """The status bar is a global area (``Window.global_areas``), never in ``screen.areas``: a redraw that walks only the
    screen leaves the bar showing the previous answer until the pointer moves."""
    tagged = []
    area = lambda kind: SimpleNamespace(type=kind, tag_redraw=lambda: tagged.append(kind))  # noqa: E731
    window = SimpleNamespace(global_areas=[area('TOPBAR'), area('STATUSBAR')], screen=SimpleNamespace(areas=[area('VIEW_3D')]))
    monkeypatch.setattr(statusbar.bpy, "context", SimpleNamespace(window_manager=SimpleNamespace(windows=[window])), raising=False)
    statusbar._redraw_statusbar()
    assert tagged == ['STATUSBAR']


def test_the_poll_is_fast_only_while_a_route_is_on():
    S.update(egress=EGRESS_IDLE, spend=SPEND, studio={})
    assert S.poll_interval() == 5.0
    S.update(egress={"routes": [{"id": "fal", "label": "fal.ai", "enabled": True}], "indicator": {"over_the_wire": False, "active": []}}, spend=SPEND, studio={})
    assert S.poll_interval() == 0.5


def test_the_plug_beside_the_wire_chip_opens_connections(statusbar):
    """specs/connections/connections_face.md section 3: the plug glyph beside the wire chip opens Connections, server up or not."""
    for fail in (False, True):
        S.update(egress=EGRESS_IDLE, spend=SPEND, studio={})
        if fail:
            S.fail("down")
        layout = Recorder()
        statusbar.draw(SimpleNamespace(layout=layout), SimpleNamespace())
        ops = [e[1] for e in layout.log if e[0] == "op"]
        assert "lampway.connections_open" in ops, layout.log


def test_signed_out_says_signed_out_not_server_down(statusbar, monkeypatch):
    """Cloud audit F22 (2026-10-06): a server that answers 401 (/auth/me, or any read) is running; the user is signed out.
    The bar says "signed out" for a 401 and for no token at all, and keeps "server not running" for a refused connection."""
    import io
    import urllib.error

    from mixar.modules.lampway_tools import status_client

    def answer_401(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b'{"detail": "not authenticated"}'))
    monkeypatch.setattr(statusbar, "_sync_route_line", lambda: None)
    monkeypatch.setattr(statusbar, "_open_awaited_card", lambda: None)
    monkeypatch.setattr(statusbar, "_show_terminal_images", lambda: None)
    monkeypatch.setattr(statusbar, "_redraw_statusbar", lambda: None)
    monkeypatch.setattr(statusbar, "sync_animation", lambda: None)
    for token, opener in (("tok", answer_401), ("", answer_401)):
        monkeypatch.setattr(urllib.request, "urlopen", opener)
        monkeypatch.setattr(statusbar, "CLIENT_FACTORY", lambda: status_client.StatusClient("http://127.0.0.1:9", lambda: token))
        S.update(egress=EGRESS_IDLE, spend=SPEND, studio=WAITING)
        statusbar.refresh()
        layout = Recorder()
        statusbar.draw(SimpleNamespace(layout=layout), SimpleNamespace())
        texts = layout.texts()
        assert "signed out" in texts and not [t for t in texts if "not running" in t or "$0.31" in t], (token, texts)
    monkeypatch.setattr(urllib.request, "urlopen", lambda req, timeout=None: (_ for _ in ()).throw(urllib.error.URLError("refused")))
    monkeypatch.setattr(statusbar, "CLIENT_FACTORY", lambda: status_client.StatusClient("http://127.0.0.1:9", lambda: "tok"))
    statusbar.refresh()
    layout = Recorder()
    statusbar.draw(SimpleNamespace(layout=layout), SimpleNamespace())
    assert "spend unknown: server not running" in layout.texts()
