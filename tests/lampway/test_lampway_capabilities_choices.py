# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Where the Capabilities page lives (E2): a row in the Choices window ("Choices and privacy"), next to Spending, with Routes one click
away in Privacy and Privacy linking back. The page itself is tests/lampway/test_lampway_capabilities_ui.py."""

import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import capabilities_face, capabilities_state, choices_state

ROOT = Path(__file__).resolve().parents[2]
CHOICES = "mixar.modules.lampway_tools.ui.choices"
CAPS = "mixar.modules.lampway_tools.ui.capabilities"
PRIVACY = ROOT / "src/scripts/mixar/modules/lampway_tools/ui/privacy.py"


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log

    def row(self, **kw):
        return Recorder(self.log)

    column = box = split = row

    def label(self, text="", **kw):
        self.log.append(("label", text))

    def operator(self, idname, text="", **kw):
        props = SimpleNamespace()
        self.log.append(("op", idname, text, kw, props))
        return props

    def separator(self, **kw):
        pass

    def ops(self, idname):
        return [e for e in self.log if e[0] == "op" and e[1] == idname]


@pytest.fixture
def choices(monkeypatch):
    for name in ("Operator", "Panel"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, CHOICES, raising=False)
    drawn, refreshed = [], []
    fake = SimpleNamespace(draw_capabilities=lambda layout, context=None: drawn.append(layout), request_refresh=lambda: refreshed.append(1))
    monkeypatch.setitem(sys.modules, CAPS, fake)
    mod = importlib.import_module(CHOICES)
    mod.drawn, mod.refreshed = drawn, refreshed
    capabilities_state.reset()
    saved = dict(choices_state.STATE)
    yield mod
    choices_state.STATE.clear()
    choices_state.STATE.update(saved)
    capabilities_state.reset()
    sys.modules.pop(CHOICES, None)


def test_the_list_has_a_capabilities_row_after_spending(choices):
    lay = Recorder()
    choices._list(lay)
    rows = [e for e in lay.log if e[0] == "op" and e[1] == "lampway.choices_select"]
    assert [e[2] for e in rows][-2:] == ["Spending", "Capabilities"]
    assert rows[-1][4].purpose == capabilities_face.PAGE_ID == "capabilities"


def test_the_row_glows_while_an_agents_proposal_waits(choices):
    quiet = Recorder()
    choices._list(quiet)
    assert quiet.ops("lampway.choices_select")[-1][3].get("depress") is False
    capabilities_state.update({"capabilities": [{"id": "terminal", "label": "Run shell commands", "enabled": False, "risk": "runs_code",
                                                 "does": "Run shell commands.", "options": [], "chosen_options": {}, "routes": []}],
                               "proposals": [{"pid": "p1", "id": "terminal", "change": {"enabled": True}, "reason": "", "origin": "agent",
                                              "state": "open", "t": 1.0}]})
    lit = Recorder()
    choices._list(lit)
    last = lit.ops("lampway.choices_select")[-1]
    assert last[3].get("depress") is True and "proposal" in last[4].hover


def test_selecting_it_reads_capabilities_and_asks_the_choices_server_nothing(choices, monkeypatch):
    class Boom:
        def one(self, *a, **k):
            raise AssertionError("Capabilities is not a Choices purpose: the Choices server was asked for it")

    monkeypatch.setattr(choices, "CLIENT_FACTORY", lambda: Boom())
    choices.select("capabilities")
    assert choices_state.STATE["selected"] == "capabilities" and choices.refreshed == [1]


def test_selecting_a_purpose_does_not_read_capabilities(choices, monkeypatch):
    class Door:
        def one(self, pid, project=None):
            return {"id": pid}

    monkeypatch.setattr(choices, "CLIENT_FACTORY", lambda: Door())
    choices.select("agent.main")
    assert choices.refreshed == []


def test_the_detail_of_the_row_is_the_capabilities_page(choices):
    choices_state.STATE["selected"] = "capabilities"
    lay = Recorder()
    choices._detail(lay)
    assert choices.drawn == [lay]


def test_choices_open_takes_the_page_as_its_purpose(choices):
    """lampway.choices_open purpose=capabilities is how the walk, the status chip and Privacy reach the page: it selects the row."""
    seen = []
    choices.REFRESH = lambda: None
    choices.select = lambda pid: seen.append(pid)
    choices._open(purpose="capabilities")
    assert seen == ["capabilities"]


def test_privacy_links_to_the_page_beside_its_routes():
    src = PRIVACY.read_text(encoding="utf-8")
    assert '"lampway.choices_open"' in src and "capabilities_face.PAGE_ID" in src, "Routes link to what the agent may do with them"


def test_the_choices_window_still_never_switches_a_route():
    src = (ROOT / "src/scripts/mixar/modules/lampway_tools/ui/choices.py").read_text(encoding="utf-8")
    for needle in ("egress/route", "set_route", 'lampway.egress_route"', "/app/connections", "put_secret", "connections_save_secret"):
        assert needle not in src, needle
