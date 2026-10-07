# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1 swarm workers (docs/reports/agent-modes-spec.md S2): each worker thinks as its own engine session.

The live test runs the REAL pinned engine twice at once (two workers), behind the real server's MCP endpoint, against a scripted
loopback model; each worker's tool call must reach only its own job's door. It needs a built engine and the ACP SDK and SKIPS
without them (a skip is not a pass). The provider choice per worker is pinned at the gateway without an engine."""

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from lampway_server.agent.providers.base import Text
from lampway_server.agent.providers.mock import ScriptedProvider
from lampway_server.agent.swarm_brains import BuiltinBrain, WorkerJob
from lampway_server.app import create_app
from lampway_server.engine.runtime import EngineRuntime, EngineSession
from lampway_server.engine.swarm_brain import EngineBrain

from .test_engine_conformance import ENGINE, HAVE_ACP, stack  # noqa: F401  (the live stack fixture)


def test_the_gateway_answers_a_worker_on_its_own_provider(settings, provider):
    """The main provider answers scene sessions; a worker's session is answered by the provider its swarm chose (agent.worker)."""
    provider.script = [[Text("main says hi")]]
    worker_provider = ScriptedProvider([[Text("worker says hi")]])
    app = create_app(settings, provider=provider)
    runtime = EngineRuntime.__new__(EngineRuntime)
    runtime.sessions = {"s1:worker:sw1:worker-1": EngineSession("s1:worker:sw1:worker-1", settings.state_dir, provider=worker_provider)}
    app.state.agent.engine = runtime
    with TestClient(app, base_url="http://127.0.0.1:8787", client=("127.0.0.1", 50000)) as c:
        reg = app.state.engine_tokens
        body = {"model": "lampway", "messages": [{"role": "user", "content": "hi"}]}
        main = c.post("/engine/v1/chat/completions", json=body, headers={"Authorization": f"Bearer {reg.issue_token('s1')}"}).json()
        work = c.post("/engine/v1/chat/completions", json=body,
                      headers={"Authorization": f"Bearer {reg.issue_token('s1:worker:sw1:worker-1')}"}).json()
    assert main["choices"][0]["message"]["content"] == "main says hi"
    assert work["choices"][0]["message"]["content"] == "worker says hi"


def test_the_swarm_thinks_the_way_its_tab_does(settings, provider):
    app = create_app(settings, provider=provider)
    hub = app.state.agent
    assert isinstance(hub.swarm.brain_for(None), BuiltinBrain)          # no engine: the built-in loop
    hub.engine = EngineRuntime.__new__(EngineRuntime)
    assert isinstance(hub.swarm.brain_for(None), EngineBrain)           # Lampway's engine in the seat: engine workers


class WorkerModel:
    """Answers each worker by its own task: first a tool call through Hermes's bridge, then its one-sentence summary."""

    def __init__(self):
        self.seen = []
        model = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                self._send(200, {"object": "list", "data": [{"id": "lampway", "object": "model", "context_length": 131072}]})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                msgs = body.get("messages") or []
                text = json.dumps(msgs)
                task = "A" if "Task A" in text else "B" if "Task B" in text else "?"
                model.seen.append({"task": task, "stream": body.get("stream"),
                                   "tools": [t.get("function", {}).get("name") for t in body.get("tools") or []]})
                if not body.get("stream"):
                    return self._send(200, {"id": "x", "object": "chat.completion", "created": 1, "model": "lampway", "choices": [
                        {"index": 0, "message": {"role": "assistant", "content": "Title"}, "finish_reason": "stop"}]})
                if msgs and msgs[-1].get("role") == "tool":
                    delta, finish = {"role": "assistant", "content": f"Worker {task} made {task}_marker."}, "stop"
                else:
                    names = model.seen[-1]["tools"]
                    full = "mcp__lampway__run_blender_python"
                    args = {"script": f"import bpy\n# marker {task}\n"}
                    name, a = (full, args) if full in names else ("tool_call", {"calls": [{"name": full, "arguments": args}]})
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"c{task}{len(model.seen)}", "type": "function",
                                                                  "function": {"name": name, "arguments": json.dumps(a)}}]}
                    finish = "tool_calls"
                chunks = [{"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "lampway",
                           "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                          {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "lampway",
                           "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}]
                self._send(200, b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n",
                           "text/event-stream")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"


@pytest.mark.skipif(ENGINE is None or not HAVE_ACP, reason="needs a built engine and the ACP SDK (scripts/lampway/engine_env.py)")
@pytest.mark.timeout(300)
def test_two_engine_workers_each_reach_only_their_own_door(stack):  # noqa: F811
    from lampway_server.agent.swarm import worker_system_prompt, worker_tools
    model = WorkerModel()
    runtime = stack["attach"](SimpleNamespace(url=model.url))
    calls = {"A": [], "B": []}

    def job_for(task, wid):
        worker = SimpleNamespace(id=wid, name=f"task{task}", prompt=f"Task {task}: make one marker.", objects=[], tool_calls=0,
                                 choice=None)

        async def door(name, arguments):
            worker.tool_calls += 1
            calls[task].append({"name": name, "script": arguments.get("script", ""),
                                "offered": sorted(t.name for t in runtime.tool_specs(EngineBrain.key(job)))})
            return json.dumps({"success": True, "created_objects": [f"{task}_marker"]}), False

        job = WorkerJob(worker, worker_system_prompt(worker), worker_tools(), door, lambda text: None,
                        {"swarm_id": "sw1", "session_id": "parent-1", "turn_id": "t1"})
        return job

    jobs = [job_for("A", "worker-1"), job_for("B", "worker-2")]
    brain = EngineBrain(runtime, provider_factory=None)

    async def go():
        return await asyncio.gather(*(brain.run(j) for j in jobs))

    summaries = asyncio.run(go())
    assert summaries == ["Worker A made A_marker.", "Worker B made B_marker."]
    for task in ("A", "B"):
        assert len(calls[task]) == 1 and calls[task][0]["name"] == "run_blender_python"
        assert f"# marker {task}" in calls[task][0]["script"], "each worker's call reached its own door only"
        offered = set(calls[task][0]["offered"])
        assert "run_blender_python" in offered and not {"swarm_start", "swarm_collect", "ask_user", "lampway_workbench"} & offered
    homes = sorted(p.name for p in (stack["settings"].state_dir / "agent" / "hermes" / "parent-1" / "workers").iterdir())
    assert homes == ["sw1-worker-1", "sw1-worker-2"], "each worker is its own engine session, beside its parent's"
    assert runtime.sessions == {}, "a worker's engine is stopped when its task ends"
