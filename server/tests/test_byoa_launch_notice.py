# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""B5 notice admission is exercised with recording launch/status seams only."""
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server import egress as E
from lampway_server.herdr.host import Cockpit
from lampway_server.herdr import harnesses as H, launcher as L


@pytest.fixture
def notice_stack(settings, provider, tmp_path, monkeypatch):
    cp = Cockpit(tmp_path / 'herdr', project_root=str(tmp_path))
    calls, status = [], []
    monkeypatch.setattr(H, 'require_enabled', lambda _: None)
    monkeypatch.setattr(L, 'server_status', lambda _: {'running': True})
    monkeypatch.setattr(cp, '_create', lambda *a, **k: calls.append('create') or
                        {'id': 'owned-pane', 'harness': 'claude', 'state': 'live'})
    monkeypatch.setattr(cp, 'reconcile', lambda: {})
    monkeypatch.setattr(cp, 'find_by_scene', lambda _: [{'id': 'previous-pane'}])
    monkeypatch.setattr(cp, 'unbind', lambda _: calls.append('unbind'))
    def login():
        status.append(True)
        return SimpleNamespace(state='signed_in', detail='RAW_STATUS_MUST_NOT_LEAK', account_label=None)
    monkeypatch.setattr(H.get('claude'), 'login_state', login)
    strict = E.Egress(tmp_path / 'egress')
    strict.set_route('byoa:claude', True)
    app = create_app(settings, provider=provider, cockpit=cp, egress=strict)
    with TestClient(app, base_url='http://127.0.0.1:8787') as http:
        from .fake_client import FakeMixarClient
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield SimpleNamespace(http=http, headers=fake.rest_headers(), cp=cp, calls=calls,
                              status=status, strict=strict, tmp=tmp_path)


def create_body(s):
    return {'agent': 'claude', 'name': 'Synthetic owned session', 'cwd': str(s.tmp)}


def test_first_launch_refuses_before_status_files_or_launch(notice_stack):
    s = notice_stack
    r = s.http.post('/app/workbench/sessions', headers=s.headers, json=create_body(s))
    assert r.status_code == 409 and r.json()['code'] == 'launch_notice_required'
    assert s.calls == s.status == []
    assert not (s.cp.root / 'launch-notices').exists()


def test_notice_prepares_then_explicit_confirm_is_one_use(notice_stack):
    s = notice_stack
    body = create_body(s)
    notice = s.http.post('/app/workbench/sessions', headers=s.headers,
                         json={**body, 'notice_request': True})
    assert notice.status_code == 200 and notice.json()['notice']['required']
    assert s.calls == [] and s.status == [True]
    assert 'RAW_STATUS' not in notice.text
    nonce = notice.json()['notice']['nonce']
    confirmed = {**body, 'notice_nonce': nonce}
    assert s.http.post('/app/workbench/sessions', headers=s.headers, json=confirmed).status_code == 200
    assert s.calls == ['create']
    assert s.http.post('/app/workbench/sessions', headers=s.headers, json=confirmed).status_code == 403
    assert s.calls == ['create']
    persisted = (s.cp.root / 'launch-notices' / 'ack.json').read_text()
    assert 'claude' in persisted and nonce not in persisted and 'RAW_STATUS' not in persisted


def test_route_off_refuses_before_native_status(notice_stack):
    s = notice_stack
    s.strict.set_route('byoa:claude', False)
    r = s.http.post('/app/workbench/sessions', headers=s.headers,
                    json={**create_body(s), 'notice_request': True})
    assert r.status_code == 403
    assert s.calls == s.status == []


@pytest.mark.parametrize('extra', [{'X-Lampway-Origin': 'agent'}, {'Origin': 'https://untrusted.invalid'}])
def test_nonhuman_cannot_prepare_or_acknowledge(notice_stack, extra):
    s = notice_stack
    r = s.http.post('/app/workbench/sessions', headers={**s.headers, **extra},
                    json={**create_body(s), 'notice_request': True, 'by': 'user', 'acknowledged': True})
    assert r.status_code == 403
    assert s.calls == s.status == []


