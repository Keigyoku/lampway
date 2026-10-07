# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""M0 (docs/reports/agent-modes-spec.md): one agent mode per scene tab, the server's half.

How the server learns a tab's mode (the choice, documented in agent/byoa.py): the chat payload carries the tab's ``agent_mode``
(``Scene.lampway_agent_mode``), and the cockpit's B2 binding table knows which scene sessions a harness pane is bound to. A tab
is in Your agent mode when either says so; then ``agent.chat`` and ``agent.input`` are refused with ``code: wrong_mode`` and a
help line naming the switch, before any turn starts. Two tabs run one mode each at the same time.

The island's switch uses two routes: ``GET /app/workbench/harnesses`` (``harnesses.listing()``) and ``POST /app/workbench/mode``,
which binds a pane to the tab (reusing one, or starting the harness the user picked) or unbinds every pane from it. Only the
user's Client switches: an agent caller is refused. herdr is a recording fake; no harness binary runs."""
import pytest
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import Text
from lampway_server.app import create_app
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L
from lampway_server.herdr.harnesses import base as HB

from .fake_client import FakeMixarClient
from .test_byoa_egress import FakeHerdr

TAB_A = "a0000000-0000-4000-8000-00000000000a"
TAB_B = "b0000000-0000-4000-8000-00000000000b"


@pytest.fixture
def stack(settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    monkeypatch.setenv("LAMPWAY_MCP_LAUNCHER", "/opt/lw/connector/lampway-mcp")
    herdr = FakeHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    proj = tmp_path / "proj"
    proj.mkdir()
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(proj))
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(proj))
    app = create_app(settings, provider=provider, cockpit=cockpit)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        yield http, fake, cockpit, herdr, proj, provider


def until(ws, pred, limit=400):
    frames = []
    for _ in range(limit):
        f = ws.receive_json()
        frames.append(f)
        if pred(f):
            return frames
    raise AssertionError(f"never seen; frames={frames!r}")


def chat(fake, ws, session_id, message="Add a cube", **extra):
    payload = {**fake.chat_payload(message, session_id), **extra}
    command_id = fake.command(ws, "chat", payload)
    return command_id, fake.last_request_id


def assert_quiet(fake, ws):
    """Nothing else was started: the next frame is the answer to a ping."""
    rid = fake.request(ws, "system.ping", {})
    assert ws.receive_json().get("id") == rid


