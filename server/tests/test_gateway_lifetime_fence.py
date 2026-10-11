# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A worker's model calls end with its key, independently of HTTP peer shutdown."""
import asyncio
import json
import socket
import threading
import time
from types import SimpleNamespace

import httpx
import pytest
from starlette.applications import Starlette

from lampway_server.agent.providers.base import Text
from lampway_server.agent.providers.chatgpt_plan import ChatGPTPlanError
from lampway_server.engine import gateway as GW
from lampway_server.herdr import host as H

from .serve_support import Stack, free_port


class HeldProvider:
    name = "held"

    def __init__(self, first=False):
        self.first = first
        self.calls = 0
        self.active = set()
        self.finished = set()
        self.releases = {}

    async def stream(self, request):
        self.calls += 1
        request_id = self.calls
        self.active.add(request_id)
        self.loop = asyncio.get_running_loop()
        release = asyncio.Event()
        self.releases[request_id] = release
        try:
            if self.first:
                yield Text("first")
            await release.wait()
            yield Text("released")
        finally:
            self.active.remove(request_id)
            self.finished.add(request_id)

    def release_all(self):
        if hasattr(self, "loop"):
            def release():
                for event in self.releases.values():
                    event.set()
            self.loop.call_soon_threadsafe(release)


def wait_for(predicate):
    deadline = time.monotonic() + 3
    while not predicate() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert predicate(), "the gateway model calls did not settle within three seconds"


def open_call(stack, token, stream=True):
    connection = socket.create_connection(("127.0.0.1", stack.settings.port), timeout=5)
    body = json.dumps({"stream": stream, "messages": [{"role": "user", "content": "hold"}]}).encode()
    headers = (f"POST {GW.CHAT_PATH} HTTP/1.1\r\nHost: 127.0.0.1\r\nAuthorization: Bearer {token}\r\n"
               f"Content-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n").encode()
    connection.sendall(headers + body)
    return connection


@pytest.mark.parametrize("stream,first", [(True, False), (True, True), (False, False)])
def test_revoked_key_closes_a_pending_model_call_even_while_tcp_stays_open(settings, stream, first):
    provider = HeldProvider(first)
    registry = GW.Registry()
    token = registry.issue_token("swarm:sw1:worker-1")
    settings.port = free_port()
    app = Starlette(routes=GW.gateway_routes(registry, lambda *args: provider))
    with Stack(app, settings) as stack:
        connection = open_call(stack, token, stream)
        try:
            wait_for(lambda: provider.active == {1})
            if first:
                assert b"200 OK" in connection.recv(4096)
            assert registry.revoke_session("swarm:sw1:worker-1") == 1
            wait_for(lambda: provider.finished == {1} and not provider.active)
            wait_for(lambda: not registry._calls)
        finally:
            connection.close()
            provider.release_all()


def test_revocation_closes_all_calls_of_its_worker_and_preserves_the_main_call(settings):
    worker, main = HeldProvider(), HeldProvider()
    registry = GW.Registry()
    worker_token = registry.issue_token("worker")
    main_token = registry.issue_token("main")
    settings.port = free_port()
    app = Starlette(routes=GW.gateway_routes(registry, lambda sid=None: worker if sid == "worker" else main))
    with Stack(app, settings) as stack:
        sockets = []
        try:
            for token in (worker_token, worker_token, main_token):
                sockets.append(open_call(stack, token))
            wait_for(lambda: worker.active == {1, 2} and main.active == {1})
            registry.revoke_session("worker")
            wait_for(lambda: worker.finished == {1, 2} and not worker.active)
            assert main.active == {1} and not main.finished
            response = httpx.post(stack.base + GW.CHAT_PATH, headers={"Authorization": f"Bearer {worker_token}"},
                                  json={"messages": [{"role": "user", "content": "retry"}]}, timeout=5)
            assert response.status_code == 401 and worker.calls == 2 and main.calls == 1
            main.release_all()
            wait_for(lambda: main.finished == {1} and not registry._calls)
        finally:
            for connection in sockets:
                connection.close()
            worker.release_all()
            main.release_all()


@pytest.mark.parametrize("enroll_before", [True, False])
def test_cross_thread_revocation_cannot_miss_enrollment(enroll_before):
    async def run():
        registry = GW.Registry()
        token = registry.issue_token("worker")
        future = registry.watch_call(token) if enroll_before else None
        thread = threading.Thread(target=registry.revoke, args=(token,))
        thread.start()
        thread.join(timeout=3)
        assert not thread.is_alive()
        future = future if future is not None else registry.watch_call(token)
        await asyncio.wait_for(future, 3)
        registry.unwatch_call(token, future)
        assert registry._calls == {} and registry.session_for(token) is None
    asyncio.run(run())


