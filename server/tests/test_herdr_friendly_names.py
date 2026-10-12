# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Friendly cockpit labels must not become herdr's restricted agent identifiers."""
import json
import re

import pytest

from lampway_server.herdr.host import Cockpit
from lampway_server.herdr import launcher as L


@pytest.fixture
def cockpit(tmp_path, monkeypatch):
    c = Cockpit(tmp_path / 'cockpit', project_root=tmp_path)
    calls = []
    monkeypatch.setattr(L, 'server_status', lambda root: {'running': True})
    monkeypatch.setattr(L, 'pane_env', lambda: [])
    monkeypatch.setattr(c, '_wait_prompt', lambda pane: None)
    def run(root, args, **kwargs):
        calls.append(args)
        if args == ['api', 'snapshot']:
            return json.dumps({'result': {'snapshot': {'workspaces': [{'label': 'lampway', 'workspace_id': 'workspace-1'}]}}})
        if args[:2] == ['tab', 'create']:
            return json.dumps({'result': {'root_pane': {'pane_id': f'pane-{len(calls)}', 'workspace_id': 'workspace-1', 'tab_id': f'tab-{len(calls)}'}}})
        if args[:2] == ['agent', 'start']:
            if not re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', args[2]):
                raise L.HerdrError('invalid_agent_name')
            return '{}'
        raise AssertionError(args)
    monkeypatch.setattr(L, 'run', run)
    return c, calls, tmp_path


@pytest.mark.parametrize('agent', ['codex', 'claude', 'opencode'])
@pytest.mark.parametrize('name', ['Chest fit audit', 'UPPERCASE', '胸当て QA / review!', 'N' * 100])
def test_friendly_label_preserved_while_launch_identifier_is_valid(cockpit, agent, name):
    c, calls, cwd = cockpit
    rec = c.create_session(agent, name, str(cwd), effort='medium')
    start = next(a for a in calls if a[:2] == ['agent', 'start'])
    assert re.fullmatch(r'[a-z][a-z0-9_-]{0,39}', start[2])
    assert rec['name'] == name
    assert rec['herdr_agent_name'] == start[2]
    assert rec['herdr_agent_name'] == 'lampway-' + rec['id']
    assert Cockpit(c.root).list_sessions() == [rec]
    tab = next(a for a in calls if a[:2] == ['tab', 'create'])
    assert tab[tab.index('--label') + 1] == name[:40]
    assert start[start.index('--kind') + 1] == agent
    assert start[start.index('--pane') + 1] == rec['pane_id']
    assert len([a for a in calls if a[:2] == ['agent', 'start']]) == 1


def test_same_friendly_label_gets_distinct_persistent_launch_identifiers(cockpit):
    c, calls, cwd = cockpit
    records = [c.create_session('codex', 'Same friendly name', str(cwd)) for _ in range(2)]
    assert len({r['herdr_agent_name'] for r in records}) == 2
    assert [r['name'] for r in records] == ['Same friendly name'] * 2
    assert Cockpit(c.root).list_sessions() == records


def test_command_label_does_not_change_command_tokens(cockpit, monkeypatch):
    c, calls, cwd = cockpit
    original_run = L.run
    def run(root, args, **kwargs):
        if args[:2] == ['pane', 'run']:
            calls.append(args)
            return '{}'
        return original_run(root, args, **kwargs)
    monkeypatch.setattr(L, 'run', run)
    rec = c.create_session('command', 'Command Audit', str(cwd), command='echo "hello world"')
    assert rec['name'] == 'Command Audit'
    assert next(a for a in calls if a[:2] == ['pane', 'run'])[3:] == ['echo', 'hello world']
    assert not any(a[:2] == ['agent', 'start'] for a in calls)
