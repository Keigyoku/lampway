# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Bootstrap refuses unsafe authority before a namespace/native process is started."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from lampway_server import grok_worker as G


def fixture(tmp_path):
    root = tmp_path / 'root'
    pane = root / 'panes' / 'owned'
    pane.mkdir(parents=True, mode=0o700)
    native = tmp_path / 'grok'; native.write_bytes(b'fixture executable'); native.chmod(0o755)
    bwrap = tmp_path / 'bwrap'; bwrap.write_bytes(b'fixture namespace'); bwrap.chmod(0o755)
    connector = tmp_path / 'lampway-pane-mcp'; connector.write_bytes(b'fixture connector'); connector.chmod(0o755)
    cwd = tmp_path / 'project'; cwd.mkdir()
    etc = tmp_path / 'etc'; etc.mkdir()
    (etc / 'native.conf').write_text('original system sentinel')
    (etc / 'grok').mkdir()
    (etc / 'grok' / 'native-sentinel.toml').write_text('original native file sentinel')
    mcp = pane / 'mcp.json'
    mcp.write_text(json.dumps({'version': 1, 'binding': 'swarm:owned:worker', 'desktop': None,
        'direct': [{'url': 'http://127.0.0.1:8787/api/v1/mcp/pane', 'headers': {
            'Authorization': 'Bearer fixture-only', 'X-Mixar-Session-Id': 'swarm:owned:worker'}}]})); mcp.chmod(0o600)
    config = {'version': 1, 'root': str(root), 'cwd': str(cwd), 'native': str(native),
        'native_sha256': hashlib.sha256(native.read_bytes()).hexdigest(), 'bwrap': str(bwrap),
        'bwrap_sha256': hashlib.sha256(bwrap.read_bytes()).hexdigest(),
        'connector': {'command': str(connector), 'args': [], 'sha256': hashlib.sha256(connector.read_bytes()).hexdigest()},
        'inner_socket': str(pane / 'inner.sock'), 'outer_socket': str(pane / 'outer.sock'),
        'task': 'literal --argument $(never execute); spaces'}
    path = pane / 'grok-worker.json'; path.write_text(json.dumps(config)); path.chmod(0o600)
    return path, config, etc


def test_plan_adds_only_restrictive_policy_and_restores_project_cwd(tmp_path):
    path, config, etc = fixture(tmp_path)
    before = (etc / 'grok' / 'native-sentinel.toml').read_bytes()
    plan = G.build_plan(path, etc=etc)
    assert plan['argv'][0] == config['bwrap']
    assert '--unshare-pid' in plan['argv'] and '--die-with-parent' in plan['argv']
    assert ['--proc', '/proc'] == plan['argv'][plan['argv'].index('--proc'):plan['argv'].index('--proc') + 2]
    work_index = plan['argv'].index(plan['work'])
    assert plan['argv'][work_index - 1:work_index + 2] == ['--ro-bind', plan['work'], plan['work']]
    assert plan['cwd'] == config['cwd']
    assert plan['argv'][-1] == config['task']
    assert '--agent' not in plan['argv'] and '--always-approve' not in plan['argv']
    assert 'allow_managed_mcp_servers_only = true' in plan['policy']
    assert 'server_command = ' in plan['policy'] and 'server_name' not in plan['policy']
    assert 'fixture-only' not in json.dumps(plan)
    assert (etc / 'grok' / 'native-sentinel.toml').read_bytes() == before
    assert plan['argv'][plan['argv'].index('--leader-socket') + 1] == config['inner_socket']


