"""The product over a real TCP socket: uvicorn on a loopback port, the
`websockets` client sending the Authorization header on the upgrade (the way
websocket-client does in socket_connection.py:143-145), one full chat turn on the
unit's Hermes pane (the scripted serve: Mode 1 runs only on Hermes, spec A5)."""

import asyncio
import json
import uuid

import httpx
import pytest
import websockets

from .fake_client import FakeMixarClient
from .serve_support import chat, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)


def test_login_handshake_and_a_tool_turn_over_tcp(stack, settings):
    with httpx.Client(base_url=stack.base) as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        assert fake.get("/api/v1/auth/me").json()["email"] == settings.user_email

    async def scenario(serve, units, island, front):
        serve.scripts.append([("say", "Adding a cube."), ("mcp", "run_blender_python", {"script": "import bpy"}), ("say", "Done.")])
        command_id, _ = await chat(island, "Add a cube", str(uuid.uuid4()))
        await island.ended(command_id)
        return island.events(command_id), island.scripts

    payloads, scripts = run(stack, scenario, on_script=lambda p: {"success": True, "created_objects": ["Cube"]})
    assert [s["script"] for s in scripts] == ["import bpy"]
    assert payloads[0]["type"] == "run_status" and payloads[-1] == {**payloads[-1], "type": "turn_end", "status": "completed"}
    assert any("Done." in json.dumps(p) for p in payloads)

    ws_url = stack.base.replace("http://", "ws://") + f"/api/agent/ws/{fake.instance_id}"

    async def refused():
        try:
            async with websockets.connect(ws_url, additional_headers={"Authorization": "Bearer nope"}, open_timeout=10) as ws:
                await ws.recv()
        except websockets.exceptions.ConnectionClosed as closed:
            return closed.rcvd.code if closed.rcvd else None
        return None

    assert asyncio.run(refused()) == 4001