def test_queued_revocation_callback_is_safe_after_request_cleanup():
    async def run():
        registry = GW.Registry()
        token = registry.issue_token("worker")
        future = registry.watch_call(token)
        errors = []
        asyncio.get_running_loop().set_exception_handler(lambda loop, context: errors.append(context))
        thread = threading.Thread(target=registry.revoke, args=(token,))
        thread.start()
        thread.join(timeout=3)
        assert not thread.is_alive()
        registry.unwatch_call(token, future)
        await asyncio.sleep(0)
        assert future.cancelled() and registry._calls == {} and not errors
    asyncio.run(run())


def test_provider_setup_error_removes_enrollment_and_keeps_the_http_error(settings):
    class Refused:
        name = "refused"

        def stream(self, request):
            raise ChatGPTPlanError("usage limit reached", code="subscription_sharing_usage_limit_exceeded")

    registry = GW.Registry()
    token = registry.issue_token("worker")
    settings.port = free_port()
    app = Starlette(routes=GW.gateway_routes(registry, lambda *args: Refused()))
    with Stack(app, settings) as stack:
        response = httpx.post(stack.base + GW.CHAT_PATH, headers={"Authorization": f"Bearer {token}"},
                              json={"stream": True, "messages": [{"role": "user", "content": "ask"}]}, timeout=5)
        assert response.status_code == 429
        assert response.json()["error"]["code"] == "subscription_sharing_usage_limit_exceeded"
        assert registry._calls == {}


@pytest.mark.parametrize("close", [True, False])
def test_owned_worker_stop_revokes_before_pane_shutdown_and_finished_history_stays(tmp_path, monkeypatch, close):
    cockpit = H.Cockpit(tmp_path / "herdr")
    rec = {"id": "owned", "created_by": "swarm", "role": "worker", "swarm_binding": "swarm:sw1:worker-1",
           "agent": "lampway_hermes", "pane_id": "w1:p2", "state": "live"}
    monkeypatch.setattr(cockpit, "_get", lambda sid: rec)
    monkeypatch.setattr(cockpit, "_update", lambda f: f({"sessions": [rec]}))
    calls = []
    cockpit.mode1 = SimpleNamespace(forget=lambda row: calls.append(("revoke", row["swarm_binding"])))
    monkeypatch.setattr(H.L, "run", lambda *args: calls.append(("close", "w1:p2")))
    cockpit.end_swarm_pane("owned", "swarm:sw1:worker-1", "cancelled" if close else "finished", close)
    assert calls == ([("revoke", "swarm:sw1:worker-1"), ("close", "w1:p2")] if close else [])
    assert rec["state"] == "ended" and rec["end_reason"] == ("cancelled" if close else "finished")


def test_a_foreign_pane_cannot_revoke_a_worker_key(tmp_path, monkeypatch):
    cockpit = H.Cockpit(tmp_path / "herdr")
    rec = {"id": "foreign", "created_by": "user", "role": "main", "swarm_binding": None}
    monkeypatch.setattr(cockpit, "_get", lambda sid: rec)
    calls = []
    cockpit.mode1 = SimpleNamespace(forget=lambda row: calls.append(row))
    monkeypatch.setattr(H.L, "run", lambda *args: calls.append(args))
    with pytest.raises(H.CockpitError, match="was not opened by the swarm"):
        cockpit.end_swarm_pane("foreign", "swarm:sw1:worker-1", "cancelled", True)
    assert not calls


@pytest.mark.parametrize("confirmed,agent", [(False, "lampway_hermes"), (True, "lampway_hermes"), (True, "codex")])
def test_user_close_forgets_only_a_confirmed_lampway_worker_key_before_pane_shutdown(tmp_path, monkeypatch, confirmed, agent):
    cockpit = H.Cockpit(tmp_path / "herdr")
    rec = {"id": "user-pane", "agent": agent, "pane_id": "w1:p1", "state": "live", "role": "worker",
           "swarm_binding": "swarm:sw1:worker-1"}
    calls = []
    monkeypatch.setattr(cockpit, "_get", lambda sid: calls.append(("get", sid)) or rec)
    monkeypatch.setattr(cockpit, "_update", lambda f: f({"sessions": [rec]}))
    cockpit.mode1 = SimpleNamespace(forget=lambda row: calls.append(("revoke", row["id"])))
    monkeypatch.setattr(H.L, "run", lambda root, argv: calls.append(("close", argv)))
    if not confirmed:
        with pytest.raises(H.CockpitError, match="explicit user action"):
            cockpit.close_session("user-pane", confirmed=False)
        assert calls == [] and rec["state"] == "live"
        return
    assert cockpit.close_session("user-pane", confirmed=True) == {"closed": "user-pane"}
    expected = [("get", "user-pane")]
    if agent == "lampway_hermes":
        expected.append(("revoke", "user-pane"))
    expected.append(("close", ["pane", "close", "w1:p1"]))
    assert calls == expected
    assert rec["state"] == "ended" and rec["end_reason"] == "closed by the user"
