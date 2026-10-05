"""The swarm: the orchestrator's tools spawn workers that each build in their own lane scene.

The client's contract (ARCHITECTURE.md "Scene routing per session", main_thread_executor.py, session.py): a worker's script is
addressed with session_id == chat_session_id == ``agentlane:<parent>:<n>``; the executor switches to the scene whose
``mixie_session_id`` is that string, and the lane maps back to its parent through the lane scene's
``mixar_workspace_main_session``. A lane the server never created is rejected ("no scene for session"), so the lane scenes
are created by a script on the PARENT session before any worker starts, and merged into the parent by another one."""

import ast
import asyncio
import json

import pytest

from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.agent.swarm import SWARM_SPECS, SwarmManager, is_swarm_tool

pytestmark = pytest.mark.anyio

PARENT = "parent-session-1"


def cube(name):
    return ToolCall(id=f"c_{name}", name="run_blender_python", arguments={"script": f"import bpy\n# {name}\n"})


class FakeBlender:
    """Answers the swarm's scripts like the client would, and records them. Scripts for a lane wait at ``gate`` so a test can
    prove several lanes are outstanding at once."""

    def __init__(self, hold=False):
        self.calls = []                                  # (session_id, chat_session_id, tool_name, script)
        self.outstanding = 0
        self.peak = 0
        self.hold = hold
        self._gate = asyncio.Event()
        if not hold:
            self._gate.set()

    def release(self):
        self._gate.set()

    async def until_outstanding(self, n):
        for _ in range(500):
            if self.outstanding >= n:
                return
            await asyncio.sleep(0.01)
        raise AssertionError(f"only {self.outstanding} of {n} lane scripts were ever outstanding")

    async def __call__(self, socket, *, session_id, chat_session_id, turn_id, call_id, tool_name, script):
        self.calls.append((session_id, chat_session_id, tool_name, script))
        self.outstanding += 1
        self.peak = max(self.peak, self.outstanding)
        try:
            if self.hold and session_id.startswith("agentlane:"):
                await asyncio.wait_for(self._gate.wait(), 5)
            if session_id == PARENT:
                return {"success": True, "lanes": [], "merged": {}}
            note = script.splitlines()[1].lstrip("# ")
            return {"success": True, "created_objects": [f"{note}_obj"]}
        finally:
            self.outstanding -= 1


def plan_of(script):
    """The merge plan the script carries: the JSON string literal that starts with a list."""
    literal = next(n.value for n in ast.walk(ast.parse(script)) if isinstance(n, ast.Constant)
                   and isinstance(n.value, str) and n.value.startswith("["))
    return json.loads(literal)


def factory_for(scripts_by_label):
    made = {}

    def make(label):
        made[label] = ScriptedProvider(list(scripts_by_label.get(label, [[Text("done")]])))
        return made[label]

    make.made = made
    return make


def ctx(blender):
    from lampway_server.agent.swarm import SwarmContext
    return SwarmContext(socket=object(), session_id=PARENT, turn_id="t1", call_id="k1", progress=lambda text: None)


TASKS = [{"name": "alpha", "prompt": "build alpha"}, {"name": "beta", "prompt": "build beta"}, {"name": "gamma", "prompt": "build gamma"}]


def worker_scripts():
    return {f"worker-{i}": [[Text("building"), cube(n)], [Text(f"{n} finished")]] for i, n in ((1, "alpha"), (2, "beta"), (3, "gamma"))}


async def start(manager, blender, tasks=TASKS):
    text, is_error = await manager.call("swarm_start", {"tasks": tasks}, ctx(blender))
    assert not is_error, text
    return json.loads(text)


def test_the_swarm_tools_have_specs_and_are_recognised():
    names = {s.name for s in SWARM_SPECS}
    assert names == {"swarm_start", "swarm_status", "swarm_cancel", "swarm_collect"}
    assert all(is_swarm_tool(n) for n in names) and not is_swarm_tool("run_blender_python")
    start_spec = next(s for s in SWARM_SPECS if s.name == "swarm_start")
    assert start_spec.parameters["required"] == ["tasks"]


async def test_lanes_are_created_by_a_script_on_the_parent_session_before_any_worker_runs():
    blender = FakeBlender()
    manager = SwarmManager(factory_for(worker_scripts()), blender)
    info = await start(manager, blender)
    await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    first = blender.calls[0]
    assert first[0] == PARENT and first[1] == PARENT and first[2] == "swarm_lanes"
    ast.parse(first[3])
    for n in (1, 2, 3):
        assert f"agentlane:{PARENT}:{n}" in first[3]
    assert "mixar_workspace_main_session" in first[3] and "mixie_session_id" in first[3]
    assert [w["lane"] for w in info["workers"]] == [f"agentlane:{PARENT}:{n}" for n in (1, 2, 3)]


async def test_each_workers_scripts_are_addressed_to_its_own_lane():
    blender = FakeBlender()
    manager = SwarmManager(factory_for(worker_scripts()), blender)
    info = await start(manager, blender)
    await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    worker_calls = [c for c in blender.calls if c[2] == "run_blender_python"]
    assert len(worker_calls) == 3
    for n, name in ((1, "alpha"), (2, "beta"), (3, "gamma")):
        lane = f"agentlane:{PARENT}:{n}"
        mine = [c for c in worker_calls if c[0] == lane]
        assert len(mine) == 1 and mine[0][1] == lane and f"# {name}" in mine[0][3]


