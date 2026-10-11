# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit summary aliases must be project-bound and retain the existing service guards."""
from types import SimpleNamespace
import pytest

from lampway_server.engine import gateway as GW, wiring as W
from lampway_server.agent.providers.base import Text
from lampway_server.app import create_app
from starlette.testclient import TestClient


def test_gateway_passes_the_summary_alias_to_the_provider_selector(settings, provider):
    app = create_app(settings, provider=provider)
    summary = SimpleNamespace(name='summary', model='small', stream=provider.stream)
    seen = []
    def choose(session_id=None, requested_model=None):
        seen.append((session_id, requested_model))
        return summary if requested_model == 'lampway-summary-selected' else app.state.agent.provider
    from starlette.applications import Starlette
    reg = GW.Registry()
    token = reg.issue_token('unit')
    http = TestClient(Starlette(routes=GW.gateway_routes(reg, choose)), base_url='http://127.0.0.1:8787', client=('127.0.0.1', 50000))
    response = http.post(GW.CHAT_PATH, headers={'Authorization': f'Bearer {token}'}, json={
        'model': 'lampway-summary-selected', 'messages': [{'role': 'user', 'content': 'Summarize'}]})
    assert response.status_code == 200, response.text
    assert seen == [('unit', 'lampway-summary-selected')], 'Gateway currently drops the explicit summarizer alias'
    assert response.json()['model'] == 'small'


def summary_setup(settings, tmp_path, monkeypatch):
    from lampway_server import choices as CH
    from lampway_server.choices.snapshot import World
    from lampway_server.engine.context_settings import Store, service_identity, summary_alias
    settings.provider = 'openrouter'
    settings.openrouter_model = 'parent'
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(
        connections={'openrouter': 'connected'}, routes={'openrouter': True},
        catalogue={'openrouter': frozenset({'parent', 'summary-small'})}))
    project = str(tmp_path / 'project')
    store = Store(settings.state_dir)
    selection = 'openrouter:summary-small'
    store.update(project, {'summarizing_model': selection}, [], summary_service=service_identity(settings))
    agent = SimpleNamespace(provider=SimpleNamespace(name='openrouter', model='parent'),
        cockpit=SimpleNamespace(list_sessions=lambda: [
            {'agent': 'lampway_hermes', 'state': 'live', 'unit': 'unit', 'project_root': project}]))
    return agent, store, project, selection, summary_alias(selection), CH


def test_only_the_explicit_project_alias_routes_and_parent_model_is_unchanged(settings, tmp_path, monkeypatch):
    import pytest
    agent, store, project, selection, alias, CH = summary_setup(settings, tmp_path, monkeypatch)
    get = W.provider_getter(agent, settings=settings)
    chosen = get('unit', requested_model=alias)
    assert chosen.model == 'summary-small'
    assert chosen.resolution.option == selection and chosen.resolution.purpose == 'agent.main'
    assert chosen.resolution.skipped == []
    assert get('unit') is agent.provider
    assert get('unit', requested_model='lampway') is agent.provider
    assert settings.openrouter_model == 'parent'
    assert store.config(project)['auxiliary']['compression']['model'] == alias
    for unit, model in (('other-unit', alias), ('unit', 'lampway-summary-unknown'),
                        ('swarm:s:w', alias)):
        with pytest.raises(ValueError):
            get(unit, requested_model=model)
    store.update(project, {}, ['summarizing_model'])
    with pytest.raises(ValueError):
        get('unit', requested_model=alias)


def test_service_or_endpoint_change_refuses_the_saved_model_without_fallback(settings, tmp_path, monkeypatch):
    import pytest
    from lampway_server.engine.context_settings import selected_summary, service_identity, Store, summary_alias
    agent, store, project, selection, alias, CH = summary_setup(settings, tmp_path, monkeypatch)
    before = store.path.read_bytes()
    settings.provider = 'chatgpt_plan'
    assert W.provider_getter(agent, settings=settings)('unit', requested_model=alias).resolution.option == selection
    assert store.path.read_bytes() == before
    settings.provider = 'openai'
    settings.openai_base_url = 'http://127.0.0.1:8788/v1'
    other = Store(tmp_path / 'local-state')
    other.update(project, {'summarizing_model': 'openai:local'}, [], summary_service=service_identity(settings))
    settings.openai_base_url = 'http://127.0.0.1:8789/v1'
    with pytest.raises(ValueError, match='service or endpoint changed'):
        selected_summary(other, project, settings, summary_alias('openai:local'))


