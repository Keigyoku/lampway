"""The swarm: several worker agents, each in its OWN headless Blender process, on the client's execution harness (harness.py).

Mixar's client already ships this model ("harness v3"); the server speaks it:
  * ``swarm_start`` activates a run on the parent (``agent.execution.activate``), then for every task spawns a headless worker
    through the parent's sandbox supervisor, binds the task to it (``agent.execution.bind_task``) and lets the worker's brain work
    there: every worker script goes to the worker's socket on its constant routing session with a v3 envelope. Workers share nothing:
    a worker's ``bpy.data`` is its own, so the name collisions of the old in-process lane scenes cannot happen;
  * what thinks in a worker is a pane on Lampway's herdr server (``herdr/swarm_brain.py`` ``PaneBrain``, the one brain: spec S1
    and A5, no agent without a pane). The unit's mode picks the adapter the pane starts through (``harnesses.worker_adapter``):
    Mode 2 the parent pane's harness, Mode 1 Lampway's Hermes pane (A1), which starts only on a server running the engine, so
    elsewhere a Mode 1 ``swarm_start`` is refused with that help before any run is activated or any worker spawned;
  * the worker's objects reach the user's scene only through the typed ``append_collection`` commit of a worker-staged native
    artifact into the AGENT_COLLECTION (brand.py), under the client's epoch / fence / document checks, journalled PREPARED then APPLIED
    (``swarm_collect``); a refused commit fails that task, never the others;
  * the chat's ``todo`` slot carries one row per task with live status, which is what the client's Parallel Agents panel (cat avatar,
    name, task, outcome) projects (agent_panel/core/cards.py). Every swarm reports there, whoever started it: on the turn that
    handed it its stream, else on Lampway Agent's live island turn, else on a card turn of its own in its unit's scene tab
    (``swarm_island.py``); a collected swarm with a failed task offers "Retry failed tasks", and the user's click runs exactly
    those tasks again as one new swarm in the same mode (``retry``), whose outcome the unit's agent is told (``retry_note``);
  * a unit's next swarm first closes the previous runs' ENDED worker panes of that unit (spec Q13, ``_close_ended_panes``), so
    its first worker splits right of the main pane again.

A task may list ``objects``: the parent copies them to a staged artifact the worker loads first, so a worker can work ON a piece
(the QA tools); what it makes comes back the same way.

The in-process lane scenes (``agentlane:`` sessions, the lane guard) are gone: the client still supports them for its own
foreground fan-out, but this server no longer needs them for anything.
"""

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from ..brand import AGENT_COLLECTION
from . import lampway_tools as lt
from . import vault_tools
from .harness import Harness, HarnessError, export_script, import_script, reset_script, stage_script
from ..herdr import harnesses as HN
from ..herdr.swarm_brain import PaneBrain, WorkerBindings, WorkerTimeout
from .swarm_brains import WorkerJob
from .providers.base import ToolCall, ToolSpec
from .tools import RUN_BLENDER_PYTHON, SCENE_SUMMARY, TOOLS, UnknownTool, format_tool_result, script_for

log = logging.getLogger("lampway.swarm")

MAX_WORKERS = 6
_RESULT_CLIP = 6000
_CALL_LOG_MAX = 40
_CALL_LOG_CHARS = 600


def _spec(name, description, properties, required):
    return ToolSpec(name, description, {"type": "object", "properties": properties, "required": required,
                                        "additionalProperties": False})


