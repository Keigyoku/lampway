# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Project Context settings must be a guarded, explicit Hermes config edit."""
from starlette.testclient import TestClient
from lampway_server.app import create_app
from .fake_client import FakeMixarClient


def test_context_routes_require_user_auth(settings):
    http = TestClient(create_app(settings), base_url="http://127.0.0.1:8787")
    assert http.get('/app/agent/context').status_code == 401
    assert http.put('/app/agent/context', json={}).status_code == 401


def test_explicit_project_context_survives_restart_and_can_reset(settings, tmp_path):
    project = str(tmp_path / 'project')
    app = create_app(settings)
    http = TestClient(app, base_url="http://127.0.0.1:8787")
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    response = user.get('/app/agent/context', params={'project': project})
    assert response.status_code == 200, response.text
    assert response.json()['overrides'] == {}
    assert not (settings.state_dir / 'agent_context.json').exists()
    response = user.put('/app/agent/context', json={'project': project, 'values': {'compression_threshold': .9}})
    assert response.status_code == 200, response.text
    assert response.json()['overrides'] == {'compression_threshold': .9}
    reopened = TestClient(create_app(settings), base_url="http://127.0.0.1:8787")
    again = FakeMixarClient(reopened, password=settings.user_password)
    again.login()
    assert again.get('/app/agent/context', params={'project': project}).json()['effective']['compression_threshold'] == .9
    assert again.get('/app/agent/context', params={'project': str(tmp_path / 'other')}).json()['overrides'] == {}
    assert again.put('/app/agent/context', json={'project': project, 'reset': ['compression_threshold']}).json()['overrides'] == {}


def test_context_config_seam_refuses_auxiliary_credentials():
    from lampway_server.engine import hermes_config as HC
    import pytest
    for value in ({'compression': {'threshold': True}}, {'context': {'engine': {'plugin': 'x'}}},
                  {'auxiliary': {'compression': {'model': 'lampway', 'api_key': 'secret'}}}):
        with pytest.raises(ValueError):
            HC._merge_context({}, value)


def test_pane_preparation_passes_its_project_to_the_context_writer(tmp_path):
    import sys
    from types import SimpleNamespace
    from lampway_server.engine.units import Mode1Units
    from lampway_server.engine.gateway import Registry
    from .mode1_support import fake_engine
    got = []
    def write(home, url, token, model, **kw):
        got.append(kw.get('project'))
        kw['rendered'].update({'platform_toolsets': {'cli': []}})
    units = Mode1Units(cockpit=SimpleNamespace(), engine=fake_engine(tmp_path / 'engine'),
        state_dir=tmp_path / 'state', server_base='http://127.0.0.1:8787', registry=Registry(),
        write_config=write, model_id='lampway', proxy_vars={}, environ={'LAMPWAY_NODE': sys.executable})
    project = str(tmp_path / 'separate-project')
    units.prepare(rid='pane', unit='unit', role='main', cwd=project, project_root=project)
    assert got == [project], 'A pane must use its own project Context, not the server-global project'


def test_context_rejects_invalid_or_privileged_edits_without_changing_saved_state(settings, tmp_path):
    import pytest
    http = TestClient(create_app(settings), base_url='http://127.0.0.1:8787')
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    project = str(tmp_path / 'project')
    assert user.put('/app/agent/context', json={'project': project, 'values': {'compression_threshold': .8}}).status_code == 200
    before = (settings.state_dir / 'agent_context.json').read_bytes()
    for values in ({'compression_threshold': True}, {'compression_threshold': 0}, {'compression_threshold': 1.1},
                   {'protected_recent_turns': True}, {'protected_recent_turns': -1}, {'protected_recent_turns': 1.5},
                   {'context_engine': 'external-plugin'}, {'summarizing_model': 'provider:paid-model'},
                   {'model': {'api_key': 'secret'}}, {'security': {'allow_lazy_installs': True}}):
        response = user.put('/app/agent/context', json={'project': project, 'values': values})
        assert response.status_code == 400, response.text
        assert (settings.state_dir / 'agent_context.json').read_bytes() == before
    from lampway_server.engine.context_settings import validate
    for ratio in (float('nan'), float('inf')):
        with pytest.raises(ValueError):
            validate({'compression_threshold': ratio})


