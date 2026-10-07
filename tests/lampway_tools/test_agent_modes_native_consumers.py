# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual native consumers, ON/OFF, in the configured build's include context.

This runs GCC preprocessing and syntax checks of real translation units, not
an OFF Blender build or a substitute for the final ON native link receipt.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONSUMERS = {
    'interface_mixar_profile_card.cc': ('interface', 'bf_editor_interface'),
    'view3d_moodboard_drawer_draw.cc': ('space_view3d', 'bf_editor_space_view3d'),
    'view3d_director_cinema_top.cc': ('space_view3d', 'bf_editor_space_view3d'),
    'agent_ui_controls_paint.cc': ('space_agent_bubble', 'bf_editor_space_agent_bubble'),
}


def cached_command(row):
    return row.get('arguments') or shlex.split(row['command'])


def require_cached_on(args, target):
    assert '-DLAMPWAY' in args or '-DLAMPWAY=1' in args, (
        f'Configured ON target {target} lacks its actual LAMPWAY compiler definition')


def consumer_command(args, enabled, preprocess=False):
    # Never reuse object/dependency outputs from the live build tree.
    result, skip = [], False
    paired = {'-o', '-MF', '-MT', '-MQ', '-MJ', '--serialize-diagnostics'}
    for arg in args:
        if skip:
            skip = False
            continue
        if arg in paired:
            skip = True
        elif arg in {'-c', '-MD', '-MMD', '-MP', '-M', '-MM'}:
            continue
        elif arg == '-DLAMPWAY' or arg.startswith('-DLAMPWAY=') or arg == '-ULAMPWAY':
            continue
        else:
            result.append(arg)
    result += ['-DLAMPWAY' if enabled else '-ULAMPWAY']
    result += ['-E', '-P'] if preprocess else ['-fsyntax-only']
    return result


def witnesses(filename, text, enabled):
    if filename == 'interface_mixar_profile_card.cc':
        on = 'add_action(&bottom, "MIXIE_CHAT_OT_open_docs"'
        off = 'PointerRNA docs = bottom.op("WM_OT_url_open"'
        assert (on in text) == enabled and (off in text) != enabled
        expected = on if enabled else off
        if enabled:
            assert 'add_action(&bottom, "MIXIE_CHAT_OT_report_bug"' in text
        return [line.strip() for line in text.splitlines() if expected in line]
    if filename == 'agent_ui_controls_paint.cc':
        assert ('AGENT_CHIP_SLOT_AGENT_MODE' in text) == enabled
        needle = 'chip_form[AGENT_CHIP_SLOT_AGENT_MODE]'
        return [line.strip() for line in text.splitlines() if needle in line]
    variables = {'outer_green': 'CinemaPillOnB' if enabled else 'Selected'} if filename.startswith('view3d_moodboard') else {
        'brand_top': 'CinemaBrandTop' if enabled else 'CinemaPillOnA',
        'brand_bottom': 'CinemaBrandBottom' if enabled else 'CinemaPillOnB'}
    found = []
    for variable, slot in variables.items():
        pattern = r'mixar_theme_color_f\s*\(\s*blender::ui::MixarThemeSlot::(\w+)\s*,\s*' + variable + r'\s*\)'
        actual = re.findall(pattern, text)
        assert actual == [slot], (filename, variable, actual, slot)
        found.extend(line.strip() for line in text.splitlines() if re.search(pattern, line))
    return found


@pytest.mark.parametrize('filename', list(CONSUMERS))
@pytest.mark.parametrize('enabled', [False, True], ids=['OFF', 'ON'])
def test_actual_native_consumer_compiler_branches(filename, enabled):
    build = Path(os.environ.get('LAMPWAY_BUILD_DIR') or ROOT / 'build/Prod')
    cache = build / 'compile_commands.json'
    assert cache.is_file(), f'No configured native compiler context at {cache}'
    assert re.search(r'^LAMPWAY:BOOL=ON$', (build / 'CMakeCache.txt').read_text(), re.M)
    rows = json.loads(cache.read_text())
    row = next(r for r in rows if Path(r['file']).name == filename)
    directory, target = CONSUMERS[filename]
    tracked = ROOT / 'src/source/blender/editors' / directory / filename
    mirror = Path(row['file'])
    assert tracked.read_bytes() == mirror.read_bytes(), f'Build mirror differs from tracked consumer {tracked}'
    args = cached_command(row)
    require_cached_on(args, target)
    syntax = consumer_command(args, enabled)
    checked = subprocess.run(syntax, cwd=row['directory'], capture_output=True, text=True, timeout=180)
    assert checked.returncode == 0, checked.stdout + checked.stderr
    expanded = consumer_command(args, enabled, preprocess=True)
    pp = subprocess.run(expanded, cwd=row['directory'], capture_output=True, text=True, timeout=180)
    assert pp.returncode == 0, pp.stderr
    branch = witnesses(filename, pp.stdout, enabled)
    receipt = {'scope': 'actual translation-unit syntax/preprocess ON/OFF; not a full OFF Blender build',
               'target': target, 'enabled': enabled, 'source': str(tracked), 'mirror': str(mirror),
               'source_sha256': hashlib.sha256(tracked.read_bytes()).hexdigest(),
               'cached_on_command': args, 'syntax_command': syntax, 'preprocess_command': expanded,
               'directory': row['directory'], 'branch_witness': branch,
               'preprocessed_sha256': hashlib.sha256(pp.stdout.encode()).hexdigest()}
    out = os.environ.get('LAMPWAY_NATIVE_CONSUMER_ARTIFACTS')
    if out:
        root = Path(out); root.mkdir(parents=True, exist_ok=True)
        (root / (filename + ('.ON.json' if enabled else '.OFF.json'))).write_text(json.dumps(receipt, indent=2))


@pytest.mark.parametrize('target', sorted({target for _, target in CONSUMERS.values()}))
def test_actual_command_gate_rejects_missing_target_definition(target):
    with pytest.raises(AssertionError, match='lacks its actual LAMPWAY compiler definition'):
        require_cached_on(['g++', '-DOTHER', '-c', 'consumer.cc'], target)
