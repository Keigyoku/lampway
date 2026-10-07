# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""BYOA B5 (docs/reports/agent-modes-spec.md): egress, environment and consent for the user's own agents in Lampway's panes.

- One route per harness (byoa:claude ... byoa:cursor), off until the user switches it on; its card says the harness talks to its
  vendor directly under the user's account and that Lampway does not see or log that traffic.
- Starting a harness pane runs inside egress.guard(route): with the route off it is refused naming the route and nothing reaches
  herdr; with it on the log row is written before herdr starts the harness.
- herdr (and so every pane) starts from the scrubbed base (connections.env_for([])); a pane gets the real login variables, and an
  API key only when the user opted in for that pane.
herdr itself is faked: no binary is started and nothing leaves the machine."""
import json

import pytest

from lampway_server import egress as EG
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

HARNESS_ROUTES = ("byoa:claude", "byoa:codex", "byoa:hermes", "byoa:opencode", "byoa:pi", "byoa:grok", "byoa:cursor")


@pytest.fixture
def strict(tmp_path):
    m = EG.Egress(tmp_path / "egress-state")
    EG.install()
    prev = EG.ACTIVE
    EG.set_active(m)
    yield m
    EG.set_active(prev)


class FakeHerdr:
    """Answers the herdr commands create_session issues, and records each one with what the egress log held at that moment."""

    def __init__(self, egress=None):
        self.calls = []
        self.egress = egress

    def __call__(self, root, args, timeout=30, input=None):
        args = [str(a) for a in args]
        sent = [r for r in (self.egress.log() if self.egress else []) if r.get("event") == "send"]
        self.calls.append({"args": args, "sends_before": [r["route"] for r in sent]})
        if args[:2] == ["api", "snapshot"]:
            return json.dumps({"result": {"snapshot": {"workspaces": [], "panes": []}}})
        if args[:2] in (["workspace", "create"], ["tab", "create"]):
            return json.dumps({"result": {"root_pane": {"pane_id": "p1", "terminal_id": "t1", "workspace_id": "w1", "tab_id": "tab1"}}})
        if args[:2] == ["pane", "read"]:
            return "user@box:~$ "
        return ""

    def first(self, *prefix):
        return next(c for c in self.calls if c["args"][:len(prefix)] == list(prefix))


@pytest.fixture
def herdr(monkeypatch, strict):
    fake = FakeHerdr(strict)
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    return fake


def test_one_route_per_harness_each_off_until_the_user_switches_it_on(strict):
    for rid in HARNESS_ROUTES:
        assert rid in EG.ROUTES, rid
        assert strict.enabled(rid) is False
        card = EG.ROUTES[rid].retention
        assert "directly" in card and "your account" in card and "Lampway does not see or log that traffic" in card, rid
    assert {r["id"] for r in strict.routes_view()} >= set(HARNESS_ROUTES)


def test_a_harness_launch_with_its_route_off_is_refused_naming_the_route_and_herdr_is_never_asked(herdr, strict, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(EG.EgressRefused, match="byoa:claude is off"):
        c.create_session("claude", "Chest fit audit", str(tmp_path), by="user")
    assert herdr.calls == [] and c.list_sessions() == []
    refused = [r for r in strict.log() if r.get("event") == "refused"]
    assert refused and refused[-1]["route"] == "byoa:claude"


def test_with_the_route_on_the_log_row_is_written_before_herdr_starts_the_harness(herdr, strict, tmp_path):
    strict.set_route("byoa:codex", True)
    c = H.Cockpit(tmp_path / "herdr")
    rec = c.create_session("codex", "Boots seed read", str(tmp_path), by="user")
    start = herdr.first("agent", "start")
    assert "byoa:codex" in start["sends_before"] and rec["agent"] == "codex"
    assert "byoa:codex" in herdr.calls[0]["sends_before"]                      # the row precedes even the pane's creation


def test_a_shell_or_command_session_is_local_and_needs_no_route(herdr, strict, tmp_path):
    c = H.Cockpit(tmp_path / "herdr")
    c.create_session("shell", "Scratch shell", str(tmp_path), by="user")
    assert not [r for r in strict.log() if str(r.get("route", "")).startswith("byoa:")]


def test_herdr_starts_from_the_scrubbed_base_no_key_and_no_lampway_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-value-not-a-key")
    monkeypatch.setenv("MESHY_API_KEY", "test-value-not-a-key")
    monkeypatch.setenv("LAMPWAY_JWT_SECRET", "test-value-not-a-secret")
    monkeypatch.setenv("HERDR_PANE_ID", "w1:p9")                               # the fleet's variables stay scrubbed too
    env = L.env_for(tmp_path / "root")
    leaked = sorted(k for k in env if k.endswith("_API_KEY") or "SECRET" in k or k == "HERDR_PANE_ID")
    assert leaked == []
    assert env["PATH"] and env["HERDR_SOCKET_PATH"].startswith(str(tmp_path / "root")) or "lampway-herdr-" in env["HERDR_SOCKET_PATH"]
    assert env["HOME"] == str(tmp_path / "root" / "home")                     # isolation (invariant 6) is intact


def test_a_pane_gets_the_real_login_variables_and_no_key_without_the_users_opt_in(herdr, strict, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-key")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "claude-config"))
    strict.set_route("byoa:claude", True)
    c = H.Cockpit(tmp_path / "herdr")
    c.create_session("claude", "Chest fit audit", str(tmp_path), by="user")
    made = herdr.first("workspace", "create")["args"]
    envs = [made[i + 1] for i, a in enumerate(made) if a == "--env"]
    assert any(e.startswith("HOME=") for e in envs) and f"CLAUDE_CONFIG_DIR={tmp_path / 'claude-config'}" in envs
    assert not [e for e in envs if "API_KEY" in e]


def test_an_api_key_reaches_a_pane_only_when_the_user_opted_in_for_that_pane(herdr, strict, monkeypatch, tmp_path):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-value-not-a-key")
    strict.set_route("byoa:claude", True)
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(H.CockpitError, match="only the user"):
        c.create_session("claude", "Chest fit audit", str(tmp_path), api_key=True, by="agent")
    c.create_session("claude", "Chest fit audit", str(tmp_path), api_key=True, by="user")
    made = herdr.first("workspace", "create")["args"]
    assert "ANTHROPIC_API_KEY=test-value-not-a-key" in [made[i + 1] for i, a in enumerate(made) if a == "--env"]
    assert c.list_sessions()[-1]["api_key"] is True


def test_the_launch_table_says_a_harness_start_is_gated_by_its_byoa_route():
    kind, reason = EG.LAUNCHES["herdr/launcher.py:_spawn"]
    assert kind == "local" and "byoa:" in reason and "guard" in reason


def test_the_create_route_refuses_a_harness_whose_route_is_off_with_403(settings, provider, tmp_path, monkeypatch, strict):
    from starlette.testclient import TestClient
    from lampway_server.app import create_app
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    fake = FakeHerdr(strict)
    monkeypatch.setattr(L, "run", fake)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    app = create_app(settings, provider=provider, cockpit=H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path)), egress=strict)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        from .fake_client import FakeMixarClient
        client = FakeMixarClient(http, password=settings.user_password)
        client.login()
        h = client.rest_headers()
        r = http.post("/app/workbench/sessions", headers=h, json={"agent": "claude", "name": "Chest fit audit", "cwd": str(tmp_path)})
        assert r.status_code == 403 and "byoa:claude" in r.json()["detail"]
        r = http.post("/app/workbench/sessions", headers={**h, "X-Lampway-Origin": "agent"},
                      json={"agent": "claude", "name": "Chest fit audit", "cwd": str(tmp_path), "api_key": True})
        assert r.status_code == 403 and "only your click" in r.json()["detail"]
