# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""In-process early-ACP-exit control; no child/native process is launched."""
import asyncio
import importlib.util
import os
from pathlib import Path
import signal
from types import SimpleNamespace

import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'tests/qa/grok_worker_validation.py'
spec = importlib.util.spec_from_file_location('owned_grok_qa_control', SOURCE)
QA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(QA)


def test_native_exit_during_first_request_cleans_orphan_exactly(tmp_path, monkeypatch):
    state = {'exited': False, 'child_live': True}
    child = {'pid': 543212, 'start': 'original-child', 'parent': 1,
             'session': 543211, 'group': 543211, 'argv': ['owned-fixture'], 'pid_namespace': 'fixture'}
    signals = []
    class Input:
        def write(self, value): pass
        async def drain(self): pass
    class Output:
        async def readline(self):
            state['exited'] = True
            raise RuntimeError('planted native ACP early exit')
    class Process:
        pid = 543211
        stdin = Input()
        stdout = Output()
        @property
        def returncode(self): return 1 if state['exited'] else None
        async def wait(self): return 1
    async def create(*args, **kwargs): return Process()
    monkeypatch.setattr(QA.asyncio, 'create_subprocess_exec', create)
    monkeypatch.setattr(QA, 'process_rows', lambda: {} if state['exited'] else {
        543211: {'pid': 543211, 'start': 'original-parent'}})
    # Old ancestry-only snapshot loses the reparented child; the corrected
    # private-session capture still identifies its recorded session origin.
    monkeypatch.setattr(QA, 'owned_snapshot', lambda root, start=None:
        [child] if start is not None and state['exited'] and state['child_live'] else [])
    monkeypatch.setattr(QA, 'still_alive', lambda row: row == child and state['child_live'])
    def kill(pid, sig):
        signals.append((pid, sig)); state['child_live'] = False
    monkeypatch.setattr(QA.os, 'kill', kill)
    monkeypatch.setattr(QA.os, 'killpg', lambda *a: pytest.fail('broad group signal prohibited'))
    validator = QA.Validator(SimpleNamespace(output=tmp_path / 'out', phase='stdio'))
    with pytest.raises(RuntimeError, match='planted native ACP early exit'):
        asyncio.run(validator.acp(['synthetic-no-process'], {}, tmp_path, 'early-exit'))
    assert signals == [(child['pid'], signal.SIGTERM)]
    assert not state['child_live']
    assert validator.receipt['cases'][-1]['name'] == 'early-exit owned ACP cleanup'
    assert validator.receipt['cases'][-1]['passed']


def test_session_snapshot_retains_orphan_and_rejects_reused_leader(monkeypatch):
    pid = os.getpid(); root = 99999999
    row = {'pid': pid, 'parent': 1, 'group': root, 'session': root, 'start': 'child-start'}
    monkeypatch.setattr(QA, 'process_rows', lambda: {pid: row})
    assert [r['pid'] for r in QA.owned_snapshot(root, 'original-parent')] == [pid]
    monkeypatch.setattr(QA, 'process_rows', lambda: {pid: row, root: {
        'pid': root, 'parent': 1, 'group': root, 'session': root, 'start': 'reused-parent'}})
    assert QA.owned_snapshot(root, 'original-parent') == []


def test_cleanup_does_not_signal_reused_child_identity(monkeypatch):
    row = {'pid': 543212, 'start': 'old-start'}
    monkeypatch.setattr(QA, 'owned_snapshot', lambda *a: [])
    monkeypatch.setattr(QA, 'still_alive', lambda value: False)
    monkeypatch.setattr(QA.os, 'kill', lambda *a: pytest.fail('reused or foreign PID must not be signalled'))
    class Process:
        pid = 543211
        async def wait(self): return 1
    asyncio.run(QA.cleanup_acp(Process(), 'parent-start', {(row['pid'], row['start']): row}))


