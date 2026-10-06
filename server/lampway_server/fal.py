"""fal.ai gateway (specs/mrmak/12): a queue provider behind the write-ahead job receipts.

The REST paths below are [UNVERIFIED] against the live service (no key here): they are isolated in the ``_URL_*`` constants, the tests drive them against a fake transport, and the
live test is a ``needs_key`` skip. Order of every paid call: schema pre-flight -> a price WITH a source -> the per-job cap -> the receipt (``planned``) -> ``mark_pending`` ->
the POST. Nothing is retried: a dropped response leaves ``submission_unknown`` and a second submit with the same key returns that receipt. An agent cannot confirm a spend."""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Optional

import httpx

from . import jobreceipts as JR

PROVIDER = "fal"
_URL_QUEUE = "https://queue.fal.run/"
_URL_SCHEMA = "https://fal.ai/api/openapi/queue/openapi.json"
_URL_PRICE = "https://api.fal.ai/v1/models/pricing"
_URL_UPLOAD = "https://rest.alpha.fal.ai/storage/upload/initiate"
_STATUS = {"IN_QUEUE": "queued", "IN_PROGRESS": "running", "COMPLETED": "completed"}
_REF_FIELDS = ("image_urls", "image_url")


class FalError(ValueError):
    pass


class FalRejected(FalError, JR.NotSent):
    """A 4xx answer: the provider refused the request, so nothing was accepted."""


def map_status(body) -> str:
    return _STATUS.get(str((body or {}).get("status", "")).upper(), "unknown")


def _clean_key(raw: str) -> str:
    raw = (raw or "").strip()
    for p in ("Bearer ", "Key "):
        if raw.startswith(p):
            raw = raw[len(p):].strip()
    return raw


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


