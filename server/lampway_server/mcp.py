"""The MCP endpoint behind the client's connector ("Connect AI apps"): one JSON-RPC 2.0 message from an external AI app per POST.

``initialize``, ``ping``, ``tools/list`` and ``tools/call`` are served; notifications are accepted (202). A tool call runs in the
app instance named by ``X-Mixar-Instance-Id`` and the scene session named by ``X-Mixar-Session-Id``, as a ``blender.execute_script``
round trip, exactly like the agent's own tool calls. Offered: the scene tools and the Lampway tools that are one script in Blender.
NOT offered: the studio tools (they spend credits on the owner's subscription), the swarm and ``ask_user`` (they need the agent loop).
"""

import json
import uuid

from .agent import lampway_tools as lt
from .agent.tools import RUN_BLENDER_PYTHON, SCENE_SUMMARY, TOOLS, UnknownTool, format_tool_result, script_for

PROTOCOL_VERSION = "2025-06-18"
PARSE_ERROR, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32601, -32602


def offered_tools() -> list:
    return [t for t in TOOLS if t.name in (RUN_BLENDER_PYTHON, SCENE_SUMMARY) or t.name in lt.BY_NAME]


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class McpServer:
    def __init__(self, hub, agent):
        self.hub = hub
        self.agent = agent

    def tools_payload(self) -> list:
        return [{"name": t.name, "description": t.description, "inputSchema": t.parameters} for t in offered_tools()]

    async def handle(self, message, instance_id: str, session_id: str):
        """The JSON-RPC response for one request, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "not a JSON-RPC 2.0 request")
        method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {}
        if request_id is None:
            return None                                              # a notification (notifications/initialized, cancelled, ...)
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "lampway", "version": "0.1.0"},
                "instructions": "Lampway's tools for the open Blender scene. Studio tools (credits) are not offered here."}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tools_payload()}}
        if method == "tools/call":
            return await self._call(request_id, params, instance_id, session_id)
        return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    async def _call(self, request_id, params, instance_id, session_id):
        name = params.get("name")
        if name not in {t.name for t in offered_tools()}:
            return _error(request_id, INVALID_PARAMS, f"unknown or not offered tool {name!r}")
        socket = self.hub.sockets.get(instance_id)
        if socket is None:
            return self._result(request_id, "the desktop app is not connected to this server (open Lampway and sign in)", True)
        try:
            script = script_for(name, params.get("arguments") or {})
        except (UnknownTool, lt.BadArguments) as exc:
            return self._result(request_id, str(exc), True)
        try:
            result = await self.agent._blender_script(socket, session_id=session_id, chat_session_id=session_id, turn_id="mcp",
                                                      call_id=str(uuid.uuid4()), tool_name=name, script=script)
        except Exception as exc:  # noqa: BLE001 - the external app is told, the server stays up
            return self._result(request_id, f"Blender could not run the tool: {type(exc).__name__}: {exc}", True)
        text, is_error = format_tool_result(result)
        return self._result(request_id, text, is_error)

    @staticmethod
    def _result(request_id, text, is_error):
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}}


def parse(body: bytes):
    try:
        return json.loads(body.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError):
        return None, _error(None, PARSE_ERROR, "Parse error")
