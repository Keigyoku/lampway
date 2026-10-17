# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Real TCP disconnects release the gateway's provider, including before headers."""
import asyncio
import json
import socket
import threading

import httpx
import pytest
from starlette.applications import Starlette

from lampway_server.agent.providers.base import Text
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanError
from lampway_server.engine import gateway as GW

from .serve_support import Stack, free_port


@pytest.mark.parametrize("stream,first_token", [(True, False), (True, True), (False, False)])
def test_tcp_disconnect_closes_a_provider_waiting_for_a_token(settings, stream, first_token):
    entered, closed = threading.Event(), threading.Event()

    class Held:
        name = "held"

        async def stream(self, request):
            self.loop = asyncio.get_running_loop()
            self.release = asyncio.Event()
            try:
                if first_token:
                    yield Text("started")
                entered.set()
                await self.release.wait()
                yield Text("released")
            finally:
                closed.set()

    provider = Held()
    registry = GW.Registry()
    token = registry.issue_token("worker-pane")
    app = Starlette(routes=GW.gateway_routes(registry, lambda *args: provider))
    settings.port = free_port()
    with Stack(app, settings):
        connection = socket.create_connection(("127.0.0.1", settings.port), timeout=5)
        body = json.dumps({"stream": stream, "messages": [{"role": "user", "content": "hold"}]}).encode()
        headers = (f"POST {GW.CHAT_PATH} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\n"
                   f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode()
        try:
            connection.sendall(headers + body)
            assert entered.wait(5), "the provider must actually reach its blocked token wait"
            if first_token:
                assert b"200 OK" in connection.recv(4096), "this case disconnects after SSE headers"
            connection.shutdown(socket.SHUT_RDWR)
            connection.close()
            assert closed.wait(3), "HTTP disconnect must close the provider without releasing its token wait"

            async def supervisors_settle():
                for _ in range(100):
                    tasks = [t for t in asyncio.all_tasks() if t.get_name() in
                             ("lampway-gateway-provider", "lampway-gateway-disconnect")]
                    if not tasks:
                        return
                    await asyncio.sleep(0.01)
                raise AssertionError("the provider wait and disconnect watcher must both be joined")

            asyncio.run_coroutine_threadsafe(supervisors_settle(), provider.loop).result(timeout=3)
        finally:
            connection.close()
            if hasattr(provider, "release"):
                provider.loop.call_soon_threadsafe(provider.release.set)


@pytest.mark.parametrize("stream", [True, False])
def test_tcp_provider_error_before_first_token_keeps_its_http_status(settings, stream):
    closed = threading.Event()

    class Refused:
        name = "refused"

        async def stream(self, request):
            try:
                await asyncio.sleep(0.02)
                raise ChatGPTPlanError("usage limit reached", code="subscription_sharing_usage_limit_exceeded")
                yield Text("unreachable")
            finally:
                closed.set()

    registry = GW.Registry()
    token = registry.issue_token("worker-pane")
    app = Starlette(routes=GW.gateway_routes(registry, lambda *args: Refused()))
    settings.port = free_port()
    with Stack(app, settings) as stack:
        response = httpx.post(stack.base + GW.CHAT_PATH, headers={"Authorization": f"Bearer {token}"},
                              json={"stream": stream, "messages": [{"role": "user", "content": "ask"}]}, timeout=5)
        assert response.status_code == 429
        assert response.headers["content-type"].startswith("application/json")
        assert response.json()["error"]["code"] == "subscription_sharing_usage_limit_exceeded"
        assert closed.is_set()
