# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""A worker's real TestClient WebSocket must close before its portal goes away."""
import threading
import uuid

import pytest
from starlette.testclient import TestClient, WebSocketTestSession

from lampway_server.app import create_app
from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet, FakeWorker


def test_fleet_close_joins_a_worker_at_the_websocket_portal_exit_boundary(settings, monkeypatch):
    app = create_app(settings)
    exiting, release = threading.Event(), threading.Event()
    records = []
    worker = None
    original_exit = WebSocketTestSession.__exit__

    def held_exit(session, *args):
        if threading.current_thread() is worker:
            records.append("worker_waits_for_portal")
            exiting.set()
            assert release.wait(10), "the test did not release the worker's WebSocket close"
        result = original_exit(session, *args)
        if threading.current_thread() is worker:
            records.append("worker_websocket_closed")
        return result
    monkeypatch.setattr(WebSocketTestSession, "__exit__", held_exit)

    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        connection = str(uuid.uuid4())
        worker = FakeWorker(fleet, connection, fake.instance_id)
        fleet.workers[connection] = worker
        original_join = worker.join

        def release_and_join(timeout=None):
            records.append("fleet_joins_worker")
            release.set()
            return original_join(timeout)
        monkeypatch.setattr(worker, "join", release_and_join)
        worker.start()
        try:
            assert worker.ready.wait(10), "worker never completed its real WebSocket handshake"
            worker.shutdown()
            assert exiting.wait(10), "worker never reached its WebSocket portal exit"
            fleet.close()
            assert not worker.is_alive(), "fleet.close returned while a worker still needed the TestClient portal"
            assert records == ["worker_waits_for_portal", "fleet_joins_worker", "worker_websocket_closed"]
        finally:
            # Keep RED runs clean too: the held worker closes while its real portal is still alive.
            release.set()
            original_join(10)
            assert not worker.is_alive()


def test_fleet_close_reports_a_worker_that_does_not_end_within_its_deadline():
    release, asked_to_stop = threading.Event(), threading.Event()
    worker = threading.Thread(target=release.wait, daemon=True)
    worker.shutdown = asked_to_stop.set
    fleet = FakeFleet(None, "fixture-parent")
    fleet.workers["fixture-stuck-worker"] = worker
    worker.start()
    try:
        with pytest.raises(RuntimeError, match="fixture-stuck-worker"):
            fleet.close(timeout=0.02)
        assert asked_to_stop.is_set() and worker.is_alive()
    finally:
        release.set()
        worker.join(10)
        assert not worker.is_alive()
