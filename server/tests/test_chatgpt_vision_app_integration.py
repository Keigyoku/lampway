# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Actual create_app/lifespan; only runtime and HTTP boundaries are synthetic."""
import asyncio
import json
import re
from types import SimpleNamespace

import httpx
import pytest

from .test_chatgpt_vision import stack, stream_response


@pytest.fixture
def integrated(stack, tmp_path, monkeypatch):
    auth, vision = stack
    for key in ('HOME', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'LAMPWAY_HOME', 'LAMPWAY_PROJECT_ROOT', 'LAMPWAY_SECRETS_DIR'):
        monkeypatch.setenv(key, str(tmp_path / key))
    import keyring
    from keyring.backends.fail import Keyring
    previous_keyring = keyring.get_keyring()
    keyring.set_keyring(Keyring())
    from lampway_server import app as A, egress
    from lampway_server.config import Settings
    from lampway_server.engine import wiring
    from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanProvider
    trace = []; requests = []
    class Engine:
        units = SimpleNamespace(capabilities_changed=lambda: trace.append('refresh'))
        async def start(self): trace.append('start')
        async def stop(self): trace.append('stop')
        async def tick(self): pytest.fail('No maintenance tick expected')
    engine = Engine()
    def wire(settings, agent, tokens, *, chatgpt_auth):
        assert chatgpt_auth is auth
        trace.append('wire')
        return engine
    monkeypatch.setattr(wiring, 'wire', wire)
    monkeypatch.setattr(A, '_open_library', lambda vault: None)
    import subprocess, socket
    monkeypatch.setattr(subprocess.Popen, '__init__', lambda *a, **k: pytest.fail('Native process launch forbidden'))
    monkeypatch.setattr(socket.socket, 'connect', lambda *a, **k: pytest.fail('Actual socket connection forbidden'))
    def response(request):
        assert str(request.url) == vision.ROUTE
        requests.append(json.loads(request.content))
        return stream_response()
    original_client = httpx.AsyncClient
    def client(*a, **kw):
        if kw.get('transport') is None: kw['transport'] = httpx.MockTransport(response)
        return original_client(*a, **kw)
    monkeypatch.setattr(httpx, 'AsyncClient', client)
    egress.set_active(egress.Egress.permissive(tmp_path / 'egress'))
    cockpit = SimpleNamespace(root=tmp_path / 'cockpit', reconcile=lambda: trace.append('reconcile'), expire_pane_images=lambda: None)
    settings = Settings(state_dir=tmp_path / 'app-state', provider='chatgpt_plan', chatgpt_model='synthetic-model')
    provider = ChatGPTPlanProvider(auth, 'synthetic-model', transport=httpx.MockTransport(response))
    application = A.create_app(settings, provider=provider, chatgpt_auth=auth, cockpit=cockpit,
        connections_transport=httpx.MockTransport(lambda r: pytest.fail('Unexpected Connections HTTP')))
    yield SimpleNamespace(app=application, auth=auth, vision=vision, trace=trace, requests=requests, client=original_client)
    egress.set_active(None)
    keyring.set_keyring(previous_keyring)


def nonce(page):
    assert page.status_code == 200
    return re.search('name="consent" value="([^"]+)"', page.text)[1]


async def admitted_page(x, client):
    """Prepare the browser entry through the authenticated human Client."""
    token = x.app.state.auth.issue_pair()['access_token']
    response = await client.post('/app/chatgpt/vision/ticket', json={}, headers={'Authorization': 'Bearer ' + token})
    assert response.status_code == 200, response.text
    return await client.get(response.json()['path'])


def test_actual_app_lifecycle_consent_probe_and_refresh(integrated):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                page = await admitted_page(x, c)
                ticket = nonce(page)
                assert not x.requests and not x.vision._path(x.auth, 'synthetic-model').exists()
                result = await c.post('/app/chatgpt/vision', data={'consent': ticket}, headers={'Origin': 'http://127.0.0.1:8787'})
                assert result.status_code == 200 and result.json()['images_enabled'] is True
                assert x.vision.admitted(x.auth, 'synthetic-model')
                assert (await c.post('/app/chatgpt/vision', data={'consent': ticket})).status_code >= 400
                assert len(x.requests) == 1
    asyncio.run(run())
    assert x.trace == ['wire', 'reconcile', 'start', 'refresh', 'stop']


@pytest.mark.parametrize('headers', [{'X-Lampway-Origin': 'agent'}, {'X-Mixar-Job-Origin': 'mcp'},
    {'Authorization': 'Bearer synthetic-invalid'}, {'Origin': 'http://127.0.0.1:9999'}, {'Origin': 'https://outside.invalid'}])
def test_actual_app_origin_and_bearer_guards(integrated, headers):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                assert (await c.get('/app/chatgpt/vision', headers=headers)).status_code == 403
    asyncio.run(run())
    assert not x.requests and 'refresh' not in x.trace


def test_actual_app_model_selection_invalidates_displayed_consent(integrated):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                ticket = nonce(await admitted_page(x, c))
                token = x.app.state.auth.issue_pair()['access_token']
                update = await c.put('/app/provider-settings', json={'values': {'chatgpt_model': 'other-model'}}, headers={'Authorization': 'Bearer ' + token})
                assert update.status_code == 200, update.text
                assert x.app.state.agent.provider.model == 'other-model'
                assert (await c.post('/app/chatgpt/vision', data={'consent': ticket})).status_code == 409
                assert not x.requests
                ticket = nonce(await admitted_page(x, c))
                assert (await c.post('/app/chatgpt/vision', data={'consent': ticket})).status_code == 200
                assert x.requests[0]['model'] == 'other-model'
                assert x.vision.admitted(x.auth, 'other-model') and not x.vision.admitted(x.auth, 'synthetic-model')
    asyncio.run(run())


