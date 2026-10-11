"""A turn must never end silently (live, 2026-10-05: eight run_blender_python calls on 0.5-1.6 MB candidate files, then the turn ended
IDLE with an EMPTY agent message and nothing in server.log, ~$1.03 spent). Mode 1 runs on Hermes (docs/reports/agent-modes-spec.md
A5), whose context, compression and stop reasons are its own (A0); what Lampway still owns is pinned here: an oversized tool result is
clipped before it reaches the pane's Hermes, and the OpenAI-compatible provider (a gateway door) reports the finish reason."""

import uuid

import pytest

from lampway_server.agent.providers.base import ModelRequest, Stop

from .serve_support import chat, final_text, run, stack  # noqa: F401  (stack: the fixture)

BIG = 1_600_000


@pytest.mark.timeout(120)
def test_an_oversized_tool_result_is_clipped_before_it_reaches_the_panes_hermes_so_the_turn_still_answers(stack):
    from lampway_server.agent.turns import MODEL_RESULT_CLIP

    async def scenario(serve, units, island, front):
        serve.scripts.append([("mcp", "run_blender_python", {"script": "x = 1"}), ("say", "Triaged: 3 deletes.")])
        command_id, _ = await chat(island, "triage the candidates", str(uuid.uuid4()))
        await island.ended(command_id)
        return serve.mcp_results, island.events(command_id)

    results, events = run(stack, scenario, on_script=lambda p: {"success": True, "output": "s" * BIG})
    text = results[-1]["content"][0]["text"]
    assert len(text) < MODEL_RESULT_CLIP + 500 and "clipped" in text, len(text)
    assert final_text(events) == "Triaged: 3 deletes."


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
