"""Endpoint backends (specs/cloud/compute_backend_serverless_gpu.md and the fal adapter): the resource is a deployed endpoint and a job is ONE REQUEST to it. RunPod Serverless, a Modal web endpoint and
fal's queue are three request SHAPES behind one class. NOTHING here was exercised against a live provider: every path and field name below is [UNVERIFIED] and frozen in the tests' fake transport, and the
live leg of each is `needs_key` (the captain is choosing the GPU provider himself). Deploying an endpoint is the captain's step: the adapter only VERIFIES one is idle-safe (min workers 0)."""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

from . import backend as BK

INLINE_LIMIT = 10 * 1024 * 1024                    # [UNVERIFIED] inline payload limit: larger inputs are refused, not truncated


@dataclass(frozen=True)
class Shape:
    name: str
    route: str
    run: str                    # path under the endpoint base
    status: str
    cancel: str
    config: Optional[str]
    status_map: dict
    key_env: tuple
    gpu: bool
    cancel_method: str = "POST"


SHAPES = {
    "runpod": Shape("runpod", "compute:runpod", "/run", "/status/{id}", "/cancel/{id}", "/config", {"IN_QUEUE": "queued", "IN_PROGRESS": "running", "COMPLETED": "done", "FAILED": "failed", "CANCELLED": "failed", "TIMED_OUT": "failed"},
                    ("RUNPOD_API_KEY",), True),
    "modal": Shape("modal", "compute:modal", "/jobs", "/jobs/{id}", "/jobs/{id}/cancel", "/config", {"queued": "queued", "running": "running", "done": "done", "failed": "failed"}, ("MODAL_TOKEN_ID", "MODAL_TOKEN_SECRET"), True),
    "fal": Shape("fal", "fal", "", "/requests/{id}/status", "/requests/{id}/cancel", None, {"IN_QUEUE": "queued", "IN_PROGRESS": "running", "COMPLETED": "done"}, ("FAL_KEY",), False, "PUT"),
}


