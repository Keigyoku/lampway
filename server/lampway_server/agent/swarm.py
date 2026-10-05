"""The swarm: several worker agents in one scene, each in its own lane scene, run by the orchestrator's tools.

How the client does it (space_mixie_chat/ARCHITECTURE.md "Scene routing per session"; main_thread_executor.py; session.py):
  * a worker's ``blender.execute_script`` carries ``session_id == agent_ctx.chat_session_id == "agentlane:<parent>:<n>"``;
    the executor switches the window to the scene whose ``mixie_session_id`` is that string, runs the script there, and
    restores the foreground scene. A lane that has no scene is REJECTED ("no scene for session"), never run in the active
    scene, so a worker cannot touch the parent by accident;
  * ``has_active_session`` maps a lane to its parent through the lane scene's ``mixar_workspace_main_session``;
  * the client runs scripts one at a time on the main thread, round-robin across lanes, so workers overlap in thinking and
    take turns in Blender: edits cannot interleave, and a worker's objects live in its own scene until they are merged.

So the server plays the orchestrator: ``swarm_start`` creates the lane scenes with ONE script on the parent session, then runs
the workers as concurrent agent loops; ``swarm_cancel`` stops one; ``swarm_collect`` waits for the rest, then merges each kept
lane into the parent scene (tagging every object with ``lw_worker``) and deletes the lanes, discarding a cancelled or failed
worker's lane. Every worker's script results are recorded against it, which is what makes each result attributable.
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional

from . import lampway_tools as lt
from .providers.base import Message, ModelRequest, Text, ToolCall, ToolSpec
from .tools import RUN_BLENDER_PYTHON, SCENE_SUMMARY, TOOLS, UnknownTool, format_tool_result, script_for

log = logging.getLogger("lampway.swarm")

MAX_WORKERS = 6
MAX_WORKER_ROUNDS = 24
LANE_SCRIPT = "swarm_lanes"
MERGE_SCRIPT = "swarm_merge"
_RESULT_CLIP = 6000


def _spec(name, description, properties, required):
    return ToolSpec(name, description, {"type": "object", "properties": properties, "required": required,
                                        "additionalProperties": False})


SWARM_SPECS = [
    _spec("swarm_start",
          "Start worker agents that each build in their OWN lane scene at the same time, one per task. Use it when the request "
          "splits into independent parts (objects, materials, checks) that do not need each other's results. Each task needs a "
          "short `name` (letters/digits) and a self-contained `prompt` (the worker sees only its prompt, not this conversation). "
          "Returns the swarm id and the workers at once; call swarm_collect to wait for them and merge their work into the scene.",
          {"tasks": {"type": "array", "description": "One entry per worker.", "items": {
              "type": "object", "properties": {"name": {"type": "string"}, "prompt": {"type": "string"}},
              "required": ["name", "prompt"], "additionalProperties": False}}}, ["tasks"]),
    _spec("swarm_status", "Where each worker of a swarm is: status, tool calls so far, objects it has created.",
          {"swarm_id": {"type": "string"}}, ["swarm_id"]),
    _spec("swarm_cancel", "Stop one worker of a running swarm; the others keep running. Its lane is discarded at collect time.",
          {"swarm_id": {"type": "string"}, "worker": {"type": "string", "description": "A worker id such as worker-2."}},
          ["swarm_id", "worker"]),
    _spec("swarm_collect", "Wait until every worker has finished, then merge each finished worker's lane into the scene and "
          "remove the lanes. Returns each worker's status, summary and the objects it created. Call it once per swarm.",
          {"swarm_id": {"type": "string"}}, ["swarm_id"]),
]
SWARM_NAMES = {s.name for s in SWARM_SPECS}


def is_swarm_tool(name: str) -> bool:
    return name in SWARM_NAMES


@dataclass
class SwarmContext:
    """What a swarm tool call knows about the turn it runs in."""
    socket: object
    session_id: str
    turn_id: str
    call_id: str
    progress: Callable[[str], None] = lambda text: None


@dataclass
class Worker:
    id: str
    name: str
    prompt: str
    lane: str
    scene_name: str
    status: str = "pending"          # pending | running | done | failed | cancelled
    tool_calls: int = 0
    created: list = field(default_factory=list)
    summary: str = ""
    error: str = ""
    task: Optional[asyncio.Task] = None

    def public(self) -> dict:
        out = {"id": self.id, "name": self.name, "lane": self.lane, "status": self.status, "tool_calls": self.tool_calls,
               "created_objects": list(self.created), "summary": self.summary}
        if self.error:
            out["error"] = self.error
        return out


@dataclass
class Swarm:
    id: str
    parent_session: str
    workers: list
    collected: bool = False


RunScript = Callable[..., Awaitable[dict]]


def worker_tools() -> list:
    """The worker's tools: Blender work and the Lampway tools; never the swarm itself and never anything that runs on the server."""
    keep = {RUN_BLENDER_PYTHON, SCENE_SUMMARY} | {s.name for s in lt.SPECS}
    return [t for t in TOOLS if t.name in keep]