def test_reap_only_owned_adopted_zombie_with_same_start(monkeypatch):
    owner = os.getpid()
    owned = [{'pid': 543211, 'start': 'parent'}, {'pid': 543212, 'start': 'child'},
             {'pid': 543213, 'start': 'reused'}, {'pid': 543214, 'start': 'foreign-parent'},
             {'pid': 543215, 'start': 'live'}]
    rows = {r['pid']: {**r, 'parent': owner, 'state': 'Z'} for r in owned}
    rows[543213]['start'] = 'new-start'
    rows[543214]['parent'] = owner + 1
    rows[543215]['state'] = 'S'
    monkeypatch.setattr(QA, 'process_rows', lambda: rows)
    waits = []
    monkeypatch.setattr(QA.os, 'waitpid', lambda pid, flags: waits.append((pid, flags)) or (pid, 0))
    QA.reap_owned({(r['pid'], r['start']): r for r in owned}, exclude=543211)
    assert waits == [(543212, os.WNOHANG)]


@pytest.mark.parametrize('label', ['baseline', 'restricted'])
def test_native_mcp_calls_never_require_a_model_prompt(tmp_path, monkeypatch, label):
    requests = []
    replies = asyncio.Queue()
    class Input:
        def write(self, value):
            request = QA.json.loads(value)
            requests.append(request)
            assert request['method'] != 'session/prompt', 'MCP proof must not wait on a denied model turn'
            result = {'sessionId': 'owned-native-id'} if request['method'] == 'session/new' else {}
            if request['method'] == '_x.ai/mcp/list':
                result = {'servers': [{'name': 'lampway_pane'}]}
            response = {'jsonrpc': '2.0', 'id': request['id'], 'result': result}
            if label == 'restricted' and request['params'].get('server') == 'foreign_same_command':
                response = {'jsonrpc': '2.0', 'id': request['id'], 'error': {'message': 'fixture policy refusal'}}
            replies.put_nowait((QA.json.dumps(response) + '\n').encode())
            if request['method'] == 'session/new':
                # The pinned native wire reports asynchronous pool completion
                # after the session reply, before session-scoped calls are ready.
                notification = {'jsonrpc': '2.0', 'method': '_x.ai/mcp_initialized',
                                'params': {'sessionId': 'owned-native-id', 'mcpToolCount': 1}}
                replies.put_nowait((QA.json.dumps(notification) + '\n').encode())
        async def drain(self): pass
    class Output:
        async def readline(self): return await replies.get()
    class Process:
        pid = 543211
        stdin = Input()
        stdout = Output()
        async def wait(self): return 0
    async def create(*args, **kwargs): return Process()
    async def cleanup(*args): pass
    original_wait = asyncio.wait_for
    deadlines = []
    async def bounded(awaitable, timeout):
        deadlines.append(timeout)
        return await original_wait(awaitable, timeout)
    monkeypatch.setattr(QA.asyncio, 'create_subprocess_exec', create)
    monkeypatch.setattr(QA.asyncio, 'wait_for', bounded)
    # Freeze only the driver's budget clock. wait_for retains its real event-loop
    # timer; no event loop, self-pipe or twenty-second bound is replaced.
    monkeypatch.setattr(QA.asyncio, 'get_running_loop', lambda: SimpleNamespace(time=lambda: 0))
    monkeypatch.setattr(QA, 'cleanup_acp', cleanup)
    monkeypatch.setattr(QA, 'process_rows', lambda: {})
    monkeypatch.setattr(QA, 'owned_snapshot', lambda *args: [])
    validator = QA.Validator(SimpleNamespace(output=tmp_path / 'out', phase='stdio'))
    asyncio.run(validator.acp(['synthetic-no-process'], {}, tmp_path, label))
    expected = ['initialize', 'session/new', '_x.ai/mcp/call']
    expected += ['_x.ai/mcp/call']
    if label == 'restricted':
        expected += ['_x.ai/mcp/list', '_x.ai/session/update_mcp_servers', '_x.ai/mcp/list']
    assert [r['method'] for r in requests] == expected
    assert all(r['params']['sessionId'] == 'owned-native-id' for r in requests[2:])
    # Each unchanged request bounds drain and reply; pool completion is one
    # additional bounded read. Every timeout remains exactly twenty seconds.
    assert deadlines == [20] * (2 * len(expected) + 1)
    assert all(c['passed'] for c in validator.receipt['cases'])


