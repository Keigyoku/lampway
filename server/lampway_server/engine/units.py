# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Mode 1's panes, the server's half (docs/reports/agent-modes-spec.md A1, S2, S3): every Lampway Agent is a ``lampway_hermes``
pane on Lampway's herdr server running ``hermes serve`` and Hermes's own TUI (``engine/hermes_pane.py``). This module prepares what
the pane needs, opens a unit's main pane through the cockpit (one tab per unit, A4), creates the pane's Hermes session and
re-adopts the panes after a restart. It never starts or stops a process itself: herdr starts the pane, the pane starts serve.

**A unit's home** is ``<state>/agent/hermes/<unit>`` (a worker's ``<unit>/workers/<swarm>-<worker>``), 0700, never the user's own
``~/.hermes`` (E1.10). Before herdr is asked, ``prepare`` (the cockpit's ``mode1`` hook) writes into it:

* ``config.yaml`` (0600): ``hermes_config`` from the active Capabilities board (a worker's less ``WORKER_NEVER``, without
  ``clarify``), the gateway with a fresh per-pane token, and Lampway's ONE MCP server: the unit's ``/engine/mcp/<unit>`` with a
  fresh per-unit bearer (A3), or a worker's pane endpoint with its binding and the swarm's worker token (S3);
* ``serve.token`` (0600): serve's dashboard token, read by the wrapper into serve's environment and by the island's client; never
  on a command line, in herdr's argv or in a record;
* ``pane.json`` (0600, no secret): the pinned ``hermes`` binary, the port, the project root, the prebuilt TUI, the Node found here,
  the egress proxy's variables;
* ``task.txt`` (0600, a worker only): its task, submitted by the server as the session's first prompt (S2).

The pane's record (``Cockpit``, ``MODE1_FIELDS``) keeps the home, the port, the token file's path, the stored session id and the
digests of the two tokens, so a restarted server adopts them again (``adopt``) and the pane thinks and calls tools on: the panes
outlive the server (law 5, A1). Opening a unit's pane is the user's own chat (``HermesFront.precheck`` refuses an agent's socket);
nothing here opens one by itself, and nothing reopens an ended pane but that chat.

**Node and the TUI** are found, never fetched (A1): ``LAMPWAY_NODE`` or ``node`` on the server's PATH; the TUI the engine build
prebuilt (``engine.json`` ``tui``) or ``LAMPWAY_HERMES_TUI_DIR``. Without them a pane is refused with what to do.
"""

import asyncio
import json
import logging
import os
import secrets
import shutil
import socket
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from ..herdr import harnesses as HN
from ..herdr import layout as LY
from ..herdr.host import CockpitError
from . import gateway as GW
from . import hermes_config as HC
from .serve_client import ServeClient, ServeError

log = logging.getLogger("lampway.engine.units")

SESSION_FILE = "session.json"
SPEC_FILE = "pane.json"
TOKEN_FILE = "serve.token"
TASK_FILE = "task.txt"
TUI_ENV = "LAMPWAY_HERMES_TUI_DIR"
NODE_ENV = "LAMPWAY_NODE"
START_TIMEOUT_S = 120.0          # herdr types the wrapper into a fresh shell, then serve listens in ~3 s (measured)
READY_TIMEOUT_S = 60.0           # a new session is ready 2-4 s after session.create (measured)


@dataclass(frozen=True)
class UnitInfo:
    """What reaches a pane's serve: its port, its token, and the session the pane shows."""
    unit: str
    record_id: str
    home: Path
    port: int
    token: str
    stored_id: str


def write_private(path: Path, text: str) -> None:
    """A 0600 file in a 0700 directory, replaced atomically."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _binding_parts(binding: str) -> tuple:
    parts = str(binding or "").split(":")
    return (parts[1], parts[2]) if len(parts) == 3 and parts[0] == "swarm" else ("", "")


class Mode1Units:
    def __init__(self, *, cockpit, engine: dict, state_dir, server_base: str, registry: GW.Registry, write_config, model_id: str,
                 proxy_vars: dict, pane_mcp_url: Optional[str] = None, environ=None):
        self.cockpit = cockpit
        self.engine = engine
        self.state_dir = Path(state_dir)
        self.base = server_base.rstrip("/")
        self.registry = registry
        self.write_config = write_config          # (home, gateway_url, token, model_id, worker=, mcp_url=, mcp_headers=) -> path
        self.model_id = model_id
        self.proxy_vars = dict(proxy_vars)
        self.pane_mcp_url = pane_mcp_url
        self.environ = os.environ if environ is None else environ
        self.loop: Optional[asyncio.AbstractEventLoop] = None
        self.mcp_digests: dict = {}               # unit -> sha256 of its MCP bearer (the live main pane's)
        self._starting: dict = {}                 # record id -> concurrent future of _start_session

    # ------------------------------------------------------------------------------------------------- where things are
    @property
    def gateway_url(self) -> str:
        return f"{self.base}/engine/v1"

    def root(self) -> Path:
        return self.state_dir / "agent" / "hermes"

    def home_for(self, unit: str, binding: Optional[str] = None) -> Path:
        swarm, worker = _binding_parts(binding) if binding else ("", "")
        home = self.root() / str(unit)
        return home / "workers" / f"{swarm}-{worker}" if binding else home

    def hermes_bin(self) -> Path:
        return Path(self.engine["dir"]) / str(self.engine.get("hermes") or "env/bin/hermes")

    def tui_dir(self) -> Optional[Path]:
        named = (self.environ.get(TUI_ENV) or "").strip()
        if named:
            return Path(named)
        tui = self.engine.get("tui")
        return Path(self.engine["dir"]) / str(tui) if tui else None

    def node(self) -> Optional[str]:
        named = (self.environ.get(NODE_ENV) or "").strip()
        if named:
            return named if os.access(named, os.X_OK) else None
        return shutil.which("node", path=self.environ.get("PATH"))

    def problem(self) -> Optional[str]:
        """Why no Mode 1 pane can start here, with what to do; None when one can."""
        if not os.access(self.hermes_bin(), os.X_OK):
            return f"Lampway's Hermes engine has no hermes binary at {self.hermes_bin()}: rebuild it with scripts/lampway/engine_env.py"
        tui = self.tui_dir()
        if tui is None or not (tui / "dist" / "entry.js").is_file():
            return ("Hermes's TUI is not prebuilt for Lampway's engine (no ui-tui/dist/entry.js): rebuild the engine with "
                    f"scripts/lampway/engine_env.py, or point {TUI_ENV} at a prebuilt ui-tui")
        if not self.node():
            return (f"Lampway Agent's pane runs Hermes's TUI on Node.js, which was not found: install Node.js 22 or 24 (nodejs.org or "
                    f"your package manager) or point {NODE_ENV} at it. Lampway never downloads it")
        return None

    # ------------------------------------------------------------------------------------------------- the cockpit's hook
    def prepare(self, *, rid, unit, role, cwd, project_root, direct=(), task=None, name="", unit_label=None) -> dict:
        """Write the pane's home before herdr is asked (see the module docstring). Raises CockpitError, with help, when no pane can
        start here."""
        why = self.problem()
        if why:
            raise CockpitError(why)
        if not unit:
            raise CockpitError("Lampway's own pane belongs to a unit: a scene tab's conversation")
        worker = role == LY.WORKER
        binding = next((d.headers.get(HN.SESSION_HEADER) for d in direct if d.headers.get(HN.SESSION_HEADER)), None) if worker else None
        if worker and not binding:
            raise CockpitError("a Mode 1 worker's pane needs its swarm binding")
        home = self.home_for(unit, binding)
        for sub in ("", "home", "managed", "locks", "logs"):
            (home / sub).mkdir(parents=True, exist_ok=True, mode=0o700)
            os.chmod(home / sub, 0o700)
        port = free_port()
        serve_token = secrets.token_urlsafe(32)
        write_private(home / TOKEN_FILE, serve_token)
        key = binding or unit
        self.registry.revoke_session(key)                          # one live gateway key per pane
        gw_token = self.registry.issue_token(key)
        mcp_bearer = None
        if worker:
            d = next(d for d in direct if d.headers.get(HN.SESSION_HEADER))
            mcp_url, headers = d.url, {**d.headers, "Authorization": f"Bearer {d.token}"}
        else:
            mcp_bearer = secrets.token_urlsafe(32)
            mcp_url, headers = f"{self.base}/engine/mcp/{unit}", {"Authorization": f"Bearer {mcp_bearer}"}
        rendered: dict = {}
        try:
            self.write_config(home, self.gateway_url, gw_token, self.model_id, worker=worker, mcp_url=mcp_url, mcp_headers=headers,
                              rendered=rendered)
        except Exception:
            self.registry.revoke(gw_token)
            raise
        label = (f"Worker · {name}" if worker else f"Lampway · {unit_label or LY.short_id(unit)}")
        spec = {"hermes": str(self.hermes_bin()), "port": port, "cwd": str(project_root or cwd), "tui_dir": str(self.tui_dir()),
                "node": self.node(), "env": self.proxy_vars, "label": label, "unit": unit, "role": role,
                "toolsets": HC.serve_toolsets(rendered)}
        write_private(home / SPEC_FILE, json.dumps(spec, indent=1, sort_keys=True))
        if worker and task:
            write_private(home / TASK_FILE, str(task))
        if not worker:
            self.mcp_digests[unit] = GW.Registry.digest(mcp_bearer)
        return {"home": str(home), "port": port, "token_file": str(home / TOKEN_FILE), "gateway_token_sha256": GW.Registry.digest(gw_token),
                "mcp_token_sha256": GW.Registry.digest(mcp_bearer) if mcp_bearer else None, "stored_session_id": None,
                "_gateway_token": gw_token}

    def abandon(self, prepared: dict) -> None:
        """The pane never opened: its gateway key dies (its home stays, holding nothing live)."""
        token = prepared.get("_gateway_token")
        if token:
            self.registry.revoke(token)

    def opened(self, rec: dict) -> None:
        """The pane is recorded: create its Hermes session on this server's loop (and a worker's first prompt). Called from the
        cockpit's thread."""
        if self.loop is None:
            log.warning("Mode 1 pane %s opened with no server loop to create its session on", rec.get("id"))
            return
        self._starting[rec["id"]] = asyncio.run_coroutine_threadsafe(self._start_session(rec), self.loop)

    # ------------------------------------------------------------------------------------------------- sessions
    def info(self, rec: dict) -> Optional[UnitInfo]:
        try:
            token = Path(rec["token_file"]).read_text(encoding="utf-8").strip()
        except (OSError, KeyError, TypeError):
            return None
        home = Path(rec.get("home") or "")
        stored = rec.get("stored_session_id") or read_session(home)
        return UnitInfo(str(rec.get("unit") or ""), rec["id"], home, int(rec.get("port") or 0), token, stored or "")

    async def _start_session(self, rec: dict) -> str:
        """Wait for the pane's serve, then make sure the pane has a session: the one its home records, else a new one in the
        project root, written to ``session.json`` and the record. A worker's task is that new session's first prompt."""
        info = self.info(rec)
        if info is None:
            raise RuntimeError(f"Mode 1 pane {rec.get('id')} has no readable serve token")
        stored = read_session(info.home)
        if stored:
            if not rec.get("stored_session_id"):
                await asyncio.to_thread(self.cockpit.update_mode1, rec["id"], stored_session_id=stored)
            return stored
        ready = asyncio.Event()

        async def on_event(params):
            if params.get("type") == "session.info":
                ready.set()
        client = await connect_when_up(info, on_event=on_event)
        try:
            res = await client.call("session.create", {"cwd": rec.get("project_root") or rec.get("cwd"), "cols": 100})
            stored, live = str(res.get("stored_session_id") or ""), str(res.get("session_id") or "")
            write_private(info.home / SESSION_FILE, json.dumps({"stored_session_id": stored}))
            await asyncio.to_thread(self.cockpit.update_mode1, rec["id"], stored_session_id=stored)
            task_path = info.home / TASK_FILE
            if rec.get("role") == LY.WORKER and task_path.is_file():
                try:
                    await asyncio.wait_for(ready.wait(), READY_TIMEOUT_S)
                except asyncio.TimeoutError:
                    log.warning("worker pane %s: its session did not report ready; its task goes in anyway", rec["id"])
                await client.call("prompt.submit", {"session_id": live, "text": task_path.read_text(encoding="utf-8")})
                task_path.unlink()
            return stored
        finally:
            await client.close()

    async def session_ready(self, rec_id: str) -> str:
        fut = self._starting.get(rec_id)
        if fut is None:
            raise RuntimeError(f"no session is being created for pane {rec_id}")
        return await asyncio.wrap_future(fut)

    def record_session(self, info: UnitInfo, stored: str) -> None:
        """The pane moved to another session (``/new``, spec Q15): its home and record follow."""
        write_private(info.home / SESSION_FILE, json.dumps({"stored_session_id": stored}))
        self.cockpit.update_mode1(info.record_id, stored_session_id=stored)

    # ------------------------------------------------------------------------------------------------- units
    def _mains(self, unit: str) -> list:
        return sorted((r for r in self.cockpit.list_sessions() if HN.is_lampway(r.get("agent")) and r.get("unit") == unit
                       and r.get("role") == LY.MAIN and r.get("state") == "live"), key=lambda r: r.get("created_at") or 0)

    def known(self, unit: str) -> Optional[UnitInfo]:
        """The unit's live main pane, from its record (the newest)."""
        mains = self._mains(unit)
        return self.info(mains[-1]) if mains else None

    def alive(self, info: UnitInfo) -> bool:
        try:
            ok, _ = self.cockpit.pane_alive(info.record_id)
            return bool(ok)
        except Exception:  # noqa: BLE001 - herdr gone: not alive as far as Lampway can tell
            return False

    async def open(self, unit: str, label: Optional[str] = None) -> UnitInfo:
        """Open the unit's main pane (one tab per unit, A4) and wait until it has a session. Only the user's own chat calls this."""
        project = str(self.cockpit.project_root or Path.cwd())
        shown = " ".join(str(label or "").split()) or LY.short_id(unit)
        rec = await asyncio.to_thread(self.cockpit.create_session, HN.MODE1_ADAPTER, f"Lampway Agent for {shown}"[:100], project,
                                      by="user", unit=unit, unit_label=label, display_agent=f"Lampway · {shown}")
        stored = await self.session_ready(rec["id"])
        info = self.info({**rec, "stored_session_id": stored})
        if info is None:
            raise CockpitError("Lampway Agent's pane opened but its serve token cannot be read")
        return info

    def forget(self, rec: dict) -> None:
        """A Mode 1 worker's pane was closed (spec Q13): its gateway key, keyed by its swarm binding, ends with it."""
        if rec.get("role") == LY.WORKER and rec.get("swarm_binding"):
            self.registry.revoke_session(rec["swarm_binding"])

    def check_mcp(self, unit: str, token: str) -> bool:
        known = self.mcp_digests.get(unit)
        return bool(known and token) and secrets.compare_digest(known, GW.Registry.digest(token))

    def adopt(self) -> list:
        """After a restart (the cockpit reconciled first): every live Lampway pane's tokens are known again by their digests, so its
        Hermes thinks and calls Lampway's tools on (A1). Returns the re-adopted records."""
        out = []
        for rec in self.cockpit.list_sessions():
            if not HN.is_lampway(rec.get("agent")) or rec.get("state") != "live":
                continue
            key = rec.get("swarm_binding") or rec.get("unit")
            if rec.get("gateway_token_sha256") and key:
                self.registry.adopt_digest(key, rec["gateway_token_sha256"])
            if rec.get("role") == LY.MAIN and rec.get("mcp_token_sha256"):
                self.mcp_digests[rec["unit"]] = rec["mcp_token_sha256"]
            out.append(rec)
        return out


def read_session(home: Path) -> str:
    try:
        return str(json.loads((Path(home) / SESSION_FILE).read_text(encoding="utf-8")).get("stored_session_id") or "")
    except (OSError, ValueError, AttributeError):
        return ""


async def connect_when_up(info: UnitInfo, *, on_event=None, on_request=None, timeout: float = START_TIMEOUT_S) -> ServeClient:
    """A connected client of the pane's serve, retried while serve starts."""
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        client = ServeClient(info.port, info.token, on_event=on_event, on_request=on_request)
        try:
            await client.connect()
            return client
        except (OSError, asyncio.TimeoutError, ServeError, ConnectionError) as exc:
            last = exc
            await client.close()
        except Exception as exc:  # noqa: BLE001 - a handshake refused while serve starts
            last = exc
            await client.close()
        await asyncio.sleep(0.3)
    raise CockpitError(f"Lampway Agent's pane did not answer on its port within {timeout:.0f}s ({type(last).__name__})")