def test_mode_refusal_preserves_previous_binding(notice_stack):
    s = notice_stack
    # No existing pane matching the chosen harness, but a previous scene is bound.
    r = s.http.post('/app/workbench/mode', headers=s.headers, json={
        'mode': 'byoa', 'harness': 'claude', 'scene_session_id': 'new-scene',
        'previous_session_id': 'old-scene'})
    assert r.status_code == 409 and r.json()['code'] == 'launch_notice_required'
    assert s.calls == s.status == []


def test_nonce_cannot_confirm_a_changed_task_or_be_replayed(notice_stack):
    s = notice_stack
    body = create_body(s)
    nonce = s.http.post('/app/workbench/sessions', headers=s.headers,
                        json={**body, 'notice_request': True}).json()['notice']['nonce']
    changed = {**body, 'task': 'different synthetic task', 'notice_nonce': nonce}
    assert s.http.post('/app/workbench/sessions', headers=s.headers, json=changed).status_code == 403
    assert s.calls == []
    assert not s.cp.launch_notices.acknowledged('claude')


def test_unknown_adapter_does_not_guess_or_call_status(notice_stack, monkeypatch):
    s = notice_stack
    ad = H.get('hermes')
    monkeypatch.setattr(ad, 'login_state', lambda: pytest.fail('UNKNOWN has no vetted status command'))
    s.strict.set_route('byoa:hermes', True)
    body = {**create_body(s), 'agent': 'hermes', 'notice_request': True}
    response = s.http.post('/app/workbench/sessions', headers=s.headers, json=body)
    notice = response.json()['notice']
    assert response.status_code == 200 and notice['login_state'] == 'unknown'
    assert notice['account'] is None and 'unavailable' in notice['account_note']
    assert s.calls == []


def test_worker_and_agent_cannot_manufacture_first_acknowledgement(notice_stack, monkeypatch):
    s = notice_stack
    monkeypatch.setattr(H, 'worker_problem', lambda _: '')
    s.cp.pane_mcp_url = 'http://127.0.0.1:8787/api/v1/mcp/pane'
    from lampway_server.herdr.launch_notice import NoticeRequired
    with pytest.raises(NoticeRequired):
        s.cp.create_session('claude', 'Synthetic worker', str(s.tmp), by='swarm',
                            swarm_worker=('swarm:owned:w1', 'synthetic-token'))
    with pytest.raises(NoticeRequired):
        s.cp.create_session('claude', 'Synthetic agent', str(s.tmp), by='agent')
    assert s.calls == s.status == []


def test_ack_is_private_minimal_and_restart_retains_only_disclosure(notice_stack):
    s = notice_stack
    from lampway_server.herdr.launch_notice import Notices
    body = create_body(s)
    nonce = s.http.post('/app/workbench/sessions', headers=s.headers,
                        json={**body, 'notice_request': True}).json()['notice']['nonce']
    s.http.post('/app/workbench/sessions', headers=s.headers, json={**body, 'notice_nonce': nonce})
    restarted = Notices(s.cp.root)
    assert restarted.acknowledged('claude') and restarted.pending == {}
    assert restarted.path.stat().st_mode & 0o777 == 0o600
    assert restarted.path.parent.stat().st_mode & 0o777 == 0o700
    s.strict.set_route('byoa:claude', False)
    assert s.http.post('/app/workbench/sessions', headers=s.headers, json=body).status_code == 403
    assert s.calls == ['create']


@pytest.mark.parametrize('raw', ['not json', '{"version":true,"harnesses":["claude"]}',
                                '{"version":1,"harnesses":["../claude"]}',
                                '{"version":1,"harnesses":["claude"],"account":"private"}'])
