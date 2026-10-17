# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Additive MAIN MCP wiring must never certify exclusive worker discovery (S3/S4)."""
import asyncio
from types import SimpleNamespace

import pytest

from lampway_server import choices as CH
from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
from lampway_server.choices.snapshot import World, byoa_worker_readiness
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import launcher as L
from lampway_server.herdr.harnesses.base import Adapter, DirectServer, PaneSpec, SESSION_HEADER
from lampway_server.herdr.host import Cockpit, CockpitError
from .test_native_main_worker_readiness import selected


def test_new_adapter_requires_explicit_worker_qualification():
    assert Adapter.worker_ok is False


@pytest.mark.parametrize('harness', ['codex', 'cursor', 'opencode'])
def test_additive_main_connector_keeps_binding_and_refuses_worker_readiness(tmp_path, monkeypatch, harness):
    selected(tmp_path, monkeypatch, harness)
    adapter = HN.get(harness)
    direct = DirectServer('lampway_swarm', 'http://127.0.0.1:8787/api/v1/mcp/pane',
                          {SESSION_HEADER: 'scene'}, 'LAMPWAY_PANE_KEY', 'synthetic-main-key')
    pane = PaneSpec(cwd=str(tmp_path), scene_session_id='scene',
                    mcp_config_path=str(tmp_path / 'main' / adapter.config_name),
                    launcher=('/synthetic/lampway-mcp',), direct=(direct,))
    wiring = adapter.lampway_tools(pane)
    assert adapter.tools_reachable and adapter.direct_ok
    assert wiring.kind in ('mcp_override', 'plugin', 'mcp_config_file') and wiring.bound_session == 'scene'
    assert (wiring.argv or wiring.env) and wiring.files
    assert 'synthetic-main-key' not in ' '.join(adapter.launch(pane))
    assert byoa_worker_readiness()[f'byoa:{harness}']
    with pytest.raises(CH.NoChoice, match='cannot run a worker'):
        CH.resolve('agent.worker_mode', CH.Job(origin='agent'))
    assert CH.preferred('agent.worker_mode') == f'byoa:{harness}'


@pytest.mark.parametrize('harness', ['codex', 'cursor', 'opencode'])
def test_stale_ready_snapshot_cannot_activate_or_start_worker_jobs(tmp_path, monkeypatch, harness):
    selected(tmp_path, monkeypatch, harness)
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(routes={f'byoa:{harness}': True}))
    events = []
    async def activate(*args):
        events.append('activate')
        raise AssertionError('Unsupported MCP worker reached run activation')
    async def job(*args):
        events.append('job')
        raise AssertionError('Unsupported MCP worker reached a job')
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    monkeypatch.setattr(manager, 'harness_for', lambda socket: SimpleNamespace(activate=activate))
    monkeypatch.setattr(manager, '_run_worker', job)
    ctx = SwarmContext(None, 'scene', 'turn', 'call', project_root=str(tmp_path))
    with pytest.raises(SwarmError, match='worker') as refused:
        asyncio.run(manager._start({'tasks': [{'name': 'owned', 'prompt': 'synthetic work'}]}, ctx))
    assert HN.get(harness).worker_note and HN.get(harness).worker_note in str(refused.value)
    assert events == [] and manager.swarms == {} and manager._seq == 0
    assert CH.preferred('agent.worker_mode') == f'byoa:{harness}'


@pytest.mark.parametrize('harness', ['codex', 'cursor', 'opencode'])
def test_host_refuses_before_owned_files_or_pane_launch(tmp_path, monkeypatch, harness):
    root = tmp_path / 'herdr'
    cockpit = Cockpit(root, project_root=tmp_path)
    cockpit.pane_mcp_url = 'http://127.0.0.1:8787/api/v1/mcp/pane'
    monkeypatch.setattr(L, 'server_status', lambda root: {'running': True})
    events = []
    def create(*args):
        events.append('create')
        raise AssertionError('Unsupported MCP worker reached file and pane creation')
    monkeypatch.setattr(cockpit, '_create', create)
    before = set(root.rglob('*'))
    with pytest.raises(CockpitError, match='worker') as refused:
        cockpit.create_session(harness, 'Isolation audit worker', str(tmp_path), by='swarm',
                               swarm_worker=('swarm:run:worker', 'synthetic-worker-key'))
    assert HN.get(harness).worker_note and HN.get(harness).worker_note in str(refused.value)
    assert events == [] and set(root.rglob('*')) == before
