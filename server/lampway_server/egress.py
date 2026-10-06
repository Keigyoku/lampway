"""Egress consent (specs/cloud/egress_consent.md): every outbound route is OFF until the user opts in, ONE choke point at the transport, a visible 'over the wire' indicator and a content-free log.

``install()`` wraps ``httpx.Client.send`` / ``httpx.AsyncClient.send`` once: every in-process provider (the Anthropic SDK included) uses httpx, so every call passes here. A call that starts another process
(a studio browser driver, a local CLI, yt-dlp, a cloud box CLI) cannot be seen at the transport: it calls ``guard(route, ...)`` where it launches. The log row is written BEFORE the bytes leave and holds the
route, the host, the kind, the byte count, asset ids and the retention class: never content, a query string or a header."""
from __future__ import annotations

import contextlib
import contextvars
import json
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx

LOOPBACK = {"127.0.0.1", "localhost", "::1", "testserver"}
KINDS = ("image", "video", "mesh", "text", "file", "request")


class EgressRefused(PermissionError):
    pass


@dataclass(frozen=True)
class Route:
    id: str
    label: str
    hosts: tuple
    retention: str
    training: str
    privacy_class: str                  # ok | conditional | retains | unknown
    requires: tuple = ()                # for conditional: ((flag, value), ...) the call must declare


_UNREAD = "unknown (the provider's terms are not read or recorded: decision D9)"
ROUTES = {r.id: r for r in (
    Route("openrouter", "OpenRouter", ("openrouter.ai",), "per model: Lampway sends zdr + data_collection=deny for private content; otherwise the model provider's policy applies",
          "per model: data_collection=deny is sent for private content", "conditional", (("zdr", True), ("data_collection", "deny"))),
    Route("chatgpt_plan", "ChatGPT plan", ("chatgpt.com", "auth.openai.com", "api.openai.com"), _UNREAD, _UNREAD, "unknown"),
    Route("claude_plan", "Claude plan", ("api.anthropic.com", "claude.ai"), _UNREAD, _UNREAD, "unknown"),
    Route("custom_llm", "Custom LLM endpoint (OPENAI_BASE_URL)", (), _UNREAD, _UNREAD, "unknown"),
    Route("mcp_probe", "MCP connection check (a server you configured)", (), "sends only initialize and tools/list, no credential and none of your content; the server you configured sees the request", "n/a: no content is sent", "ok"),
    Route("studio:tripo", "Tripo Studio", ("tripo3d.ai", "tripo3d.com", "tripo.ai"), _UNREAD, _UNREAD, "unknown"),
    Route("studio:meshy", "Meshy", ("meshy.ai",), _UNREAD, _UNREAD, "unknown"),
    Route("studio:hi3d", "Hi3D", ("hitem3d.com", "hitem3d.ai"), _UNREAD, _UNREAD, "unknown"),
    Route("studio:hyper3d", "Hyper3D / Rodin", ("hyper3d.ai", "hyper3d.com", "deemos.com"), _UNREAD, _UNREAD, "unknown"),
    Route("higgsfield", "Higgsfield", ("higgsfield.ai",), _UNREAD, _UNREAD, "unknown"),
    Route("heygen", "HeyGen", ("heygen.com",), _UNREAD, _UNREAD, "unknown"),
    Route("fal", "fal.ai", ("fal.ai", "fal.run", "fal.media"), _UNREAD, _UNREAD, "unknown"),
    Route("video_link", "Video download from a link you pasted (yt-dlp)", (), "the site you pasted sees your IP address and the link; nothing of yours is uploaded; what the site keeps is its own policy",
          "n/a: nothing of yours is sent", "ok"),
    Route("model_download", "Model weights download (Hugging Face)", ("huggingface.co", "cdn-lfs.huggingface.co", "cdn-lfs-us-1.hf.co", "hf.co", "cas-bridge.xethub.hf.co"),
          "no user content: a plain GET of public weights; the host sees your IP address and which file you asked for", "n/a: no content is sent", "ok"),
    Route("cc0:ambientcg", "ambientCG (CC0 materials)", ("ambientcg.com", "acg-media.struffelproductions.com"),
          "no user content: GETs of public CC0 files; the host sees your IP address and which assets you asked for", "n/a: no content is sent", "ok"),
    Route("cc0:polyhaven", "Poly Haven (CC0 textures, HDRIs, models)", ("api.polyhaven.com", "dl.polyhaven.org", "polyhaven.com", "cdn.polyhaven.com"),
          "no user content: GETs of public CC0 files; the host sees your IP address and which assets you asked for", "n/a: no content is sent", "ok"),
    Route("compute:boat", "Boat (cloud CPU box)", ("boat.dev",), "a sandbox with snapshots off is erased by a stop (measured, BOAT.md section 6); what Boat does with content in flight is unread",
          _UNREAD, "conditional", (("snapshots", False), ("noEnv", True))),
    Route("compute:modal", "Modal (serverless GPU)", ("modal.run", "modal.com"), _UNREAD, _UNREAD, "unknown"),
    Route("compute:runpod", "RunPod (serverless GPU)", ("runpod.ai", "runpod.io", "runpod.net"), _UNREAD, _UNREAD, "unknown"),
)}

