"""The Boat adapter, CLI mode (specs/cloud/compute_backend_boat.md): CPU-only VMs through the installed `boat` binary (called by absolute path: `boat` is a shell function in interactive shells).

The CLI cannot name a sandbox (no --name flag) and Lampway never creates a Boat API key, so ownership is the RECEIPT SET: `set_known()` tells the adapter which ids are ours, `list_owned()` returns only
those, and a box created by a lost response is reported as a CANDIDATE for the user to link, never adopted or stopped. The captain's own boxes are never touched. REST mode (names, idempotency keys) needs a
scoped key the captain creates: until then it is `needs_key`."""
from __future__ import annotations

import datetime
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Optional

from . import backend as BK

RATES_PER_HOUR = {"small": 0.018, "default": 0.036, "large": 0.072}            # docs.boat.dev/pricing.md, dated 2026-10-06 (BOAT.md section 3)
ACTIVE_STATES = ("provisioned", "cloning", "ready", "idle", "running")
KEEP_ENV = ("HOME", "PATH", "USER", "LANG", "XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME", "BOAT_API_URL", "BOAT_ORG")
WORK = "/tmp/lw"
_ID = re.compile(r"\bbx_[A-Za-z0-9]+")


def clean_env() -> dict:
    """The binary sees its own login and nothing else: no provider key of Lampway's reaches it."""
    return {k: os.environ[k] for k in KEEP_ENV if k in os.environ}


def _epoch(iso: str) -> float:
    try:
        return datetime.datetime.strptime(iso.replace("Z", "+0000"), "%Y-%m-%dT%H:%M:%S.%f%z").timestamp()
    except (ValueError, AttributeError):
        return 0.0


def default_runner(argv, timeout=60, env=None):
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, env=env if env is not None else clean_env())
    return p.returncode, p.stdout, p.stderr


