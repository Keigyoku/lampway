# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure mocked path-contract controls; every launch/account/network seam refuses."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
READINESS_SOURCE = ROOT / 'server/lampway_server/native_worker_readiness.py'
QA_SOURCE = ROOT / 'tests/qa/grok_worker_validation.py'


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(autouse=True)
def no_launches(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError('native/subprocess/account/provider/network seam prohibited')
    monkeypatch.setattr(subprocess, 'Popen', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    class RefusedSocket(socket.socket):
        def __new__(cls, *args, **kwargs): forbidden(*args, **kwargs)
    monkeypatch.setattr(socket, 'socket', RefusedSocket)
    for name in ['execve', 'execv', 'execl', 'system', 'kill', 'killpg']:
        monkeypatch.setattr(os, name, forbidden)
    from lampway_server.herdr import launcher as L
    for name in ['run', 'worker_probe', 'start_server', 'stop_server']:
        monkeypatch.setattr(L, name, forbidden)
    monkeypatch.setattr(L, 'server_info', lambda *args: None)


@pytest.fixture
def installed(tmp_path, monkeypatch):
    from lampway_server import grok_worker as G
    directory = tmp_path / 'installed'
    directory.mkdir()
    paths = {key: directory / name for key, name in [
        ('native', 'grok'), ('bwrap', 'bwrap'), ('connector', 'lampway-pane-mcp')]}
    for key, path in paths.items():
        path.write_bytes(('synthetic ordinary ' + key).encode()); path.chmod(0o755)
    interpreter = directory / 'python'
    interpreter.write_bytes(b'synthetic interpreter never executed')
    monkeypatch.setattr(sys, 'executable', str(interpreter))
    monkeypatch.setenv('PATH', str(directory))
    monkeypatch.setattr(G.sys, 'platform', 'linux')
    return G, paths


def test_readiness_consumes_actual_mapping_before_probing(installed, monkeypatch, tmp_path):
    G, paths = installed
    R = load('lampway_server._candidate_readiness', READINESS_SOURCE)
    description = {key: str(value) for key, value in paths.items()}
    description.update(native_sha256='owned fixture hash', namespace_probe=['synthetic bounded namespace'])
    seen = []
    def probe(argv, env, **kwargs):
        seen.append((argv, env, kwargs))
        if len(seen) == 1:
            assert argv == [str(paths['native']), 'mcp', 'list', '--json']
            assert env == {} and kwargs == {'cwd': str(tmp_path.resolve())}
            return 0, 'synthetic native listing'
        assert argv == ['synthetic bounded namespace'] and env == {} and kwargs == {}
        return 0, ''
    def preflight(native, bwrap, connector, listing):
        assert [native, bwrap, connector] == [str(paths[key]) for key in ['native', 'bwrap', 'connector']]
        assert listing == 'synthetic native listing'
        return dict(description)
    monkeypatch.setattr(R.L, 'worker_probe', probe)
    monkeypatch.setattr(G, 'preflight', preflight)
    result = R.grok_worker_description(str(paths['native']), cwd=tmp_path)
    assert result == {key: value for key, value in description.items() if key != 'namespace_probe'}
    assert len(seen) == 2


@pytest.mark.parametrize('failure', ['listing', 'namespace'])
def test_failed_native_or_namespace_probe_refuses_without_files(installed, monkeypatch, failure):
    G, paths = installed
    R = load('lampway_server._candidate_readiness_failure', READINESS_SOURCE)
    def probe(argv, env, **kwargs):
        if argv[0] == str(paths['native']): return (78, '') if failure == 'listing' else (0, 'listing')
        return 78, ''
    monkeypatch.setattr(R.L, 'worker_probe', probe)
    monkeypatch.setattr(G, 'preflight', lambda *args: {'namespace_probe': ['mock namespace']})
    before = sorted(paths['native'].parent.iterdir())
    assert R.grok_worker_note(str(paths['native'])) == R.GROK_REFUSAL
    assert sorted(paths['native'].parent.iterdir()) == before


@pytest.mark.parametrize('mapping', [{}, {'native': 'missing'}, ('native', 'bwrap', 'connector')])
def test_malformed_path_contract_refuses_before_any_probe(installed, monkeypatch, mapping):
    G, paths = installed
    R = load('lampway_server._candidate_readiness_malformed', READINESS_SOURCE)
    monkeypatch.setattr(G, 'candidate_paths', lambda *args: mapping)
    assert R.grok_worker_note(str(paths['native'])) == R.GROK_REFUSAL


@pytest.mark.parametrize('bad_pin', [None, 'native', 'bwrap', 'connector'])
def test_native_fixture_uses_actual_lookup_with_owned_pinned_path_links(installed, monkeypatch, tmp_path, bad_pin):
    G, paths = installed
    QA = load('candidate_grok_proof_driver', QA_SOURCE)
    options = SimpleNamespace(output=tmp_path / 'proof', grok=paths['native'], bwrap=paths['bwrap'],
        herdr=tmp_path / 'synthetic-herdr', phase='loopback')
    validator = QA.Validator(options)
    validator.receipt['versions'] = {}
    monkeypatch.setattr(validator, 'run', lambda *args, **kwargs: 'synthetic herdr version')
    monkeypatch.setattr(QA, 'GROK_SHA256', hashlib.sha256(paths['native'].read_bytes()).hexdigest())
    config = {'bwrap_sha256': QA.digest(paths['bwrap']),
              'connector': {'command': str(paths['connector']), 'sha256': QA.digest(paths['connector'])}}
    if bad_pin == 'native': monkeypatch.setattr(QA, 'GROK_SHA256', '0' * 64)
    elif bad_pin == 'bwrap': config['bwrap_sha256'] = '0' * 64
    elif bad_pin == 'connector': config['connector']['sha256'] = '0' * 64
    original = G.candidate_paths
    lookups = []
    def observed(binary):
        result = original(binary); lookups.append(result); return result
    monkeypatch.setattr(G, 'candidate_paths', observed)
    from lampway_server.herdr import launcher as L
    class StopBeforeNative(Exception): pass
    monkeypatch.setattr(L, 'start_server', lambda *args, **kwargs: (_ for _ in ()).throw(StopBeforeNative()))
    before_env = dict(os.environ)
    expected = AssertionError if bad_pin else StopBeforeNative
    with pytest.raises(expected):
        validator.native_panes(tmp_path / 'never-read.json', {'PATH': '/synthetic/foreign-path'}, tmp_path, config)
    assert os.environ == before_env
    assert len(lookups) == 1, 'Proof must use the actual production mapping lookup before starting native herdr'
    result = lookups[0]
    assert Path(result['native']).resolve() == paths['native'].resolve()
    assert Path(result['bwrap']).resolve() == paths['bwrap'].resolve()
    assert Path(result['connector']).resolve() == paths['connector'].resolve()
    if bad_pin:
        assert validator.receipt['cases'][-1]['passed'] is False
    else:
        assert all(case['passed'] for case in validator.receipt['cases'])
    assert validator.receipt['candidate_paths'] == result
    assert (validator.output / 'native-bin/bwrap').resolve() == paths['bwrap'].resolve()
    source = (QA_SOURCE).read_text()
    assert "patch.object(G, 'candidate_paths'" not in source