async def test_workers_run_concurrently_not_one_after_another():
    blender = FakeBlender(hold=True)                      # every worker's script waits until all three are outstanding
    manager = SwarmManager(factory_for(worker_scripts()), blender)
    info = await start(manager, blender)
    await blender.until_outstanding(3)
    blender.release()
    text, is_error = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    assert not is_error and blender.peak == 3


async def test_every_result_is_attributed_to_the_worker_that_made_it():
    blender = FakeBlender()
    manager = SwarmManager(factory_for(worker_scripts()), blender)
    info = await start(manager, blender)
    text, is_error = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    result = json.loads(text)
    by_name = {w["name"]: w for w in result["workers"]}
    assert not is_error
    for name in ("alpha", "beta", "gamma"):
        assert by_name[name]["status"] == "done"
        assert by_name[name]["created_objects"] == [f"{name}_obj"]
        assert by_name[name]["summary"] == f"{name} finished"
    merge = next(c for c in blender.calls if c[2] == "swarm_merge")
    assert merge[0] == PARENT
    plan = plan_of(merge[3])
    assert {p["name"]: p["keep"] for p in plan} == {"alpha": True, "beta": True, "gamma": True}
    assert "lw_worker" in merge[3]


async def test_cancelling_one_worker_leaves_the_others_running_and_its_lane_is_discarded():
    blender = FakeBlender(hold=True)                      # all three are inside Blender's queue when beta is cancelled
    manager = SwarmManager(factory_for(worker_scripts()), blender)
    info = await start(manager, blender)
    beta = next(w for w in info["workers"] if w["name"] == "beta")["id"]
    await blender.until_outstanding(3)
    text, is_error = await manager.call("swarm_cancel", {"swarm_id": info["swarm_id"], "worker": beta}, ctx(blender))
    assert not is_error and json.loads(text)["status"] == "cancelled"
    blender.release()
    text, is_error = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    result = json.loads(text)
    status_by_name = {w["name"]: w["status"] for w in result["workers"]}
    assert status_by_name == {"alpha": "done", "beta": "cancelled", "gamma": "done"}
    merge = next(c for c in blender.calls if c[2] == "swarm_merge")
    keep = {w["name"]: w["keep"] for w in plan_of(merge[3])}
    assert keep == {"alpha": True, "beta": False, "gamma": True}


async def test_a_worker_that_fails_is_reported_and_does_not_stop_the_others():
    class Boom(ScriptedProvider):
        async def stream(self, request):
            raise RuntimeError("OpenRouter session spend ceiling reached")
            yield  # pragma: no cover

    scripts = worker_scripts()
    made = {}

    def make(label):
        made[label] = Boom() if label == "worker-2" else ScriptedProvider(list(scripts[label]))
        return made[label]

    blender = FakeBlender()
    manager = SwarmManager(make, blender)
    info = await start(manager, blender)
    text, is_error = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    by_name = {w["name"]: w for w in json.loads(text)["workers"]}
    assert (by_name["alpha"]["status"], by_name["beta"]["status"], by_name["gamma"]["status"]) == ("done", "failed", "done")
    assert "spend ceiling" in by_name["beta"]["error"]


async def test_collecting_twice_or_an_unknown_swarm_is_an_error_not_a_second_merge():
    blender = FakeBlender()
    manager = SwarmManager(factory_for(worker_scripts()), blender)
    info = await start(manager, blender)
    await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    text, is_error = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    assert is_error and "already collected" in text
    text, is_error = await manager.call("swarm_status", {"swarm_id": "nope"}, ctx(blender))
    assert is_error and "unknown swarm" in text
    assert sum(1 for c in blender.calls if c[2] == "swarm_merge") == 1


async def test_a_task_list_that_is_empty_or_over_the_cap_is_refused_before_any_lane_is_made():
    blender = FakeBlender()
    manager = SwarmManager(factory_for({}), blender, max_workers=4)
    for tasks in ([], [{"name": f"w{i}", "prompt": "x"} for i in range(5)], [{"name": "a"}], "not a list"):
        text, is_error = await manager.call("swarm_start", {"tasks": tasks}, ctx(blender))
        assert is_error, tasks
    assert blender.calls == []


async def test_the_workers_get_a_prompt_that_names_their_lane_and_their_task_and_a_tool_list_without_swarm_or_studio_tools():
    blender = FakeBlender()
    make = factory_for(worker_scripts())
    manager = SwarmManager(make, blender)
    info = await start(manager, blender)
    await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    request = make.made["worker-1"].requests[0]
    assert "alpha" in request.system and "worker-1" in request.system
    assert request.messages[0].text() == "build alpha"
    names = {t.name for t in request.tools}
    assert "run_blender_python" in names and "scene_summary" in names
    assert not any(n.startswith("swarm_") or n.startswith("studio_") for n in names)


async def test_blender_not_answering_to_the_lane_script_is_a_tool_error_not_a_crashed_turn():
    async def silent(socket, **kw):
        raise asyncio.TimeoutError()

    manager = SwarmManager(factory_for({}), silent)
    text, is_error = await manager.call("swarm_start", {"tasks": TASKS}, ctx(None))
    assert is_error and "could not" in text.lower() and manager.swarms == {}
