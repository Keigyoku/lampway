# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Prepared gateway image RED fixtures. Synthetic in-process transport only."""
import base64
import json
from copy import deepcopy

import pytest
from starlette.applications import Starlette
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import Text
from lampway_server.engine import gateway as GW

DATA = base64.b64encode(b'\x89PNG\r\n\x1a\nsynthetic attached bytes').decode()
SOURCE = {"type": "base64", "media_type": "image/png", "data": DATA}
BODY = {"messages": [{"role": "user", "content": [
    {"type": "text", "text": "Before image."},
    {"type": "image_url", "image_url": {"url": "data:image/png;base64," + DATA}},
    {"type": "text", "text": "After image."}]}]}


def test_data_image_reaches_neutral_request_with_original_bytes_type_and_caption_order():
    original = deepcopy(BODY)
    request = GW.to_request(BODY, "synthetic-session")
    assert request.messages[0].content == [
        {"type": "text", "text": "Before image."},
        {"type": "image", "source": SOURCE},
        {"type": "text", "text": "After image."}]
    assert base64.b64decode(request.messages[0].content[1]["source"]["data"]) == base64.b64decode(DATA)
    assert BODY == original


class RecordingProvider:
    name = "synthetic-selected-provider"
    model = "synthetic-model"

    def __init__(self, vision):
        self.supports_vision = vision
        self.requests = []

    async def stream(self, request):
        self.requests.append(request)
        yield Text("synthetic answer")


@pytest.mark.parametrize("stream", [False, True])
def test_live_selected_provider_gate_preserves_supported_then_omits_unsupported_images(stream):
    yes, no = RecordingProvider(True), RecordingProvider(False)
    selected = [yes]
    registry = GW.Registry()
    token = registry.issue_token("synthetic-session")
    app = Starlette(routes=GW.gateway_routes(registry, lambda session_id: selected[0]))
    with TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 50000)) as client:
        def ask():
            response = client.post(GW.CHAT_PATH, headers={"Authorization": "Bearer " + token},
                                   json={**BODY, "stream": stream})
            assert response.status_code == 200, response.text
        ask()
        assert yes.requests[0].messages[0].content[1] == {"type": "image", "source": SOURCE}
        selected[0] = no
        ask()
    message = no.requests[0].messages[0]
    assert not any(part.get("type") == "image" for part in message.content)
    assert "Before image." in message.text() and "After image." in message.text()
    assert "image omitted" in message.text()
    assert DATA not in str(no.requests[0])
    # Provider selection never changes the earlier request's durable content.
    assert yes.requests[0].messages[0].content[1]["source"] == SOURCE


def _wire_provider(kind, captured):
    import httpx
    import httpx2
    from lampway_server.agent.providers.anthropic_provider import AnthropicProvider
    from lampway_server.agent.providers.openai_compat import OpenAICompatProvider
    if kind == "anthropic":
        def handler(request):
            captured.append(json.loads(request.content))
            events = [
                {"type": "message_start", "message": {"id": "synthetic", "type": "message", "role": "assistant",
                    "model": "synthetic-model", "content": [], "stop_reason": None, "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 0}}},
                {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
                {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "synthetic answer"}},
                {"type": "content_block_stop", "index": 0},
                {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                    "usage": {"output_tokens": 1}},
                {"type": "message_stop"}]
            wire = ''.join('event: '+e['type']+'\ndata: '+json.dumps(e)+'\n\n' for e in events)
            return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=wire.encode())
        provider = AnthropicProvider(model="synthetic-model", api_key="synthetic-no-account",
                                     transport=httpx2.MockTransport(handler))
        expected = [{"type": "text", "text": "Before image."}, {"type": "image", "source": SOURCE},
                    {"type": "text", "text": "After image."}]
    else:
        def handler(request):
            captured.append(json.loads(request.content))
            return httpx.Response(200, headers={"content-type": "text/event-stream"},
                content='data: {"choices":[{"delta":{"content":"synthetic answer"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n')
        provider = OpenAICompatProvider("http://synthetic.invalid/v1", "synthetic-model",
                                       transport=httpx.MockTransport(handler))
        expected = BODY['messages'][0]['content']
    return provider, expected


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
def test_gateway_delivers_actual_provider_wire_images_without_real_network(kind):
    captured = []
    provider, expected = _wire_provider(kind, captured)
    # Explicit supported fixture declaration; no inference from account or model name.
    provider.supports_vision = True
    registry = GW.Registry()
    token = registry.issue_token("synthetic-session")
    app = Starlette(routes=GW.gateway_routes(registry, lambda: provider))
    with TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 50000)) as client:
        response = client.post(GW.CHAT_PATH, headers={"Authorization": "Bearer " + token}, json=BODY)
        assert response.status_code == 200, response.text
    users = [message for message in captured[0]['messages'] if message['role'] == 'user']
    assert users == [{'role':'user','content':expected}]
    assert DATA in str(users)
    assert len(captured) == 1, 'No automatic image or mutation retries'


