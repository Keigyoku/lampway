# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""An installed worker must refuse an unsupported startup before owned activation."""
import asyncio
from types import SimpleNamespace

import pytest

from lampway_server import choices as CH
from lampway_server import egress as EG
from lampway_server.agent.swarm import SwarmContext, SwarmError, SwarmManager
from lampway_server.choices.snapshot import World, byoa_worker_readiness
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L
from .worker_choice_support import install_worker_harness

REFUSAL = "installed worker startup cannot enforce its MCP admission"


def unsupported(tmp_path, monkeypatch):
    install_worker_harness(tmp_path, monkeypatch, "claude")
    monkeypatch.setenv("LAMPWAY_LOCAL_CLI", "1")
    EG.ACTIVE.set_route("byoa:claude", True)
    adapter = HN.get("claude")
    monkeypatch.setattr(adapter, "worker_ok", True)
    monkeypatch.setattr(adapter, "worker_compatibility_note", lambda: REFUSAL, raising=False)
    store = CH.FileStore(tmp_path / "choices")
    store.set("agent.worker_mode", "global", None, {"preferred": "byoa:claude"}, by="user")
    monkeypatch.setattr(CH, "_STORE", store)
    monkeypatch.setattr(CH, "WORLD_FACTORY", None)
    return adapter


def test_startup_failure_is_visible_without_replacing_saved_choice(tmp_path, monkeypatch):
    unsupported(tmp_path, monkeypatch)
    assert REFUSAL in byoa_worker_readiness().get("byoa:claude", "")
    with pytest.raises(CH.NoChoice, match=REFUSAL):
        CH.resolve("agent.worker_mode", CH.Job(origin="agent"))
    assert CH.preferred("agent.worker_mode") == "byoa:claude"


def test_stale_ready_snapshot_cannot_reach_worker_activation(tmp_path, monkeypatch):
    unsupported(tmp_path, monkeypatch)
    monkeypatch.setattr(CH, "WORLD_FACTORY", lambda: World(routes={"byoa:claude": True}))
    events = []
    async def activate(*args):
        events.append("activate")
        raise AssertionError("unsupported startup reached activation")
    manager = SwarmManager(None)
    manager.cockpit = SimpleNamespace(project_root=str(tmp_path), mode1=object())
    monkeypatch.setattr(manager, "harness_for", lambda socket: SimpleNamespace(activate=activate))
    with pytest.raises(SwarmError, match=REFUSAL):
        asyncio.run(manager._start({"tasks": [{"name": "owned", "prompt": "synthetic"}]},
            SwarmContext(None, "scene", "turn", "call", project_root=str(tmp_path))))
    assert events == [] and manager.swarms == {} and manager._seq == 0


def test_host_refuses_before_pane_files_or_launch(tmp_path, monkeypatch):
    unsupported(tmp_path, monkeypatch)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    cockpit = H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path))
    cockpit.pane_mcp_url = "http://127.0.0.1/api/v1/mcp/pane"
    events = []
    def create(*args):
        events.append("create")
        return {}
    monkeypatch.setattr(cockpit, "_create", create)
    with pytest.raises(H.CockpitError, match=REFUSAL):
        cockpit.create_session("claude", "Owned worker", str(tmp_path), by="swarm",
            prompt="synthetic", swarm_worker=("swarm:one:worker", "synthetic"))
    assert events == [] and not (cockpit.root / "panes").exists()