def test_summary_rechecks_choices_connection_route_privacy_catalogue_and_spend(settings, tmp_path, monkeypatch):
    import pytest
    from lampway_server.choices.snapshot import World
    agent, store, project, selection, alias, CH = summary_setup(settings, tmp_path, monkeypatch)
    get = W.provider_getter(agent, settings=settings)
    allowed = {'connections': {'openrouter': 'connected'}, 'routes': {'openrouter': True}}
    denied = [World(**{**allowed, 'connections': {'openrouter': 'disconnected'}}),
              World(**{**allowed, 'routes': {'openrouter': False}}),
              World(**allowed, catalogue={'openrouter': frozenset({'parent'})}),
              World(**allowed, enforce_private=True, zdr=frozenset()),
              World(**allowed, costs={selection: {'amount': 2}}, spend={'openrouter': {'job_cap': 1}}),
              World(**allowed, local={selection: 'not ready'})]
    for world in denied:
        monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda world=world: world)
        with pytest.raises(ValueError):
            get('unit', requested_model=alias)
    assert agent.provider.model == 'parent'


def test_summary_uses_existing_factory_egress_context_and_closes_its_own_client(settings, tmp_path, monkeypatch):
    import asyncio
    from lampway_server.agent import providers as P
    from lampway_server.agent.providers.base import ModelRequest, Message
    from lampway_server import egress as E
    agent, store, project, selection, alias, CH = summary_setup(settings, tmp_path, monkeypatch)
    seen, closed, contexts = [], [], []
    class Provider:
        name = 'openrouter'
        model = 'summary-small'
        client = SimpleNamespace(aclose=lambda: close())
        async def stream(self, request):
            yield Text('summary')
    async def close():
        closed.append(True)
    def factory(s, chatgpt_auth=None, resolution=None):
        seen.append((s, chatgpt_auth, resolution.option))
        return Provider()
    from contextlib import contextmanager
    @contextmanager
    def context(**kw):
        contexts.append(kw)
        yield
    monkeypatch.setattr(P, 'make_provider', factory)
    monkeypatch.setattr(E, 'context', context)
    async def run():
        chosen = W.provider_getter(agent, settings=settings)('unit', requested_model=alias)
        return [e async for e in chosen.stream(ModelRequest('', [Message('user', [])], [], 'unit'))]
    assert len(asyncio.run(run())) == 1
    assert seen == [(settings, None, selection)]
    assert closed == [True]
    assert contexts and all(c['option'] == selection and c['content_class'] == 'private' for c in contexts)


def test_user_save_and_gateway_route_keep_auth_admission_and_exact_model(settings, tmp_path, monkeypatch, provider):
    from lampway_server.engine.context_settings import summary_alias
    from lampway_server.agent import providers as P
    from .fake_client import FakeMixarClient
    from lampway_server import choices as CH
    from lampway_server.choices.snapshot import World
    settings.provider = 'openrouter'
    settings.openrouter_model = 'parent'
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(connections={'openrouter': 'connected'},
        routes={'openrouter': True}, catalogue={'openrouter': frozenset({'parent', 'summary-small'})}))
    app = create_app(settings, provider=provider)
    http = TestClient(app, base_url='http://127.0.0.1:8787', client=('127.0.0.1', 50000))
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    project, option = str(tmp_path / 'project'), 'openrouter:summary-small'
    saved = user.put('/app/agent/context', json={'project': project, 'values': {'summarizing_model': option}})
    assert saved.status_code == 200, saved.text
    assert saved.json()['overrides'] == {'summarizing_model': option}
    monkeypatch.setattr(app.state.agent.cockpit, 'list_sessions', lambda: [
        {'agent': 'lampway_hermes', 'state': 'live', 'unit': 'unit', 'project_root': project}])
    constructed, sent = [], []
    class Summary:
        name, model = 'openrouter', 'summary-small'
        async def stream(self, request):
            sent.append(request)
            yield Text('summary')
    def construct(s, auth=None):
        constructed.append((s.provider, s.openrouter_model, s.openrouter_budget_usd))
        return Summary()
    monkeypatch.setattr(P, '_make_provider', construct)
    token = app.state.engine_tokens.issue_token('unit')
    headers = {'Authorization': f'Bearer {token}'}
    body = {'model': summary_alias(option), 'messages': [{'role': 'user', 'content': 'Summary input'}]}
    response = http.post(GW.CHAT_PATH, json=body, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()['model'] == 'summary-small'
    assert constructed == [('openrouter', 'summary-small', settings.openrouter_budget_usd)]
    assert len(sent) == 1 and provider.requests == [] and settings.openrouter_model == 'parent'
    response = http.post(GW.CHAT_PATH, json={**body, 'model': 'lampway-summary-unknown'}, headers=headers)
    assert response.status_code >= 400 and len(sent) == 1
    app.state.engine_tokens.revoke(token)
    assert http.post(GW.CHAT_PATH, json=body, headers=headers).status_code == 401
    assert len(sent) == 1
    assert http.post(GW.CHAT_PATH, json=body, headers=user.rest_headers()).status_code == 401
    other = TestClient(app, base_url='http://127.0.0.1:8787', client=('203.0.113.10', 50000))
    assert other.post(GW.CHAT_PATH, json=body, headers=headers).status_code == 403
    token = app.state.engine_tokens.issue_token('unit')
    app.state.engine_tokens.first_check = lambda *_: 'forbidden tool'
    blocked = {**body, 'tools': [{'type': 'function', 'function': {'name': 'forbidden'}}]}
    response = http.post(GW.CHAT_PATH, json=blocked, headers={'Authorization': f'Bearer {token}'})
    assert response.status_code == 400 and len(sent) == 1


def test_context_save_refuses_other_services_or_unavailable_models_without_mutation(settings, tmp_path, monkeypatch, provider):
    from .fake_client import FakeMixarClient
    from lampway_server import choices as CH
    from lampway_server.choices.snapshot import World
    settings.provider, settings.openrouter_model = 'openrouter', 'parent'
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(connections={'openrouter': 'connected'},
        routes={'openrouter': True}, catalogue={'openrouter': frozenset({'parent'})}))
    app = create_app(settings, provider=provider)
    http = TestClient(app, base_url='http://127.0.0.1:8787')
    user = FakeMixarClient(http, password=settings.user_password)
    user.login()
    for option in ('anthropic:claude-sonnet-5-5', 'openrouter:unavailable', 'lampway-summary-0000000000000000'):
        response = user.put('/app/agent/context', json={'project': str(tmp_path / 'project'),
            'values': {'summarizing_model': option}})
        assert response.status_code == 400, response.text
        assert not (settings.state_dir / 'agent_context.json').exists()


