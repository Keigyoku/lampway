# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Studio service: plan -> the captain's confirm -> a server job -> files for the Client.

The shelf's AXI drivers are the engine (``LAMPWAY_STUDIO_SHELF`` = the shelf's ``tools`` directory: they are run as they are, never
rewritten); without it the bundled ports of the older drivers run. Everything that spends credits goes through ``plan`` (a driver read
back that clicks nothing, env NOT armed) and an approval only the captain can confirm; the confirmed run is the one place the arming
variable is set, for that one process. Free actions (state, clone, retry, pick, save...) run as jobs at once.
"""

import asyncio
import os
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Optional

from . import toon
from .actions import ACTIONS, ActionError
from .approvals import Approvals, ApprovalError

PKG_ROOT = str(Path(__file__).resolve().parents[2])
BUNDLED = {"tripo_mesh", "tripo_image", "tripo_texture", "tripo_fetch", "tripo_regen", "seed_db", "relief_gen"}
PLAN_TIMEOUT_S = 600.0
RUN_TIMEOUT_S = 2400.0


def default_execute(argv, env, timeout):
    p = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=timeout)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


class Engine:
    """Resolves a driver name to the command that runs it: the shelf's script when configured, else the bundled port."""

    def __init__(self, shelf: Optional[Path], python: str):
        self.shelf, self.python = (Path(shelf) if shelf else None), python

    def shelf_script(self, driver: str, studio: str = "tripo") -> Optional[Path]:
        if self.shelf is None:
            return None
        p = self.shelf / "studios" / studio / f"{driver}.py"
        return p if p.is_file() else None

    def resolve(self, driver: str, studio: str = "tripo") -> list:
        script = self.shelf_script(driver, studio)
        if script is not None:
            return [self.python, str(script)]
        if studio == "tripo" and driver in BUNDLED:
            return [self.python, "-m", f"lampway_server.studios.tripo.{driver}"]
        raise ActionError(f"the driver {driver} is not bundled: set LAMPWAY_STUDIO_SHELF to the shelf's tools directory "
                          "(the engine is the owner's own AXI drivers)")


