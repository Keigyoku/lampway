# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine in production: Hermes in Mode 1's seat, every agent a pane (docs/reports/agent-modes-spec.md A1-A3, E1.3-E1.5).

``create_app`` calls ``wire`` once. Mode 1 runs only on the Hermes runtime (spec A0, A5): Lampway's own provider loop is gone, so
nothing else can run it and there is no switch. The engine is in the seat whenever

* a finished build is found: ``$LAMPWAY_ENGINES_DIR`` when it is set (and only there), else ``<repo>/build/engines``, else
  ``<state_dir>/engines`` (``find_engine``: the newest ``hermes/*/engine.json``, written last by scripts/lampway/engine_env.py), and
* the server is reachable on loopback (its doors answer loopback only).

Otherwise Mode 1 is unavailable on this server: one log line says why, and the hub refuses every Mode 1 chat with that reason and
its fix (``AgentHub.engine_problem``: the code, why, and the exact build command or setting), before any turn starts. The same
holds when the engine was selected but could not start (``start_failed``). ``LAMPWAY_AGENT_ENGINE``, the switch of the days when the
built-in loop could stand in, is no longer read; a server that finds it set says so once.

Selected, the app's lifespan (``start``/``stop``/``tick``) gives Mode 1's panes Lampway's two doors and the user's choices:

* **the model gateway** (E1.4): ``http://127.0.0.1:<port>/engine/v1`` on this server; each pane's key is a fresh
  ``gateway.Registry`` token for its unit (a worker's: its swarm binding), an older one for the same pane revoked first;
* **the MCP endpoints** (A3, S3): a main pane's ``/engine/mcp/<unit>`` with its per-unit bearer, a worker's the pane endpoint;
* **the egress proxy** (E1.5): ``engine/proxy.py`` on loopback, on the port it had before a restart when that port is free (the
  panes outlive the server and keep its address), with the server's port as the gateway's;
* **the config** (E1.3, A1): ``hermes_config.write`` from the ACTIVE Capabilities board and project, the terminal backend from the
  capability's ``options["backend"]``; a worker's (``worker=True``, spec S2) is the board less ``WORKER_NEVER``, without clarify;
* **the start-up check** (E1.3): ``hermes_config.check_advertised`` on each token's first chat request that carries tools, against
  the board its config was written from; a mismatch refuses that request and every later one of that pane (``Registry.first_check``);
* **a Capabilities change while panes run** (E2): ``capabilities.subscribe`` -> ``Mode1Units.capabilities_changed``: every live
  Lampway pane's config and toolset pin are re-rendered, its serve reloads them (``reload.env``, ``reload.mcp``; the conversation is
  kept), and the gateway checks its next tool list again (``Registry.recheck``); a turn about to start waits for that refresh;
* **the panes** (A1): ``units.Mode1Units`` is the cockpit's ``mode1`` hook and ``front.HermesFront`` the hub's engine (A2). The
  start re-adopts every live Lampway pane the cockpit reconciled (its tokens by their digests) and re-attaches to it. Shutdown
  closes this server's connections and stops the proxy; it never ends a pane or its serve (law 5).

"""

import asyncio
import ipaddress
import json
import logging
import os
from pathlib import Path
from typing import NamedTuple, Optional

from .. import capabilities as CAP
from . import gateway as GW
from . import hermes_config as HC
from . import proxy as PX

log = logging.getLogger("lampway.engine")

RETIRED_SWITCH = "LAMPWAY_AGENT_ENGINE"   # no longer read (spec A5): the engine runs Mode 1 whenever it is built
ENGINE_NAME = "hermes"
REPO_ENGINES = Path(__file__).resolve().parents[3] / "build" / "engines"
MODEL_ID = "lampway"                     # the id the engine asks the gateway for; the current main provider answers whatever it is
WILDCARD_BINDS = {"0.0.0.0", "::", ""}
PROXY_PORT_FILE = "proxy.port"
#: Spec S2: what a swarm worker never does, whatever the parent chose (its tool list also leaves out ``ask_user`` and ``clarify``).
WORKER_NEVER = frozenset({"subagents", "swarm", "schedule", "panes.drive", "computer.use"})
WORKER_NEVER_FAMILIES = ("messaging.",)


class Unavailable(NamedTuple):
    """Why Mode 1 cannot run on this server, as the hub's refusal says it: its code, why, and the exact fix."""
    code: str
    why: str
    fix: str


BUILD_FIX = "Build Lampway's pinned Hermes engine: scripts/lampway/engine_env.py (then restart Lampway)"


def start_failed(exc: BaseException) -> Unavailable:
    return Unavailable("engine_unavailable", f"the engine could not start: {type(exc).__name__}: {exc}",
                       "Read the server log (server.log in the Lampway home) for why, fix it, then restart Lampway")


def find_engine(engines_dir) -> Optional[dict]:
    """The newest finished build under ``<engines_dir>/hermes/*/engine.json`` (scripts/lampway/engine_env.py), or None."""
    base = Path(engines_dir) / "hermes"
    builds = sorted((p for p in base.glob("*/engine.json") if p.is_file()), key=lambda p: p.stat().st_mtime) if base.is_dir() else []
    if not builds:
        return None
    rec = json.loads(builds[-1].read_text())
    rec["dir"] = str(builds[-1].parent)
    rec["entry_path"] = str(builds[-1].parent / rec["entry"])
    return rec


def _loopback_reachable(host: str) -> bool:
    host = str(host or "").strip("[]").lower()
    if host in WILDCARD_BINDS or host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def engines_dirs(state_dir, environ) -> list:
    named = (environ.get("LAMPWAY_ENGINES_DIR") or "").strip()
    return [Path(named)] if named else [REPO_ENGINES, Path(state_dir) / "engines"]


def select(state_dir, environ=None, host: str = "127.0.0.1") -> tuple:
    """(the engine build record, what was selected), or (None, ``Unavailable``: why Mode 1 cannot run here, and its fix)."""
    environ = os.environ if environ is None else environ
    if not _loopback_reachable(host):
        return None, Unavailable("engine_unavailable", f"the server listens on {host}, not on loopback, and the engine's gateway and "
                                 "MCP endpoint answer loopback only", "Run Lampway's server on loopback (LAMPWAY_HOST=127.0.0.1, the default)")
    dirs = engines_dirs(state_dir, environ)
    for d in dirs:
        try:
            rec = find_engine(d)
        except Exception as exc:  # noqa: BLE001 - an unreadable record is no build
            log.warning("engine: the build record under %s is unreadable (%s)", d, type(exc).__name__)
            continue
        if rec is not None:
            return rec, f"the Hermes engine {rec.get('tag', '?')} from {rec['dir']}"
    return None, Unavailable("engine_not_built", f"no finished engine build under {', '.join(str(d) for d in dirs)}", BUILD_FIX)


class WorkerBoard:
    """A swarm worker's view of the Capabilities board (spec S2): the parent's choices, less ``WORKER_NEVER``. Read-only."""

    def __init__(self, board):
        self.board = board

    @staticmethod
    def never(cid: str) -> bool:
        return cid in WORKER_NEVER or str(cid).startswith(WORKER_NEVER_FAMILIES)

    def setting(self, cid: str, project: Optional[str] = None) -> dict:
        out = dict(self.board.setting(cid, project))
        if self.never(cid):
            out.update(enabled=False, scope="worker")
        return out

    def effective(self, cid: str, project: Optional[str] = None, routes_on=None) -> tuple:
        if self.never(cid):
            return False, f"{cid} is never a swarm worker's (spec S2)"
        return self.board.effective(cid, project, routes_on)


def provider_getter(agent):
    """The gateway's provider for a pane: the current main provider, read at call time. Callable with or without the session id.
    The engine's hidden swarm workers, which had a provider of their own, are gone (spec A5)."""
    def get(session_id: Optional[str] = None):
        return agent.provider
    return get


class EngineWiring:
    def __init__(self, engine: dict, *, settings, agent, registry: GW.Registry):
        self.engine = engine
        self.settings = settings
        self.agent = agent
        self.registry = registry
        self.front = None                                # front.HermesFront, while the server runs
        self.units = None                                # units.Mode1Units, the cockpit's mode1 hook
        self._boards: dict = {}                          # token digest -> (the board its pane's config was written from, asks_user)
        registry.first_check = self.check

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{int(self.settings.port)}"

    def _proxy_port_path(self) -> Path:
        return Path(self.settings.state_dir) / "agent" / "hermes" / PROXY_PORT_FILE

    def _previous_proxy_port(self) -> int:
        try:
            return int(self._proxy_port_path().read_text().strip())
        except (OSError, ValueError):
            return 0

    # -- the lifespan
    async def start(self) -> None:
        from .front import HermesFront
        from .units import Mode1Units, write_private
        previous = self._previous_proxy_port()
        try:
            _, proxy_port = await PX.start(port=previous, gateway_port=int(self.settings.port))
        except OSError:
            _, proxy_port = await PX.start(gateway_port=int(self.settings.port))
            if previous:
                log.warning("engine: the egress proxy's previous port %s is taken; panes started before this restart reach nothing "
                            "outside Lampway until they are reopened", previous)
        write_private(self._proxy_port_path(), str(proxy_port))
        cockpit = getattr(self.agent, "cockpit", None)
        if cockpit is None:
            raise RuntimeError("Mode 1 runs in panes on Lampway's herdr server, and this server has no herdr host")
        self.units = Mode1Units(cockpit=cockpit, engine=self.engine, state_dir=self.settings.state_dir, server_base=self.base,
                                registry=self.registry, write_config=self.write_config, model_id=MODEL_ID,
                                proxy_vars=PX.proxy_vars(f"http://127.0.0.1:{proxy_port}"), pane_mcp_url=getattr(cockpit, "pane_mcp_url", None))
        self.units.loop = asyncio.get_running_loop()
        self.front = HermesFront(self.agent, self.units)
        cockpit.mode1 = self.units
        self.agent.engine = self.front
        CAP.subscribe(self.units.capabilities_changed)      # spec E2: a switch reaches every running pane before its next tool call
        adopted = self.units.adopt()
        for rec in adopted:
            digest = rec.get("gateway_token_sha256")
            if digest:
                self._boards[digest] = (WorkerBoard(CAP.ACTIVE) if rec.get("role") == "worker" else None, rec.get("role") != "worker")
        await self.front.adopt(adopted)
        log.info("engine: Hermes %s runs Mode 1 in panes (gateway %s/engine/v1, egress proxy on 127.0.0.1:%s, %d pane(s) re-adopted)",
                 self.engine.get("tag", "?"), self.base, proxy_port, len(adopted))

    async def stop(self) -> None:
        if self.units is not None:
            CAP.unsubscribe(self.units.capabilities_changed)
        front, self.front = self.front, None
        if front is not None:
            try:
                await asyncio.wait_for(front.close(), 15)    # this server's connections only: the panes run on (law 5)
            except Exception:  # noqa: BLE001 - shutdown goes on
                log.debug("engine: closing the panes' connections did not finish", exc_info=True)
            if self.agent.engine is front:
                self.agent.engine = None
        cockpit = getattr(self.agent, "cockpit", None)
        if cockpit is not None and getattr(cockpit, "mode1", None) is self.units:
            cockpit.mode1 = None
        await PX.stop()

    async def tick(self) -> None:
        """The server's 60 s tick. Nothing to reap: every agent is a pane, and a pane ends only by the user (A0, law 5)."""
        return None

    # -- the panes' hooks
    def write_config(self, home, gateway_url, token, model_id, worker: bool = False, mcp_url=None, mcp_headers=None, rendered=None):
        board = CAP.ACTIVE
        if board is None:
            raise HC.Refused("refused: the Capabilities board is not available, so the engine's config cannot be written")
        if worker:
            board = WorkerBoard(board)
        path = HC.write(home, board, CAP.project(), gateway_url, token, model_id, supports_vision=sees_images(self.agent), rendered=rendered,
                        mcp_url=mcp_url, mcp_headers=mcp_headers, asks_user=not worker)
        self._boards[GW.Registry.digest(token)] = (board, not worker)
        return path

    def check(self, session_id: str, token: str, tools) -> Optional[str]:
        board, asks_user = self._boards.get(GW.Registry.digest(token)) or (None, True)
        board = board or CAP.ACTIVE
        if board is None:
            return "refused: the Capabilities board is not available, so the engine's tools cannot be checked"
        mismatches = HC.check_advertised(tools, board, CAP.project(), asks_user=asks_user)
        if not HC.refuses(mismatches):
            return None
        blocking = [m for m in mismatches if m.blocking]
        log.warning("engine: pane %s refused at its start-up check: %s", session_id, ", ".join(m.tool for m in blocking))
        return ("refused: the engine offered tools your Capabilities do not allow, so this session was stopped before the model "
                "saw them: " + "; ".join(m.why for m in blocking) + ". Lampway's engine config and the pinned engine disagree "
                "(spec E1.3, E1.8).")


def sees_images(agent) -> Optional[bool]:
    """Whether the main provider's model sees images (spec R3, R0a): Anthropic does; a key or endpoint saved in the dialog says so
    itself (its supports_vision flag); Sign in with ChatGPT is held back until its vision probe is recorded; anything else is
    unknown (None: Hermes decides from its own catalogue)."""
    provider = getattr(agent, "provider", None)
    name = getattr(provider, "name", "") or ""
    if name == "anthropic":
        return True
    if name == "chatgpt_plan":
        return False
    if name in ("openai", "openai_compat"):
        store = getattr(agent, "settings_store", None)
        byok = store.byok() if store is not None else None
        if isinstance(byok, dict) and "supports_vision" in byok:
            return bool(byok["supports_vision"])
    return None


def wire(settings, agent, registry: GW.Registry, environ=None) -> Optional[EngineWiring]:
    """``create_app``'s one call: the wiring when the engine is selected, else None and the hub told why (its Mode 1 refusal); one
    log line either way."""
    environ = os.environ if environ is None else environ
    if (environ.get(RETIRED_SWITCH) or "").strip():
        log.warning("engine: %s is no longer read: Mode 1 runs on the Hermes engine whenever it is built, and only on it",
                    RETIRED_SWITCH)
    engine, why = select(settings.state_dir, environ, host=settings.host)
    if engine is None:
        agent.engine_problem = tuple(why)
        log.warning("engine: Mode 1 is unavailable on this server, and a Mode 1 chat is refused: %s (%s)", why.why, why.fix)
        return None
    log.info("engine: selected %s", why)
    return EngineWiring(engine, settings=settings, agent=agent, registry=registry)