def test_namespace_plan_and_readiness_probe_use_private_devices(tmp_path, monkeypatch):
    path, config, etc = fixture(tmp_path)
    monkeypatch.setattr(G, 'NATIVE_SHA256', config['native_sha256'])
    listing = json.dumps({'servers': [{'name': 'lampway_pane', 'command': config['connector']['command'], 'args': []}]})
    monkeypatch.setattr(G, 'native_connector_identity', lambda *args: None)
    probe = G.preflight(config['native'], config['bwrap'], config['connector']['command'], listing, etc=etc)
    for argv in [G.build_plan(path, etc=etc)['argv'], probe['namespace_probe']]:
        root = argv.index('--bind')
        assert argv[root:root + 5] == ['--bind', '/', '/', '--dev', '/dev']
        assert argv.count('--dev') == 1
        assert '--dev-bind' not in argv


@pytest.mark.parametrize('kind', ['file', 'symlink', 'directory'])
def test_occupied_requirements_slot_refuses_without_replacing_it(tmp_path, kind):
    path, config, etc = fixture(tmp_path)
    slot = etc / 'grok' / 'requirements.toml'
    if kind == 'file': slot.write_text('original requirements')
    elif kind == 'directory': slot.mkdir()
    else: slot.symlink_to(etc / 'native.conf')
    with pytest.raises(ValueError, match='occupied'):
        G.build_plan(path, etc=etc)
    assert slot.exists()


@pytest.mark.parametrize('change', ['same_socket', 'foreign_socket', 'wrong_hash', 'setuid', 'metadata_mode', 'desktop', 'unbound', 'symlink'])
def test_bad_worker_authority_refuses_before_launch(tmp_path, change):
    path, config, etc = fixture(tmp_path)
    if change == 'same_socket': config['inner_socket'] = config['outer_socket']
    elif change == 'foreign_socket': config['inner_socket'] = str(tmp_path / 'foreign.sock')
    elif change == 'wrong_hash': config['native_sha256'] = '0' * 64
    elif change == 'setuid': Path(config['bwrap']).chmod(0o4755)
    elif change == 'metadata_mode': path.chmod(0o644)
    elif change in {'desktop', 'unbound'}:
        mcp = path.with_name('mcp.json'); value = json.loads(mcp.read_text())
        value['desktop' if change == 'desktop' else 'binding'] = {'command': config['native']} if change == 'desktop' else ''
        mcp.write_text(json.dumps(value))
    elif change == 'symlink':
        original = path.with_name('original.json'); path.rename(original); path.symlink_to(original)
    if change != 'symlink': path.write_text(json.dumps(config))
    with pytest.raises(ValueError): G.build_plan(path, etc=etc)


def test_prepare_preserves_original_layers_and_adds_exact_readonly_identity(tmp_path):
    path, config, etc = fixture(tmp_path)
    original = {p: p.read_bytes() for p in etc.rglob('*') if p.is_file()}
    plan = G.build_plan(path, etc=etc)
    G.prepare(plan)
    assert original == {p: p.read_bytes() for p in original}
    assert not (etc / 'grok' / 'requirements.toml').exists()
    policy = Path(plan['policy_path'])
    import tomllib
    assert tomllib.loads(policy.read_text())['allowed_mcp_servers'] == [
        {'server_command': [config['connector']['command']]}]
    assert policy.stat().st_mode & 0o777 == 0o400
    original_connector = Path(config['connector']['command'])
    assert hashlib.sha256(original_connector.read_bytes()).hexdigest() == config['connector']['sha256']
    assert ['--ro-bind', plan['shim'], str(original_connector.resolve())] == plan['argv'][
        plan['argv'].index(plan['shim']) - 1:plan['argv'].index(plan['shim']) + 2]
    assert Path(plan['work']).stat().st_mode & 0o777 == 0o700
    with pytest.raises(ValueError, match='already exists'):
        G.build_plan(path, etc=etc)