@pytest.mark.parametrize("kind", ["anthropic", "openai"])
def test_native_screenshot_tool_result_keeps_typed_images_on_provider_wire(kind):
    from lampway_server.agent.providers.anthropic_provider import AnthropicProvider
    from lampway_server.agent.providers.openai_compat import OpenAICompatProvider
    body = {"messages": [{"role": "assistant", "content": None, "tool_calls": [
        {"id": "screenshot-call", "type": "function", "function": {"name": "screenshot", "arguments": "{}"}}]},
        {"role": "tool", "tool_call_id": "screenshot-call", "content": BODY['messages'][0]['content']}]}
    neutral = GW.to_request(body, "synthetic-session").messages[-1]
    assert neutral.content[0]['content'] == [
        {"type": "text", "text": "Before image."}, {"type": "image", "source": SOURCE},
        {"type": "text", "text": "After image."}]
    if kind == 'anthropic':
        provider = object.__new__(AnthropicProvider)
        wire = provider._message(neutral)
        assert wire['content'][0]['tool_use_id'] == 'screenshot-call'
        assert wire['content'][0]['content'] == neutral.content[0]['content']
    else:
        wire = OpenAICompatProvider._messages(neutral)
        assert wire[0]['role'] == 'tool' and wire[0]['tool_call_id'] == 'screenshot-call'
        assert isinstance(wire[0]['content'], str)
        assert wire[1]['role'] == 'user'
        assert 'screenshot-call' in wire[1]['content'][0]['text']
        assert wire[1]['content'][1:] == BODY['messages'][0]['content']


def test_selected_main_worker_and_summary_vision_never_inherits_wrong_model():
    from types import SimpleNamespace
    from lampway_server.engine import wiring as W
    def provider(model):
        return SimpleNamespace(name='openai', model=model, base_url='http://127.0.0.1:9/v1')
    saved = {'provider':'openai','model':'main-model','base_url':'http://127.0.0.1:9/v1','supports_vision':True}
    main, worker = provider('main-model'), provider('worker-model')
    resolution = SimpleNamespace(provider='openai', model='local', params={'model':'worker-model','base_url':worker.base_url})
    agent = SimpleNamespace(provider=main, settings_store=SimpleNamespace(byok=lambda:saved),
                            swarm=SimpleNamespace(bindings=SimpleNamespace(choice_for=lambda key:resolution)),
                            swarm_provider_factory=lambda label, resolution:worker)
    get = W.provider_getter(agent)
    assert get.vision_for('main', get('main')) is True
    assert get.vision_for('swarm:one:worker', get('swarm:one:worker')) is False
    summary = W._SummaryProvider(SimpleNamespace(), agent, resolution)
    assert summary.supports_vision is False
    resolution.params['supports_vision'] = True
    assert W._SummaryProvider(SimpleNamespace(), agent, resolution).supports_vision is True
    saved['supports_vision'] = False
    assert get.vision_for('main', get('main')) is False
    saved['supports_vision'] = True
    saved['model'] = 'unrelated-model'
    assert get.vision_for('main', get('main')) is False


