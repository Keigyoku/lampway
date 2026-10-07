# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One worker brain (docs/reports/agent-modes-spec.md S1 and A5, captain 2026-10-07): every swarm worker, in either mode, is a
process in a pane on Lampway's herdr server; no agent runs without a pane.

* ``BuiltinBrain`` (Lampway's own loop), ``EngineBrain`` (hidden Hermes children) and the brain choice are gone; ``PaneBrain`` is
  the only brain.
* The unit's mode picks the worker's adapter: Mode 2 (a bound pane, or a tab in Your agent mode) the parent pane's harness;
  Mode 1 ``lampway_hermes``, Lampway's own Hermes pane (A1). That adapter is registered but not built: it refuses to launch, so a
  swarm started in Mode 1 is refused with the A1 help before anything runs, never run another way."""
import asyncio
import importlib.util
import re

import pytest
from starlette.testclient import TestClient

from lampway_server.agent import swarm_brains as SB
from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L

from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet, new_session
from .herdr_support import PaneHerdr

A1 = "Lampway's Hermes pane (agent-modes spec A1) is not built yet"


def test_there_is_one_worker_brain_and_no_agent_without_a_pane():
    from lampway_server.engine import runtime as RT
    for gone in ("BuiltinBrain", "model_round", "MAX_WORKER_ROUNDS", "MODEL_ROUND_TIMEOUT_S"):
        assert not hasattr(SB, gone), f"{gone} is Lampway's own worker loop: removed (spec A5)"
    assert hasattr(SB, "WorkerJob"), "the job, its call_tool door and the brain's protocol stay"
    assert not hasattr(SwarmManager(run_script=None), "brain_for"), "no brain choice: the mode picks the adapter, not the brain"
    assert importlib.util.find_spec("lampway_server.engine.swarm_brain") is None, "EngineBrain's hidden Hermes children are gone"
    for gone in ("run_worker", "provider_for"):
        assert not hasattr(RT.EngineRuntime, gone), f"EngineRuntime.{gone} served only the engine's hidden workers"
    assert not {"tool_router", "collector", "worker"} & set(RT.EngineSession.__dataclass_fields__)


def test_the_units_mode_picks_the_workers_adapter():
    assert HN.worker_adapter("byoa", "codex") == "codex", "Mode 2: the parent pane's own harness (Q10)"
    assert HN.worker_adapter("byoa", "claude") == "claude"
    assert HN.worker_adapter("runtime", None) == "lampway_hermes", "Mode 1: Lampway's Hermes pane (A1)"
    assert HN.worker_adapter("runtime", "codex") == "lampway_hermes", "Mode 1 never borrows a user's harness"
    with pytest.raises(ValueError, match="pane"):
        HN.worker_adapter("byoa", None)


def test_lampway_hermes_is_registered_as_a_stub_that_refuses_to_launch(tmp_path, monkeypatch):
    ad = HN.get("lampway_hermes")
    assert ad.id == "lampway_hermes" and "lampway_hermes" in HN.LAMPWAY_ADAPTERS
    assert "lampway_hermes" not in HN.ids() and "lampway_hermes" not in [r["id"] for r in HN.listing()], \
        "Lampway's own agent is never in the user's Your agent list"
    with pytest.raises(ValueError, match=re.escape(A1)):
        ad.launch(HN.PaneSpec(cwd=str(tmp_path)), task="Do the thing")
    with pytest.raises(ValueError, match=re.escape(A1)):
        HN.require_launchable("lampway_hermes")
    HN.require_launchable("claude")                                        # a user's harness is not refused here
    calls = []
    monkeypatch.setattr(L, "run", lambda root, args, **k: calls.append(args) or "")
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    c = H.Cockpit(tmp_path / "herdr")
    with pytest.raises(H.CockpitError, match=re.escape(A1)):
        c.create_session("lampway_hermes", "Lampway for a scene tab", str(tmp_path), by="swarm")
    assert calls == [] and c.list_sessions() == [], "herdr is never asked"


def test_the_swarm_manager_builds_a_pane_brain_on_the_units_adapter(tmp_path):
    from lampway_server.herdr.swarm_brain import PaneBrain
    mgr = SwarmManager(run_script=None)
    mgr.cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path))
    byoa = SwarmContext(socket=None, session_id="scene-1", turn_id="t", call_id="c", mode="byoa", harness="codex", cwd=str(tmp_path))
    brain = mgr.worker_brain(byoa)
    assert isinstance(brain, PaneBrain) and brain.kind == "pane" and brain.harness == "codex" and brain.bindings is mgr.bindings
    with pytest.raises(SwarmError, match=re.escape(A1)):
        mgr.worker_brain(SwarmContext(socket=None, session_id="scene-1", turn_id="t", call_id="c"))     # Mode 1 by default


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
    from lampway_server import capabilities as CAP
    from lampway_server.agent.providers.mock import ScriptedProvider
    from lampway_server.app import create_app
    herdr = PaneHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    (tmp_path / "proj").mkdir()
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj"))
    provider = ScriptedProvider([[ToolCall(id="s1", name="swarm_start", arguments={"tasks": [{"name": "boots", "prompt": "Model the boots"}]})],
                                 [Text("I could not start the swarm.")]])
    app = create_app(settings, provider=provider, cockpit=cockpit)
    CAP.ACTIVE.set("swarm", enabled=True, by="user")
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            cmd = fake.command(ws, "chat", fake.chat_payload("Split it up", new_session()))
            fleet.drive(ws, cmd)
        fleet.close()
    result = next(p for m in provider.requests[1].messages for p in m.content if p.get("type") == "tool_result")
    assert result["is_error"] and A1 in result["content"], result
    assert [m for m, _ in fleet.requests if m.startswith("agent.")] == [], "no run activated, no worker spawned"
    assert herdr.made() == [] and not [c for c in herdr.calls if c["args"][:2] in (["agent", "start"], ["pane", "run"])]
    assert cockpit.list_sessions() == []
