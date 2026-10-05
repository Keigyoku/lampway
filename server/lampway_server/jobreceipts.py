"""Write-ahead job receipts: a paid provider job is written to disk BEFORE it is sent and survives a crash (specs/mrmak/06-job-receipts.md).

Pure python (no server imports), so tests and the Client's tools can use it like ledger.py. A receipt is ``<root>/jobs/<provider>/<key>/receipt.json`` created with exclusive
open (``"x"``): a second submitter of the same key gets the existing receipt and never a second job. States:

    planned -> submission_pending -> submitted | submission_unknown -> running -> completed -> downloaded | result_saved
                                  \\-> provider_error / cancelled / abandoned

``submission_pending`` is written before the first byte goes to the provider; a process that dies there leaves it, and ``reconcile`` turns it into ``submission_unknown`` (a receipt can
never be pending in a process that is not running). Nothing resubmits an unknown job: only the user can ``acknowledge`` (it did not run) or ``link`` (here is its provider id).
Files are 0600 in 0700 directories, every update is a temp file plus ``os.replace``, and ``export_safe`` drops signed URLs and secrets before a receipt goes anywhere else."""

import hashlib
import json
import os
import re
import time
import urllib.parse
from pathlib import Path
from typing import Callable, Optional

SCHEMA = "lampway.job-receipt/v1"
STATES = ("planned", "submission_pending", "submitted", "submission_unknown", "running", "completed", "downloaded", "provider_error", "result_saved", "cancelled", "abandoned")
TERMINAL = ("downloaded", "provider_error", "result_saved", "cancelled", "abandoned")
_ALLOWED = {
    "planned": ("submission_pending", "cancelled", "abandoned"),
    "submission_pending": ("submitted", "submission_unknown", "provider_error", "cancelled"),
    "submitted": ("running", "completed", "provider_error", "cancelled", "abandoned"),
    "running": ("running", "completed", "provider_error", "cancelled", "abandoned"),
    "submission_unknown": ("submitted", "abandoned"),
    "completed": ("downloaded", "result_saved", "provider_error"),
}
MAX_FILE_BYTES = 512 * 1024 * 1024
DEFAULT_CAP_BYTES = 20 * 1024 ** 3
_EXT = {"video/mp4": ".mp4", "video/webm": ".webm", "video/quicktime": ".mov", "image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp", "model/gltf-binary": ".glb",
        "application/json": ".json"}
_SECRET_KEY = re.compile(r"(token|secret|authorization|signature|api[_-]?key|password)", re.I)
_PLACEHOLDER = re.compile(r"\{\{\s*\w+[^}]*\}\}|example\.invalid")


class ReceiptError(ValueError):
    pass


class NotSent(Exception):
    """Raised by an adapter that KNOWS nothing reached the provider (a validation or cap refusal): the receipt is not made ``submission_unknown`` for it."""


def _now() -> float:
    return time.time()


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), default=str)


def payload_sha256(payload) -> str:
    return hashlib.sha256(canonical(payload).encode()).hexdigest()


def key_for(provider: str, model: str, payload, origin: str, idempotency_key: Optional[str] = None) -> str:
    """The Client's own key when it sends one, else the hash of (provider, model, canonical payload, origin)."""
    basis = idempotency_key if idempotency_key else canonical([provider, model, payload, origin])
    return hashlib.sha256(basis.encode()).hexdigest()[:16]


def check_rendered(payload) -> None:
    """A payload whose text still holds an unresolved {{variable}} or the placeholder host is refused before anything is written."""
    if _PLACEHOLDER.search(canonical(payload)):
        raise ReceiptError("Replace placeholder references before submitting: the payload still holds an unresolved {{variable}} or example.invalid")


def collect_urls(result) -> list:
    """Every string ``url`` of any dict, and every list under a key ending ``_urls`` (fal_job's shape), in order, de-duplicated."""
    out = []

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k == "url" and isinstance(v, str):
                    out.append(v)
                elif isinstance(k, str) and k.endswith("_urls") and isinstance(v, list):
                    out.extend(u for u in v if isinstance(u, str))
                else:
                    walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(result)
    return list(dict.fromkeys(out))


def check_url(url: str) -> urllib.parse.ParseResult:
    p = urllib.parse.urlparse(url)
    if p.scheme != "https":
        raise ReceiptError(f"refusing to download {p.scheme or 'a non-https'} URL: media come from https only")
    if p.username or p.password:
        raise ReceiptError("refusing a URL with userinfo (user:password@host)")
    if not p.hostname:
        raise ReceiptError("refusing a URL with no host")
    if p.hostname.endswith("example.invalid"):
        raise ReceiptError("Replace placeholder references before submitting: example.invalid is not a real host")
    return p


