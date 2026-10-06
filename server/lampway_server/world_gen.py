"""splat_world, the generate half: a world model turns text or one image into a Gaussian-splat environment (an SPZ, a GLB collider and a panorama), planned
here and run only after the user's confirm (specs/mixar_docs/splat_world.md). The import half (SPZ -> PLY -> a point object) is the Client's
``api.splat_world``.

World Labs (Marble) is the only vendor the Client names, and it is not one of the captain's subscriptions: with no key configured the answer is needs_key and
the Client's World Labs tab stays hidden (no world_labs job service is registered; tests/test_job_queue.py pins its 422). The request shapes below follow the Client's wire (``{prompt, params: {mode,
lod}, image_bytes_b64}``, result files SPZ / GLB / PANO); the provider's own endpoints are [UNVERIFIED] and have only met a fake transport. Every request
is an httpx call, so it passes the egress choke point (route ``world_labs``, off until the user opts in); polling is bounded; only the user confirms."""

import base64
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx

BASE = "https://api.worldlabs.ai/v1"          # [UNVERIFIED] the provider's API root
LODS = ("low", "medium", "high")
MODES = ("text", "image")
FILE_KINDS = {"spz": "world.spz", "glb": "collider.glb", "pano": "pano.jpg"}
MAX_POLLS = 360


class WorldError(ValueError):
    pass


def _jail(root, rel) -> Path:
    full = Path(rel) if os.path.isabs(rel) else Path(root) / rel
    real_root, real = Path(os.path.realpath(root)), Path(os.path.realpath(full))
    if real != real_root and real_root not in real.parents:
        raise WorldError(f"{rel} is outside the project root")
    return real


def _validate(root, p) -> dict:
    p = p if isinstance(p, dict) else {}
    if p.get("mode") not in MODES:
        raise WorldError("mode is text or image")
    prompt = str(p.get("prompt") or "").strip()
    if not prompt or len(prompt) > 2000:
        raise WorldError("a prompt of 1..2000 characters")
    if p.get("lod") not in LODS:
        raise WorldError("lod is low, medium or high")
    image = None
    if p["mode"] == "image":
        if not p.get("image"):
            raise WorldError("mode image needs an image (a project path)")
        image = _jail(root, p["image"])
        if not image.is_file():
            raise WorldError(f"{p['image']} is not a file")
    return {"mode": p["mode"], "prompt": prompt, "lod": p["lod"], "image": str(image) if image else None}


def plan_or_needs_key(client, root, params) -> dict:
    if client is None:
        return {"state": "needs_key", "service": "world_labs",
                "error": "no world-model backend configured: World Labs is not one of the configured subscriptions; nothing was planned or sent",
                "help": ["add a World Labs key to the server's settings (the captain's decision), or use an existing splat with lampway_splat_import"]}
    return client.plan(root, params)


class WorldClient:
    def __init__(self, key: str, transport: Optional[httpx.BaseTransport] = None, base: str = BASE, poll_s: float = 10.0, timeout_s: float = 1800.0):
        if not key:
            raise WorldError("a WorldClient needs its key")
        self._key, self._transport, self.base, self.poll_s, self.timeout_s = key, transport, base.rstrip("/"), poll_s, timeout_s
        self.last_request: Optional[str] = None

    def _http(self):
        return httpx.Client(transport=self._transport, timeout=60.0)

    def plan(self, root, params) -> dict:
        clean = _validate(root, params)
        return {"state": "needs_approval", "service": "world_labs", "params": {k: v for k, v in clean.items() if k != "image"},
                "image": os.path.relpath(clean["image"], os.path.realpath(root)) if clean["image"] else None, "price": None,
                "price_note": "World Labs publishes no price Lampway can read: the cost is read back at the confirm, never estimated here",
                "how": "the user confirms this job in the Client; an agent cannot", "_clean": clean}

    def run(self, root, plan, confirmed_by: str) -> dict:
        if confirmed_by != "user":
            raise WorldError("only the user confirms a world-model job (a spend); an agent can plan it")
        clean = plan.get("_clean") or _validate(root, plan.get("params"))
        body = {"prompt": clean["prompt"], "params": {"mode": clean["mode"], "lod": clean["lod"]}}
        if clean["image"]:
            body["image_bytes_b64"] = base64.b64encode(Path(clean["image"]).read_bytes()).decode("ascii")
        self.last_request = json.dumps(body)
        headers = {"Authorization": f"Bearer {self._key}"}
        started = time.monotonic()
        with self._http() as http:
            r = http.post(f"{self.base}/worlds", json=body, headers=headers)
            if r.status_code >= 400:
                raise WorldError(f"the world model answered HTTP {r.status_code} on submit")
            job = r.json()["id"]
            for _ in range(MAX_POLLS):
                st = http.get(f"{self.base}/worlds/{job}", headers=headers).json()
                if st.get("status") == "completed":
                    break
                if st.get("status") == "failed":
                    raise WorldError(f"the world job {job} failed: {str(st.get('error'))[:200]}")
                if time.monotonic() - started > self.timeout_s:
                    raise WorldError(f"the world job {job} did not finish in {self.timeout_s:.0f} s: it is not resubmitted (a second submit is a second charge)")
                time.sleep(self.poll_s)
            else:
                raise WorldError(f"the world job {job} did not finish in {MAX_POLLS} polls: it is not resubmitted")
            out_dir = _jail(root, f"worlds/{job}")
            out_dir.mkdir(parents=True, exist_ok=True)
            files = []
            for kind, url in (st.get("files") or {}).items():
                if kind not in FILE_KINDS:
                    continue
                data = http.get(url).content
                dst = out_dir / FILE_KINDS[kind]
                dst.write_bytes(data)
                files.append({"kind": kind, "path": os.path.relpath(dst, os.path.realpath(root)), "bytes": len(data)})
        return {"job": job, "files": files, "next": "import the SPZ with lampway_splat_world_import (a splat is a point object: mesh tools refuse it)"}

