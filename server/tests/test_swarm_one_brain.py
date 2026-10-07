# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One worker brain (docs/reports/agent-modes-spec.md S1 and A5, captain 2026-10-07): every swarm worker, in either mode, is a
process in a pane on Lampway's herdr server; no agent runs without a pane.

* ``BuiltinBrain`` (Lampway's own loop), ``EngineBrain`` (hidden Hermes children) and the brain choice are gone; ``PaneBrain`` is
  the only brain.
* The user's saved ``agent.worker_mode`` picks the worker's adapter independently of the parent. The separate ``agent.worker``
  choice retains the API/model chain for Mode 1's ``lampway_hermes``, Lampway's own Hermes pane (A1). Its pane starts only on a server running the Hermes engine (the
  cockpit's ``mode1`` hook); elsewhere a swarm started in Mode 1 is refused with that help before anything runs, never run another
  way. ``EngineRuntime``'s hidden ACP children are gone too (A5): every Mode 1 agent is that pane."""
import asyncio
import importlib.util
import re

import pytest
from starlette.testclient import TestClient

from lampway_server.agent import swarm_brains as SB
from lampway_server import choices as CH, egress as EG
from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet, new_session
from .herdr_support import PaneHerdr
from .worker_choice_support import install_worker_harness

A1 = "Lampway Agent runs on Lampway's pinned Hermes engine (agent-modes spec A1), and this server is not running it"


def test_there_is_one_worker_brain_and_no_agent_without_a_pane():
    for gone in ("BuiltinBrain", "model_round", "MAX_WORKER_ROUNDS", "MODEL_ROUND_TIMEOUT_S"):
        assert not hasattr(SB, gone), f"{gone} is Lampway's own worker loop: removed (spec A5)"
    assert hasattr(SB, "WorkerJob"), "the job, its call_tool door and the brain's protocol stay"
    assert not hasattr(SwarmManager(run_script=None), "brain_for"), "no brain choice: the mode picks the adapter, not the brain"
    assert importlib.util.find_spec("lampway_server.engine.swarm_brain") is None, "EngineBrain's hidden Hermes children are gone"
    assert importlib.util.find_spec("lampway_server.engine.runtime") is None, "EngineRuntime's hidden ACP children are gone (A5)"
    from pathlib import Path
    import lampway_server
    src = "\n".join(p.read_text() for p in Path(lampway_server.__file__).parent.rglob("*.py"))
    assert "from acp" not in src and "import acp" not in src, "nothing in the server speaks ACP"


@pytest.mark.parametrize("worker_mode,expected", [("byoa:codex", "codex"), ("byoa:claude", "claude"),
                                                  ("local:lampway_hermes", "lampway_hermes")])
def test_saved_worker_mode_picks_the_adapter_independently_of_the_parent(tmp_path, monkeypatch, worker_mode, expected):
    model_chain = CH.chain("agent.worker")
    if worker_mode.startswith("byoa:"):
        install_worker_harness(tmp_path, monkeypatch, expected)
        monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
        EG.ACTIVE.set_route(worker_mode, True)
    CH.active_store().set("agent.worker_mode", "global", None, {"preferred": worker_mode}, by="user")
    mgr = SwarmManager(run_script=None)
    mgr.cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path))
    mgr.cockpit.mode1 = object()
    for parent_mode, parent_harness in (("runtime", None), ("runtime", "codex"), ("byoa", "codex"),
                                        ("byoa", "claude"), ("byoa", None)):
        ctx = SwarmContext(None, "scene", "turn", "call", mode=parent_mode, harness=parent_harness)
        brain = mgr.worker_brain(ctx)
        assert brain.harness == expected, "the saved worker mode wins over the parent's mode and harness"
        assert brain.mode_choice.option == worker_mode
    assert CH.chain("agent.worker") == model_chain, "worker mode selection preserves the API/model chain"