def test_bootstrap_restores_native_wrap_cwd_without_replacing_login_or_persona(tmp_path, monkeypatch):
    path, config, etc = fixture(tmp_path)
    native_home = tmp_path / 'original-home'; native_home.mkdir()
    monkeypatch.chdir(native_home)
    monkeypatch.setenv('HOME', str(native_home))
    monkeypatch.setenv('GROK_HOME', str(native_home / '.grok'))
    monkeypatch.setenv('GROK_AUTH_PATH', str(native_home / 'original-auth'))
    monkeypatch.setenv('ORIGINAL_NATIVE_SETTING', 'preserve-literal')
    original_build = G.build_plan
    monkeypatch.setattr(G, 'build_plan', lambda value, task=None: original_build(value, task=task, etc=etc))
    witness = {}
    class ExecObserved(BaseException):
        pass
    def exec_observed(executable, argv, env):
        witness.update(executable=executable, argv=argv, env=env, cwd=os.getcwd())
        raise ExecObserved
    monkeypatch.setattr(G.os, 'execve', exec_observed)
    with pytest.raises(ExecObserved): G.main(['--config', str(path)])
    assert witness['cwd'] == config['cwd']
    assert witness['env']['HOME'] == str(native_home)
    assert witness['env']['GROK_HOME'] == str(native_home / '.grok')
    assert witness['env']['GROK_AUTH_PATH'] == str(native_home / 'original-auth')
    assert witness['env']['ORIGINAL_NATIVE_SETTING'] == 'preserve-literal'
    assert witness['env']['LAMPWAY_HERMES_CONNECTOR_CONFIG'] == str(path.with_name('mcp.json'))
    assert witness['argv'][-1] == config['task'] and '--agent' not in witness['argv']


def test_hard_bound_shim_refuses_native_entry_env_rebinding(tmp_path, monkeypatch):
    import sys
    import types
    path, config, etc = fixture(tmp_path)
    monkeypatch.setenv('LAMPWAY_HERMES_CONNECTOR_CONFIG', '/synthetic-foreign/panes/other/mcp.json')
    monkeypatch.setenv('LAMPWAY_HERMES_CONNECTOR_ROOT', '/synthetic-foreign')
    seen = {}
    helper = types.ModuleType('lampway_server.pane_mcp')
    def observe():
        seen.update(config=os.environ['LAMPWAY_HERMES_CONNECTOR_CONFIG'], root=os.environ['LAMPWAY_HERMES_CONNECTOR_ROOT'])
        return 0
    helper.main = observe
    monkeypatch.setitem(sys.modules, 'lampway_server.pane_mcp', helper)
    with pytest.raises(SystemExit) as exit:
        exec(G._shim_source(path.with_name('mcp.json'), Path(config['root'])), {})
    assert exit.value.code == 0
    assert seen == {'config': str(path.with_name('mcp.json')), 'root': config['root']}


def test_existing_outer_socket_requires_the_exact_native_wrap_parent(tmp_path, monkeypatch):
    import socket
    path, config, etc = fixture(tmp_path)
    with socket.socket(socket.AF_UNIX) as outer:
        outer.bind(config['outer_socket'])
        with pytest.raises(ValueError, match='native wrap parent'):
            G.build_plan(path, etc=etc)
        monkeypatch.setattr(G, '_native_wrap_parent', lambda native, path: path == Path(config['outer_socket']))
        assert G.build_plan(path, etc=etc)['outer_socket'] == config['outer_socket']


def test_native_directory_traversal_modes_are_preserved(tmp_path):
    path, config, etc = fixture(tmp_path)
    etc.chmod(0o751); (etc / 'grok').chmod(0o710)
    plan = G.build_plan(path, etc=etc); G.prepare(plan)
    assert Path(plan['skeleton']).stat().st_mode & 0o777 == 0o751
    assert (Path(plan['skeleton']) / 'grok').stat().st_mode & 0o777 == 0o710


def test_root_owned_private_directory_cannot_be_made_readable_by_recreation(tmp_path, monkeypatch):
    from types import SimpleNamespace
    path = tmp_path / 'original-protected-policy-directory'; path.mkdir()
    original_stat = Path.stat
    def stat_control(target, *args, **kwargs):
        if target == path:
            return SimpleNamespace(st_mode=0o40700, st_uid=os.getuid() + 1000, st_gid=os.getgid() + 1000)
        return original_stat(target, *args, **kwargs)
    monkeypatch.setattr(Path, 'stat', stat_control)
    with pytest.raises(ValueError, match='traversal permissions'):
        G._directory_access(path)