class FalClient:
    def __init__(self, root, receipts, key: Optional[str] = None, transport=None, max_job_usd: float = 5.0):
        if receipts is None:
            raise FalError("fal needs job receipts: a paid fal job must survive a restart")
        self.root, self.receipts, self.max_job_usd = Path(root), receipts, float(max_job_usd)
        self._key, self._http = key, httpx.Client(transport=transport, timeout=30.0)
        self._uploads = self.root / "fal" / "uploads.json"

    # ----------------------------------------------------------------------------------------------------- plumbing
    def _auth(self) -> dict:
        k = _clean_key(self._key or "")
        if not k:                                       # Connections: FAL_KEY / FALAI_KEY, else an owner-only FAL_KEY_FILE (C8), else a saved key
            from . import connections as C
            try:
                k = C.secret_of(C.credential("fal"))
            except C.Refused as exc:
                raise FalError(f"no fal key: set FAL_KEY in the environment or a key file (FAL_KEY_FILE, owner-only), or connect fal in Connections ({exc})") from None
        return {"authorization": f"Key {k}"}

    def _call(self, method: str, url: str, **kw) -> dict:
        r = self._http.request(method, url, headers=self._auth(), **kw)                   # a transport error propagates as-is (the caller decides what it means)
        if r.status_code >= 400:                                                          # the body is never quoted: it can carry signed URLs or echoed keys
            cls = FalRejected if r.status_code < 500 and r.status_code not in (408, 429) else FalError
            raise cls(f"fal answered HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            return {}

    # ---------------------------------------------------------------------------------------------------- schema/price
    def schema(self, endpoint: str) -> dict:
        doc = self._call("GET", _URL_SCHEMA, params={"endpoint_id": endpoint})
        schemas = (doc.get("components") or {}).get("schemas") or {}
        pick = lambda suffix: next((v for k, v in schemas.items() if k.endswith(suffix)), {})  # noqa: E731
        return {"input": pick("Input"), "output": pick("Output")}

    def _check_input(self, endpoint: str, inp: dict) -> dict:
        s = self.schema(endpoint)["input"]
        props = s.get("properties") or {}
        for k, v in inp.items():
            if k not in props:
                raise FalError(f"{endpoint} does not take '{k}': it takes {', '.join(sorted(props))}")
            enum = props[k].get("enum")
            if enum and v not in enum:
                raise FalError(f"{endpoint} field '{k}' must be one of {enum}, not {v!r}")
        for k in s.get("required") or ():
            if k not in inp:
                raise FalError(f"{endpoint} needs '{k}'")
        return props

    def _price(self, endpoint: str, inp: dict) -> dict:
        doc = self._call("GET", _URL_PRICE, params={"endpoint_id": endpoint})
        row = next((p for p in doc.get("prices") or [] if p.get("endpoint_id") == endpoint and p.get("unit_price") is not None), None)
        if row is None:
            raise FalError(f"no price for {endpoint} from fal get_pricing: a job without a priced source is refused")
        qty = int(inp.get("num_images") or 1)
        return {"amount": float(row["unit_price"]) * qty, "unit": f"{row.get('currency', 'USD')} per {row.get('unit', 'unit')}", "source": "fal get_pricing", "quantity": qty}

    def plan(self, endpoint: str, inp: dict) -> dict:
        self._check_input(endpoint, inp)
        price = self._price(endpoint, inp)
        return {"state": "needs_approval", "endpoint": endpoint, "price": price, "cap": self.max_job_usd}

    # --------------------------------------------------------------------------------------------------------- upload
    def _registry(self) -> dict:
        try:
            return json.loads(self._uploads.read_text())
        except (OSError, ValueError):
            return {"by_sha": {}, "by_path": {}}

    def upload(self, path: str) -> dict:
        """Reuse by sha256; the same path with other bytes is refused. The URL is stored (0600) and never returned."""
        real = Path(os.path.realpath(self.root / path if not os.path.isabs(path) else path))
        if not str(real).startswith(os.path.realpath(self.root) + os.sep):
            raise FalError("that file is outside the project root")
        sha, reg = _sha(real), self._registry()
        if reg["by_path"].get(str(real), sha) != sha:
            raise FalError("that file changed since it was uploaded: a path is bound to the bytes it first held (copy it to a new name)")
        reg["by_path"][str(real)] = sha
        hit = reg["by_sha"].get(sha)
        if hit:
            self._save(reg)
            return {"sha256": sha, "reused": True, "url_hash": hit["url_hash"]}
        init = self._call("POST", _URL_UPLOAD, json={"file_name": real.name, "content_type": "application/octet-stream"})
        put = self._http.put(init["upload_url"], content=real.read_bytes())
        if put.status_code >= 400:
            raise FalError(f"fal storage answered HTTP {put.status_code}")
        reg["by_sha"][sha] = {"url": init["file_url"], "url_hash": hashlib.sha256(init["file_url"].encode()).hexdigest()[:16]}
        self._save(reg)
        return {"sha256": sha, "reused": False, "url_hash": reg["by_sha"][sha]["url_hash"]}

    def _save(self, reg: dict) -> None:
        self._uploads.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(self._uploads, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(reg, fh)

    # --------------------------------------------------------------------------------------------------------- submit
    def submit(self, endpoint: str, inp: dict, dry_run: bool = True, confirmed: bool = False, origin: str = "user", references=None, idempotency_key: Optional[str] = None) -> dict:
        if dry_run:
            return {"dry_run": True, "state": "planned", "would_send": {"endpoint": endpoint, "input": dict(inp), "references": list(references or [])}}
        props = self._check_input(endpoint, inp)
        price = self._price(endpoint, inp)
        if price["amount"] > self.max_job_usd:
            raise FalError(f"{endpoint} costs ${price['amount']:.2f}: over the per-job cap of ${self.max_job_usd:.2f}; nothing was sent")
        if origin == "agent" or not confirmed:
            return {"state": "needs_approval", "endpoint": endpoint, "price": price, "cap": self.max_job_usd}
        body = dict(inp)
        refs = []
        for p in references or ():
            self.upload(p)
            real = os.path.realpath(self.root / p if not os.path.isabs(p) else p)
            refs.append(self._registry()["by_sha"][self._registry()["by_path"][real]]["url"])
        if refs:
            field = next((f for f in _REF_FIELDS if f in props), None)
            if field is None:
                raise FalError(f"{endpoint} takes no reference image (no image_urls or image_url field)")
            body[field] = refs if field == "image_urls" else refs[0]
        keyed = dict(inp, _refs=[_sha(Path(os.path.realpath(self.root / p if not os.path.isabs(p) else p))) for p in references or ()])
        r, created = self.receipts.create(PROVIDER, endpoint, keyed, idempotency_key, origin, price=price)
        if not created:
            return {"already_exists": True, "key": r["key"], "state": r["state"], "provider_job_id": r.get("provider_job_id")}

        def send():
            doc = self._call("POST", _URL_QUEUE + endpoint, json=body)
            return doc["request_id"], {"status": doc.get("status_url"), "response": doc.get("response_url"), "cancel": doc.get("cancel_url")}

        JR.submit_guarded(self.receipts, r, send)
        return {"key": r["key"], "state": r["state"], "provider_job_id": r["provider_job_id"], "price": price}

    # --------------------------------------------------------------------------------------------------------- result
    def status(self, r: dict) -> str:
        return map_status(self._call("GET", JR.check_url(r["status_url"]).geturl()))

    def result(self, key: str) -> dict:
        r = self.receipts.get(key, PROVIDER)
        if r is None:
            raise FalError("no such fal job")
        if r["state"] in JR.TERMINAL:
            return self._view(r)
        st = self.status(r)
        if st != "completed":
            return {"key": key, "state": r["state"], "status": st}
        if self.receipts.saved_result(r) is None:
            self.receipts.save_result(r, self._call("GET", JR.check_url(r["response_url"]).geturl()))
        if r["state"] == "completed":
            self.receipts.download(r)
        return self._view(r)

    @staticmethod
    def _view(r: dict) -> dict:
        return {"key": r["key"], "state": r["state"], "outputs": r["outputs"], "error_text": r.get("error_text", "")}


class FalAdapter:
    """The adapter ``JobReceipts.reconcile`` resumes a submitted fal job through (by provider id, never a resubmit)."""

    def __init__(self, client: FalClient):
        self.client = client

    def status(self, r: dict) -> str:
        return self.client.status(r)

    def result(self, r: dict) -> dict:
        return self.client._call("GET", JR.check_url(r["response_url"]).geturl())