class EndpointBackend:
    egress_via = "transport"

    def __init__(self, shape: str, endpoints: dict, transport=None, env=None):
        """endpoints: {recipe_id: {"base_url", "rate_usd_per_s", "exec_timeout_s", "idle_timeout_s", "max_workers", "kind": "web"|"function", "image_digest"?, "setup_seconds_max"?}}"""
        self.shape, self.name, self.egress_route = SHAPES[shape], SHAPES[shape].name, SHAPES[shape].route
        self.endpoints, self.env = endpoints, env if env is not None else os.environ
        self._http = httpx.Client(transport=transport, timeout=60.0)
        self._inputs: dict = {}
        self.constraints = {"no_payload_logging": True}

    # -------------------------------------------------------------------------------------------- privacy
    def privacy_for(self, recipe, spec=None) -> BK.PrivacyDeclaration:
        cfg = self.endpoints.get(recipe.id) or {}
        if self.name == "modal":
            ok = cfg.get("kind") == "web" and recipe.no_payload_logging and not cfg.get("payload_logged")
            return BK.PrivacyDeclaration("conditional", "PROVIDERS.md Modal row: web/server endpoint payloads 'not stored: proxied directly to your container'; function calls keep inputs and outputs up to 7 days; training use unread (D9)",
                                         ("web endpoint", "no_payload_logging"), ok, "private content only through a web endpoint with no payload logging")
        return BK.PrivacyDeclaration("unknown", f"{self.name}: payload and training terms not read (decision D9)", (), False, "terms not read")

    # --------------------------------------------------------------------------------------------- plumbing
    def _headers(self) -> dict:
        vals = [self.env.get(k) for k in self.shape.key_env]
        if not all(vals):
            raise BK.Rejected(f"needs_key: no {self.name} key (set {' + '.join(self.shape.key_env)} in the environment): the live leg is skipped until the captain provides one")
        if self.name == "modal":
            return {"Modal-Key": vals[0], "Modal-Secret": vals[1]}
        return {"Authorization": ("Key " if self.name == "fal" else "Bearer ") + vals[0].replace("Bearer ", "").replace("Key ", "")}

    def _cfg(self, recipe_or_id) -> dict:
        rid = getattr(recipe_or_id, "id", recipe_or_id)
        if rid not in self.endpoints:
            raise BK.Rejected(f"no {self.name} endpoint is configured for recipe {rid!r}: deploy it yourself and add it to the backend config")
        return self.endpoints[rid]

    def _call(self, method, url, **kw):
        try:
            r = self._http.request(method, url, headers=self._headers(), **kw)
        except httpx.TimeoutException:
            raise BK.Unknown(f"{self.name} did not answer in time")
        except httpx.TransportError as exc:
            raise BK.Unknown(f"{self.name} transport error: {type(exc).__name__}")
        if r.status_code >= 400:
            cls = BK.Rejected if r.status_code < 500 and r.status_code not in (408, 429) else BK.Unknown
            raise cls(f"{self.name} answered HTTP {r.status_code}")                       # the body is never quoted
        try:
            return r.json()
        except ValueError:
            return {}

    # ---------------------------------------------------------------------------------------------- the seam
    def quote(self, spec, recipe) -> BK.Quote:
        if self.shape.gpu and recipe.hardware_gpu == "none":
            raise BK.Rejected("CPU recipe: use Boat or run locally")
        cfg = self._cfg(recipe)
        setup = int(cfg.get("setup_seconds_max", recipe.setup_seconds_max))
        ex, idle, w = int(cfg["exec_timeout_s"]), int(cfg.get("idle_timeout_s", 5)), int(cfg.get("max_workers", 1))
        ms = min(int(spec["max_seconds"]), ex)
        return BK.Quote(self.name, f"{recipe.hardware_gpu} endpoint", float(cfg["rate_usd_per_s"]), ms, setup, float(cfg["rate_usd_per_s"]) * (setup + ms + idle) * w, "documented", ms + setup + idle)

    def provision(self, spec, key, recipe, ttl) -> str:
        cfg = self._cfg(recipe)
        self._headers()                                                  # needs_key BEFORE anything is created or sent
        if self.shape.config:
            c = self._call("GET", cfg["base_url"] + self.shape.config)
            if int(c.get("min_workers", 0)) > 0:
                raise BK.Rejected("this endpoint bills while idle: set min workers to 0")
            if int(c.get("max_workers", 0)) > int(cfg.get("max_workers", 1)):
                raise BK.Rejected("this endpoint allows more workers than the configured maximum")
            want = recipe.image_digest or cfg.get("image_digest")
            if want and c.get("image_digest") != want:
                raise BK.Rejected("the endpoint's image digest differs from the recipe's: redeploy it or update the recipe")
        return f"{self.name}:{recipe.id}:{key[:8]}"

    def upload(self, ref, name, path) -> None:
        data = Path(path).read_bytes()
        if len(data) > INLINE_LIMIT:
            raise BK.Rejected(f"{name} is over the {INLINE_LIMIT // (1024 * 1024)} MB inline limit of {self.name} requests")
        self._inputs.setdefault(ref, {})[name] = base64.b64encode(data).decode()

    def run(self, ref, recipe, spec) -> str:
        cfg = self._cfg(recipe)
        key = ref.rsplit(":", 1)[1]
        ex = min(int(spec["max_seconds"]), int(cfg["exec_timeout_s"]))
        inp = {"files": self._inputs.get(ref, {}), "params": spec.get("params") or {}, "lampway_key": key}
        if self.name == "runpod":
            body = {"input": inp, "policy": {"executionTimeout": ex * 1000}}
        elif self.name == "modal":
            body = {"input": inp, "timeout_s": ex}
        else:
            body = dict(inp, timeout=ex)
        doc = self._call("POST", cfg["base_url"] + self.shape.run, json=body)
        rid = doc.get("id") or doc.get("job_id") or doc.get("request_id")
        if not rid:
            raise BK.Unknown(f"{self.name} accepted the request without an id: it is not resent")
        return str(rid)

    def _status_doc(self, ref, handle):
        cfg = self.endpoints[ref.split(":")[1]]
        return self._call("GET", cfg["base_url"] + self.shape.status.format(id=handle))

    def status(self, ref, handle=None) -> str:
        if not handle:
            return "unknown"
        st = self._status_doc(ref, handle).get("status")
        return self.shape.status_map.get(st, "unknown") if self.shape.status_map.get(st) != "queued" else "running"

    def fetch(self, ref, name, dest, handle=None) -> int:
        doc = self._status_doc(ref, handle)
        out = doc.get("output") or doc.get("result") or {}
        blob = (out.get("files") or {}).get(name) if isinstance(out, dict) else None
        if blob is None:
            raise BK.ComputeError(f"{name} is not in the {self.name} result")
        data = base64.b64decode(blob)
        Path(dest).write_bytes(data)
        return len(data)

    def teardown(self, ref, mode, handle=None) -> str:
        self._inputs.pop(ref, None)
        if handle:
            try:
                if self.status(ref, handle) == "running":
                    cfg = self.endpoints[ref.split(":")[1]]
                    self._call(self.shape.cancel_method, cfg["base_url"] + self.shape.cancel.format(id=handle))
            except BK.ComputeError:
                return "failed"
        return "done"

    def list_owned(self):
        return []                                                     # a request is not a resource: nothing here bills after it ends

    def meter(self, ref):
        return None

    def idle_report(self) -> list:
        """What reconcile reports and never edits: an endpoint with min workers above 0 bills while idle."""
        out = []
        for rid, cfg in self.endpoints.items():
            if self.shape.config:
                c = self._call("GET", cfg["base_url"] + self.shape.config)
                if int(c.get("min_workers", 0)) > 0:
                    out.append({"recipe": rid, "reason": "min workers above 0: bills while idle"})
        return out