def worker_system_prompt(worker: Worker) -> str:
    return (f"You are {worker.id}, one worker of a swarm that is building in Blender at the same time as other workers. "
            f"Your task is named \"{worker.name}\". You run in your OWN scene (a lane); what you create there is merged into the "
            "user's scene when you finish, so create things there and do not look for the user's other objects.\n"
            f"- Give every object you create a name that starts with `{worker.name}_` so it can be told apart from the others'.\n"
            "- Use `run_blender_python` (the data API `bpy.data` is the reliable way) and `scene_summary` to check your work. "
            "The sandbox has no os/sys/subprocess/file system.\n"
            "- Do only your task; do not wait for or coordinate with other workers. Keep it to a handful of tool calls.\n"
            "- When done, reply with ONE plain sentence saying what you made, naming the objects.")


def lane_script(parent: str, lanes: list) -> str:
    """One script on the PARENT session that creates every lane scene. The data travels as a JSON string literal, so no task
    name or prompt can change the code."""
    data = json.dumps([{"scene": w.scene_name, "lane": w.lane} for w in lanes])
    return (
        "import bpy, json\n"
        f"_lanes = json.loads({json.dumps(data)})\n"
        f"_parent = {json.dumps(parent)}\n"
        "_made = []\n"
        "for _spec in _lanes:\n"
        "    _scene = bpy.data.scenes.new(_spec['scene'])\n"
        "    _scene.mixie_session_id = _spec['lane']\n"
        "    _scene['mixar_workspace_main_session'] = _parent\n"
        "    _made.append(_scene.name)\n"
        "__RESULT__ = {'lanes': _made}\n")


def merge_script(plan: list) -> str:
    """One script on the parent session: link each kept lane's objects into the parent scene tagged with their worker, discard the
    rest, remove every lane scene."""
    data = json.dumps(plan)
    return (
        "import bpy, json\n"
        f"_plan = json.loads({json.dumps(data)})\n"
        "_parent = bpy.context.scene\n"
        "_merged = {}\n"
        "_discarded = {}\n"
        "for _w in _plan:\n"
        "    _lane = bpy.data.scenes.get(_w['scene'])\n"
        "    if _lane is None:\n"
        "        continue\n"
        "    _objects = list(_lane.collection.all_objects)\n"
        "    _colls = [_lane.collection] + list(_lane.collection.children_recursive)\n"
        "    if _w['keep']:\n"
        "        for _ob in _objects:\n"
        "            _ob['lw_worker'] = _w['id']\n"
        "            _ob['lw_worker_name'] = _w['name']\n"
        "            _parent.collection.objects.link(_ob)\n"
        "            for _c in _colls:\n"
        "                if _ob.name in _c.objects:\n"
        "                    _c.objects.unlink(_ob)\n"
        "        _merged[_w['id']] = [_ob.name for _ob in _objects]\n"
        "    else:\n"
        "        _discarded[_w['id']] = [_ob.name for _ob in _objects]\n"
        "        for _ob in _objects:\n"
        "            bpy.data.objects.remove(_ob, do_unlink=True)\n"
        "    bpy.data.scenes.remove(_lane)\n"
        "__RESULT__ = {'merged': _merged, 'discarded': _discarded}\n")


