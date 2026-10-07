# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""The installed-style launcher negotiates real MCP even before a desktop exists."""

import asyncio
import json
import re
import os
from pathlib import Path
import sys

import pytest

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.mark.parametrize("saved_inspect", [False, True])
def test_sdk_initializes_and_exposes_ui_without_blender_or_backend(tmp_path, saved_inspect):
    if saved_inspect:
        connector = tmp_path / "connector"
        connector.mkdir()
        (connector / "tools.json").write_text(json.dumps({"version": 1, "tools": [{
            "name": "lampway_inspect", "description": "Read the open scene as typed data.",
            "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}}]}))
    async def run():
        script = Path(__file__).resolve().parents[2] / "src/scripts/mixar/mcp.py"
        env = {**os.environ, "LAMPWAY_MCP_DISCOVERY_DIR": str(tmp_path / "discovery")}
        async with stdio_client(StdioServerParameters(command=sys.executable, args=[str(script)], env=env)) as streams:
            async with ClientSession(*streams) as session:
                result = await asyncio.wait_for(session.initialize(), 5)
                assert result.server_info.name == "Lampway"
                assert result.instructions and "only the user confirms" in result.instructions
                assert len(result.instructions.encode()) <= 2048
                resource = await session.read_resource("lampway://guide")
                assert resource.contents[0].text == result.instructions
                prompts = await session.list_prompts()
                assert prompts.prompts[0].name == "build-and-verify"
                prompt = await session.get_prompt("build-and-verify", {"goal": "make a cube"})
                assert "make a cube" in prompt.messages[0].content.text
                assert result.instructions in prompt.messages[0].content.text
                quote = await session.call_tool("mixar_tool_quote", {"tool": "mixar_ui_act"})
                assert quote.structured_content["result"]["invocation_credits"] == 0
                catalog = await session.list_tools()
                names = {tool.name for tool in catalog.tools}
                assert set(re.findall(r"[a-z]+(?:_[a-z0-9]+)+", result.instructions)) <= names
                if saved_inspect:
                    assert "First call lampway_inspect" in result.instructions
                else:
                    assert "lampway_inspect" not in result.instructions
                assert {"mixar_ui_context", "mixar_ui_observe", "mixar_ui_act", "mixar_ui_call_status"} <= names
                status = await session.call_tool("mixar_ui_context", {})
                assert status.is_error
                assert "Lampway is not open" in str(status.content)  # Nothing installed here.
    asyncio.run(run())