def export_safe(receipt: dict) -> dict:
    """The receipt without signed URLs (any ``*_url`` with a query string or userinfo) and without keys that look like secrets: the only form a ledger row or a report may carry."""
    def clean(o):
        if isinstance(o, dict):
            out = {}
            for k, v in o.items():
                if _SECRET_KEY.search(str(k)):
                    continue
                if isinstance(v, str) and str(k).endswith("url"):
                    p = urllib.parse.urlparse(v)
                    if p.query or p.username or p.password:
                        continue
                out[k] = clean(v)
            return out
        if isinstance(o, list):
            return [clean(v) for v in o]
        if isinstance(o, str) and re.search(r"[?&](X-Amz-Signature|Signature|sig|token)=", o, re.I):
            return "[signed url removed]"
        return o
    return clean(receipt)


class JobReceipts:
    def __init__(self, root, cap_bytes: int = DEFAULT_CAP_BYTES, ledger=None, fetch: Optional[Callable] = None, fetchers: Optional[dict] = None):
        self.base = Path(root) / "jobs"
        self.cap = int(cap_bytes)
        self.ledger = ledger
        self.fetch = fetch or _default_fetch
        self.fetchers = fetchers or {}                                # per provider: a fetch that carries that provider's authorization

    # ---------------------------------------------------------------------------------------------------------- files
    def _dir(self, provider: str, key: str) -> Path:
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,64}", provider) or not re.fullmatch(r"[0-9a-f]{16}", key):
            raise ReceiptError("bad provider or key")
        return self.base / provider.replace(":", "_") / key

    def _mkdir(self, d: Path) -> None:
        d.mkdir(parents=True, exist_ok=True)
        for p in (d, d.parent, self.base):
            try:
                os.chmod(p, 0o700)
            except OSError:
                pass

    def _write(self, r: dict) -> None:
        d = self._dir(r["provider"], r["key"])
        r["updated_at"] = _now()
        tmp = d / ".receipt.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(r, indent=1, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, d / "receipt.json")

    def _load(self, d: Path) -> dict:
        return json.loads((d / "receipt.json").read_text())

    def disk_bytes(self) -> int:
        total = 0
        for dp, _dn, fn in os.walk(self.base):
            for f in fn:
                try:
                    total += os.lstat(os.path.join(dp, f)).st_size
                except OSError:
                    pass
        return total

    # --------------------------------------------------------------------------------------------------------- create
    def create(self, provider: str, model: str, payload, idempotency_key: Optional[str], origin: str, price: Optional[dict] = None, approval_id: Optional[str] = None,
               job_id: str = "") -> tuple:
        """(receipt, created). The receipt file is opened with ``"x"``: a key that already has one returns it and is NEVER a second job."""
        check_rendered(payload)
        key = key_for(provider, model, payload, origin, idempotency_key)
        d = self._dir(provider, key)
        if self.cap and self.disk_bytes() > self.cap:
            raise ReceiptError("jobs folder is over its cap: delete or move finished jobs")
        self._mkdir(d)
        r = {"schema": SCHEMA, "key": key, "job_id": job_id, "provider": provider, "model": model, "state": "planned", "created_at": _now(), "updated_at": _now(), "origin": origin,
             "price": price or {}, "approval_id": approval_id, "payload_sha256": payload_sha256(payload), "provider_job_id": None, "status_url": None, "response_url": None,
             "cancel_url": None, "error_class": None, "error_text": "", "outputs": [], "history": [{"state": "planned", "at": _now(), "note": ""}]}
        try:
            fd = os.open(d / "receipt.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            return self._load(d), False
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(r, indent=1, sort_keys=True))
            fh.flush()
            os.fsync(fh.fileno())
        return r, True

    def get(self, key: str, provider: Optional[str] = None) -> Optional[dict]:
        provs = [provider.replace(":", "_")] if provider else ([p.name for p in self.base.iterdir() if p.is_dir()] if self.base.exists() else [])
        for p in provs:
            d = self.base / p / key
            if (d / "receipt.json").exists():
                return self._load(d)
        return None

    def find_job(self, job_id: str) -> Optional[dict]:
        return next((r for r in self.list() if r.get("job_id") == job_id), None)

    def list(self, state: Optional[str] = None) -> list:
        out = []
        if self.base.exists():
            for pd in sorted(self.base.iterdir()):
                for d in sorted(pd.iterdir()) if pd.is_dir() else []:
                    if (d / "receipt.json").exists():
                        try:
                            r = self._load(d)
                        except ValueError:
                            continue
                        if state in (None, r["state"]):
                            out.append(r)
        return out

    # ------------------------------------------------------------------------------------------------------ transitions
    def _move(self, r: dict, new: str, note: str = "", **fields) -> dict:
        cur = self._load(self._dir(r["provider"], r["key"]))
        if new not in _ALLOWED.get(cur["state"], ()):
            raise ReceiptError(f"a {cur['state']} job cannot become {new}")
        cur.update(fields)
        cur["state"] = new
        cur["history"].append({"state": new, "at": _now(), "note": note[:300]})
        self._write(cur)
        r.clear()
        r.update(cur)
        if new in TERMINAL:
            self._ledger_row(cur)
        return r

    def mark_pending(self, r: dict) -> dict:
        """Called immediately BEFORE the first byte goes to the provider."""
        if self._load(self._dir(r["provider"], r["key"]))["state"] != "planned":
            raise ReceiptError("mark_pending needs a planned receipt: this job was already sent or settled; nothing is submitted twice")
        return self._move(r, "submission_pending")

    def mark_submitted(self, r: dict, provider_job_id: str, urls: Optional[dict] = None) -> dict:
        urls = urls or {}
        return self._move(r, "submitted", provider_job_id=str(provider_job_id), status_url=urls.get("status"), response_url=urls.get("response"), cancel_url=urls.get("cancel"))

    def mark_unknown(self, r: dict, error_class: str, text: str = "") -> dict:
        return self._move(r, "submission_unknown", "Submission outcome is unknown. Inspect the provider's history before resubmitting.", error_class=error_class[:80], error_text=text[:600])

    def mark_running(self, r: dict) -> dict:
        return self._move(r, "running")

    def mark_error(self, r: dict, text: str, error_class: str = "provider_error") -> dict:
        return self._move(r, "provider_error", text, error_class=error_class[:80], error_text=text[:600])

    def cancel(self, r: dict, note: str = "") -> dict:
        return self._move(r, "cancelled", note)

    def acknowledge(self, r: dict, by: str) -> dict:
        if by != "user":
            raise ReceiptError("only the user can acknowledge a submission_unknown job (it did not run)")
        return self._move(r, "abandoned", "acknowledged by the user: it did not run")

    def link(self, r: dict, provider_job_id: str, by: str) -> dict:
        if by != "user":
            raise ReceiptError("only the user can link a submission_unknown job to a provider job id")
        if not provider_job_id:
            raise ReceiptError("link needs the provider's job id")
        return self._move(r, "submitted", "linked by the user", provider_job_id=str(provider_job_id))

    def save_result(self, r: dict, result: dict) -> dict:
        """The provider's final result goes to result.json FIRST, so it outlives the provider's history. An error key inside a completed result is a provider_error."""
        d = self._dir(r["provider"], r["key"])
        tmp = d / ".result.tmp"
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            fh.write(json.dumps(result, indent=1, sort_keys=True, default=str))
        os.replace(tmp, d / "result.json")
        if isinstance(result, dict) and result.get("error"):
            self._move(r, "completed", "the provider returned a result carrying an error")
            return self.mark_error(r, "the result carries an error: " + str(result["error"])[:300], "result_error")
        return self._move(r, "completed")

    def saved_result(self, r: dict) -> Optional[dict]:
        p = self._dir(r["provider"], r["key"]) / "result.json"
        return json.loads(p.read_text()) if p.exists() else None

    def attach_outputs(self, r: dict, paths) -> dict:
        """Record files a job already saved elsewhere (a clip in the project's video folder): path, bytes and sha256 per file."""
        for p in paths:
            p = Path(p)
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for c in iter(lambda: fh.read(1 << 20), b""):
                    h.update(c)
            r["outputs"].append({"path": str(p), "bytes": p.stat().st_size, "sha256": h.hexdigest(), "kind": "file"})
        self._write(r)
        return r

    def mark_downloaded(self, r: dict) -> dict:
        return self._move(r, "downloaded" if r["outputs"] else "result_saved")

    # ------------------------------------------------------------------------------------------------------- download
    def download(self, r: dict, urls: Optional[list] = None, fetch: Optional[Callable] = None) -> dict:
        d = self._dir(r["provider"], r["key"]) / "assets"
        self._mkdir(d)
        result = self.saved_result(r)
        urls = urls if urls is not None else collect_urls(result or {})
        fetch = fetch or self.fetchers.get(r["provider"]) or self.fetch
        for i, url in enumerate(urls, 1):
            check_url(url)
            stem = f"{i:02d}-{hashlib.sha256(url.encode()).hexdigest()[:10]}"
            if any(o["path"].startswith(f"assets/{stem}") for o in r["outputs"]):
                continue
            chunks, ctype, length = fetch(url)
            if length is not None and length > MAX_FILE_BYTES:
                raise ReceiptError("Media exceeds the 512 MB per-file limit; download it separately")
            ext = Path(urllib.parse.urlparse(url).path).suffix.lower()
            if not re.fullmatch(r"\.[a-z0-9]{1,5}", ext or ""):
                ext = _EXT.get((ctype or "").split(";")[0].strip().lower(), "")
            final = d / f"{stem}{ext}"
            part = d / f"{stem}{ext}.part"
            if part.exists():
                part.unlink()                                       # ranges are not trusted: a .part is fetched again from byte 0
            h, n = hashlib.sha256(), 0
            fd = os.open(part, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            try:
                with os.fdopen(fd, "wb") as fh:
                    for c in chunks:
                        n += len(c)
                        if n > MAX_FILE_BYTES:
                            raise ReceiptError("Media exceeds the 512 MB per-file limit; download it separately")
                        h.update(c)
                        fh.write(c)
            except BaseException:
                if part.exists():
                    part.unlink()
                raise
            os.replace(part, final)
            r["outputs"].append({"path": f"assets/{final.name}", "bytes": n, "sha256": h.hexdigest(), "kind": (ctype or "").split("/")[0] or "file"})
            self._write(r)
        return self._move(r, "downloaded" if r["outputs"] else "result_saved")

    # ------------------------------------------------------------------------------------------------------ reconcile
    def reconcile(self, adapters: Optional[dict] = None) -> dict:
        """At server start (and every minute): pending -> unknown; submitted/running resume through the provider's adapter by id; completed without all outputs download the rest.
        A job whose provider forgot it is finished from the saved result.json. Returns {resumed, unknown, completed, abandoned, waiting}."""
        adapters = adapters or {}
        out = {"resumed": [], "unknown": [], "completed": [], "abandoned": [], "waiting": []}
        for r in self.list():
            st = r["state"]
            if st == "submission_pending":
                self.mark_unknown(r, "process_died", "the process stopped between the write-ahead receipt and the provider's answer")
                out["unknown"].append(r["key"])
            elif st == "submission_unknown":
                out["waiting"].append(r["key"])
            elif st == "completed":
                self.download(r)
                out["completed"].append(r["key"])
            elif st in ("submitted", "running"):
                ad = adapters.get(r["provider"])
                if ad is None:
                    out["waiting"].append(r["key"])
                    continue
                saved = self.saved_result(r)
                try:
                    status = ad.status(r)
                    res = saved if saved is not None else (ad.result(r) if status == "completed" else None)
                except Exception as exc:  # noqa: BLE001
                    if saved is None:
                        out["waiting"].append(r["key"])
                        continue
                    status, res = "completed", saved
                if status in ("queued", "running"):
                    if st != "running":
                        self.mark_running(r)
                    out["resumed"].append(r["key"])
                elif status == "completed":
                    if saved is None:
                        self.save_result(r, res)
                    elif r["state"] != "completed":
                        self._move(r, "completed")
                    if r["state"] == "completed":
                        self.download(r)
                    out["completed"].append(r["key"])
                elif status == "failed":
                    self.mark_error(r, "the provider reports the job failed")
                    out["abandoned"].append(r["key"])
                else:
                    out["waiting"].append(r["key"])
        return out

    # --------------------------------------------------------------------------------------------------------- ledger
    def _ledger_row(self, r: dict) -> None:
        if self.ledger is None:
            return
        safe = export_safe(r)
        self.ledger.record_job({"job_key": safe["key"], "provider": safe["provider"], "model": safe["model"], "state": safe["state"], "price": safe.get("price") or {},
                                "output_hashes": [o["sha256"] for o in safe.get("outputs", [])], "origin": safe.get("origin")})


def submit_guarded(store: "JobReceipts", r: dict, send: Callable) -> dict:
    """The ordering law in one place: ``mark_pending`` BEFORE ``send()``, ``mark_submitted`` after. ``send()`` returns (provider_job_id, urls). An exception leaves the job
    ``submission_unknown`` (never retried); ``NotSent`` (the adapter knows nothing left the machine) is a provider_error; a process-ending BaseException leaves it pending for reconcile."""
    store.mark_pending(r)
    try:
        pid, urls = send()
    except NotSent as exc:
        store.mark_error(r, f"not sent: {exc}", "not_sent")
        raise
    except Exception as exc:  # noqa: BLE001
        store.mark_unknown(r, type(exc).__name__, str(exc))
        raise
    return store.mark_submitted(r, pid, urls)


def _default_fetch(url: str):
    import httpx
    client = httpx.Client(timeout=300.0, follow_redirects=False)
    resp = client.stream("GET", url)
    r = resp.__enter__()
    if r.status_code >= 400:
        resp.__exit__(None, None, None)
        raise ReceiptError(f"downloading the result answered HTTP {r.status_code}")
    length = int(r.headers.get("content-length")) if r.headers.get("content-length", "").isdigit() else None

    def gen():
        try:
            yield from r.iter_bytes(1 << 20)
        finally:
            resp.__exit__(None, None, None)
            client.close()
    return gen(), r.headers.get("content-type"), length
