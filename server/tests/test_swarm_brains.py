# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""One swarm substrate, pluggable brains (docs/reports/agent-modes-spec.md S1): the brain only thinks; its one door to a scene is the
job's ``call_tool``, which runs on its own worker's headless Lampway with that worker's v3 envelope."""

from lampway_server.agent import swarm_brains as SB

from .test_swarm_v3 import run_swarm


class RecordingBrain:
    """A brain with no model: it runs one marked script through its job and reports. What the S2 and S3 brains plug into."""
    kind = "test"

    def __init__(self, seen):
        self.seen = seen

    async def run(self, job: SB.WorkerJob) -> str:
        text, is_error = await job.call_tool("run_blender_python", {"script": f"import bpy\n# by {job.worker.id}\n# collection QA_candidates {job.worker.name}_L000\n"})
        self.seen.append({"worker": job.worker.id, "error": is_error, "tools": sorted(t.name for t in job.tools),
                          "system": job.system, "meta": dict(job.meta)})
        return f"{job.worker.name} made its marker"

    async def stop(self, job):
        return None


def test_a_brain_reaches_only_its_own_workers_lampway(settings):
    seen = []

    import lampway_server.agent.swarm as SW
    original = SW.SwarmManager.__init__

    def patched(self, *a, **k):
        original(self, *a, **k)
        self.brain_for = lambda ctx: RecordingBrain(seen)
    SW.SwarmManager.__init__ = patched
    try:
        fleet, frames, session_id, command_id = run_swarm(settings, ("a", "b"))
    finally:
        SW.SwarmManager.__init__ = original
    assert sorted(s["worker"] for s in seen) == ["worker-1", "worker-2"] and not any(s["error"] for s in seen)
    for worker in fleet.workers.values():
        marked = [f["params"] for f in worker.frames if f.get("method") == "blender.execute_script" and "# by worker-" in f["params"]["script"]]
        assert len(marked) == 1, "each brain's script reached exactly its own worker"
        assert marked[0]["session_id"] == f"agent:{worker.connection_id}" and marked[0]["envelope"]["execution_target"] == worker.connection_id
    parent = [p for m, p in fleet.requests if m == "blender.execute_script" and "# by worker-" in p.get("script", "")]
    assert parent == [], "no brain's call reached the user's scene"
    for s in seen:                                   # never the swarm, the studios, ask_user or the panes in a worker's hands
        assert not {"swarm_start", "swarm_collect", "ask_user", "lampway_workbench", "studio_plan"} & set(s["tools"])
        assert s["meta"]["session_id"] == session_id and s["meta"]["swarm_id"]
    commits = [p for m, p in fleet.requests if m == "agent.execution.commit"]
    assert len(commits) == 2


def test_the_builtin_brain_is_the_default():
    from lampway_server.agent.swarm import SwarmManager
    m = SwarmManager(lambda label: None, run_script=None)
    assert isinstance(m.brain_for(None), SB.BuiltinBrain)
