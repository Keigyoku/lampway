# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real GUI T2 acceptance on a new isolated Xvfb, never an inherited DISPLAY."""
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import socket
import time
import urllib.request
import sys

import pytest

from issue2_graphics import prepare_environment, validate_renderer


def test_issue2_onboarding_and_native_target_labels(tmp_path, request):
    binary = os.environ.get('LAMPWAY_VIEW_BIN')
    xvfb = os.environ.get('LAMPWAY_VIEW_XVFB') or shutil.which('Xvfb')
    if not binary or not xvfb:
        pytest.skip('LAMPWAY_VIEW_BIN and isolated Xvfb required; desktop pixels unverified')
    env = prepare_environment(os.environ)
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_STATE_HOME', 'XDG_CACHE_HOME',
                'XDG_RUNTIME_DIR', 'LAMPWAY_HOME', 'LAMPWAY_LEGACY_HOME', 'TMPDIR'):
        path = tmp_path / key.lower()
        path.mkdir(mode=0o700)
        env[key] = str(path)
    project = tmp_path / 'project'
    project.mkdir()
    import importlib.util
    module_path = Path(__file__).resolve().parents[2] / 'server/lampway_server/egress.py'
    spec = importlib.util.spec_from_file_location('issue2_egress', module_path)
    import sys
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    routes = [dict(id=r.id, label=r.label, hosts=list(r.hosts), retention=r.retention,
                   training=r.training, privacy_class=r.privacy_class, enabled=False) for r in module.ROUTES.values()]
    (project / 'routes.json').write_text(json.dumps(routes))
    env.update(LAMPWAY_PROJECT_ROOT=str(project), LAMPWAY_TEST_ROOT=str(tmp_path),
               LAMPWAY_VIEW_OVERLAY=str(Path(__file__).resolve().parents[2] / 'src/scripts'),
               LAMPWAY_BACKEND_URL='http://127.0.0.1:9', LAMPWAY_BRIDGE_PORT='0')
    # The native build can have older installed Python. Merge the current
    # public overlay into a disposable copy rather than syncing that build.
    installed = list(Path(binary).resolve().parent.glob('*/scripts'))
    assert len(installed) == 1, 'one installed script tree required'
    scripts = tmp_path / 'runtime-scripts'
    shutil.copytree(installed[0], scripts, ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copytree(Path(__file__).resolve().parents[2] / 'src/scripts', scripts,
                    dirs_exist_ok=True, ignore=shutil.ignore_patterns('__pycache__'))
    runtime = tmp_path / 'runtime-bin'
    runtime.mkdir()
    runtime_binary = runtime / Path(binary).name
    subprocess.run(['cp', '--reflink=auto', binary, str(runtime_binary)], check=True)
    for entry in Path(binary).resolve().parent.iterdir():
        if entry.name == Path(binary).name:
            continue
        if entry == installed[0].parent:
            version = runtime / entry.name
            version.mkdir()
            for child in entry.iterdir():
                (version / child.name).symlink_to(scripts if child.name == 'scripts' else child, target_is_directory=child.is_dir())
        else:
            (runtime / entry.name).symlink_to(entry, target_is_directory=entry.is_dir())
    env.pop('WAYLAND_DISPLAY', None)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    env.update(LAMPWAY_PORT=str(port), LAMPWAY_HOST='127.0.0.1', LAMPWAY_PROVIDER='mock',
               LAMPWAY_STATE_DIR=str(tmp_path / 'server-state'), LAMPWAY_BACKEND_URL=f'http://127.0.0.1:{port}')
    server_env = dict(env, PYTHONPATH=str(Path(__file__).resolve().parents[2] / 'server'))
    server_log = (tmp_path / 'backend.log').open('w')
    backend = subprocess.Popen([sys.executable, '-m', 'lampway_server'], env=server_env, stdout=server_log, stderr=subprocess.STDOUT)
    def cleanup_backend():
        if backend.poll() is None:
            backend.terminate()
            backend.wait(timeout=10)
        server_log.close()
    request.addfinalizer(cleanup_backend)
    deadline = time.monotonic() + 15
    while True:
        try:
            urllib.request.urlopen(env['LAMPWAY_BACKEND_URL'] + '/app', timeout=.5).close()
            break
        except Exception:
            assert backend.poll() is None and time.monotonic() < deadline, 'mock backend startup failed'
            time.sleep(.1)
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
            result = subprocess.run([str(runtime_binary), '--factory-startup', '--enable-event-simulate', '--disable-autoexec',
                                     '--python-exit-code', '1', '--python',
                                     str(Path(__file__).with_name('issue2_gui_fixture.py'))],
                                    env=env, capture_output=True, text=True, timeout=150)
            output = result.stdout + result.stderr
            (tmp_path / 'gui.log').write_text(output)
            assert result.returncode == 0, output[-8000:]
            failure = project / 'failure.txt'
            assert not failure.exists(), failure.read_text() if failure.exists() else ''
            assert (project / 'receipt.json').exists(), output[-8000:]
            receipt = json.loads((project / 'receipt.json').read_text())
            assert receipt['step1']['frame']['width'] > 0
            assert receipt['graphics']['requested_software_gl'] == env['LAMPWAY_VIEW_SOFTWARE_GL']
            validate_renderer(env['LAMPWAY_VIEW_SOFTWARE_GL'], receipt['graphics']['renderer'])
            assert receipt['popup_recovered'] is True
            assert receipt['browser_opens'] == []
            assert len(receipt['steps']) == 4
            assert all(t['label'].strip() for t in receipt['observed']['targets'])
        finally:
            os.close(read_fd)
            server.terminate()
            server.wait(timeout=10)
