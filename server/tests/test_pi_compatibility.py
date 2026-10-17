# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Installed-version refusal uses only the launcher's local version probe, never a native model turn."""
import pytest

from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import launcher
from lampway_server.herdr.harnesses.pi import Pi


@pytest.mark.parametrize('version', ['0.84.2', '0.98.9', 'unknown', '1.0.4-beta.1', ''])
def test_incompatible_installed_pi_is_not_offered_and_refuses_before_wiring(monkeypatch, version):
    adapter = Pi(which=lambda *a, **k: '/fixture/pi')
    monkeypatch.setattr(launcher, 'probe', lambda argv: (0, version))
    monkeypatch.setitem(HN.ADAPTERS, 'pi', adapter)
    row = next(row for row in HN.listing() if row['id'] == 'pi')
    assert row['installed'] is True
    assert row['tools'] is False
    assert 'registerMcpServer' in row['tools_note'] and '0.99.0' in row['tools_note']
    pane = HN.PaneSpec(cwd='/fixture/project', scene_session_id='scene', mcp_config_path='/fixture/pane/mcp.json')
    for operation in [lambda: adapter.lampway_tools(pane), lambda: adapter.launch(pane), lambda: adapter.resume('native-id', pane)]:
        with pytest.raises(ValueError, match='registerMcpServer'):
            operation()


@pytest.mark.parametrize('version', ['0.99.0', '1.0.4'])
def test_supported_pi_keeps_native_launch_and_connector(monkeypatch, version):
    adapter = Pi(which=lambda *a, **k: '/fixture/pi')
    probes = []
    def probe(argv):
        probes.append(argv)
        return 0, version
    monkeypatch.setattr(launcher, 'probe', probe)
    pane = HN.PaneSpec(cwd='/fixture/project', session_id='session', scene_session_id='scene', mcp_config_path='/fixture/pane/mcp.json')
    adapter.detect()
    assert adapter.tools_reachable is True
    assert adapter.lampway_tools(pane).verified is True
    assert adapter.launch(pane)[:3] == ['pi', '--session-id', 'session']
    assert probes and all(argv == ['/fixture/pi', '--version'] for argv in probes)


def test_changed_install_rechecks_compatibility(monkeypatch):
    adapter = Pi(which=lambda *a, **k: '/fixture/pi')
    version = ['0.84.2']
    monkeypatch.setattr(launcher, 'probe', lambda argv: (0, version[0]))
    adapter.detect()
    assert adapter.compatibility_note()
    version[0] = '1.0.4'
    adapter.detect()
    assert adapter.compatibility_note() == ''


def test_incompatible_saved_pi_worker_refuses_before_activation(tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from lampway_server import choices as CH
    from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
    from lampway_server.choices.snapshot import World, byoa_worker_readiness
    from .test_native_main_worker_readiness import selected
    selected(tmp_path, monkeypatch, 'pi')
    monkeypatch.setattr(launcher, 'probe', lambda argv: (0, '0.84.2'))
    assert 'registerMcpServer' in byoa_worker_readiness()['byoa:pi']
    with pytest.raises(CH.NoChoice):
        CH.resolve('agent.worker_mode', CH.Job(origin='agent'))
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(routes={'byoa:pi': True}))
    events = []
    async def activate(*args):
        events.append('activate')
        raise AssertionError('incompatible Pi reached activation')
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    monkeypatch.setattr(manager, 'harness_for', lambda socket: SimpleNamespace(activate=activate))
    with pytest.raises(SwarmError, match='registerMcpServer'):
        asyncio.run(manager._start({'tasks': [{'name': 'owned', 'prompt': 'synthetic'}]},
            SwarmContext(None, 'scene', 'turn', 'call', project_root=str(tmp_path))))
    assert events == [] and manager.swarms == {} and manager._seq == 0


def test_supported_saved_pi_worker_remains_ready(tmp_path, monkeypatch):
    from lampway_server import choices as CH
    from lampway_server.choices.snapshot import byoa_worker_readiness
    from .test_native_main_worker_readiness import selected
    selected(tmp_path, monkeypatch, 'pi')
    monkeypatch.setattr(launcher, 'probe', lambda argv: (0, '1.0.4'))
    assert 'byoa:pi' not in byoa_worker_readiness()
    assert CH.resolve('agent.worker_mode', CH.Job(origin='agent')).option == 'byoa:pi'
