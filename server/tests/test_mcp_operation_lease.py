"""Audit F2 (2026-10-06): a scene tool over MCP runs inside an MCP operation. The client admits a script only while the scene is
leased (mcp.begin_operation sets it BUSY, so connection_manager.on_script_execute finds an active session) and only when the
script's agent_ctx carries that lease's mcp_operation_id (lease.authorize_script). The server never opened one, so every scene
tool answered "Agent session not active". The fake client below enforces both gates the way the client does."""
import asyncio
import json
import uuid

from lampway_server import mcp as M
from lampway_server.agent.turns import AgentHub


class GatedClient:
    """The desktop's side of the socket: begin/end lease a scene; execute_script passes both of the client's gates or is refused."""

    def __init__(self, scene_session=None, fail_script=False):
        self.scene_session = scene_session or str(uuid.uuid4())
        self.leases = {}                                   # session id -> operation id
        self.calls = []
        self.fail_script = fail_script

    async def request(self, method, params, timeout=None):
        self.calls.append(method)
        if method == "mcp.begin_operation":
            op = str(uuid.UUID(params["operation_id"]))
            sid = params.get("session_id") or self.scene_session
            if sid != self.scene_session:
                return {"success": False, "error_type": "document_changed", "error": "the scene is gone"}
            if sid in self.leases:
                return {"success": False, "error_type": "scene_busy", "error": "Another AI app connection is working in this scene tab"}
            self.leases[sid] = op
            return {"success": True, "operation_id": op, "session_id": sid, "scene_name": "Scene", "expires_in_seconds": params.get("timeout_seconds", 120)}
        if method == "mcp.end_operation":
            released = self.leases.get(params["session_id"]) == params["operation_id"]
            if released:
                del self.leases[params["session_id"]]
            return {"success": True, "released": released}
        if method == "blender.execute_script":
            ctx = params.get("agent_ctx") or {}
            sid = ctx.get("chat_session_id") or params.get("session_id")
            if sid not in self.leases:                                     # connection_manager.on_script_execute
                return {"success": False, "error": "Agent session not active"}
            if ctx.get("mcp_operation_id") != self.leases[sid] or params.get("session_id") != sid:   # lease.authorize_script
                return {"success": False, "error_type": "mcp_operation_expired", "error": "MCP operation is missing, expired or belongs to another scene"}
            if self.fail_script:
                raise ConnectionError("the socket dropped mid-script")
            return {"success": True, "output": "ran in the leased scene", "created_objects": []}
        raise AssertionError(f"unexpected request {method}")


class Hub:
    def __init__(self, socket):
        self.sockets = {"i1": socket}


class Agent:
    script_timeout_s = 5.0
    _blender_script = AgentHub._blender_script                          # the real request the agent sends


def call(server, session=""):
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": "run_blender_python", "arguments": {"script": "print(1)"}}}
    return asyncio.run(server.handle(msg, "i1", session))


def test_a_scene_tool_over_mcp_runs_inside_a_lease_and_releases_it():
    client = GatedClient()
    r = call(M.McpServer(Hub(client), Agent()), client.scene_session)
    assert r["result"]["isError"] is False, r
    assert "ran in the leased scene" in r["result"]["content"][0]["text"]
    assert client.calls == ["mcp.begin_operation", "blender.execute_script", "mcp.end_operation"] and client.leases == {}


def test_with_no_session_header_the_lease_names_the_scene_the_script_then_uses():
    client = GatedClient()
    r = call(M.McpServer(Hub(client), Agent()), "")
    assert r["result"]["isError"] is False, r
    assert client.leases == {}


def test_a_refused_lease_is_the_answer_and_no_script_is_sent():
    client = GatedClient()
    client.leases[client.scene_session] = str(uuid.uuid4())             # another AI app holds the scene
    r = call(M.McpServer(Hub(client), Agent()), client.scene_session)
    assert r["result"]["isError"] is True and "scene_busy" in r["result"]["content"][0]["text"]
    assert "blender.execute_script" not in client.calls


def test_the_lease_is_released_when_the_script_fails():
    client = GatedClient(fail_script=True)
    r = call(M.McpServer(Hub(client), Agent()), client.scene_session)
    assert r["result"]["isError"] is True
    assert client.calls[-1] == "mcp.end_operation" and client.leases == {}
