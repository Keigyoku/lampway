# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The captain's ruling 10 (2026-10-07): a dead Lampway herdr server is reported and "Start" is offered; it is restarted ONLY on the user's
click, never automatically - not at start-up (the lifespan's one reconcile pass), not at a reconcile, not by an agent's tool, not by a
request that declares an agent origin. ``Cockpit.ensure_server`` is the only caller of ``launcher.start_server``, and the start route is
its only caller."""

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.herdr import launcher as L
from lampway_server.herdr.host import Cockpit


@pytest.fixture
def dead(monkeypatch, tmp_path):
    starts = []
    monkeypatch.setattr(L, "server_status", lambda root: {"running": False})
    monkeypatch.setattr(L, "server_info", lambda root: {"method": None})
    monkeypatch.setattr(L, "start_server", lambda root, method="auto": starts.append(root) or {"running": True})
    return starts


def test_reconcile_reports_the_dead_server_offers_start_and_starts_nothing(dead, tmp_path):
    out = Cockpit(tmp_path / "herdr").reconcile()
    assert out["server"] == "not_running" and "start" in out["offered"] and dead == []


def test_start_up_and_the_routes_never_start_it_and_the_users_click_does(dead, settings, provider, tmp_path, monkeypatch):
    from tests.fake_client import FakeMixarClient
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(tmp_path))
    app = create_app(settings, provider=provider, cockpit=Cockpit(tmp_path / "herdr", project_root=str(tmp_path)))
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:                # the lifespan reconcile runs here
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        h = fake.rest_headers()
        home = http.get("/app/workbench", headers=h).json()
        assert home["server"]["running"] is False and "start" in home["offered"]
        assert http.post("/app/workbench/reconcile", headers=h).json()["offered"] == ["start", "resume"]
        assert dead == []
        r = http.post("/app/workbench/server/start", headers={**h, "x-lampway-origin": "agent"})
        assert r.status_code == 403 and dead == []
        assert http.post("/app/workbench/server/start", headers=h).status_code == 200 and len(dead) == 1      # the user's click


def test_no_agent_tool_can_start_it():
    from lampway_server.agent import workbench_tools as WT
    for spec in WT.specs():
        assert "start" not in str(spec.parameters.get("properties", {}).get("action", {}).get("enum", [])).replace("restart", "")
