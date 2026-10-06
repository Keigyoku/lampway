"""The REST client behind every Studio REST action. One class, four shapes (shapes.py). The laws: a missing key is `needs_key` before any request; a key never leaves (not printed, not logged, not written); the base
URL can only be overridden to a loopback host (the tests' fake server); a CREATE is sent exactly once and an outcome that is unknown (a timeout, a 5xx, a dropped connection) is NEVER resent; a full queue (429) means
nothing was created and nothing is retried; only READS (balance, status, download) are retried, a few times, and then the error names the task id so it can be polled later by hand; downloads are https only
(loopback http under the override), no userinfo, 512 MB at most, a .part file renamed when whole, a sha256 per file."""
from __future__ import annotations

import base64
import hashlib
import os
import re
import stat
import time
import urllib.parse
from pathlib import Path
from typing import Optional

import httpx

from . import shapes as SH

MAX_FILE_BYTES = 512 * 1024 * 1024
POLL_ERRORS_MAX = 5
LOOPBACK = {"127.0.0.1", "localhost", "::1"}


class StudioError(Exception):
    pass


class StudioUnknown(StudioError):
    """The create's outcome is unknown: it is not resent."""


def _safe(text, n=160) -> str:
    s = re.sub(r"(?i)(bearer|basic)\s+[A-Za-z0-9._\-+/=]{6,}", r"\1 [redacted]", str(text))
    s = re.sub(r"https?://[^\s\"']+", "[url]", s)
    return s[:n]


def _secret_value(env, var):
    if env.get(var):
        return env[var].strip()
    fv = env.get(var + "_FILE")
    if fv:
        p = Path(fv)
        try:
            mode = p.stat().st_mode
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                raise StudioError(f"{fv} must be owner-only (chmod 600): the key file is readable by others")
            return p.read_text().strip()
        except OSError:
            raise StudioError(f"{fv} could not be read")
    return None