@pytest.mark.parametrize('kind', ['anthropic', 'openai'])
def test_parallel_screenshot_results_acknowledge_all_ids_before_images_on_actual_wire(kind):
    captured = []
    provider, expected = _wire_provider(kind, captured)
    provider.supports_vision = True
    calls = [{'id':call, 'type':'function', 'function':{'name':'screenshot','arguments':'{}'}} for call in ['first','second']]
    body = {'messages':[{'role':'assistant','content':None,'tool_calls':calls},
                        {'role':'tool','tool_call_id':'first','content':BODY['messages'][0]['content']},
                        {'role':'tool','tool_call_id':'second','content':'plain result'}]}
    registry = GW.Registry()
    token = registry.issue_token('synthetic-session')
    with TestClient(Starlette(routes=GW.gateway_routes(registry, lambda:provider)),
                    base_url='http://127.0.0.1:8787', client=('127.0.0.1',50000)) as client:
        response = client.post(GW.CHAT_PATH, json=body, headers={'Authorization':'Bearer '+token})
        assert response.status_code == 200, response.text
    wire = captured[0]['messages']
    if kind == 'openai':
        assert [message['tool_call_id'] for message in wire if message['role']=='tool'] == ['first','second']
        assert wire[-2] == {'role':'tool','tool_call_id':'second','content':'plain result'}
        assert wire[-1]['role']=='user' and 'first' in wire[-1]['content'][0]['text']
        assert wire[-1]['content'][1:] == expected
    else:
        results = wire[-1]['content']
        assert [part['tool_use_id'] for part in results] == ['first','second']
        assert results[0]['content'] == expected
        assert results[1]['content'] == 'plain result'
    assert len(captured)==1


@pytest.mark.parametrize('vision,name', [(None,'unknown'), ('true','unknown'), (True,'chatgpt_plan'), (False,'openai')])
def test_unverified_selected_provider_strips_attachment_and_native_screenshot_images(vision,name):
    provider = RecordingProvider(vision)
    provider.name = name
    request = GW.to_request({'messages':BODY['messages']+[
        {'role':'tool','tool_call_id':'screenshot','content':BODY['messages'][0]['content']}]}, 'synthetic')
    GW._provider_images(request,provider)
    assert DATA not in str(request)
    assert request.messages[0].text() == 'Before image.'+GW.IMAGE_NOTE+'After image.'
    assert request.messages[1].content[0]['content'] == 'Before image.'+GW.IMAGE_NOTE+'After image.'


@pytest.mark.parametrize('url', ['data:image/png,abc','data:image/png;base64,!','data:image/png;base64,',
                                  'data:text/plain;base64,YQ==','file:///synthetic.png','http://['])
def test_malformed_images_refuse_before_a_provider_call(url):
    with pytest.raises(GW.BadRequest):
        GW.to_request({'messages':[{'role':'user','content':[{'type':'image_url','image_url':{'url':url}}]}]}, 'synthetic')


def test_model_metadata_advertises_only_explicit_supported_vision():
    for vision in [True,False,None,'true']:
        provider = RecordingProvider(vision)
        entry = GW.models_dev_registry(provider)['lampway']['models']['lampway']
        assert entry['attachment'] is (vision is True)
        assert ('image' in entry['modalities']['input']) is (vision is True)
    provider = RecordingProvider(True)
    provider.name = 'chatgpt_plan'
    assert GW.models_dev_registry(provider)['lampway']['models']['lampway']['attachment'] is False


@pytest.mark.parametrize('saved_model', ['claude-selected', 'older-model'])
def test_older_anthropic_settings_preserve_supported_default(saved_model):
    from types import SimpleNamespace
    from lampway_server.engine import wiring as W
    provider = SimpleNamespace(name='anthropic', model='claude-selected', supports_vision=True)
    saved = {'provider':'anthropic', 'model':saved_model}
    agent = SimpleNamespace(settings_store=SimpleNamespace(byok=lambda:saved))
    assert W.selected_vision(provider, agent) is True
    saved['supports_vision'] = False
    assert W.selected_vision(provider, agent) is (saved_model != provider.model)


