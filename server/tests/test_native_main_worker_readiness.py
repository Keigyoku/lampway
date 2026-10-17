# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""MAIN connector support must not admit an unsupported saved worker choice."""
import asyncio
from types import SimpleNamespace

import pytest

from lampway_server import native_worker_readiness as N

from lampway_server import choices as CH
from lampway_server import egress as EG
from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
from lampway_server.choices.snapshot import World, byoa_worker_readiness
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr.harnesses.base import PaneSpec
from .worker_choice_support import install_worker_harness


def selected(tmp_path, monkeypatch, harness):
    if harness == 'grok':
        # Explicit synthetic human consent reaches the independent native-readiness refusal.
        from lampway_server import capabilities as CAP
        board = CAP.Store(tmp_path / 'consent-state')
        monkeypatch.setattr(CAP, 'ACTIVE', board)
        disclosure = CAP.grok_compat_disclosure()
        board.set('grok.worker_compat', enabled=True, options={
            'consent_version': disclosure['consent_version'], 'effects_sha256': disclosure['effects_sha256']}, by='user')
    install_worker_harness(tmp_path, monkeypatch, harness)
    monkeypatch.setenv('LAMPWAY_LOCAL_CLI', '1')
    EG.ACTIVE.set_route(f'byoa:{harness}', True)
    store = CH.FileStore(tmp_path / 'choices')
    store.set('agent.worker_mode', 'global', None, {'preferred': f'byoa:{harness}'}, by='user')
    monkeypatch.setattr(CH, '_STORE', CH.FileStore(tmp_path / 'choices'))
    monkeypatch.setattr(CH, '_STATE', tmp_path / 'choices')
    monkeypatch.setattr(CH, 'WORLD_FACTORY', None)


@pytest.mark.parametrize('harness', ['grok'])   # Hermes workers are permitted unverified (captain, 2026-10-13): the test below
def test_installed_main_connector_does_not_advertise_worker_readiness(tmp_path, monkeypatch, harness):
    selected(tmp_path, monkeypatch, harness)
    adapter = HN.get(harness)
    assert adapter.tools_reachable and adapter.direct_ok
    path = tmp_path / 'panes' / 'main' / 'mcp.json'
    wiring = adapter.lampway_tools(PaneSpec(cwd=str(tmp_path), scene_session_id='scene',
        mcp_config_path=str(path), launcher=('/synthetic/lampway-mcp',)))
    assert wiring.kind == 'symbolic_stdio'
    missing = byoa_worker_readiness()
    assert f'byoa:{harness}' in missing
    # Grok is a worker harness (captain, 2026-10-12): an installed MAIN connector still does not make it ready. Here readiness has
    # no owning project root, so the native startup qualification fails closed before any probe (grok_worker_description).
    assert (N.GROK_REFUSAL if harness == 'grok' else adapter.worker_note) in missing[f'byoa:{harness}']
    with pytest.raises(CH.NoChoice, match='cannot run a worker'):
        CH.resolve('agent.worker_mode', CH.Job(origin='agent'))
    assert CH.preferred('agent.worker_mode') == f'byoa:{harness}'


@pytest.mark.parametrize('harness', ['grok'])
def test_saved_unsupported_worker_refuses_before_activation_even_with_stale_readiness(tmp_path, monkeypatch, harness):
    selected(tmp_path, monkeypatch, harness)
    # A previously captured ready snapshot must not bypass actual launch preflight.
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(routes={f'byoa:{harness}': True}))
    events = []
    async def activate(*args):
        events.append('activate')
        raise AssertionError('Unsupported worker reached run activation')
    def launch(*args, **kwargs):
        events.append('pane')
        raise AssertionError('Unsupported worker reached pane launch')
    async def job(*args):
        events.append('job')
        raise AssertionError('Unsupported worker reached a job')
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object(), create_session=launch)
    monkeypatch.setattr(manager, 'harness_for', lambda socket: SimpleNamespace(activate=activate))
    monkeypatch.setattr(manager, '_run_worker', job)
    ctx = SwarmContext(None, 'scene', 'turn', 'call', project_root=str(tmp_path))
    with pytest.raises(SwarmError, match='worker') as refused:
        asyncio.run(manager._start({'tasks': [{'name': 'owned', 'prompt': 'synthetic work'}]}, ctx))
    assert (N.GROK_REFUSAL if harness == 'grok' else HN.get(harness).worker_note) in str(refused.value)
    assert events == [] and manager.swarms == {} and manager._seq == 0
    assert CH.preferred('agent.worker_mode') == f'byoa:{harness}'


def test_supported_worker_stays_ready_and_resolves_saved_choice(tmp_path, monkeypatch):
    selected(tmp_path, monkeypatch, 'claude')
    assert 'byoa:claude' not in byoa_worker_readiness()
    assert HN.get('claude').worker_ok
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    brain = manager.worker_brain(SwarmContext(None, 'scene', 'turn', 'call', project_root=str(tmp_path)))
    assert brain.harness == 'claude' and brain.mode_choice.option == 'byoa:claude'


def test_an_unqualified_installed_hermes_is_a_ready_worker_that_runs_unverified(tmp_path, monkeypatch):
    """Captain, 2026-10-13: "It should permit unverified". An installed Hermes whose startup cannot take Lampway's guard is a
    worker Choices resolves, not a refusal; its wiring says it runs unverified."""
    selected(tmp_path, monkeypatch, 'hermes')
    monkeypatch.setattr(N, 'hermes_worker_note', lambda binary: N.HERMES_REFUSAL)
    assert 'byoa:hermes' not in byoa_worker_readiness()
    assert CH.resolve('agent.worker_mode', CH.Job(origin='agent')).option == 'byoa:hermes'
    adapter = HN.get('hermes')
    assert adapter.worker_verification() == N.HERMES_REFUSAL
