# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine in production (docs/reports/agent-modes-spec.md E1.2-E1.5, E1.3's start-up check): how ``create_app`` puts Hermes in
Mode 1's seat. No engine runs here (a fake build record is enough to select one); the live turn is test_engine_wiring_live.py."""

import asyncio
import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from lampway_server import capabilities as CAP
from lampway_server.agent.providers.base import Text
from lampway_server.app import create_app
from lampway_server.engine import gateway as GW
from lampway_server.engine import hermes_config as HC
from lampway_server.engine import proxy as PX
from lampway_server.engine import runtime as R
from lampway_server.engine import wiring as W

BASE = "http://127.0.0.1:8787"


def fake_build(root: Path) -> Path:
    build = root / "hermes" / "v0-test"
    build.mkdir(parents=True)
    (build / "engine.json").write_text(json.dumps({"engine": "hermes", "tag": "v0-test", "entry": "env/bin/hermes-acp", "source": "src"}))
    return root


@pytest.fixture
def no_repo_build(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "REPO_ENGINES", tmp_path / "no-repo-build")
    monkeypatch.delenv("LAMPWAY_ENGINES_DIR", raising=False)
    monkeypatch.delenv(W.SWITCH, raising=False)


# ---------------------------------------------------------------------------------------------------- selection
def test_the_built_in_loop_stays_without_the_switch_and_says_why(no_repo_build, settings, tmp_path, caplog):
    fake_build(tmp_path / "engines")
    with caplog.at_level(logging.INFO, logger="lampway.engine"):
        engine, why = W.select(settings.state_dir, environ={"LAMPWAY_ENGINES_DIR": str(tmp_path / "engines")})
    assert engine is None and W.SWITCH in why
    with caplog.at_level(logging.INFO, logger="lampway.engine"):
        app = create_app(settings)
    assert app.state.engine_wiring is None and app.state.agent.engine is None
    assert [r for r in caplog.records if "built-in agent loop" in r.getMessage() and W.SWITCH in r.getMessage()]


def test_the_switch_without_a_finished_build_keeps_the_built_in_loop(no_repo_build, settings, tmp_path):
    engine, why = W.select(settings.state_dir, environ={W.SWITCH: "hermes", "LAMPWAY_ENGINES_DIR": str(tmp_path / "empty")})
    assert engine is None and "no finished engine build" in why and str(tmp_path / "empty") in why
    engine, why = W.select(settings.state_dir, environ={W.SWITCH: "claude"})
    assert engine is None and "hermes" in why


def test_the_build_is_found_in_the_named_dir_then_the_repository_then_the_state_dir(no_repo_build, settings, tmp_path, monkeypatch):
    named = fake_build(tmp_path / "named")
    engine, _ = W.select(settings.state_dir, environ={W.SWITCH: "hermes", "LAMPWAY_ENGINES_DIR": str(named)})
    assert engine["dir"].startswith(str(named))
    in_state = fake_build(settings.state_dir / "engines")
    engine, _ = W.select(settings.state_dir, environ={W.SWITCH: "hermes"})
    assert engine["dir"].startswith(str(in_state))
    repo = fake_build(tmp_path / "repo-build")
    monkeypatch.setattr(W, "REPO_ENGINES", repo)
    engine, _ = W.select(settings.state_dir, environ={W.SWITCH: "hermes"})
    assert engine["dir"].startswith(str(repo))


def test_a_server_not_reachable_on_loopback_keeps_the_built_in_loop(no_repo_build, settings, tmp_path):
    settings.host = "192.0.2.10"
    engine, why = W.select(settings.state_dir, environ={W.SWITCH: "hermes", "LAMPWAY_ENGINES_DIR": str(fake_build(tmp_path / "e"))},
                           host=settings.host)
    assert engine is None and "loopback" in why


# ---------------------------------------------------------------------------------------------------- the app with the engine selected
@pytest.fixture
def engine_app(no_repo_build, settings, provider, tmp_path, monkeypatch):
    monkeypatch.setenv(W.SWITCH, "hermes")
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(fake_build(tmp_path / "engines")))
    return create_app(settings, provider=provider)


def test_the_lifespan_starts_the_proxy_and_the_runtime_and_stops_them(engine_app, monkeypatch):
    killed = []
    monkeypatch.setattr(R.EngineRuntime, "kill_all", lambda self: killed.append(self))
    assert engine_app.state.engine_wiring is not None and engine_app.state.agent.engine is None
    with TestClient(engine_app, base_url=BASE):
        rt = engine_app.state.agent.engine
        assert isinstance(rt, R.EngineRuntime)
        assert rt.gateway_url == f"{BASE}/engine/v1" and rt.mcp_url_for("s1") == f"{BASE}/engine/mcp/s1"
        assert rt.proxy_url.startswith("http://127.0.0.1:") and PX._DEFAULT is not None
        assert PX._DEFAULT.gateway_ports == {8787}
        assert rt.config_writer is not None and rt.engine["tag"] == "v0-test"
    assert killed == [rt] and PX._DEFAULT is None


