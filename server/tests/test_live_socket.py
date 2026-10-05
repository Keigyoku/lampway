"""The product over a real TCP socket: uvicorn on a loopback port, the
`websockets` client sending the Authorization header on the upgrade (the way
websocket-client does in socket_connection.py:143-145), one full chat turn."""

import asyncio
import json
import socket
import threading
import time
import uuid

import httpx
import pytest
import uvicorn
import websockets

from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.app import create_app

from .fake_client import FakeMixarClient


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def live_server(settings, provider):
    settings.port = free_port()
    app = create_app(settings, provider=provider)
    config = uvicorn.Config(app, host="127.0.0.1", port=settings.port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("uvicorn did not start")
        time.sleep(0.05)
    yield f"http://127.0.0.1:{settings.port}"
    server.should_exit = True
    thread.join(timeout=10)


def test_login_handshake_and_a_tool_turn_over_tcp(live_server, provider, settings):
    provider.script.append([Text("Adding a cube."),
                            ToolCall(id="c1", name="run_blender_python", arguments={"script": "import bpy"})])
    provider.script.append([Text("Done.")])
    with httpx.Client(base_url=live_server) as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        assert fake.get("/api/v1/auth/me").json()["email"] == settings.user_email

    ws_url = live_server.replace("http://", "ws://") + f"/api/agent/ws/{fake.instance_id}"

    async def drive():
        headers = {"Authorization": f"Bearer {fake.access_token}", "x-telemetry-consent": "1",
                   "X-Mixar-Locale": "en_US"}
        async with websockets.connect(ws_url, additional_headers=headers, open_timeout=10) as ws:
            handshake = fake.handshake_frame()
            await ws.send(json.dumps(handshake))
            reply = json.loads(await asyncio.wait_for(ws.recv(), 10))
            assert reply["id"] == handshake["id"] and reply["result"]["agent_ws_v1"] is True
            session_id = str(uuid.uuid4())
            command_id = str(uuid.uuid4())
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": "req_1", "method": "agent.chat",
                                      "params": {"command_id": command_id,
                                                 "payload": fake.chat_payload("Add a cube", session_id)}}))
            frames = []
            while True:
                frame = json.loads(await asyncio.wait_for(ws.recv(), 10))
                frames.append(frame)
                if frame.get("method") == "blender.execute_script":
                    assert frame["params"]["script"] == "import bpy"
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": frame["id"],
                                              "result": {"success": True, "created_objects": ["Cube"]}}))
                if frame.get("method") == "agent.turn.ended":
                    return frames

    async def refused():
        try:
            async with websockets.connect(ws_url, additional_headers={"Authorization": "Bearer nope"},
                                          open_timeout=10) as ws:
                await ws.recv()
        except websockets.exceptions.ConnectionClosed as closed:
            return closed.rcvd.code if closed.rcvd else None
        return None

    frames = asyncio.run(drive())
    payloads = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]
    assert payloads[0]["type"] == "run_status" and payloads[-1] == {**payloads[-1], "type": "turn_end",
                                                                      "status": "completed"}
    assert any("Done." in json.dumps(p) for p in payloads)
    assert asyncio.run(refused()) == 4001
