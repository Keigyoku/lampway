# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0's separate native mode chip. Source evidence only; no native build proof."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / 'src/source/blender/editors/space_agent_bubble'
MENU = ROOT / 'src/scripts/mixar/modules/byok/ui/menus/agent_model_menu.py'


def test_mode_chip_uses_one_rect_for_paint_and_menu_beside_model():
    layout = (NATIVE / 'agent_ui_layout.cc').read_text()
    assert 'place(layout.chip_agent_mode, fit.width[AGENT_CHIP_SLOT_AGENT_MODE]);' in layout
    assert layout.index('place(layout.chip_agent_mode,') < layout.index('place(layout.chip_model,')
    state = (NATIVE / 'agent_ui_state.cc').read_text()
    assert '"lampway_agent_mode"' in state and 'r_state->agent_byoa' in state
    paint = (NATIVE / 'agent_ui_controls_paint.cc').read_text()
    assert 'layout->chip_agent_mode' in paint and 'state->agent_byoa' in paint
    source = (NATIVE / 'space_agent_bubble.cc').read_text()
    assert 'agent_bubble_rect_to_region(region, layout->chip_agent_mode,' in source
    assert 'WM_menutype_find("MIXIE_CHAT_MT_agent_mode", false)' in source


def test_mode_chip_is_a_fitted_core_control_with_an_icon_floor():
    source = (NATIVE / 'agent_ui_chip_fit.hh').read_text()
    assert 'AGENT_CHIP_SLOT_AGENT_MODE' in source
    assert 'bool agent_mode_available = false;' in source
    assert 'r_chips[AGENT_CHIP_SLOT_AGENT_MODE]' in source
    assert 'width(in.agent_byoa ? LAMPWAY_YOUR_AGENT_NAME : LAMPWAY_AGENT_NAME, m.icon)' in source
    assert 'AGENT_CHIP_SLOT_AGENT_MODE,' in source[source.index('AGENT_CHIP_SHED_ORDER[]'):]


def test_mode_menu_is_registered_and_model_picker_leaves_switching_to_it():
    source = MENU.read_text()
    tree = ast.parse(source)
    modes = next((n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'MIXIE_CHAT_MT_agent_mode'), None)
    assert modes is not None, 'Separate mode menu is missing'
    assert 'AM.draw_rows(' in ast.get_source_segment(source, modes)
    model = next(n for n in ast.walk(tree) if isinstance(n, ast.ClassDef) and n.name == 'MIXIE_CHAT_MT_agent_model')
    body = ast.get_source_segment(source, model)
    assert 'AM.draw_rows(' not in body
    assert 'AM.is_byoa(' in body and 'AM.MODEL_NOTE' in body
    assert 'MIXIE_CHAT_MT_agent_mode,' in source[source.index('classes = ('):]
