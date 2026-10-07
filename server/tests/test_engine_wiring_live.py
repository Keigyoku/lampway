# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine in production, live (docs/reports/agent-modes-spec.md E1.2-E1.6): ``create_app`` with ``LAMPWAY_AGENT_ENGINE=hermes``
puts the REAL pinned Hermes in Mode 1's seat, with nothing attached by hand. One chat turn from the client calls ``scene_summary``
through the engine and ends with the main provider's text, which proves:

* the engine's model is Lampway's gateway, answered by the app's main provider (a scripted one: no network, no spend);
* its way out is Lampway's egress proxy, which let nothing leave (no ``send`` row for a host off this machine);
* its config came from ``hermes_config`` (the written config.yaml is exactly what ``render`` makes from the active board);
* its tools passed E1.3's start-up check on the first request that carried them.

Needs a built engine (``scripts/lampway/engine_env.py``: ``$LAMPWAY_ENGINES_DIR``, or ``build/engines`` in this checkout or one
above it) and the ACP SDK. Without them the test SKIPS, and a skip is not a pass. It starts one engine child (~20 s cold)."""

import asyncio
import json
import os
import re
import uuid
from pathlib import Path

import pytest

from lampway_server import capabilities as CAP
from lampway_server import egress as EG
from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.engine import hermes_config as HC
from lampway_server.engine import wiring as W
from lampway_server.engine.runtime import find_engine


def _engines_dir():
    given = os.environ.get("LAMPWAY_ENGINES_DIR")
    candidates = [Path(given)] if given else [p / "build" / "engines" for p in Path(__file__).resolve().parents]
    return next((c for c in candidates if find_engine(c) is not None), None)


ENGINES = _engines_dir()
try:
    import acp  # noqa: F401
    ACP_MISSING = None
except ImportError as exc:  # pragma: no cover - depends on the environment
    ACP_MISSING = f"the ACP SDK (agent-client-protocol) is not importable: {exc}"

pytestmark = [pytest.mark.skipif(ENGINES is None, reason="no built engine (LAMPWAY_ENGINES_DIR or build/engines): run "
                                                         "scripts/lampway/engine_env.py"),
              pytest.mark.skipif(ACP_MISSING is not None, reason=ACP_MISSING or ""),
              pytest.mark.timeout(400)]

FULL = "mcp__lampway__scene_summary"
SCENE = {"success": True, "scene": "Scene", "object_count": 1, "objects": [{"name": "Cube", "type": "MESH"}]}


class EngineTurnProvider(ScriptedProvider):
    """The app's main provider, scripted by what the engine sends: a request with no tools is Hermes's auxiliary call (a title);
    the turn's first request calls ``scene_summary`` (directly when visible, else through Hermes's ``tool_call`` bridge); once a
    tool result is in the conversation it answers."""

    name = "scripted-engine"
    ANSWER = "There is one cube."

    async def stream(self, request):
        self.requests.append(request)
        names = [t.name for t in request.tools]
        if not names:
            yield Text("Scene question")
            return
        if not any(p.get("type") == "tool_result" for m in request.messages for p in m.content):
            if FULL in names:
                yield ToolCall(id="call_1", name=FULL, arguments={})
            else:
                yield ToolCall(id="call_1", name="tool_call", arguments={"calls": [{"name": FULL, "arguments": {}}]})
            return
        yield Text(self.ANSWER)


@pytest.fixture
def live_stack(settings, tmp_path, monkeypatch):
    from .test_engine_conformance import free_port
    import threading
    import time
    import uvicorn
    from lampway_server.app import create_app
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setenv(W.SWITCH, "hermes")
    monkeypatch.setenv("LAMPWAY_ENGINES_DIR", str(ENGINES))
    monkeypatch.setenv("LAMPWAY_PROJECT_ROOT", str(project))
    settings.port = free_port()
    strict = EG.Egress(tmp_path / "strict-egress")                    # a fresh install: every route off
    provider = EngineTurnProvider()
    app = create_app(settings, provider=provider, egress=strict)
    assert app.state.engine_wiring is not None, "create_app did not select the engine"
    checks = []
    original = app.state.engine_tokens.first_check

    def recorded(session_id, token, tools):
        verdict = original(session_id, token, tools)
        checks.append((session_id, [t["function"]["name"] for t in tools], verdict))
        return verdict

    app.state.engine_tokens.first_check = recorded
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=settings.port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)

    def stop():
        server.should_exit = True
        thread.join(timeout=60)

    yield {"app": app, "base": f"http://127.0.0.1:{settings.port}", "settings": settings, "provider": provider, "egress": strict,
           "checks": checks, "project": project, "stop": stop}
    stop()


def test_create_app_with_the_switch_runs_a_tool_turn_through_the_real_engine(live_stack):
    from .test_engine_conformance import _login, _turn
    import websockets
    st = live_stack
    fake = _login(st["base"], st["settings"])
    ws_url = st["base"].replace("http://", "ws://") + f"/api/agent/ws/{fake.instance_id}"
    sid = str(uuid.uuid4())
    scripts = []

    async def go():
        headers = {"Authorization": f"Bearer {fake.access_token}", "x-telemetry-consent": "1", "X-Mixar-Locale": "en_US"}
        async with websockets.connect(ws_url, additional_headers=headers, open_timeout=10, max_size=None) as ws:
            await ws.send(json.dumps(fake.handshake_frame()))
            json.loads(await asyncio.wait_for(ws.recv(), 10))
            events, _ = await _turn(ws, "agent.chat", fake.chat_payload("What is in my scene?", sid),
                                    lambda p: (scripts.append(p["script"]), SCENE)[1], timeout=300)
            rt = st["app"].state.agent.engine
            return events, rt

    events, rt = asyncio.run(go())
    provider = st["provider"]

    # the gateway, not a fake model, answered the engine: the app's own provider saw the turn, offered Lampway's tool, and the
    # tool's result came back to it from Blender
    assert rt is not None and rt.gateway_url == f"{st['base']}/engine/v1"
    turns = [r for r in provider.requests if r.tools]
    assert turns, f"the main provider never saw the engine's turn ({len(provider.requests)} requests)"
    offered = {t.name for t in turns[0].tools}
    assert FULL in offered or "tool_call" in offered, sorted(offered)
    assert scripts, "the engine's tool call never reached Blender"
    results = [p for r in turns for m in r.messages for p in m.content if p.get("type") == "tool_result"]
    assert results and "Cube" in str(results[0]["content"])
    final = [e for e in events if (e.get("content") or {}).get("set")]
    assert final and final[-1]["content"]["set"] == EngineTurnProvider.ANSWER
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "completed"

    # E1.3's start-up check ran on the first request with tools, and passed
    assert len(st["checks"]) == 1 and st["checks"][0][0] == sid and st["checks"][0][2] is None, st["checks"]

    # the proxy let nothing leave: no send row at all, every attempt a refusal row naming the engine proxy
    rows = st["egress"].log()
    assert not [r for r in rows if r.get("event") == "send"], rows
    tried = sorted({r["provider"] for r in rows if r.get("via") == "engine_proxy"})
    print(f"\n[live wiring] hosts the engine tried and the proxy refused: {tried}")

    # the child's config came from hermes_config, from the active board and project
    home = Path(st["settings"].state_dir) / "agent" / "hermes" / sid
    text = (home / "config.yaml").read_text()
    token = re.search(r'^  api_key: "([^"]+)"$', text, re.M).group(1)
    assert token.startswith("lwe_")
    expected = HC.to_yaml(HC.render(CAP.ACTIVE, str(st["project"]), f"{st['base']}/engine/v1", token, W.MODEL_ID))
    assert text == expected
    assert f'url: "{st["base"]}/engine/v1/models-dev.json"' in text
    assert (home / "managed").is_dir() and not any((home / "managed").iterdir())
    cache = home / "models_dev_cache.json"                   # if Hermes read models.dev, it read it from the gateway
    if cache.exists():
        assert list(json.loads(cache.read_text())) == ["lampway"]
    print(f"[live wiring] model requests {len(provider.requests)} (with tools {len(turns)}); tool call "
          f"{'direct' if FULL in offered else 'through the tool_call bridge'}; checked tools {st['checks'][0][1]}; "
          f"models.dev cache from the gateway: {cache.exists()}")
    # the server's shutdown stops the child (the lifespan's kill_all and stop) and its key dies with it
    es = rt.sessions[sid]
    pid = es.proc.pid
    st["stop"]()
    assert es.proc is None and st["app"].state.agent.engine is None
    assert st["app"].state.engine_tokens.session_for(token) is None
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)
