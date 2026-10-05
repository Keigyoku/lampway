"""The real providers against fake transports: no network, no real LLM, no real key.

What matters is the translation of our neutral messages/tools to each wire format
and the events yielded back, so each test captures the request the provider sent."""

import json

import httpx
import httpx2
import pytest

from lampway_server.agent.providers.anthropic_provider import AnthropicProvider
from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall
from lampway_server.agent.providers.openai_compat import OpenAICompatProvider
from lampway_server.agent.tools import TOOLS

pytestmark = pytest.mark.anyio

HISTORY = [
    Message.user_text("Add a cube"),
    Message("assistant", [
        {"type": "text", "text": "Adding a cube."},
        {"type": "tool_call", "id": "call_1", "name": "run_blender_python", "arguments": {"script": "import bpy"}},
    ]),
    Message("user", [{"type": "tool_result", "tool_call_id": "call_1",
                      "content": '{"success": true, "created_objects": ["Cube"]}', "is_error": False}]),
]


def sse(events):
    return "".join(f"event: {e['type']}\ndata: {json.dumps(e)}\n\n" for e in events)


ANTHROPIC_STREAM = sse([
    {"type": "message_start", "message": {"id": "msg_1", "type": "message", "role": "assistant",
                                          "model": "claude-sonnet-5-5", "content": [], "stop_reason": None,
                                          "stop_sequence": None,
                                          "usage": {"input_tokens": 10, "output_tokens": 1}}},
    {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "Adding "}},
    {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "a cube."}},
    {"type": "content_block_stop", "index": 0},
    {"type": "content_block_start", "index": 1,
     "content_block": {"type": "tool_use", "id": "toolu_1", "name": "run_blender_python", "input": {}}},
    {"type": "content_block_delta", "index": 1,
     "delta": {"type": "input_json_delta", "partial_json": '{"script": "import bpy\\nbpy.ops.mesh.primitive_cube_add()"}'}},
    {"type": "content_block_stop", "index": 1},
    {"type": "message_delta", "delta": {"stop_reason": "tool_use", "stop_sequence": None},
     "usage": {"output_tokens": 20}},
    {"type": "message_stop"},
])


async def test_anthropic_provider_translates_the_request_and_streams_text_then_tool_calls(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    captured = {}

    def handler(request):
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx2.Response(200, headers={"content-type": "text/event-stream"}, content=ANTHROPIC_STREAM.encode())

    provider = AnthropicProvider(model="claude-sonnet-5-5", transport=httpx2.MockTransport(handler))
    request = ModelRequest("You are Lampway.", HISTORY, list(TOOLS))
    events = [e async for e in provider.stream(request)]

    body = captured["body"]
    assert body["model"] == "claude-sonnet-5-5"
    assert body["stream"] is True
    assert body["system"] == "You are Lampway." or body["system"][0]["text"] == "You are Lampway."
    names = [t["name"] for t in body["tools"]]
    assert names[:2] == ["run_blender_python", "scene_summary"] and "lampway_qa_candidates" in names
    assert body["tools"][0]["input_schema"]["required"] == ["script"]
    assert body["messages"][0] == {"role": "user", "content": [{"type": "text", "text": "Add a cube"}]}
    assert body["messages"][1]["role"] == "assistant"
    assert body["messages"][1]["content"][1] == {"type": "tool_use", "id": "call_1", "name": "run_blender_python",
                                                 "input": {"script": "import bpy"}}
    assert body["messages"][2]["content"][0]["type"] == "tool_result"
    assert body["messages"][2]["content"][0]["tool_use_id"] == "call_1"
    assert "tool_choice" not in body  # forced tool use is a 400 on Sonnet 5.5
    assert captured["headers"]["x-api-key"] == "sk-ant-test-not-real"

    assert events == [Text("Adding "), Text("a cube."),
                      ToolCall(id="toolu_1", name="run_blender_python",
                               arguments={"script": "import bpy\nbpy.ops.mesh.primitive_cube_add()"})]


def openai_chunks(chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" for c in chunks) + "data: [DONE]\n\n"


OPENAI_STREAM = openai_chunks([
    {"id": "c1", "object": "chat.completion.chunk", "choices": [
        {"index": 0, "delta": {"role": "assistant", "content": "Adding "}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"content": "a cube."}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "id": "call_9", "type": "function",
         "function": {"name": "run_blender_python", "arguments": '{"scr'}}]}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {"tool_calls": [
        {"index": 0, "function": {"arguments": 'ipt": "import bpy"}'}}]}, "finish_reason": None}]},
    {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}]},
])


