# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 02, onboarding (P1): four steps on the lit path, every route off until the user switches it, the last button names the outcome.

The walk (``lampway_tools/onboarding.py``) holds no bpy; the popup (``ui/onboarding.py``) draws it with native rows. The server-backed walk is
``server/tests/test_onboarding_walk.py``."""

import sys
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import onboarding as ob

ROUTES = [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "hosts": ["openrouter.ai"], "privacy_class": "conditional",
           "retention": "per model: zdr", "training": "per model: data_collection=deny"},
          {"id": "chatgpt_plan", "label": "ChatGPT plan", "enabled": False, "hosts": ["chatgpt.com", "auth.openai.com"], "privacy_class": "unknown",
           "retention": "unknown (unread)", "training": "unknown (unread)"},
          {"id": "fal", "label": "fal.ai", "enabled": False, "hosts": ["fal.ai"], "privacy_class": "unknown", "retention": "unknown", "training": "unknown"},
          {"id": "model_download", "label": "Model weights download (Hugging Face)", "enabled": False, "hosts": ["huggingface.co"],
           "privacy_class": "ok", "retention": "no user content", "training": "n/a"}]


def walk(provider="mock"):
    return ob.Walk(routes=ROUTES, provider=provider)


@pytest.mark.parametrize("n, label", [(0, "Continue with 0 routes on"), (1, "Continue with 1 route on"), (3, "Continue with 3 routes on")])
def test_continue_names_the_count(n, label):
    w = walk()
    for route in ROUTES[:n]:
        w.click_route(route["id"], True)
    assert w.continue_label() == label
    assert ob.continue_label(n) == label


def test_the_routes_come_before_the_provider():
    """The audit's F3, ruled by the captain (keep the four steps, fix the order): a plan provider needs its route, so the
    route switches come first and a fresh install on a plan can always advance."""
    assert ob.STEPS == ("Language and keys", "What may leave this machine", "Where the agent thinks", "Spending caps")
    w = walk("chatgpt_plan")
    assert w.next() is None and w.step == 2                       # routes
    w.click_route("chatgpt_plan", True)
    assert w.next() is None and w.step == 3                       # provider: its route is on
    assert w.next() is None and w.step == 4


def test_the_provider_step_refuses_a_provider_whose_route_is_off():
    w = walk("chatgpt_plan")
    w.step = 3
    assert w.next() == "ChatGPT plan needs the chatgpt.com route: go Back and switch it on, or pick a local provider"
    assert w.step == 3, "the step stays"
    w.back()
    assert w.step == 2, "Back reaches the routes"
    keyed = walk("anthropic")
    keyed.step = 3
    assert keyed.next() == "Claude plan needs the api.anthropic.com route: go Back and switch it on, or pick a local provider"
    free = walk("mock")
    free.step = 3
    assert free.next() is None


def test_offline_continue_saves_only_language_and_keys():
    w = ob.Walk(routes=None, provider="")
    assert not w.online
    for _ in range(3):
        assert w.next() is None
    assert w.step == 4
    assert w.finish(None) == ["preferences"]


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.enabled = True

    def row(self, **_kw):
        return Recorder(self.log)

    column = split = row

    def label(self, text="", icon="NONE", **_kw):
        self.log.append(("label", text, icon))

    def operator(self, idname, text="", icon="NONE", **_kw):
        self.log.append(("op", idname, text, icon))
        return SimpleNamespace()

    def prop(self, data, name, text=None, **_kw):
        self.log.append(("prop", name, getattr(data, "route_id", None)))

    def separator(self, **_kw):
        pass


@pytest.fixture
def ui(monkeypatch):
    monkeypatch.setattr(sys.modules["bpy.types"], "Operator", object, raising=False)
    monkeypatch.setattr(sys.modules["bpy.types"], "PropertyGroup", object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.onboarding", raising=False)
    import importlib
    return importlib.import_module("mixar.modules.lampway_tools.ui.onboarding")


def test_onboarding_rows_have_one_line(ui):
    """Each route is one row: one label (its name, the host in tier 3), the shield whose policy is its hover text, the switch."""
    rows = [SimpleNamespace(route_id=r["id"], enabled=False) for r in ROUTES]
    layout = Recorder()
    ui.draw_routes(layout, walk(), rows)
    labels = [e for e in layout.log if e[0] == "label"]
    switches = [e for e in layout.log if e[0] == "prop"]
    shields = [e for e in layout.log if e[0] == "op" and e[1] == "lampway.onboarding_policy"]
    assert len(labels) == len(switches) == len(shields) == len(ROUTES)
    assert [s[2] for s in switches] == [r["id"] for r in ROUTES]
    assert labels[0][1] == "OpenRouter   openrouter.ai"
    assert [s[3] for s in shields] == ['LAMPWAY_SHIELD_HALF', 'LAMPWAY_SHIELD_UNKNOWN', 'LAMPWAY_SHIELD_UNKNOWN', 'LAMPWAY_SHIELD']
    assert "per model: zdr" in ui.policy_text(ROUTES[0])


def test_quick_setup_continue_opens_the_walk(monkeypatch):
    """Step 1 is the splash's Quick Setup; its Continue opens steps 2-4 (which save the preferences at the end, as Continue did)."""
    import importlib
    from unittest.mock import MagicMock
    monkeypatch.setattr(sys.modules["bpy.types"], "Menu", object, raising=False)
    monkeypatch.setattr(sys.modules["bpy.types"], "PREFERENCES_OT_copy_prev", None, raising=False)
    monkeypatch.setitem(sys.modules, "bpy.app.translations", SimpleNamespace(pgettext_iface=lambda s, *a: s))
    monkeypatch.delitem(sys.modules, "mixar.bootstrap.splash_quick_setup", raising=False)
    quick = importlib.import_module("mixar.bootstrap.splash_quick_setup")
    monkeypatch.setattr(quick.bpy.types, "PREFERENCES_OT_copy_prev", None, raising=False)  # a first install: nothing to import
    monkeypatch.setattr(Recorder, "menu",lambda self, *a, **k: None, raising=False)
    layout = Recorder()
    quick.WM_MT_splash_quick_setup.draw(SimpleNamespace(layout=layout), SimpleNamespace(window_manager=MagicMock()))
    ops = [e[1] for e in layout.log if e[0] == "op"]
    assert "lampway.onboarding" in ops and "wm.save_userpref" not in ops


def test_offline_steps_name_the_stopped_server(ui):
    w = ob.Walk(routes=None, provider="")
    w.step = 3
    layout = Recorder()
    ui.draw_step(layout, w, [])
    assert ("label", "Lampway's server is not running: Start it", "ERROR") in layout.log


def test_the_caps_step_saves_ruling_5s_day_cap_and_its_defaults():
    """Ruling 5 (2026-10-07): the cap is a saved per-day total, $1 per job, $5 per day, a click above $0.25. The walk said
    session_cap and its popup "Per session"; the server read it as day_cap, but the words were wrong."""
    w = walk()
    assert w.caps == {"job_cap": 1.0, "day_cap": 5.0, "above": 0.25}
    from pathlib import Path
    popup = (Path(ob.__file__).parent / "ui" / "onboarding.py").read_text(encoding="utf-8")
    assert "session_cap" not in popup and "Per session" not in popup and '"Per day"' in popup
