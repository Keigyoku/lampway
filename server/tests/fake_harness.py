"""A fake fleet for the swarm tests: one PARENT client and its headless WORKERS, each worker its own process-like world.

The parent answers the harness requests the way the client's own code does (the real code is exercised against the real binary in
tests/lampway_tools/test_agent_execution.py; the semantics modelled here are bindings.py activate/bind_task/check_commit_allowed and
commit.py append_collection: epochs only go up, a task commits only if it is bound and its fence is not older, an operation id is
applied once and replayed by payload hash). Each worker is a thread with its OWN world (``collections``), because the point of the
v3 design is that workers share nothing.
"""

import hashlib
import json
import re
import threading
import uuid


class World:
    """One process's bpy.data, reduced to what the swarm tests look at."""

    def __init__(self):
        self.collections: dict[str, list] = {}
        self.objects: set = set()


class FakeWorker(threading.Thread):
    def __init__(self, fleet, connection_id, parent_instance_id):
        super().__init__(daemon=True)
        self.fleet, self.connection_id, self.parent = fleet, connection_id, parent_instance_id
        self.world = World()
        self.frames = []
        self.ready = threading.Event()
        self.stop = threading.Event()
        self.role = "sandbox"

    def shutdown(self):
        """What sandbox_control shutdown does: the child process ends, its socket closes."""
        self.stop.set()
        ws = getattr(self, "ws", None)
        if ws is not None:
            try:                      # wake the worker thread's blocked receive; its loop then sees ``stop`` and closes the socket itself
                ws.send_json({"jsonrpc": "2.0", "method": "system.ping", "id": "bye"})
            except Exception:  # noqa: BLE001 - already closed
                pass

    def run(self):
        f = self.fleet
        headers = {"Authorization": f"Bearer {f.fake.access_token}", "host": "127.0.0.1:8787"}
        with f.fake.http.websocket_connect(f"/api/agent/ws/{self.connection_id}", headers=headers) as ws:
            ws.send_json({"jsonrpc": "2.0", "method": "system.handshake", "id": "hs", "params": {
                "capabilities": ["script_execution", "exec_envelope_v3"], "role": self.role, "parent_instance_id": self.parent}})
            ws.receive_json()
            self.ws = ws
            self.ready.set()
            while not self.stop.is_set():
                try:
                    frame = ws.receive_json()
                except Exception:  # noqa: BLE001 - the socket closed
                    return
                self.frames.append(frame)
                if frame.get("method") == "blender.execute_script" and frame.get("id"):
                    ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": self.execute(frame["params"])})

    def execute(self, params):
        """A worker script: the swarm's own trusted scripts (import / stage) and the model's, a '# collection <name> <objs>' line."""
        script, tool = params["script"], params["tool_name"]
        refused = self.fleet.refuse_worker_script(self, params)
        if refused:
            return {"success": False, "error": refused, "error_type": "not_assigned"}
        if "reset_worker_scene" in script:
            self.world.collections.clear()
            self.world.objects.clear()
            return {"success": True, "method": "read_homefile"}
        if "staging.stage_scene" in script:
            p = _literal(script)
            names = [o for o in self.world.objects if o not in set(p["skip"])]
            digest = hashlib.sha256((p["collection"] + ",".join(sorted(names))).encode()).hexdigest()
            self.fleet.artifacts[p["artifact_id"]] = {"collection": p["collection"], "objects": sorted(names), "hash": digest}
            return {"success": True, "artifact_id": p["artifact_id"], "collection_name": p["collection"], "object_names": sorted(names),
                    "content_hash": digest, "object_count": len(names), "finite": True}
        if "staging.import_artifact" in script:
            p = _literal(script)
            art = self.fleet.artifacts[p["artifact_id"]]
            self.world.objects.update(art["objects"])
            return {"success": True, "object_names": art["objects"]}
        m = re.search(r"# collection (\S+) (\S*)", script)
        if m:
            name, objs = m.group(1), [o for o in m.group(2).split(",") if o]
            old = self.world.collections.pop(name, None)       # the by-name replace the real draw does, in THIS process only
            self.world.collections[name] = objs
            self.world.objects.update(objs)
            return {"success": True, "created_objects": objs, "replaced": old is not None}
        return {"success": True}