class StudioService:
    def __init__(self, root, execute: Callable = default_execute, *, shelf=None, python: str = None, now=time.time,
                 approval_ttl: float = 600.0):
        self.root = Path(root)
        self.execute = execute
        self.engine = Engine(shelf, python or os.environ.get("LAMPWAY_PYTHON_BROWSER") or sys.executable)
        self._now = now
        self._approvals = Approvals(now, approval_ttl)
        self._jobs: dict[str, dict] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._hung: dict[str, str] = {}                 # action id -> the hung job's id, until the captain acknowledges it

    # ------------------------------------------------------------------ paths
    def jail(self, path: str) -> str:
        full = Path(path) if Path(path).is_absolute() else self.root / path
        real_root, real = Path(os.path.realpath(self.root)), Path(os.path.realpath(full))
        if real != real_root and real_root not in real.parents:
            raise ActionError(f"{path} is outside the project root")
        return str(full)

    def _dir(self, kind: str) -> str:
        d = self.root / "studio" / f"{kind}-{uuid.uuid4().hex[:8]}"
        return str(d)

    def _env(self, armed: bool) -> dict:
        env = dict(os.environ)
        env["PYTHONPATH"] = PKG_ROOT + os.pathsep + env.get("PYTHONPATH", "")
        env.pop("LAMPWAY_STUDIO_ARMED", None)           # a plan is never armed, whatever the server's own environment says
        if armed:
            env["LAMPWAY_STUDIO_ARMED"] = "1"           # the confirmed run (or a free step), for this one process
        return env

    # ------------------------------------------------------------------ plan
    async def plan(self, action_id: str, args: dict, by: str) -> dict:
        action = ACTIONS.get(action_id)
        if action is None:
            raise ActionError(f"no studio action {action_id!r}; the actions are: {sorted(ACTIONS)}")
        clean = action.validate(args if isinstance(args, dict) else {}, self.jail)
        if clean.get("paired") and self.engine.shelf_script(action.driver, action.studio) is None:
            raise ActionError("paired pieces (front + back views only) need the shelf's tripo_mesh (--views): set LAMPWAY_STUDIO_SHELF")
        if not action.needs_approval:
            job = self._start(action, clean, requested_by=by, approval=None)
            return {"state": "running", "job": self._public(job)}
        if action_id in self._hung:
            return self._refused(action, f"the earlier {action_id} job ({self._hung[action_id]}) is HUNG: reload Studio once, check the credits "
                                         "for the refund and never re-click; the captain acknowledges it before another is planned")
        argv = self.engine.resolve(action.plan_driver or action.driver, action.studio) + action.plan_args(clean, self._dir("plan") if action.needs_out_dir else "")
        out_dir = next((a for a in argv if "/plan-" in a), None)
        if out_dir:
            Path(out_dir).parent.mkdir(parents=True, exist_ok=True)
        try:
            rc, text = await asyncio.to_thread(self.execute, argv, self._env(False), PLAN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            return self._refused(action, f"the read back timed out after {PLAN_TIMEOUT_S:.0f} s")
        parsed = toon.parse(text)
        if parsed.error or rc != 0:
            return self._refused(action, parsed.error or text.strip()[-300:] or f"the driver exited {rc}")
        plan = action.read_plan(parsed, clean)
        if plan.problems:
            return self._refused(action, "; ".join(plan.problems))
        if action.guard_plan:
            why = action.guard_plan(parsed, clean)
            if why:
                return self._refused(action, why)
        if plan.price is None:
            return self._refused(action, "no price was read back from Studio, so there is nothing to approve")
        if plan.price != action.expected_price:
            return self._refused(action, f"Studio shows a price of {plan.price}, not the expected {action.expected_price}: nothing was approved")
        a = self._approvals.propose(action=action.id, studio=action.studio, label=action.label, args=clean, price=plan.price,
                                    settings=plan.settings, requested_by=by)
        return {"state": "needs_approval", "approval": a.public(self._now()),
                "message": (f"{action.label} costs {plan.price} credits. Nothing was clicked. The captain confirms or rejects it in the "
                            "Client (Studios panel); it cannot be confirmed from here.")}

    @staticmethod
    def _refused(action, reason: str) -> dict:
        return {"state": "refused", "action": action.id, "reason": reason}

    # --------------------------------------------------------------- approvals
    async def confirm(self, approval_id: str, price, by: str) -> dict:
        a = self._approvals.confirm(approval_id, price, by)
        action = ACTIONS[a.action]
        job = self._start(action, a.args, requested_by=a.requested_by, approval=a.id, armed=True)
        a.job_id = job["id"]
        return self._public(job)

    def reject(self, approval_id: str, by: str) -> dict:
        return self._approvals.reject(approval_id, by).public(self._now())

    def approvals(self) -> list:
        return [a.public(self._now()) for a in self._approvals.all()]

    # -------------------------------------------------------------------- jobs
    def _start(self, action, clean, *, requested_by: str, approval, armed: bool = True) -> dict:
        out_dir = self._dir("job")
        argv = self.engine.resolve(action.driver, action.studio) + action.run_args(clean, out_dir)
        job = {"id": Path(out_dir).name, "action": action.id, "studio": action.studio, "label": action.label, "state": "running",
               "started": self._now(), "finished": None, "kv": {}, "tables": {}, "error": "", "files": [], "approval": approval,
               "requested_by": requested_by, "_dir": out_dir, "_argv": argv}
        self._jobs[job["id"]] = job
        self._tasks[job["id"]] = asyncio.get_running_loop().create_task(self._run(job, armed))
        return job

    async def _run(self, job: dict, armed: bool) -> None:
        Path(job["_dir"]).mkdir(parents=True, exist_ok=True)
        try:
            rc, text = await asyncio.to_thread(self.execute, job["_argv"], self._env(armed), RUN_TIMEOUT_S)
        except subprocess.TimeoutExpired:
            rc, text = 1, f"error: the driver did not finish within {RUN_TIMEOUT_S:.0f} s: HUNG (never re-click)"
        except Exception as exc:  # noqa: BLE001
            rc, text = 1, f"error: could not run the driver: {type(exc).__name__}: {exc}"
        parsed = toon.parse(text)
        job.update(kv=parsed.kv, tables=parsed.tables, finished=self._now())
        if parsed.error or rc != 0:
            job["error"] = parsed.error or text.strip()[-300:]
            job["state"] = "hung" if "HUNG" in job["error"] else "failed"
            if job["state"] == "hung":
                self._hung[job["action"]] = job["id"]
        else:
            job["state"] = "done"
        d = Path(job["_dir"])
        job["files"] = sorted(({"name": p.name, "size": p.stat().st_size} for p in d.iterdir() if p.is_file() and not p.name.startswith(".")),
                              key=lambda f: f["name"]) if d.is_dir() else []

    async def wait(self, job_id: str) -> dict:
        task = self._tasks.get(job_id)
        if task is not None:
            await task
        return self._public(self._jobs[job_id])

    def acknowledge_hung(self, job_id: str, by: str) -> None:
        if by != "captain":
            raise ApprovalError("only the captain acknowledges a hung job")
        for action, jid in list(self._hung.items()):
            if jid == job_id:
                del self._hung[action]

    @staticmethod
    def _public(job: dict) -> dict:
        return {k: v for k, v in job.items() if not k.startswith("_")}

    def jobs(self) -> list:
        return [self._public(j) for j in self._jobs.values()]

    def job(self, job_id: str) -> Optional[dict]:
        j = self._jobs.get(job_id)
        return self._public(j) if j else None

    def job_file(self, job_id: str, name: str) -> Optional[Path]:
        j = self._jobs.get(job_id)
        if j is None or "/" in name or "\\" in name or name.startswith("."):
            return None
        p = Path(j["_dir"]) / name
        return p if p.is_file() else None
