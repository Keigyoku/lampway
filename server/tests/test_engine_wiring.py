# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine in production (docs/reports/agent-modes-spec.md A1-A3, E1.3-E1.5, E1.3's start-up check): how ``create_app`` puts
Hermes in Mode 1's seat, every agent a pane. No engine runs here (a stand-in build is enough to select one); the live turns are
test_engine_pane_live.py."""

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
from lampway_server.engine import wiring as W
from lampway_server.engine.front import HermesFront
from lampway_server.engine.units import Mode1Units

from .mode1_support import fake_engine, mcp_entry

BASE = "http://127.0.0.1:8787"


def fake_build(root: Path) -> Path:
    fake_engine(root)
    return root


def test_find_engine_reads_only_finished_builds(tmp_path):
    assert W.find_engine(tmp_path) is None
    unfinished = tmp_path / "hermes" / "v1"
    unfinished.mkdir(parents=True)
    assert W.find_engine(tmp_path) is None
    (unfinished / "engine.json").write_text('{"engine": "hermes", "tag": "v1", "entry": "env/bin/hermes", "source": "src"}')
    found = W.find_engine(tmp_path)
    assert found["tag"] == "v1" and found["entry_path"] == str(unfinished / "env/bin/hermes")


@pytest.fixture
def no_repo_build(monkeypatch, tmp_path):
    monkeypatch.setattr(W, "REPO_ENGINES", tmp_path / "no-repo-build")
    monkeypatch.delenv("LAMPWAY_ENGINES_DIR", raising=False)


# ---------------------------------------------------------------------------------------------------- selection
def test_without_a_build_mode1_is_unavailable_and_the_hub_is_told_why_and_how_to_build_it(no_repo_build, settings, tmp_path, caplog):
    engine, why = W.select(settings.state_dir, environ={"LAMPWAY_ENGINES_DIR": str(tmp_path / "empty")})
    assert engine is None and why.code == "engine_not_built" and str(tmp_path / "empty") in why.why
    assert "scripts/lampway/engine_env.py" in why.fix
    with caplog.at_level(logging.INFO, logger="lampway.engine"):
        app = create_app(settings)
    assert app.state.engine_wiring is None and app.state.agent.engine is None
    assert app.state.agent.engine_problem[0] == "engine_not_built"
    assert [r for r in caplog.records if "Mode 1 is unavailable" in r.getMessage() and "engine_env.py" in r.getMessage()]


def test_the_retired_switch_is_not_read_and_a_server_that_finds_it_says_so(no_repo_build, settings, tmp_path, caplog, monkeypatch):
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(fake_build(tmp_path / "engines")))
    for value in ("off", "claude", "hermes"):
        monkeypatch.setenv(W.RETIRED_SWITCH, value)
        caplog.clear()
        with caplog.at_level(logging.INFO, logger="lampway.engine"):
            app = create_app(settings)
        assert app.state.engine_wiring is not None, f"{W.RETIRED_SWITCH}={value} changed nothing"
        assert [r for r in caplog.records if W.RETIRED_SWITCH in r.getMessage() and "no longer read" in r.getMessage()]


def test_the_build_is_found_in_the_named_dir_then_the_repository_then_the_state_dir(no_repo_build, settings, tmp_path, monkeypatch):
    named = fake_build(tmp_path / "named")
    engine, _ = W.select(settings.state_dir, environ={"LAMPWAY_ENGINES_DIR": str(named)})
    assert engine["dir"].startswith(str(named))
    in_state = fake_build(settings.state_dir / "engines")
    engine, _ = W.select(settings.state_dir, environ={})
    assert engine["dir"].startswith(str(in_state))
    repo = fake_build(tmp_path / "repo-build")
    monkeypatch.setattr(W, "REPO_ENGINES", repo)
    engine, _ = W.select(settings.state_dir, environ={})
    assert engine["dir"].startswith(str(repo))


def test_a_server_not_reachable_on_loopback_cannot_run_mode1_and_says_so(no_repo_build, settings, tmp_path):
    settings.host = "192.0.2.10"
    engine, why = W.select(settings.state_dir, environ={"LAMPWAY_ENGINES_DIR": str(fake_build(tmp_path / "e"))}, host=settings.host)
    assert engine is None and why.code == "engine_unavailable" and "loopback" in why.why and "LAMPWAY_HOST" in why.fix


# ---------------------------------------------------------------------------------------------------- the app with the engine selected
@pytest.fixture
def engine_app(no_repo_build, settings, provider, tmp_path, monkeypatch):
    import sys
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(fake_build(tmp_path / "engines")))
    monkeypatch.setenv("LAMPWAY_NODE", sys.executable)                     # a stand-in Node: nothing runs it here
    return create_app(settings, provider=provider)


def test_the_lifespan_starts_the_proxy_and_the_panes_front_and_stops_them_ending_no_pane(engine_app, monkeypatch):
    killed = []
    import os
    monkeypatch.setattr(os, "kill", lambda pid, sig: killed.append(pid))
    monkeypatch.setattr(os, "killpg", lambda pid, sig: killed.append(pid))
    assert engine_app.state.engine_wiring is not None and engine_app.state.agent.engine is None
    cockpit = engine_app.state.agent.cockpit
    with TestClient(engine_app, base_url=BASE):
        front, wiring = engine_app.state.agent.engine, engine_app.state.engine_wiring
        assert isinstance(front, HermesFront) and isinstance(front.units, Mode1Units) and cockpit.mode1 is front.units
        assert front.units.gateway_url == f"{BASE}/engine/v1" and front.units.base == BASE
        assert PX._DEFAULT is not None and PX._DEFAULT.gateway_ports == {8787}
        port = PX._DEFAULT._server.sockets[0].getsockname()[1]
        assert front.units.proxy_vars["HTTPS_PROXY"] == f"http://127.0.0.1:{port}" and front.units.proxy_vars["NO_PROXY"] == "127.0.0.1"
        assert front.units.engine["tag"] == "v0-test"
    assert engine_app.state.agent.engine is None and cockpit.mode1 is None and PX._DEFAULT is None
    assert killed == [], "shutdown ends no pane and no serve: they outlive the server (law 5, A1)"


def test_the_proxy_keeps_its_port_across_a_restart_so_panes_that_outlived_the_server_still_reach_it(engine_app, settings):
    with TestClient(engine_app, base_url=BASE):
        first = PX._DEFAULT._server.sockets[0].getsockname()[1]
    again = create_app(settings)
    again.state.engine_wiring = W.EngineWiring(engine_app.state.engine_wiring.engine, settings=settings, agent=again.state.agent,
                                               registry=again.state.engine_tokens)
    asyncio.run(_start_stop(again.state.engine_wiring))
    assert again.state.engine_wiring.proxy_port_seen == first


async def _start_stop(wiring):
    await wiring.start()
    wiring.proxy_port_seen = PX._DEFAULT._server.sockets[0].getsockname()[1]
    await wiring.stop()


def test_a_panes_model_token_is_the_gateways_and_dies_when_its_prepare_is_abandoned(engine_app):
    with TestClient(engine_app, base_url=BASE):
        units, reg = engine_app.state.agent.engine.units, engine_app.state.engine_tokens
        first = units.prepare(rid="r1", unit="s1", role="main", cwd="/proj", project_root="/proj")
        token = next(ln.split('"')[1] for ln in (Path(first["home"]) / "config.yaml").read_text().splitlines() if ln.startswith("  api_key:"))
        assert reg.session_for(token) == "s1" and token.startswith("lwe_")
        second = units.prepare(rid="r2", unit="s1", role="main", cwd="/proj", project_root="/proj")      # a reopened pane
        token2 = second["_gateway_token"]
        assert reg.session_for(token) is None and reg.session_for(token2) == "s1", "one live key per pane"
        units.abandon(second)
        assert reg.session_for(token2) is None


def test_the_panes_config_is_written_from_the_active_board_and_the_clients_backend_option(engine_app, tmp_path):
    from .fake_client import FakeMixarClient
    with TestClient(engine_app, base_url=BASE) as http:
        fake = FakeMixarClient(http, password="correct-horse")
        fake.login()
        assert fake.put("/app/capabilities/terminal", json={"enabled": True, "options": {"backend": "docker"}}).status_code == 200
        wiring = engine_app.state.engine_wiring
        home = tmp_path / "state" / "agent" / "hermes" / "s1"
        wiring.write_config(home, f"{BASE}/engine/v1", "lwe_tok", "lampway", mcp_url=f"{BASE}/engine/mcp/s1",
                            mcp_headers={"Authorization": "Bearer b"})
        text = (home / "config.yaml").read_text()
    assert 'backend: "docker"' in text and '- "terminal"' in text and f'base_url: "{BASE}/engine/v1"' in text
    assert f'url: "{BASE}/engine/v1/models-dev.json"' in text
    assert mcp_entry(home) == (f"{BASE}/engine/mcp/s1", {"Authorization": "Bearer b"})


def test_a_worker_config_drops_what_a_worker_may_never_do(engine_app, tmp_path):
    with TestClient(engine_app, base_url=BASE):
        board = CAP.ACTIVE
        for cid in ("subagents", "schedule", "computer.use", "memory", "swarm", "panes.drive", "messaging.*"):
            board.set(cid, enabled=True, by="user")
        wiring = engine_app.state.engine_wiring
        scene, worker = tmp_path / "scene", tmp_path / "worker"
        wiring.write_config(scene, f"{BASE}/engine/v1", "lwe_a", "lampway")
        wiring.write_config(worker, f"{BASE}/engine/v1", "lwe_b", "lampway", worker=True)
        s, w = (scene / "config.yaml").read_text(), (worker / "config.yaml").read_text()
        view = W.WorkerBoard(board)
        assert not any(view.effective(c)[0] for c in ("subagents", "swarm", "schedule", "panes.drive", "computer.use",
                                                      "messaging.telegram"))
        assert view.effective("memory")[0] and view.setting("subagents")["enabled"] is False
    for toolset in ("delegation", "cronjob", "computer_use"):
        assert f'- "{toolset}"' in s.split("disabled_toolsets")[0] and f'- "{toolset}"' not in w.split("disabled_toolsets")[0]
    assert '- "memory"' in w.split("disabled_toolsets")[0]
    assert '- "clarify"' in s.split("disabled_toolsets")[0] and '- "clarify"' not in w.split("disabled_toolsets")[0], \
        "a worker never asks the user (S2)"


# ---------------------------------------------------------------------------------------------------- one pane environment
def test_a_panes_proxy_variables_are_the_proxys_one_source(engine_app, tmp_path):
    with TestClient(engine_app, base_url=BASE):
        units = engine_app.state.agent.engine.units
        prepared = units.prepare(rid="r1", unit="s1", role="main", cwd="/proj", project_root="/proj")
        spec = json.loads((Path(prepared["home"]) / "pane.json").read_text())
        port = PX._DEFAULT._server.sockets[0].getsockname()[1]
        assert spec["env"] == PX.child_env(port), "one source of truth for the proxy variables: NO_PROXY the gateway's loopback host"
        managed = Path(prepared["home"]) / "managed"
        assert managed.is_dir() and not any(managed.iterdir()), "an empty managed dir: no /etc/hermes overrides the config"


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
        wiring.write_config(tmp_path / "h", f"{BASE}/engine/v1", "lwe_x", "lampway")
        allowed = [_tool(n) for n in sorted(HC.expected_tools(CAP.ACTIVE, CAP.project()))] + [_tool("mcp__lampway__scene_summary")]
        assert wiring.check("s1", "lwe_x", allowed) is None
        assert wiring.check("s1", "lwe_x", allowed + [_tool("clarify")]) is None, "a main agent asks the island (A2)"
        refusal = wiring.check("s1", "lwe_x", allowed + [_tool("terminal")])
        assert refusal and "terminal" in refusal and "Capabilities" in refusal
        CAP.ACTIVE.set("subagents", enabled=True, by="user")
        wiring.write_config(tmp_path / "w", f"{BASE}/engine/v1", "lwe_w", "lampway", worker=True)
        assert "delegate_task" in wiring.check("w1", "lwe_w", allowed + [_tool("delegate_task")])
        assert "clarify" in wiring.check("w1", "lwe_w", allowed + [_tool("clarify")]), "a worker never asks (S2)"
        assert wiring.check("s1", "lwe_other", allowed + [_tool("delegate_task")]) is None   # a scene pane: subagents is chosen


CHAT = "/engine/v1/chat/completions"


def _ask(http, token, text="hello"):
    r = http.post(CHAT, json={"messages": [{"role": "user", "content": text}]}, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200, r.text
    return r.json()["choices"][0]["message"]["content"]


def test_a_mode1_workers_gateway_calls_are_answered_by_the_worker_choice_and_the_main_session_by_the_main_provider(settings):
    """Spec S2 (as superseded by A): a Mode 1 worker's pane thinks through the gateway on the ``agent.worker`` choice, not on the main
    agent's provider. The gateway tells them apart by the token's session: a worker pane's token is keyed by its swarm binding
    (``Mode1Units.prepare``), a main pane's by its unit. The worker's provider is built once, at its first call (HC23: never
    mid-turn), and only for workers."""
    from lampway_server.agent.providers.mock import ScriptedProvider
    main = ScriptedProvider([[Text("main says hi")], [Text("main again")]])
    worker = ScriptedProvider([[Text("worker 1 says hi")], [Text("worker 1 again")], [Text("worker 2 says hi")]])
    built = []
    app = create_app(settings, provider=main, swarm_provider_factory=lambda label: built.append(label) or worker)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000)) as http:
        reg = app.state.engine_tokens
        unit, w1, w2 = reg.issue_token("scene-1"), reg.issue_token("swarm:sw1:worker-1"), reg.issue_token("swarm:sw1:worker-2")
        assert _ask(http, unit) == "main says hi"
        assert _ask(http, w1) == "worker 1 says hi"
        assert _ask(http, w1) == "worker 1 again"
        assert _ask(http, w2) == "worker 2 says hi"
        assert _ask(http, unit) == "main again"
    assert len(main.requests) == 2 and len(worker.requests) == 3, "each pane was answered by its own choice, never the other's"
    assert built == ["worker-1", "worker-2"], "one worker provider per worker pane, built at its first call"


def test_with_no_worker_choice_a_mode1_worker_follows_the_main_agent(settings):
    """The documented default (Choices registry and bridge): with no ``agent.worker`` choice and no swarm provider set, the chain is
    ``follow:agent.main``: the worker is answered by a provider like the main one (``make_swarm_provider``); with a provider handed
    to the app and no worker factory, by the current main provider itself."""
    from lampway_server.agent.providers.mock import ScriptedProvider
    from lampway_server.choices.bridge import chains
    assert chains(settings)["agent.worker"]["preferred"] == "follow:agent.main"
    app = create_app(settings)                                       # the configured providers: mock, no worker choice
    get = W.provider_getter(app.state.agent)
    assert get("swarm:sw1:worker-1").name == get("scene-1").name == "mock"
    main = ScriptedProvider([[Text("main answers the worker")]])
    app = create_app(settings, provider=main)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000)) as http:
        assert _ask(http, app.state.engine_tokens.issue_token("swarm:sw1:worker-1")) == "main answers the worker"


def test_the_providers_dialogs_swarm_model_is_the_answer_the_gateway_gives_a_mode1_worker(settings, monkeypatch):
    """One answer for the workers: the Providers dialog's swarm choice is written to Choices' ``agent.worker`` (step 9), Choices
    sets the settings ``make_swarm_provider`` reads, and that factory is what the gateway asks for a worker pane. Which wins: the
    environment (``LAMPWAY_SWARM_PROVIDER`` and its models, a session scope), then ``agent.worker`` in Choices (the dialog and
    the model picker both write it), then the default ``follow:agent.main``."""
    from lampway_server import provider_prefs as PP
    from .fake_client import FakeMixarClient
    for k in PP.ENV_VARS.values():
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-" "or-v1-" + "1f2e" * 16)
    app = create_app(settings)
    with TestClient(app, base_url=BASE) as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        get = W.provider_getter(app.state.agent)
        assert get("swarm:sw1:worker-1").name == "mock", "before the choice: the worker follows the main agent"
        r = fake.put("/app/provider-settings", json={"values": {"swarm_provider": "openrouter",
                                                                "openrouter_swarm_model": "deepseek/deepseek-v4.1-flash"}})
        assert r.status_code == 200, r.text
        worker = get("swarm:sw2:worker-1")                                # a worker of the next swarm: built at its first call
        assert worker.name == "openrouter" and worker.model == "deepseek/deepseek-v4.1-flash"
        assert get("scene-1").name == "mock", "the main pane keeps the main provider"
        assert get("swarm:sw1:worker-1").name == "mock", "a worker already answered keeps its provider for its life"


def test_a_worker_choice_that_cannot_be_built_is_an_openai_error_not_the_main_provider(settings):
    """The gateway never answers a worker with another provider than its choice: a worker choice that cannot be built (no key) is an
    OpenAI-style error for that pane, and the main session is still answered."""
    from lampway_server.agent.providers.mock import ScriptedProvider
    main = ScriptedProvider([[Text("main is fine")]])

    def factory(label):
        raise ValueError("no OpenRouter key is connected for the swarm workers")
    app = create_app(settings, provider=main, swarm_provider_factory=factory)
    with TestClient(app, base_url=BASE, client=("127.0.0.1", 50000)) as http:
        reg = app.state.engine_tokens
        r = http.post(CHAT, json={"messages": [{"role": "user", "content": "hi"}]},
                      headers={"Authorization": f"Bearer {reg.issue_token('swarm:sw1:worker-1')}"})
        assert r.status_code >= 400 and "OpenRouter key" in r.json()["error"]["message"]
        assert _ask(http, reg.issue_token("scene-1")) == "main is fine"
    assert len(main.requests) == 1


def test_the_gateway_is_answered_by_the_current_main_provider(settings, provider):
    """The engine's hidden swarm workers, with a provider of their own, are gone (spec A5): every pane is answered by the current
    main provider, whatever its session."""
    agent = SimpleNamespace(provider=provider, engine=None)
    get = W.provider_getter(agent)
    assert get() is provider and get("s1") is provider
    other = object()
    agent.engine = SimpleNamespace(provider_for=lambda sid: other)
    assert get("w1") is provider and get("s1") is provider
    agent.provider = other
    assert get("s1") is other, "the provider is read at call time, not captured"


def test_the_tick_ends_no_pane(engine_app, monkeypatch):
    """Nothing is reaped: every agent is a pane, and a pane ends only by the user (A0, law 5)."""
    with TestClient(engine_app, base_url=BASE):
        cockpit = engine_app.state.agent.cockpit
        asked = []
        monkeypatch.setattr(cockpit, "close_session", lambda *a, **k: asked.append(a))
        monkeypatch.setattr(cockpit, "end_swarm_pane", lambda *a, **k: asked.append(a))
        asyncio.run(engine_app.state.engine_wiring.tick())
    assert asked == []


def test_the_engine_config_says_whether_the_model_sees_images(settings, provider):
    """R3/R0a: Hermes sends images only to a model it knows sees them; Lampway says so per provider."""
    from types import SimpleNamespace
    from lampway_server.engine import hermes_config as HC
    from lampway_server.engine.wiring import sees_images

    class Store:
        def __init__(self, byok):
            self._b = byok

        def byok(self):
            return self._b

    agent = lambda name, byok=None: SimpleNamespace(provider=SimpleNamespace(name=name), settings_store=Store(byok))  # noqa: E731
    assert sees_images(agent("anthropic")) is True
    assert sees_images(agent("chatgpt_plan")) is False                      # until the R0a vision probe is recorded
    assert sees_images(agent("openai", {"supports_vision": False})) is False
    assert sees_images(agent("openai", {"supports_vision": True})) is True
    assert sees_images(agent("openrouter")) is None and sees_images(agent("openai", None)) is None
    from lampway_server import capabilities as CAP
    board = CAP.Store(settings.state_dir)
    seen = HC.render(board, None, "http://127.0.0.1:8787/engine/v1", "tok", "m", supports_vision=True)
    unknown = HC.render(board, None, "http://127.0.0.1:8787/engine/v1", "tok", "m")
    assert seen["model"]["supports_vision"] is True and "supports_vision" not in unknown["model"]
