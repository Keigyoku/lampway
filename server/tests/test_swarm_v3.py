"""The swarm on the client's own harness (v3): every worker is its own headless process, results enter the user's scene only through
the typed append_collection commit, and the Parallel Agents panel is fed by the chat's todo slot. The parent and the workers are
the fake fleet in fake_harness.py."""

import json

import pytest
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.app import create_app

from .fake_client import FakeMixarClient
from .fake_harness import FakeFleet, new_session


def worker_provider(label):
    n = label.split("-")[1]
    return ScriptedProvider([
        [ToolCall(id=f"w{n}", name="run_blender_python", arguments={"script": f"import bpy\n# collection QA_candidates w{n}_L000,w{n}_label\n"})],
        [Text(f"w{n} drew its markers")]])


def tasks(*names):
    return [{"name": n, "prompt": f"QA the piece {n} and draw its candidates"} for n in names]


def run_swarm(settings, names=("a", "b", "c"), *, worker_factory=worker_provider, configure=None, collect=True):
    calls = [ToolCall(id="s1", name="swarm_start", arguments={"tasks": tasks(*names)})]
    script = [calls]
    if collect:
        script.append([ToolCall(id="s2", name="swarm_collect", arguments={"swarm_id": "sw1"})])
    script.append([Text("Done.")])
    app = create_app(settings, provider=ScriptedProvider(script), swarm_provider_factory=worker_factory)
    with TestClient(app, base_url="http://127.0.0.1:8787") as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
        fleet = FakeFleet(fake, fake.instance_id)
        if configure:
            configure(fleet)
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            session_id = new_session()
            command_id = fake.command(ws, "chat", fake.chat_payload("QA three pieces", session_id))
            frames = fleet.drive(ws, command_id)
        fleet.close()
    return fleet, frames, session_id, command_id


def events(frames):
    return [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]


def test_the_swarm_feeds_the_parallel_agents_panel_with_a_todo_slot_per_task(settings):
    _fleet, frames, *_ = run_swarm(settings)
    todos = [e["todo"] for e in events(frames) if "todo" in e]
    assert todos, "no todo slot was emitted, so the client's Parallel Agents cards never appear"
    first, last = todos[0], todos[-1]
    assert len(first) == 3 and len({row["id"] for row in first}) == 3
    assert all(set(row) == {"id", "text", "status"} for row in first)
    assert {row["status"] for row in first} <= {"PENDING", "IN_PROGRESS"}
    assert {row["status"] for row in last} == {"DONE"} and [r["id"] for r in last] == [r["id"] for r in first]
    assert any(row["status"] == "IN_PROGRESS" for t in todos for row in t)


def test_a_failed_worker_shows_as_a_failed_card_and_its_work_is_not_committed(settings):
    def factory(label):
        if label == "worker-2":
            return ScriptedProvider([[Text("")]])                      # an empty response: the worker fails
        return worker_provider(label)
    fleet, frames, *_ = run_swarm(settings, ("a", "b"), worker_factory=factory)
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert [r["status"] for r in last] == ["DONE", "FAILED"]
    commits = [p for m, p in fleet.requests if m == "agent.execution.commit"]
    assert len(commits) == 1


def test_the_swarm_speaks_v3_activate_spawn_bind_envelope_stage_commit_status(settings):
    fleet, frames, session_id, command_id = run_swarm(settings, ("a", "b"))
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


def test_every_worker_starts_from_an_empty_scene_before_anything_else(settings):
    """Live (2026-10-05): a headless worker boots with Blender's default Camera/Cube/Light, and they were staged back as 'its work'."""
    fleet, frames, *_ = run_swarm(settings, ("a", "b"))
    for worker in fleet.workers.values():
        runs = [f["params"] for f in worker.frames if f.get("method") == "blender.execute_script"]
        assert runs[0]["tool_name"] == "swarm_reset" and "reset_worker_scene" in runs[0]["script"]


def test_three_workers_that_all_draw_the_same_collection_name_all_land_in_the_users_scene(settings):
    fleet, frames, *_ = run_swarm(settings)
    landed = fleet.parent.collections["Lampway Agent"]
    assert len(landed) == 3, "each worker owns its process: nobody wipes anybody's markers"
    objs = sorted(o for c in landed for o in c["objects"])
    assert objs == sorted(f"w{n}_{s}" for n in (1, 2, 3) for s in ("L000", "label"))
    for worker in fleet.workers.values():                       # the same name existed in three worlds at once
        assert list(worker.world.collections) == ["QA_candidates"]
    collect_steps = [row for e in events(frames) for row in (e.get("steps") or {}).get("items", []) if row["label"] == "swarm_collect"]
    assert collect_steps and collect_steps[-1]["status"] == "done"


def test_a_refused_commit_fails_the_task_and_names_the_clients_reason(settings):
    fleet, frames, *_ = run_swarm(settings, ("a", "b"), configure=lambda f: setattr(f, "reject_commits", "stale_fence"))
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert {r["status"] for r in last} == {"FAILED"}
    assert fleet.parent.collections["Lampway Agent"] == []


def test_a_worker_that_cannot_be_spawned_is_a_failed_card_not_a_hang_and_nothing_is_bound_or_committed(settings):
    fleet, frames, *_ = run_swarm(settings, ("a",), configure=lambda f: setattr(f, "spawn_error", "no sandbox supervisor"))
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert [r["status"] for r in last] == ["FAILED"]
    methods = [m for m, _ in fleet.requests]
    assert "agent.execution.bind_task" not in methods and "agent.execution.commit" not in methods


def test_a_worker_connection_that_is_not_a_sandbox_of_this_parent_is_never_driven(settings, monkeypatch):
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
    fleet, frames, *_ = run_swarm(settings, ("a",), configure=make)
    assert all(not [f for f in w.frames if f.get("method") == "blender.execute_script"] for w in fleet.workers.values())


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
    mgr = SwarmManager(lambda label: None, None)
    ctx = SwarmContext(socket=object(), session_id="s", turn_id="t", call_id="c")
    out = asyncio.run(mgr.call("swarm_collect", {"swarm_id": "nope"}, ctx))
    assert out[1] is True and "unknown swarm" in out[0]
    assert asyncio.run(mgr.call("swarm_start", {"tasks": []}, ctx))[1] is True
    assert "at most" in asyncio.run(mgr.call("swarm_start", {"tasks": [{"name": "a", "prompt": "b"}] * 7}, ctx))[0]
    assert "objects" in asyncio.run(mgr.call("swarm_start", {"tasks": [{"name": "a", "prompt": "b", "objects": [3]}]}, ctx))[0]


class HangingProvider:
    """A model call that never returns (a headless CLI that wedged)."""
    async def stream(self, request):
        import asyncio
        await asyncio.sleep(3600)
        yield  # pragma: no cover


def test_a_worker_whose_model_call_never_returns_fails_with_the_timeout_and_the_others_finish(settings, monkeypatch):
    from lampway_server.agent import swarm
    monkeypatch.setattr(swarm, "MODEL_ROUND_TIMEOUT_S", 0.3)
    fleet, frames, *_ = run_swarm(settings, ("a", "b"), worker_factory=lambda label: HangingProvider() if label == "worker-1" else worker_provider(label))
    last = [e["todo"] for e in events(frames) if "todo" in e][-1]
    assert [r["status"] for r in last] == ["FAILED", "DONE"]
