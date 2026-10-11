# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's model gateway (docs/reports/agent-modes-spec.md E1.4): an OpenAI-compatible endpoint on the existing server, for the
engine child only. Scripted providers and Starlette's TestClient; no network, no model."""
import json
from types import SimpleNamespace

import httpx
import pytest
from starlette.testclient import TestClient

from lampway_server import egress as E
from lampway_server import logredact
from lampway_server.agent.providers.base import Stop, Text, ToolCall
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanError, _RECOVERY
from lampway_server.agent.providers.openai_compat import OpenAICompatProvider
from lampway_server.app import create_app
from lampway_server.engine import gateway as GW

BASE = "http://127.0.0.1:8787"
CHAT = "/engine/v1/chat/completions"
LIMIT = "subscription_sharing_usage_limit_exceeded"


def client_for(app, host="127.0.0.1"):
    return TestClient(app, base_url=BASE, client=(host, 50000))


@pytest.fixture
def gw(settings, provider):
    app = create_app(settings, provider=provider)
    with client_for(app) as c:
        token = app.state.engine_tokens.issue_token("sess-1")
        yield SimpleNamespace(c=c, app=app, token=token, provider=provider, h={"Authorization": f"Bearer {token}"})


def ask(gw, body, **kw):
    return gw.c.post(CHAT, json=body, headers=gw.h, **kw)


def sse(text: str) -> list:
    out = []
    for block in text.split("\n\n"):
        block = block.strip()
        if block.startswith("data:"):
            data = block[5:].strip()
            out.append(data if data == "[DONE]" else json.loads(data))
    return out


TOOL = {"type": "function", "function": {"name": "scene_summary", "description": "Summarise the scene.",
                                         "parameters": {"type": "object", "properties": {"detail": {"type": "string"}}}}}


# ------------------------------------------------------------------------------------------------ the token registry
def test_a_token_is_random_per_issue_and_the_registry_holds_no_raw_value_in_its_repr():
    reg = GW.Registry()
    a, b = reg.issue_token("s1"), reg.issue_token("s1")
    assert a != b and a.startswith("lwe_") and len(a) >= 40
    assert reg.session_for(a) == "s1" and reg.session_for("nope") is None
    assert a not in repr(reg) and a not in str(vars(reg))
    assert reg.revoke(a) is True and reg.revoke(a) is False and reg.session_for(a) is None
    assert reg.session_for(b) == "s1"
    reg.revoke_session("s1")
    assert reg.session_for(b) is None


def test_the_app_registry_is_the_active_one(gw):
    assert gw.app.state.engine_tokens is GW.ACTIVE
    assert GW.issue_token("other").startswith("lwe_")