class BoatCliBackend:
    name = "boat"
    egress_route = "compute:boat"
    constraints = {"snapshots": False, "noEnv": True}                           # true by construction: every box is made with --no-snapshots --no-env

    def __init__(self, binary: Optional[str] = None, runner=None, clock=None, allow_xlarge: bool = False):
        import time
        self.binary = binary or str(Path.home() / ".ascii" / "bin" / "boat")
        self.runner = runner or default_runner
        self.clock = clock or time.time
        self.allow_xlarge = allow_xlarge
        self.known: set = set()
        self.privacy = BK.PrivacyDeclaration("conditional", "BOAT.md section 6 (measured 2026-10-06: a --no-snapshots sandbox is erased by stop); Boat's own terms for content in flight are unread (decision D9)",
                                             ("snapshots:false", "noEnv:true", "outputs fetched before stop"), True, "what Boat does with content in flight and any training use is unread")

    def set_known(self, refs, pending) -> None:
        self.known = set(refs)

    # --------------------------------------------------------------------------------------------------- plumbing
    def _cli(self, verb, *args, timeout=60):
        argv = [self.binary, verb, *args, "--json", "--no-update"]
        if not Path(self.binary).exists() and self.runner is default_runner:
            raise BK.Rejected(f"the boat CLI is not at {self.binary}: install it and run `boat login` yourself (Lampway never creates a Boat key)")
        return self.runner(argv, timeout, clean_env()) if self.runner is default_runner else self.runner(argv, timeout)

    def _exec(self, ref, script, detach=False, timeout=30):
        args = [ref, "--timeout", str(timeout)] + (["--detach"] if detach else []) + ["--", "sh", "-c", script]
        return self._cli("exec", *args, timeout=timeout + 30)

    # ---------------------------------------------------------------------------------------------- the seam
    def quote(self, spec, recipe) -> BK.Quote:
        if recipe.hardware_gpu != "none":
            raise BK.Rejected("Boat has no GPU: use a serverless GPU backend or a subscription route")
        t = (spec.get("params") or {}).get("type") or recipe.type
        if t == "xlarge" and not self.allow_xlarge:
            raise BK.Rejected("xlarge needs the $100 Boat plan and allow_xlarge in the backend config (untested): use small, default or large")
        if t not in RATES_PER_HOUR:
            raise BK.Rejected(f"Boat machine type {t!r}: use small, default or large")
        rate = RATES_PER_HOUR[t] / 3600.0
        ms, setup = int(spec["max_seconds"]), int(recipe.setup_seconds_max)
        return BK.Quote("boat", f"{t} (docs.boat.dev/machines.md)", rate, ms, setup, rate * (setup + ms), "documented", ms + setup + 60)

    def provision(self, spec, key, recipe, ttl) -> str:
        t = (spec.get("params") or {}).get("type") or recipe.type
        rc, out, err = self._cli("limits")
        if rc == 0:
            try:
                d = json.loads(out)
                if not d.get("canStart", True) or int(((d.get("starts") or {}).get("minute") or {}).get("remaining", 1)) <= 0:
                    raise BK.Rejected("Boat start limit reached (12 starts a minute on the $20 plan): retry in 60 s")
            except (ValueError, TypeError):
                pass
        try:
            rc, out, err = self._cli("new", "--type", t, "--ttl", str(int(ttl)), "--no-env", "--no-snapshots", "--fail-fast", timeout=120)
        except subprocess.TimeoutExpired:
            raise BK.Unknown("boat new did not answer in time: the box may exist; it is not retried")
        m = _ID.search(out or "")
        if rc == 0 and m:
            return m.group(0)
        if "no_ready_machine" in (err or "") + (out or ""):
            raise BK.Rejected("Boat has no ready machine of that type: nothing was created or billed")
        if rc != 0 and not m and any(w in (err or "").lower() for w in ("unauthorized", "not logged in", "login", "blocked", "payment")):
            raise BK.Rejected("Boat refused the request: " + (err or "").strip().splitlines()[-1][:160])
        raise BK.Unknown("boat new ended without a sandbox id: the box may exist; it is not retried")

    def upload(self, ref, name, path) -> None:
        rc, _o, err = self._exec(ref, f"mkdir -p {WORK}/in {WORK}/out")
        if rc != 0:
            raise BK.ComputeError("could not prepare the box: " + (err or "").strip()[-160:])
        rc, _o, err = self._cli("scp", str(path), f"{ref}:{WORK}/in/{name}", timeout=600)
        if rc != 0:
            raise BK.ComputeError("upload failed: " + (err or "").strip()[-160:])

    def run(self, ref, recipe, spec) -> str:
        parts = [f"mkdir -p {WORK}/in {WORK}/out", f"cd {WORK}", "rm -f exit"]
        script = "; ".join(parts) + "; (" + ((recipe.setup + " && ") if recipe.setup else "") + recipe.entry + f"); echo $? > {WORK}/exit"
        rc, _o, err = self._exec(ref, script, detach=True)
        if rc != 0:
            raise BK.Unknown("starting the job did not answer: it is polled, not re-run")
        return "detached"

    def status(self, ref, handle=None) -> str:
        rc, out, _e = self._exec(ref, f"cat {WORK}/exit 2>/dev/null || echo running")
        if rc != 0:
            return "unknown"
        w = (out or "").strip().splitlines()[-1:] or [""]
        return "running" if w[0] == "running" else ("done" if w[0] == "0" else "failed")

    def fetch(self, ref, name, dest, handle=None) -> int:
        rc, _o, err = self._cli("scp", f"{ref}:{WORK}/out/{name}", str(dest), timeout=600)
        if rc != 0:
            raise BK.ComputeError(f"{name} could not be fetched: " + (err or "").strip()[-160:])
        return Path(dest).stat().st_size

    def teardown(self, ref, mode, handle=None) -> str:
        rc, _o, err = self._cli("stop", ref) if mode == "stop" else self._cli("delete", ref, "--yes")
        return "done" if rc == 0 or "not_found" in (err or "") else "failed"

    def _list(self) -> list:
        rc, out, err = self._cli("list", "--all")
        if rc != 0:
            raise BK.ComputeError("boat list failed: " + (err or "").strip()[-120:])
        try:
            return json.loads(out).get("sandboxes") or []
        except ValueError:
            raise BK.ComputeError("boat list answered with something that is not JSON")

    def list_owned(self):
        rate = RATES_PER_HOUR["default"] / 3600.0
        return [BK.OwnedResource(s["id"], s.get("name") or "", None, s.get("state") or "", _epoch(s.get("createdAt")), RATES_PER_HOUR.get(s.get("type"), 0.036) / 3600.0 or rate, (s.get("state") in ACTIVE_STATES))
                for s in self._list() if s.get("id") in self.known]

    def candidates(self, since: float) -> list:
        """Boxes that appeared after a lost create and that no receipt owns: REPORTED for the user to link. Never adopted, never stopped."""
        return [{"id": s["id"], "state": s.get("state"), "created_at": s.get("createdAt")} for s in self._list()
                if s.get("id") not in self.known and s.get("state") in ACTIVE_STATES and _epoch(s.get("createdAt")) >= since - 10]

    def meter(self, ref):
        rc, out, _e = self._cli("usage", ref)
        if rc != 0:
            return None
        try:
            d = json.loads(out)
            return float(d["dollars"]) if "dollars" in d else None
        except (ValueError, KeyError, TypeError):
            return None
