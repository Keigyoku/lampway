# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine runtime's pieces that need no engine (docs/reports/agent-modes-spec.md E1.2, E1.6): the child's environment and the
session MCP endpoint's gates. The engine itself is exercised in test_engine_conformance.py."""

from pathlib import Path

from lampway_server.engine import runtime as R


def test_the_child_environment_holds_no_secret_and_never_the_users_hermes(tmp_path):
    base = {"PATH": "/usr/bin", "OPENROUTER_API_KEY": "sk-or-v1-FAKE", "ANTHROPIC_API_KEY": "sk-ant-FAKE", "GITHUB_TOKEN": "ghp_FAKE",
            "HERMES_HOME": "~/.hermes", "HTTPS_PROXY": "http://corp-proxy:3128", "LAMPWAY_JWT_SECRET": "x", "LANG": "C.UTF-8"}
    env = R.child_env(tmp_path / "h", "http://127.0.0.1:9999", base_env=base)
    assert env["HERMES_HOME"] == str(tmp_path / "h") and env["HOME"] == str(tmp_path / "h" / "home")
    assert not [k for k in env if k.endswith(("_KEY", "_TOKEN", "_SECRET"))]
    assert env["HTTPS_PROXY"] == env["HTTP_PROXY"] == env["ALL_PROXY"] == "http://127.0.0.1:9999"
    assert env["NO_PROXY"] == "127.0.0.1" and env["PATH"] == "/usr/bin" and env["LANG"] == "C.UTF-8"


def test_the_minimal_config_names_only_the_gateway():
    cfg = R.minimal_config("http://127.0.0.1:8787/engine/v1", "tok", "lampway")
    assert "provider: custom" in cfg and 'base_url: "http://127.0.0.1:8787/engine/v1"' in cfg and 'api_key: "tok"' in cfg


def test_find_engine_reads_only_finished_builds(tmp_path):
    assert R.find_engine(tmp_path) is None
    unfinished = tmp_path / "hermes" / "v1"
    unfinished.mkdir(parents=True)
    assert R.find_engine(tmp_path) is None
    (unfinished / "engine.json").write_text('{"engine": "hermes", "tag": "v1", "entry": "env/bin/hermes-acp", "source": "src"}')
    found = R.find_engine(tmp_path)
    assert found["tag"] == "v1" and found["entry_path"] == str(unfinished / "env/bin/hermes-acp")


class _Runtime(R.EngineRuntime):
    def __init__(self):
        self.sessions = {"s1": R.EngineSession("s1", Path("/nonexistent"), mcp_token="right")}
        self.calls = []

    async def call_tool(self, session_id, name, arguments):
        self.calls.append((session_id, name, arguments))
        return "pong", False


def test_the_engine_endpoint_needs_its_sessions_token_and_offers_the_users_tools(fake, http):
    rt = _Runtime()
    http.app.state.agent.engine = rt
    rpc = lambda body, token="right", sid="s1": http.post(f"/engine/mcp/{sid}", json=body, headers={"Authorization": f"Bearer {token}"})  # noqa: E731
    assert rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, token="wrong").status_code == 401
    assert rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}, sid="s2").status_code == 401
    init = rpc({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}}).json()
    assert init["result"]["serverInfo"]["name"] == "lampway"
    assert rpc({"jsonrpc": "2.0", "method": "notifications/initialized"}).status_code == 202
    names = {t["name"] for t in rpc({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}).json()["result"]["tools"]}
    assert {"run_blender_python", "scene_summary", "ask_user", "lampway_capabilities"} <= names
    assert "swarm_start" not in names                                    # the swarm is off until the user switches it on (E2)
    off = rpc({"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "swarm_start", "arguments": {}}}).json()
    assert off["result"]["isError"] and "capability" in off["result"]["content"][0]["text"] and rt.calls == []
    ok = rpc({"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "scene_summary", "arguments": {}}}).json()
    assert ok["result"] == {"content": [{"type": "text", "text": "pong"}], "isError": False}
    assert rt.calls == [("s1", "scene_summary", {})]


def test_a_closed_socket_detaches_an_engine_turn_and_still_cancels_a_built_in_one(settings, provider):
    """E1.7/R5: the hub names the engine's running turn as a survivor of its client's socket (ws.py then leaves it running) and
    marks it detached; with no engine in the seat the turn is cancelled as before."""
    import asyncio
    from types import SimpleNamespace

    from lampway_server.agent.turns import Session, Turn
    from lampway_server.app import create_app

    hub = create_app(settings, provider=provider).state.agent

    async def go(engine_running):
        hub.engine = SimpleNamespace(is_running=lambda sid: engine_running) if engine_running is not None else None
        sock = object()
        session = Session("s1")
        turn = Turn("s1", "t1", "r1")
        turn.task = asyncio.get_running_loop().create_task(asyncio.sleep(30))
        turn.socket = sock
        session.current = turn
        hub.sessions["s1"] = session
        survivors = hub.socket_closed(sock)
        await asyncio.sleep(0)
        out = (survivors, turn.detached, turn.task.cancelled())
        turn.task.cancel()
        return out, turn.task

    (survivors, detached, cancelled), task = asyncio.run(go(True))
    assert survivors == {task} and detached and not cancelled
    (survivors, detached, cancelled), _ = asyncio.run(go(None))
    assert survivors == set() and not detached and cancelled