# ------------------------------------------------------------------------------------------------ authentication
def test_a_request_without_a_token_is_401_in_the_openai_error_shape_and_the_provider_is_not_called(gw):
    r = gw.c.post(CHAT, json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 401
    err = r.json()["error"]
    assert err["code"] == "invalid_api_key" and err["message"] and "type" in err
    assert gw.provider.requests == []


def test_an_unknown_a_revoked_and_a_lampway_login_token_are_all_401(gw):
    body = {"messages": [{"role": "user", "content": "hi"}]}
    assert gw.c.post(CHAT, json=body, headers={"Authorization": "Bearer lwe_notissued"}).status_code == 401
    login = gw.app.state.auth.issue_pair()["access_token"]                       # the user's own session is not the engine's key
    assert gw.c.post(CHAT, json=body, headers={"Authorization": f"Bearer {login}"}).status_code == 401
    gw.app.state.engine_tokens.revoke(gw.token)
    assert ask(gw, body).status_code == 401
    assert gw.provider.requests == []


@pytest.mark.parametrize("host", ["203.0.113.9", "192.168.1.20", "testclient", "::ffff:10.0.0.1"])
def test_a_client_that_is_not_loopback_is_403_even_with_a_valid_token(gw, host):
    with client_for(gw.app, host) as other:
        r = other.post(CHAT, json={"messages": [{"role": "user", "content": "hi"}]}, headers=gw.h)
        assert r.status_code == 403
        assert other.get("/engine/v1/models", headers=gw.h).status_code == 403
    assert gw.provider.requests == []


@pytest.mark.parametrize("host", ["127.0.0.1", "::1", "::ffff:127.0.0.1"])
def test_loopback_clients_are_served(gw, host):
    with client_for(gw.app, host) as other:
        assert other.get("/engine/v1/models", headers=gw.h).status_code == 200


# ------------------------------------------------------------------------------------------------ models
def test_models_lists_the_current_providers_model_and_follows_a_choice_that_swaps_it(gw):
    r = gw.c.get("/engine/v1/models", headers=gw.h)
    data = r.json()
    assert r.status_code == 200 and data["object"] == "list" and [m["id"] for m in data["data"]] == ["scripted"]
    gw.app.state.agent.provider = SimpleNamespace(name="openai", model="gpt-test", stream=gw.provider.stream)
    assert [m["id"] for m in gw.c.get("/engine/v1/models", headers=gw.h).json()["data"]] == ["gpt-test"]


def test_the_models_call_the_engine_makes_at_the_origin_is_answered_too_and_401_without_the_token(gw):
    """Measured with the pinned Hermes: it asks GET /api/v1/models at the origin of its base_url, once without any Authorization."""
    assert gw.c.get("/api/v1/models").status_code == 401
    assert gw.c.get("/api/v1/models", headers={"Authorization": "Bearer lwe_nope"}).status_code == 401
    ok = gw.c.get("/api/v1/models", headers=gw.h)
    assert ok.status_code == 200 and ok.json()["data"][0]["id"] == "scripted"
    assert gw.c.get("/engine/v1/models").status_code == 401


def test_the_ollama_probe_at_the_origin_is_answered_harmlessly_and_never_reaches_the_provider(gw):
    """Measured on the pinned ``hermes serve`` (spec A1): a custom endpoint also receives ``POST /api/show`` at the origin of its
    base_url, an Ollama model probe, with or without the key. The gateway answers it itself: an OpenAI-style 404 that names no
    model, so Hermes falls back to its own defaults. Loopback only, like every gateway route."""
    for headers in ({}, gw.h):
        r = gw.c.post("/api/show", json={"model": "lampway"}, headers=headers)
        assert r.status_code == 404 and r.json()["error"]["code"] == "not_ollama", r.text
    with client_for(gw.app, "203.0.113.9") as other:
        assert other.post("/api/show", json={"model": "lampway"}).status_code == 403
    assert gw.provider.requests == []


def test_a_panes_token_is_adopted_again_after_a_restart_by_its_digest_only():
    """Spec A1 (persistence): a Mode 1 pane outlives the server, and its config still holds the token it was given. The restarted
    server adopts that token again from the digest it kept in the unit's own record (never the token), so the pane thinks on."""
    first = GW.Registry()
    token = first.issue_token("unit-1")
    digest = GW.Registry.digest(token)
    assert token not in digest and len(digest) == 64
    again = GW.Registry()
    assert again.session_for(token) is None
    again.adopt_digest("unit-1", digest)
    assert again.session_for(token) == "unit-1" and token not in repr(again)
    again.revoke_session("unit-1")
    assert again.session_for(token) is None


def test_a_provider_that_knows_its_context_window_says_so(gw):
    gw.app.state.agent.provider = SimpleNamespace(name="x", model="m", context_length=131072, stream=gw.provider.stream)
    assert gw.c.get("/engine/v1/models", headers=gw.h).json()["data"][0]["context_length"] == 131072


# ------------------------------------------------------------------------------------------------ a round trip with a tool call
def test_one_round_trip_with_a_tool_call_and_its_result(gw):
    gw.provider.script = [[Text("Looking."), ToolCall("call_1", "scene_summary", {"detail": "full"})], [Text("The scene has a cube.")]]
    first = ask(gw, {"model": "whatever", "tools": [TOOL],
                     "messages": [{"role": "system", "content": "You are the engine."}, {"role": "user", "content": "what is in the scene?"}]})
    assert first.status_code == 200
    body = first.json()
    assert body["object"] == "chat.completion" and body["model"]
    choice = body["choices"][0]
    assert choice["finish_reason"] == "tool_calls" and choice["message"]["role"] == "assistant" and choice["message"]["content"] == "Looking."
    call = choice["message"]["tool_calls"][0]
    assert call["id"] == "call_1" and call["type"] == "function" and call["function"]["name"] == "scene_summary"
    assert json.loads(call["function"]["arguments"]) == {"detail": "full"}

    req = gw.provider.requests[0]
    assert req.system == "You are the engine." and req.session_id == "sess-1"
    assert [(m.role, m.text()) for m in req.messages] == [("user", "what is in the scene?")]
    assert [(t.name, t.description) for t in req.tools] == [("scene_summary", "Summarise the scene.")]
    assert req.tools[0].parameters["properties"]["detail"] == {"type": "string"}

    second = ask(gw, {"tools": [TOOL], "messages": [
        {"role": "system", "content": "You are the engine."}, {"role": "user", "content": "what is in the scene?"},
        {"role": "assistant", "content": "Looking.", "tool_calls": [call]},
        {"role": "tool", "tool_call_id": "call_1", "content": "a cube"}]})
    assert second.json()["choices"][0]["message"]["content"] == "The scene has a cube." and second.json()["choices"][0]["finish_reason"] == "stop"
    msgs = gw.provider.requests[1].messages
    assert [m.role for m in msgs] == ["user", "assistant", "user"]
    assert msgs[1].content == [{"type": "text", "text": "Looking."},
                               {"type": "tool_call", "id": "call_1", "name": "scene_summary", "arguments": {"detail": "full"}}]
    assert msgs[2].content == [{"type": "tool_result", "tool_call_id": "call_1", "content": "a cube", "is_error": False}]


def test_several_tool_results_after_one_assistant_message_become_one_results_message_in_order(gw):
    calls = [{"id": f"c{i}", "type": "function", "function": {"name": "scene_summary", "arguments": "{}"}} for i in (1, 2)]
    ask(gw, {"messages": [{"role": "user", "content": "go"}, {"role": "assistant", "content": None, "tool_calls": calls},
                          {"role": "tool", "tool_call_id": "c1", "content": "one"},
                          {"role": "tool", "tool_call_id": "c2", "content": [{"type": "text", "text": "two"}]}]})
    msgs = gw.provider.requests[0].messages
    assert [m.role for m in msgs] == ["user", "assistant", "user"]
    assert [(p["tool_call_id"], p["content"]) for p in msgs[2].content] == [("c1", "one"), ("c2", "two")]
    assert msgs[1].content == [{"type": "tool_call", "id": "c1", "name": "scene_summary", "arguments": {}},
                               {"type": "tool_call", "id": "c2", "name": "scene_summary", "arguments": {}}]


def test_the_auxiliary_call_with_no_stream_key_and_an_empty_tools_list_is_served(gw):
    gw.provider.script = [[Text("A title")]]
    r = ask(gw, {"tools": [], "messages": [{"role": "user", "content": "title this"}]})
    assert r.status_code == 200 and r.json()["choices"][0]["message"]["content"] == "A title"
    assert gw.provider.requests[0].tools == []


def test_invalid_tool_arguments_and_content_parts_and_developer_messages_are_translated(gw):
    ask(gw, {"messages": [{"role": "developer", "content": "be brief"}, {"role": "system", "content": [{"type": "text", "text": "and kind"}]},
                          {"role": "user", "content": [{"type": "text", "text": "a"}, {"type": "text", "text": "b"}]},
                          {"role": "assistant", "content": "", "tool_calls": [{"id": "x", "type": "function", "function": {"name": "t", "arguments": "{not json"}}]},
                          {"role": "tool", "tool_call_id": "x", "content": "err"}]})
    req = gw.provider.requests[0]
    assert req.system == "be brief\n\nand kind"
    assert req.messages[0].text() == "ab"
    assert req.messages[1].content == [{"type": "tool_call", "id": "x", "name": "t", "arguments": {"__invalid_json__": "{not json"}}]


@pytest.mark.parametrize("stop,finish", [("length", "length"), ("max_tokens", "length"), ("content_filter", "content_filter"), ("weird", "stop")])
def test_an_abnormal_stop_becomes_the_matching_finish_reason(gw, stop, finish):
    gw.provider.script = [[Text("cut"), Stop(stop)]]
    assert ask(gw, {"messages": [{"role": "user", "content": "x"}]}).json()["choices"][0]["finish_reason"] == finish


# ------------------------------------------------------------------------------------------------ streaming
def test_a_stream_carries_text_deltas_then_the_tool_call_with_its_id_then_the_finish_reason_and_done(gw):
    gw.provider.script = [[Text("Hel"), Text("lo"), ToolCall("call_9", "scene_summary", {"detail": "x"}), ToolCall("call_10", "scene_summary", {})]]
    r = ask(gw, {"stream": True, "tools": [TOOL], "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/event-stream")
    events = sse(r.text)
    assert events[-1] == "[DONE]"
    chunks = events[:-1]
    assert {c["object"] for c in chunks} == {"chat.completion.chunk"} and len({c["id"] for c in chunks}) == 1
    assert chunks[0]["choices"][0]["delta"].get("role") == "assistant"
    assert "".join(c["choices"][0]["delta"].get("content") or "" for c in chunks) == "Hello"
    tcs = [tc for c in chunks for tc in c["choices"][0]["delta"].get("tool_calls") or []]
    assert [(t["index"], t["id"], t["type"], t["function"]["name"]) for t in tcs] == [
        (0, "call_9", "function", "scene_summary"), (1, "call_10", "function", "scene_summary")]
    assert json.loads(tcs[0]["function"]["arguments"]) == {"detail": "x"}
    finishes = [c["choices"][0]["finish_reason"] for c in chunks if c["choices"][0].get("finish_reason")]
    assert finishes == ["tool_calls"] and chunks[-1]["choices"][0]["finish_reason"] == "tool_calls"


def test_a_text_only_stream_finishes_with_stop_and_a_cut_off_one_with_length(gw):
    gw.provider.script = [[Text("done")], [Text("cu"), Stop("length")]]
    a = sse(ask(gw, {"stream": True, "messages": [{"role": "user", "content": "x"}]}).text)
    b = sse(ask(gw, {"stream": True, "messages": [{"role": "user", "content": "x"}]}).text)
    assert a[-2]["choices"][0]["finish_reason"] == "stop" and b[-2]["choices"][0]["finish_reason"] == "length"


# ------------------------------------------------------------------------------------------------ errors
class Raising:
    name = "raising"

    def __init__(self, exc, before=()):
        self.exc, self.before, self.calls = exc, before, 0

    async def stream(self, request):
        self.calls += 1
        for e in self.before:
            yield e
        raise self.exc


def test_the_usage_limit_recovery_text_reaches_the_engine_in_an_openai_error_and_nothing_is_retried(gw):
    bad = Raising(ChatGPTPlanError(_RECOVERY[LIMIT], code=LIMIT))
    gw.app.state.agent.provider = bad
    for stream in (False, True):                                   # before any event the HTTP status carries it, in both modes
        r = ask(gw, {"stream": stream, "messages": [{"role": "user", "content": "x"}]})
        assert r.status_code == 429 and r.headers["content-type"].startswith("application/json")
        err = r.json()["error"]
        assert "usage limit" in err["message"] and "chatgpt.com/settings/usage" in err["message"] and err["code"] == LIMIT
    assert bad.calls == 2                                           # one call per request: never again, never on another provider
    assert gw.provider.requests == []                               # the configured fallback (the scripted one) was never asked


@pytest.mark.parametrize("exc,status,code", [
    (E.EgressRefused("custom_llm is off: switch it on in Privacy to let data leave"), 403, "egress_refused"),
    (RuntimeError("the model server fell over"), 502, "provider_error"),
    (httpx.ConnectError("refused"), 502, "provider_error"),
])
def test_other_provider_failures_map_to_a_status_and_a_code(gw, exc, status, code):
    gw.app.state.agent.provider = Raising(exc)
    r = ask(gw, {"messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == status and r.json()["error"]["code"] == code and r.json()["error"]["message"]


def test_a_secret_in_a_provider_error_is_redacted(gw):
    gw.app.state.agent.provider = Raising(RuntimeError("bad key sk-abcdefghijklmnopqrstuvwx0123 and Bearer abcdefgh12345678"))
    text = ask(gw, {"messages": [{"role": "user", "content": "x"}]}).text
    assert "sk-abcdefgh" not in text and "[redacted]" in text


def test_an_error_after_the_stream_began_is_an_error_event_with_no_finish_chunk(gw):
    gw.app.state.agent.provider = Raising(ChatGPTPlanError(_RECOVERY[LIMIT], code=LIMIT), before=[Text("part")])
    r = ask(gw, {"stream": True, "messages": [{"role": "user", "content": "x"}]})
    assert r.status_code == 200
    events = sse(r.text)
    assert events[-1] == "[DONE]" and "usage limit" in events[-2]["error"]["message"] and events[-2]["error"]["code"] == LIMIT
    assert not any(c["choices"][0].get("finish_reason") for c in events[:-2])
    assert "".join(c["choices"][0]["delta"].get("content") or "" for c in events[:-2]) == "part"


@pytest.mark.parametrize("body", [
    "not json", {"messages": "x"}, {}, {"messages": [{"role": "user", "content": "x"}], "n": 2},
    {"messages": [{"role": "user", "content": "x"}], "tools": [{"type": "web_search"}]},
    {"messages": [{"role": "tool", "content": "orphan"}]}, {"messages": [{"role": "wizard", "content": "x"}]},
])
def test_a_malformed_request_is_400_and_never_reaches_the_provider(gw, body):
    r = gw.c.post(CHAT, content=body if isinstance(body, str) else json.dumps(body), headers={**gw.h, "content-type": "application/json"})
    assert r.status_code == 400 and r.json()["error"]["message"]
    assert gw.provider.requests == []


# ------------------------------------------------------------------------------------------------ Lampway's own gates apply
def test_the_current_main_provider_goes_through_the_egress_choke_point(gw, tmp_path):
    seen = []

    def handler(request):
        seen.append(request)
        body = 'data: {"choices":[{"delta":{"content":"hi"},"finish_reason":"stop"}]}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body, headers={"content-type": "text/event-stream"})

    mgr = E.Egress(tmp_path / "strict")
    E.set_active(mgr)
    mgr.register_host("custom_llm", "llm.example")
    gw.app.state.agent.provider = OpenAICompatProvider("https://llm.example/v1", "m", "key-1234567890", transport=httpx.MockTransport(handler))
    body = {"messages": [{"role": "user", "content": "x"}]}
    off = ask(gw, body)
    assert off.status_code == 403 and off.json()["error"]["code"] == "egress_refused" and seen == []
    assert mgr.log()[-1]["event"] == "refused" and mgr.log()[-1]["route"] == "custom_llm"
    mgr.set_route("custom_llm", True)
    on = ask(gw, body)
    assert on.status_code == 200 and on.json()["choices"][0]["message"]["content"] == "hi" and len(seen) == 1
    assert mgr.log()[-1]["event"] == "send" and mgr.log()[-1]["provider"] == "llm.example"


def test_observers_hear_of_each_request_before_the_model_is_called(gw):
    heard = []
    gw.app.state.engine_tokens.observers.append(lambda session_id, provider: heard.append((session_id, provider, len(gw.provider.requests))))
    ask(gw, {"messages": [{"role": "user", "content": "x"}]})
    assert heard == [("sess-1", "scripted", 0)]


# ------------------------------------------------------------------------------------------------ secrets
def test_a_token_is_redacted_from_log_text_and_never_in_a_log_record_the_gateway_writes(gw, caplog):
    import logging
    logredact.install()
    assert gw.token not in logredact.redact_text(f"GET /x Authorization: Bearer {gw.token} {gw.token}")
    with caplog.at_level(logging.DEBUG):
        ask(gw, {"messages": [{"role": "user", "content": "x"}]})
        gw.c.post(CHAT, json={}, headers={"Authorization": f"Bearer {gw.token}x"})
        gw.app.state.agent.provider = Raising(RuntimeError(f"failed for {gw.token}"))
        ask(gw, {"messages": [{"role": "user", "content": "x"}]})
    assert gw.token not in caplog.text
    assert gw.token not in ask(gw, {"messages": [{"role": "user", "content": "x"}]}).text
