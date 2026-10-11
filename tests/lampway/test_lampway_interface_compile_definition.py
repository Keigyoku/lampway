# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Native editor fork guards must be enabled on their own CMake targets.

The creator directory's definitions do not propagate into sibling editor
directories. These source gates retain the ON/OFF scope and plant corruptions;
the native build crew still verifies the resulting compiler command.
"""

from pathlib import Path
import re

import pytest


ROOT = Path(__file__).resolve().parents[2]
INTERFACE = ROOT / 'src/source/blender/editors/interface/CMakeLists.txt'
VIEW3D = ROOT / 'src/source/blender/editors/space_view3d/CMakeLists.txt'


def assert_interface_fork_definition(source, name='bf_editor_interface'):
    code = re.sub(r'#[^\n]*', '', source)
    target = re.search(r'blender_add_lib\(' + re.escape(name) + r'\b[^)]*\)', code)
    assert target, 'the interface library must exist before its target definition'
    guarded = re.search(
        r'if\(LAMPWAY\)\s*'
        r'target_compile_definitions\(' + re.escape(name) + r'\s+PRIVATE\s+LAMPWAY\)\s*'
        r'endif\(\)', code,
    )
    assert guarded, f'{name} needs its own PRIVATE definition only when LAMPWAY is ON'
    assert target.end() < guarded.start(), 'define the macro after creating the target'
    # No second, unconditional definition may enable fork branches in OFF builds.
    definitions = re.findall(r'target_compile_definitions\(' + re.escape(name) + r'\s+[^)]*\bLAMPWAY\b[^)]*\)', code)
    assert len(definitions) == 1, 'the fork macro must have exactly one guarded owner'


def test_interface_target_compiles_its_lampway_branches_only_for_fork_builds():
    source = INTERFACE.read_text()
    assert_interface_fork_definition(source)
    # Pin the concrete Docs/Report a Bug consumer, not just an unused macro.
    assert 'interface_mixar_profile_card.cc' in source
    profile = (INTERFACE.parent / 'interface_mixar_profile_card.cc').read_text()
    branch = re.search(r'#ifdef LAMPWAY(.*?)#else(.*?)#endif', profile, flags=re.S)
    assert branch, 'profile actions must keep their fork/upstream branches'
    assert 'MIXIE_CHAT_OT_open_docs' in branch.group(1)
    assert 'MIXIE_CHAT_OT_report_bug' in branch.group(1)
    assert 'WM_OT_url_open' not in branch.group(1)
    assert 'WM_OT_url_open' in branch.group(2)


def test_view3d_target_compiles_its_palette_branches_only_for_fork_builds():
    source = VIEW3D.read_text()
    assert_interface_fork_definition(source, 'bf_editor_space_view3d')
    for filename, fork_tokens, upstream_tokens in (
        ('view3d_moodboard_drawer_draw.cc', ['CinemaPillOnB'], ['Selected']),
        ('view3d_director_cinema_top.cc', ['CinemaBrandTop', 'CinemaBrandBottom'], ['CinemaPillOnA', 'CinemaPillOnB']),
    ):
        assert filename in source
        consumer = (VIEW3D.parent / filename).read_text()
        branch = re.search(r'#ifdef LAMPWAY(.*?)#else(.*?)#endif', consumer, flags=re.S)
        assert branch, f'{filename} must keep its fork/upstream palette branches'
        assert all(token in branch.group(1) for token in fork_tokens)
        assert all(token in branch.group(2) for token in upstream_tokens)


@pytest.mark.parametrize('name', ['bf_editor_interface', 'bf_editor_space_view3d'])
@pytest.mark.parametrize('corruption', ['missing', 'wrong_target', 'public', 'unconditional', 'before_target'])
def test_interface_definition_gate_rejects_broken_target_and_option_scope(corruption, name):
    target = 'blender_add_lib(' + name + ' "${SRC}" "${INC}" "${INC_SYS}" "${LIB}")\n'
    guarded = 'if(LAMPWAY)\n  target_compile_definitions(' + name + ' PRIVATE LAMPWAY)\nendif()\n'
    source = target + guarded
    if corruption == 'missing':
        source = target
    elif corruption == 'wrong_target':
        source = target + guarded.replace(name, 'mixar')
    elif corruption == 'public':
        source = source.replace('PRIVATE', 'PUBLIC')
    elif corruption == 'unconditional':
        source += 'target_compile_definitions(' + name + ' PRIVATE LAMPWAY)\n'
    else:
        source = guarded + target
    with pytest.raises(AssertionError):
        assert_interface_fork_definition(source, name)
