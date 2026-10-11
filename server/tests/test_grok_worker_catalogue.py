# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Pinned native catalogue semantics; no native process, socket or grant."""
import copy
import importlib.util
import os
from pathlib import Path
import socket
import subprocess

import pytest

SOURCE = Path(__file__).resolve().parents[2] / 'tests/qa/grok_worker_validation.py'
spec = importlib.util.spec_from_file_location('owned_grok_catalogue_control', SOURCE)
QA = importlib.util.module_from_spec(spec)
spec.loader.exec_module(QA)


@pytest.fixture(autouse=True)
def refuse_external_operations(monkeypatch):
    def refuse(*args, **kwargs):
        pytest.fail('catalogue controls cannot launch, connect or signal')
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    monkeypatch.setattr(subprocess, 'run', refuse)
    monkeypatch.setattr(socket, 'socket', refuse)
    monkeypatch.setattr(os, 'kill', refuse)
    monkeypatch.setattr(os, 'killpg', refuse)
    monkeypatch.setattr(QA.asyncio, 'create_subprocess_exec', refuse)


def native_reply():
    # Shape independently witnessed in the 1.0.46 restricted native wire.
    return {'id': 5, 'result': {'result': {'sessionMcpResolved': True, 'servers': [
        {'name': 'foreign_user', 'session': {'enabled': False, 'blockedReason': 'requirements.toml'}},
        {'name': 'lampway_pane', 'session': {'enabled': True, 'status': 'ready'}},
        {'name': 'foreign_same_command', 'session': {'enabled': False, 'blockedReason': 'managed_config.toml'}},
        {'name': 'foreign_compat', 'session': {'enabled': False, 'blockedReason': 'requirements.toml'}},
    ]}}}


def test_native_extension_retains_blocked_configs_without_admitting_routes():
    reply = native_reply()
    original = copy.deepcopy(reply)
    assert QA.enabled_native_servers(reply) == ['lampway_pane']
    assert reply == original  # Preserve native evidence, including blocked names.


@pytest.mark.parametrize('name', ['foreign_user', 'foreign_compat', 'foreign_plugin',
                                  'foreign_same_command', 'dynamic'])
def test_enabled_foreign_identity_fails_exact_canonical_exclusivity(name):
    reply = native_reply()
    rows = reply['result']['result']['servers']
    row = next((row for row in rows if row['name'] == name), None)
    if row is None:
        row = {'name': name}
        rows.append(row)
    row['session'] = {'enabled': True, 'status': 'ready'}
    assert QA.enabled_native_servers(reply) != ['lampway_pane']


@pytest.mark.parametrize('kind', ['error', 'flat', 'unresolved', 'missing_resolved',
                                  'servers_object', 'row_object', 'missing_session',
                                  'missing_enabled', 'enabled_integer', 'duplicate',
                                  'canonical_initializing', 'canonical_missing_status'])
def test_malformed_or_unready_native_catalogue_fails_closed(kind):
    reply = native_reply()
    payload = reply['result']['result']
    canonical = payload['servers'][1]
    if kind == 'error': reply['error'] = {'code': -32603}
    elif kind == 'flat': reply['result'] = payload
    elif kind == 'unresolved': payload['sessionMcpResolved'] = False
    elif kind == 'missing_resolved': del payload['sessionMcpResolved']
    elif kind == 'servers_object': payload['servers'] = {}
    elif kind == 'row_object': payload['servers'].append(None)
    elif kind == 'missing_session': del payload['servers'][0]['session']
    elif kind == 'missing_enabled': del payload['servers'][0]['session']['enabled']
    elif kind == 'enabled_integer': payload['servers'][0]['session']['enabled'] = 0
    elif kind == 'duplicate': payload['servers'].append(copy.deepcopy(canonical))
    elif kind == 'canonical_initializing': canonical['session']['status'] = 'initializing'
    elif kind == 'canonical_missing_status': del canonical['session']['status']
    with pytest.raises(ValueError, match='native'):
        QA.enabled_native_servers(reply)
