"""The chatgpt_plan provider: the Responses API route of ChatGPT plan usage, from the documented requirements
(preview-limitations): store:false, stream:true, full history in `input`, `instructions` for the system prompt, function
tools grouped in a namespace, none of the rejected fields; errors stop inference with their exact code, no fallback to
another billing path; image generation is not on this route."""

import asyncio
import json

import httpx
import pytest

from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall, ToolSpec
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanError, ChatGPTPlanProvider
from lampway_server import chatgpt_auth as CA

REJECTED = {"background", "conversation", "max_output_tokens", "max_tool_calls", "metadata", "moderation", "multi_agent", "prompt",
            "prompt_cache_retention", "safety_identifier", "temperature", "top_logprobs", "top_p", "truncation", "user",
            "previous_response_id"}


class FakeAuth:
    def __init__(self, token="tok-A", error=None):
        self.token, self.error = token, error

    async def access_token(self):
        if self.error:
            raise self.error
        return self.token


def sse(*events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events).encode()


def provider(handler, auth=None, **kw):
    return ChatGPTPlanProvider(auth or FakeAuth(), model="gpt-6.1-sol", transport=httpx.MockTransport(handler), **kw)


def collect(p, request):
    async def run():
        return [e async for e in p.stream(request)]
    return asyncio.run(run())


TOOLS = [ToolSpec("scene_summary", "List the scene.", {"type": "object", "properties": {}}),
         ToolSpec("run_blender_python", "Run Python.", {"type": "object", "properties": {"script": {"type": "string"}}, "required": ["script"]})]


def req(*messages, tools=TOOLS):
    return ModelRequest("SYSTEM PROMPT", list(messages), list(tools))


OK = sse({"type": "response.output_text.delta", "delta": "Hel"}, {"type": "response.output_text.delta", "delta": "lo"},
         {"type": "response.completed", "response": {"status": "completed"}})


def test_the_request_has_the_documented_shape_and_none_of_the_rejected_fields():
    seen = {}

    def handler(request):
        seen["url"], seen["headers"], seen["body"] = str(request.url), dict(request.headers), json.loads(request.content)
        return httpx.Response(200, content=OK, headers={"content-type": "text/event-stream"})

    collect(provider(handler), req(Message.user_text("hi")))
    b = seen["body"]
    assert seen["url"] == "https://api.openai.com/v1/responses" and seen["headers"]["authorization"] == "Bearer tok-A"
    assert b["store"] is False and b["stream"] is True and b["model"] == "gpt-6.1-sol" and b["instructions"] == "SYSTEM PROMPT"
    assert not (set(b) & REJECTED)
    assert b["input"] == [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "hi"}]}]
    assert not any(i.get("role") == "system" for i in b["input"])                       # explicit system items are rejected


def test_tools_are_function_tools_grouped_in_one_namespace_and_there_is_no_image_tool():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=OK)

    collect(provider(handler), req(Message.user_text("hi")))
    tools = seen["body"]["tools"]
    assert len(tools) == 1 and tools[0]["type"] == "namespace" and tools[0]["name"] == "lampway"
    inner = tools[0]["tools"]
    assert [t["name"] for t in inner] == ["scene_summary", "run_blender_python"] and all(t["type"] == "function" for t in inner)
    assert inner[1]["parameters"]["required"] == ["script"]
    flat = json.dumps(seen["body"])
    for unsupported in ("image_generation", "file_search", "code_interpreter", "computer", "tool_search", "mcp"):
        assert unsupported not in flat


def test_text_deltas_stream_and_completed_ends_the_stream():
    events = collect(provider(lambda r: httpx.Response(200, content=OK)), req(Message.user_text("hi")))
    assert events == [Text("Hel"), Text("lo")]


def test_a_function_call_becomes_a_tool_call_with_parsed_arguments():
    body = sse({"type": "response.output_item.done", "item": {"type": "function_call", "call_id": "call_1", "name": "run_blender_python",
                                                              "namespace": "lampway", "arguments": "{\"script\": \"print(1)\"}"}},
               {"type": "response.completed", "response": {"status": "completed"}})
    events = collect(provider(lambda r: httpx.Response(200, content=body)), req(Message.user_text("go")))
    assert events == [ToolCall(id="call_1", name="run_blender_python", arguments={"script": "print(1)"})]


