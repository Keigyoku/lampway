"""The server side of the client's execution harness ("harness v3"), as Mixar's own backend spoke it.

The client already ships the whole worker model; its code is the specification (file:line in reports/studios.md "swarm v3"):

  * a worker is its OWN headless Blender process, spawned by the parent's sandbox supervisor when the server asks with the
    ``agent.sandbox_control`` request (bootstrap/sandbox_supervisor.py handle_sandbox_control); it connects back to
    ``/api/agent/ws/{connection_id}`` with ``connection_id == "{parent_instance_id}-sbx-{n}"`` and announces
    ``role: "sandbox"`` + ``parent_instance_id`` in ``system.handshake`` (core/socket_connection.py _perform_handshake);
  * the parent keeps a run binding per chat session (modules/common/agent_execution/bindings.py): ``agent.execution.activate``
    {protocol_version "v3", run_id, session_id, turn_epoch} (a newer epoch revokes the older run), ``agent.execution.bind_task``
    {run_id, turn_epoch, task_id, generation, attempt, fence_token, worker_connection_id, execution_class}, ``agent.execution.revoke``;
  * a worker's ``blender.execute_script`` carries ``params["envelope"]`` (request.py ExecutionEnvelope) and the constant routing
    session ``agent:{connection_id}`` (identity.py), which the worker checks before it runs anything;
  * a worker stages its result as a native artifact (agent_execution/staging.py stage_collection) and the ONLY live write into the
    user's scene is the typed ``agent.execution.commit`` ``append_collection`` (commit.py), under epoch / fence / document checks,
    the journal recording PREPARED then APPLIED; ``agent.execution.status`` {operation_ids} reads the receipts back.

Everything here is protocol; the model-facing swarm tools live in swarm.py.
"""

import asyncio
import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from typing import Optional

PROTOCOL_VERSION = "v3"
TARGET_COLLECTION = "Mixie Agent"
WORKER_SUFFIX = "-sbx-"
SPAWN_TIMEOUT_S = 90.0
CONNECT_TIMEOUT_S = 90.0
RPC_TIMEOUT_S = 60.0
IDLE_TTL_S = 900


class HarnessError(RuntimeError):
    """A refusal or failure of the harness; ``error_type`` is the client's typed reason when it gave one."""

    def __init__(self, message: str, error_type: str = ""):
        super().__init__(message)
        self.error_type = error_type


