# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Facelift decision F2: Lampway Night is the default for new profiles, an existing profile keeps its own colours and
is offered Night once (a toast with one button), and Mixar's Forest is no longer offered."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

ROOT = Path(__file__).resolve().parents[2]
NIGHT = ROOT / "src/scripts/presets/interface_theme/Lampway_Night.xml"
FOREST = ROOT / "src/release/datafiles/userdef/Mixar_theme.xml"


def theme_from(xml_path):
    """The three fingerprint colours of a theme file, shaped like bpy's theme (floats 0..1)."""
    import xml.etree.ElementTree as ET
    theme = ET.parse(xml_path).getroot().find("Theme")

    def colour(path, attr):
        hx = theme.find(path).attrib[attr][1:]
        return tuple(int(hx[i:i + 2], 16) / 255 for i in range(0, len(hx), 2))

    return SimpleNamespace(
        user_interface=SimpleNamespace(
            mixar_canvas=colour("user_interface/ThemeUserInterface", "mixar_canvas"),
            wcol_regular=SimpleNamespace(inner=colour("user_interface/ThemeUserInterface/wcol_regular/ThemeWidgetColors",
                                                      "inner"))),
        view_3d=SimpleNamespace(space=SimpleNamespace(gradients=SimpleNamespace(high_gradient=colour(
            "view_3d/ThemeView3D/space/ThemeSpaceGradient/gradients/ThemeGradientColors", "high_gradient")))))


class Config:
    def __init__(self, **saved):
        self.saved = dict(saved)

    def get_config(self):
        return self.saved

    def add_config(self, key, value):
        self.saved[key] = value
        return True


@pytest.fixture
def night():
    from mixar.modules.common.core import lampway_night
    return lampway_night


def test_a_new_profile_already_wears_night_and_is_never_asked(night):
    config, store = Config(), MagicMock()
    assert night.offer_once(theme_from(NIGHT), str(NIGHT), config, store) == "wears-night"
    store.push.assert_not_called()
    assert config.saved[night.OFFERED_KEY] is True


def test_an_existing_profile_keeps_its_colours_and_is_offered_night_once(night):
    config, store = Config(), MagicMock()
    forest = theme_from(FOREST)
    assert night.offer_once(forest, str(NIGHT), config, store) == "offered"
    store.push.assert_called_once()
    kwargs = store.push.call_args.kwargs
    assert kwargs["title"] == "Try Lampway Night"
    assert [(a.label, a.operator) for a in kwargs["actions"]] == [("Try Lampway Night", "lampway.apply_night_theme")]
    assert kwargs["dismissible"] is True
    assert forest.user_interface.mixar_canvas == theme_from(FOREST).user_interface.mixar_canvas  # nothing applied
    assert night.offer_once(forest, str(NIGHT), config, store) == "already-offered"
    store.push.assert_called_once()


def test_the_offer_waits_for_a_ui_session_and_never_runs_headless(night, monkeypatch):
    headless = SimpleNamespace(app=SimpleNamespace(background=True, timers=MagicMock()))
    assert night.schedule_offer(headless) is False
    headless.app.timers.register.assert_not_called()

    forest = theme_from(FOREST)
    ui = SimpleNamespace(app=SimpleNamespace(background=False, timers=MagicMock()),
                         utils=SimpleNamespace(preset_paths=lambda _kind: [str(NIGHT.parent)]),
                         context=SimpleNamespace(preferences=SimpleNamespace(themes=[forest])))
    config, store = Config(), MagicMock()
    import mixar.config.config as real_config
    import mixar.modules.common.notifications.store as real_store
    monkeypatch.setattr(real_config, "get_config", config.get_config)
    monkeypatch.setattr(real_config, "add_config", config.add_config)
    monkeypatch.setattr(real_store, "get_notification_store", lambda: store)
    assert night.schedule_offer(ui) is True
    (offer,), kwargs = ui.app.timers.register.call_args
    assert kwargs["first_interval"] > 0
    assert offer() is None  # a one-shot timer
    store.push.assert_called_once()
    assert config.saved[night.OFFERED_KEY] is True


def test_startup_schedules_the_offer():
    import ast
    tree = ast.parse((ROOT / "src/scripts/startup/bootstrap/__init__.py").read_text(encoding="utf-8"))
    register = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "register")
    calls = {ast.unparse(n.func) for n in ast.walk(register) if isinstance(n, ast.Call)}
    assert "schedule_offer" in {c.rsplit(".", 1)[-1] for c in calls}, sorted(calls)


def test_the_theme_panel_offers_night_and_no_longer_offers_forest(monkeypatch):
    import bpy
    monkeypatch.setattr(sys.modules["bpy.types"], "Panel", object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.common.ui.panels.theme_panel", raising=False)
    from mixar.modules.common.ui.panels.theme_panel import MIXAR_PT_theme_preferences

    layout = MagicMock()
    layout.panel.return_value = (MagicMock(), None)
    theme = MagicMock()
    theme.user_interface.bl_rna.properties = []
    context = SimpleNamespace(preferences=SimpleNamespace(themes=[theme]))
    monkeypatch.setattr(bpy, "context", context, raising=False)
    MIXAR_PT_theme_preferences.draw(SimpleNamespace(layout=layout), context)
    operators = [c[1][0] for c in layout.mock_calls if c[0].endswith("operator") and c[1]]
    assert "lampway.apply_night_theme" in operators
    assert "mixar.apply_forest_theme" not in operators


def test_forest_is_not_registered_as_an_operator(monkeypatch):
    monkeypatch.setattr(sys.modules["bpy.types"], "Operator", object, raising=False)
    monkeypatch.delitem(sys.modules, "mixar.modules.common.ui.operators.theme_ops", raising=False)
    from mixar.modules.common.ui.operators import theme_ops
    idnames = [c.bl_idname for c in theme_ops.classes]
    assert "lampway.apply_night_theme" in idnames
    assert "mixar.apply_forest_theme" not in idnames