class SwarmManager:
    def __init__(self, provider_factory: Callable[[str], object], run_script: RunScript, *, max_workers: int = MAX_WORKERS):
        self.provider_factory = provider_factory
        self.run_script = run_script
        self.max_workers = max_workers
        self.swarms: dict[str, Swarm] = {}
        self._seq = 0

    # ------------------------------------------------------------- the tools
    async def call(self, name: str, arguments: dict, ctx: SwarmContext) -> tuple[str, bool]:
        arguments = arguments if isinstance(arguments, dict) else {}
        try:
            handler = {"swarm_start": self._start, "swarm_status": self._status, "swarm_cancel": self._cancel,
                       "swarm_collect": self._collect}[name]
            return json.dumps(await handler(arguments, ctx), default=str), False
        except SwarmError as exc:
            return str(exc), True
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
            clean.append((_safe_name(task["name"], i), task["prompt"]))
        self._seq += 1
        swarm_id = f"sw{self._seq}"
        workers = []
        for n, (name, prompt) in enumerate(clean, 1):
            lane = f"agentlane:{ctx.session_id}:{n}"
            workers.append(Worker(f"worker-{n}", name, prompt, lane, f"{swarm_id}_{name}"))
        swarm = Swarm(swarm_id, ctx.session_id, workers)
        result = await self.run_script(ctx.socket, session_id=ctx.session_id, chat_session_id=ctx.session_id,
                                       turn_id=ctx.turn_id, call_id=ctx.call_id, tool_name=LANE_SCRIPT,
                                       script=lane_script(ctx.session_id, workers))
        if not (isinstance(result, dict) and result.get("success")):
            raise SwarmError(f"the lane scenes could not be created: {json.dumps(result, default=str)[:400]}")
        self.swarms[swarm_id] = swarm
        for worker in workers:
            worker.status = "running"
            worker.task = asyncio.create_task(self._run_worker(swarm, worker, ctx))
        ctx.progress(f"{len(workers)} workers started")
        return {"swarm_id": swarm_id, "workers": [w.public() for w in workers]}

    async def _status(self, arguments, ctx) -> dict:
        swarm = self._get(arguments)
        return {"swarm_id": swarm.id, "collected": swarm.collected, "workers": [w.public() for w in swarm.workers]}

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
        if worker.status == "running":
            worker.status = "cancelled"
            if worker.task is not None:
                worker.task.cancel()

    async def _collect(self, arguments, ctx) -> dict:
        swarm = self._get(arguments)
        if swarm.collected:
            raise SwarmError(f"swarm {swarm.id} was already collected")
        try:
            await asyncio.gather(*(w.task for w in swarm.workers if w.task is not None), return_exceptions=True)
        except asyncio.CancelledError:                          # the orchestrator's turn was stopped: stop the workers too
            self.cancel_all(swarm)
            raise
        swarm.collected = True
        plan = [{"id": w.id, "name": w.name, "scene": w.scene_name, "keep": w.status == "done"} for w in swarm.workers]
        merge = await self.run_script(ctx.socket, session_id=ctx.session_id, chat_session_id=ctx.session_id,
                                      turn_id=ctx.turn_id, call_id=ctx.call_id, tool_name=MERGE_SCRIPT,
                                      script=merge_script(plan))
        out = {"swarm_id": swarm.id, "workers": [w.public() for w in swarm.workers],
               "merge": {k: v for k, v in (merge or {}).items() if k in ("success", "merged", "discarded", "error")}}
        if not (isinstance(merge, dict) and merge.get("success")):
            out["merge_failed"] = True
        return out

    def cancel_all(self, swarm: Swarm) -> None:
        for worker in swarm.workers:
            self.cancel_worker(worker)

    def cancel_session(self, session_id: str) -> None:
        for swarm in self.swarms.values():
            if swarm.parent_session == session_id and not swarm.collected:
                self.cancel_all(swarm)

    # ------------------------------------------------------------ one worker
    async def _run_worker(self, swarm: Swarm, worker: Worker, ctx: SwarmContext) -> None:
        provider = self.provider_factory(worker.id)
        system = worker_system_prompt(worker)
        tools = worker_tools()
        messages = [Message.user_text(worker.prompt)]
        try:
            for _round in range(MAX_WORKER_ROUNDS):
                text_parts, calls = [], []
                async for event in provider.stream(ModelRequest(system, list(messages), tools)):
                    if isinstance(event, Text):
                        text_parts.append(event.text)
                    elif isinstance(event, ToolCall):
                        calls.append(event)
                text = "".join(text_parts)
                messages.append(Message("assistant", ([{"type": "text", "text": text}] if text else []) + [
                    {"type": "tool_call", "id": c.id, "name": c.name, "arguments": c.arguments} for c in calls]))
                if not calls:
                    if not text.strip() and worker.tool_calls == 0:      # nothing said, nothing done: not a finished task
                        raise RuntimeError("the model returned an empty response")
                    worker.summary = text.strip() or "(no summary)"
                    worker.status = "done"
                    ctx.progress(f"{worker.id} ({worker.name}) done")
                    return
                results = []
                for call in calls:
                    content, is_error = await self._worker_tool(worker, ctx, call)
                    worker.tool_calls += 1
                    results.append({"type": "tool_result", "tool_call_id": call.id, "content": content, "is_error": is_error})
                messages.append(Message("user", results))
                ctx.progress(f"{worker.id} ({worker.name}): {worker.tool_calls} tool calls, {len(worker.created)} objects")
            worker.summary = "stopped after too many tool calls"
            worker.status = "failed"
            worker.error = worker.summary
        except asyncio.CancelledError:
            worker.status = "cancelled"
            raise
        except Exception as exc:  # noqa: BLE001 - one worker's failure must not end the others
            worker.status = "failed"
            worker.error = str(exc)[:500]
            log.warning("%s failed: %s", worker.id, worker.error)

    async def _worker_tool(self, worker: Worker, ctx: SwarmContext, call: ToolCall) -> tuple[str, bool]:
        try:
            script = script_for(call.name, call.arguments)
        except UnknownTool as exc:
            return str(exc), True
        result = await self.run_script(ctx.socket, session_id=worker.lane, chat_session_id=worker.lane, turn_id=ctx.turn_id,
                                       call_id=call.id, tool_name=call.name, script=script)
        if isinstance(result, dict):
            for name in result.get("created_objects") or []:
                if name not in worker.created:
                    worker.created.append(name)
        text, is_error = format_tool_result(result)
        return (text[:_RESULT_CLIP] + "...[clipped]" if len(text) > _RESULT_CLIP else text), is_error


class SwarmError(ValueError):
    pass


def _safe_name(name: str, index: int) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in name.strip())[:24].strip("_")
    return cleaned or f"task{index}"
