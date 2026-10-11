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
  ``gateway.Registry`` token for its unit (a worker's: its swarm binding), an older one for the same pane revoked first; a main
  pane is answered by the main provider, a worker's by the ``agent.worker`` choice (``provider_getter``, spec S2);
* **the MCP endpoints** (A3, S3): a main pane's ``/engine/mcp/<unit>`` with its per-unit bearer, a worker's the pane endpoint;
* **the egress proxy** (E1.5): ``engine/proxy.py`` on loopback, on the port it had before a restart when that port is free (the
  panes outlive the server and keep its address), with the server's port as the gateway's;
* **the config** (E1.3, A1): ``hermes_config.write`` from the ACTIVE Capabilities board and project, the terminal backend from the
  capability's ``options["backend"]``, and Lampway's guidance on its tools (``agent/prompt.py``) as Hermes's ``agent.system_prompt``;
  a worker's (``worker=True``, spec S2) is the board less ``WORKER_NEVER``, without clarify, its prompt the one its task carries;
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
import copy
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
#: Spec S2: what a swarm worker never does, whatever the parent chose (its tool list also leaves out ``clarify``).
WORKER_NEVER = frozenset({"subagents", "swarm", "schedule", "background", "panes.drive", "computer.use"})
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


#: How many Mode 1 worker panes' providers the gateway keeps (a swarm has at most 6 workers; older entries are dropped first).
WORKER_PROVIDERS_KEPT = 64


def is_worker_session(session_id) -> bool:
    """A Mode 1 worker pane's gateway token is keyed by its swarm binding ``swarm:<swarm_id>:<worker_id>`` (``Mode1Units.prepare``);
    a main pane's by its unit (the scene session id)."""
    parts = str(session_id or "").split(":")
    return len(parts) == 3 and parts[0] == "swarm" and all(parts)


def selected_vision(provider, agent, resolution=None) -> Optional[bool]:
    """Vision belongs to this selected model/endpoint, never a different parent or saved model."""
    name = getattr(provider, "name", "")
    if name == "chatgpt_plan":
        params = getattr(resolution, "params", {}) if resolution is not None else {}
        if "supports_vision" in params:
            matched = params.get("model", getattr(resolution, "model", None)) == getattr(provider, "model", None)
            if not matched or params["supports_vision"] is not True:
                return False
        from ..chatgpt_vision import admitted
        return admitted(getattr(provider, "auth", None), getattr(provider, "model", None),
                        str(getattr(provider, "base_url", "")) + "/responses")
    model = getattr(provider, "model", None)
    params = getattr(resolution, "params", {}) if resolution is not None else {}
    if "supports_vision" in params:
        matched = (params.get("model", getattr(resolution, "model", None)) == model)
        if name in {"openai", "openai_compat"}:
            matched = matched and str(params.get("base_url", "")).rstrip("/") == str(getattr(provider, "base_url", "")).rstrip("/")
        return matched and params["supports_vision"] is True
    store = getattr(agent, "settings_store", None)
    read_byok = getattr(store, "byok", None) if name in {"anthropic", "openai", "openai_compat"} else None
    byok = read_byok() if callable(read_byok) else None
    if isinstance(byok, dict) and byok.get("provider") == name:
        matched = byok.get("model") == model
        if name in {"openai", "openai_compat"}:
            matched = matched and str(byok.get("base_url") or "").rstrip("/") == str(getattr(provider, "base_url", "")).rstrip("/")
        if matched and "supports_vision" in byok:
            return byok["supports_vision"] is True
        return name == "anthropic"
    return True if name == "anthropic" else getattr(provider, "supports_vision", None)


def _resolution_vision(agent, resolution, chatgpt_auth=None) -> Optional[bool]:
    """Read resolved metadata without constructing a provider or inspecting credentials."""
    from types import SimpleNamespace
    params = resolution.params
    metadata = SimpleNamespace(name=resolution.provider,
        model=params.get("model") if resolution.provider == "openai" else resolution.model,
        base_url="https://api.openai.com/v1" if resolution.provider == "chatgpt_plan" else params.get("base_url", ""),
        auth=chatgpt_auth if chatgpt_auth is not None else getattr(agent.provider, "auth", None))
    return selected_vision(metadata, agent, resolution)


def provider_getter(agent, *, settings=None, chatgpt_auth=None):
    """The gateway's provider for a pane, decided from its token's session (spec S2 as superseded by A):

    * a unit's main pane: the current main provider (``agent.provider``, the ``agent.main`` choice), read at call time;
    * a Mode 1 worker's pane (its token keyed by its swarm binding): the spawn-time ``agent.worker`` resolution,
      built by the hub's ``swarm_provider_factory`` at its FIRST call and kept for that worker's life. No resolution (including a
      surviving pane after a server restart) or an incompatible factory refuses the call; no worker label follows the current
      main provider or reselects from changed Settings. The gateway reports the refusal as an OpenAI-style error.

    Callable with or without the session id (``models-dev.json`` asks without one: the main provider)."""
    import collections
    workers: "collections.OrderedDict" = collections.OrderedDict()

    def get(session_id: Optional[str] = None, requested_model=None):
        from .context_settings import SUMMARY_PREFIX, Store as ContextStore, selected_summary
        if isinstance(requested_model, str) and requested_model.startswith(SUMMARY_PREFIX):
            if settings is None:
                raise ValueError("The Context settings are unavailable")
            from ..herdr import harnesses as HN
            recs = agent.cockpit.list_sessions()
            if is_worker_session(session_id):
                bindings = getattr(getattr(agent, "swarm", None), "bindings", None)
                if bindings is None or not bindings.is_live(session_id) or bindings.choice_for(session_id) is None:
                    raise ValueError("The summary alias requires a live owned worker job binding")
                matched = [r for r in recs if r.get("swarm_binding") == session_id
                           and r.get("role") == "worker" and r.get("created_by") == "swarm"]
            else:
                matched = [r for r in recs if r.get("unit") == session_id and not r.get("swarm_binding")]
            projects = {r.get("project_root") for r in matched if r.get("state") == "live"
                        and HN.is_lampway(r.get("agent")) and r.get("project_root")}
            if len(projects) != 1:
                raise ValueError("The summarizer alias requires exactly one live project-bound pane")
            resolution = selected_summary(ContextStore(settings.state_dir), projects.pop(), settings, requested_model)
            return _SummaryProvider(settings, agent, resolution, chatgpt_auth)
        if not is_worker_session(session_id):
            return agent.provider
        key = str(session_id)
        cached = workers.get(key)
        provider = cached[0] if cached is not None else None
        if provider is None:
            factory = getattr(agent, "swarm_provider_factory", None)
            bindings = getattr(getattr(agent, "swarm", None), "bindings", None)
            choice = bindings.choice_for(key) if bindings is not None else None
            if choice is not None:
                # The same choice that opened this pane must answer it. An old
                # factory cannot silently choose another service from Settings.
                import inspect
                parameters = inspect.signature(factory).parameters if factory is not None else {}
                if "resolution" not in parameters and not any(p.kind == p.VAR_KEYWORD for p in parameters.values()):
                    raise ValueError("the worker provider factory does not support its saved Choices resolution")
                provider = factory(key.rsplit(":", 1)[1], resolution=choice)
            else:
                raise ValueError("the pinned worker choice is unavailable after this server restart; "
                                 "this pane cannot make model calls. Start a new swarm using your saved Choices")
            workers[key] = (provider, selected_vision(provider, agent, choice), copy.deepcopy(choice))
            while len(workers) > WORKER_PROVIDERS_KEPT:
                workers.popitem(last=False)
        return provider

    def vision_for(session_id, provider):
        # Capability is request metadata, not a mutation of potentially shared providers.
        if isinstance(provider, _SummaryProvider):
            return provider.supports_vision
        if not is_worker_session(session_id):
            return selected_vision(provider, agent)
        cached = workers.get(str(session_id))
        if cached is not None and cached[0] is provider and getattr(provider, "name", "") == "chatgpt_plan":
            # Receipt qualification is current; provider/model and explicit choice restrictions stay pinned.
            return selected_vision(provider, agent, cached[2])
        return cached[1] if cached is not None and cached[0] is provider else False

    get.vision_for = vision_for
    return get


class EngineWiring:
    def __init__(self, engine: dict, *, settings, agent, registry: GW.Registry, chatgpt_auth=None):
        self.chatgpt_auth = chatgpt_auth
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
        try:
            await self.units.maintain_sessions()
        except Exception:
            log.warning("native session visibility maintenance failed at restart", exc_info=True)
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
        """The server's 60 s tick: native ended-history visibility only; panes are never reaped (A0, law 5, Q2)."""
        if self.units is not None:
            await self.units.maintain_sessions()

    # -- the panes' hooks
    @HC.serialized_config
    def write_config(self, home, gateway_url, token, model_id, worker: bool = False, mcp_url=None, mcp_headers=None, rendered=None, project=None):
        board = CAP.ACTIVE
        if board is None:
            raise HC.Refused("refused: the Capabilities board is not available, so the engine's config cannot be written")
        if worker:
            board = WorkerBoard(board)
        from ..agent.prompt import SYSTEM_PROMPT
        from .context_settings import Store as ContextStore
        project = project or CAP.project()
        vision = selected_vision(self.agent.provider, self.agent)
        if worker:
            binding = (mcp_headers or {}).get("X-Mixar-Session-Id")
            bindings = getattr(getattr(self.agent, "swarm", None), "bindings", None)
            choice = bindings.choice_for(binding) if bindings is not None else None
            vision = _resolution_vision(self.agent, choice, self.chatgpt_auth) if choice is not None else False
        path = HC.write(home, board, project, gateway_url, token, model_id, supports_vision=vision if isinstance(vision, bool) else None, rendered=rendered,
                        mcp_url=mcp_url, mcp_headers=mcp_headers, asks_user=not worker,
                        instructions=None if worker else SYSTEM_PROMPT,
                        context=ContextStore(self.settings.state_dir).config(project))     # a worker's prompt comes with its task (S3)
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
        return getattr(provider, "supports_vision", False) is True
    if name in ("openai", "openai_compat"):
        store = getattr(agent, "settings_store", None)
        byok = store.byok() if store is not None else None
        if isinstance(byok, dict) and "supports_vision" in byok:
            return bool(byok["supports_vision"])
    return None


def wire(settings, agent, registry: GW.Registry, environ=None, *, chatgpt_auth=None) -> Optional[EngineWiring]:
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
    return EngineWiring(engine, settings=settings, agent=agent, registry=registry, chatgpt_auth=chatgpt_auth)


class _SummaryProvider:
    """One call to the explicit resolved model, through existing provider and egress guards."""
    def __init__(self, settings, agent, resolution, chatgpt_auth=None):
        self.chatgpt_auth = chatgpt_auth
        self.settings, self.agent, self.resolution = settings, agent, resolution
        self.name = resolution.provider
        self.model = resolution.params.get("model") if resolution.provider == "openai" else resolution.model
        self.auth = chatgpt_auth if chatgpt_auth is not None else getattr(agent.provider, "auth", None)
        self.base_url = "https://api.openai.com/v1" if self.name == "chatgpt_plan" else resolution.params.get("base_url", "")
        self.supports_vision = _resolution_vision(agent, resolution, self.auth)

    async def stream(self, request):
        from ..agent.providers import make_provider, ResolvedWorkerProvider
        # Reuse the app-owned ChatGPT auth instance; no credentials or grants copied.
        auth = self.chatgpt_auth if self.chatgpt_auth is not None else getattr(self.agent.provider, 'auth', None)
        if self.resolution.provider == 'chatgpt_plan' and auth is None:
            raise ValueError('The app-owned ChatGPT authentication is unavailable')
        provider = make_provider(self.settings, chatgpt_auth=auth, resolution=self.resolution)
        guarded = ResolvedWorkerProvider(provider, self.resolution)
        try:
            async for event in guarded.stream(request):
                yield event
        finally:
            # These clients were made for this call, never the main pane's shared client.
            import inspect
            client = getattr(provider, 'client', None)
            close = getattr(client, 'aclose', None) or getattr(client, 'close', None)
            if close is not None:
                result = close()
                if inspect.isawaitable(result):
                    await result