def test_invalid_retained_ack_refuses_without_overwriting(notice_stack, raw):
    s = notice_stack
    path = s.cp.launch_notices.path
    path.parent.mkdir(parents=True)
    path.write_text(raw)
    response = s.http.post('/app/workbench/sessions', headers=s.headers,
                           json={**create_body(s), 'notice_request': True})
    assert response.status_code == 403
    assert path.read_text() == raw and s.calls == s.status == []


def test_existing_ack_allows_agent_create_but_never_agent_notice(notice_stack):
    s = notice_stack
    body = create_body(s)
    nonce = s.http.post('/app/workbench/sessions', headers=s.headers,
                        json={**body, 'notice_request': True}).json()['notice']['nonce']
    assert s.http.post('/app/workbench/sessions', headers=s.headers,
                       json={**body, 'notice_nonce': nonce}).status_code == 200
    headers = {**s.headers, 'X-Lampway-Origin': 'agent'}
    assert s.http.post('/app/workbench/sessions', headers=headers, json=body).status_code == 200
    for field in ({'notice_request': True}, {'notice_nonce': nonce}):
        assert s.http.post('/app/workbench/sessions', headers=headers,
                           json={**body, **field}).status_code == 403
    assert s.calls == ['create', 'create'] and s.status == [True]


def test_existing_pane_notice_preparation_has_no_binding_effects(notice_stack, monkeypatch):
    s = notice_stack
    rec = {'id': 'existing-owned-pane', 'harness': 'claude', 'state': 'live'}
    monkeypatch.setattr(s.cp, 'find_by_scene', lambda _: [rec])
    monkeypatch.setattr(s.cp, 'bind', lambda *a, **k: pytest.fail('preparation bound a pane'))
    response = s.http.post('/app/workbench/mode', headers=s.headers, json={
        'mode': 'byoa', 'harness': 'claude', 'scene_session_id': 'new-scene',
        'previous_session_id': 'old-scene', 'notice_request': True})
    assert response.status_code == 200 and response.json() == {'notice': {'required': False}}
    assert s.calls == s.status == []


def test_existing_pane_cannot_ignore_a_forged_nonce(notice_stack, monkeypatch):
    s = notice_stack
    rec = {'id': 'existing-owned-pane', 'harness': 'claude', 'state': 'live'}
    monkeypatch.setattr(s.cp, 'find_by_scene', lambda _: [rec])
    monkeypatch.setattr(s.cp, 'bind', lambda *a, **k: s.calls.append('bind') or rec)
    response = s.http.post('/app/workbench/mode', headers=s.headers, json={
        'mode': 'byoa', 'harness': 'claude', 'scene_session_id': 'new-scene',
        'notice_nonce': 'not-issued'})
    assert response.status_code == 403
    assert s.calls == s.status == []


def test_independent_notice_stores_preserve_concurrent_acknowledgements(notice_stack):
    from concurrent.futures import ThreadPoolExecutor
    from lampway_server.herdr.launch_notice import Notices
    s = notice_stack
    stores = [Notices(s.cp.root) for _ in range(24)]
    ads = [SimpleNamespace(id='fixture_' + str(i), label='Synthetic fixture', route='byoa:claude',
                           status_argv=None) for i in range(len(stores))]
    nonces = [store.prepare(ad, 'synthetic-owner', 'synthetic-operation')['nonce']
              for store, ad in zip(stores, ads)]
    def admit(i):
        stores[i].admit(ads[i], 'synthetic-owner', 'synthetic-operation', nonces[i])
    with ThreadPoolExecutor(max_workers=12) as workers:
        list(workers.map(admit, range(len(stores))))
    assert all(stores[0].acknowledged(ad.id) for ad in ads)


