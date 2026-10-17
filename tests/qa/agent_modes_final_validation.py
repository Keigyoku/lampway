# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Serial final PR4 validation packet after the owner finishes the combined build.

Run under the configured cloud native-env.sh. This never syncs native source,
configures CMake, builds Ninja targets or writes BUILT_FROM. Existing binary
fixtures refresh only the Python install through their documented helper.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def fingerprint(binary, build, expected):
    assert git('rev-parse', 'HEAD') == expected, 'HEAD differs from the requested final build commit'
    assert (build / 'BUILT_FROM').read_text().strip() == expected, 'BUILT_FROM must be the exact final commit'
    assert not git('status', '--porcelain', '--untracked-files=all'), (
        'tracked or untracked changes would mix the proof with another source state')
    native_state = subprocess.check_output([str(ROOT / 'scripts/lampway/built_from.sh'),
                                           'state', str(ROOT)], text=True).strip()
    assert native_state == expected, f'Native state is not the clean pushed final commit: {native_state}'
    git('ls-files', '--error-unmatch', 'tests/qa/agent_modes_final_validation.py',
        'tests/lampway_tools/test_agent_modes_native_consumers.py',
        'tests/lampway_tools/test_agent_modes_workers_stop_live.py')
    return {'head': expected, 'built_from': expected, 'binary': str(binary),
            'sha256': digest(binary), 'bytes': binary.stat().st_size,
            'compile_commands_sha256': digest(build / 'compile_commands.json'),
            'cmake_cache_sha256': digest(build / 'CMakeCache.txt')}


def checked(command, env, log, timeout):
    with log.open('w') as output:
        result = subprocess.run(command, cwd=ROOT, env=env, stdout=output,
                                stderr=subprocess.STDOUT, timeout=timeout)
    assert result.returncode == 0, f'{command[0]} failed; see {log}'


def junit(path):
    tree = ET.parse(path)
    cases = tree.findall('.//testcase')
    bad = [case.get('name') for case in cases if any(case.find(kind) is not None
           for kind in ('failure', 'error', 'skipped'))]
    assert cases and not bad, f'Validation requires actual passes without skips: {bad}; see {path}'
    return {'passed': len(cases), 'seconds': sum(float(c.get('time', 0)) for c in cases)}