def test_actual_app_scope_change_refuses_preexisting_consent(integrated):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                ticket = nonce(await admitted_page(x, c))
                state = x.auth._read(); state['accounts'][state['selected']]['vision_login_id'] = 'different-login'; x.auth._write(state)
                assert (await c.post('/app/chatgpt/vision', data={'consent': ticket})).status_code == 409
    asyncio.run(run())
    assert not x.requests and 'refresh' not in x.trace


def test_actual_app_signout_revokes_admission_and_pending_consent(integrated):
    x = integrated
    from .test_chatgpt_vision import verified
    verified(x.auth, x.vision)
    revocations = []
    x.auth.http = httpx.Client(transport=httpx.MockTransport(lambda r: (revocations.append(str(r.url)) or httpx.Response(200))))
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                ticket = nonce(await admitted_page(x, c))
                assert x.vision.admitted(x.auth, 'synthetic-model')
                assert (await c.post('/app/chatgpt/signout')).status_code == 303
                assert not x.vision.admitted(x.auth, 'synthetic-model')
                assert (await c.post('/app/chatgpt/vision', data={'consent': ticket})).status_code == 403
    asyncio.run(run())
    assert not x.requests


def test_raw_loopback_cannot_mint_consent(integrated):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                assert (await c.get('/app/chatgpt/vision')).status_code == 403
                assert (await c.post('/app/chatgpt/vision/ticket', json={})).status_code == 403
                assert (await c.post('/app/chatgpt/vision', data={'consent': 'not-issued'})).status_code == 403
                assert not x.requests and not x.vision._path(x.auth, 'synthetic-model').exists()
    asyncio.run(run())


@pytest.mark.parametrize('origin', ['agent', 'mcp'])
def test_authenticated_agent_claims_cannot_prepare_admission(integrated, origin):
    from lampway_server.auth import mint_jwt
    import time
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                token = mint_jwt(x.app.state.auth._secret, {'sub': 'synthetic-agent', 'exp': time.time() + 3600, 'origin': origin})
                assert (await c.post('/app/chatgpt/vision/ticket', json={}, headers={'Authorization': 'Bearer ' + token})).status_code == 403
                assert not x.requests
    asyncio.run(run())


@pytest.mark.parametrize('headers', [{'X-Lampway-Origin': 'agent'}, {'X-Mixar-Job-Origin': 'mcp'}, {'Origin': 'http://127.0.0.1:9999'}])
def test_human_bearer_does_not_override_declared_agent_or_cross_origin(integrated, headers):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                token = x.app.state.auth.issue_pair()['access_token']
                assert (await c.post('/app/chatgpt/vision/ticket', json={}, headers={**headers, 'Authorization': 'Bearer ' + token})).status_code == 403
                assert not x.requests
    asyncio.run(run())


def test_admission_exchange_is_one_use_and_account_bound(integrated):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                token = x.app.state.auth.issue_pair()['access_token']
                async def entry():
                    response = await c.post('/app/chatgpt/vision/ticket', json={}, headers={'Authorization': 'Bearer ' + token})
                    assert response.status_code == 200 and response.headers['cache-control'] == 'no-store'
                    assert token not in response.text and 'synthetic-account' not in response.text
                    from lampway_server.logredact import redact_text
                    path = response.json()['path']
                    assert path.split('ticket=')[1] not in redact_text(path)
                    return path
                path = await entry()
                page = await c.get(path)
                assert page.status_code == 200 and page.headers['referrer-policy'] == 'no-referrer'
                assert "form-action 'self'" in page.headers['content-security-policy']
                assert (await c.get(path)).status_code == 403
                path = await entry()
                state = x.auth._read(); state['accounts'][state['selected']]['vision_login_id'] = 'changed-login'; x.auth._write(state)
                assert (await c.get(path)).status_code == 409
                assert (await c.get(path)).status_code == 403
                assert not x.requests
    asyncio.run(run())


def test_admission_expiry_is_bound_to_authenticated_session(integrated, monkeypatch):
    from lampway_server import chatgpt_vision_routes as routes
    from lampway_server.auth import mint_jwt
    import time
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                now = time.time()
                token = mint_jwt(x.app.state.auth._secret, {'sub': 'synthetic-user', 'exp': now + 30})
                response = await c.post('/app/chatgpt/vision/ticket', json={}, headers={'Authorization': 'Bearer ' + token})
                assert response.status_code == 200
                with monkeypatch.context() as patch:
                    patch.setattr(routes.time, 'time', lambda: now + 31)
                    assert (await c.get(response.json()['path'])).status_code == 403
                assert not x.requests
    asyncio.run(run())


@pytest.mark.parametrize("late_claims", [None, {}, {"exp": "bad"}, {"exp": float("inf")}, {"exp": True}])
def test_auth_expiry_between_ticket_guard_reads_fails_closed(integrated, monkeypatch, late_claims):
    x = integrated
    async def run():
        async with x.app.router.lifespan_context(x.app):
            async with x.client(transport=httpx.ASGITransport(x.app, client=('127.0.0.1', 1234)), base_url='http://127.0.0.1:8787') as c:
                auth = x.app.state.auth
                token = auth.issue_pair()['access_token']
                claims = auth.verify_access(token)
                reads = []
                def expiry_race(value):
                    reads.append(value)
                    return claims if len(reads) <= 3 else late_claims
                monkeypatch.setattr(auth, 'verify_access', expiry_race)
                response = await c.post('/app/chatgpt/vision/ticket', json={}, headers={'Authorization': 'Bearer ' + token})
                assert response.status_code == 403, response.text
                assert not x.requests
    asyncio.run(run())
