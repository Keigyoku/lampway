# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later
"""Audit F2, both halves at once: the SERVER's MCP call (lampway_server.mcp.McpServer with the agent's real _blender_script)
against the CLIENT's real admission code - mcp_bridge's rpc.dispatch for begin/end, and for a script the two gates the client
applies (connection_manager.on_script_execute's SessionManager.has_active_session, then lease.authorize_script). The server's
own test fakes the client; this one proves the request shapes the server sends are the ones the client admits."""
import asyncio
from pathlib import Path
import sys
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from test_mcp_operation_leases import env  # noqa: E402,F401 - the client's lease fixture (two scenes, MCP enabled)

from lampway_server import mcp as M  # noqa: E402
from lampway_server.agent.turns import AgentHub  # noqa: E402
from mixar.modules.mcp_bridge.core import lease, rpc  # noqa: E402
from mixar.modules.space_mixie_chat.core.session import SessionManager  # noqa: E402


class ClientSocket:
    def __init__(self):
        self.seen = []

    async def request(self, method, params, timeout=None):
        self.seen.append(method)
        if method in ("mcp.begin_operation", "mcp.end_operation"):
            return rpc.dispatch(method, params)
        assert method == "blender.execute_script"
        ctx = params.get("agent_ctx") or {}
        if not SessionManager.has_active_session(ctx.get("chat_session_id") or params.get("session_id") or ""):
            return {"success": False, "error": "Agent session not active"}
        refused = lease.authorize_script(params.get("session_id"), ctx)
        return refused or {"success": True, "output": "admitted by the client's gates", "created_objects": []}


class Agent:
    script_timeout_s = 60.0
    _blender_script = AgentHub._blender_script


def test_the_servers_mcp_call_is_admitted_by_the_clients_real_gates(env):
    socket = ClientSocket()
    server = M.McpServer(type("Hub", (), {"sockets": {"i1": socket}})(), Agent())
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "print(1)"}}}
    r = asyncio.run(server.handle(msg, "i1", env.first.mixie_session_id))
    assert r["result"]["isError"] is False and "admitted by the client's gates" in r["result"]["content"][0]["text"], r
    assert socket.seen == ["mcp.begin_operation", "blender.execute_script", "mcp.end_operation"]
    assert not lease.any_active_operation() and env.first.mixie_chat_state == "IDLE"


def test_with_no_scene_named_the_current_scene_is_leased_and_used(env):
    socket = ClientSocket()
    server = M.McpServer(type("Hub", (), {"sockets": {"i1": socket}})(), Agent())
    msg = {"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "print(1)"}}}
    r = asyncio.run(server.handle(msg, "i1", ""))
    assert r["result"]["isError"] is False, r
    assert not lease.any_active_operation()


def test_a_scene_the_chat_is_using_is_refused_and_no_script_is_sent(env):
    from mixar.modules.space_mixie_chat.constants import SessionState
    SessionManager.set_state(env.first, SessionState.BUSY)
    socket = ClientSocket()
    server = M.McpServer(type("Hub", (), {"sockets": {"i1": socket}})(), Agent())
    msg = {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "print(1)"}}}
    r = asyncio.run(server.handle(msg, "i1", env.first.mixie_session_id))
    assert r["result"]["isError"] is True and "scene_busy" in r["result"]["content"][0]["text"]
    assert socket.seen == ["mcp.begin_operation"] and uuid.UUID(env.first.mixie_session_id)