def test_lampway_hermes_is_registered_and_refused_with_help_where_the_engine_is_not_running(tmp_path, monkeypatch):
    ad = HN.get("lampway_hermes")
    assert ad.id == "lampway_hermes" and "lampway_hermes" in HN.LAMPWAY_ADAPTERS
    assert "lampway_hermes" not in HN.ids() and "lampway_hermes" not in [r["id"] for r in HN.listing()], \
        "Lampway's own agent is never in the user's Your agent list"
    assert ad.launch(HN.PaneSpec(cwd=str(tmp_path), home=str(tmp_path / "h")), task="Do the thing")[-2:] == ["--home", str(tmp_path / "h")]
    calls = []
    monkeypatch.setattr(L, "run", lambda root, args, **k: calls.append(args) or "")
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(H.CockpitError, match=re.escape(A1)):
        c.create_session("lampway_hermes", "Lampway for a scene tab", str(tmp_path), by="swarm")
    assert calls == [] and c.list_sessions() == [], "herdr is never asked"


def test_the_swarm_manager_builds_a_pane_brain_on_the_saved_workers_adapter(tmp_path, monkeypatch):
    from lampway_server.herdr.swarm_brain import PaneBrain
    mgr = SwarmManager(run_script=None)
    mgr.cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path))
    install_worker_harness(tmp_path, monkeypatch, "codex")
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    EG.ACTIVE.set_route("byoa:codex", True)
    CH.active_store().set("agent.worker_mode", "global", None, {"preferred": "byoa:codex"}, by="user")
    byoa = SwarmContext(socket=None, session_id="scene-1", turn_id="t", call_id="c", mode="byoa", harness="codex", cwd=str(tmp_path))
    brain = mgr.worker_brain(byoa)
    assert isinstance(brain, PaneBrain) and brain.kind == "pane" and brain.harness == "codex" and brain.bindings is mgr.bindings
    CH.active_store().set("agent.worker_mode", "global", None, {"preferred": "local:lampway_hermes"}, by="user")
    with pytest.raises(SwarmError, match=re.escape(A1)):
        mgr.worker_brain(SwarmContext(socket=None, session_id="scene-1", turn_id="t", call_id="c"))     # Mode 1 by default
    mgr.cockpit.mode1 = object()                                           # a server running the engine
    mode1 = mgr.worker_brain(SwarmContext(socket=None, session_id="scene-1", turn_id="t", call_id="c"))
    assert isinstance(mode1, PaneBrain) and mode1.harness == "lampway_hermes"


def test_a_mode1_swarm_start_is_refused_with_the_a1_help_before_anything_runs(tmp_path):
    mgr = SwarmManager(run_script=None)
    mgr.cockpit = H.Cockpit(tmp_path / "herdr")
    asked = []

    class Socket:                                   # the desktop: nothing may be asked of it
        async def request(self, method, params, timeout=None):
            asked.append(method)
            return {"success": True}
    ctx = SwarmContext(socket=Socket(), session_id="scene-1", turn_id="t", call_id="c")
    text, is_error = asyncio.run(mgr.call("swarm_start", {"tasks": [{"name": "boots", "prompt": "Model the boots"}]}, ctx))
    assert is_error and A1 in text and "Your agent" in text, text
    assert asked == [] and mgr.swarms == {}, "no run activated, no worker spawned"


def test_the_in_app_agent_s_swarm_is_refused_in_mode_1_and_nothing_reaches_herdr_or_the_desktop(settings, tmp_path, monkeypatch):
    """The unit's Hermes pane (the scripted serve) calls ``swarm_start`` through its MCP endpoint on a server whose cockpit has no
    Mode 1 hook: refused with A1's help, and nothing runs another way."""
    from lampway_server import capabilities as CAP
    from lampway_server.app import create_app

    from .serve_support import mode1_turn
    herdr = PaneHerdr()
    monkeypatch.setattr(L, "run", herdr)
    (tmp_path / "proj").mkdir()
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj"))
    app = create_app(settings, cockpit=cockpit)
    CAP.ACTIVE.set("swarm", enabled=True, by="user")
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        _, serve = mode1_turn(monkeypatch, http, fake, [("mcp", "swarm_start", {"tasks": [{"name": "boots", "prompt": "Model the boots"}]}),
                                                         ("say", "I could not start the swarm.")], "Split it up", session_id=new_session(),
                              drive=fleet.drive)
        fleet.close()
    result = serve.mcp_results[-1]
    assert result["isError"] and A1 in result["content"][0]["text"], result
    assert [m for m, _ in fleet.requests if m.startswith("agent.")] == [], "no run activated, no worker spawned"
    assert herdr.made() == [] and not [c for c in herdr.calls if c["args"][:2] in (["agent", "start"], ["pane", "run"])]
    assert cockpit.list_sessions() == []