# ------------------------------------------------------------------------------------------------------------------ wrong_mode
def test_a_chat_that_says_its_tab_is_in_your_agent_mode_is_refused_with_the_switch_named(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, rid = chat(fake, ws, TAB_A, agent_mode="byoa")
        reply = until(ws, lambda f: f.get("id") == rid)[-1]
        assert_quiet(fake, ws)
    result = reply["result"]
    assert result["state"] == "complete" and result["result"]["ok"] is False and result["result"]["code"] == "wrong_mode"
    assert any("Lampway Agent" in h for h in result["result"]["help"]) and "Your agent" in result["result"]["message"]


def test_a_chat_into_a_tab_a_harness_pane_is_bound_to_is_refused_even_if_the_payload_says_nothing(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    cockpit.create_session("claude", "Chest fit audit", str(proj), by="user", scene_session_id=TAB_A)
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, rid = chat(fake, ws, TAB_A)
        reply = until(ws, lambda f: f.get("id") == rid)[-1]
        assert_quiet(fake, ws)
        cid = fake.command(ws, "input", {"session_id": TAB_A, "text": "yes"})
        answer = until(ws, lambda f: f.get("id") == fake.last_request_id)[-1]
    assert reply["result"]["result"]["code"] == "wrong_mode" and answer["result"]["result"]["code"] == "wrong_mode"
    assert cid


def test_two_tabs_run_one_mode_each_at_the_same_time(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    cockpit.create_session("claude", "Chest fit audit", str(proj), by="user", scene_session_id=TAB_A)
    provider.script.append([Text("Mode 1 answers tab B.")])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        _, rid_a = chat(fake, ws, TAB_A)
        refused = until(ws, lambda f: f.get("id") == rid_a)[-1]
        cid_b, _ = chat(fake, ws, TAB_B, agent_mode="runtime")
        frames = fake.run_turn(ws, cid_b, on_script=lambda p: fake.execute_script_result(p["script"]))
    assert refused["result"]["result"]["code"] == "wrong_mode"
    assert any(f.get("method") == "agent.turn.started" and f["params"]["session_id"] == TAB_B for f in frames)
    texts = [f["params"]["event"].get("content", {}).get("set") for f in frames if f.get("method") == "agent.turn.event"]
    assert "Mode 1 answers tab B." in texts


def test_an_unbound_pane_no_longer_puts_its_old_tab_in_your_agent_mode(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    rec = cockpit.create_session("claude", "Chest fit audit", str(proj), by="user", scene_session_id=TAB_A)
    cockpit.unbind(rec["id"])
    provider.script.append([Text("Back in Mode 1.")])
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        cid, _ = chat(fake, ws, TAB_A)
        frames = fake.run_turn(ws, cid, on_script=lambda p: fake.execute_script_result(p["script"]))
    assert any(f.get("method") == "agent.turn.started" for f in frames)


# ------------------------------------------------------------------------------------------------------------------ the routes
def test_the_harness_listing_is_every_adapter_with_how_to_install_a_missing_one(stack, monkeypatch):
    http, fake, cockpit, herdr, proj, provider = stack
    monkeypatch.setattr(HB.Adapter, "locate", lambda self: "/opt/fake/bin/claude" if self.id == "claude" else None)
    monkeypatch.setattr(L, "probe", lambda argv, timeout=10: (0, "1.2.3 (Claude Code)"))
    r = http.get("/app/workbench/harnesses", headers=fake.rest_headers())
    assert r.status_code == 200
    body = r.json()
    assert [h["id"] for h in body["harnesses"]] == list(HN.ids()) and body["enabled"] is True
    claude = body["harnesses"][0]
    assert claude["installed"] is True and claude["version"] == "1.2.3 (Claude Code)" and claude["label"] == "Claude Code"
    assert all(h["installed"] is False and h["install"] for h in body["harnesses"][1:])
    assert http.get("/app/workbench/harnesses").status_code == 401


def _mode(http, fake, body, headers=None):
    return http.post("/app/workbench/mode", headers={**fake.rest_headers(), **(headers or {})}, json=body)


def test_switching_a_tab_to_your_agent_starts_the_picked_harness_bound_to_it(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    r = _mode(http, fake, {"scene_session_id": TAB_A, "mode": "byoa", "harness": "claude", "name": "Scene tab one"})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["mode"] == "byoa" and out["pane"]["harness"] == "claude" and out["pane"]["scene_session_id"] == TAB_A
    assert out["view"] == "transcript"
    assert [s["id"] for s in cockpit.find_by_scene(TAB_A)] == [out["pane"]["id"]]
    again = _mode(http, fake, {"scene_session_id": TAB_A, "mode": "byoa", "harness": "claude"}).json()
    assert again["pane"]["id"] == out["pane"]["id"] and len(cockpit.list_sessions()) == 1                # a live bound pane is reused


def test_a_new_tab_session_takes_the_pane_over_from_the_previous_one(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    rec = cockpit.create_session("claude", "Chest fit audit", str(proj), by="user", scene_session_id=TAB_A)
    r = _mode(http, fake, {"scene_session_id": TAB_B, "previous_session_id": TAB_A, "mode": "byoa", "pane": rec["id"]})
    assert r.status_code == 200, r.text
    assert cockpit.find_by_scene(TAB_A) == [] and [s["id"] for s in cockpit.find_by_scene(TAB_B)] == [rec["id"]]
    assert len(cockpit.list_sessions()) == 1


def test_switching_back_to_lampway_agent_unbinds_and_never_touches_the_pane(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    rec = cockpit.create_session("claude", "Chest fit audit", str(proj), by="user", scene_session_id=TAB_A)
    before = len(herdr.calls)
    r = _mode(http, fake, {"scene_session_id": TAB_A, "mode": "runtime"})
    assert r.status_code == 200 and r.json() == {"mode": "runtime", "unbound": [rec["id"]]}
    assert cockpit.find_by_scene(TAB_A) == [] and cockpit.list_sessions()[0]["state"] == "live"
    assert len(herdr.calls) == before                                                                    # law 5: the pane runs on


def test_only_the_users_client_switches_a_tab(stack):
    http, fake, cockpit, herdr, proj, provider = stack
    r = _mode(http, fake, {"scene_session_id": TAB_A, "mode": "byoa", "harness": "claude"}, {"X-Lampway-Origin": "agent"})
    assert r.status_code == 403 and cockpit.list_sessions() == []


def test_a_switch_the_server_cannot_do_is_refused_with_its_reason(stack, monkeypatch):
    http, fake, cockpit, herdr, proj, provider = stack
    assert _mode(http, fake, {"scene_session_id": TAB_A, "mode": "sideways"}).status_code == 400
    assert _mode(http, fake, {"mode": "runtime"}).status_code == 400
    assert _mode(http, fake, {"scene_session_id": TAB_A, "mode": "byoa"}).status_code == 400              # neither a harness nor a pane
    shell = cockpit.create_session("shell", "Scratch shell", str(proj), by="user")
    r = _mode(http, fake, {"scene_session_id": TAB_A, "mode": "byoa", "pane": shell["id"]})
    assert r.status_code == 409 and "harness" in r.json()["detail"]
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "0")
    r = _mode(http, fake, {"scene_session_id": TAB_A, "mode": "byoa", "harness": "claude"})
    assert r.status_code == 403 and "off" in r.json()["detail"]
