# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""connections_store.md tests 1 and 13 (the hub's routes) and section 4.1/4.2: every route needs the bearer, no route ever returns a
secret, a write from a declared agent or a cross-origin page is refused, and the store kind is reported with its reason."""

import json

import httpx
import pytest

from lampway_server.app import create_app

SENTINEL = "sk-" "or-v1-FAKE-ROUTE-SENTINEL-00000000000000"
SENT = []


def _fake_openrouter(request):
    """Every check in these tests lands here, never on the network; it echoes the key back to prove the hub never forwards a body."""
    SENT.append(request)
    return httpx.Response(401, json={"error": f"bad key {request.headers.get('authorization')}"})


@pytest.fixture
def app(settings, provider):
    SENT.clear()
    return create_app(settings, provider=provider, connections_transport=httpx.MockTransport(_fake_openrouter))


@pytest.fixture
def auth(fake):
    fake.login()
    return fake.rest_headers()


def _routes():
    return [("GET", "/app/connections", None), ("GET", "/app/connections/openrouter", None),
            ("POST", "/app/connections/openrouter/source", {"mode": "manual"}),
            ("PUT", "/app/connections/openrouter/secret", {"fields": {"key": SENTINEL}}),
            ("POST", "/app/connections/openrouter/rotate", {"fields": {"key": SENTINEL}}),
            ("POST", "/app/connections/openrouter/test", {}), ("POST", "/app/connections/chatgpt_plan/signin", {}),
            ("POST", "/app/connections/chatgpt_plan/signout", {}), ("DELETE", "/app/connections/openrouter/source/pointer", None),
            ("POST", "/app/connections/openrouter/move-to-keyring", {}), ("POST", "/app/connections/scan", {})]


def test_status_routes_need_the_bearer(http):
    for method, path, body in _routes():
        r = http.request(method, path, json=body)
        assert r.status_code == 401, (method, path, r.status_code)


def test_no_route_returns_a_secret(http, auth):
    r = http.put("/app/connections/openrouter/secret", json={"fields": {"key": SENTINEL}}, headers=auth)
    assert r.status_code == 200 and r.json()["fingerprint"]["last4"] == SENTINEL[-4:]
    for method, path, body in _routes():
        r = http.request(method, path, json=body, headers=auth)
        blob = r.text + json.dumps(dict(r.headers))
        assert SENTINEL not in blob, (method, path)
        assert SENTINEL[-12:] not in blob, (method, path)
    assert SENT and all(str(q.url).startswith("https://openrouter.ai/api/v1/key") for q in SENT)     # test and rotate reached the fake


def test_the_list_reports_the_store_and_every_registry_row(http, auth):
    body = http.get("/app/connections", headers=auth).json()
    assert body["store"]["kind"] == "file" and body["store"]["reason"]            # the test session has no keyring backend
    ids = {c["id"] for c in body["connections"]}
    assert {"openrouter", "chatgpt_plan", "studio:meshy", "mcp:hyper3d", "github", "huggingface"} <= ids
    gh = next(c for c in body["connections"] if c["id"] == "github")
    assert gh["unused"] is True                                                    # C10


def test_a_declared_agent_write_is_refused(http, auth):
    for header in ({"x-lampway-origin": "agent"}, {"x-mixar-job-origin": "agent"}):
        r = http.put("/app/connections/openrouter/secret", json={"fields": {"key": SENTINEL}}, headers={**auth, **header})
        assert r.status_code == 403 and r.json()["detail"] == "only your click in Connections can change a credential"


def test_a_cross_origin_write_is_refused(http, auth):
    r = http.put("/app/connections/openrouter/secret", json={"fields": {"key": SENTINEL}}, headers={**auth, "origin": "https://evil.example"})
    assert r.status_code == 403


def test_an_unknown_id_is_404_with_the_list(http, auth):
    r = http.get("/app/connections/nope", headers=auth)
    assert r.status_code == 404 and r.json()["detail"].startswith("no connection nope: the connections are ")


def test_a_route_off_test_is_refused_with_the_route(http, auth, monkeypatch):
    from lampway_server import egress as E
    E.ACTIVE._permissive = False
    http.put("/app/connections/studio:meshy/secret", json={"fields": {"key": "msy-FAKE-ROUTE-0000000000000000"}}, headers=auth)
    r = http.post("/app/connections/studio:meshy/test", json={}, headers=auth)
    assert r.status_code == 409 and r.json()["detail"] == "testing sends your key to api.meshy.ai: switch Meshy on in Privacy first"


def test_the_write_log_holds_actions_never_values(http, auth, settings):
    http.put("/app/connections/openrouter/secret", json={"fields": {"key": SENTINEL}}, headers=auth)
    rows = [json.loads(l) for l in (settings.state_dir / "connections" / "log.jsonl").read_text().splitlines()]
    assert rows[-1]["id"] == "openrouter" and rows[-1]["action"] == "secret" and rows[-1]["by"] == "user" and rows[-1]["ok"] is True
    assert SENTINEL not in (settings.state_dir / "connections" / "log.jsonl").read_text()