SWARM_SPECS = [
    _spec("swarm_start",
          "Start worker agents, one per task, each in its OWN headless Blender process, all at the same time. Use it when the request "
          "splits into independent parts (pieces, objects, materials, checks) that do not need each other's results. Each task needs a "
          "short `name` (letters/digits) and a self-contained `prompt` (the worker sees only its prompt, not this conversation); "
          "`objects` lists the scene objects the worker must work on (they are copied into its scene first). Each worker shows as a "
          "card in the Parallel Agents panel. Returns the swarm id and the workers at once; call swarm_collect to wait for them and "
          f"bring their work into the scene (appended under the collection '{AGENT_COLLECTION}').",
          {"tasks": {"type": "array", "description": "One entry per worker.", "items": {
              "type": "object", "properties": {"name": {"type": "string"}, "prompt": {"type": "string"},
                                               "objects": {"type": "array", "items": {"type": "string"}}},
              "required": ["name", "prompt"], "additionalProperties": False}}}, ["tasks"]),
    _spec("swarm_status", "Where each worker of a swarm is: status, tool calls so far, objects it has created.",
          {"swarm_id": {"type": "string"}}, ["swarm_id"]),
    _spec("swarm_cancel", "Stop one worker of a running swarm; the others keep running. Nothing of it is brought into the scene.",
          {"swarm_id": {"type": "string"}, "worker": {"type": "string", "description": "A worker id such as worker-2."}},
          ["swarm_id", "worker"]),
    _spec("swarm_collect", "Wait until every worker has finished, then append each finished worker's staged result to the scene "
          f"(collection '{AGENT_COLLECTION}') and stop the workers. Returns each worker's status, summary, the objects it made and the "
          "client's receipt for each commit. Call it once per swarm.",
          {"swarm_id": {"type": "string"}}, ["swarm_id"]),
]
SWARM_NAMES = {s.name for s in SWARM_SPECS}

TODO_STATUS = {"pending": "PENDING", "running": "IN_PROGRESS", "staged": "IN_PROGRESS", "done": "DONE", "failed": "FAILED",
               "cancelled": "FAILED"}


def is_swarm_tool(name: str) -> bool:
    return name in SWARM_NAMES


@dataclass
class SwarmContext:
    """What a swarm tool call knows about the turn it runs in."""
    socket: object
    session_id: str
    turn_id: str
    call_id: str
    run_id: str = ""
    progress: Callable[[str], None] = lambda text: None
    emit_todo: Optional[Callable[[list], Awaitable]] = None      # the chat's todo slot: the Parallel Agents cards
    # The unit's mode (spec M0, S1 as superseded by A): "byoa" (Mode 2: a bound pane, or a tab in Your agent mode) runs the workers
    # on ``harness``, the parent pane's own; anything else is Mode 1 (Lampway's Hermes pane). ``session_id`` is the unit.
    mode: str = "runtime"
    harness: Optional[str] = None
    cwd: Optional[str] = None                                    # where the worker panes start (default: the cockpit's project root)
    project_root: Optional[str] = None
    owner: str = ""                                              # who started it: "pane:<cockpit id>" for a bound pane's swarm (S3)


@dataclass
class Worker:
    id: str
    name: str
    prompt: str
    objects: list = field(default_factory=list)
    connection_id: str = ""
    status: str = "pending"          # pending | running | staged | done | failed | cancelled
    tool_calls: int = 0
    created: list = field(default_factory=list)
    summary: str = ""
    error: str = ""
    error_code: str = ""
    timeout_s: Optional[float] = None
    calls: list = field(default_factory=list)       # what this worker did, for the owner (not sent to the model)
    handle: object = None
    receipt: Optional[dict] = None
    choice: Optional[dict] = None                   # the agent.worker option that served it, when it was a fallback (HC23)
    inputs_loaded: list = field(default_factory=list)
    task: Optional[asyncio.Task] = None

    def public(self) -> dict:
        out = {"id": self.id, "name": self.name, "status": self.status, "tool_calls": self.tool_calls,
               "created_objects": list(self.created), "summary": self.summary}
        if self.objects:
            out["inputs"] = list(self.objects)
        if self.error:
            out["error"] = self.error
        if self.error_code:
            out["error_code"] = self.error_code
        if self.timeout_s is not None:
            out["timeout_s"] = self.timeout_s
        if self.receipt:
            out["receipt"] = self.receipt
        if self.choice:
            out["choice"] = self.choice
        return out

    def detail(self) -> dict:
        return {**self.public(), "connection_id": self.connection_id, "calls": self.calls}


