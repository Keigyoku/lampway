"""Deterministic providers: no network, no model.

``MockProvider`` is what LAMPWAY_PROVIDER=mock runs: it asks for a scene summary
once, then answers with it. ``ScriptedProvider`` replays whatever a test queued.
"""

import json
from typing import AsyncIterator

from .base import ModelRequest, ProviderEvent, Text, ToolCall


class MockProvider:
    name = "mock"

    def __init__(self):
        self.requests: list[ModelRequest] = []

    async def stream(self, request: ModelRequest) -> AsyncIterator[ProviderEvent]:
        self.requests.append(request)
        last = request.messages[-1]
        results = [p for p in last.content if p.get("type") == "tool_result"]
        if results:
            yield Text("Mock provider. Scene summary from Blender:\n")
            yield Text(results[-1]["content"])
            return
        yield Text("Mock provider: looking at the scene.")
        yield ToolCall(id=f"mock_call_{len(self.requests)}", name="scene_summary", arguments={})


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
