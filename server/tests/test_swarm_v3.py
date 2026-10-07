"""The swarm on the client's own harness (v3): every worker is its own headless process, results enter the user's scene only through
the typed append_collection commit, and the Parallel Agents panel is fed by the chat's todo slot. The parent and the workers are
the fake fleet in fake_harness.py.

Every worker thinks in a pane (``PaneBrain``, spec S1 and A5: no agent without a pane). These tests start the swarm from the in-app
agent, i.e. in Mode 1, whose worker adapter is ``lampway_hermes`` (A1). That adapter is not built yet, so here a played stand-in
takes its place in the adapter registry (``PlayedHermes``: herdr starts it the way it starts Claude Code), and ``PanePlayer`` plays
each worker pane the way a harness would: its tool calls over the pane endpoint, then ``lampway_worker_done``. herdr is played
(``herdr_support.PaneHerdr``); no binary runs and nothing leaves the machine."""

import json
import threading
import time
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.app import create_app
from lampway_server.herdr import harnesses as HN
from lampway_server.herdr import host as H
from lampway_server.herdr import launcher as L
from lampway_server.herdr.harnesses.claude import Claude

from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet, new_session
from .herdr_support import PaneHerdr


class PlayedHermes(Claude):
    """A stand-in for Lampway's Hermes pane (agent-modes spec A1), which another lane builds: herdr starts it like Claude Code."""
    id = "lampway_hermes"
    label = "Lampway's agent (played)"
    built = True

    @property
    def route(self) -> str:
        return "byoa:claude"


def marker_play(swarm_id, worker_id):
    """What a worker's harness does by default: one marked script in its own scene, then its summary."""
    n = worker_id.split("-")[1]
    return [("call", "run_blender_python", {"script": f"import bpy\n# by {worker_id}\n# collection QA_candidates w{n}_L000,w{n}_label\n"}),
            ("done", f"w{n} drew its markers")]


class PanePlayer:
    """Plays every worker pane the swarm opens, as its harness would. ``play(swarm_id, worker_id)`` returns the steps:
    ``("call", tool, arguments)``, ``("done", summary)``, ``("exit",)`` (the harness quits) or ``("hang",)`` (it never finishes)."""

    def __init__(self, http, cockpit, herdr, play):
        self.http, self.cockpit, self.herdr, self.play = http, cockpit, herdr, play
        self.seen, self.results = set(), {}
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._watch, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *exc):
        self.stop.set()
        self.thread.join(5)

    def _watch(self):
        while not self.stop.is_set():
            for rec in self.cockpit.list_sessions():
                if rec.get("created_by") == "swarm" and rec["id"] not in self.seen:
                    self.seen.add(rec["id"])
                    threading.Thread(target=self._play, args=(rec,), daemon=True).start()
            time.sleep(0.02)

    def _play(self, rec):
        _, swarm_id, worker_id = rec["swarm_binding"].split(":")
        entry = json.loads(Path(rec["mcp_config_path"]).read_text())["mcpServers"]["lampway"]
        for step in self.play(swarm_id, worker_id):
            if step[0] == "exit":
                self.herdr.exit(rec["pane_id"])
                return
            if step[0] == "hang":
                return
            name, arguments = (step[1], step[2]) if step[0] == "call" else ("lampway_worker_done", {"summary": step[1]})
            r = self.http.post(entry["url"], json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}},
                               headers={**entry["headers"], "Accept": "application/json, text/event-stream"})
            self.results.setdefault(f"{swarm_id}:{worker_id}", []).append((name, r.json().get("result")))


@pytest.fixture
def played(monkeypatch, tmp_path):
    """Lampway's herdr, played, with the played Mode 1 adapter in the registry; returns (cockpit, herdr)."""
    from lampway_server.herdr import swarm_brain as SB
    herdr = PaneHerdr()
    monkeypatch.setattr(L, "run", herdr)
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    monkeypatch.setitem(HN.LAMPWAY_ADAPTERS, "lampway_hermes", PlayedHermes())
    monkeypatch.setattr(SB, "POLL_S", 0.05)
    (tmp_path / "proj").mkdir()
    return H.Cockpit(tmp_path / "herdr", project_root=str(tmp_path / "proj")), herdr


def tasks(*names):
    return [{"name": n, "prompt": f"QA the piece {n} and draw its candidates"} for n in names]


