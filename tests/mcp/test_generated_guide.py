# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The launcher uses the server's generated guide and never invents a tool."""
import asyncio
import re

import pytest

from mcp import Client
from mixar.modules.mcp_bridge.core import stdio_server


@pytest.mark.parametrize("mode", ["auto", "legacy"])
def test_live_initialize_guide_resources_and_prompt_use_backend_instructions(mode):
    class Connector:
        health = {}
        def instructions(self):
            return 'Call lampway_inspect first. Live server guidance.'
        def catalog(self):
            return [{'name': 'lampway_inspect', 'description': 'Read the scene.',
                     'inputSchema': {'type': 'object', 'properties': {}}}]

    async def run():
        async with Client(stdio_server.create_server(Connector()), mode=mode) as client:
            guide = client.instructions
            assert guide == 'Call lampway_inspect first. Live server guidance.'
            resource = await client.read_resource('lampway://guide')
            assert resource.contents[0].text == guide
            prompt = await client.get_prompt('build-and-verify', {'goal': 'make a cube'})
            assert guide in prompt.messages[0].content.text
            names = {t.name for t in (await client.list_tools()).tools}
            assert set(re.findall(r'[a-z]+(?:_[a-z0-9]+)+', prompt.messages[0].content.text)) <= names
    asyncio.run(run())


def test_closed_app_guide_mentions_only_tools_in_tools_list():
    class Closed:
        health = {'ui_control': False}
        def instructions(self):
            raise RuntimeError('Lampway is not open')
        def readiness(self):
            return 'absent', ''

    async def run():
        async with Client(stdio_server.create_server(Closed())) as client:
            guide = client.instructions
            names = {t.name for t in (await client.list_tools()).tools}
            assert set(re.findall(r'[a-z]+(?:_[a-z0-9]+)+', guide)) <= names
            assert len(guide.encode()) <= 2048
            assert 'only the user confirms' in guide
    asyncio.run(run())


def test_connector_reads_guide_from_initialize_once_without_starting_app(monkeypatch):
    from mixar.modules.mcp_bridge.core import connector as module
    connector = module.Connector()
    calls = []
    def attach(start=False):
        assert not start
        return {'port': 1}, {}
    def request(record, method, path, payload, *args, **kwargs):
        calls.append(payload['method'])
        if payload['method'] == 'initialize':
            return {'result': {'protocolVersion': '2025-11-25', 'instructions': 'Live guidance.'}}
        return {'result': {'tools': []}}
    monkeypatch.setattr(connector, 'attach', attach)
    monkeypatch.setattr(module, 'request', request)
    assert connector.instructions() == 'Live guidance.'
    assert connector.catalog() == []
    assert connector.instructions() == 'Live guidance.'
    assert calls == ['initialize', 'tools/list']


def test_invalid_tool_in_live_guide_is_removed_but_other_guidance_survives():
    class Connector:
        health = {}
        def instructions(self):
            return "Call nonexistent_tool first.\nPreserve this advice."
        def catalog(self):
            return []
    async def run():
        async with Client(stdio_server.create_server(Connector())) as client:
            assert client.instructions == "Preserve this advice."
    asyncio.run(run())