def test_synthetic_native_user_plugin_is_explicitly_enabled(tmp_path):
    import tomllib
    options = SimpleNamespace(output=tmp_path / 'out', phase='stdio',
                              grok=tmp_path / 'grok', bwrap=tmp_path / 'bwrap')
    options.grok.write_bytes(b'owned synthetic native identity')
    options.bwrap.write_bytes(b'owned synthetic namespace identity')
    validator = QA.Validator(options)
    _, env, _, _ = validator.make_fixture()
    config = Path(env['GROK_HOME']) / 'config.toml'
    parsed = tomllib.loads(config.read_text())
    assert parsed.get('plugins', {}).get('enabled') == ['owned-sentinel']
    assert validator.receipt['synthetic_inputs'][str(config)]['sha256'] == QA.digest(config)
    assert validator.receipt['synthetic_inputs'][str(Path(env['GROK_HOME']) / 'trusted_folders.toml')] == {'absent': True}


def test_preliminary_namespace_probe_has_private_devices(tmp_path, monkeypatch):
    validator = QA.Validator(SimpleNamespace(output=tmp_path / 'out', phase='stdio',
        grok=tmp_path / 'grok', bwrap=tmp_path / 'bwrap'))
    monkeypatch.setattr(QA, 'digest', lambda p: QA.GROK_SHA256)
    monkeypatch.setattr(QA.os, 'getuid', lambda: 1001)
    calls = []
    class StopProbe(Exception): pass
    def stop(argv, **kwargs):
        calls.append(argv)
        raise StopProbe
    monkeypatch.setattr(validator, 'run', stop)
    with pytest.raises(StopProbe): validator.validate()
    argv = calls[0]; root = argv.index('--bind')
    assert argv[root:root + 5] == ['--bind', '/', '/', '--dev', '/dev']


@pytest.mark.parametrize('changed', ['auth.json', 'original-agent.md', None])
def test_warmed_baseline_records_caches_but_refuses_auth_or_persona_changes(tmp_path, monkeypatch, changed):
    from lampway_server import grok_worker as G
    options = SimpleNamespace(output=tmp_path / 'out', phase='stdio',
        grok=tmp_path / 'grok', bwrap=tmp_path / 'bwrap')
    options.grok.write_bytes(b'fixture native'); options.bwrap.write_bytes(b'fixture namespace')
    validator = QA.Validator(options)
    original_digest = QA.digest
    monkeypatch.setattr(QA, 'digest', lambda p: QA.GROK_SHA256 if Path(p) == options.grok else original_digest(p))
    monkeypatch.setattr(QA.os, 'getuid', lambda: 1001)
    monkeypatch.setattr(QA, 'deny_inet', lambda: None)
    original_socket = QA.socket.socket
    def blocked_socket(family=QA.socket.AF_INET, *args, **kwargs):
        if family in [QA.socket.AF_INET, QA.socket.AF_INET6]: raise PermissionError('fixture guard')
        return original_socket(family, *args, **kwargs)
    monkeypatch.setattr(QA.socket, 'socket', blocked_socket)
    monkeypatch.setattr(validator, 'run', lambda *args, **kwargs: 'synthetic version or head')
    async def native_baseline(argv, env, cwd, label):
        home = Path(env['GROK_HOME'])
        for source in ['user', 'compat', 'plugin']:
            (validator.output / ('foreign-' + source + '.jsonl')).write_text('{"method":"initialize"}\n')
        for name in ['requirements.toml', 'managed_config.toml']: (home / name).unlink()
        with (home / 'config.toml').open('a') as stream:
            stream.write('\n[marketplace]\ndefault_skills_installs_purged=true\n')
        if changed: (home / changed).write_text('planted unexpected native mutation')
    monkeypatch.setattr(validator, 'acp', native_baseline)
    class StopBeforeBoundary(Exception): pass
    def stop(*args, **kwargs): raise StopBeforeBoundary
    monkeypatch.setattr(G, 'build_plan', stop)
    expected = AssertionError if changed else StopBeforeBoundary
    with pytest.raises(expected): validator.validate()
    if not changed:
        side_effects = validator.receipt['native_baseline_side_effects']
        assert sorted(Path(p).name for p in side_effects) == ['config.toml', 'managed_config.toml', 'requirements.toml']
        assert all(side_effects[p]['warmed'] == {'absent': True} for p in side_effects if p.endswith('requirements.toml') or p.endswith('managed_config.toml'))
