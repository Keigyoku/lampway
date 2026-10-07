"""Deterministic providers: no network, no model.

``MockProvider`` is what LAMPWAY_PROVIDER=mock runs, behind the model gateway, for Lampway Agent's Hermes (spec A5): it asks for a
scene summary once, then answers with it. A user message beginning ``py:`` runs the rest as a Blender script instead (so a live run
through the real client can change the scene), and the answer reports the script's result. It calls Lampway's tools by the names
Hermes offers them (``mcp__lampway__<tool>``, or through Hermes's ``tool_call`` bridge when they are deferred behind
``tool_search``), never a tool the request did not offer, and a request with no tools (Hermes's title or summary call) gets text
only. ``ScriptedProvider`` replays whatever a test queued.
"""

import json
from typing import AsyncIterator, Optional

from .base import ModelRequest, ProviderEvent, Text, ToolCall


SCRIPT_PREFIX = "py:"
MCP_PREFIX = "mcp__lampway__"
BRIDGE = "tool_call"
TITLE = "Lampway mock conversation"


def _called(messages, tool_name) -> bool:
    """Whether the conversation called ``tool_name`` (by any of the names it may carry, or through the bridge)."""
    for m in messages:
        for p in m.content:
            if p.get("type") != "tool_call":
                continue
            name = str(p.get("name") or "")
            if name in (tool_name, MCP_PREFIX + tool_name):
                return True
            if name == BRIDGE and tool_name in json.dumps(p.get("arguments") or {}):
                return True
    return False


def _call(request: ModelRequest, tool: str, arguments: dict, n: int) -> Optional[ToolCall]:
    """Lampway's ``tool`` as this request offers it: by its own name (the gateway's older callers), its MCP name, or the bridge."""
    names = {t.name for t in request.tools}
    for name in (MCP_PREFIX + tool, tool):
        if name in names:
            return ToolCall(id=f"mock_call_{n}", name=name, arguments=arguments)
    if BRIDGE in names:
        return ToolCall(id=f"mock_call_{n}", name=BRIDGE, arguments={"calls": [{"name": MCP_PREFIX + tool, "arguments": arguments}]})
    return None


class MockProvider:
    name = "mock"

    def __init__(self):
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        if not request.tools:
            yield Text(TITLE)                             # Hermes's own title or summary call: no tool to call there
            return
        last = request.messages[-1]
        results = [p for p in last.content if p.get("type") == "tool_result"]
        if results:
            if _called(request.messages, "run_blender_python"):
                yield Text("Mock provider. Ran your script in Blender. Result:\n")
                yield Text(results[-1]["content"])
                return
            yield Text("Mock provider. Scene summary from Blender:\n")
            yield Text(results[-1]["content"])
            return
        text = last.text().strip()
        if text.lower().startswith(SCRIPT_PREFIX):
            call = _call(request, "run_blender_python", {"script": text[len(SCRIPT_PREFIX):].lstrip()}, len(self.requests))
            if call is None:
                yield Text("Mock provider: Lampway's run_blender_python tool is not offered to me (Capabilities), so nothing ran.")
                return
            yield Text("Mock provider: running your script.")
            yield call
            return
        call = _call(request, "scene_summary", {}, len(self.requests))
        if call is None:
            yield Text("Mock provider: Lampway's scene_summary tool is not offered to me (Capabilities), so I cannot look.")
            return
        yield Text("Mock provider: looking at the scene.")
        yield call


class ScriptedProvider(MockProvider):
    """``script`` holds one list of events per expected model call."""

    name = "scripted"

    def __init__(self, script=None):
        super().__init__()
        self.script = list(script or [])

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        if not self.script:
            yield Text("(scripted provider: no reply queued for call "
                       f"{len(self.requests)}; last message: {json.dumps(request.messages[-1].content)[:200]})")
            return
        for event in self.script.pop(0):
            yield event