# Every process the server starts that is NOT lexically inside ``guard(route)``, with its reason (tests/test_egress_launch_audit.py holds this list to the code):
#   local          the program it starts sends nothing of ours off the machine;
#   callers_guard  a launch helper whose every call in its module is inside ``guard``;
#   wrapped        a launch helper injected as a value: every use of it in its module goes through the named wrapper, which holds ``guard``;
#   driver         a launch inside a studio driver script, which itself only ever runs as a gated process (studios.service._gated_execute, agent.server_tools._exec).
LAUNCHES: dict = {
    "agent/cli_adapters.py:_run_gated": ("callers_guard", "the Claude/Codex CLI subprocess; its only caller, _run, holds guard(claude_plan|chatgpt_plan)"),
    "agent/providers/codex_app_server.py:probe_binary": ("local", "codex --version and generate-json-schema: local schema generation, no model call (measured)"),
    "agent/providers/codex_app_server.py:_Client.start": ("local", "starts the long-lived codex app-server process; every turn that talks to the provider is gated by guard(chatgpt_plan) in stream()"),
    "agent/server_tools.py:_exec_local": ("local", "the seed catalog driver reads the local seeds.sqlite only (LOCAL_MODULES)"),
    "compute/boat.py:default_runner": ("wrapped", "the Boat CLI; injected as BoatCliBackend.runner and called only inside _cli, which holds guard(compute:boat)"),
    "cards/activity.py:_commits": ("local", "git log on the local repository (the report card's recorded changes)"),
    "herdr/launcher.py:_spawn": ("local", "Lampway's own herdr server and client on local unix sockets"),
    "herdr/launcher.py:_systemd_ok": ("local", "systemctl --user is-system-running: a local query"),
    "library/ingest.py:extract_video": ("local", "ffprobe on a local file"),
    "library/previews.py:video_thumb": ("local", "nice ffmpeg: one thumbnail frame of a library video file"),
    "library/video.py:_run": ("local", "nice ffmpeg/ffprobe on library video files (probe, frame count, loudness, derived strips and panels); every caller in video.py passes an ffmpeg or ffprobe argv"),
    "mcp_inventory/probe.py:_stdio": ("local", "starts the user's own configured stdio MCP server and speaks initialize/tools-list over stdin; what that program does is the user's own configuration"),
    "studios/service.py:default_execute": ("wrapped", "the studio driver process; injected as StudioService.execute and called only through _gated_execute, which holds guard(studio:<name>)"),
    "studios/tripo/relief_gen.py:ensure_browser": ("driver", "the relief site's headed browser, started from inside the Tripo driver process, which only runs gated"),
    "studios/tripo/tripo_texture.py:run_and_fetch": ("local", "nice blender -b on the downloaded FBX: a local headless render"),
    "videogate.py:probe": ("local", "ffprobe on a local clip"),
    "videogate.py:decode": ("local", "ffmpeg decode of a local clip"),
    "videogate.py:pingpong_file": ("local", "ffmpeg re-encode of a local clip"),
    "videoingest.py:_run": ("callers_guard", "yt-dlp; its only caller, ingest, holds guard(video_link) around every call"),
    "videoingest.py:probe": ("local", "ffprobe on the downloaded local file"),
    "videojobs.py:probe_video": ("local", "ffprobe on a local clip"),
}
WRAPPERS = {"compute/boat.py:default_runner": ("BoatCliBackend._cli", "runner"), "studios/service.py:default_execute": ("_gated_execute", "execute")}

_ctx: contextvars.ContextVar = contextvars.ContextVar("lampway_egress_ctx", default={})


@contextlib.contextmanager
def context(**declared):
    """What the next calls carry: kind, asset_ids, content_class (public | synthetic | private), constraints, route (explicit, for a CDN host no table lists)."""
    tok = _ctx.set({**_ctx.get(), **declared})
    try:
        yield
    finally:
        _ctx.reset(tok)


