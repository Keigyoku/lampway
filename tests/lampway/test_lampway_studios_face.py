# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Contract 06, the Studios panel (the Providers half moved to Choices, specs/choices/facelift_06_amendment.md): a
waiting spend says its price on the button, a job Lampway cannot account for offers the user's two ways out and
nothing that sends it again, the plan form has typed fields instead of JSON, and the panel has one glow."""

import sys
from types import SimpleNamespace

import pytest

from mixar.modules.lampway_tools import studio_state


class Recorder:
    def __init__(self, log=None):
        self.log = [] if log is None else log
        self.alert = False
        self.enabled = True
        self.use_property_split = False

    def _child(self, **_kw):
        return Recorder(self.log)

    row = column = box = split = _child

    def label(self, text="", icon="NONE", **_kw):
        self.log.append(("label", text, icon, self.alert))

    def operator(self, idname, text="", icon="NONE", depress=False, **_kw):
        self.log.append(("op", idname, text, icon, depress or self.alert))
        return SimpleNamespace()

    def prop(self, data, name, text=None, **_kw):
        self.log.append(("prop", name, text))

    def template_list(self, *a, **_kw):
        self.log.append(("list", a[0] if a else ""))

    def separator(self, **_kw):
        pass

    def panel(self, idname, default_closed=False):
        return Recorder(self.log), Recorder(self.log)   # drawn open, so the test sees the body

    def ops(self):
        return [e for e in self.log if e[0] == "op"]

    def texts(self):
        return [e[2] if e[0] == "op" else e[1] for e in self.log if e[0] in ("op", "label")]


@pytest.fixture
def panel(monkeypatch):
    from unittest.mock import MagicMock
    monkeypatch.setitem(sys.modules, "mathutils.bvhtree", MagicMock())
    for name in ("Panel", "Operator", "UIList", "PropertyGroup", "Menu"):
        monkeypatch.setattr(sys.modules["bpy.types"], name, object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.lampway_tools.ui.panels.lampway_panels", raising=False)
    import importlib
    mod = importlib.import_module("mixar.modules.lampway_tools.ui.panels.lampway_panels")
    studio_state.STATE.update(actions=[{"id": "tripo.mesh", "label": "Smart Mesh"}], approvals=[], jobs=[], engine={}, error="",
                              receipts=[])
    yield mod
    studio_state.STATE.update(approvals=[], jobs=[], receipts=[])


def _draw(mod):
    layout = Recorder()
    scene = SimpleNamespace(lampway_tools=SimpleNamespace(studio_action="tripo.mesh", studio_plan_args=[],
                                                          studio_plan_args_index=0))
    mod.LAMPWAY_PT_studios.draw(SimpleNamespace(layout=layout), SimpleNamespace(scene=scene))
    return layout


def test_spend_button_carries_the_price(panel):
    studio_state.STATE["approvals"] = [{"id": "a1", "state": "pending", "label": "Smart Mesh", "price": 13.5, "studio": "tripo",
                                        "settings": {"unit": "credits"}}]
    layout = _draw(panel)
    spend = [e for e in layout.ops() if e[1] == "lampway.studio_confirm"]
    assert spend and spend[0][2] == "Spend 13.5 credits", layout.ops()
    assert [e for e in layout.ops() if e[1] == "lampway.studio_reject"][0][2] == "Not now"
    assert "Confirm and spend" not in layout.texts()


def test_maybe_sent_offers_two_actions(panel):
    studio_state.STATE["receipts"] = [{"key": "k1", "label": "Smart Mesh", "state": "submission_unknown", "provider": "tripo",
                                       "actions": ["acknowledge", "link"]}]
    layout = _draw(panel)
    ops = {e[1]: e[2] for e in layout.ops()}
    assert ops.get("lampway.receipt_acknowledge") == "It did not run"
    assert ops.get("lampway.receipt_link") == "Link its job id"
    assert not [e for e in layout.ops() if e[1] in ("lampway.studio_plan", "lampway.studio_confirm") and "k1" in str(e)], \
        "nothing on a maybe-sent job sends it again"


def test_studios_plan_form_has_no_json(panel):
    layout = _draw(panel)
    assert ("prop", "studio_args", "") not in layout.log and not [e for e in layout.log if e[0] == "prop" and e[1] == "studio_args"]
    from mixar.modules.lampway_tools.ui.operators import studio_ops
    rows = [SimpleNamespace(key="polycount", kind='NUMBER', text="", number=30000.0, path="", flag=False),
            SimpleNamespace(key="prompt_file", kind='FILE', text="", number=0.0, path="//plates/front.png", flag=False),
            SimpleNamespace(key="paired", kind='FLAG', text="", number=0.0, path="", flag=True),
            SimpleNamespace(key="set", kind='TEXT', text="painted", number=0.0, path="", flag=False),
            SimpleNamespace(key="", kind='TEXT', text="ignored", number=0.0, path="", flag=False)]
    assert studio_ops.plan_args(rows) == {"polycount": 30000, "prompt_file": "plates/front.png", "paired": True, "set": "painted"}


def test_one_glow_per_panel(panel):
    """The waiting spend is the one lamplit thing; a maybe-sent job keeps its two actions visible but does not glow."""
    studio_state.STATE["approvals"] = [{"id": "a1", "state": "pending", "label": "Smart Mesh", "price": 30, "studio": "tripo",
                                        "settings": {"unit": "credits"}}]
    studio_state.STATE["receipts"] = [{"key": "k1", "label": "Smart Mesh", "state": "submission_unknown", "provider": "tripo",
                                       "actions": ["acknowledge", "link"]}]
    layout = _draw(panel)
    lit = [e for e in layout.log if e[0] == "op" and e[4]]
    assert len(lit) == 1 and lit[0][1] == "lampway.studio_confirm", lit
