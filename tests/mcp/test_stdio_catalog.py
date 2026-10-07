# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""The launcher passes the backend's discovery hints through and indexes its own UI tools."""

import asyncio
import json

from mcp import Client

from mixar.modules.mcp_bridge.core import stdio_server

BACKEND_TOOLS = [
    {"name": "execute_bpy_script", "description": "Run bpy.\nMixar credits: free.",
     "inputSchema": {"type": "object", "properties": {"code": {"type": "string"}},
                     "additionalProperties": False},
     "_meta": {"mixar/domain": "build", "anthropic/alwaysLoad": True}},
    {"name": "mixar_tool_catalog", "description": "Index of Lampway tools.\nMixar credits: free.",
     "inputSchema": {"type": "object", "properties": {
         "query": {"type": "string"}, "domain": {"enum": ["account", "build"]}},
         "additionalProperties": False},
     "_meta": {"mixar/domain": "account"}},
]


class FakeConnector:
    def __init__(self):
        self.tasks, self.calls = set(), []

    def catalog(self):
        return json.loads(json.dumps(BACKEND_TOOLS))

    def call(self, name, arguments, call_id):
        self.calls.append((name, arguments))
        payload = {"result": {"domains": {"build": 1}, "tools": [
            {"name": "execute_bpy_script", "domain": "build", "summary": "Run bpy.",
             "read_only": False, "credits": "free."}]}, "usage": {"request_id": call_id}}
        return {"content": [{"type": "text", "text": json.dumps(payload)}],
                "structuredContent": payload, "isError": False}

    def cancel(self, call_id=None):
        pass


def run(check):
    connector = FakeConnector()

    async def main():
        async with Client(stdio_server.create_server(connector)) as client:
            await check(client, connector)
    asyncio.run(main())


#: Claude Code keeps only this many characters of server instructions and
#: each tool description.
CLAUDE_CODE_TEXT_CAP = 2048


def test_instructions_teach_the_scene_workflow_within_claude_codes_cap():
    assert len(stdio_server.GUIDE.encode()) <= CLAUDE_CODE_TEXT_CAP
    # Preserve audit F3's scene workflow and safety guidance in the generated
    # server-owned instructions, alongside C2's new first inspection step.
    assert "First call lampway_inspect with no arguments" in stdio_server.GUIDE
    for tool in ("lampway_scene_new", "run_blender_python", "lampway_status", "lampway_vault_search",
                 "lampway_call_status", "lampway_ui_call_status"):
        assert tool in stdio_server.GUIDE
    flat = " ".join(stdio_server.GUIDE.split())
    assert "Ask the user when an open choice matters" in flat and "never use OS-level computer use" in flat
    assert "Nothing offered here spends credits" in flat
    assert "plan, never confirm" in stdio_server.GUIDE
    assert "Never delete or overwrite the user's source files" in stdio_server.GUIDE
    from mixar.modules.common.ui_control.core import schema
    assert all(len(tool["description"]) <= CLAUDE_CODE_TEXT_CAP for tool in schema.tools())


def test_backend_discovery_hints_survive_the_launcher():
    async def check(client, connector):
        tools = {tool.name: tool for tool in (await client.list_tools()).tools}
        assert tools["execute_bpy_script"].meta["anthropic/alwaysLoad"] is True
        assert tools["mixar_ui_act"].meta["mixar/domain"] == "ui"
        assert tools["mixar_tool_catalog"].input_schema["properties"]["domain"]["enum"][-2:] == ["ui", "scenes"]
        assert tools["mixar_scene_new"].meta["mixar/domain"] == "scenes"
    run(check)


def test_catalog_index_merges_ui_tools_and_answers_the_ui_domain_locally():
    async def check(client, connector):
        merged = (await client.call_tool("mixar_tool_catalog", {})).structured_content["result"]
        assert merged["domains"] == {"build": 1, "ui": 5, "scenes": 5}
        assert {"mixar_ui_observe", "execute_bpy_script"} <= {entry["name"] for entry in merged["tools"]}
        ui_only = (await client.call_tool("mixar_tool_catalog", {"domain": "ui"})).structured_content
        assert {entry["domain"] for entry in ui_only["result"]["tools"]} == {"ui"}
        assert len(connector.calls) == 1  # domain="ui" never reaches the backend
        build_only = (await client.call_tool("mixar_tool_catalog", {"domain": "build"})).structured_content
        assert "ui" not in build_only["result"]["domains"]
    run(check)


def test_every_tool_the_launchers_guide_and_prompt_name_is_listed():
    """Audit F3 (2026-10-06): the launcher's guide replaced the server's instructions and named 18 tools that do not exist in Lampway
    (upstream Mixar's backend vocabulary: execute_bpy_script, render_viewport, scene_overview, ...). Every tool name the guide and
    the build-and-verify prompt use must be in tools/list as an AI app sees it: the launcher's own tools plus Lampway's server."""
    import re
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "server"))
    from lampway_server import mcp as server_mcp

    class ServerConnector(FakeConnector):
        def catalog(self):
            return json.loads(json.dumps(server_mcp.McpServer(None, None).tools_payload()))

    seen = {}

    async def main():
        async with Client(stdio_server.create_server(ServerConnector())) as client:
            seen["names"] = {tool.name for tool in (await client.list_tools()).tools}
            prompt = await client.get_prompt("build-and-verify", {"goal": "make a cube"})
            seen["prompt"] = prompt.messages[0].content.text
    asyncio.run(main())
    # every snake_case word is read as a tool name, except attribute paths (bpy.data.scenes.new) and the words listed here
    prose = {"build_and_verify"}
    named = set(re.findall(r"(?<![.\w])[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b", stdio_server.GUIDE + seen["prompt"])) - prose
    assert named and not (named - seen["names"]), sorted(named - seen["names"])
