# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine's MCP endpoint (docs/reports/agent-modes-spec.md E1.6): ``POST /engine/mcp/<session_id>``, MCP over streamable HTTP
answered with plain JSON, for the one Hermes child of that scene session.

* Loopback only, and only with that session's bearer token (issued when the child starts; never logged).
* ``tools/list`` is the agent's full registry as the user's Capabilities allow (not the external-app subset ``mcp.py`` offers),
  plus ``ask_user``; ``tools/call`` runs through ``EngineRuntime.call_tool``, i.e. ``AgentHub._run_tool`` with its gates.
* Replies are JSON today. The captain decided the engine gets TOON (2026-10-06); that arrives with the companion spec's C0
  encoder and C1 envelope, which another crew builds, through ``format_result`` here.
"""

from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

PROTOCOL_VERSION = "2025-06-18"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def format_result(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}


def _error(rid, code, message):
    return {"jsonrpc": "2.0", "id": rid, "error": {"code": code, "message": message}}


def engine_mcp_routes(get_runtime) -> list:
    async def endpoint(request: Request):
        runtime = get_runtime()
        if runtime is None:
            return JSONResponse({"detail": "the engine is not running on this server"}, status_code=404)
        if (request.client.host if request.client else "") not in LOOPBACK:
            return JSONResponse({"detail": "loopback only"}, status_code=403)
        session_id = request.path_params["session_id"]
        auth = request.headers.get("authorization") or ""
        token = auth[7:] if auth.lower().startswith("bearer ") else ""
        if runtime.session_for_token(session_id, token) is None:
            return JSONResponse({"detail": "not this session's engine"}, status_code=401)
        try:
            msg = await request.json()
        except ValueError:
            return JSONResponse(_error(None, -32700, "not JSON"), status_code=400)
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0":
            return JSONResponse(_error(None, -32600, "not a JSON-RPC 2.0 request"), status_code=400)
        rid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if rid is None:
            return Response(status_code=202)                          # notifications/initialized and friends
        if method == "initialize":
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "lampway", "version": "0.1.0"},
                "instructions": "Lampway's tools for the scene this conversation belongs to. Call scene_summary first."}})
        if method == "ping":
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {}})
        if method == "tools/list":
            tools = [{"name": t.name, "description": t.description, "inputSchema": t.parameters} for t in runtime.tool_specs()]
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": {"tools": tools}})
        if method == "tools/call":
            name = str(params.get("name") or "")
            if name not in {t.name for t in runtime.tool_specs()}:
                return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": format_result(
                    f"refused: {name} is not one of Lampway's tools here, or its capability is off "
                    "(lampway_capabilities action=list shows what you may do)", True)})
            text, is_error = await runtime.call_tool(session_id, name, params.get("arguments") or {})
            return JSONResponse({"jsonrpc": "2.0", "id": rid, "result": format_result(text, is_error)})
        return JSONResponse(_error(rid, -32601, f"Method not found: {method}"))

    return [Route("/engine/mcp/{session_id}", endpoint, methods=["POST"])]
