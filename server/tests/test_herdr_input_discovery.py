# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Ordered native submission and the explicit custom discovery environment boundary."""
import json
import time
from types import SimpleNamespace

import pytest

from lampway_server.herdr import launcher as L
from lampway_server.herdr.host import Cockpit, CockpitError


def session(tmp_path, agent='codex', sends=True):
    c = Cockpit(tmp_path / 'cockpit')
    rec = dict(id='owned', pane_id='w1:p1', agent=agent, state='live', agent_sends=sends)
    c._save(dict(version=1, sessions=[rec]))
    return c


@pytest.mark.parametrize('agent', ['codex', 'claude', 'opencode', 'command', 'shell'])
def test_submit_uses_one_native_ordered_submission_after_paste_acceptance(tmp_path, monkeypatch, agent):
    c, calls, submitted = session(tmp_path, agent), [], []
    text = 'Review this literal text: "quoted"\nSecond line — QA'
    # Split paste+Enter loses Enter while the terminal is accepting the paste.
    # The native ordered submission acknowledges after text and Enter are written.
    def run(root, args, **kwargs):
        calls.append(args)
        if args[:2] in (['agent', 'prompt'], ['pane', 'run']):
            submitted.append(args[3])
        return json.dumps({'result': {'ok': True}})
    monkeypatch.setattr(L, 'run', run)
    c.send_input('owned', text, by='user')
    assert submitted == [text]
    assert calls == [['agent', 'prompt', 'w1:p1', text] if agent in ('codex', 'claude', 'opencode')
                     else ['pane', 'run', 'w1:p1', text]]


@pytest.mark.parametrize('reason', ['agent_blocked', 'agent_not_ready', 'agent_prompt_failed'])
def test_native_prompt_failure_never_falls_back_or_sends_a_second_enter(tmp_path, monkeypatch, reason):
    c, calls = session(tmp_path), []
    def run(root, args, **kwargs):
        calls.append(args)
        if args[:2] == ['agent', 'prompt']:
            raise L.HerdrError(reason)
        return '{}'
    monkeypatch.setattr(L, 'run', run)
    with pytest.raises(L.HerdrError, match=reason):
        c.send_input('owned', 'one request', by='user')
    assert calls == [['agent', 'prompt', 'w1:p1', 'one request']]


def test_staging_does_not_submit_or_change_native_target(tmp_path, monkeypatch):
    c, calls = session(tmp_path), []
    monkeypatch.setattr(L, 'run', lambda root, args, **kwargs: calls.append(args) or '{}')
    c.send_input('owned', 'stage only', submit=False, by='user')
    assert calls == [['pane', 'send-text', 'w1:p1', 'stage only']]


@pytest.mark.parametrize('agent,sends,by,typed,text,reason', [
    ('shell', True, 'agent', None, 'x', 'shell'),
    ('codex', False, 'agent', None, 'x', 'sends are off'),
    ('codex', True, 'agent', 'now', 'x', 'You are typing'),
    ('codex', True, 'user', None, 'x' * 64001, '64000'),
])
def test_existing_guards_refuse_before_any_native_input(tmp_path, monkeypatch, agent, sends, by, typed, text, reason):
    c = session(tmp_path, agent, sends)
    monkeypatch.setattr(L, 'run', lambda *args, **kwargs: pytest.fail('guard allowed terminal input'))
    with pytest.raises(CockpitError, match=reason):
        c.send_input('owned', text, by=by, user_typed_at=time.time() if typed else None)


def test_explicit_discovery_path_reaches_pane_without_secret_environment_forwarding(monkeypatch, tmp_path):
    path = str(tmp_path / 'private connector discovery')
    monkeypatch.setenv('LAMPWAY_MCP_DISCOVERY_DIR', path)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-secret-not-forwarded')
    monkeypatch.setenv('LAMPWAY_PANE_KEY', 'synthetic-pane-key-not-forwarded')
    result = L.pane_env()
    assert f'LAMPWAY_MCP_DISCOVERY_DIR={path}' in result
    assert '--env' == result[result.index(f'LAMPWAY_MCP_DISCOVERY_DIR={path}') - 1]
    assert not any(x.startswith(('OPENAI_API_KEY=', 'LAMPWAY_PANE_KEY=')) for x in result)


def test_systemd_whitelist_preserves_only_explicit_discovery_override(tmp_path, monkeypatch):
    path = str(tmp_path / 'private connector discovery')
    monkeypatch.setenv('LAMPWAY_MCP_DISCOVERY_DIR', path)
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-secret-not-forwarded')
    monkeypatch.setenv('LAMPWAY_PANE_KEY', 'synthetic-pane-key-not-forwarded')
    calls, count = [], [0]
    def status(root):
        count[0] += 1
        return dict(running=count[0] > 1)
    monkeypatch.setattr(L, 'server_status', status)
    monkeypatch.setattr(L, 'bin_path', lambda: '/synthetic/herdr')
    monkeypatch.setattr(L, '_spawn', lambda cmd, env, *args, **kwargs: calls.append(cmd) or SimpleNamespace(returncode=0))
    L.start_server(tmp_path / 'cockpit', method='systemd')
    setenv = [x for x in calls[0] if x.startswith('--setenv=')]
    assert f'--setenv=LAMPWAY_MCP_DISCOVERY_DIR={path}' in setenv
    assert not any(x.startswith(('--setenv=OPENAI_API_KEY=', '--setenv=LAMPWAY_PANE_KEY=')) for x in setenv)


from .herdr_support import lroot, needs_herdr, wait_for  # noqa: E402,F401


@needs_herdr
def test_native_owned_pane_inherits_custom_discovery_and_submits_once(tmp_path, monkeypatch, lroot):
    """Actual Herdr PTY with a local echo fixture; no account or provider turn."""
    import shlex
    import sys
    discovery = tmp_path / 'private connector discovery'
    discovery.mkdir()
    monkeypatch.setenv('LAMPWAY_MCP_DISCOVERY_DIR', str(discovery))
    fixture = tmp_path / 'echo_fixture.py'
    fixture.write_text(
        'import os, sys\n'
        f'print("discovery-match:", os.environ.get("LAMPWAY_MCP_DISCOVERY_DIR") == {str(discovery)!r}, flush=True)\n'
        'print("local-echo-ready", flush=True)\n'
        'for index, line in enumerate(sys.stdin, 1):\n'
        '    print("accepted:", index, line.strip(), flush=True)\n')
    c = Cockpit(lroot)
    c.ensure_server()
    rec = c.create_session('command', 'Discovery input QA', str(tmp_path),
        command=shlex.join([sys.executable, str(fixture)]), by='user')
    assert wait_for(lambda: 'local-echo-ready' in c.read_screen(rec['id']))
    assert 'discovery-match: True' in c.read_screen(rec['id'])
    c.send_input(rec['id'], 'first synthetic message', by='user')
    assert wait_for(lambda: 'accepted: 1 first synthetic message' in c.read_screen(rec['id']))
    c.send_input(rec['id'], 'second synthetic message', by='user')
    assert wait_for(lambda: 'accepted: 2 second synthetic message' in c.read_screen(rec['id']))
    screen = c.read_screen(rec['id'])
    assert screen.count('accepted: 1 first synthetic message') == 1
    assert screen.count('accepted: 2 second synthetic message') == 1
    assert 'accepted: 3' not in screen
