# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Isolated real-binary T2 focus test; imports the overlay without syncing an installed app."""
import json
import os
from pathlib import Path
import subprocess

import pytest


def test_focus_bounds_selection_and_hidden_target_on_real_binary(tmp_path):
    binary = os.environ.get('LAMPWAY_VIEW_BIN')
    if not binary:
        pytest.skip('LAMPWAY_VIEW_BIN required; this test never syncs the installed app')
    overlay = str(Path(__file__).resolve().parents[2] / 'src/scripts')
    script = tmp_path / 'focus.py'
    script.write_text('''import sys, json
sys.path.insert(0, OVERLAY)
import bpy, mixar, mixar.modules
mixar.__path__.insert(0, OVERLAY + '/mixar')
mixar.modules.__path__.insert(0, OVERLAY + '/mixar/modules')
from mixar.modules import lampway_tools
lampway_tools.__path__.insert(0, OVERLAY + '/mixar/modules/lampway_tools')
from mixar.modules.lampway_tools import api_view
from mixar.modules.lampway_tools.view import runtime
assert api_view.__file__.startswith(OVERLAY)
assert runtime.__file__.startswith(OVERLAY)
assert api_view.view(action='screenshot',area='INVENTED_EDITOR')['code']=='bad_argument'
assert 'ShaderNodeTree' in api_view.view(action='help')['arguments']['area']
try:
    runtime.find_area(bpy.context.window,'ShaderNodeTree')
except runtime.ViewError as exc:
    assert exc.code=='no_area',exc.code
else:
    raise AssertionError('factory window unexpectedly has a shader editor')
cube = bpy.data.objects['Cube']
cube.location = (3, 4, 5)
bpy.context.view_layer.update()
selected = sorted(o.name for o in bpy.context.selected_objects)
active = bpy.context.view_layer.objects.active
result = api_view.view(action='focus', object='Cube', shot=False)
assert result.get('object') == 'Cube', result
area = next(a for a in bpy.context.window.screen.areas if a.type == 'VIEW_3D')
assert all(abs(a-b) < 1e-5 for a,b in zip(area.spaces.active.region_3d.view_location, (3,4,5)))
assert selected == sorted(o.name for o in bpy.context.selected_objects)
assert active == bpy.context.view_layer.objects.active
cube.hide_set(True)
assert api_view.view(action='focus', object='Cube', shot=False)['code'] == 'hidden'
result = api_view.view(action='focus', object='Cube', shot=False, unhide=True)
assert result.get('unhidden') is True, result
assert not cube.hide_get()
print('VIEW_RESULT ' + json.dumps({'overlay': api_view.__file__, 'location': list(area.spaces.active.region_3d.view_location), 'unhidden': True}))
'''.replace('OVERLAY', repr(overlay)))
    env = os.environ.copy()
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        folder = tmp_path / key.lower()
        folder.mkdir()
        env[key] = str(folder)
    env['LAMPWAY_PROJECT_ROOT'] = str(tmp_path / 'project')
    run = subprocess.run([binary, '--background', '--factory-startup', '--disable-autoexec',
                          '--python-exit-code', '1', '--python', str(script)], env=env,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=60)
    assert run.returncode == 0, run.stdout[-6000:]
    rows = [line.removeprefix('VIEW_RESULT ') for line in run.stdout.splitlines() if line.startswith('VIEW_RESULT ')]
    assert len(rows) == 1, run.stdout[-6000:]
    assert json.loads(rows[0])['location'] == [3, 4, 5]