async def test_openai_compatible_provider_translates_the_request_and_streams_text_then_tool_calls():
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=OPENAI_STREAM.encode())

    provider = OpenAICompatProvider(base_url="http://127.0.0.1:11434/v1", model="qwen3",
                                    api_key="sk-local-test", transport=httpx.MockTransport(handler))
    request = ModelRequest("You are Lampway.", HISTORY, list(TOOLS))
    events = [e async for e in provider.stream(request)]

    assert captured["url"] == "http://127.0.0.1:11434/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer sk-local-test"
    body = captured["body"]
    assert body["model"] == "qwen3" and body["stream"] is True
    assert body["messages"][0] == {"role": "system", "content": "You are Lampway."}
    assert body["messages"][1] == {"role": "user", "content": "Add a cube"}
    assistant = body["messages"][2]
    assert assistant["role"] == "assistant" and assistant["content"] == "Adding a cube."
    assert assistant["tool_calls"] == [{"id": "call_1", "type": "function", "function": {
        "name": "run_blender_python", "arguments": json.dumps({"script": "import bpy"})}}]
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "call_1",
                                   "content": '{"success": true, "created_objects": ["Cube"]}'}
    assert [t["function"]["name"] for t in body["tools"]][:2] == ["run_blender_python", "scene_summary"]
    assert body["tools"][0]["type"] == "function"

    assert events == [Text("Adding "), Text("a cube."),
                      ToolCall(id="call_9", name="run_blender_python", arguments={"script": "import bpy"})]


async def test_openai_compatible_provider_without_a_key_sends_no_authorization_header():
    captured = {}

    def handler(request):
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              content=openai_chunks([{"choices": [{"index": 0, "delta": {"content": "hi"},
                                                                   "finish_reason": "stop"}]}]).encode())

    provider = OpenAICompatProvider(base_url="http://127.0.0.1:8080/v1", model="m", api_key="",
                                    transport=httpx.MockTransport(handler))
    events = [e async for e in provider.stream(ModelRequest("s", [Message.user_text("x")], []))]
    assert "authorization" not in captured["headers"]
    assert events == [Text("hi")]


def test_make_provider_builds_the_configured_provider(settings, monkeypatch):
    from lampway_server.agent.providers import make_provider

    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-not-real")
    settings.provider = "anthropic"
    anthropic = make_provider(settings)
    assert isinstance(anthropic, AnthropicProvider) and anthropic.model == "claude-sonnet-5-5"

    monkeypatch.setenv("OPENAI_API_KEY", "sk-local")
    settings.provider = "openai"
    settings.openai_model = "qwen3"
    settings.openai_base_url = "http://127.0.0.1:1234/v1"
    openai = make_provider(settings)
    assert isinstance(openai, OpenAICompatProvider) and openai.model == "qwen3"
    assert openai.base_url == "http://127.0.0.1:1234/v1"


def test_an_openai_compatible_error_body_that_echoes_the_key_is_redacted(anyio_backend):
    """Redaction covered OpenRouter only. Any OpenAI-compatible server (BYOK, a local runtime) can echo the Authorization
    value in an error body; the configured key must never reach the message the model, the log or the person sees."""
    import asyncio
    import httpx
    from lampway_server.agent.providers.openai_compat import OpenAICompatProvider
    from lampway_server.agent.providers.base import Message, ModelRequest

    key = "sk-test-" + "k" * 40

    def handler(request):
        return httpx.Response(401, json={"error": {"message": f"bad token {key} for Bearer {key}"}})

    provider = OpenAICompatProvider("http://unit.test/v1", "m", api_key=key, transport=httpx.MockTransport(handler))

    async def run():
        with pytest.raises(RuntimeError) as exc:
            async for _ in provider.stream(ModelRequest("s", [Message.user_text("hi")], [])):
                pass
        return str(exc.value)

    message = asyncio.run(run())
    assert key not in message and "401" in message and "[redacted]" in message
