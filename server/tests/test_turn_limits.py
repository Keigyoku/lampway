"""A turn must never end silently (live, 2026-10-05: eight run_blender_python calls on 0.5-1.6 MB candidate files, then the turn ended
IDLE with an EMPTY agent message and nothing in server.log, ~$1.03 spent). Two causes are pinned here: an oversized tool result
reaching the model, and a model reply that is empty (the provider's stop reason being the only clue)."""

import json
import uuid

import pytest
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import ModelRequest, Stop, Text, ToolCall
from lampway_server.app import create_app

from .fake_client import FakeMixarClient

BIG = 1_600_000
CONTEXT_LIMIT_CHARS = 300_000


class LimitedProvider:
    """A model that, like the live one, answers with NOTHING (and a 'length' stop) when the request is past its context limit."""
    name = "limited"

    def __init__(self, plan):
        self.plan = list(plan)
        self.sizes = []

    async def stream(self, request: ModelRequest):
        size = len(request.system) + sum(len(json.dumps(m.content, default=str)) for m in request.messages)
        self.sizes.append(size)
        if size > CONTEXT_LIMIT_CHARS:
            yield Stop("length")
            return
        for event in self.plan.pop(0):
            yield event


def run(settings, provider, on_script):
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            command_id = fake.command(ws, "chat", fake.chat_payload("triage the candidates", str(uuid.uuid4())))
            return fake.run_turn(ws, command_id, on_script=on_script)


def content_of(frames):
    out = [f["params"]["event"]["content"]["set"] for f in frames
           if f.get("method") == "agent.turn.event" and (f["params"]["event"].get("content") or {}).get("set")]
    return out[-1] if out else ""


def test_an_oversized_tool_result_is_clipped_before_it_reaches_the_model_so_the_turn_still_answers(settings):
    provider = LimitedProvider([
        [ToolCall(id="c1", name="run_blender_python", arguments={"script": "x = 1"})],
        [Text("Triaged: 3 deletes.")]])
    frames = run(settings, provider, lambda p: {"success": True, "output": "s" * BIG})
    assert content_of(frames) == "Triaged: 3 deletes.", "the 1.6 MB result blew the context and the turn ended empty"
    assert max(provider.sizes) < CONTEXT_LIMIT_CHARS


def test_a_turn_that_ends_on_an_empty_reply_says_why_with_the_stop_reason(settings):
    class Empty:
        name = "empty"

        async def stream(self, request):
            yield Stop("length")
    frames = run(settings, Empty(), lambda p: {"success": True})
    text = content_of(frames)
    assert text, "an empty final message is a silent turn"
    assert "length" in text and "output" in text.lower()


def test_an_empty_reply_after_tool_calls_names_how_many_and_is_logged(settings, caplog):
    provider = LimitedProvider([[ToolCall(id="c1", name="run_blender_python", arguments={"script": "x = 1"})]])

    class Then:
        name = "then"
        calls = 0

        async def stream(self, request):
            Then.calls += 1
            if Then.calls == 1:
                yield ToolCall(id="c1", name="run_blender_python", arguments={"script": "x = 1"})
            else:
                return
                yield
    with caplog.at_level("WARNING", logger="lampway.agent"):
        frames = run(settings, Then(), lambda p: {"success": True})
    text = content_of(frames)
    assert "1 tool call" in text and "empty reply" in text
    assert any("empty reply" in r.getMessage() for r in caplog.records)


def test_the_tool_round_cap_is_reported_with_its_number(settings):
    class Loop:
        name = "loop"

        async def stream(self, request):
            yield ToolCall(id=f"c{len(request.messages)}", name="scene_summary", arguments={})
    frames = run(settings, Loop(), lambda p: {"success": True, "object_count": 0})
    assert "64" in content_of(frames) and "tool" in content_of(frames)


def test_old_tool_results_are_dropped_from_the_context_when_the_history_outgrows_the_budget(settings):
    big = "r" * 120_000
    provider = LimitedProvider([
        [ToolCall(id=f"c{i}", name="run_blender_python", arguments={"script": "x"})] for i in range(1, 15)] + [[Text("done")]])
    frames = run(settings, provider, lambda p: {"success": True, "output": big})
    assert content_of(frames) == "done" and max(provider.sizes) < CONTEXT_LIMIT_CHARS


def test_the_openai_compatible_provider_reports_the_finish_reason_as_a_stop_event():
    import asyncio
    import httpx
    from lampway_server.agent.providers.openai_compat import OpenAICompatProvider

    sse = ('data: {"choices":[{"delta":{"content":""},"finish_reason":null}]}\n\n'
           'data: {"choices":[{"delta":{},"finish_reason":"length"}]}\n\ndata: [DONE]\n\n')
    transport = httpx.MockTransport(lambda req: httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"}))
    provider = OpenAICompatProvider("http://x", "m", transport=transport)

    async def collect():
        return [e async for e in provider.stream(ModelRequest("s", [], []))]
    assert asyncio.run(collect()) == [Stop("length")]