def test_a_childs_model_token_is_the_gateways_and_is_revoked_when_the_child_stops(engine_app):
    with TestClient(engine_app, base_url=BASE):
        rt, reg = engine_app.state.agent.engine, engine_app.state.engine_tokens
        first = rt.model_token_for("s1")
        assert reg.session_for(first) == "s1"
        second = rt.model_token_for("s1")                       # a restarted child: the dead one's token goes
        assert reg.session_for(first) is None and reg.session_for(second) == "s1"
        es = rt._session("s1")
        es.model_token, es.proc = second, SimpleNamespace(returncode=0)
        asyncio.run(rt.stop("s1"))
        assert reg.session_for(second) is None


def test_the_childs_config_is_written_from_the_active_board_and_the_clients_backend_option(engine_app, tmp_path):
    from .fake_client import FakeMixarClient
    with TestClient(engine_app, base_url=BASE) as http:
        fake = FakeMixarClient(http, password="correct-horse")
        fake.login()
        assert fake.put("/app/capabilities/terminal", json={"enabled": True, "options": {"backend": "docker"}}).status_code == 200
        rt = engine_app.state.agent.engine
        home = tmp_path / "state" / "agent" / "hermes" / "s1"
        rt.config_writer(home, rt.gateway_url, "lwe_tok", "lampway")
        text = (home / "config.yaml").read_text()
    assert 'backend: "docker"' in text and '- "terminal"' in text and f'base_url: "{BASE}/engine/v1"' in text
    assert f'url: "{BASE}/engine/v1/models-dev.json"' in text


def test_a_worker_config_drops_what_a_worker_may_never_do(engine_app, tmp_path):
    with TestClient(engine_app, base_url=BASE):
        board = CAP.ACTIVE
        for cid in ("subagents", "schedule", "computer.use", "memory", "swarm", "panes.drive", "messaging.*"):
            board.set(cid, enabled=True, by="user")
        rt = engine_app.state.agent.engine
        scene, worker = tmp_path / "scene", tmp_path / "worker"
        rt.config_writer(scene, rt.gateway_url, "lwe_a", "lampway")
        rt.config_writer(worker, rt.gateway_url, "lwe_b", "lampway", worker=True)
        s, w = (scene / "config.yaml").read_text(), (worker / "config.yaml").read_text()
        view = W.WorkerBoard(board)
        assert not any(view.effective(c)[0] for c in ("subagents", "swarm", "schedule", "panes.drive", "computer.use",
                                                      "messaging.telegram"))
        assert view.effective("memory")[0] and view.setting("subagents")["enabled"] is False
    for toolset in ("delegation", "cronjob", "computer_use"):
        assert f'- "{toolset}"' in s.split("disabled_toolsets")[0] and f'- "{toolset}"' not in w.split("disabled_toolsets")[0]
    assert '- "memory"' in w.split("disabled_toolsets")[0]


# ---------------------------------------------------------------------------------------------------- one child environment
def test_one_child_environment_with_an_empty_managed_dir_and_loopback_only_no_proxy(tmp_path):
    env = R.child_env(tmp_path / "h", "http://127.0.0.1:9999", base_env={"PATH": "/usr/bin", "HERMES_MANAGED_DIR": "/etc/hermes"})
    managed = Path(env["HERMES_MANAGED_DIR"])
    assert managed.is_dir() and not any(managed.iterdir()) and managed.parent == tmp_path / "h"
    assert env["NO_PROXY"] == env["no_proxy"] == "127.0.0.1"
    proxy_vars = PX.child_env(9999)
    assert {k: env[k] for k in proxy_vars} == proxy_vars                       # one source of truth for the proxy variables


# ---------------------------------------------------------------------------------------------------- the gateway's two additions
@pytest.fixture
def gw(settings, provider):
    app = create_app(settings, provider=provider)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000)) as c:
        yield SimpleNamespace(c=c, app=app, reg=app.state.engine_tokens, provider=provider)