def test_canonical_name_and_exact_argv_are_separate_native_policy_intersections(tmp_path):
    import tomllib
    path, config, etc = fixture(tmp_path)
    # Existing managed files are not rewritten to make space for our second
    # restriction. This positive fixture has two genuinely unoccupied slots.
    plan = G.build_plan(path, etc=etc)
    assert 'server_name = "lampway_pane"' in plan['name_policy']
    assert tomllib.loads(plan['policy'])['allowed_mcp_servers'] == [{'server_command': [config['connector']['command']]}]
    assert tomllib.loads(plan['name_policy'])['allowed_mcp_servers'] == [{'server_name': 'lampway_pane'}]


@pytest.mark.parametrize('kind', ['file', 'symlink', 'directory'])
def test_occupied_managed_slot_refuses_without_replacing_it(tmp_path, kind):
    path, config, etc = fixture(tmp_path)
    slot = etc / 'grok' / 'managed_config.toml'
    if kind == 'file': slot.write_text('original native managed policy')
    elif kind == 'directory': slot.mkdir()
    else: slot.symlink_to(etc / 'native.conf')
    with pytest.raises(ValueError, match='occupied'):
        G.build_plan(path, etc=etc)
    assert slot.exists()


def test_task_can_be_supplied_as_literal_launch_argv_without_metadata_schema_change(tmp_path):
    path, config, etc = fixture(tmp_path)
    config.pop('task'); path.write_text(json.dumps(config))
    task = '--literal-task $(never_execute); spaces'
    assert G.build_plan(path, task=task, etc=etc)['argv'][-1] == task
    with pytest.raises(ValueError, match='task'):
        G.build_plan(path, task='', etc=etc)


@pytest.mark.parametrize('bad', ['absent', 'wrong_command', 'wrong_args', 'disabled', 'blocked', 'malformed'])
def test_native_connector_query_refuses_uninstalled_or_wrong_binding_identity(bad):
    row = {'name': 'lampway_pane', 'command': '/synthetic-installed/lampway-pane-mcp', 'args': [], 'enabled': True}
    if bad == 'wrong_command': row['command'] = '/synthetic-foreign/server'
    elif bad == 'wrong_args': row['args'] = ['--foreign']
    elif bad == 'disabled': row['enabled'] = False
    elif bad == 'blocked': row['blocked_reason'] = 'original policy'
    value = 'not json' if bad == 'malformed' else json.dumps([] if bad == 'absent' else [row])
    with pytest.raises(ValueError): G.native_connector_identity(value, '/synthetic-installed/lampway-pane-mcp')


def test_native_connector_query_returns_only_identity_not_native_secret_fields():
    row = {'name': 'lampway_pane', 'command': '/synthetic-installed/lampway-pane-mcp', 'args': [], 'enabled': True,
           'env': {'NATIVE_PROVIDER_KEY': 'synthetic-do-not-export'}, 'headers': {'Authorization': 'synthetic-private'}}
    result = G.native_connector_identity(json.dumps([row]), row['command'])
    assert result == {'name': 'lampway_pane', 'command': row['command'], 'args': []}
    assert 'synthetic-do-not-export' not in json.dumps(result)


def test_acl_effective_access_disagreement_refuses_private_directory_recreation(tmp_path, monkeypatch):
    path = tmp_path / 'acl-protected-policy'; path.mkdir(); path.chmod(0o755)
    original_access = os.access
    monkeypatch.setattr(G.os, 'access', lambda target, mode: False if target == path and mode == os.R_OK else original_access(target, mode))
    with pytest.raises(ValueError, match='traversal permissions'):
        G._directory_access(path)
