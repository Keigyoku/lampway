# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Worker deadline configuration and revocation, without a provider or account."""
import asyncio
import time
from types import SimpleNamespace

import pytest

from lampway_server.agent.swarm import SwarmContext, SwarmManager, Worker
from lampway_server import choices as CH, egress as EG
from lampway_server.agent.swarm_brains import WorkerJob
from lampway_server.herdr import swarm_brain as SB
from .test_swarm_v3 import played, run_swarm, marker_play, events
from .worker_choice_support import install_worker_harness


def brain(cockpit=None, **kwargs):
    return SB.PaneBrain(cockpit, "claude", cwd=".", project_root=None, bindings=SB.WorkerBindings(), **kwargs)


def test_environment_sets_worker_timeout_before_a_pane_starts(monkeypatch):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", "91.25")
    assert brain().timeout_s == 91.25


def test_existing_default_is_used_only_without_a_setting(monkeypatch):
    monkeypatch.delenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", raising=False)
    assert brain().timeout_s == 1800.0


@pytest.mark.parametrize("value", ["", "garbage", "nan", "inf", "-inf", "0", "-1"])
def test_invalid_environment_refuses_a_worker_before_start(monkeypatch, value):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", value)
    with pytest.raises(ValueError, match="positive finite"):
        brain()


def test_manager_override_reaches_the_brain_and_wins_over_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", "100")
    install_worker_harness(tmp_path, monkeypatch, "claude")
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    EG.ACTIVE.set_route("byoa:claude", True)
    CH.active_store().set("agent.worker_mode", "global", None, {"preferred": "byoa:claude"}, by="user")
    manager = SwarmManager(None, worker_timeout_s=7.5)
    manager.cockpit = SimpleNamespace(project_root=".")
    pane = manager.worker_brain(SwarmContext(None, "scene", "turn", "call", mode="byoa", harness="codex"))
    assert pane.harness == "claude" and pane.mode_choice.option == "byoa:claude"
    assert pane.timeout_s == 7.5


def test_short_deadline_is_not_delayed_by_the_poll_and_revokes_binding(monkeypatch):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", "0.03")
    monkeypatch.setattr(SB, "POLL_S", 10.0)
    progress = []
    cockpit = SimpleNamespace(create_session=lambda *a, **kw: {"id": "pane-1", "name": "worker pane"},
                              pane_alive=lambda sid: (True, ""))
    worker = Worker("worker-1", "QA", "do work")
    job = WorkerJob(worker, "system", [], None, progress.append, {"swarm_id": "sw1"})
    pane = brain(cockpit)

    async def run():
        with pytest.raises(RuntimeError, match="0.03s.*deadline expired") as error:
            # A bounded wait is the falsifier: the old 10 s poll does not expire in time.
            await asyncio.wait_for(pane.run(job), 1.0)
        assert error.value.code == "worker_timeout"
        assert error.value.timeout_s == 0.03
        assert not pane.bindings.is_live("swarm:sw1:worker-1")
    asyncio.run(run())
    assert any("0.03s deadline" in message for message in progress)
    assert any("expired" in message for message in progress)


def test_completion_before_deadline_stays_successful(monkeypatch):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", "0.1")
    pane = brain()

    def opened(*a, **kw):
        binding = pane.bindings._by_name["swarm:sw1:worker-1"]
        loop.call_soon_threadsafe(pane.bindings.finish, binding, "finished")
        return {"id": "pane-1", "name": "worker pane"}
    pane.cockpit = SimpleNamespace(create_session=opened, pane_alive=lambda sid: (True, ""))

    async def run():
        nonlocal loop
        loop = asyncio.get_running_loop()
        job = WorkerJob(Worker("worker-1", "QA", "do work"), "system", [], None, meta={"swarm_id": "sw1"})
        assert await pane.run(job) == "finished"
        assert not pane.bindings.is_live("swarm:sw1:worker-1")
    loop = None
    asyncio.run(run())


def test_a_slow_liveness_probe_does_not_keep_worker_tools_live_past_expiry(monkeypatch):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", "0.03")
    monkeypatch.setattr(SB, "POLL_S", 0.005)

    def slow_probe(sid):
        time.sleep(0.25)
        return True, ""
    pane = brain(SimpleNamespace(create_session=lambda *a, **kw: {"id": "pane-1", "name": "worker pane"},
                                 pane_alive=slow_probe))

    async def run():
        job = WorkerJob(Worker("worker-1", "QA", "work"), "system", [], None, meta={"swarm_id": "sw1"})
        with pytest.raises(SB.WorkerTimeout):
            await asyncio.wait_for(pane.run(job), 0.1)
        assert not pane.bindings.is_live("swarm:sw1:worker-1")
    asyncio.run(run())


def test_timeout_metadata_reaches_cards_and_only_the_expired_pane_closes(settings, played, monkeypatch):
    monkeypatch.setenv("LAMPWAY_PANE_WORKER_TIMEOUT_S", "0.6")
    captured = {}

    def after(fake, *args):
        captured["worker"] = next(iter(fake.http.app.state.agent.swarm.swarms.values())).workers[0].public()
    _fleet, frames, _s, _c, cockpit, herdr, _p = run_swarm(
        settings, played, ("a", "b"), play=lambda s, w: [("hang",)] if w == "worker-1" else marker_play(s, w), after=after)
    rows = [event["todo"] for event in events(frames) if "todo" in event][-1]
    assert [row["status"] for row in rows] == ["FAILED", "DONE"]
    # swarm_status carries the structured failure, and the card carries its readable reason.
    worker = captured["worker"]
    assert worker["error_code"] == "worker_timeout" and worker["timeout_s"] == 0.6
    assert "deadline expired" in worker["error"]
    hung = next(s for s in cockpit.list_sessions() if s.get("swarm_binding", "").endswith(":worker-1"))
    assert herdr.closed() == [hung["pane_id"]]