@dataclass
class Swarm:
    id: str
    parent_session: str
    workers: list
    run: object = None
    harness: object = None
    brain: object = None             # the swarm's one PaneBrain (one swarm, one adapter)
    emit_todo: Optional[Callable[[list], Awaitable]] = None
    collected: bool = False
    collected_turn: str = ""         # the turn whose swarm_collect ended it: that turn offers Retry failed tasks
    retried: bool = False            # its failed tasks were re-run once (by a Retry): they are not offered again
    retried_as: str = ""             # the swarm that re-ran them (the agent sees it in swarm_status)
    # what the swarm was started as, so a Retry runs the failed tasks the same way (spec S1: the unit's mode picks the adapter)
    mode: str = "runtime"
    harness_id: Optional[str] = None
    cwd: Optional[str] = None
    project_root: Optional[str] = None
    owner: str = ""


RunScript = Callable[..., Awaitable[dict]]


def worker_tools() -> list:
    """The worker's tools: Blender work and the Lampway tools; never the swarm itself and never anything that runs on the server."""
    keep = {RUN_BLENDER_PYTHON, SCENE_SUMMARY} | {s.name for s in lt.SPECS} | {n for n in vault_tools.NAMES if vault_tools.AUTHORITY[n] in vault_tools.GRANTS["worker"]}
    return [t for t in TOOLS if t.name in keep]


def worker_system_prompt(worker: Worker) -> str:
    inputs = (f"The objects {', '.join(worker.objects)} have been copied into your scene for you to work on. "
              if worker.objects else "Your scene starts empty. ")
    return (f"You are {worker.id}, one worker of a swarm. Your task is named \"{worker.name}\". You run in your OWN Blender process "
            "with your own scene: nothing you do can touch the user's scene or another worker's, and nothing of theirs is visible "
            f"to you. {inputs}When you finish, everything you made is brought into the user's scene automatically (appended under "
            f"the collection '{AGENT_COLLECTION}'), so you only create things and report; do not try to export or save.\n"
            f"- Name what you create so it can be told apart (start names with `{worker.name}_`).\n"
            "- Use `run_blender_python` (the data API `bpy.data` is the reliable way) and `scene_summary` to check your work. "
            "The sandbox has no os/sys/subprocess/file system.\n"
            "- Do only your task; do not wait for or coordinate with other workers. Keep it to a handful of tool calls.\n"
            "- When done, reply with ONE plain sentence saying what you made, naming the objects.")


def _head(prompt: str) -> str:
    line = prompt.strip().splitlines()[0] if prompt.strip() else ""
    return line[:90]


