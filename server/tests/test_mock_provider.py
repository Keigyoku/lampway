"""The mock provider (LAMPWAY_PROVIDER=mock) is how the real client is driven with no model. Behind the gateway it answers Lampway
Agent's Hermes (spec A5): it looks at the scene with Lampway's ``scene_summary`` under the name Hermes offers it (``mcp__lampway__``,
or through Hermes's ``tool_call`` bridge when the tool is deferred), and a user message beginning ``py:`` runs the rest as a Blender
script, so a live run can change the scene. It never calls a tool Hermes did not offer, and a request with no tools (Hermes's title
or summary call) gets text only."""

import asyncio

from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall, ToolSpec
from lampway_server.agent.providers.mock import MockProvider

SCHEMA = {"type": "object", "properties": {}}
#: What Hermes sends with Lampway's tools visible (measured shapes: the MCP prefix, its own tools beside them)
VISIBLE = [ToolSpec("mcp__lampway__scene_summary", "List the scene.", SCHEMA), ToolSpec("mcp__lampway__run_blender_python", "Run.", SCHEMA),
           ToolSpec("clarify", "Ask.", SCHEMA), ToolSpec("vision_analyze", "Look.", SCHEMA)]
#: ...and with them deferred behind tool_search: only the bridge is visible
BRIDGE = [ToolSpec("tool_search", "Deferred tool catalog ...", SCHEMA), ToolSpec("tool_describe", "Describe.", SCHEMA),
          ToolSpec("tool_call", "Call deferred tools.", SCHEMA), ToolSpec("clarify", "Ask.", SCHEMA)]


def _collect(provider, messages, tools):
    async def run():
        return [e async for e in provider.stream(ModelRequest(system="", messages=messages, tools=list(tools)))]
    return asyncio.run(run())


def test_a_py_message_becomes_a_run_blender_python_call():
    events = _collect(MockProvider(), [Message.user_text("py: import bpy\nbpy.ops.mesh.primitive_cube_add()")], VISIBLE)
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert [(c.name, c.arguments) for c in calls] == [
        ("mcp__lampway__run_blender_python", {"script": "import bpy\nbpy.ops.mesh.primitive_cube_add()"})]


def test_the_result_of_a_py_call_is_reported_back():
    messages = [
        Message.user_text("py: result = 1"),
        Message("assistant", [{"type": "tool_call", "id": "c1", "name": "mcp__lampway__run_blender_python",
                               "arguments": {"script": "result = 1"}}]),
        Message("user", [{"type": "tool_result", "tool_call_id": "c1", "content": '{"success": true}', "is_error": False}]),
    ]
    text = "".join(e.text for e in _collect(MockProvider(), messages, VISIBLE) if isinstance(e, Text))
    assert "Ran your script" in text and '"success": true' in text


def test_other_messages_still_ask_for_a_scene_summary():
    events = _collect(MockProvider(), [Message.user_text("what is here?")], VISIBLE)
    assert [(e.name) for e in events if isinstance(e, ToolCall)] == ["mcp__lampway__scene_summary"]


def test_a_deferred_scene_tool_is_called_through_hermess_bridge():
    events = _collect(MockProvider(), [Message.user_text("what is here?")], BRIDGE)
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert [(c.name, c.arguments) for c in calls] == [
        ("tool_call", {"calls": [{"name": "mcp__lampway__scene_summary", "arguments": {}}]})]


def test_a_request_with_no_tools_gets_text_only():
    """Hermes's auxiliary calls (a title, a summary) carry no tools: a tool call there would be one nothing can answer."""
    events = _collect(MockProvider(), [Message.user_text("Write a short title for this conversation.")], [])
    assert events and all(isinstance(e, Text) for e in events)


def test_with_no_scene_tool_offered_it_says_so_and_calls_nothing():
    """The user's Capabilities switched the scene tools off: the mock names no tool Hermes did not offer."""
    events = _collect(MockProvider(), [Message.user_text("what is here?")], [ToolSpec("clarify", "Ask.", SCHEMA)])
    assert not [e for e in events if isinstance(e, ToolCall)]
    assert "not offered" in "".join(e.text for e in events if isinstance(e, Text))
