# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Symbolic user-Hermes binding exists before launch, without touching its home."""
import json
import stat
import tomllib
from pathlib import Path
import pytest

from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from .test_byoa_binding import herdr, _envs


@pytest.mark.parametrize('harness', ['hermes', 'grok'])
def test_unbound_symbolic_harness_starts_with_empty_owned_binding_for_later_rebind(herdr, tmp_path, harness):
    cockpit = H.Cockpit(tmp_path / 'herdr')
    rec = cockpit.create_session(harness, 'Owned synthetic pane', str(tmp_path), by='user')
    assert rec['mcp_config_path'], 'symbolic connector needs its path before the native pane starts'
    cfg = Path(rec['mcp_config_path'])
    assert cfg.is_relative_to(tmp_path / 'herdr' / 'panes' / rec['id'])
    assert stat.S_IMODE(cfg.stat().st_mode) == 0o600
    assert stat.S_IMODE(cfg.parent.stat().st_mode) == 0o700
    assert json.loads(cfg.read_text())['binding'] == ''
    assert f'LAMPWAY_HERMES_CONNECTOR_CONFIG={cfg}' in _envs(herdr)
    before = len(herdr.calls)
    cockpit.bind(rec['id'], 'scene-two')
    assert len(herdr.calls) == before
    assert json.loads(cfg.read_text())['binding'] == 'scene-two'
    cockpit.unbind(rec['id'])
    assert len(herdr.calls) == before
    assert json.loads(cfg.read_text())['binding'] == ''


def test_supported_hermes_listing_keeps_required_manual_setup_note():
    row = next(row for row in HN.listing() if row['id'] == 'hermes')
    assert row['tools'] is True
    assert 'install' in row['tools_note'] and 'unverified' in row['tools_note']


def test_packaged_symbolic_connector_has_its_own_executable_entry():
    root = Path(__file__).resolve().parents[1]
    scripts = tomllib.loads((root / 'pyproject.toml').read_text())['project']['scripts']
    assert scripts.get('lampway-hermes-mcp') == 'lampway_server.pane_mcp:main'


@pytest.mark.parametrize('harness', ['hermes', 'grok'])
def test_native_worker_refused_by_host_before_owned_files_or_pane_placement(herdr, tmp_path, monkeypatch, harness):
    adapter = HN.get(harness)
    monkeypatch.setattr(adapter, 'worker_ok', False, raising=False)
    cockpit = H.Cockpit(tmp_path / 'herdr')
    cockpit.pane_mcp_url = 'http://127.0.0.1:8787/api/v1/mcp/pane'
    with pytest.raises(H.CockpitError, match='worker'):
        cockpit.create_session(harness, 'Refused native worker', str(tmp_path), by='swarm',
                               swarm_worker=('swarm:one:worker', 'synthetic-worker-token'))
    assert herdr.calls == [], 'no placement or native start is allowed for an unsupported worker'
    assert not list((tmp_path / 'herdr' / 'panes').glob('*')), 'refusal precedes creation of owned worker files'
