# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1 runs only on Hermes (docs/reports/agent-modes-spec.md A0, A5; captain, 2026-10-07: "Agents/workers run on either of those
modes nothing else"). Lampway's own provider loop is gone, so nothing can stand in for the engine: with no engine build, no herdr or
no Node, a Mode 1 ``agent.chat`` or ``agent.input`` is refused before any turn starts, in the repository's refusal shape (a plain
message, and help naming the exact build command and the switch to Your agent), and the model is never called. The engine is in
Mode 1's seat whenever a finished build is found: there is no switch to turn it on."""

import uuid

import pytest
from starlette.testclient import TestClient

from lampway_server.app import create_app
from lampway_server.engine import wiring as W
from lampway_server.engine.front import HermesFront
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .fake_client import FakeMixarClient
from .mode1_support import fake_engine, units_for
from .serve_support import chat, run, stack  # noqa: F401  (stack: the fixture)

pytestmark = pytest.mark.timeout(120)
YOUR_AGENT = "Your agent"


def reply_to(fake, ws, request_id, limit=200):
    """The reply to ``request_id`` and every frame before it."""
    frames = []
    for _ in range(limit):
        frame = ws.receive_json()
        frames.append(frame)
        if frame.get("id") == request_id:
            return frame, frames
    raise AssertionError(f"no reply to {request_id}; frames={frames!r}")


def refused(reply, code):
    result = reply["result"]
    assert result["state"] == "complete", result
    assert result["result"]["ok"] is False and result["result"]["code"] == code, result
    return result["result"]


# ---------------------------------------------------------------------------------------------------- nothing else runs Mode 1
def test_lampways_own_provider_loop_is_gone_and_the_hub_drives_only_the_engine():
    import ast
    import inspect

    from lampway_server.agent import turns as T
    for gone in ("MAX_ROUNDS", "HISTORY_BUDGET", "trim_history", "pair_tool_calls", "add_tool_results", "empty_reply_note"):
        assert not hasattr(T, gone), f"{gone} was the built-in loop's (spec A5)"
    for gone in ("_agent_loop", "_ask", "_ask_batch", "_retry_failed"):
        assert not hasattr(T.AgentHub, gone), f"AgentHub.{gone} was the built-in loop's (spec A5)"
    tree = ast.parse(inspect.getsource(T))
    streamed = [n for n in ast.walk(tree) if isinstance(n, ast.Attribute) and n.attr == "stream"
                and isinstance(n.value, ast.Attribute) and n.value.attr == "provider"]
    assert streamed == [], "the hub never streams from a provider: the gateway is the providers' only caller for Mode 1"
    from lampway_server.agent import prompt
    assert not hasattr(prompt, "PLAN_MODE_PROMPT")


# ---------------------------------------------------------------------------------------------------- no engine build
@pytest.fixture
def no_engine(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "REPO_ENGINES", tmp_path / "no-repo-build")
    monkeypatch.delenv("LAMPWAY_ENGINES_DIR", raising=False)


def test_with_no_engine_built_a_mode1_chat_is_refused_before_any_turn_and_no_model_is_called(no_engine, fake, provider):
    fake.login()
    with fake.connect_ws() as ws:
        fake.handshake(ws)
        session_id = str(uuid.uuid4())
        fake.command(ws, "chat", fake.chat_payload("Add a cube", session_id))
        reply, frames = reply_to(fake, ws, fake.last_request_id)
        fake.command(ws, "input", {"session_id": session_id, "action": "respond", "text": "red"})
        answer, more = reply_to(fake, ws, fake.last_request_id)
        rid = fake.request(ws, "system.ping", {})
        assert ws.receive_json().get("id") == rid, "nothing else was started"
    result = refused(reply, "engine_not_built")
    assert "Hermes" in result["message"] and "not sent" in result["message"]
    assert "scripts/lampway/engine_env.py" in result["help"][0] and any(YOUR_AGENT in h for h in result["help"])
    refused(answer, "engine_not_built")
    assert not [f for f in frames + more if f.get("method") in ("agent.turn.started", "agent.turn.event")]
    assert provider.requests == [], "no other loop answered in the engine's place"


