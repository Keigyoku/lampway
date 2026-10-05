# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Background jobs for the slow tools.

A rebuild is minutes of batch work. The heavy part runs in a thread; its ``on_done`` callback (the part that touches the
scene: loading the rebuilt mesh beside the previous one) runs on the MAIN thread, from ``pump()``, which the app's timer
calls every second (``ensure_timer``). A job never raises into its caller: failure is a state with the error text.
"""

import itertools
import threading
import time
from typing import Callable, Optional

KEEP = 20
_lock = threading.Lock()
_jobs: dict = {}
_order: list = []
_counter = itertools.count(1)


class Job:
    def __init__(self, kind: str, fn: Callable, on_done: Optional[Callable]):
        self.id = f"{kind}-{next(_counter)}"
        self.kind, self.fn, self.on_done = kind, fn, on_done
        self.state = "running"
        self.result = None
        self.error = ""
        self.finish_error = ""
        self.started = time.time()
        self.finished: Optional[float] = None
        self._handled = False
        self._thread = threading.Thread(target=self._run, name=self.id, daemon=True)

    def _run(self):
        try:
            self.result = self.fn()
            self.state = "done"
        except Exception as exc:                              # a job failure is a state, never an exception in the caller
            self.error = f"{type(exc).__name__}: {exc}"
            self.state = "failed"
        self.finished = time.time()


def reset() -> None:
    with _lock:
        _jobs.clear()
        _order.clear()


def start(kind: str, fn: Callable, on_done: Optional[Callable] = None) -> Job:
    job = Job(kind, fn, on_done)
    with _lock:
        _jobs[job.id] = job
        _order.append(job.id)
    job._thread.start()
    return job


def get(job_id: str) -> Optional[Job]:
    return _jobs.get(job_id)


def pump() -> int:
    """Run the ``on_done`` of every finished job, once, on the calling (main) thread; returns how many were handled.
    Also trims the history to the last KEEP finished jobs."""
    handled = 0
    for jid in list(_order):
        job = _jobs.get(jid)
        if job is None or job.state == "running" or job._handled:
            continue
        job._handled = True
        handled += 1
        if job.on_done is not None and job.state == "done":
            try:
                job.on_done(job)
            except Exception as exc:
                job.finish_error = f"{type(exc).__name__}: {exc}"
    with _lock:
        finished = [j for j in _order if _jobs[j].state != "running" and _jobs[j]._handled]
        for jid in finished[: max(0, len(finished) - KEEP)]:
            _order.remove(jid)
            del _jobs[jid]
    return handled


def status() -> list:
    now = time.time()
    return [{"id": j.id, "kind": j.kind, "state": j.state, "seconds": round((j.finished or now) - j.started, 1),
             "error": j.error, "finish_error": j.finish_error} for j in (_jobs[i] for i in _order)]


_timer_on = False


def ensure_timer() -> None:
    """Register the app timer that pumps finished jobs (a no-op outside Blender or when already registered)."""
    global _timer_on
    if _timer_on:
        return
    try:
        import bpy
        if not bpy.app.timers.is_registered(_tick):
            bpy.app.timers.register(_tick, first_interval=1.0, persistent=True)
        _timer_on = True
    except Exception:
        pass


def _tick():
    pump()
    return 1.0