class SwarmManager:
    def __init__(self, run_script: RunScript, *, max_workers: int = MAX_WORKERS, script_timeout_s: float = 600.0,
                 worker_timeout_s: Optional[float] = None):
        self.run_script = run_script
        self.max_workers = max_workers
        self.script_timeout_s = script_timeout_s
        self.worker_timeout_s = worker_timeout_s
        self.swarms: dict[str, Swarm] = {}
        self._harness: dict = {}                      # parent socket -> Harness
        self.library = None                           # the Asset Vault (set by the hub)
        self.cockpit = None                           # Lampway's herdr host, where every worker's pane opens (set by the hub)
        self.bindings = WorkerBindings()              # the worker panes' bindings; the pane endpoint resolves them (mcp.py)
        self.island = None                            # agent/swarm_island.SwarmIsland: every swarm's cards in its unit's island (set by the app)
        self._seq = 0

    def worker_brain(self, ctx: SwarmContext) -> PaneBrain:
        """The swarm's one brain (spec S1 as superseded by A): a ``PaneBrain`` on the adapter the unit's mode picks. Refused, with
        help, when no herdr host is known or the adapter cannot start a pane here (Mode 1's, on a server that is not running the
        Hermes engine): never run another way."""
        try:
            harness = HN.worker_adapter(ctx.mode, ctx.harness)
        except ValueError as exc:
            raise SwarmError(f"refused: swarm_start did not run: {exc}") from None
        if self.cockpit is None:
            raise SwarmError("refused: swarm_start did not run: every worker runs in a pane on Lampway's herdr server, and this "
                             "server has no herdr host")
        if HN.is_lampway(harness) and getattr(self.cockpit, "mode1", None) is None:
            raise SwarmError(f"refused: swarm_start did not run: {HN.MODE1_UNAVAILABLE}")
        return PaneBrain(self.cockpit, harness, cwd=ctx.cwd or str(self.cockpit.project_root or "."), project_root=ctx.project_root,
                         bindings=self.bindings, timeout_s=self.worker_timeout_s)

    def harness_for(self, socket) -> Harness:
        h = self._harness.get(socket)
        if h is None:
            h = self._harness[socket] = Harness(socket, script_timeout_s=self.script_timeout_s)
        return h

    def socket_closed(self, socket) -> None:
        self._harness.pop(socket, None)
        for swarm in self.swarms.values():
            if swarm.harness is not None and swarm.harness.socket is socket and not swarm.collected:
                self.cancel_all(swarm)

    # ------------------------------------------------------------- the tools
    async def call(self, name: str, arguments: dict, ctx: SwarmContext) -> tuple[str, bool]:
        arguments = arguments if isinstance(arguments, dict) else {}
        try:
            handler = {"swarm_start": self._start, "swarm_status": self._status, "swarm_cancel": self._cancel,
                       "swarm_collect": self._collect}[name]
            return json.dumps(await handler(arguments, ctx), default=str), False
        except SwarmError as exc:
            return str(exc), True
        except HarnessError as exc:
            return f"{name} could not run: {exc}", True
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - Blender silent or gone: the model is told, the turn goes on
            return f"{name} could not run: {type(exc).__name__}: {exc}", True

    def _get(self, arguments) -> Swarm:
        swarm = self.swarms.get(str(arguments.get("swarm_id") or ""))
        if swarm is None:
            raise SwarmError(f"unknown swarm {arguments.get('swarm_id')!r}")
        return swarm

    async def _start(self, arguments, ctx) -> dict:
        tasks = arguments.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            raise SwarmError("swarm_start needs `tasks`: a non-empty list of {name, prompt}")
        if len(tasks) > self.max_workers:
            raise SwarmError(f"at most {self.max_workers} workers per swarm; got {len(tasks)}")
        clean = []
        for i, task in enumerate(tasks, 1):
            if not (isinstance(task, dict) and isinstance(task.get("name"), str) and isinstance(task.get("prompt"), str)
                    and task["name"].strip() and task["prompt"].strip()):
                raise SwarmError(f"task {i} needs a non-empty string `name` and `prompt`")
            objects = task.get("objects") or []
            if not (isinstance(objects, list) and all(isinstance(o, str) and o for o in objects)):
                raise SwarmError(f"task {i}: `objects` must be a list of object names")
            clean.append((_safe_name(task["name"], i), task["prompt"], list(dict.fromkeys(objects))))
        brain = self.worker_brain(ctx)                 # before anything runs: a refused mode activates no run and spawns no worker
        harness = self.harness_for(ctx.socket)
        run = await harness.activate(ctx.run_id or str(uuid.uuid4()), ctx.session_id)
        closed = await self._close_ended_panes(ctx)    # spec Q13: the unit's previous runs' ended worker panes, before any split
        self._seq += 1
        swarm_id = f"sw{self._seq}"
        workers = [Worker(f"worker-{n}", name, prompt, objects) for n, (name, prompt, objects) in enumerate(clean, 1)]
        swarm = Swarm(swarm_id, ctx.session_id, workers, run=run, harness=harness, brain=brain, emit_todo=ctx.emit_todo,
                      mode=ctx.mode, harness_id=ctx.harness, cwd=ctx.cwd, project_root=ctx.project_root, owner=ctx.owner)
        self.swarms[swarm_id] = swarm
        await self._todo(swarm)
        for worker in workers:
            worker.task = asyncio.create_task(self._run_worker(swarm, worker, ctx))
        ctx.progress(f"{len(workers)} workers starting")
        return {"swarm_id": swarm_id, "workers": [w.public() for w in workers], "closed_panes": closed}

    async def _close_ended_panes(self, ctx: SwarmContext) -> list:
        """Spec A4, Q13 (built 2026-10-07): a finished worker's pane stays readable until its unit's next swarm; this is that
        moment. The cockpit closes only panes Lampway opened as this unit's workers whose worker has ended
        (``Cockpit.close_ended_workers``), so the new run's first worker splits right of the main pane again. Best effort: a
        herdr that cannot be asked closes nothing and the swarm goes on. Returns what was closed (the agent is told)."""
        if self.cockpit is None or not ctx.session_id or not hasattr(self.cockpit, "close_ended_workers"):
            return []
        try:
            closed = await asyncio.to_thread(self.cockpit.close_ended_workers, ctx.session_id, self.bindings.is_live)
        except Exception as exc:  # noqa: BLE001 - herdr gone or refusing: nothing is closed, the swarm goes on
            log.warning("the unit's ended worker panes were not closed: %s", exc)
            return []
        if closed:
            ctx.progress(f"closed {len(closed)} finished worker pane(s) of the previous run")
        return [{"id": c["id"], "name": c.get("name"), "why": c.get("why")} for c in closed]

    async def _status(self, arguments, ctx) -> dict:
        swarm = self._get(arguments)
        out = {"swarm_id": swarm.id, "collected": swarm.collected, "workers": [w.public() for w in swarm.workers]}
        if swarm.retried_as:
            out["retried_as"] = swarm.retried_as                   # the user's Retry re-ran its failed tasks as that swarm
        return out

    async def _cancel(self, arguments, ctx) -> dict:
        swarm = self._get(arguments)
        worker = next((w for w in swarm.workers if w.id == arguments.get("worker")), None)
        if worker is None:
            raise SwarmError(f"unknown worker {arguments.get('worker')!r} in {swarm.id}")
        self.cancel_worker(worker)
        ctx.progress(f"{worker.id} cancelled")
        return worker.public()

    @staticmethod
    def cancel_worker(worker: Worker) -> None:
        if worker.status in ("pending", "running", "staged"):
            worker.status = "cancelled"
            if worker.task is not None:
                worker.task.cancel()

    def _task_id(self, swarm: Swarm, worker: Worker) -> str:
        return f"{swarm.id}:{worker.id}"

    async def _todo(self, swarm: Swarm, final: bool = False) -> None:
        """The chat's todo slot, whole list each time (slot_processor _apply_todo_slot replaces it): the Parallel Agents cards. A
        Mode 1 swarm on a server running Lampway Agent's front, and every swarm no turn handed a stream (a bound pane's, over MCP),
        report to the island of the unit's scene tab as it is NOW (``swarm_island``: the live island turn, else a card turn), so
        the cards follow the swarm past the turn that started it; a turn's own stream is used only without the front.
        ``final``: it is collected (the Retry chip, the card turn's end)."""
        rows = [{"id": self._task_id(swarm, w), "text": f"{w.name}: {_head(w.prompt)}"[:200], "status": TODO_STATUS[w.status]}
                for w in swarm.workers]
        try:
            if self.island is not None and (swarm.emit_todo is None or self.island.takes_over(swarm)):
                await self.island.report(swarm, rows, final=final)
            elif swarm.emit_todo is not None:
                await swarm.emit_todo(rows)
        except Exception:  # noqa: BLE001 - a closed stream must not stop the work
            log.debug("could not emit the todo slot", exc_info=True)

    async def _collect(self, arguments, ctx) -> dict:
        swarm = self._get(arguments)
        if swarm.collected:
            raise SwarmError(f"swarm {swarm.id} was already collected")
        if ctx.emit_todo is not None:
            swarm.emit_todo = ctx.emit_todo
        try:
            await asyncio.gather(*(w.task for w in swarm.workers if w.task is not None), return_exceptions=True)
        except asyncio.CancelledError:                          # the orchestrator's turn was stopped: stop the workers too
            self.cancel_all(swarm)
            raise
        swarm.collected = True
        operations = {}
        for w in swarm.workers:
            if w.status == "staged":
                await self._commit(swarm, w)
        ids = [w.handle.operation_id for w in swarm.workers if w.handle is not None and w.handle.operation_id]
        if ids:
            try:
                operations = await swarm.harness.status(ids)
            except Exception as exc:  # noqa: BLE001
                operations = {"error": str(exc)}
        await self._todo(swarm, final=True)
        await self._finish(swarm)
        return {"swarm_id": swarm.id, "workers": [w.public() for w in swarm.workers], "operations": operations,
                "target_collection": AGENT_COLLECTION}

    async def _commit(self, swarm: Swarm, worker: Worker) -> None:
        art = worker.handle.artifact or {}
        if not art.get("object_count"):
            worker.status = "done"
            worker.summary = (worker.summary + " (it made no objects, so nothing was added to the scene)").strip()
            return
        try:
            result = await swarm.harness.commit(swarm.run, worker.handle, worker.name)
            worker.receipt = result.get("receipt") or {}
            worker.created = list(worker.receipt.get("created_object_names") or worker.created)
            worker.status = "done"
        except HarnessError as exc:
            worker.status = "failed"
            worker.error = f"{exc.error_type or 'commit_refused'}: {exc}"[:500]
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            worker.status = "failed"
            worker.error = f"commit failed: {type(exc).__name__}: {exc}"[:500]

    async def _finish(self, swarm: Swarm) -> None:
        """Stop the workers; revoke the tasks, and the run once none of its swarms is still open."""
        for w in swarm.workers:
            if w.handle is not None:
                await swarm.harness.revoke(swarm.run, w.handle.task_id)
            if w.connection_id:
                await swarm.harness.shutdown_worker(w.connection_id)
        if all(s.collected for s in self.swarms.values() if s.run is swarm.run):
            await swarm.harness.revoke(swarm.run)

    def cancel_all(self, swarm: Swarm) -> None:
        for worker in swarm.workers:
            self.cancel_worker(worker)

    def failed_tasks(self, session_id: str, collected_in: Optional[str] = None) -> list:
        """The tasks of this session's collected swarms that failed (or were cancelled) and were not retried yet, as swarm_start tasks."""
        out = []
        for swarm in self.swarms.values():
            if swarm.parent_session != session_id or not swarm.collected or swarm.retried:
                continue
            if collected_in is not None and swarm.collected_turn != collected_in:
                continue
            out += [{"name": w.name, "prompt": w.prompt, **({"objects": list(w.objects)} if w.objects else {})}
                    for w in swarm.workers if w.status in ("failed", "cancelled")]
        return out

    def retryable(self, session_id: str) -> bool:
        """Whether the unit has failed tasks its cards offer to retry (collected, not retried yet)."""
        return bool(self.failed_tasks(session_id))

    async def retry(self, session_id: str, socket, *, emit_todo=None, progress=None, turn_id: str = "", run_id: str = "") -> Optional[dict]:
        """The user's "Retry failed tasks" click (the cards' chip sends the user's "continue" from the user's own Client socket: the
        callers, ``HermesFront.drive`` and ``ByoaView.send``, check that): the unit's failed tasks run again as ONE new swarm, in
        the mode, harness and folder of the swarm they failed in, and it is collected into the scene. The same rules as any swarm:
        capability ``swarm`` in force, the unit's mode picks the adapter, nothing spends. Returns what happened (None: nothing to
        retry); the caller tells the unit's agent (``retry_note``)."""
        from .. import capabilities as CAP
        sources = [s for s in self.swarms.values() if s.parent_session == session_id and s.collected and not s.retried
                   and any(w.status in ("failed", "cancelled") for w in s.workers)]
        if not sources:
            return None
        tasks = self.failed_tasks(session_id)
        out = {"retried_from": [s.id for s in sources], "tasks": [t["name"] for t in tasks]}
        refusal = CAP.check_tool("swarm_start", {"tasks": tasks}, origin="user:retry")
        if refusal is not None:
            return {**out, "error": refusal}
        last = sources[-1]
        ctx = SwarmContext(socket=socket, session_id=session_id, turn_id=turn_id or f"retry_{uuid.uuid4().hex[:8]}",
                           call_id=f"retry_{uuid.uuid4().hex[:8]}", run_id=run_id, progress=progress or (lambda text: None),
                           emit_todo=emit_todo, mode=last.mode, harness=last.harness_id, cwd=last.cwd, project_root=last.project_root,
                           owner=last.owner)
        for s in sources:
            s.retried = True                              # one click, one retry: a second click finds nothing to run again
        text, is_error = await self.call("swarm_start", {"tasks": tasks}, ctx)
        if is_error:
            for s in sources:
                s.retried = False                         # nothing ran: the cards still offer it
            return {**out, "error": text}
        swarm_id = json.loads(text)["swarm_id"]
        for s in sources:
            s.retried_as = swarm_id
        out["swarm_id"] = swarm_id
        text, is_error = await self.call("swarm_collect", {"swarm_id": swarm_id}, ctx)
        if is_error:
            out["error"] = text
        else:
            out["workers"] = json.loads(text)["workers"]
        return out

    def mark_retried(self, session_id: str) -> None:
        for swarm in self.swarms.values():
            if swarm.parent_session == session_id and swarm.collected:
                swarm.retried = True

    def cancel_session(self, session_id: str) -> None:
        for swarm in self.swarms.values():
            if swarm.parent_session == session_id and not swarm.collected:
                self.cancel_all(swarm)

    # ------------------------------------------------------------ one worker
    async def _run_worker(self, swarm: Swarm, worker: Worker, ctx: SwarmContext) -> None:
        """The substrate (spec S1): spawn, bind, reset and seed this worker's own Lampway, let the swarm's brain (its pane) think,
        then stage. The brain's only door to a scene is the job's ``call_tool``, which runs on this worker's Lampway."""
        harness, run, brain = swarm.harness, swarm.run, swarm.brain

        async def call_tool(name: str, arguments: dict) -> tuple:
            content, is_error = await self._worker_tool(swarm, worker, ctx, ToolCall(id=f"{worker.id}-{uuid.uuid4().hex[:8]}",
                                                                                     name=name, arguments=arguments or {}))
            worker.tool_calls += 1
            ctx.progress(f"{worker.id} ({worker.name}): {worker.tool_calls} tool calls, {len(worker.created)} objects")
            return content, is_error

        job = WorkerJob(worker, worker_system_prompt(worker), worker_tools(), call_tool, ctx.progress,
                        {"swarm_id": swarm.id, "session_id": ctx.session_id, "turn_id": ctx.turn_id, "workers": len(swarm.workers)})
        try:
            worker.connection_id = await harness.spawn_worker()
            worker.handle = await harness.bind_task(run, self._task_id(swarm, worker), worker.connection_id)
            worker.status = "running"
            await self._todo(swarm)
            reset = await harness.run_script(run, worker.handle, turn_id=ctx.turn_id, call_id=f"{worker.id}-reset",
                                             tool_name="swarm_reset", script=reset_script())
            if not (isinstance(reset, dict) and reset.get("success")):
                raise RuntimeError(f"{worker.id} could not clear its scene: {_clip_json(reset)}")
            if worker.objects:
                await self._seed(swarm, worker, ctx)
            worker.summary = await brain.run(job) or "(no summary)"
            await self._stage(swarm, worker, ctx)
            worker.status = "staged"
            ctx.progress(f"{worker.id} ({worker.name}) finished")
        except asyncio.CancelledError:
            worker.status = "cancelled"
            try:
                await brain.stop(job)
            finally:
                await self._todo(swarm)
            raise
        except Exception as exc:  # noqa: BLE001 - one worker's failure must not end the others
            worker.status = "failed"
            worker.error = (f"{exc.error_type}: {exc}" if isinstance(exc, HarnessError) and exc.error_type else str(exc))[:500]
            if isinstance(exc, WorkerTimeout):
                worker.error_code, worker.timeout_s = exc.code, exc.timeout_s
            log.warning("%s failed: %s", worker.id, worker.error)
            try:
                await brain.stop(job)
            except Exception:  # noqa: BLE001
                log.debug("%s: the brain did not stop cleanly", worker.id, exc_info=True)
        finally:
            if worker.status in ("failed", "cancelled"):
                if worker.handle is not None:
                    await harness.revoke(run, worker.handle.task_id)
                if worker.connection_id:
                    await harness.shutdown_worker(worker.connection_id)
                await self._todo(swarm)

    async def _seed(self, swarm: Swarm, worker: Worker, ctx: SwarmContext) -> None:
        """Copy the worker's input objects from the user's scene into its own: the parent stages them, the worker loads them."""
        artifact_id = str(uuid.uuid4())
        sent = await self.run_script(ctx.socket, session_id=ctx.session_id, chat_session_id=ctx.session_id, turn_id=ctx.turn_id,
                                     call_id=f"{worker.id}-export", tool_name="swarm_export",
                                     script=export_script(artifact_id, worker.objects))
        if not (isinstance(sent, dict) and sent.get("success")):
            raise RuntimeError(f"could not copy {', '.join(worker.objects)} for {worker.id}: {_clip_json(sent)}")
        got = await swarm.harness.run_script(swarm.run, worker.handle, turn_id=ctx.turn_id, call_id=f"{worker.id}-import",
                                             tool_name="swarm_import", script=import_script(artifact_id))
        if not (isinstance(got, dict) and got.get("success")):
            raise RuntimeError(f"{worker.id} could not load its inputs: {_clip_json(got)}")
        worker.inputs_loaded = list(got.get("object_names") or [])

    async def _stage(self, swarm: Swarm, worker: Worker, ctx: SwarmContext) -> None:
        artifact_id = str(uuid.uuid4())
        skip = list(worker.inputs_loaded)
        got = await swarm.harness.run_script(swarm.run, worker.handle, turn_id=ctx.turn_id, call_id=f"{worker.id}-stage",
                                             tool_name="swarm_stage", script=stage_script(artifact_id, worker.name, skip))
        if not (isinstance(got, dict) and got.get("success")):
            raise RuntimeError(f"{worker.id} could not stage its result: {_clip_json(got)}")
        worker.handle.artifact = got
        for name in got.get("object_names") or []:
            if name not in worker.created:
                worker.created.append(name)

    async def _worker_tool(self, swarm: Swarm, worker: Worker, ctx: SwarmContext, call: ToolCall) -> tuple[str, bool]:
        if call.name in vault_tools.NAMES:                         # the Vault runs on the server, attributed to this worker
            return await vault_tools.call(self.library, call.name, call.arguments, {"origin": "worker", "agent_id": worker.id})
        try:
            script = script_for(call.name, call.arguments)
        except UnknownTool as exc:
            return str(exc), True
        result = await swarm.harness.run_script(swarm.run, worker.handle, turn_id=ctx.turn_id, call_id=call.id,
                                                tool_name=call.name, script=script)
        created = []
        if isinstance(result, dict):
            for name in result.get("created_objects") or []:
                created.append(name)
                if name not in worker.created:
                    worker.created.append(name)
        if len(worker.calls) < _CALL_LOG_MAX:
            worker.calls.append({"tool": call.name, "script": script[:_CALL_LOG_CHARS],
                                 "success": bool(isinstance(result, dict) and result.get("success")),
                                 "error": str(result.get("error", ""))[:300] if isinstance(result, dict) else "",
                                 "created": created})
        text, is_error = format_tool_result(result)
        text = text[:_RESULT_CLIP] + "...[clipped]" if len(text) > _RESULT_CLIP else text
        return text, is_error