def test_shared_provider_worker_and_summary_keep_pinned_vision_after_main_changes():
    from types import SimpleNamespace
    from lampway_server.engine import wiring as W
    # A valid factory may return the same service object: main selection must not mutate it.
    provider = RecordingProvider(None)
    provider.name = 'openai'
    provider.model = 'selected-model'
    provider.base_url = 'http://127.0.0.1:9/v1'
    saved = {'provider':'openai', 'model':provider.model, 'base_url':provider.base_url, 'supports_vision':True}
    resolution = SimpleNamespace(provider='openai', model='local', params={'model':provider.model, 'base_url':provider.base_url})
    agent = SimpleNamespace(provider=provider, settings_store=SimpleNamespace(byok=lambda:saved),
        swarm=SimpleNamespace(bindings=SimpleNamespace(choice_for=lambda key:resolution)),
        swarm_provider_factory=lambda label, resolution:provider)
    get = W.provider_getter(agent)
    sid = 'swarm:one:worker'
    assert get(sid) is provider
    summary = W._SummaryProvider(SimpleNamespace(), agent, resolution)
    assert get.vision_for(sid, provider) is True
    assert summary.supports_vision is True
    saved['supports_vision'] = False
    saved['model'] = 'different-main-model'
    assert get('main') is provider
    assert get.vision_for('main', provider) is False
    assert get(sid) is provider and get.vision_for(sid, provider) is True
    assert summary.supports_vision is True
    assert provider.supports_vision is None
    registry = GW.Registry()
    main_token = registry.issue_token('main')
    worker_token = registry.issue_token(sid)
    with TestClient(Starlette(routes=GW.gateway_routes(registry, get)),
                    base_url='http://127.0.0.1:8787', client=('127.0.0.1',50000)) as client:
        for token in [main_token, worker_token]:
            response = client.post(GW.CHAT_PATH, headers={'Authorization':'Bearer '+token}, json=BODY)
            assert response.status_code == 200, response.text
    main_parts, worker_parts = [request.messages[0].content for request in provider.requests]
    assert DATA not in str(main_parts) and GW.IMAGE_NOTE in str(main_parts)
    assert worker_parts == [{'type':'text','text':'Before image.'}, {'type':'image','source':SOURCE},
                            {'type':'text','text':'After image.'}]
    assert provider.supports_vision is None

@pytest.mark.parametrize('store_kind', ['credentials-only', 'unrelated-byok'])
def test_unknown_provider_does_not_read_unrelated_byok_settings(store_kind):
    from types import SimpleNamespace
    from lampway_server.engine import wiring as W
    def unrelated_byok():
        raise AssertionError('Unknown provider must not consult another service settings')
    store = SimpleNamespace(credentials_view=lambda: {'items': []})
    if store_kind == 'unrelated-byok':
        store.byok = unrelated_byok
    provider = SimpleNamespace(name='scripted-live')
    agent = SimpleNamespace(provider=provider, settings_store=store)
    assert W.selected_vision(provider, agent) is None
    request = GW.to_request(BODY, 'synthetic-session')
    GW._provider_images(request, provider, W.selected_vision(provider, agent))
    assert DATA not in str(request.messages[0].content)
    assert GW.IMAGE_NOTE in str(request.messages[0].content)
    assert GW.models_dev_registry(provider)['lampway']['models']['lampway']['attachment'] is False


def test_unknown_native_vision_remains_omitted_without_admitting_images(settings, tmp_path, monkeypatch):
    from types import SimpleNamespace
    from lampway_server.engine import wiring as W, hermes_config as HC
    from lampway_server import capabilities as CAP
    project = str(tmp_path / 'project')
    monkeypatch.setattr(CAP, 'ACTIVE', CAP.Store(settings.state_dir))
    agent = SimpleNamespace(provider=SimpleNamespace(),
        settings_store=SimpleNamespace(credentials_view=lambda: {'items': []}))
    wiring = W.EngineWiring({}, settings=settings, agent=agent, registry=GW.Registry())
    home = tmp_path / 'pane'
    wiring.write_config(home, 'http://127.0.0.1:8787/engine/v1', 'lwe_test', 'lampway', project=project)
    assert 'supports_vision' not in HC.read(home)['model']