def _literal(script):
    return json.loads(json.loads(re.search(r"json\.loads\((\".*\")\)", script).group(1)))


class FakeFleet:
    """The parent's side: ``handle(frame)`` answers one server request; ``drive`` runs a turn to its end."""

    def __init__(self, fake, instance_id):
        self.fake = fake
        self.instance_id = instance_id
        self.workers: dict[str, FakeWorker] = {}
        self.artifacts: dict = {}
        self.parent = World()
        self.parent.collections["Lampway Agent"] = []
        self.frames: list = []
        self.runs: dict = {}                # session -> {run_id, epoch, revoked, tasks{task: fence}}
        self.ops: dict = {}                 # operation id -> {hash, state, receipt}
        self.requests: list = []            # (method, params) the parent was asked, in order
        self.spawn_error = None
        self.reject_commits = None          # an error_type to refuse every commit with

    def refuse_worker_script(self, worker, params):
        env = params.get("envelope") or {}
        if env.get("execution_target") and env["execution_target"] != worker.connection_id:
            return f"request assigned to {env['execution_target']!r}, this worker is {worker.connection_id!r}"
        if params.get("session_id") != f"agent:{worker.connection_id}":
            return f"per-scene routing session {params.get('session_id')!r} cannot run on worker {worker.connection_id!r}"
        return None

    # ---- the parent's answers
    def handle(self, frame):
        method, p = frame["method"], frame.get("params") or {}
        self.requests.append((method, p))
        if method == "agent.sandbox_control":
            return self._sandbox(p)
        if method == "agent.execution.activate":
            return self._activate(p)
        if method == "agent.execution.bind_task":
            return self._bind(p)
        if method == "agent.execution.commit":
            return self._commit(p)
        if method == "agent.execution.status":
            return {"success": True, "operations": {i: {"state": self.ops[i]["state"], "receipt": self.ops[i]["receipt"]}
                                                    for i in p.get("operation_ids", []) if i in self.ops}}
        if method == "agent.execution.revoke":
            run = next((r for r in self.runs.values() if r["run_id"] == p.get("run_id")), None)
            if run is not None:
                if p.get("task_id"):
                    run["revoked_tasks"].add(p["task_id"])
                else:
                    run["revoked"] = True
            return {"success": True, "known": run is not None}
        if method == "blender.execute_script":
            return self._parent_script(p)
        return {"success": False, "error": f"unexpected {method}"}

    def _parent_script(self, p):
        if "staging.export_copies" in p["script"]:
            lit = _literal(p["script"])
            self.artifacts[lit["artifact_id"]] = {"collection": "inputs", "objects": sorted(lit["objects"]), "hash": "x"}
            return {"success": True, "artifact_id": lit["artifact_id"], "object_names": sorted(lit["objects"])}
        return {"success": True}

    def _sandbox(self, p):
        if p["action"] == "spawn":
            if self.spawn_error:
                return {"success": False, "error": self.spawn_error}
            w = FakeWorker(self, p["connection_id"], p["parent_instance_id"])
            self.workers[p["connection_id"]] = w
            w.start()
            assert w.ready.wait(20), "the fake worker never finished its handshake"
            return {"success": True, "pid": 1000 + len(self.workers)}
        w = self.workers.get(p.get("connection_id"))
        if w is not None:
            w.shutdown()
        return {"success": True}

    def _activate(self, p):
        if p.get("protocol_version") != "v3" or not p.get("run_id") or not p.get("session_id") or int(p.get("turn_epoch", -1)) < 0:
            return {"success": False, "error": "activate requires run_id, session_id, turn_epoch", "error_type": "invalid_params"}
        prior = self.runs.get(p["session_id"])
        if prior is not None and p["turn_epoch"] <= prior["epoch"]:
            return {"success": False, "error": f"turn_epoch {p['turn_epoch']} is not newer than {prior['epoch']}", "error_type": "stale_epoch"}
        if prior is not None:
            prior["revoked"] = True
        self.runs[p["session_id"]] = {"run_id": p["run_id"], "epoch": p["turn_epoch"], "revoked": False, "tasks": {}, "revoked_tasks": set()}
        return {"success": True, "ack": True, "run_id": p["run_id"], "turn_epoch": p["turn_epoch"], "capabilities": ["task_binding_v1"]}

    def _run(self, run_id):
        return next((r for r in self.runs.values() if r["run_id"] == run_id), None)

    def _bind(self, p):
        run = self._run(p.get("run_id"))
        if run is None:
            return {"success": False, "error": "unknown run", "error_type": "unknown_run"}
        if p.get("turn_epoch") != run["epoch"] or run["revoked"]:
            return {"success": False, "error": "stale turn_epoch", "error_type": "stale_epoch"}
        if p.get("execution_class", "worker") not in ("worker", "foreground"):
            return {"success": False, "error": "bad class", "error_type": "invalid_params"}
        run["tasks"][p["task_id"]] = int(p["fence_token"])
        return {"success": True, "execution_class": p.get("execution_class", "worker"), "foreground_tasks": 0}

    def _commit(self, p):
        if self.reject_commits:
            return {"success": False, "error": "refused for the test", "error_type": self.reject_commits}
        run = self._run(p.get("run_id"))
        if run is None:
            return {"success": False, "error": "run is not active on this client", "error_type": "unknown_run"}
        if run["revoked"] or p.get("turn_epoch") != run["epoch"]:
            return {"success": False, "error": "stale epoch", "error_type": "stale_epoch"}
        if p["task_id"] in run["revoked_tasks"]:
            return {"success": False, "error": "task was revoked", "error_type": "stale_fence"}
        bound = run["tasks"].get(p["task_id"])
        if bound is None or int(p["fence_token"]) < bound:
            return {"success": False, "error": "task is not bound / fence older", "error_type": "stale_fence"}
        art = self.artifacts.get(p["artifact_id"])
        if art is None or art["hash"] != p["content_hash"]:
            return {"success": False, "error": "artifact hash mismatch", "error_type": "hash_mismatch"}
        prev = self.ops.get(p["operation_id"])
        if prev is not None:
            if prev["hash"] != p["payload_hash"]:
                return {"success": False, "error": "operation id already used with a different payload", "error_type": "payload_mismatch"}
            return {"success": True, "state": "applied", "receipt": prev["receipt"], "replayed": True}
        target = self.parent.collections.setdefault(p["target_collection"], [])
        names = list(art["objects"])
        applied = p["collection_name"] if p["collection_name"] not in target else f"{p['collection_name']}.001"
        target.append({"collection": applied, "objects": names})
        receipt = {"created_object_names": names, "collection_name": applied, "target_collection": p["target_collection"]}
        self.ops[p["operation_id"]] = {"hash": p["payload_hash"], "state": "applied", "receipt": receipt}
        return {"success": True, "state": "applied", "receipt": receipt}

    # ---- driving a turn
    def drive(self, ws, command_id, *, max_frames=800):
        for _ in range(max_frames):
            frame = ws.receive_json()
            self.frames.append(frame)
            if "error" in frame:
                raise AssertionError(f"server answered an error during turn {command_id}: {frame!r}")
            if frame.get("method") and frame.get("id"):
                ws.send_json({"jsonrpc": "2.0", "id": frame["id"], "result": self.handle(frame)})
            if frame.get("method") == "agent.turn.ended" and frame["params"].get("turn_id") == command_id:
                return self.frames
        raise AssertionError(f"turn {command_id} never ended; last frames={self.frames[-6:]!r}")

    def close(self):
        for w in self.workers.values():
            w.shutdown()


def new_session():
    return str(uuid.uuid4())