class Egress:
    def __init__(self, state_dir, permissive: bool = False):
        self.state_dir = Path(state_dir)
        self._permissive = permissive
        self._lock = threading.RLock()
        self._active: dict = {}
        self._last: Optional[dict] = None
        self._hosts: dict = {}

    @classmethod
    def permissive(cls, state_dir):
        return cls(state_dir, True)

    # ---------------------------------------------------------------------------------------------------- prefs
    @property
    def _prefs_path(self) -> Path:
        return self.state_dir / "egress.json"

    def _prefs(self) -> dict:
        try:
            return json.loads(self._prefs_path.read_text())
        except (OSError, ValueError):
            return {"routes": {}, "overrides": []}

    def _save(self, prefs: dict) -> None:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        tmp = self._prefs_path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump(prefs, fh, indent=1)
        os.replace(tmp, self._prefs_path)

    def enabled(self, route: str) -> bool:
        return True if self._permissive else bool(self._prefs()["routes"].get(route, {}).get("enabled", False))

    def set_route(self, route: str, on: bool) -> dict:
        if route not in ROUTES:
            raise ValueError(f"no route {route!r}: the routes are {sorted(ROUTES)}")
        with self._lock:
            p = self._prefs()
            p["routes"][route] = {"enabled": bool(on)}
            self._save(p)
        return {"route": route, "enabled": bool(on)}

    def register_host(self, route: str, host: str) -> None:
        """A route whose host is configured, not fixed (the custom LLM endpoint)."""
        self._hosts[host.lower()] = route

    def overridden(self, asset_id: str, route: str) -> bool:
        return any(o["asset_id"] == asset_id and o["route"] == route for o in self._prefs()["overrides"])

    def override(self, asset_id: str, route: str) -> dict:
        """The per-asset override of the private rule: loud (a log row of its own) and scoped to one asset and one route."""
        if route not in ROUTES:
            raise ValueError(f"no route {route!r}")
        with self._lock:
            p = self._prefs()
            if not self.overridden(asset_id, route):
                p["overrides"].append({"asset_id": asset_id, "route": route, "at": time.time()})
                self._save(p)
        self._append({"event": "override", "route": route, "asset_id": asset_id, "action": "set"})
        return {"asset_id": asset_id, "route": route}

    def clear_override(self, asset_id: str, route: str) -> None:
        with self._lock:
            p = self._prefs()
            p["overrides"] = [o for o in p["overrides"] if not (o["asset_id"] == asset_id and o["route"] == route)]
            self._save(p)
        self._append({"event": "override", "route": route, "asset_id": asset_id, "action": "cleared"})

    # ------------------------------------------------------------------------------------------------------ log
    @property
    def _log_path(self) -> Path:
        return self.state_dir / "egress" / "log.jsonl"

    def _append(self, row: dict) -> None:
        row = {"t": time.time(), **row}
        with self._lock:
            self._log_path.parent.mkdir(parents=True, exist_ok=True)
            fd = os.open(self._log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as fh:
                fh.write(json.dumps(row, sort_keys=True) + "\n")

    def log(self, limit: Optional[int] = None) -> list:
        try:
            rows = [json.loads(l) for l in self._log_path.read_text().splitlines() if l.strip()]
        except OSError:
            rows = []
        return rows[-limit:] if limit else rows

    def export_text(self) -> str:
        try:
            return self._log_path.read_text()
        except OSError:
            return ""

    # ------------------------------------------------------------------------------------------------ indicator
    def indicator(self) -> dict:
        with self._lock:
            return {"over_the_wire": bool(self._active), "active": sorted(self._active), "last": self._last}

    def routes_view(self) -> list:
        last = {}
        for r in self.log():
            if r.get("event") == "send":
                last[r["route"]] = r["t"]
        return [{"id": r.id, "label": r.label, "enabled": self.enabled(r.id) if not self._permissive else self.enabled(r.id), "retention": r.retention, "training": r.training,
                 "privacy_class": r.privacy_class, "hosts": list(r.hosts), "last_used": last.get(r.id)} for r in ROUTES.values()]

    # --------------------------------------------------------------------------------------------------- the gate
    def route_for_host(self, host: str) -> Optional[str]:
        host = host.lower()
        if host in self._hosts:
            return self._hosts[host]
        for r in ROUTES.values():
            if any(host == h or host.endswith("." + h) for h in r.hosts):
                return r.id
        return None

    def begin(self, host: str, method: str, nbytes: int, explicit_route: Optional[str] = None):
        d = _ctx.get()
        route = explicit_route or d.get("route") or self.route_for_host(host)
        base = {"provider": host, "method": method, "kind": d.get("kind", "request"), "bytes": int(nbytes), "asset_ids": list(d.get("asset_ids") or []),
                "content_class": d.get("content_class", "unclassified")}
        if route is None:
            if self._permissive:
                route = "unmapped"
            else:
                self._append({"event": "refused", "route": None, **base, "reason": "unmapped host"})
                raise EgressRefused(f"host {host} is not a known route: add it to the route table; nothing was sent")
        spec = ROUTES.get(route)
        policy = {"retention": spec.retention, "training": spec.training, "privacy_class": spec.privacy_class} if spec else {"retention": "unmapped host", "training": "unknown", "privacy_class": "unknown"}
        if not self.enabled(route):
            self._append({"event": "refused", "route": route, **base, **policy, "reason": "route off"})
            raise EgressRefused(f"{route} is off: switch it on in Privacy to let data leave")
        override = False
        if base["content_class"] == "private" and not self._permissive:
            ok = spec is not None and (spec.privacy_class == "ok" or (spec.privacy_class == "conditional" and all((d.get("constraints") or {}).get(k) == v for k, v in spec.requires)))
            if not ok:
                ids = base["asset_ids"]
                if ids and all(self.overridden(i, route) for i in ids):
                    override = True
                else:
                    need = ", ".join(f"{k}={v}" for k, v in spec.requires) if spec and spec.requires else "a verified-ephemeral guarantee"
                    self._append({"event": "refused", "route": route, **base, **policy, "reason": "private content"})
                    raise EgressRefused(f"this asset is private and {route} requires {need} (policy: {policy['retention'][:80]}): use a verified route, run it locally, or flip the per-asset override (logged)")
        self._append({"event": "send", "route": route, **base, **policy, "override": override})
        with self._lock:
            self._active[route] = self._active.get(route, 0) + 1
            self._last = {"route": route, "t": time.time()}
        return route

    def end(self, route: str) -> None:
        with self._lock:
            n = self._active.get(route, 0) - 1
            if n <= 0:
                self._active.pop(route, None)
            else:
                self._active[route] = n


ACTIVE: Optional[Egress] = None


def set_active(m: Optional[Egress]) -> None:
    global ACTIVE
    ACTIVE = m


def _nbytes(request: httpx.Request) -> int:
    try:
        return len(request.content)
    except Exception:  # noqa: BLE001  (a streamed body that was not read)
        try:
            return int(request.headers.get("content-length") or 0)
        except ValueError:
            return 0


def _begin(request: httpx.Request):
    m = ACTIVE
    host = (request.url.host or "").lower()
    if m is None or host in LOOPBACK:
        return None
    return m, m.begin(host, request.method, _nbytes(request))


_installed = False
_orig_send = httpx.Client.send
_orig_asend = httpx.AsyncClient.send


def install() -> None:
    """Wrap the two httpx send methods once. With no active manager they pass straight through."""
    global _installed
    if _installed:
        return
    _installed = True

    def send(self, request, **kw):
        tok = _begin(request)
        try:
            return _orig_send(self, request, **kw)
        finally:
            if tok:
                tok[0].end(tok[1])

    async def asend(self, request, **kw):
        tok = _begin(request)
        try:
            return await _orig_asend(self, request, **kw)
        finally:
            if tok:
                tok[0].end(tok[1])

    httpx.Client.send = send
    httpx.AsyncClient.send = asend


@contextlib.contextmanager
def guard(route: str, kind: Optional[str] = None, asset_ids=None, content_class: Optional[str] = None, constraints=None, nbytes: int = 0):
    """The same gate for a call that starts another process (a studio driver, a local CLI, yt-dlp, a cloud box CLI): lit while it runs, logged before it starts.
    What it does not say is inherited from an enclosing ``context`` (a runner declares the asset ids; the backend's own guard gates each call)."""
    m = ACTIVE
    if m is None:
        yield
        return
    outer = _ctx.get()
    with context(kind=kind or outer.get("kind", "request"), asset_ids=list(asset_ids if asset_ids is not None else outer.get("asset_ids") or []),
                 content_class=content_class or outer.get("content_class", "unclassified"), constraints=constraints if constraints is not None else outer.get("constraints") or {}):
        r = m.begin(route, "PROCESS", nbytes, explicit_route=route)
    try:
        yield
    finally:
        m.end(r)


def preflight(route: str) -> None:
    """Refuse BEFORE a receipt is marked pending: a route that is off sent nothing, so the job must not read as 'submission unknown'."""
    m = ACTIVE
    if m is not None and not m.enabled(route):
        m._append({"event": "refused", "route": route, "kind": "request", "bytes": 0, "reason": "route off"})
        raise EgressRefused(f"{route} is off: switch it on in Privacy to let data leave")