def test_the_engine_is_in_the_seat_whenever_a_build_is_found_with_no_switch(no_engine, settings, tmp_path, monkeypatch):
    fake_engine(tmp_path / "engines")
    engine, why = W.select(settings.state_dir, environ={"LAMPWAY_ENGINES_DIR": str(tmp_path / "engines")})
    assert engine is not None and engine["tag"] == "v0-test", why
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(tmp_path / "engines"))
    assert create_app(settings).state.engine_wiring is not None


def test_an_engine_that_could_not_start_refuses_mode1_saying_so(no_engine, settings, provider, tmp_path, monkeypatch):
    fake_engine(tmp_path / "engines")
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(tmp_path / "engines"))

    async def broken(self):
        raise RuntimeError("the proxy could not bind")
    monkeypatch.setattr(W.EngineWiring, "start", broken)
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            fake.command(ws, "chat", fake.chat_payload("Add a cube", str(uuid.uuid4())))
            reply, _ = reply_to(fake, ws, fake.last_request_id)
    result = refused(reply, "engine_unavailable")
    assert "could not start" in result["message"] and any(YOUR_AGENT in h for h in result["help"])
    assert provider.requests == []


# ---------------------------------------------------------------------------------------------------- no herdr
def test_without_herdr_a_mode1_chat_is_refused_naming_its_build_and_nothing_opens(stack, monkeypatch):
    def missing():
        raise L.HerdrError("herdr is not installed")
    monkeypatch.setattr(L, "bin_path", missing)

    async def scenario(serve, units, island, front):
        _, rid = await chat(island, "Hello", "scene-1")
        return await island.reply(rid), units.opened, serve.calls, island.started()

    reply, opened, calls, started = run(stack, scenario)
    result = refused(reply, "herdr_not_built")
    assert "herdr" in result["message"] and "not sent" in result["message"]
    assert "scripts/lampway/herdr_env.py" in result["help"][0] and "LAMPWAY_HERDR_BIN" in result["help"][0]
    assert not any(YOUR_AGENT in h for h in result["help"]), "Your agent runs in a herdr pane too: it is no way round a missing herdr"
    assert opened == [] and calls == [] and started == []


# ---------------------------------------------------------------------------------------------------- no Node
def test_without_node_a_mode1_chat_is_refused_naming_node_and_herdr_is_never_asked(settings, provider, tmp_path, monkeypatch):
    asked = []
    monkeypatch.setattr(L, "run", lambda root, args, **k: asked.append(args) or "")
    monkeypatch.setattr(L, "server_status", lambda root: asked.append("status") or {"running": True})
    monkeypatch.setattr(L, "bin_path", lambda: "/usr/bin/herdr-played")
    app = create_app(settings, provider=provider)
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path))
    units = units_for(cockpit, settings.state_dir, app.state.engine_tokens, engine=fake_engine(tmp_path / "engines"))
    units.environ = {"PATH": str(tmp_path / "no-node-here")}                  # no LAMPWAY_NODE, and no node on PATH
    app.state.agent.engine = HermesFront(app.state.agent, units)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            asked.clear()                                                     # the start's own reconcile asked; the chat may not
            fake.command(ws, "chat", fake.chat_payload("Add a cube", str(uuid.uuid4())))
            reply, frames = reply_to(fake, ws, fake.last_request_id)
    result = refused(reply, "node_missing")
    assert "Node.js" in result["message"] and "not sent" in result["message"]
    assert "Node.js 22" in result["help"][0] and "LAMPWAY_NODE" in result["help"][0]
    assert any(YOUR_AGENT in h for h in result["help"])
    assert asked == [] and cockpit.list_sessions() == [] and provider.requests == []
    assert not [f for f in frames if f.get("method") == "agent.turn.started"]
