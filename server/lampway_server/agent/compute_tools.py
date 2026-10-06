"""The agent's compute tool: PLAN, read the state, list jobs and see the reconcile report: never submit, approve or cancel (an agent can plan; the captain confirms in the Client or the CLI). The provider
is the user's choice: with none enabled, plan says so."""
import asyncio
import json
from pathlib import Path

from ..compute import cli as CLI
from ..compute import runner as R
from .providers.base import ToolSpec

NAMES = {"lampway_compute"}
ACTIONS = ["plan", "status", "list", "reconcile_report"]


def specs() -> list:
    return [ToolSpec("lampway_compute", "Rent compute through the user's chosen provider (Boat, Modal, RunPod, fal): you can only PLAN (the priced card: worst case, caps, privacy verdict, whether a click is needed), read a job's "
                     "`status`, `list` jobs, and see the `reconcile_report` (orphans and what still bills; it re-adopts nothing for you). You cannot submit: the captain confirms in the Client or the CLI. Inputs carry a "
                     "content_class (public | synthetic | private; none means private).",
                     {"type": "object", "additionalProperties": False, "required": ["action"], "properties": {
                         "action": {"type": "string", "enum": ACTIONS},
                         "job": {"type": "object", "description": "plan: {recipe, inputs: [{path, content_class}], backend, params, max_seconds, max_usd}"},
                         "key": {"type": "string", "description": "status: the job key"}}})]


def _run(state_dir, root, arguments):
    import os
    from ..config import _default_state_dir
    ctx = CLI.Context(root=Path(root), state=Path(state_dir or os.environ.get("LAMPWAY_STATE_DIR") or _default_state_dir()))
    prefs, runner = CLI.build(ctx, own_egress=False)
    a = arguments.get("action")
    if a == "plan":
        return runner.plan(dict(arguments.get("job") or {}, origin="agent"))
    if a == "status":
        return runner.status(str(arguments.get("key") or ""))
    if a == "list":
        jobs = runner.list_jobs()
        return {"count": len(jobs), "jobs": jobs}
    if a == "reconcile_report":
        return runner.reconcile()
    raise R.Refused("action is plan, status, list or reconcile_report: an agent cannot submit, approve or cancel a spend")


async def call(state_dir, root, name: str, arguments: dict) -> tuple:
    try:
        return json.dumps(await asyncio.to_thread(_run, state_dir, root, arguments or {}), default=str), False
    except (R.Refused, KeyError, ValueError) as exc:
        return str(exc), True
    except PermissionError as exc:
        return str(exc), True
