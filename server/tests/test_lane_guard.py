"""The lane guard: a worker's script is wrapped so that, in the SAME main-thread slot, every object outside its lane is
fingerprinted before the body and checked after it. What can be put back (a move, a rename, a re-parent, a visibility
flip, a collection link) is put back and reported; what cannot (a deletion, a geometry or data edit) fails the worker,
whose lane is then discarded at collect time. A worker renaming its OWN object is not a violation: ownership is judged
by the object's pointer, not its name, and the rename is reported so the worker's created list follows it."""

import ast
import json

import pytest

from lampway_server.agent import lane_guard
from lampway_server.agent.providers.base import Text, ToolCall
from lampway_server.agent.swarm import SwarmManager
from .test_swarm import FakeBlender, ctx, cube, factory_for, note_of, plan_of, start

pytestmark = pytest.mark.anyio


def test_the_body_runs_inside_the_guard_and_the_result_carries_the_lane_guard_section():
    script = lane_guard.guarded_script("sw1_alpha", "import bpy\nob = bpy.data.objects.new('alpha_1', None)\n__RESULT__ = {'n': 1}\n")
    tree = ast.parse(script)
    tries = [n for n in ast.walk(tree) if isinstance(n, ast.Try)]
    assert tries, "the body must run under a try so the check runs even when it raises"
    body_src = ast.unparse(ast.Module(body=tries[0].body, type_ignores=[]))
    assert "alpha_1" in body_src and "__RESULT__" in body_src
    assert "'sw1_alpha'" in script or '"sw1_alpha"' in script
    last = tree.body[-1]
    assert isinstance(last, ast.Assign) and last.targets[0].id == "__RESULT__"


def test_a_body_that_does_not_parse_is_returned_unchanged_for_the_executor_to_report():
    body = "def broken(:\n"
    assert lane_guard.guarded_script("sw1_alpha", body) == body


class GuardingBlender(FakeBlender):
    """Answers a worker's script with a lane_guard section taken from ``guards`` (by worker note), like the wrapped script
    would produce in Blender."""

    def __init__(self, guards):
        super().__init__()
        self.guards = guards

    async def __call__(self, socket, *, session_id, chat_session_id, turn_id, call_id, tool_name, script):
        result = await super().__call__(socket, session_id=session_id, chat_session_id=chat_session_id, turn_id=turn_id,
                                        call_id=call_id, tool_name=tool_name, script=script)
        if session_id.startswith("agentlane:"):
            extra = self.guards.get(note_of(script))
            if extra:
                result = {**result, **extra}
        return result


def guard(violations=(), restored=(), unrestored=(), renamed_own=None):
    return {"lane_guard": {"violations": list(violations), "restored": list(restored), "unrestored": list(unrestored),
                           "renamed_own": renamed_own or {}}}


def scripts(**per_worker):
    base = {f"worker-{i}": [[Text("building"), cube(n)], [Text(f"{n} finished")]] for i, n in ((1, "alpha"), (2, "beta"), (3, "gamma"))}
    base.update(per_worker)
    return base


async def test_every_worker_script_is_wrapped_by_the_guard_and_the_owner_record_keeps_the_original():
    blender = GuardingBlender({})
    manager = SwarmManager(factory_for(scripts()), blender)
    info = await start(manager, blender)
    await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    lane_scripts = [s for sid, _c, tool, s in blender.calls if sid.startswith("agentlane:")]
    assert lane_scripts and all("_lw_before" in s for s in lane_scripts)
    worker = manager.swarms[info["swarm_id"]].workers[0]
    assert worker.calls[0]["script"].startswith("import bpy\n'note:alpha'") and "_lw_before" not in worker.calls[0]["script"], \
        "the owner sees the worker's own script, not the wrapper"


async def test_a_worker_that_deleted_another_lanes_object_fails_and_its_lane_is_discarded():
    blender = GuardingBlender({"beta": guard(violations=[{"object": "alpha_obj", "kind": "deleted"}], unrestored=["alpha_obj"])})
    manager = SwarmManager(factory_for(scripts()), blender)
    info = await start(manager, blender)
    text, is_error = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    assert not is_error, text
    out = json.loads(text)
    beta = next(w for w in out["workers"] if w["name"] == "beta")
    assert beta["status"] == "failed" and "alpha_obj" in beta["error"]
    merge = [s for sid, _c, tool, s in blender.calls if tool == "swarm_merge"][0]
    assert {p["name"]: p["keep"] for p in plan_of(merge)} == {"alpha": True, "beta": False, "gamma": True}
    assert out["violations"]["worker-2"][0]["object"] == "alpha_obj"


async def test_a_restorable_touch_is_reported_to_the_worker_as_an_error_and_the_worker_goes_on():
    blender = GuardingBlender({"beta": guard(violations=[{"object": "chest", "kind": "moved"}], restored=["chest"])})
    provider_scripts = scripts(**{"worker-2": [[Text("building"), cube("beta")], [Text("beta finished")]]})
    factory = factory_for(provider_scripts)
    manager = SwarmManager(factory, blender)
    info = await start(manager, blender)
    text, _ = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    out = json.loads(text)
    beta = next(w for w in out["workers"] if w["name"] == "beta")
    assert beta["status"] == "done"
    worker_provider = factory.made["worker-2"]
    tool_result = worker_provider.requests[-1].messages[-1].content[0]
    assert tool_result["is_error"] is True and "chest" in tool_result["content"] and "put back" in tool_result["content"]


async def test_renaming_its_own_object_is_not_a_violation_and_the_created_list_follows_the_new_name():
    blender = GuardingBlender({"beta": guard(renamed_own={"beta_obj": "beta_cube"})})
    manager = SwarmManager(factory_for(scripts()), blender)
    info = await start(manager, blender)
    text, _ = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    out = json.loads(text)
    beta = next(w for w in out["workers"] if w["name"] == "beta")
    assert beta["status"] == "done" and beta["created_objects"] == ["beta_cube"]
    assert "worker-2" not in out["violations"]


async def test_a_body_error_reaches_the_worker_as_a_failed_tool_result_not_a_failed_worker():
    blender = GuardingBlender({"beta": {"body_error": "KeyError: 'nope'", "lane_guard": guard()["lane_guard"]}})
    factory = factory_for(scripts())
    manager = SwarmManager(factory, blender)
    info = await start(manager, blender)
    text, _ = await manager.call("swarm_collect", {"swarm_id": info["swarm_id"]}, ctx(blender))
    out = json.loads(text)
    beta = next(w for w in out["workers"] if w["name"] == "beta")
    assert beta["status"] == "done"
    tool_result = factory.made["worker-2"].requests[-1].messages[-1].content[0]
    assert tool_result["is_error"] is True and "KeyError: 'nope'" in tool_result["content"]
    assert '"success": false' in tool_result["content"]
