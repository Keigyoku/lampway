"""ComputeRunner: the one deep module behind the verbs plan / approve / submit / status / list / cancel / reconcile. Ordering law (contract 06): the receipt exists BEFORE the paid call; a crash leaves
`submission_pending`, which reconcile turns into `submission_unknown` and NEVER re-provisions. Nothing here retries a provider call whose outcome is unknown. Cleanup runs on Exception only: a process that is
killed cannot clean up, which is exactly what reconcile is for."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import time
from pathlib import Path
from typing import Optional

from .. import egress as E
from .. import jobreceipts as JR
from ..spendpolicy import SpendPolicy
from . import backend as BK
from . import recipes as RC

LIVE_STATES = ("submitted", "running")
BACKOFF_S = 60


class Refused(ValueError):
    pass


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def _mask(ref: str) -> str:
    return f"sha256:{hashlib.sha256(ref.encode()).hexdigest()[:16]}...{ref[-6:]}"


class ComputeRunner:
    def __init__(self, root, receipts, ledger, prefs, backends: dict, clock=time.time, sleep=time.sleep, poll_s: float = 5.0, watchdog_s: float = 15.0):
        self.root, self.receipts, self.ledger, self.prefs, self.backends = Path(root), receipts, ledger, prefs, backends
        self.clock, self.sleep, self.poll_s, self.watchdog_s = clock, sleep, poll_s, watchdog_s
        self.policy = SpendPolicy(lambda: {"compute": self._spend()})

    # ------------------------------------------------------------------------------------------------ prefs/files
    def _spend(self) -> dict:
        s = self.prefs.data["spend"]
        return {"click": s["click"], "above": s.get("above"), "job_cap": s.get("job_cap")}

    def _cj_path(self, r) -> Path:
        return self.receipts._dir(r["provider"], r["key"]) / "compute.json"

    def _cj(self, r) -> dict:
        try:
            return json.loads(self._cj_path(r).read_text())
        except (OSError, ValueError):
            return {}

    def _save(self, r, cj: dict) -> None:
        p = self._cj_path(r)
        tmp = p.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(cj, fh, indent=1, sort_keys=True)
        os.replace(tmp, p)

    @property
    def _approvals_path(self) -> Path:
        return self.root / "jobs" / "compute" / "approvals.json"

    def _approvals(self) -> dict:
        try:
            return json.loads(self._approvals_path.read_text())
        except (OSError, ValueError):
            return {"plans": {}, "approvals": {}}

    def _save_approvals(self, a: dict) -> None:
        self._approvals_path.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._approvals_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(a, fh)

    # ---------------------------------------------------------------------------------------------- the job spec
    def _spec(self, job: dict) -> dict:
        try:
            recipe = RC.get(str(job.get("recipe") or ""))
        except KeyError as exc:
            raise Refused(str(exc).strip("'\""))
        ins = []
        for i in job.get("inputs") or []:
            p = Path(i["path"] if os.path.isabs(i["path"]) else self.root / i["path"])
            real = Path(os.path.realpath(p))
            if not str(real).startswith(os.path.realpath(self.root) + os.sep) or not real.is_file():
                raise Refused(f"input {i['path']} is not a file inside the project root")
            ins.append({"path": str(real), "name": real.name, "sha256": _sha(real), "bytes": real.stat().st_size, "content_class": i.get("content_class") or "private"})
        ms = int(job.get("max_seconds") or 300)
        mu = float(job.get("max_usd") if job.get("max_usd") is not None else self.prefs.data["spend"]["job_cap"])
        if not 1 <= ms <= 86400 or not 0.0001 <= mu <= 100:
            raise Refused("max_seconds is 1..86400 and max_usd is 0.0001..100")
        b = job.get("backend")
        if not b:
            raise Refused(f"pick a provider for this job: the enabled backends are {self.prefs.data['backends'] or 'none (enable one in Providers)'}")
        if b not in self.backends or b not in self.prefs.data["backends"]:
            raise Refused(f"backend {b!r} is not enabled: enabled are {self.prefs.data['backends'] or 'none'}; the user enables a provider in Providers")
        return {"recipe": recipe.id, "recipe_version": recipe.version, "inputs": ins, "params": job.get("params") or {}, "backend": b, "max_seconds": ms, "max_usd": mu,
                "origin": job.get("origin") or "user", "idempotency_key": job.get("idempotency_key")}

    @staticmethod
    def _class(spec: dict) -> str:
        return "private" if any(i["content_class"] not in ("public", "synthetic") for i in spec["inputs"]) else "synthetic"

    def _privacy(self, spec, be) -> dict:
        cls = self._class(spec)
        decl = be.privacy_for(RC.get(spec["recipe"]), spec) if hasattr(be, "privacy_for") else be.privacy
        verdict = {"content_class": cls, "backend_class": decl.cls, "conditions_met": decl.conditions_met, "evidence": decl.evidence}
        if cls == "private":
            if decl.cls == "ephemeral_verified" or (decl.cls == "conditional" and decl.conditions_met):
                if be.name not in self.prefs.data["private_backends"]:
                    raise Refused(f"this input is private and {be.name} is not in your private_backends: allow it in Providers or run it locally")
            else:
                raise Refused(f"this input is private and {be.name} is {decl.cls} ({decl.reason or 'conditions not met'}): pick a verified-ephemeral backend or run it locally")
        return verdict

    def _day_spent(self) -> float:
        today = time.strftime("%Y-%m-%d", time.localtime(self.clock()))
        total = 0.0
        for r in self.receipts.list():
            if not r["provider"].startswith("compute:"):
                continue
            cj = self._cj(r)
            if not cj.get("provisioned_at") or time.strftime("%Y-%m-%d", time.localtime(cj["provisioned_at"])) != today:
                continue
            total += max(cj.get("accrued_usd_estimate") or 0.0, cj.get("accrued_usd_meter") or 0.0, self._live_estimate(cj))
        return total

    def _live_estimate(self, cj) -> float:
        if cj.get("teardown") == "verified" or not cj.get("provisioned_at"):
            return 0.0
        return cj.get("rate_usd_per_s", 0.0) * max(0.0, self.clock() - cj["provisioned_at"])

    # ------------------------------------------------------------------------------------------------ plan/approve
    def plan(self, job: dict) -> dict:
        spec = self._spec(job)
        be, recipe = self.backends[spec["backend"]], RC.get(spec["recipe"])
        try:
            q = be.quote(spec, recipe)
        except BK.Rejected as exc:
            raise Refused(str(exc))
        privacy = self._privacy(spec, be)
        s = self.prefs.data["spend"]
        cap = min(float(s["job_cap"]), spec["max_usd"])
        if q.upper_bound_usd > cap:
            raise Refused(f"estimated worst case ${q.upper_bound_usd:.4f} is over the cap ${cap:.4f} ({q.max_seconds} s at ${q.rate_usd_per_s:g}/s): lower max_seconds or raise the cap")
        spent = self._day_spent()
        if spent + q.upper_bound_usd > float(s["day_cap"]):
            raise Refused(f"this would pass today's cap (${spent:.4f} of ${float(s['day_cap']):.2f} used, local day): wait for tomorrow or raise the cap")
        needs = q.basis == "assumed" or self.policy.needs_click("compute", q.upper_bound_usd)
        pid = hashlib.sha256(json.dumps({k: v for k, v in spec.items() if k not in ("origin",)}, sort_keys=True, default=str).encode() + f"{q.upper_bound_usd:.8f}".encode()).hexdigest()[:12]
        a = self._approvals()
        a["plans"][pid] = q.upper_bound_usd
        self._save_approvals(a)
        return {"ok": True, "plan": {"plan_id": pid, "quote": q.__dict__, "privacy": privacy, "caps": {"job_cap_usd": float(s["job_cap"]), "day_cap_usd": float(s["day_cap"]), "day_spent_usd": spent},
                                     "needs_click": needs, "uploads": {"files": len(spec["inputs"]), "bytes": sum(i["bytes"] for i in spec["inputs"])}, "hosts": [getattr(be, "egress_route", None)]}}

    def approve(self, plan_id: str, by: str) -> dict:
        if by != "user":
            raise Refused("only the user approves a spend: an agent can plan; the captain confirms in the Client")
        a = self._approvals()
        if plan_id not in a["plans"]:
            raise Refused(f"no plan {plan_id!r}: run plan first")
        aid = "ap-" + plan_id
        a["approvals"][aid] = {"plan_id": plan_id, "upper_bound_usd": a["plans"][plan_id], "at": self.clock()}
        self._save_approvals(a)
        return {"approval_id": aid, "upper_bound_usd": a["plans"][plan_id]}

    # ---------------------------------------------------------------------------------------------------- submit
    @contextlib.contextmanager
    def _gate(self, be, cj):
        route = getattr(be, "egress_route", None)
        if not route:
            yield
            return
        if getattr(be, "egress_via", "guard") == "transport":                      # an httpx adapter: the transport hook logs and lights; this only declares what the call carries
            with E.context(route=route, kind="file", asset_ids=[i["sha256"][:12] for i in cj["spec"]["inputs"]], content_class=cj["content_class"], constraints=getattr(be, "constraints", {})):
                yield
            return
        with E.guard(route, kind="file", asset_ids=[i["sha256"][:12] for i in cj["spec"]["inputs"]], content_class=cj["content_class"], constraints=getattr(be, "constraints", {})):
            yield

    def submit(self, job: dict, approval_id: Optional[str] = None) -> dict:
        origin = job.get("origin") or "user"
        if origin != "user":
            pid = self.plan(dict(job, origin="user"))["plan"]["plan_id"]
            raise Refused(f"an agent can plan; the captain confirms in the Client (plan id {pid})")
        spec = self._spec(job)
        p = self.plan(job)["plan"]
        if p["needs_click"]:
            ap = self._approvals()["approvals"].get(approval_id or "")
            if not ap or ap["plan_id"] != p["plan_id"] or abs(ap["upper_bound_usd"] - p["quote"]["upper_bound_usd"]) > 1e-12:
                raise Refused(f"this job needs the user's approval of ${p['quote']['upper_bound_usd']:.4f} (plan id {p['plan_id']}): an approval for a different price is void")
        be, recipe = self.backends[spec["backend"]], RC.get(spec["recipe"])
        payload = {"recipe": spec["recipe"], "version": spec["recipe_version"], "inputs": [(i["name"], i["sha256"]) for i in spec["inputs"]], "params": spec["params"], "backend": spec["backend"], "max_seconds": spec["max_seconds"]}
        price = {"amount": p["quote"]["upper_bound_usd"], "unit": "USD upper bound", "source": f"{be.name} rate table ({p['quote']['basis']})", "rate_usd_per_s": p["quote"]["rate_usd_per_s"]}
        r, created = self.receipts.create(f"compute:{be.name}", spec["recipe"], payload, spec["idempotency_key"], "user", price=price)
        if not created:
            return {"already_exists": True, "key": r["key"], "state": r["state"]}
        cj = {"backend": be.name, "key": r["key"], "spec": spec, "content_class": self._class(spec), "ttl": p["quote"]["ttl_seconds"], "rate_usd_per_s": p["quote"]["rate_usd_per_s"], "cap_usd": min(float(self.prefs.data["spend"]["job_cap"]), spec["max_usd"]),
              "upper_bound_usd": p["quote"]["upper_bound_usd"], "stage": "planned", "teardown": "none"}
        self._save(r, cj)
        route = getattr(be, "egress_route", None)
        if route:
            try:
                E.preflight(route)
            except PermissionError:                                              # nothing was sent: cancelled, never 'unknown'
                self.receipts.cancel(r, "egress route off")
                raise
        def send():                                                              # submit_guarded marks `submission_pending` on disk BEFORE calling this
            cj["pending_at"] = self.clock()
            self._save(r, cj)
            try:
                with self._gate(be, cj):
                    ref = be.provision(spec, r["key"], recipe, cj["ttl"])
            except BK.Rejected as exc:
                raise JR.NotSent(BK.sanitize(exc))
            except BK.Unknown as exc:
                raise BK.Unknown(BK.sanitize(exc))
            except BK.ComputeError as exc:
                raise BK.ComputeError(BK.sanitize(exc))
            cj.update(ref=ref, provisioned_at=self.clock(), stage="provisioned")
            self._save(r, cj)                                                    # the raw id lives only here (0600), never in the receipt
            return _mask(ref), {}

        JR.submit_guarded(self.receipts, r, send)
        return self._continue(r, cj)

    # ------------------------------------------------------------------------------------------------- the run
    def _tell(self, be) -> None:
        """A backend that cannot name its resources (the Boat CLI has no --name) learns which ids are ours from the receipts: ownership is the receipt set, never a guess."""
        if hasattr(be, "set_known"):
            known, pending = set(), []
            for r in self.receipts.list():
                if r["provider"] == f"compute:{be.name}":
                    cj = self._cj(r)
                    if cj.get("ref"):
                        known.add(cj["ref"])
                    elif r["state"] in ("submission_unknown", "submission_pending") and cj.get("pending_at"):
                        pending.append((r["key"], cj["pending_at"]))
            be.set_known(known, pending)

    def _watchdog(self, be, cj, ref) -> Optional[str]:
        est = self._live_estimate(cj)
        meter = None
        try:
            meter = be.meter(ref)
        except Exception:  # noqa: BLE001
            pass
        if max(est, meter or 0.0) >= cj["cap_usd"]:
            return f"stopped at the cap ${cj['cap_usd']:.4f}"
        return None

    def _continue(self, r: dict, cj: dict) -> dict:
        be, recipe = self.backends[cj["backend"]], RC.get(cj["spec"]["recipe"])
        ref, spec, error = cj["ref"], cj["spec"], cj.get("error")
        dest = self.receipts._dir(r["provider"], r["key"]) / "assets"
        try:
            if cj["stage"] in ("provisioned", "uploaded", "ran") and not error:
                if cj["stage"] == "provisioned":
                    with self._gate(be, cj):
                        for i in spec["inputs"]:
                            be.upload(ref, i["name"], i["path"])
                    cj["stage"] = "uploaded"
                    self._save(r, cj)
                if cj["stage"] == "uploaded":
                    cj.update(stage="ran", run_started_at=self.clock())
                    self._save(r, cj)                                            # intent first: run is never called twice for one receipt
                    try:
                        with self._gate(be, cj):
                            cj["handle"] = be.run(ref, recipe, spec)
                        self._save(r, cj)
                    except BK.Unknown:
                        pass                                                     # a timeout on run: poll, do not re-run
                if r["state"] == "submitted":
                    self.receipts.mark_running(r)
                error = self._poll(be, cj, r, ref)
                if not error:
                    with self._gate(be, cj):
                        error = self._fetch(be, recipe, ref, dest, r, cj)
                    if not error:
                        cj["stage"] = "fetched"
                        self._save(r, cj)
        except Exception as exc:  # noqa: BLE001
            error = BK.sanitize(exc)
        if error and not cj.get("error"):
            cj["error"] = error
            self._save(r, cj)
        self._teardown(r, cj)
        return self._finish(r, cj)

    def _poll(self, be, cj, r, ref) -> Optional[str]:
        last_wd, bad = self.clock(), 0
        while True:
            st = be.status(ref, cj.get("handle"))
            if st == "done":
                return None
            if st == "failed":
                return "the job failed on the box"
            bad = bad + 1 if st == "unknown" else 0
            if bad >= 3:
                if not cj.get("handle") and cj.get("stage") == "ran":
                    return "the run request's outcome is unknown (a timeout) and it is not resent: check the provider's console before running it again"
                return "the box stopped answering for this job"
            if self.clock() - last_wd >= self.watchdog_s:
                last_wd = self.clock()
                if (msg := self._watchdog(be, cj, ref)):
                    return msg
            if self.clock() - cj["run_started_at"] >= cj["spec"]["max_seconds"]:
                return f"max_seconds ({cj['spec']['max_seconds']} s) reached"
            self.sleep(self.poll_s)

    def _fetch(self, be, recipe, ref, dest: Path, r, cj) -> Optional[str]:
        """Outputs are fetched and verified BEFORE teardown: a stop on a no-snapshot box erases them."""
        dest.mkdir(parents=True, exist_ok=True)
        made, files = [], []
        for name in recipe.outputs:
            part, final = dest / (name + ".part"), dest / name
            try:
                n = be.fetch(ref, name, str(part), cj.get("handle"))
            except BK.ComputeError as exc:
                return f"output {name} missing: {BK.sanitize(exc)}"
            if not n:
                return f"output {name} missing or empty"
            os.replace(part, final)
            made.append(final)
            files.append({"name": name, "bytes": final.stat().st_size, "sha256": _sha(final)})
        if self.receipts.saved_result(r) is None:
            self.receipts.save_result(r, {"recipe": recipe.id, "outputs": files})
        if not r["outputs"]:
            self.receipts.attach_outputs(r, made)
        return None

    def _teardown(self, r, cj) -> None:
        if cj.get("teardown") == "verified" or not cj.get("ref"):
            return
        now = self.clock()
        if cj.get("next_teardown_at") and now < cj["next_teardown_at"]:
            return
        be, ref = self.backends[cj["backend"]], cj["ref"]
        mode = "stop" if cj["content_class"] == "private" else "delete"
        try:
            res = be.teardown(ref, mode, cj.get("handle"))
        except Exception:  # noqa: BLE001
            res = "failed"
        alive = True
        try:
            self._tell(be)
            alive = any(o.ref == ref and o.billing for o in be.list_owned())
        except Exception:  # noqa: BLE001
            pass
        cj["teardown_mode"] = mode
        meter = None
        try:
            meter = be.meter(ref)
        except Exception:  # noqa: BLE001
            pass
        if res != "failed" and not alive:
            cj.update(teardown="verified", torn_down_at=now, accrued_usd_estimate=cj["rate_usd_per_s"] * max(0.0, now - cj["provisioned_at"]), accrued_usd_meter=meter)
            cj.pop("next_teardown_at", None)
        else:
            n = cj.get("teardown_attempts", 0) + 1
            cj.update(teardown="failed", teardown_attempts=n, next_teardown_at=now + min(BACKOFF_S * 2 ** (n - 1), 3600), accrued_usd_estimate=self._live_estimate(cj), accrued_usd_meter=meter)
        self._save(r, cj)

    def _finish(self, r, cj) -> dict:
        est, meter = cj.get("accrued_usd_estimate") or 0.0, cj.get("accrued_usd_meter")
        drift = bool(meter is not None and est > 0 and abs(meter - est) / est > 0.2)
        r["price"] = {**(r.get("price") or {}), "accrued_usd_estimate": est, "accrued_usd_meter": meter, "meter_drift": drift, "source": "rate x seconds" + (" + provider meter" if meter is not None else "")}
        if r["state"] not in JR.TERMINAL:
            self.receipts._write(r)
            if cj.get("error"):
                self.receipts.mark_error(r, cj["error"], "compute")
            elif r["state"] == "completed":
                self.receipts.mark_downloaded(r)
        return {"key": r["key"], "state": r["state"], "ref": cj.get("ref"), "error": cj.get("error", ""), "teardown": cj.get("teardown"), "outputs": r.get("outputs", []), "accrued_usd_estimate": est,
                "accrued_usd_meter": meter}

    # ------------------------------------------------------------------------------------------------ reading
    def billing_now(self) -> list:
        out = []
        for r in self.receipts.list():
            if r["provider"].startswith("compute:"):
                cj = self._cj(r)
                if cj.get("ref") and cj.get("teardown") != "verified":
                    out.append({"backend": cj["backend"], "ref_suffix": cj["ref"][-6:], "since": cj.get("provisioned_at"), "rate_usd_per_s": cj["rate_usd_per_s"], "accrued_usd": self._live_estimate(cj) if cj.get("teardown") != "failed" else max(cj.get("accrued_usd_estimate") or 0.0, self._live_estimate(cj))})
        return out

    def list_jobs(self) -> list:
        return [{"key": r["key"], "backend": r["provider"].split(":", 1)[1], "recipe": r["model"], "state": r["state"], "teardown": self._cj(r).get("teardown")} for r in self.receipts.list() if r["provider"].startswith("compute:")]

    def status(self, key: str) -> dict:
        for r in self.receipts.list():
            if r["key"] == key and r["provider"].startswith("compute:"):
                cj = self._cj(r)
                return {"key": key, "state": r["state"], "backend": cj.get("backend"), "teardown": cj.get("teardown"), "error": cj.get("error", ""), "outputs": r["outputs"]}
        raise Refused(f"no compute job {key!r}")

    def cancel(self, key: str) -> dict:
        for r in self.receipts.list():
            if r["key"] == key and r["provider"].startswith("compute:"):
                cj = self._cj(r)
                if r["state"] in JR.TERMINAL:
                    return {"key": key, "state": r["state"]}
                cj["error"] = "cancelled by the user"
                self._save(r, cj)
                self._teardown(r, cj)
                if r["state"] in ("submitted", "running", "planned", "submission_pending"):
                    self.receipts.cancel(r, "cancelled by the user")
                return {"key": key, "state": r["state"], "teardown": cj.get("teardown")}
        raise Refused(f"no compute job {key!r}")

    # ----------------------------------------------------------------------------------------------- reconcile
    def reconcile(self) -> dict:
        """Once at start, every minute and on demand. Idempotent. Re-adopts, finishes and tears down; REPORTS orphans (stops them only when orphan_action is stop); never deletes; never touches a resource
        without our prefix; never re-provisions."""
        rep = {"resumed": [], "unknown": [], "completed": [], "torn_down": [], "abandoned": [], "orphans": [], "waiting": [], "skipped": [], "billing_now": []}
        owned, owned_ok = {}, {}
        for name in self.prefs.data["backends"]:
            be = self.backends.get(name)
            if be is None:
                continue
            route = getattr(be, "egress_route", None)
            try:
                if route:
                    E.preflight(route)
                self._tell(be)
                owned[name] = be.list_owned()
                owned_ok[name] = True
            except PermissionError:
                rep["skipped"].append(name)
            except Exception:  # noqa: BLE001
                rep["skipped"].append(name)
        known_refs, known_keys = set(), set()
        for r in self.receipts.list():
            if not r["provider"].startswith("compute:"):
                continue
            cj = self._cj(r)
            known_keys.add(r["key"])
            if cj.get("ref"):
                known_refs.add(cj["ref"])
        for r in self.receipts.list():
            if not r["provider"].startswith("compute:"):
                continue
            name = r["provider"].split(":", 1)[1]
            cj = self._cj(r)
            if not cj:
                continue
            if r["state"] == "submission_pending":
                self.receipts.mark_unknown(r, "process_died", "the process stopped between the write-ahead receipt and the provider's answer")
                rep["unknown"].append(r["key"])
            if r["state"] == "submission_unknown":
                ref = cj.get("ref")
                if not ref and owned_ok.get(name):
                    cands = [o for o in owned[name] if o.key == r["key"]]
                    if len(cands) == 1:
                        ref = cands[0].ref
                        cj.update(ref=ref, provisioned_at=cands[0].since, stage="provisioned", linked_by="reconcile")
                        self._save(r, cj)
                if not ref:
                    if r["key"] not in rep["unknown"]:
                        rep["waiting"].append(r["key"])
                    if owned_ok.get(name) and hasattr(self.backends[name], "candidates"):
                        rep.setdefault("candidates", {})[r["key"]] = self.backends[name].candidates(cj.get("pending_at") or 0)      # report only: the user links one, or none
                    continue
                cj.setdefault("provisioned_at", self.clock())
                self._save(r, cj)
                self.receipts._move(r, "submitted", "linked by reconcile", provider_job_id=_mask(ref))
            if r["state"] in LIVE_STATES and cj.get("ref"):
                if owned_ok.get(name) and not any(o.ref == cj["ref"] for o in owned[name]):
                    self.receipts._move(r, "abandoned", "the provider no longer lists this resource")
                    rep["abandoned"].append(r["key"])
                    continue
                if owned_ok.get(name):
                    self._continue(r, cj)
                    rep["completed" if r["state"] in JR.TERMINAL else "resumed"].append(r["key"])
                continue
            if r["state"] in JR.TERMINAL and cj.get("ref") and cj.get("teardown") != "verified" and owned_ok.get(name):
                self._teardown(r, cj)
                if self._cj(r).get("teardown") == "verified":
                    rep["torn_down"].append(r["key"])
        for name, rows in owned.items():
            for o in rows:
                if o.ref in known_refs or o.key in known_keys or not o.billing:
                    continue
                rep["orphans"].append({"backend": name, "ref_suffix": o.ref[-6:], "since": o.since, "rate_usd_per_s": o.rate_usd_per_s, "accrued_usd": o.rate_usd_per_s * max(0.0, self.clock() - o.since)})
                if self.prefs.data["orphan_action"] == "stop":
                    self.backends[name].teardown(o.ref, "stop")                      # stop only: reconcile never deletes
        rep["billing_now"] = self.billing_now() + [{"backend": o["backend"], "ref_suffix": o["ref_suffix"], "since": o["since"], "rate_usd_per_s": o["rate_usd_per_s"], "accrued_usd": o["accrued_usd"], "orphan": True} for o in rep["orphans"]]
        return rep
