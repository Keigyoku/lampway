# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The pane brain: a swarm worker that thinks in a pane on Lampway's herdr server (docs/reports/agent-modes-spec.md S3).

It is the ONE worker brain (spec S1 and A5, captain 2026-10-07: every agent is a process in a pane; no agent runs without one), in
either mode. Saved ``agent.worker_mode`` Choices picks the runtime independently of the parent's mode (Q10): a BYOA harness,
or Lampway's Hermes pane (``lampway_hermes``, A1; refused with help until it is built). Mode 1 separately resolves ``agent.worker``'s API/model service.

The swarm's substrate (``agent/swarm.py``) spawns, binds, resets and seeds the worker's own headless Lampway, then hands this brain a
``WorkerJob``. The brain:

* opens ONE pane through that adapter, under its route (B5, inside ``Cockpit.create_session``), with the task (``job.system`` plus
  the task prompt) on the harness's own command line. The pane splits into its unit's tab (the swarm's scene session, spec A4) and
  reports itself to herdr as "Worker N · <task>";
* binds the pane to ``swarm:<swarm_id>:<worker_id>``: its own MCP config (B2's mechanism: 0600 under the Lampway root) has ONE
  Lampway server, the pane endpoint ``/api/v1/mcp/pane``, with that binding as its session header and a per-worker token as its
  bearer. The token is minted here, exists only in the pane's config (or its environment) and in this process's memory as a hash,
  and is the proof that a call comes from the pane the swarm opened. The pane gets no desktop launcher: the launcher serves the
  desktop's own UI and scene-tab tools (``mcp_bridge`` ``schema.tools()``; ``lampway_scene_switch`` re-binds a connection to a real
  scene tab), which would reach the user's scene;
* waits until the worker calls ``lampway_worker_done(summary)`` (answered by ``mcp.py``), and returns the summary. A pane that exits
  first, or a worker that runs past ``PANE_WORKER_TIMEOUT_S``, fails the task;
* on cancel or failure closes only the pane it opened (``Cockpit.end_swarm_pane`` refuses any other: law 5). A finished worker's pane
  stays open for the user to read until its unit's next swarm starts, which closes it (Q13, ``Cockpit.close_ended_workers``); its
  binding is revoked, so it can no longer reach the worker.

Every tool call of the pane runs through ``job.call_tool``, i.e. on this worker's headless Lampway, never the user's scene.
"""

import asyncio
import hashlib
import hmac
import logging
import math
import os
import secrets
from dataclasses import dataclass, field
from typing import Optional

from ..agent.providers.base import ToolSpec

log = logging.getLogger("lampway.swarm.panes")

#: Existing proposed default, not a captain ruling. Set LAMPWAY_PANE_WORKER_TIMEOUT_S to configure the worker's deadline.
PANE_WORKER_TIMEOUT_S = 1800.0
#: How often the brain looks at its pane while it waits for ``lampway_worker_done``.
POLL_S = 2.0
#: Consecutive looks that find the harness gone before the task fails (one look can land between two foreground processes).
MISSES = 2


class WorkerTimeout(RuntimeError):
    """An explicit task expiry, kept distinct from a harness failure."""
    code = "worker_timeout"

    def __init__(self, worker_id: str, timeout_s: float):
        self.timeout_s = timeout_s
        super().__init__(f"{worker_id} did not finish within {timeout_s:g}s: deadline expired; its pane never called lampway_worker_done")


def worker_timeout(setting=None) -> float:
    """Resolve once per swarm before any worker opens; an invalid setting never silently falls back."""
    value = setting if setting is not None else os.environ.get("LAMPWAY_PANE_WORKER_TIMEOUT_S", PANE_WORKER_TIMEOUT_S)
    try:
        timeout_s = float(value)
    except (TypeError, ValueError):
        timeout_s = float("nan")
    if not math.isfinite(timeout_s) or timeout_s <= 0:
        raise ValueError("LAMPWAY_PANE_WORKER_TIMEOUT_S must be a positive finite number of seconds")
    return timeout_s


WORKER_DONE = ToolSpec(
    "lampway_worker_done",
    "Finish your task: call it ONCE, when your work in your own scene is complete, with one plain sentence saying what you made "
    "(name the objects). Everything you made is then brought into the user's scene. Until you call it your work is not collected; "
    "after it you can no longer use Lampway's tools.",
    {"type": "object", "additionalProperties": False, "required": ["summary"],
     "properties": {"summary": {"type": "string", "description": "One sentence: what you made, naming the objects."}}})

DONE_INSTRUCTION = ("You work through the Lampway MCP server of this session; its tools act on YOUR scene only. When your task is "
                    "done, call the Lampway tool lampway_worker_done with your one sentence as `summary`: that is how your work reaches "
                    "the user. Do not ask the user anything; if something cannot be done, say so in the summary.")


def task_text(job) -> str:
    """What the pane starts with (spec S3): the worker's system prompt, how it finishes, then its task."""
    return f"{job.system}\n{DONE_INSTRUCTION}\n\nYour task:\n{job.worker.prompt}"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass
class WorkerBinding:
    """One worker pane's binding: ``swarm:<swarm_id>:<worker_id>`` and the job its calls run through."""
    name: str
    token_sha: str
    job: object
    done: asyncio.Future = field(repr=False)
    state: str = "live"                      # live | done | revoked

    @property
    def live(self) -> bool:
        return self.state == "live"


class WorkerBindings:
    """The live and past worker bindings of this server, by name. Only the token's hash is kept."""

    def __init__(self):
        self._by_name: dict = {}

    def issue(self, name: str, job) -> tuple:
        """A fresh token for ``name``: returns (binding, token). A name is issued once; a second issue is a bug, refused."""
        if name in self._by_name and self._by_name[name].live:
            raise ValueError(f"{name} is already bound to a live worker pane")
        token = secrets.token_urlsafe(32)
        binding = WorkerBinding(name, _sha(token), job, asyncio.get_running_loop().create_future())
        self._by_name[name] = binding
        return binding, token

    def resolve(self, name: str, token: str) -> Optional[WorkerBinding]:
        """The binding a call names, only when its bearer is that binding's own token (live or not: a finished worker is told so)."""
        b = self._by_name.get(name or "")
        if b is None or not token or not hmac.compare_digest(b.token_sha, _sha(token)):
            return None
        return b

    @staticmethod
    def finish(binding: WorkerBinding, summary: str) -> None:
        if binding.live and not binding.done.done():
            binding.done.set_result(summary)
        binding.state = "done"

    def revoke(self, name: str) -> None:
        b = self._by_name.get(name)
        if b is not None and b.live:
            b.state = "revoked"

    def is_live(self, name: str) -> bool:
        """Whether ``name`` is a live worker binding of THIS server (one it never issued, e.g. before a restart, is not)."""
        b = self._by_name.get(name or "")
        return b is not None and b.live

    def choice_for(self, name: str):
        """Trusted in-process gateway lookup, never an endpoint or bearer bypass."""
        binding = self._by_name.get(name)
        # Revocation closes the tools door. Its readable pane must still keep
        # the same model selection until the gateway token is revoked too.
        return binding.job.meta.get("choice") if binding is not None else None


class PaneBrain:
    """``WorkerBrain`` kind ``pane``, the only one: running the adapter resolved from saved worker Choices."""
    kind = "pane"

    def __init__(self, cockpit, harness: str, *, cwd: str, project_root: Optional[str], bindings: WorkerBindings, timeout_s=None,
                 choice=None, mode_choice=None):
        self.cockpit = cockpit
        self.harness = harness
        self.cwd = cwd
        self.project_root = project_root
        self.bindings = bindings
        self.timeout_s = worker_timeout(timeout_s)
        self.choice = choice
        self.mode_choice = mode_choice
        self._panes: dict = {}               # worker id -> (cockpit session id, binding name)
        self._exited: dict = {}              # worker id -> why its pane is gone (nothing to close)

    @staticmethod
    def binding_name(job) -> str:
        return f"swarm:{job.meta.get('swarm_id')}:{job.worker.id}"

    async def run(self, job) -> str:
        wid, name = job.worker.id, self.binding_name(job)
        if self.choice is not None:
            job.meta["choice"] = self.choice
        if self.mode_choice is not None:
            job.meta["mode_choice"] = self.mode_choice
        binding, token = self.bindings.issue(name, job)
        loop = asyncio.get_running_loop()
        opening = asyncio.ensure_future(asyncio.to_thread(
            self.cockpit.create_session, self.harness, f"{job.worker.name} ({job.meta.get('swarm_id')} {wid})", self.cwd,
            task=f"{job.worker.name}: {job.worker.prompt.strip()[:160]}", by="swarm", project_root=self.project_root,
            prompt=task_text(job), swarm_worker=(name, token), unit=job.meta.get("session_id"),
            display_agent=f"Worker {wid.rsplit('-', 1)[-1]} · {job.worker.name}", planned=job.meta.get("workers")))
        try:
            rec = await asyncio.shield(opening)
        except asyncio.CancelledError:
            self.bindings.revoke(name)

            def close_late(f):                # cancelled while herdr was opening it: close the pane once it exists
                if not f.cancelled() and f.exception() is None:
                    loop.run_in_executor(None, self.cockpit.end_swarm_pane, f.result()["id"], name,
                                         "closed by its swarm: the task was cancelled", True)
            opening.add_done_callback(close_late)
            raise
        except Exception as exc:  # noqa: BLE001 - the route off, herdr not running, a harness that cannot run a worker
            self.bindings.revoke(name)
            raise RuntimeError(f"{wid}'s pane could not start: {exc}") from None
        self._panes[wid] = (rec["id"], name)
        timeout_s = self.timeout_s
        job.progress(f"{wid} ({job.worker.name}): working in pane {rec['name']}; {timeout_s:g}s deadline")
        deadline, misses = loop.time() + timeout_s, 0
        try:
            while True:
                remaining = deadline - loop.time()
                if remaining <= 0:
                    expiry = WorkerTimeout(wid, timeout_s)
                    job.progress(str(expiry))
                    raise expiry
                try:
                    return await asyncio.wait_for(asyncio.shield(binding.done), min(POLL_S, remaining))
                except asyncio.TimeoutError:
                    pass
                if loop.time() >= deadline:
                    expiry = WorkerTimeout(wid, timeout_s)
                    job.progress(str(expiry))
                    raise expiry
                try:
                    alive, why = await asyncio.wait_for(asyncio.to_thread(self.cockpit.pane_alive, rec["id"]),
                                                        max(0, deadline - loop.time()))
                except asyncio.TimeoutError:
                    expiry = WorkerTimeout(wid, timeout_s)
                    job.progress(str(expiry))
                    raise expiry from None
                misses = 0 if alive else misses + 1
                if misses >= MISSES:
                    self._exited[wid] = why
                    raise RuntimeError(f"{wid}'s pane exited without calling lampway_worker_done ({why})")
        finally:
            self.bindings.revoke(name)       # done or not: the pane can no longer reach the worker's scene

    async def stop(self, job) -> None:
        """Cancel or failure: close the pane this brain opened, and only it (law 5)."""
        wid = job.worker.id
        self.bindings.revoke(self.binding_name(job))
        opened = self._panes.get(wid)
        if opened is None:
            return
        sid, name = opened
        exited = self._exited.get(wid)
        why = f"its pane exited ({exited})" if exited else ("closed by its swarm: the task was cancelled" if job.worker.status == "cancelled"
                                                           else "closed by its swarm: the task failed")
        try:
            await asyncio.to_thread(self.cockpit.end_swarm_pane, sid, name, why, exited is None)
        except Exception:  # noqa: BLE001 - herdr gone: the record is reconciled at the next start
            log.debug("%s: could not end its pane %s", wid, sid, exc_info=True)
