# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The engine in production: Hermes in Mode 1's seat (docs/reports/agent-modes-spec.md E1.2-E1.5, E1.3's start-up check).

``create_app`` calls ``wire`` once. The engine runs Mode 1 only when both hold; otherwise the built-in loop stays, and one log line
says why:

* ``LAMPWAY_AGENT_ENGINE=hermes`` is set (the user's or the launcher's choice; nothing turns it on by itself), and
* a finished build is found: ``$LAMPWAY_ENGINES_DIR`` when it is set (and only there), else ``<repo>/build/engines``, else
  ``<state_dir>/engines`` (``runtime.find_engine``: the newest ``hermes/*/engine.json``).

Selected, the app's lifespan (``start``/``stop``/``tick``) gives the runtime Lampway's two doors and the user's choices:

* **the model gateway** (E1.4): ``http://127.0.0.1:<port>/engine/v1`` on this server; each child's key is a fresh
  ``gateway.Registry`` token for its session (an older one for the same session is revoked first, so a crashed child's key dies
  with it) and is revoked when the child stops;
* **the session's MCP endpoint** (E1.6): ``/engine/mcp/<session_id>`` on this server;
* **the egress proxy** (E1.5): ``engine/proxy.py``, started on loopback in the lifespan with the server's port as the gateway's;
* **the config** (E1.3): ``hermes_config.write`` from the ACTIVE Capabilities board and project, the terminal backend from the
  capability's ``options["backend"]`` (what the Client writes). A swarm worker's config (``worker=True``, spec S2) is the same
  board less what a worker never does (``WORKER_NEVER``);
* **the start-up check** (E1.3): ``hermes_config.check_advertised`` on each token's first chat request that carries tools, against
  the board its config was written from; a mismatch refuses that request and every later one of that child (``Registry.first_check``).

The server must be reachable on loopback (its doors are loopback only): a non-loopback ``LAMPWAY_HOST`` keeps the built-in loop.
"""

import asyncio
import ipaddress
import logging
import os
from pathlib import Path
from typing import Optional

from .. import capabilities as CAP
from . import gateway as GW
from . import hermes_config as HC
from . import proxy as PX
from .runtime import EngineRuntime, find_engine

log = logging.getLogger("lampway.engine")

SWITCH = "LAMPWAY_AGENT_ENGINE"
ENGINE_NAME = "hermes"
REPO_ENGINES = Path(__file__).resolve().parents[3] / "build" / "engines"
MODEL_ID = "lampway"                     # the id the engine asks the gateway for; the current main provider answers whatever it is
WILDCARD_BINDS = {"0.0.0.0", "::", ""}
#: Spec S2: what a swarm worker never does, whatever the parent chose (its tool list also leaves out ``ask_user``).
WORKER_NEVER = frozenset({"subagents", "swarm", "schedule", "panes.drive", "computer.use"})
WORKER_NEVER_FAMILIES = ("messaging.",)


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
    """(the engine build record, why) or (None, why the built-in loop stays)."""
    environ = os.environ if environ is None else environ
    choice = (environ.get(SWITCH) or "").strip().lower()
    if not choice:
        return None, f"{SWITCH} is not set (set it to {ENGINE_NAME} to run the Hermes engine)"
    if choice != ENGINE_NAME:
        return None, f"{SWITCH}={choice!r} names no engine Lampway has; the one engine is {ENGINE_NAME}"
    if not _loopback_reachable(host):
        return None, f"the server listens on {host}, not on loopback, and the engine's gateway and MCP endpoint answer loopback only"
    dirs = engines_dirs(state_dir, environ)
    for d in dirs:
        try:
            rec = find_engine(d)
        except Exception as exc:  # noqa: BLE001 - an unreadable record is no build
            log.warning("engine: the build record under %s is unreadable (%s)", d, type(exc).__name__)
            continue
        if rec is not None:
            return rec, f"the Hermes engine {rec.get('tag', '?')} from {rec['dir']}"
    return None, (f"{SWITCH}={ENGINE_NAME} but no finished engine build under {', '.join(str(d) for d in dirs)} "
                  "(scripts/lampway/engine_env.py builds one)")


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
    """The gateway's provider for a session: a swarm worker's own provider when the runtime names one
    (``EngineRuntime.provider_for``), else the current main provider. Callable with or without the session id."""
    def get(session_id: Optional[str] = None):
        engine = agent.engine
        pick = getattr(engine, "provider_for", None) if engine is not None and session_id else None
        return (pick(session_id) if pick is not None else None) or agent.provider
    return get


class EngineWiring:
    def __init__(self, engine: dict, *, settings, agent, registry: GW.Registry):
        self.engine = engine
        self.settings = settings
        self.agent = agent
        self.registry = registry
        self.runtime: Optional[EngineRuntime] = None
        self._boards: dict = {}                          # token digest -> the board its child's config was written from
        registry.first_check = self.check

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{int(self.settings.port)}"

    # -- the lifespan
    async def start(self) -> None:
        _, proxy_port = await PX.start(gateway_port=int(self.settings.port))
        base = self.base
        self.runtime = EngineRuntime(
            self.agent, engine=self.engine, state_dir=self.settings.state_dir, gateway_url=f"{base}/engine/v1",
            model_token_for=self.model_token, model_id=MODEL_ID, mcp_url_for=lambda sid: f"{base}/engine/mcp/{sid}",
            proxy_url=f"http://127.0.0.1:{proxy_port}", project_root=CAP.project(), config_writer=self.write_config,
            on_child_stop=self.child_stopped)
        self.agent.engine = self.runtime
        log.info("engine: Hermes %s runs Mode 1 (gateway %s/engine/v1, egress proxy on 127.0.0.1:%s)",
                 self.engine.get("tag", "?"), base, proxy_port)

    async def stop(self) -> None:
        rt, self.runtime = self.runtime, None
        if rt is not None:
            rt.kill_all()                                  # every child by its recorded PID
            try:
                await asyncio.wait_for(rt.stop(), 15)      # reaps them and revokes their keys
            except Exception:  # noqa: BLE001 - shutdown goes on
                log.debug("engine: stopping the children did not finish", exc_info=True)
            if self.agent.engine is rt:
                self.agent.engine = None
        await PX.stop()

    async def tick(self) -> None:
        """The server's 60 s tick: a child with no live turn past ``runtime.IDLE_REAP_S`` is stopped (E1.2)."""
        if self.runtime is not None:
            await self.runtime.reap_idle()

    # -- the runtime's hooks
    def model_token(self, session_id: str) -> str:
        self.registry.revoke_session(session_id)          # one live key per session's child
        return self.registry.issue_token(session_id)

    def child_stopped(self, es) -> None:
        if es.model_token:
            self.registry.revoke(es.model_token)
            self._boards.pop(GW.Registry._digest(es.model_token), None)

    def write_config(self, home, gateway_url, token, model_id, worker: bool = False):
        board = CAP.ACTIVE
        if board is None:
            raise HC.Refused("refused: the Capabilities board is not available, so the engine's config cannot be written")
        if worker:
            board = WorkerBoard(board)
        path = HC.write(home, board, CAP.project(), gateway_url, token, model_id, supports_vision=sees_images(self.agent))
        self._boards[GW.Registry._digest(token)] = board
        return path

    def check(self, session_id: str, token: str, tools) -> Optional[str]:
        board = self._boards.get(GW.Registry._digest(token)) or CAP.ACTIVE
        if board is None:
            return "refused: the Capabilities board is not available, so the engine's tools cannot be checked"
        mismatches = HC.check_advertised(tools, board, CAP.project())
        if not HC.refuses(mismatches):
            return None
        blocking = [m for m in mismatches if m.blocking]
        log.warning("engine: session %s refused at its start-up check: %s", session_id, ", ".join(m.tool for m in blocking))
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
    """``create_app``'s one call: the wiring when the engine is selected, else None; one log line either way."""
    engine, why = select(settings.state_dir, environ, host=settings.host)
    if engine is None:
        log.info("engine: the built-in agent loop runs Mode 1: %s", why)
        return None
    log.info("engine: selected %s", why)
    return EngineWiring(engine, settings=settings, agent=agent, registry=registry)
