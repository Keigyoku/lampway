"""FakeBackend: in-process, fully scriptable, on a fake clock. Every test of the runner runs against it, and the shared conformance behaviour of the real adapters is defined by what it does."""
from __future__ import annotations

import threading
from typing import Optional

from . import backend as BK


class FakeClock:
    def __init__(self, start: float = 1_700_000_000.0):
        self.t = float(start)

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += float(s)

    advance = sleep

    def set(self, t: float) -> None:
        self.t = float(t)


class FakeBackend:
    name = "fake"

    def __init__(self, clock: FakeClock, rate: float = 0.0001, privacy_class: str = "ephemeral_verified", conditions_met: bool = True, prefix: str = "lampway-test0001-", run_seconds: float = 12.0,
                 setup_seconds: int = 10, egress_route: Optional[str] = None, **knobs):
        self.clock, self.rate, self.prefix, self.run_seconds, self.setup_seconds, self.egress_route = clock, rate, prefix, run_seconds, setup_seconds, egress_route
        self.privacy = BK.PrivacyDeclaration(privacy_class, "fake backend", (), conditions_met, "the fake backend's declared class")
        self.constraints = {}
        self.resources: dict = {}
        self.calls: list = []
        self.provision_hook = None
        self.rate_basis = "measured"
        self.last_ttl = None
        self._n = 0
        self._lock = threading.RLock()
        # fault knobs
        self.drop_response_after_create = False
        self.provision_timeout = False
        self.provision_error = False
        self.error_text = "boom"
        self.run_timeout = False
        self.never_finish = False
        self.error_result = False
        self.teardown_fails = False
        self.stop_erases = False
        self.missing_output = False
        self.meter_factor = 1.0
        self.actual_factor = 1.0
        self.outputs = {"result.json": b'{"ok": true}'}
        for k, v in knobs.items():
            setattr(self, k, v)

    # ------------------------------------------------------------------------------------------------- helpers
    def _rec(self, verb, *a):
        with self._lock:
            self.calls.append((verb, *a))

    def add_resource(self, name, key, foreign=False, state="running") -> str:
        with self._lock:
            self._n += 1
            ref = f"fk-{self._n:06d}-{'x' if foreign else 'o'}{self._n:05d}"
            self.resources[ref] = {"ref": ref, "name": name, "key": key, "state": state, "created": self.clock.now(), "ended": None, "foreign": foreign, "finish_at": None, "files": {}, "outputs": dict(self.outputs)}
            return ref

    def accrued_usd(self, ref) -> float:
        r = self.resources[ref]
        end = r["ended"] if r["ended"] is not None else self.clock.now()
        return self.rate * self.actual_factor * max(0.0, end - r["created"])

    # ---------------------------------------------------------------------------------------------- the seam
    def quote(self, spec, recipe) -> BK.Quote:
        setup = max(self.setup_seconds, 0)
        ms = int(spec["max_seconds"])
        return BK.Quote(self.name, "fake 4 vCPU", self.rate, ms, setup, self.rate * (setup + ms), self.rate_basis, ms + setup + 60)

    def provision(self, spec, key, recipe, ttl) -> str:
        self._rec("provision", key)
        self.last_ttl = ttl
        if self.provision_hook:
            self.provision_hook()
        if self.provision_timeout:
            raise BK.Unknown("the provider did not answer in time")
        if self.provision_error:
            raise BK.ComputeError(self.error_text)
        ref = self.add_resource(self.prefix + key[:8], key)
        if self.drop_response_after_create:
            raise BK.Unknown("the response was lost after the create")
        return ref

    def upload(self, ref, name, path) -> None:
        self._rec("upload", ref, name)
        self.resources[ref]["files"][name] = True

    def run(self, ref, recipe, spec) -> str:
        self._rec("run", ref)
        r = self.resources[ref]
        r["finish_at"] = None if self.never_finish else self.clock.now() + self.run_seconds
        if self.run_timeout:
            raise BK.Unknown("the run request timed out")
        return "h-" + ref

    def status(self, ref, handle=None) -> str:
        self._rec("status", ref)
        r = self.resources.get(ref)
        if r is None or r["state"] in ("gone", "stopped"):
            return "unknown"
        if r["finish_at"] is None:
            return "running"
        if self.clock.now() >= r["finish_at"]:
            return "failed" if self.error_result else "done"
        return "running"

    def fetch(self, ref, name, dest) -> int:
        self._rec("fetch", ref, name)
        r = self.resources[ref]
        if r["state"] in ("gone", "stopped") and self.stop_erases:
            raise BK.ComputeError("the box was erased")
        if self.missing_output:
            raise BK.ComputeError(f"{name} was not produced")
        data = r["outputs"][name]
        with open(dest, "wb") as fh:
            fh.write(data)
        return len(data)

    def teardown(self, ref, mode) -> str:
        self._rec("teardown", ref, mode)
        if self.teardown_fails:
            return "failed"
        r = self.resources[ref]
        r["state"] = "stopped" if mode == "stop" else "gone"
        r["ended"] = self.clock.now()
        if mode == "stop" and self.stop_erases:
            r["outputs"] = {}
        return "done"

    def list_owned(self):
        self._rec("list_owned")
        out = []
        for r in self.resources.values():
            if r["foreign"] or not r["name"].startswith(self.prefix):
                continue
            out.append(BK.OwnedResource(r["ref"], r["name"], r["key"], r["state"], r["created"], self.rate, r["state"] == "running"))
        return out

    def meter(self, ref):
        r = self.resources.get(ref)
        return None if r is None else self.accrued_usd(ref) * self.meter_factor