class RestStudio:
    def __init__(self, shape: SH.Studio, env: dict, transport=None):
        self.shape, self.env = shape, env
        self.override = env.get(f"LAMPWAY_STUDIO_REST_BASE_{shape.name.upper()}")
        if self.override:
            host = urllib.parse.urlsplit(self.override).hostname
            if host not in LOOPBACK:
                raise StudioError("LAMPWAY_STUDIO_REST_BASE_* may only point at a loopback host (it exists for the tests' fake server): a key is never sent anywhere else")
        self.base = (self.override or shape.base).rstrip("/")
        self.http = httpx.Client(transport=transport, timeout=httpx.Timeout(60.0, connect=15.0), follow_redirects=False)
        self.sleep = lambda: time.sleep(float(env.get("LAMPWAY_STUDIO_POLL_S", "3")))
        self.max_wait = float(env.get("LAMPWAY_STUDIO_MAX_WAIT_S", "1800"))
        self._token: Optional[str] = None

    # ------------------------------------------------------------------------------------------------- auth
    def _keys(self):
        vars_ = self.shape.key_vars
        if self.shape.name == "hi3d":
            single = _secret_value(self.env, vars_[0])
            if single and "\n" in single:
                a, b = single.split("\n", 1)
                return a.strip(), b.strip()
            other = _secret_value(self.env, vars_[1])
            if single and other:
                return single, other
        else:
            for v in vars_:
                val = _secret_value(self.env, v)
                if val:
                    return (val,)
        raise StudioError(f"needs_key: set {' and '.join(vars_) if self.shape.name == 'hi3d' else ' or '.join(vars_)} in the environment (or <NAME>_FILE pointing at an owner-only file): nothing was requested")

    def _auth(self) -> dict:
        k = self._keys()
        if self.shape.name == "hi3d":
            if self._token is None:
                r = self._send("POST", "/open-api/v1/auth/token", headers={"Authorization": "Basic " + base64.b64encode(f"{k[0]}:{k[1]}".encode()).decode()})
                self._token = ((r.json().get("data") or {}).get("accessToken"))
                if not self._token:
                    raise StudioError("the provider issued no access token")
            return {"Authorization": f"Bearer {self._token}"}
        return {"Authorization": f"Bearer {k[0]}"}

    def check_key(self) -> None:
        self._keys()

    # ---------------------------------------------------------------------------------------------- requests
    def _send(self, method, path, headers=None, **kw):
        return self.http.request(method, path if path.startswith("http") else self.base + path, headers=headers, **kw)

    def _read(self, method, path, **kw):
        """A READ (balance, status): retried a few times on transient errors; the error names what failed."""
        last = None
        for _ in range(POLL_ERRORS_MAX):
            try:
                r = self._send(method, path, headers=self._auth(), **kw)
                if r.status_code in (401, 403):
                    raise StudioError(f"the {self.shape.name} key was refused (HTTP {r.status_code}): check it in the provider's dashboard")
                if r.status_code < 400:
                    return r
                last = f"HTTP {r.status_code}"
            except httpx.TransportError as exc:
                last = type(exc).__name__
            self.sleep()
        raise StudioError(f"{self.shape.name} did not answer a read ({last}) after {POLL_ERRORS_MAX} tries")

    def balance(self) -> float:
        m, p, parse = self.shape.balance
        try:
            return float(parse(self._read(m, p).json()))
        except (ValueError, KeyError, TypeError):
            raise StudioError(f"{self.shape.name} answered the balance request with something unreadable")

    def action(self, name: str) -> SH.ActionShape:
        if name not in self.shape.actions:
            raise StudioError(f"no such action {name!r} for {self.shape.name}; the actions are {sorted(self.shape.actions)}")
        return self.shape.actions[name]

    def upload(self, path) -> str:
        """Tripo: a file token for a local file (multipart). The upload is a write: one try, not resent."""
        p = Path(path)
        try:
            r = self._send("POST", "/v3/files", headers=self._auth(), files={"file": (p.name, p.read_bytes())})
        except httpx.TransportError:
            raise StudioError("the file upload did not complete: nothing was created; run it again yourself")
        if r.status_code >= 400:
            raise StudioError(f"the file upload was refused (HTTP {r.status_code})")
        return r.json()["data"]["file_token"]

    # ----------------------------------------------------------------------------------------------- create
    def create(self, act: SH.ActionShape, clean: dict) -> dict:
        method, path, kind, payload = act.create(clean, self)
        headers = self._auth()
        kw = {}
        if kind == "json":
            kw["json"] = payload
        else:
            files = [(field, (Path(p).name, Path(p).read_bytes())) for field, p in payload["files"]]
            kw["files"], kw["data"] = files, payload["fields"]
        try:
            r = self._send(method, path, headers=headers, **kw)
        except httpx.TransportError as exc:
            raise StudioUnknown(f"the create's outcome is unknown ({type(exc).__name__}): the provider may have started the task. It is NOT resent: check the provider's task list before running it again")
        if r.status_code in (401, 403):
            raise StudioError(f"the {self.shape.name} key was refused (HTTP {r.status_code}): nothing was created")
        if r.status_code == 429:
            raise StudioError("the provider's queue is full (HTTP 429): nothing was created and nothing was retried; try again later yourself")
        if 400 <= r.status_code < 500:
            raise StudioError(f"the provider refused the request (HTTP {r.status_code}: {_safe(self._msg(r))}): nothing was created")
        if r.status_code >= 500:
            raise StudioUnknown(f"the create answered HTTP {r.status_code}: its outcome is unknown. It is NOT resent: check the provider's task list before running it again")
        try:
            return self._handle(r.json())
        except (ValueError, KeyError, TypeError):
            raise StudioUnknown("the create answered but no task id could be read from it: its outcome is unknown. It is NOT resent")

    @staticmethod
    def _msg(r):
        try:
            j = r.json()
            return j.get("message") or j.get("error") or j.get("msg") or ""
        except ValueError:
            return ""

    def _handle(self, j: dict) -> dict:
        n = self.shape.name
        if n == "meshy":
            return {"id": j["result"]}
        if n == "hyper3d":
            return {"id": j["uuid"], "sub": j["jobs"]["subscription_key"], "consumed": j.get("consumed")}
        if n == "hi3d":
            return {"id": j["data"]["task_id"]}
        return {"id": j["data"]["task_id"]}

    # ------------------------------------------------------------------------------------------------ poll
    def poll(self, act: SH.ActionShape, h: dict) -> dict:
        """Wait for the task. Returns {state: done|failed, urls: [(name, url)], consumed, error}. A poll that keeps failing names the task."""
        n, start = self.shape.name, time.monotonic()
        while True:
            try:
                st = self._status(act, h)
            except StudioError as exc:
                raise StudioError(f"{exc}; the task is {h['id']}: poll it later by hand (it is not resubmitted)")
            if st["state"] in ("done", "failed"):
                return st
            if time.monotonic() - start > self.max_wait:
                raise StudioError(f"the task {h['id']} was still running after {int(self.max_wait)} s: poll it later by hand (it is not resubmitted)")
            self.sleep()

    def _status(self, act, h) -> dict:
        n = self.shape.name
        if n == "hyper3d":
            r = self._read("POST", "/api/v2/status", json={"subscription_key": h["sub"]})
            jobs = r.json().get("jobs") or []
            sts = {str(j.get("status")).lower() for j in jobs}
            if "failed" in sts:
                return {"state": "failed", "error": "the provider reports the job failed", "urls": [], "consumed": h.get("consumed")}
            if sts and sts <= {"done"}:
                d = self._read("POST", "/api/v2/download", json={"task_uuid": h["id"]}).json()
                return {"state": "done", "urls": [(x.get("name") or f"result_{i}", x["url"]) for i, x in enumerate(d.get("list") or [])], "consumed": h.get("consumed")}
            return {"state": "running"}
        j = self._read("GET", act.status_path.format(id=h["id"])).json()
        if n == "meshy":
            s = j.get("status")
            if s == "SUCCEEDED":
                urls = [(f"model.{fmt}", u) for fmt, u in (j.get("model_urls") or {}).items() if isinstance(u, str) and u]
                for t in j.get("texture_urls") or []:
                    urls += [(f"texture_{k}.png", u) for k, u in t.items() if isinstance(u, str)]
                return {"state": "done", "urls": urls, "consumed": j.get("consumed_credits")}
            if s in ("FAILED", "CANCELED"):
                return {"state": "failed", "error": _safe((j.get("task_error") or {}).get("message") or s), "urls": [], "consumed": j.get("consumed_credits")}
            return {"state": "running"}
        d = j.get("data") or {}
        if n == "hi3d":
            s = d.get("state")
            if s == "success":
                return {"state": "done", "urls": [("result.glb", d["url"])] if d.get("url") else [], "consumed": None}
            if s == "failed":
                return {"state": "failed", "error": _safe(d.get("message") or "the provider reports the task failed"), "urls": [], "consumed": None}
            return {"state": "running"}
        s = d.get("status")                                                                    # tripo v3
        if s == "success":
            out = d.get("output") or {}
            return {"state": "done", "urls": [(f"{k}.glb" if k != "rendered_image" else f"{k}.png", u) for k, u in out.items() if isinstance(u, str) and u.startswith("http")], "consumed": d.get("consumed_credit")}
        if s in ("failed", "cancelled", "banned", "expired"):
            return {"state": "failed", "error": _safe(d.get("message") or s), "urls": [], "consumed": d.get("consumed_credit")}
        return {"state": "running"}

    # --------------------------------------------------------------------------------------------- download
    def download(self, url: str, out_dir, name: str) -> dict:
        p = urllib.parse.urlsplit(url)
        loop = self.override is not None and p.hostname in LOOPBACK
        if p.scheme != "https" and not (p.scheme == "http" and loop):
            raise StudioError("downloads are https only")
        if p.username is not None or p.password is not None or "@" in p.netloc:
            raise StudioError("a download URL with userinfo is refused")
        out = Path(out_dir)
        out.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name) or "result"
        final, part = out / safe, out / (safe + ".part")
        h, n = hashlib.sha256(), 0
        try:
            with self.http.stream("GET", url, follow_redirects=False) as r:
                if r.status_code >= 400:
                    raise StudioError(f"the download answered HTTP {r.status_code}")
                if int(r.headers.get("content-length") or 0) > MAX_FILE_BYTES:
                    raise StudioError("a file is over the 512 MB limit: download it separately")
                with open(part, "wb") as fh:
                    for chunk in r.iter_bytes():
                        n += len(chunk)
                        if n > MAX_FILE_BYTES:
                            raise StudioError("a file is over the 512 MB limit: download it separately")
                        h.update(chunk)
                        fh.write(chunk)
        except httpx.TransportError as exc:
            part.unlink(missing_ok=True)
            raise StudioError(f"the download failed ({type(exc).__name__})")
        except StudioError:
            part.unlink(missing_ok=True)
            raise
        os.replace(part, final)
        return {"name": safe, "path": str(final), "bytes": n, "sha256": h.hexdigest()}