def test_history_is_sent_back_as_function_call_and_function_call_output_items():
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, content=OK)

    history = [Message.user_text("go"),
               Message("assistant", [{"type": "text", "text": "Looking."}, {"type": "tool_call", "id": "call_1", "name": "scene_summary", "arguments": {}}]),
               Message("user", [{"type": "tool_result", "tool_call_id": "call_1", "content": "{\"objects\": 3}", "is_error": False}])]
    collect(provider(handler), req(*history))
    items = seen["body"]["input"]
    assert items[1] == {"type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "Looking."}]}
    assert items[2] == {"type": "function_call", "call_id": "call_1", "name": "scene_summary", "namespace": "lampway", "arguments": "{}"}
    assert items[3] == {"type": "function_call_output", "call_id": "call_1", "output": "{\"objects\": 3}"}


@pytest.mark.parametrize("code,needle", [
    ("subscription_sharing_usage_limit_exceeded", "chatgpt.com/settings/usage"),
    ("subscription_sharing_user_not_eligible", "not available"),
    ("subscription_sharing_usage_unavailable", "later"),
    ("subscription_sharing_unsupported_capability", "unsupported"),
    ("subscription_sharing_route_not_supported", "route"),
    ("subscription_sharing_invalid_user", "sign in again"),
])
def test_a_failed_response_stops_inference_with_its_exact_code_and_the_documented_recovery(code, needle):
    body = sse({"type": "response.output_text.delta", "delta": "x"},
               {"type": "response.failed", "response": {"error": {"code": code, "message": "m", "param": "p"}}})
    with pytest.raises(ChatGPTPlanError) as e:
        collect(provider(lambda r: httpx.Response(200, content=body)), req(Message.user_text("hi")))
    assert e.value.code == code and needle in str(e.value).lower() + str(e.value)


def test_a_failure_before_the_stream_keeps_the_status_and_the_detail_body():
    with pytest.raises(ChatGPTPlanError) as e:
        collect(provider(lambda r: httpx.Response(403, json={"detail": "region not permitted"})), req(Message.user_text("hi")))
    assert e.value.status == 403 and "region not permitted" in str(e.value)


def test_a_stream_that_ends_without_completed_is_an_error_not_a_success():
    body = sse({"type": "response.output_text.delta", "delta": "x"})
    with pytest.raises(ChatGPTPlanError, match="response.completed"):
        collect(provider(lambda r: httpx.Response(200, content=body)), req(Message.user_text("hi")))


def test_an_incomplete_response_is_reported_separately():
    body = sse({"type": "response.incomplete", "response": {"incomplete_details": {"reason": "max_output_tokens"}}})
    with pytest.raises(ChatGPTPlanError, match="incomplete"):
        collect(provider(lambda r: httpx.Response(200, content=body)), req(Message.user_text("hi")))


def test_not_signed_in_stops_before_any_request():
    calls = []
    p = provider(lambda r: calls.append(r) or httpx.Response(200, content=OK), auth=FakeAuth(error=CA.NotSignedIn("sign in")))
    with pytest.raises(CA.NotSignedIn):
        collect(p, req(Message.user_text("hi")))
    assert calls == []


def test_the_token_is_only_ever_in_the_authorization_header():
    seen = {}

    def handler(request):
        seen["url"], seen["body"] = str(request.url), request.content.decode()
        return httpx.Response(200, content=OK)

    collect(provider(handler, auth=FakeAuth("SECRET-TOKEN")), req(Message.user_text("hi")))
    assert "SECRET-TOKEN" not in seen["url"] and "SECRET-TOKEN" not in seen["body"]


def test_a_reasoning_effort_is_sent_as_reasoning_effort_and_absent_by_default():
    seen = []

    def handler(request):
        seen.append(json.loads(request.content))
        return httpx.Response(200, content=OK, headers={"content-type": "text/event-stream"})

    collect(provider(handler, effort="medium"), req(Message.user_text("hi")))
    collect(provider(handler), req(Message.user_text("hi")))
    assert seen[0]["reasoning"] == {"effort": "medium"} and "reasoning" not in seen[1]


def test_an_unknown_effort_is_refused_at_construction():
    with pytest.raises(ValueError):
        provider(lambda r: None, effort="max")


def test_the_swarm_on_chatgpt_plan_uses_its_own_model_and_effort(tmp_path):
    from lampway_server.config import Settings
    from lampway_server.agent.providers import make_provider, make_swarm_provider
    s = Settings.from_env({"LAMPWAY_STATE_DIR": str(tmp_path), "LAMPWAY_PROVIDER": "chatgpt_plan", "LAMPWAY_CHATGPT_MODEL": "gpt-6.1-sol",
                           "LAMPWAY_CHATGPT_EFFORT": "medium", "LAMPWAY_CHATGPT_SWARM_MODEL": "gpt-6.1-sol", "LAMPWAY_CHATGPT_SWARM_EFFORT": "low"})
    shared = FakeAuth()
    main, worker = make_provider(s, chatgpt_auth=shared), make_swarm_provider(s, "worker-1", chatgpt_auth=shared)
    assert main.auth is shared and worker.auth is shared          # one sign-in: rotating refresh tokens must never be refreshed twice
    assert isinstance(main, ChatGPTPlanProvider) and isinstance(worker, ChatGPTPlanProvider)
    assert (main.model, main.effort) == ("gpt-6.1-sol", "medium") and (worker.model, worker.effort) == ("gpt-6.1-sol", "low")