def run_swarm(settings, played, names=("a", "b", "c"), *, play=marker_play, configure=None, collect=True, after=None):
    """One in-app turn that starts a swarm of ``names`` and (by default) collects it. ``after(fake, ws, fleet, session_id)`` runs
    further turns on the same socket. Returns (fleet, frames, session_id, command_id, cockpit, herdr, provider)."""
    cockpit, herdr = played
    calls = [ToolCall(id="s1", name="swarm_start", arguments={"tasks": tasks(*names)})]
    script = [calls]
    if collect:
        script.append([ToolCall(id="s2", name="swarm_collect", arguments={"swarm_id": "sw1"})])
    script.append([Text("Done.")])
    provider = ScriptedProvider(script)
    app = create_app(settings, provider=provider, cockpit=cockpit)
    from lampway_server import capabilities as CAP
    CAP.ACTIVE.set("swarm", enabled=True, by="user")             # the swarm is off until the user switches it on (spec E2, Q8)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        if configure:
            configure(fleet)
        with PanePlayer(http, cockpit, herdr, play), fake.connect_ws() as ws:
            fake.handshake(ws)
            session_id = new_session()
            command_id = fake.command(ws, "chat", fake.chat_payload("QA three pieces", session_id))
            frames = fleet.drive(ws, command_id)
            if after is not None:
                after(fake, ws, fleet, session_id, provider)
        fleet.close()
    return fleet, frames, session_id, command_id, cockpit, herdr, provider


def events(frames):
    return [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]


def test_the_swarm_feeds_the_parallel_agents_panel_with_a_todo_slot_per_task(settings, played):
    _fleet, frames, *_ = run_swarm(settings, played)
    todos = [e["todo"] for e in events(frames) if "todo" in e]
    assert todos, "no todo slot was emitted, so the client's Parallel Agents cards never appear"
    first, last = todos[0], todos[-1]
    assert len(first) == 3 and len({row["id"] for row in first}) == 3
    assert all(set(row) == {"id", "text", "status"} for row in first)
    assert {row["status"] for row in first} <= {"PENDING", "IN_PROGRESS"}
    assert {row["status"] for row in last} == {"DONE"} and [r["id"] for r in last] == [r["id"] for r in first]
    assert any(row["status"] == "IN_PROGRESS" for t in todos for row in t)


def test_every_worker_is_a_pane_on_the_units_adapter_in_one_tab(settings, played):
    """Spec S1, A4: Mode 1 picks lampway_hermes; each worker's pane is in its unit's tab, its task on the command line."""
    fleet, frames, session_id, _cmd, cockpit, herdr, _p = run_swarm(settings, played, ("a", "b"))
    panes = sorted((s for s in cockpit.list_sessions() if s.get("created_by") == "swarm"), key=lambda s: s["swarm_binding"])
    assert [p["agent"] for p in panes] == ["lampway_hermes", "lampway_hermes"]
    assert [(p["unit"], p["role"]) for p in panes] == [(session_id, "worker")] * 2 and len({p["tab_id"] for p in panes}) == 1
    assert [herdr.metadata[p["pane_id"]]["display_agent"] for p in panes] == ["Worker 1 · a", "Worker 2 · b"]
    assert herdr.closed() == [], "a finished worker's pane stays open for the user to read"


def test_a_brain_reaches_only_its_own_workers_lampway(settings, played):
    fleet, *_ = run_swarm(settings, played, ("a", "b"))
    for worker in fleet.workers.values():
        marked = [f["params"] for f in worker.frames if f.get("method") == "blender.execute_script" and "# by worker-" in f["params"]["script"]]
        assert len(marked) == 1, "each pane's script reached exactly its own worker"
        assert marked[0]["session_id"] == f"agent:{worker.connection_id}" and marked[0]["envelope"]["execution_target"] == worker.connection_id
    parent = [p for m, p in fleet.requests if m == "blender.execute_script" and "# by worker-" in p.get("script", "")]
    assert parent == [], "no worker's call reached the user's scene"


def test_a_worker_whose_pane_exits_shows_as_a_failed_card_and_its_work_is_not_committed(settings, played):
    def play(swarm_id, worker_id):
        return [("exit",)] if worker_id == "worker-2" else marker_play(swarm_id, worker_id)
    fleet, frames, *_ = run_swarm(settings, played, ("a", "b"), play=play)
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert [r["status"] for r in last] == ["DONE", "FAILED"]
    commits = [p for m, p in fleet.requests if m == "agent.execution.commit"]
    assert len(commits) == 1