def test_live_context_save_refuses_without_changing_any_state(settings, tmp_path, monkeypatch):
    from lampway_server.engine import context_settings as CS
    async def busy(*args):
        return True
    monkeypatch.setattr(CS, 'panes_busy', busy)
    app = create_app(settings)
    http = TestClient(app, base_url='http://127.0.0.1:8787')
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    project = str(tmp_path / 'project')
    user.put('/app/agent/context', json={'project': project, 'values': {'compression_threshold': .8}})
    before = (settings.state_dir / 'agent_context.json').read_bytes()
    monkeypatch.setattr(app.state.agent.cockpit, 'list_sessions', lambda: [
        {'agent': 'lampway_hermes', 'state': 'live', 'project_root': project}])
    response = user.put('/app/agent/context', json={'project': project, 'values': {'compression_threshold': .9}})
    assert response.status_code == 409, response.text
    assert response.json()['code'] == 'context_busy'
    assert (settings.state_dir / 'agent_context.json').read_bytes() == before
    assert user.get('/app/agent/context', params={'project': project}).json()['live_pane'] is True


def test_context_overrides_render_exact_hermes_fields_and_preserve_security(settings, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from lampway_server.engine.context_settings import Store
    from lampway_server.engine import wiring as W, gateway as GW, hermes_config as HC
    from lampway_server import capabilities as CAP
    project = str(tmp_path / 'own-project')
    chosen = {'compression_threshold': .8, 'protected_recent_turns': 7,
              'context_engine': 'compressor', 'summarizing_model': 'lampway'}
    store = Store(settings.state_dir)
    store.update(project, chosen, [])
    monkeypatch.setattr(CAP, 'ACTIVE', CAP.Store(settings.state_dir))
    agent = SimpleNamespace(settings_store=SimpleNamespace(credentials_view=lambda: {'items': []}), provider=SimpleNamespace())
    wiring = W.EngineWiring({}, settings=settings, agent=agent, registry=GW.Registry())
    home = tmp_path / 'pane'
    wiring.write_config(home, 'http://127.0.0.1:8787/engine/v1', 'lwe_test', 'lampway', project=project)
    cfg = HC.read(home)
    assert cfg['compression'] == {'threshold': .8, 'protect_last_n': 7}
    assert cfg['context'] == {'engine': 'compressor'}
    assert cfg['auxiliary']['compression'] == {'model': 'lampway'}
    assert cfg['auxiliary']['background_review']['enabled'] is False
    assert cfg['model']['provider'] == 'custom' and cfg['model']['api_key'] == 'lwe_test'
    assert cfg['auth']['adopt_external_logins'] is False
    assert cfg['security']['allow_lazy_installs'] is False
    store.update(project, {}, list(chosen))
    wiring.write_config(home, 'http://127.0.0.1:8787/engine/v1', 'lwe_test', 'lampway', project=project)
    cfg = HC.read(home)
    assert 'compression' not in cfg and 'context' not in cfg
    assert 'compression' not in cfg['auxiliary'], 'Reset restores Hermes defaults by omitting overrides'


def test_context_write_is_only_the_users_own_client(settings, tmp_path):
    import time
    from lampway_server.auth import mint_jwt
    from .fake_client import decode_jwt_claims
    http = TestClient(create_app(settings), base_url='http://127.0.0.1:8787')
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    body = {'project': str(tmp_path / 'project'), 'values': {'compression_threshold': .8}}
    claims = decode_jwt_claims(user.access_token)
    agent_token = mint_jwt(settings.jwt_secret, {**claims, 'origin': 'agent', 'exp': time.time() + 300})
    mcp_token = mint_jwt(settings.jwt_secret, {**claims, 'aud': 'mcp', 'exp': time.time() + 300})
    for headers in ({**user.rest_headers(), 'x-lampway-origin': 'agent'},
                    {**user.rest_headers(), 'x-mixar-job-origin': 'mcp'},
                    {**user.rest_headers(), 'Origin': 'https://untrusted.invalid'},
                    {'Authorization': f'Bearer {agent_token}'}, {'Authorization': f'Bearer {mcp_token}'},
                    {'Authorization': 'Bearer lwe_not-a-user-key'}):
        response = http.put('/app/agent/context', json=body, headers=headers)
        assert response.status_code in (401, 403), response.text
        assert not (settings.state_dir / 'agent_context.json').exists()


def test_default_view_reports_real_window_and_never_writes_defaults(tmp_path):
    from types import SimpleNamespace
    from lampway_server.engine.context_settings import Store, view, DEFAULTS
    store = Store(tmp_path / 'state')
    project = str(tmp_path / 'project')
    for value, expected in ((131072, 131072), (None, None), (True, None), (-1, None)):
        got = view(store, project, SimpleNamespace(context_length=value))
        assert got['defaults'] == DEFAULTS and got['effective'] == DEFAULTS
        assert got['model_window'] == {'tokens': expected, 'source': 'provider' if expected else 'unknown'}
        assert got['independent_summarizing_model_supported'] is True
        assert got['live_reload_supported'] is True
    assert store.config(project) == {} and not store.path.exists()


def test_corrupt_saved_context_is_reported_and_retained(tmp_path):
    import pytest
    from lampway_server.engine.context_settings import Store
    store = Store(tmp_path / 'state')
    store.path.parent.mkdir()
    store.path.write_text('{broken')
    with pytest.raises(ValueError):
        store.update(str(tmp_path / 'project'), {'compression_threshold': .8}, [])
    assert not store.path.exists()
    assert next(store.path.parent.glob('agent_context.json.corrupt-*')).read_text() == '{broken'


def test_idle_live_context_save_writes_its_config_and_keeps_the_session(settings, tmp_path, monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from lampway_server.engine import context_settings as CS, hermes_config as HC
    from .mode1_support import fake_engine
    home = tmp_path / 'pane'
    home.mkdir()
    original = {'model': {'provider': 'custom', 'api_key': 'lwe_live', 'default': 'lampway'},
                'auth': {'adopt_external_logins': False}, 'compression': {'threshold': .8}}
    (home / 'config.yaml').write_text(HC.to_yaml(original))
    project = str(tmp_path / 'project')
    app = create_app(settings)
    record = {'agent': 'lampway_hermes', 'state': 'live', 'project_root': project, 'home': str(home), 'unit': 'unit'}
    monkeypatch.setattr(app.state.agent.cockpit, 'list_sessions', lambda: [record])
    calls = []
    async def idle(*args):
        calls.append('native-idle-check')
        return False
    monkeypatch.setattr(CS, 'panes_busy', idle, raising=False)
    http = TestClient(app, base_url='http://127.0.0.1:8787')
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    response = user.put('/app/agent/context', json={'project': project, 'values': {
        'compression_threshold': .9, 'protected_recent_turns': 7, 'context_engine': 'compressor'}})
    assert response.status_code == 200, response.text
    assert calls == ['native-idle-check']
    cfg = HC.read(home)
    assert cfg['compression'] == {'threshold': .9, 'protect_last_n': 7}
    assert cfg['context'] == {'engine': 'compressor'}
    assert cfg['model'] == original['model'] and cfg['auth'] == original['auth']
    assert record['unit'] == 'unit'
    assert response.json()['live_reload_supported'] is True
    assert response.json()['apply_at'] == 'native_turn_boundary'


def test_context_rejects_malformed_project_entry_without_overwriting_it(tmp_path):
    import json
    import pytest
    from lampway_server.engine.context_settings import Store
    store = Store(tmp_path / 'state'); store.path.parent.mkdir()
    project = str(tmp_path / 'project')
    store.path.write_text(json.dumps({project: None}))
    original = store.path.read_bytes()
    with pytest.raises(ValueError, match='project entry'):
        store.read(project)
    with pytest.raises(ValueError, match='project entry'):
        store.update(project, {'compression_threshold': .9}, [])
    assert store.path.read_bytes() == original