def test_models_dev_is_served_on_loopback_as_a_registry_hermes_reads(gw):
    reply = gw.c.get("/engine/v1/models-dev.json")                       # Hermes's models.dev fetch carries no token
    assert reply.status_code == 200
    data = reply.json()
    assert isinstance(data, dict) and data
    provider = data["lampway"]
    assert provider["id"] == "lampway" and provider["env"] == [] and provider["models"]
    for mid, model in provider["models"].items():
        assert model["id"] == mid and model["tool_call"] is True and model["limit"]["context"] > 0
        assert model["modalities"]["input"] == ["text"] and model["cost"] == {"input": 0, "output": 0}
    with TestClient(gw.app, base_url=BASE, client=("192.0.2.7", 50000)) as outside:
        assert outside.get("/engine/v1/models-dev.json").status_code == 403


def _tool(name):
    return {"type": "function", "function": {"name": name, "description": "", "parameters": {"type": "object", "properties": {}}}}


def test_the_first_chat_with_tools_is_checked_and_a_mismatch_refuses_the_session(gw):
    seen = []

    def check(session_id, token, tools):
        seen.append((session_id, [t["function"]["name"] for t in tools]))
        bad = [t["function"]["name"] for t in tools if t["function"]["name"] == "terminal"]
        return f"refused: the engine offered {', '.join(bad)}, which your Capabilities do not allow" if bad else None

    gw.reg.first_check = check
    token = gw.reg.issue_token("s1")
    h = {"Authorization": f"Bearer {token}"}
    msgs = [{"role": "user", "content": "hi"}]
    gw.provider.script = [[Text("title")]]
    assert gw.c.post("/engine/v1/chat/completions", json={"messages": msgs}, headers=h).status_code == 200   # no tools: not the check
    assert seen == []
    refused = gw.c.post("/engine/v1/chat/completions", json={"messages": msgs, "tools": [_tool("mcp__lampway__scene_summary"),
                                                                                            _tool("terminal")]}, headers=h)
    assert refused.status_code == 400
    err = refused.json()["error"]
    assert err["code"] == "engine_tools_mismatch" and "terminal" in err["message"]
    again = gw.c.post("/engine/v1/chat/completions", json={"messages": msgs, "tools": [_tool("mcp__lampway__scene_summary")]}, headers=h)
    assert again.status_code == 400 and len(seen) == 1                    # the session stays refused; checked once
    calls = len(gw.provider.requests)
    ok_token = gw.reg.issue_token("s2")
    gw.provider.script = [[Text("fine")]]
    ok = gw.c.post("/engine/v1/chat/completions", json={"messages": msgs, "tools": [_tool("mcp__lampway__scene_summary")]},
                   headers={"Authorization": f"Bearer {ok_token}"})
    assert ok.status_code == 200 and len(gw.provider.requests) == calls + 1
    gw.c.post("/engine/v1/chat/completions", json={"messages": msgs, "tools": [_tool("terminal")]},
              headers={"Authorization": f"Bearer {ok_token}"})
    assert len(seen) == 2                                                  # only the first request with tools is checked


def test_the_wiring_check_uses_check_advertised_against_the_board_the_config_came_from(engine_app, tmp_path):
    with TestClient(engine_app, base_url=BASE):
        wiring = engine_app.state.engine_wiring
        rt = engine_app.state.agent.engine
        rt.config_writer(tmp_path / "h", rt.gateway_url, "lwe_x", "lampway")
        allowed = [_tool(n) for n in sorted(HC.expected_tools(CAP.ACTIVE, CAP.project()))] + [_tool("mcp__lampway__scene_summary")]
        assert wiring.check("s1", "lwe_x", allowed) is None
        refusal = wiring.check("s1", "lwe_x", allowed + [_tool("terminal")])
        assert refusal and "terminal" in refusal and "Capabilities" in refusal
        CAP.ACTIVE.set("subagents", enabled=True, by="user")
        rt.config_writer(tmp_path / "w", rt.gateway_url, "lwe_w", "lampway", worker=True)
        assert "delegate_task" in wiring.check("w1", "lwe_w", allowed + [_tool("delegate_task")])
        assert wiring.check("s1", "lwe_other", allowed + [_tool("delegate_task")]) is None   # a scene child: subagents is chosen


def test_the_gateway_is_answered_by_a_workers_own_provider_when_the_runtime_names_one(settings, provider):
    agent = SimpleNamespace(provider=provider, engine=None)
    get = W.provider_getter(agent)
    assert get() is provider and get("s1") is provider
    other = object()
    agent.engine = SimpleNamespace(provider_for=lambda sid: other if sid == "w1" else None)
    assert get("w1") is other and get("s1") is provider


def test_idle_children_are_reaped_on_the_tick(engine_app):
    with TestClient(engine_app, base_url=BASE):
        rt = engine_app.state.agent.engine
        reaped = []

        async def reap_idle(now=None):
            reaped.append(now)
            return 0

        rt.reap_idle = reap_idle
        asyncio.run(engine_app.state.engine_wiring.tick())
    assert reaped == [None]