def test_named_local_model_preserves_endpoint_and_named_chatgpt_model_shares_app_auth(settings, tmp_path, monkeypatch):
    import asyncio
    from lampway_server import choices as CH
    from lampway_server.choices.snapshot import World
    from lampway_server.engine.context_settings import Store, service_identity, summary_alias
    from lampway_server.agent import providers as P
    from lampway_server.agent.providers.base import ModelRequest
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(
        connections={'chatgpt_plan': 'connected'}, routes={'chatgpt_plan': True}))
    project, store = str(tmp_path / 'project'), Store(settings.state_dir)
    auth = object()
    rec = {'agent': 'lampway_hermes', 'state': 'live', 'unit': 'unit', 'project_root': project}
    agent = SimpleNamespace(provider=SimpleNamespace(auth=auth), cockpit=SimpleNamespace(list_sessions=lambda: [rec]))
    received = []
    class Provider:
        async def stream(self, request):
            yield Text('summary')
    def factory(s, auth=None):
        received.append((s.provider, s.openai_model, s.openai_base_url, s.chatgpt_model, auth))
        return Provider()
    monkeypatch.setattr(P, '_make_provider', factory)
    async def call(selection):
        chosen = W.provider_getter(agent, settings=settings)('unit', requested_model=summary_alias(selection))
        return chosen, [e async for e in chosen.stream(ModelRequest('', [], [], 'unit'))]
    settings.provider, settings.openai_model = 'openai', 'parent-local'
    settings.openai_base_url = 'http://127.0.0.1:9876/v1'
    store.update(project, {'summarizing_model': 'openai:small-local'}, [], summary_service=service_identity(settings))
    chosen, _ = asyncio.run(call('openai:small-local'))
    assert chosen.model == 'small-local'
    assert received[-1][:3] == ('openai', 'small-local', 'http://127.0.0.1:9876/v1')
    assert settings.openai_model == 'parent-local'
    settings.provider, settings.chatgpt_model = 'chatgpt_plan', 'parent-plan'
    store.update(project, {'summarizing_model': 'chatgpt_plan:summary-plan'}, [], summary_service=service_identity(settings))
    chosen, _ = asyncio.run(call('chatgpt_plan:summary-plan'))
    assert chosen.model == 'summary-plan'
    assert received[-1][3:] == ('summary-plan', auth)
    assert settings.chatgpt_model == 'parent-plan'


