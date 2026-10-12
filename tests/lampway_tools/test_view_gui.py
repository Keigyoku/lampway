# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real GUI T2 acceptance on a new isolated Xvfb, never an inherited DISPLAY."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess

import pytest


def test_masked_editors_real_undo_and_repeated_async_stills(tmp_path):
    binary = os.environ.get('LAMPWAY_VIEW_BIN')
    xvfb = os.environ.get('LAMPWAY_VIEW_XVFB') or shutil.which('Xvfb')
    if not binary or not xvfb:
        pytest.skip('LAMPWAY_VIEW_BIN and isolated Xvfb required; desktop pixels unverified')
    env = os.environ.copy()
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'XDG_RUNTIME_DIR', 'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        path = tmp_path / key.lower()
        path.mkdir(mode=0o700)
        env[key] = str(path)
    project = tmp_path / 'project'
    project.mkdir()
    env.update(LAMPWAY_PROJECT_ROOT=str(project), LAMPWAY_TEST_ROOT=str(tmp_path),
               LAMPWAY_VIEW_OVERLAY=str(Path(__file__).resolve().parents[2] / 'src/scripts'),
               LIBGL_ALWAYS_SOFTWARE='1', LAMPWAY_BACKEND_URL='http://127.0.0.1:9', LAMPWAY_BRIDGE_PORT='0')
    env.pop('WAYLAND_DISPLAY', None)
    read_fd, write_fd = os.pipe()
    with (tmp_path / 'xvfb.log').open('w') as log:
        server = subprocess.Popen([xvfb, '-displayfd', str(write_fd), '-screen', '0',
                                   '1280x900x24', '-nolisten', 'tcp'], pass_fds=(write_fd,),
                                  stdout=log, stderr=subprocess.STDOUT)
        os.close(write_fd)
        try:
            assert select.select([read_fd], [], [], 15)[0], 'isolated Xvfb did not start'
            number = os.read(read_fd, 32).decode().strip()
            assert number.isdigit(), (tmp_path / 'xvfb.log').read_text()
            env['DISPLAY'] = ':' + number
            result = subprocess.run([binary, '--factory-startup', '--enable-event-simulate', '--disable-autoexec',
                                     '--python-exit-code', '1', '--python',
                                     str(Path(__file__).with_name('view_gui_fixture.py'))],
                                    env=env, capture_output=True, text=True, timeout=150)
            output = result.stdout + result.stderr
            (tmp_path / 'gui.log').write_text(output)
            assert result.returncode == 0, output[-8000:]
            failure = project / 'failure.txt'
            assert not failure.exists(), failure.read_text() if failure.exists() else ''
            assert (project / 'receipt.json').exists(), output[-8000:]
            receipt = json.loads((project / 'receipt.json').read_text())
            assert len(receipt['captures']) == 3
            assert all(item['image']['bytes'] <= 50000 for item in receipt['captures'])
            assert receipt['mask_pixel'] == [0, 0, 0]
            assert [item['path'] for item in receipt['renders']] == ['renders/still.png', 'renders/still-2.png']
            assert receipt.get('current_render', {}).get('image', {}).get('width') == 320
            assert receipt['current_render']['image']['height'] == 240
            assert receipt['current_receipt']['preset'] == 'current'
        finally:
            os.close(read_fd)
            server.terminate()
            server.wait(timeout=10)