def capture_native_commands(build, out):
    """Read-only Ninja command expansion; does not execute a compiler or build."""
    ninja = shutil.which('ninja')
    assert ninja, 'configured Ninja is required to capture the actual ON target commands'
    names = {'interface_mixar_profile_card.cc', 'view3d_moodboard_drawer_draw.cc',
             'view3d_director_cinema_top.cc', 'agent_ui_controls_paint.cc'}
    records = []
    for row in json.loads((build / 'compile_commands.json').read_text()):
        name = Path(row['file']).name
        if name not in names:
            continue
        args = row.get('arguments') or shlex.split(row['command'])
        assert '-DLAMPWAY' in args or '-DLAMPWAY=1' in args, f'{name} actual ON command lacks LAMPWAY'
        target = args[args.index('-o') + 1]
        command = [ninja, '-C', str(build), '-t', 'commands', target]
        result = subprocess.run(command, capture_output=True, text=True, check=True)
        log = out / (name + '.ninja-commands.log')
        log.write_text(result.stdout + result.stderr)
        actual = [line for line in result.stdout.splitlines() if name in line and '-c ' in line]
        assert actual and any('-DLAMPWAY' in shlex.split(line) or '-DLAMPWAY=1' in shlex.split(line)
                              for line in actual), f'No actual guarded Ninja compile command for {name}'
        records.append({'consumer': name, 'read_only_command': command, 'object': target,
                        'cached_compile_command': args, 'ninja_compile_command': actual[-1], 'log': str(log)})
    assert {r['consumer'] for r in records} == names
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--expected-sha', required=True)
    parser.add_argument('--build-dir', default=ROOT / 'build/Prod', type=Path)
    parser.add_argument('--native-build-log', required=True, type=Path)
    args = parser.parse_args()
    assert len(args.expected_sha) == 40 and all(c in '0123456789abcdef' for c in args.expected_sha)
    build, out = args.build_dir.resolve(), args.output.resolve()
    binary = Path(os.environ.get('LAMPWAY_BIN') or build / 'bin/mixar').resolve()
    assert binary.is_file() and args.native_build_log.is_file()
    assert args.native_build_log.stat().st_size, 'the actual completed native build log is required'
    assert not out.exists(), 'use a new packet directory to preserve earlier evidence'
    out.mkdir(parents=True)
    env = dict(os.environ, LAMPWAY_BIN=str(binary), LAMPWAY_BUILD_DIR=str(build))
    python = ROOT / 'server/.venv/bin/python'
    receipt = {'scope': 'Actual final ON binary and isolated cloud fixtures; ON/OFF consumer compilation is not a full OFF build; local deterministic models, no account proof',
               'started_at': time.time(), 'start': fingerprint(binary, build, args.expected_sha),
               'native_build_log': {'path': str(args.native_build_log.resolve()),
                                    'sha256': digest(args.native_build_log)}, 'checks': {}}
    manifest = out / 'manifest.json'
    def save():
        manifest.write_text(json.dumps(receipt, indent=2))
    try:
        receipt['actual_on_ninja_commands'] = capture_native_commands(build, out)
        save()
        suites = [
            ('target-definitions', ['tests/lampway/test_lampway_interface_compile_definition.py',
                'tests/lampway/test_agent_mode_compile_definition.py', 'tests/lampway_tools/test_agent_mode_fitter.py']),
            ('native-consumers', ['tests/lampway_tools/test_agent_modes_native_consumers.py']),
            ('rna-client', ['tests/lampway_tools/test_agent_modes_client_live.py']),
            ('main-integrated', ['tests/lampway_tools/test_agent_modes_integrated_live.py']),
            ('workers-collect', ['tests/lampway_tools/test_agent_modes_workers_live.py']),
            ('workers-stop-streamed', ['tests/lampway_tools/test_agent_modes_workers_stop_live.py::test_actual_parent_stop_interrupts_both_worker_panes_without_commits[streamed]']),
            ('workers-stop-before-first', ['tests/lampway_tools/test_agent_modes_workers_stop_live.py::test_actual_parent_stop_interrupts_both_worker_panes_without_commits[before-first-token]']),
        ]
        for name, paths in suites:
            folder = out / name; folder.mkdir()
            stage_env = dict(env, LAMPWAY_NATIVE_CONSUMER_ARTIFACTS=str(folder / 'commands'),
                LAMPWAY_INTEGRATION_ARTIFACTS=str(folder), LAMPWAY_WORKER_ARTIFACTS=str(folder),
                LAMPWAY_WORKER_STOP_ARTIFACTS=str(folder))
            xml, log = folder / 'results.xml', folder / 'results.log'
            checked([str(python), '-m', 'pytest', '-q', *paths, '--basetemp=' + str(folder / 'run'),
                     '--junitxml=' + str(xml)], stage_env, log, timeout=2400)
            receipt['checks'][name] = {**junit(xml), 'log': str(log), 'xml': str(xml)}
            assert fingerprint(binary, build, args.expected_sha) == receipt['start'], 'binary/source changed during validation'
            save()
        gui = out / 'native-chip'; gui.mkdir()
        gui_env = dict(env, LW_QA_OUT=str(gui), LAMPWAY_BRIDGE_PORT='0', LAMPWAY_BACKEND_URL='http://127.0.0.1:9')
        for key, sub in {'HOME': 'home', 'XDG_CONFIG_HOME': 'config', 'XDG_DATA_HOME': 'data',
                         'XDG_STATE_HOME': 'state', 'XDG_CACHE_HOME': 'cache', 'TMPDIR': 'tmp',
                         'LAMPWAY_HOME': 'profile', 'LAMPWAY_LEGACY_HOME': 'no-legacy'}.items():
            path = gui / sub; path.mkdir(); gui_env[key] = str(path)
        gui_env['LAMPWAY_TEST_ROOT'] = str(gui)
        xvfb = shutil.which('xvfb-run'); assert xvfb, 'isolated Xvfb is required'
        checked([xvfb, '-a', '-s', '-screen 0 1600x1000x24', 'nice', '-n', '15', str(binary),
                 '--enable-event-simulate', '--python-exit-code', '1', '-P',
                 str(ROOT / 'tests/qa/agent_mode_chip_native.py')], gui_env, gui / 'native.log', timeout=240)
        result = json.loads((gui / 'result.json').read_text())
        assert result['ok'], result
        images = {}
        for name in ('mode-chip.png', 'mode-menu.png'):
            image = gui / name
            assert image.read_bytes().startswith(b'\x89PNG\r\n\x1a\n'), f'Actual native capture missing: {image}'
            images[name] = {'path': str(image), 'sha256': digest(image)}
        receipt['checks']['native-chip'] = {'result': result, 'images': images, 'log': str(gui / 'native.log')}
        receipt['end'] = fingerprint(binary, build, args.expected_sha)
        assert receipt['end'] == receipt['start'], 'binary/source changed during validation'
        receipt.update(ok=True, completed_at=time.time())
    except BaseException as exc:
        receipt.update(ok=False, failure=str(exc), completed_at=time.time())
        raise
    finally:
        save()
    print(json.dumps({'ok': True, 'manifest': str(manifest)}))


if __name__ == '__main__':
    main()