def test_nonce_is_bound_to_its_endpoint(notice_stack):
    s = notice_stack
    body = {**create_body(s), 'mode': 'byoa', 'harness': 'claude',
            'scene_session_id': 'synthetic-scene'}
    nonce = s.http.post('/app/workbench/sessions', headers=s.headers,
                        json={**body, 'notice_request': True}).json()['notice']['nonce']
    response = s.http.post('/app/workbench/mode', headers=s.headers,
                           json={**body, 'notice_nonce': nonce})
    assert response.status_code == 403 and s.calls == []


def test_fresh_host_route_off_remains_first_actionable_refusal(notice_stack):
    s = notice_stack
    s.strict.set_route('byoa:claude', False)
    with pytest.raises(E.EgressRefused, match='byoa:claude is off'):
        s.cp.create_session('claude', 'Synthetic direct launch', str(s.tmp), by='user')
    assert s.calls == s.status == [] and not s.cp.launch_notices.path.exists()


def test_fresh_unsupported_worker_refuses_readiness_before_notice(notice_stack, monkeypatch):
    from lampway_server.herdr.host import CockpitError
    s = notice_stack
    monkeypatch.setattr(H, 'worker_problem', lambda _: 'synthetic unsupported worker endpoint')
    with pytest.raises(CockpitError, match='synthetic unsupported worker endpoint'):
        s.cp.create_session('claude', 'Synthetic worker', str(s.tmp), by='swarm',
                            swarm_worker=('swarm:owned:w1', 'synthetic-token'))
    assert s.calls == s.status == [] and not s.cp.launch_notices.path.exists()


def test_changed_default_project_cannot_consume_notice(notice_stack, monkeypatch):
    s = notice_stack
    body = {**create_body(s), 'cwd': ''}
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(s.tmp / 'before'))
    nonce = s.http.post('/app/workbench/sessions', headers=s.headers,
                        json={**body, 'notice_request': True}).json()['notice']['nonce']
    monkeypatch.setenv('LAMPWAY_PROJECT_ROOT', str(s.tmp / 'after'))
    response = s.http.post('/app/workbench/sessions', headers=s.headers,
                           json={**body, 'notice_nonce': nonce})
    assert response.status_code == 403 and s.calls == []


@pytest.mark.parametrize('email,logged_in,want', [
    ('notice-fixture@example.invalid', True, 'notice-fixture@example.invalid'),
    ('notice-fixture@example.invalid', False, None), ('unsafe\nlabel', True, None),
    ({'email': 'nested'}, True, None), ('x' * 201, True, None)])
def test_claude_confirmed_status_email_is_the_only_display_identity(email, logged_in, want):
    import json
    state = H.get('claude').read_status(0, json.dumps({'loggedIn': logged_in, 'authMethod': 'claude.ai',
        'email': email, 'orgName': 'DO_NOT_DISPLAY_OR_PERSIST', 'subscriptionType': 'DO_NOT_DISPLAY'}))
    assert state.account_label == want


def test_existing_pane_consumes_issued_mode_nonce_and_refuses_replay(notice_stack, monkeypatch):
    s = notice_stack
    body = {'mode': 'byoa', 'harness': 'claude', 'scene_session_id': 'synthetic-scene'}
    nonce = s.http.post('/app/workbench/mode', headers=s.headers,
                        json={**body, 'notice_request': True}).json()['notice']['nonce']
    rec = {'id': 'existing-owned-pane', 'harness': 'claude', 'state': 'live'}
    monkeypatch.setattr(s.cp, 'find_by_scene', lambda _: [rec])
    monkeypatch.setattr(s.cp, 'bind', lambda *a, **k: s.calls.append('bind') or rec)
    confirmed = {**body, 'notice_nonce': nonce}
    assert s.http.post('/app/workbench/mode', headers=s.headers, json=confirmed).status_code == 200
    assert s.cp.launch_notices.acknowledged('claude') and s.calls == ['bind']
    assert s.http.post('/app/workbench/mode', headers=s.headers, json=confirmed).status_code == 403
    assert s.calls == ['bind'] and s.status == [True]
