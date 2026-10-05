"""The mock provider (LAMPWAY_PROVIDER=mock) is how the real client is driven with no model.
A user message beginning ``py:`` runs the rest as a Blender script, so a live run can change the scene."""

import asyncio

from lampway_server.agent.providers.base import Message, ModelRequest, Text, ToolCall
from lampway_server.agent.providers.mock import MockProvider


def _collect(provider, messages):
    async def run():
        return [e async for e in provider.stream(ModelRequest(system="", messages=messages, tools=[]))]
    return asyncio.run(run())


def test_a_py_message_becomes_a_run_blender_python_call():
    events = _collect(MockProvider(), [Message.user_text("py: import bpy\nbpy.ops.mesh.primitive_cube_add()")])
    calls = [e for e in events if isinstance(e, ToolCall)]
    assert [(c.name, c.arguments) for c in calls] == [
        ("run_blender_python", {"script": "import bpy\nbpy.ops.mesh.primitive_cube_add()"})]


def test_the_result_of_a_py_call_is_reported_back():
    messages = [
        Message.user_text("py: result = 1"),
        Message("assistant", [{"type": "tool_call", "id": "c1", "name": "run_blender_python", "arguments": {"script": "result = 1"}}]),
        Message("user", [{"type": "tool_result", "tool_call_id": "c1", "content": '{"success": true}', "is_error": False}]),
    ]
    text = "".join(e.text for e in _collect(MockProvider(), messages) if isinstance(e, Text))
    assert "Ran your script" in text and '"success": true' in text


def test_other_messages_still_ask_for_a_scene_summary():
    events = _collect(MockProvider(), [Message.user_text("what is here?")])
    assert [(e.name) for e in events if isinstance(e, ToolCall)] == ["scene_summary"]
