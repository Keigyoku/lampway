# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Per-call cancellation: signal only this worker and the processes it owns."""
import threading


class MotionCancelled(RuntimeError):
    pass


class Cancellation:
    def __init__(self):
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._stops = set()
        self._assets = []
        self._active_commits = 0
        self._filing = {"filed": False, "spooled": False}

    def check(self):
        if self._event.is_set():
            raise MotionCancelled("motion graphics cancelled")

    def cancel(self):
        with self._lock:
            self._event.set()
            stops = list(self._stops)
        for stop in stops:
            stop()

    def on_cancel(self, stop):
        with self._lock:
            self._stops.add(stop)
            cancelled = self._event.is_set()
        if cancelled:
            stop()
        def unregister():
            with self._lock:
                self._stops.discard(stop)
        return unregister

    def record_assets(self, assets):
        with self._lock:
            for asset in assets:
                key = asset.get("id") if isinstance(asset, dict) else asset
                for index, existing in enumerate(self._assets):
                    prior = existing.get("id") if isinstance(existing, dict) else existing
                    if prior == key:
                        if isinstance(existing, dict) and isinstance(asset, dict):
                            self._assets[index] = {**existing, **asset}
                        break
                else:
                    self._assets.append(dict(asset) if isinstance(asset, dict) else asset)

    def snapshot_assets(self):
        with self._lock:
            return list(self._assets)

    def commit_owned(self, operation, *args, **kwargs):
        """Atomically admit a publication before cancellation; an admitted transaction may finish.

        No lock is held during I/O: cancel can stop owned processes while an admitted DB commit finishes.
        The caller records its committed assets before checking cancellation again.
        """
        with self._lock:
            self.check()
            self._active_commits += 1
        try:
            return operation(*args, **kwargs)
        finally:
            with self._lock:
                self._active_commits -= 1

    def record_filing(self, filed):
        self.record_assets(filed.get("assets") or [])
        with self._lock:
            self._filing = {"filed": bool(filed.get("filed")), "spooled": bool(filed.get("spooled"))}

    def snapshot_filing(self):
        with self._lock:
            assets = list(self._assets)
            return {**self._filing, "assets": assets, "partial": bool(assets) and not self._filing["filed"]}


def checkpoint(cancel):
    if cancel is not None:
        cancel.check()


def own_process(process):
    """Reserve the group's leader PID until one group stop precedes reaping.

    WNOWAIT preserves the leader's exit status and numeric identity while children may still own pipes.
    Cancellation can signal the group while normal exit observation waits; no shutdown lock is held then.
    """
    import os
    import subprocess
    import time
    state = {"lock": threading.Lock(), "wait_lock": threading.Lock(), "stopped": False}
    process._lampway_owned_group = state
    original_wait = process.wait

    def wait_owned(timeout=None):
        with state["wait_lock"]:
            if process.returncode is None and not state["stopped"]:
                if timeout is None:
                    os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT)
                else:
                    deadline = time.monotonic() + timeout
                    while os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG) is None:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            raise subprocess.TimeoutExpired(process.args, timeout)
                        time.sleep(min(0.01, remaining))
                kill_owned(process)
            return original_wait(timeout=timeout)

    process.wait = wait_owned
    return process


def kill_owned(process):
    """Stop this exact owned group once, before its reserved leader PID can be reaped/reused."""
    import os
    import signal
    state = process._lampway_owned_group
    with state["lock"]:
        if state["stopped"]:
            return
        state["stopped"] = True
        # Own wait paths stop before reaping. If an outside caller already reaped, avoid a reused numeric ID.
        if process.returncode is not None:
            return
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def run_owned(command, cancel=None, **kwargs):
    """Interrupt blocking communicate by terminating this exact owned process group."""
    import subprocess
    checkpoint(cancel)
    process = own_process(subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True, **kwargs))
    unregister = cancel.on_cancel(lambda: kill_owned(process)) if cancel is not None else None
    try:
        stdout, stderr = process.communicate()
        checkpoint(cancel)
        return subprocess.CompletedProcess(command, process.returncode, stdout, stderr)
    finally:
        if unregister is not None:
            unregister()
        kill_owned(process)
        process.wait()