@pytest.mark.parametrize("worker", [False, True])
def test_revoking_a_summary_token_cancels_the_running_call_and_closes_only_its_client(settings, tmp_path, monkeypatch, worker):
    import asyncio
    import httpx
    from starlette.applications import Starlette
    from lampway_server.agent import providers as P
    agent, store, project, selection, alias, CH = summary_setup(settings, tmp_path, monkeypatch)
    key = 'swarm:s:w' if worker else 'unit'
    if worker:
        agent.swarm = SimpleNamespace(bindings=SimpleNamespace(is_live=lambda name: name == key, choice_for=lambda name: object()))
        agent.cockpit.list_sessions = lambda: [{'agent': 'lampway_hermes', 'state': 'live', 'role': 'worker',
            'created_by': 'swarm', 'swarm_binding': key, 'unit': 'parent-unit', 'project_root': project}]
    async def run():
        started, cancelled, closed = asyncio.Event(), asyncio.Event(), []
        class Held:
            name, model = 'openrouter', 'summary-small'
            client = SimpleNamespace(aclose=lambda: close())
            async def stream(self, request):
                try:
                    started.set()
                    await asyncio.Future()
                    yield Text('never')
                finally:
                    cancelled.set()
        async def close():
            closed.append(True)
        monkeypatch.setattr(P, 'make_provider', lambda *a, **kw: Held())
        registry = GW.Registry()
        token, main = registry.issue_token(key), registry.issue_token('unrelated-main')
        app = Starlette(routes=GW.gateway_routes(registry, W.provider_getter(agent, settings=settings)))
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=('127.0.0.1', 50000)),
                                     base_url='http://127.0.0.1:8787') as http:
            request = asyncio.create_task(http.post(GW.CHAT_PATH, headers={'Authorization': f'Bearer {token}'},
                json={'model': alias, 'messages': [{'role': 'user', 'content': 'Summarize'}]}))
            await asyncio.wait_for(started.wait(), 2)
            registry.revoke(token)
            response = await asyncio.wait_for(request, 2)
            await asyncio.wait_for(cancelled.wait(), 2)
        assert response.status_code >= 400
        assert closed == [True]
        assert registry.session_for(main) == 'unrelated-main'
    asyncio.run(run())


def test_cross_service_summary_keeps_exact_selection_and_existing_app_auth(settings, tmp_path, monkeypatch):
    import asyncio
    from lampway_server import choices as CH
    from lampway_server.choices.snapshot import World
    from lampway_server.engine.context_settings import Store, service_identity, summary_alias, resolve_summary
    from lampway_server.agent import providers as P
    from lampway_server.agent.providers.base import ModelRequest
    settings.provider, settings.openrouter_model = 'openrouter', 'parent'
    selection = 'chatgpt_plan:gpt-5.5'
    monkeypatch.setattr(CH, 'WORLD_FACTORY', lambda: World(
        connections={'chatgpt_plan': 'connected'}, routes={'chatgpt_plan': True}))
    project = str(tmp_path / 'project')
    resolved = resolve_summary(settings, project, selection)
    assert resolved.provider == 'chatgpt_plan' and resolved.option == selection
    Store(settings.state_dir).update(project, {'summarizing_model': selection}, [], service_identity(settings, selection))
    auth, sent = object(), []
    agent = SimpleNamespace(provider=SimpleNamespace(name='openrouter', model='parent'), cockpit=SimpleNamespace(list_sessions=lambda: [
        {'agent': 'lampway_hermes', 'state': 'live', 'unit': 'unit', 'project_root': project}]))
    class Provider:
        async def stream(self, request):
            yield Text('summary')
    def factory(s, auth=None):
        sent.append((s.provider, s.chatgpt_model, auth))
        return Provider()
    monkeypatch.setattr(P, '_make_provider', factory)
    async def run():
        chosen = W.provider_getter(agent, settings=settings, chatgpt_auth=auth)('unit', requested_model=summary_alias(selection))
        return [e async for e in chosen.stream(ModelRequest('', [], [], 'unit'))]
    assert len(asyncio.run(run())) == 1
    assert sent == [('chatgpt_plan', 'gpt-5.5', auth)]
    assert settings.provider == 'openrouter' and settings.openrouter_model == 'parent'


def test_owned_live_worker_summary_uses_project_alias_without_replacing_pinned_normal_choice(settings, tmp_path, monkeypatch):
    import pytest
    agent, store, project, selection, alias, CH = summary_setup(settings, tmp_path, monkeypatch)
    key = 'swarm:s:w'
    pinned = SimpleNamespace(provider='openrouter', option='openrouter:parent', model='parent', params={})
    normal = SimpleNamespace(name='openrouter', model='worker-pinned')
    bindings = SimpleNamespace(is_live=lambda name: name == key, choice_for=lambda name: pinned if name == key else None)
    agent.swarm = SimpleNamespace(bindings=bindings)
    agent.swarm_provider_factory = lambda label, resolution=None: normal
    rec = {'agent': 'lampway_hermes', 'state': 'live', 'role': 'worker', 'created_by': 'swarm',
           'swarm_binding': key, 'unit': 'parent-unit', 'project_root': project}
    agent.cockpit.list_sessions = lambda: [rec]
    getter = W.provider_getter(agent, settings=settings)
    assert getter(key) is normal
    assert getter(key, requested_model=alias).resolution.option == selection
    assert getter(key) is normal
    rec['project_root'] = str(tmp_path / 'other')
    with pytest.raises(ValueError):
        getter(key, requested_model=alias)
    rec['project_root'] = project
    bindings.is_live = lambda name: False
    with pytest.raises(ValueError):
        getter(key, requested_model=alias)