def test_the_swarm_speaks_v3_activate_spawn_bind_envelope_stage_commit_status(settings, played):
    fleet, frames, session_id, command_id, *_ = run_swarm(settings, played, ("a", "b"))
    methods = [m for m, _ in fleet.requests]
    assert methods.index("agent.execution.activate") < methods.index("agent.sandbox_control") < methods.index("agent.execution.bind_task")
    activate = next(p for m, p in fleet.requests if m == "agent.execution.activate")
    started = next(f for f in frames if f.get("method") == "agent.turn.started")
    assert activate["protocol_version"] == "v3" and activate["session_id"] == session_id
    assert activate["run_id"] == started["params"]["run_id"] and isinstance(activate["turn_epoch"], int) and activate["turn_epoch"] > 0
    spawns = [p for m, p in fleet.requests if m == "agent.sandbox_control" and p["action"] == "spawn"]
    assert len(spawns) == 2 and all("-sbx-" in p["connection_id"] and p["parent_instance_id"] == fleet.instance_id for p in spawns)
    binds = [p for m, p in fleet.requests if m == "agent.execution.bind_task"]
    assert sorted(b["worker_connection_id"] for b in binds) == sorted(p["connection_id"] for p in spawns)
    assert all(b["execution_class"] == "worker" and b["turn_epoch"] == activate["turn_epoch"] and isinstance(b["fence_token"], int) for b in binds)
    for worker in fleet.workers.values():                       # every script went to a worker, on its constant routing session, with an envelope
        runs = [f["params"] for f in worker.frames if f.get("method") == "blender.execute_script"]
        assert runs and all(p["session_id"] == f"agent:{worker.connection_id}" for p in runs)
        env = runs[0]["envelope"]
        assert env["run_id"] == activate["run_id"] and env["turn_epoch"] == activate["turn_epoch"] and env["execution_target"] == worker.connection_id
        assert env["protocol_version"] == "v3" and env["task_id"] and env["fence_token"] == "1"
    parent_scripts = [p["tool_name"] for m, p in fleet.requests if m == "blender.execute_script"]
    assert "swarm_lanes" not in parent_scripts and "swarm_merge" not in parent_scripts
    commits = [p for m, p in fleet.requests if m == "agent.execution.commit"]
    assert len(commits) == 2 and all(c["op"] == "append_collection" and c["target_collection"] == "Lampway Agent" for c in commits)
    assert all(c["artifact_id"] and c["content_hash"] and c["operation_id"] and len(c["payload_hash"]) == 64 for c in commits)
    statuses = [p for m, p in fleet.requests if m == "agent.execution.status"]
    assert statuses and set(statuses[-1]["operation_ids"]) == {c["operation_id"] for c in commits}
    assert not any(s["session_id"].startswith("agentlane:") for s in (p for m, p in fleet.requests if m == "blender.execute_script"))


def test_every_worker_starts_from_an_empty_scene_before_anything_else(settings, played):
    """Live (2026-10-05): a headless worker boots with Blender's default Camera/Cube/Light, and they were staged back as 'its work'."""
    fleet, *_ = run_swarm(settings, played, ("a", "b"))
    for worker in fleet.workers.values():
        runs = [f["params"] for f in worker.frames if f.get("method") == "blender.execute_script"]
        assert runs[0]["tool_name"] == "swarm_reset" and "reset_worker_scene" in runs[0]["script"]


def test_three_workers_that_all_draw_the_same_collection_name_all_land_in_the_users_scene(settings, played):
    fleet, frames, *_ = run_swarm(settings, played)
    landed = fleet.parent.collections["Lampway Agent"]
    assert len(landed) == 3, "each worker owns its process: nobody wipes anybody's markers"
    objs = sorted(o for c in landed for o in c["objects"])
    assert objs == sorted(f"w{n}_{s}" for n in (1, 2, 3) for s in ("L000", "label"))
    for worker in fleet.workers.values():                       # the same name existed in three worlds at once
        assert list(worker.world.collections) == ["QA_candidates"]
    collect_steps = [row for e in events(frames) for row in (e.get("steps") or {}).get("items", []) if row["label"] == "swarm_collect"]
    assert collect_steps and collect_steps[-1]["status"] == "done"


def test_a_refused_commit_fails_the_task_and_names_the_clients_reason(settings, played):
    fleet, frames, *_ = run_swarm(settings, played, ("a", "b"), configure=lambda f: setattr(f, "reject_commits", "stale_fence"))
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert {r["status"] for r in last} == {"FAILED"}
    assert fleet.parent.collections["Lampway Agent"] == []


