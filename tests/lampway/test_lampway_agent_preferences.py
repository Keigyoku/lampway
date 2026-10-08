# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Agent preferences expose the server's experimental Hermes switches, never local defaults."""
import importlib
import sys
from types import SimpleNamespace

import pytest

from test_lampway_capabilities_ui import Recorder, door, load, press, row, ui
from mixar.modules.lampway_tools import capabilities_face, capabilities_state as state, human_gate

FEATURES = ('subagents', 'schedule', 'background')


@pytest.fixture
def preferences(ui, monkeypatch):
    name = 'mixar.modules.lampway_tools.ui.agent_pill_pref'
    monkeypatch.setattr(sys.modules['bpy.types'], 'Panel', object, raising=False)
    monkeypatch.delitem(sys.modules, name, raising=False)
    module = importlib.import_module(name)
    monkeypatch.setattr(Recorder, 'prop', lambda self, data, key: self.log.append(('prop', key)), raising=False)
    yield module
    sys.modules.pop(name, None)


def draw(preferences):
    layout = Recorder()
    panel = preferences.LAMPWAY_PT_agent_pill_preferences()
    panel.layout = layout
    panel.draw(SimpleNamespace(window_manager=SimpleNamespace()))
    return layout


def test_agent_preferences_show_server_default_off_controls_and_persistent_warning(preferences, door):
    load(*(row(cid, risk='runs_code', default=False) for cid in FEATURES))
    layout = draw(preferences)
    switches = layout.ops('lampway.capability_switch')
    assert [x[4].cap_id for x in switches] == list(FEATURES)
    assert all(x[4].enabled is True and x[4].confirm is False and x[3] == 'CHECKBOX_DEHLT' for x in switches)
    assert 'untested layering' in ' '.join(layout.labels())
    assert door.calls == [], 'drawing cached defaults must not read or write the server'


def test_preferences_do_not_invent_defaults_before_server_refresh(preferences, door):
    state.reset()
    layout = draw(preferences)
    assert not layout.ops('lampway.capability_switch')
    assert layout.ops('lampway.capabilities_refresh')
    assert 'untested layering' in ' '.join(layout.labels())
    assert door.calls == []


def test_preferences_display_existing_opt_in_and_toggle_it_off(preferences, ui, door):
    load(*(row(cid, enabled=True, risk='runs_code') for cid in FEATURES))
    layout = draw(preferences)
    switches = layout.ops('lampway.capability_switch')
    assert [x[4].cap_id for x in switches] == list(FEATURES)
    assert all(x[4].enabled is False and x[3] == 'CHECKBOX_HLT' for x in switches)
    assert 'untested layering' in ' '.join(layout.labels())
    props = switches[0][4]
    result, _ = press(ui.LAMPWAY_OT_capability_switch, **vars(props))
    assert result == {'FINISHED'}
    assert door.calls[0]['enabled'] is False


@pytest.mark.parametrize('cid', FEATURES)
def test_every_surface_requires_untested_layering_warning_and_explicit_opt_in(ui, door, cid):
    # These feature IDs retain the warning even if a server changes their risk category.
    load(row(cid, risk='reads'))
    assert capabilities_face.needs_confirm(state.STATE['rows'][0])
    assert 'untested layering' in capabilities_face.warning(state.STATE['rows'][0])
    result, _ = press(ui.LAMPWAY_OT_capability_switch, cap_id=cid, enabled=True, confirm=False)
    assert result == {'FINISHED'} and not door.calls and state.STATE['pending'] == cid
    result, _ = press(ui.LAMPWAY_OT_capability_switch, cap_id=cid, enabled=True, confirm=True)
    assert result == {'FINISHED'} and door.calls[0]['enabled'] is True


@pytest.mark.parametrize('cid', FEATURES)
def test_confirm_flag_without_the_feature_warning_open_does_not_opt_in(ui, door, cid):
    load(row(cid, risk='runs_code'))
    result, _ = press(ui.LAMPWAY_OT_capability_switch, cap_id=cid, enabled=True, confirm=True)
    assert result == {'FINISHED'} and not door.calls and state.STATE['pending'] == cid


@pytest.mark.parametrize('cid', FEATURES)
def test_disabling_each_feature_needs_no_confirmation(ui, door, cid):
    load(row(cid, enabled=True, risk='runs_code'))
    result, _ = press(ui.LAMPWAY_OT_capability_switch, cap_id=cid, enabled=False, confirm=False)
    assert result == {'FINISHED'} and door.calls[0]['enabled'] is False
    assert state.STATE['pending'] == ''


def test_stale_preferences_do_not_offer_cached_feature_switches(preferences, door):
    load(*(row(cid, enabled=True, risk='runs_code') for cid in FEATURES), ok=False)
    layout = draw(preferences)
    assert not layout.ops('lampway.capability_switch') and not door.calls
    assert 'untested layering' in ' '.join(layout.labels())


def test_preferences_confirmation_prompt_points_to_the_visible_warning(preferences, ui, door):
    load(row('subagents', risk='runs_code'))
    switch = draw(preferences).ops('lampway.capability_switch')[0][4]
    result, messages = press(ui.LAMPWAY_OT_capability_switch, **vars(switch))
    assert result == {'FINISHED'} and not door.calls
    assert messages[-1][1] == 'Read the warning below and confirm to let your agent use subagents'
    confirmation = draw(preferences).ops('lampway.capability_switch')[-1][4]
    assert confirmation.cap_id == 'subagents' and confirmation.enabled and confirmation.confirm


@pytest.mark.parametrize('cid', FEATURES)
def test_feature_opt_in_is_refused_to_scripts(ui, door, monkeypatch, cid):
    load(row(cid, risk='runs_code'))
    monkeypatch.setattr(human_gate, 'script_running', lambda: True)
    result, _ = press(ui.LAMPWAY_OT_capability_switch, cap_id=cid, enabled=True, confirm=True)
    assert result == {'CANCELLED'} and not door.calls