def payload_hash(op: dict) -> str:
    """The commit's content address: sha256 of the canonical JSON of the operation (the client stores it per operation id and refuses
    a replay with a different one: commit.py 'payload_mismatch')."""
    return hashlib.sha256(json.dumps(op, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def next_epoch(previous: int) -> int:
    """A turn epoch strictly above ``previous`` that also survives a server restart (the client keeps the highest epoch it accepted
    per chat session in its journal and refuses anything not newer): wall-clock seconds, bumped when two runs land in one second."""
    return max(int(time.time()), previous + 1)


@dataclass
class TaskHandle:
    """One worker's task: the ids the client binds and checks every commit against."""
    task_id: str
    connection_id: str
    fence: int = 1
    generation: int = 0
    attempt: int = 1
    artifact: Optional[dict] = None       # the staging manifest, once the worker staged
    operation_id: str = ""
    receipt: Optional[dict] = None


@dataclass
class Run:
    """One activated run on the parent: the (run_id, turn_epoch) pair every later frame carries."""
    run_id: str
    session_id: str
    turn_epoch: int
    tasks: dict = field(default_factory=dict)
    revoked: bool = False


class Harness:
    """The v3 conversation with one parent client (an ``AgentSocket``)."""

    def __init__(self, socket, *, script_timeout_s: float = 600.0):
        self.socket = socket
        self.script_timeout_s = script_timeout_s
        self._worker_seq = 0
        self._epoch = 0
        self.runs: dict[str, Run] = {}

    # --------------------------------------------------------------- the run
    async def activate(self, run_id: str, session_id: str) -> Run:
        """``agent.execution.activate``: the client refuses a stale epoch and revokes this session's previous run."""
        existing = self.runs.get(run_id)
        if existing is not None and not existing.revoked:
            return existing
        epoch = self._epoch = next_epoch(self._epoch)
        result = await self._rpc("agent.execution.activate", {
            "protocol_version": PROTOCOL_VERSION, "run_id": run_id, "session_id": session_id, "turn_epoch": epoch})
        self._expect(result, "activate")
        run = self.runs[run_id] = Run(run_id, session_id, epoch)
        return run

    async def revoke(self, run: Run, task_id: Optional[str] = None) -> None:
        """``agent.execution.revoke``: with a task, that task may not commit any more; without, the whole run is revoked."""
        params = {"run_id": run.run_id}
        if task_id:
            params["task_id"] = task_id
        else:
            run.revoked = True
        try:
            await self._rpc("agent.execution.revoke", params)
        except Exception:  # noqa: BLE001 - a revoke on a socket that is gone has nothing left to stop
            pass

    # --------------------------------------------------------------- workers
    async def spawn_worker(self) -> str:
        """Ask the parent to launch a headless worker, then wait until it has connected back and said who it is."""
        self._worker_seq += 1
        parent = self.socket.instance_id
        connection_id = f"{parent}{WORKER_SUFFIX}{self._worker_seq}-{uuid.uuid4().hex[:6]}"
        result = await self._rpc("agent.sandbox_control", {
            "action": "spawn", "connection_id": connection_id, "parent_instance_id": parent, "idle_ttl_s": IDLE_TTL_S},
            timeout=SPAWN_TIMEOUT_S)
        self._expect(result, "spawn")
        worker = await self._wait_for_worker(connection_id)
        if worker is None:
            await self.shutdown_worker(connection_id)
            raise HarnessError(f"worker {connection_id} did not connect within {CONNECT_TIMEOUT_S:.0f}s "
                               "(its log is mixar_sandbox_<id>.log in the client's temp directory)", "worker_unreachable")
        return connection_id

    async def _wait_for_worker(self, connection_id: str):
        deadline = time.monotonic() + CONNECT_TIMEOUT_S
        while time.monotonic() < deadline:
            sock = self.socket.hub.sockets.get(connection_id)
            if sock is not None and sock.handshake_done:
                if getattr(sock, "role", "") != "sandbox" or getattr(sock, "parent_instance_id", "") != self.socket.instance_id:
                    return None              # not a worker of THIS parent: never driven
                return sock
            await asyncio.sleep(0.05)
        return None

    def worker_socket(self, connection_id: str):
        sock = self.socket.hub.sockets.get(connection_id)
        if sock is None:
            raise HarnessError(f"worker {connection_id} is not connected", "worker_unreachable")
        return sock

    async def shutdown_worker(self, connection_id: str) -> None:
        try:
            await self._rpc("agent.sandbox_control", {"action": "shutdown", "connection_id": connection_id})
        except Exception:  # noqa: BLE001 - the parent kills every child on exit anyway
            pass

    # ----------------------------------------------------------------- tasks
    async def bind_task(self, run: Run, task_id: str, connection_id: str) -> TaskHandle:
        """``agent.execution.bind_task``: from now on a commit for this task is refused unless its fence is not older."""
        handle = run.tasks.get(task_id) or TaskHandle(task_id, connection_id)
        handle.connection_id = connection_id
        result = await self._rpc("agent.execution.bind_task", {
            "run_id": run.run_id, "turn_epoch": run.turn_epoch, "task_id": task_id, "generation": handle.generation,
            "attempt": handle.attempt, "fence_token": handle.fence, "worker_connection_id": connection_id,
            "execution_class": "worker"})
        self._expect(result, "bind_task")
        run.tasks[task_id] = handle
        return handle

    def envelope(self, run: Run, handle: TaskHandle, operation_id: str = "") -> dict:
        """The v3 task envelope attached to a worker's ``blender.execute_script`` (request.py ExecutionEnvelope: strings are
        bounded ids, ``turn_epoch``/``task_generation`` ints; ``execution_target`` names the one worker allowed to run it)."""
        env = {"protocol_version": PROTOCOL_VERSION, "run_id": run.run_id, "session_id": run.session_id,
               "turn_epoch": run.turn_epoch, "task_id": handle.task_id, "task_generation": handle.generation,
               "attempt": str(handle.attempt), "fence_token": str(handle.fence), "execution_target": handle.connection_id}
        if operation_id:
            env["operation_id"] = operation_id
        return env

    @staticmethod
    def routing_session(connection_id: str) -> str:
        """identity.py constant_routing_session: the only routing session a worker accepts."""
        return f"agent:{connection_id}"

    async def run_script(self, run: Run, handle: TaskHandle, *, turn_id: str, call_id: str, tool_name: str, script: str) -> dict:
        """One ``blender.execute_script`` on the task's worker, with its envelope and routing session."""
        worker = self.worker_socket(handle.connection_id)
        routing = self.routing_session(handle.connection_id)
        return await worker.request("blender.execute_script", {
            "script": script, "tool_name": tool_name, "session_id": routing,
            "agent_ctx": {"chat_session_id": routing, "turn_id": turn_id, "call_id": call_id},
            "envelope": self.envelope(run, handle)}, timeout=self.script_timeout_s)

    # ------------------------------------------------------ the one live write
    async def commit(self, run: Run, handle: TaskHandle, collection_name: str, *, target: str = TARGET_COLLECTION) -> dict:
        """``agent.execution.commit`` (op append_collection): the typed write of the worker's staged artifact into the user's scene.
        The client answers {success, state: applied, receipt} or a typed refusal (stale_epoch, stale_fence, hash_mismatch, deferred...)."""
        art = handle.artifact or {}
        if not (art.get("artifact_id") and art.get("content_hash")):
            raise HarnessError(f"task {handle.task_id} staged no artifact", "artifact_missing")
        handle.operation_id = handle.operation_id or str(uuid.uuid4())
        op = {"op": "append_collection", "run_id": run.run_id, "task_id": handle.task_id, "artifact_id": art["artifact_id"],
              "content_hash": art["content_hash"], "collection_name": collection_name, "target_collection": target}
        result = await self._rpc("agent.execution.commit", {
            **op, "turn_epoch": run.turn_epoch, "generation": handle.generation, "fence_token": handle.fence,
            "operation_id": handle.operation_id, "payload_hash": payload_hash(op)})
        if not isinstance(result, dict) or not result.get("success"):
            error = result if isinstance(result, dict) else {}
            raise HarnessError(str(error.get("error") or "commit refused"), str(error.get("error_type") or ""))
        handle.receipt = result.get("receipt") or {}
        return result

    async def status(self, operation_ids: list) -> dict:
        """``agent.execution.status``: the journal's receipts for these operations (handlers.py dispatch 'status')."""
        result = await self._rpc("agent.execution.status", {"operation_ids": list(operation_ids)})
        return (result or {}).get("operations", {}) if isinstance(result, dict) else {}

    # ------------------------------------------------------------- plumbing
    async def _rpc(self, method: str, params: dict, timeout: float = RPC_TIMEOUT_S):
        return await self.socket.request(method, params, timeout=timeout)

    @staticmethod
    def _expect(result, what: str) -> dict:
        if isinstance(result, dict) and result.get("success"):
            return result
        error = result if isinstance(result, dict) else {}
        raise HarnessError(f"{what} refused by the client: {error.get('error') or result!r}", str(error.get("error_type") or ""))


# --- the trusted scripts the server runs (never model-authored): the data travels as a JSON string literal, so no task name
# --- or object name can change the code.

def stage_script(artifact_id: str, collection_name: str, skip: list) -> str:
    """Run on the WORKER at the end of its task: stage every object it made (all but the seeded inputs) as a native artifact."""
    data = json.dumps({"artifact_id": artifact_id, "collection": collection_name, "skip": list(skip)})
    return (
        "import bpy, json\n"
        "from mixar.modules.common.agent_execution import staging\n"
        f"_p = json.loads({json.dumps(data)})\n"
        "_names = [_o.name for _o in bpy.data.objects if _o.name not in set(_p['skip'])]\n"
        "__RESULT__ = staging.stage_collection(_p['artifact_id'], _p['collection'], _names)\n")


def export_script(artifact_id: str, object_names: list) -> str:
    """Run on the PARENT before a worker starts: copy the named objects (and their data) to a staged artifact the worker loads."""
    data = json.dumps({"artifact_id": artifact_id, "objects": list(object_names)})
    return (
        "import json\n"
        "from mixar.modules.common.agent_execution import staging\n"
        f"_p = json.loads({json.dumps(data)})\n"
        "__RESULT__ = staging.export_copies(_p['artifact_id'], _p['objects'])\n")


def import_script(artifact_id: str) -> str:
    """Run on the WORKER first: load the parent's exported objects into the worker's own scene."""
    data = json.dumps({"artifact_id": artifact_id})
    return (
        "import json\n"
        "from mixar.modules.common.agent_execution import staging\n"
        f"_p = json.loads({json.dumps(data)})\n"
        "__RESULT__ = staging.import_artifact(_p['artifact_id'])\n")