def test_a_worker_that_cannot_be_spawned_is_a_failed_card_not_a_hang_and_nothing_is_bound_committed_or_opened(settings, played):
    fleet, frames, _s, _c, cockpit, herdr, _p = run_swarm(settings, played, ("a",), configure=lambda f: setattr(f, "spawn_error", "no sandbox supervisor"))
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert [r["status"] for r in last] == ["FAILED"]
    methods = [m for m, _ in fleet.requests]
    assert "agent.execution.bind_task" not in methods and "agent.execution.commit" not in methods
    assert cockpit.list_sessions() == [] and herdr.made() == [], "no pane opens for a worker whose scene never started"


def test_a_worker_connection_that_is_not_a_sandbox_of_this_parent_is_never_driven(settings, played, monkeypatch):
    from lampway_server.agent import harness
    monkeypatch.setattr(harness, "CONNECT_TIMEOUT_S", 0.5)
    from .fake_harness import FakeWorker
    monkeypatch.setattr(FakeWorker, "role", "desktop", raising=False)

    def make(fleet):
        original = fleet._sandbox

        def spawn(p):
            if p["action"] == "spawn":
                w = FakeWorker(fleet, p["connection_id"], "someone-else")
                w.role = "sandbox"
                fleet.workers[p["connection_id"]] = w
                w.start()
                w.ready.wait(10)
                return {"success": True}
            return original(p)
        fleet._sandbox = spawn
    fleet, *_ = run_swarm(settings, played, ("a",), configure=make)
    assert all(not [f for f in w.frames if f.get("method") == "blender.execute_script"] for w in fleet.workers.values())


def test_a_worker_that_never_finishes_fails_with_the_timeout_and_the_others_finish(settings, played, monkeypatch):
    from lampway_server.herdr import swarm_brain as SB
    monkeypatch.setattr(SB, "PANE_WORKER_TIMEOUT_S", 0.6)
    fleet, frames, _s, _c, cockpit, herdr, _p = run_swarm(
        settings, played, ("a", "b"), play=lambda s, w: [("hang",)] if w == "worker-1" else marker_play(s, w))
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert [r["status"] for r in last] == ["FAILED", "DONE"]
    hung = next(s for s in cockpit.list_sessions() if s.get("swarm_binding", "").endswith(":worker-1"))
    assert herdr.closed() == [hung["pane_id"]], "the swarm closes the pane it opened for the timed-out worker, and only it"


def test_the_system_prompt_teaches_the_v3_swarm_not_lane_scenes():
    from lampway_server.agent.prompt import SYSTEM_PROMPT
    for token in ("swarm_start", "swarm_collect", "swarm_cancel", "Lampway Agent", "objects", "OWN Blender process"):
        assert token in SYSTEM_PROMPT
    assert "lane" not in SYSTEM_PROMPT


def test_a_worker_prompt_names_its_inputs_and_says_nothing_of_lanes():
    from lampway_server.agent.swarm import Worker, worker_system_prompt
    text = worker_system_prompt(Worker("worker-1", "boots", "QA", ["Boots1_uv"]))
    assert "Boots1_uv" in text and "OWN Blender process" in text and "lane" not in text
    assert "starts empty" in worker_system_prompt(Worker("worker-2", "x", "y"))


def test_the_worker_tools_are_blender_and_lampway_tools_never_the_swarm_or_the_studios():
    from lampway_server.agent.swarm import SWARM_NAMES, worker_tools
    names = {t.name for t in worker_tools()}
    assert "run_blender_python" in names and not names & SWARM_NAMES and not any(n.startswith("studio_") for n in names)


def test_collecting_twice_or_an_unknown_swarm_is_an_error_and_the_task_list_is_validated(settings):
    import asyncio
    from lampway_server.agent.swarm import SwarmContext, SwarmManager
    mgr = SwarmManager(run_script=None)
    ctx = SwarmContext(socket=object(), session_id="s", turn_id="t", call_id="c")
    out = asyncio.run(mgr.call("swarm_collect", {"swarm_id": "nope"}, ctx))
    assert out[1] is True and "unknown swarm" in out[0]
    assert asyncio.run(mgr.call("swarm_start", {"tasks": []}, ctx))[1] is True
    assert "at most" in asyncio.run(mgr.call("swarm_start", {"tasks": [{"name": "a", "prompt": "b"}] * 7}, ctx))[0]
    assert "objects" in asyncio.run(mgr.call("swarm_start", {"tasks": [{"name": "a", "prompt": "b", "objects": [3]}]}, ctx))[0]