class SwarmError(ValueError):
    pass


def retry_note(result: Optional[dict]) -> str:
    """One line for the unit's agent after the user's Retry (nothing is hidden from the agent): what ran again and how it ended.
    No newline: a pane takes it as one typed line."""
    if not result:
        return ""
    head = (f"(Lampway: the user clicked Retry failed tasks in Lampway's island, so the failed tasks "
            f"({', '.join(result.get('tasks') or [])}) of swarm {', '.join(result.get('retried_from') or [])}")
    if result.get("error") and not result.get("swarm_id"):
        return f"{head} could not run again: {' '.join(str(result['error']).split())[:300]})"
    parts = []
    for w in result.get("workers") or []:
        made = f", made {', '.join(w.get('created_objects') or [])}" if w.get("created_objects") else ""
        why = f": {' '.join(str(w.get('error') or '').split())[:120]}" if w.get("error") else ""
        parts.append(f"{w.get('name')} {w.get('status')}{made}{why}")
    tail = f" ({' '.join(str(result['error']).split())[:200]})" if result.get("error") else ""
    return (f"{head} ran again as swarm {result.get('swarm_id')} and were collected into the scene: {'; '.join(parts) or 'no workers'}"
            f"{tail}; swarm_status {result.get('swarm_id')} has the details.)")


def _clip_json(value) -> str:
    return json.dumps(value, default=str)[:300]


def _safe_name(name: str, index: int) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip())[:24].strip("_")
    return cleaned or f"task{index}"
