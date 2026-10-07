# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Hermes in the seat: Lampway's Mode 1 engine over ACP (docs/reports/agent-modes-spec.md E1.2, E1.6, E1.7).

Lampway's server is an ACP *client*. Per scene tab it runs one pinned ``hermes acp`` child (E1.2) with its own
``HERMES_HOME=<state_dir>/agent/hermes/<session_id>``; Hermes owns the conversation and its durability (captain, 2026-10-07).
Lampway keeps the client protocol, the tools, the gates and the model gateway:

* **Models** go only to Lampway's gateway (E1.4): the child's config names it as a ``custom`` provider with a per-process token.
* **Egress**: the child's proxy variables point at Lampway's loopback proxy (E1.5); ``NO_PROXY`` names loopback only.
* **Tools** (E1.6): Lampway serves the session one HTTP MCP endpoint, ``/engine/mcp/<session_id>``, with the agent's full registry
  as the user's Capabilities allow; every call runs through ``AgentHub._run_tool`` (the Blender bridge, capabilities, spend plans,
  receipts). Hermes registers them as ``mcp__lampway__<tool>`` (measured 2026-10-07).
* **Mapping** (E1.7): ``agent.chat`` -> ``prompt``; ``agent.cancel`` -> ``cancel``; ``agent_message_chunk`` -> the bubble's text;
  ``tool_call`` / ``tool_call_update`` -> ``steps`` rows. A question (``ask_user`` over MCP) ends the client's turn as today while
  the ACP prompt keeps running, blocked in that MCP call; the user's answer resolves the call and the client's next turn attaches
  to the same running prompt.

Measured against the pinned release (v2026.9.24) and the ACP SDK (agent-client-protocol 0.9.0): initialize ~1 s, a cold
``new_session`` ~20 s, a short prompt < 1 s. ``[UNVERIFIED]``: per-process isolation beyond one session per child,
``load_session`` replaying history as notifications, memory per child.
"""

import asyncio
import json
import logging
import os
import secrets
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

log = logging.getLogger("lampway.engine")

MCP_PREFIX = "mcp__lampway__"
IDLE_REAP_S = 600.0                    # E1.2: a child with no live turn is reaped after 10 minutes
SCRUB = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")


@dataclass
class Sink:
    """Where the running prompt's events go: the client turn currently attached to it."""
    socket: object
    session: object
    turn: object
    stream: object
    bubble_id: str
    steps: list
    text: list = field(default_factory=list)


@dataclass
class EngineSession:
    session_id: str
    home: Path
    proc: Optional[asyncio.subprocess.Process] = None
    conn: object = None
    acp_session_id: str = ""
    mcp_token: str = ""
    model_token: str = ""
    prompt_task: Optional[asyncio.Task] = None
    sink: Optional[Sink] = None
    question: Optional[asyncio.Future] = None        # resolved with the user's answer to ask_user
    asked: Optional[asyncio.Event] = None            # set when the running prompt stops for a question
    last_used: float = 0.0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    # A swarm worker's session (spec S2): its own tool list and router (the worker's headless Lampway), its own provider behind the
    # gateway (agent.worker), and its text collected into the worker's summary instead of a client turn's bubble.
    worker: bool = False
    tools: Optional[list] = None
    tool_router: object = None
    provider: object = None
    collector: Optional[list] = None
    on_progress: object = None


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


def child_env(home: Path, proxy_url: Optional[str], base_env=None) -> dict:
    """The engine child's environment: the server's, with every secret-shaped variable removed (Hermes holds no key), its own
    HERMES_HOME and HOME inside it (never the user's ~/.hermes), and every proxy variable at Lampway's proxy. Loopback stays
    direct so the gateway and the MCP endpoint are reachable."""
    env = {k: v for k, v in (os.environ if base_env is None else base_env).items()
           if not any(t in k.upper() for t in SCRUB) and not k.upper().startswith(("HERMES_", "OPENAI_", "ANTHROPIC_", "OPENROUTER_"))
           and k.upper() not in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "NO_PROXY")}
    env.update(HERMES_HOME=str(home), HOME=str(home / "home"), NO_COLOR="1", PYTHONUNBUFFERED="1")
    if proxy_url:
        for k in ("HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY", "https_proxy", "http_proxy", "all_proxy"):
            env[k] = proxy_url
    env["NO_PROXY"] = env["no_proxy"] = "127.0.0.1,localhost,::1"
    return env


def minimal_config(gateway_url: str, model_token: str, model_id: str) -> str:
    """The smallest config.yaml that makes the gateway the engine's only model endpoint. E1.3 (engine/hermes_config.py) renders
    the full one from the user's Capabilities; this is the fallback and the conformance suite's baseline."""
    return ("model:\n"
            f"  default: {json.dumps(model_id)}\n"
            "  provider: custom\n"
            f"  base_url: {json.dumps(gateway_url)}\n"
            f"  api_key: {json.dumps(model_token)}\n")


class LampwayACPClient:
    """The client half of ACP for one engine session: maps the engine's updates onto the client's turn events."""

    def __init__(self, es: EngineSession, runtime: "EngineRuntime"):
        self.es = es
        self.runtime = runtime

    async def session_update(self, session_id, update, **kw):
        sink = self.es.sink
        kind = getattr(update, "session_update", "")
        if sink is None:
            if self.es.collector is not None:                       # a swarm worker: its words become its summary
                if kind == "agent_message_chunk":
                    self.es.collector.append(getattr(getattr(update, "content", None), "text", "") or "")
                elif kind == "tool_call" and callable(self.es.on_progress):
                    self.es.on_progress(f"{self.es.session_id.rsplit(':', 1)[-1]}: {getattr(update, 'title', '')}")
            return
        try:
            if kind == "agent_message_chunk":
                text = getattr(getattr(update, "content", None), "text", "") or ""
                if text:
                    sink.text.append(text)
                    await sink.stream.emit({"bubble_id": sink.bubble_id, "ephemeral": {"append": text}})
            elif kind == "agent_thought_chunk":
                text = getattr(getattr(update, "content", None), "text", "") or ""
                if text:
                    await sink.stream.emit({"bubble_id": sink.bubble_id, "ephemeral": {"append": text}})
            elif kind == "tool_call":
                title = str(getattr(update, "title", "") or "tool")
                label = title[len(MCP_PREFIX):] if title.startswith(MCP_PREFIX) else title
                sink.steps.append({"id": update.tool_call_id, "kind": "tool", "label": label, "target": "", "detail": "",
                                   "status": "running"})
                await sink.stream.emit({"bubble_id": sink.bubble_id, "steps": {"items": list(sink.steps)}})
            elif kind == "tool_call_update":
                status = str(getattr(update, "status", "") or "")
                for step in sink.steps:
                    if step["id"] == update.tool_call_id and status in ("completed", "failed"):
                        step["status"] = "done" if status == "completed" else "failed"
                await sink.stream.emit({"bubble_id": sink.bubble_id, "steps": {"items": list(sink.steps)}})
        except Exception:  # noqa: BLE001 - a socket that went away must not break the engine's stream
            log.debug("engine update not delivered", exc_info=True)

    async def request_permission(self, options, session_id, tool_call, **kw):
        """Hermes asks before an action the user's Capabilities set to ask (E2). Until the client's approval input is wired (R4),
        nothing is allowed without the user: the request is refused and the engine is told so."""
        from acp.schema import DeniedOutcome, RequestPermissionResponse
        log.info("engine permission request refused (no approval surface yet): %s", getattr(tool_call, "title", ""))
        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))

    # The engine is never given the client's file system or terminals: everything goes through Lampway's tools.
    async def write_text_file(self, *a, **k):
        raise RuntimeError("Lampway does not lend its file system to the engine; use Lampway's tools")

    async def read_text_file(self, *a, **k):
        raise RuntimeError("Lampway does not lend its file system to the engine; use Lampway's tools")

    async def create_terminal(self, *a, **k):
        raise RuntimeError("Lampway does not lend a terminal to the engine")

    async def terminal_output(self, *a, **k):
        raise RuntimeError("no terminal")

    async def release_terminal(self, *a, **k):
        return None

    async def wait_for_terminal_exit(self, *a, **k):
        raise RuntimeError("no terminal")

    async def kill_terminal(self, *a, **k):
        return None

    async def ext_method(self, method, params):
        return {}

    async def ext_notification(self, method, params):
        return None

    def on_connect(self, conn):
        pass


class EngineRuntime:
    """One engine child per scene session, driven over ACP; the AgentHub calls ``drive`` instead of its own model loop."""

    def __init__(self, hub, *, engine: dict, state_dir, gateway_url: str, model_token_for, model_id: str = "lampway",
                 mcp_url_for, proxy_url: Optional[str] = None, project_root: Optional[str] = None, config_writer=None):
        self.hub = hub
        self.engine = engine
        self.state_dir = Path(state_dir)
        self.gateway_url = gateway_url
        self.model_token_for = model_token_for            # session_id -> a gateway token for that child
        self.model_id = model_id
        self.mcp_url_for = mcp_url_for                    # session_id -> the engine MCP endpoint URL
        self.proxy_url = proxy_url
        self.project_root = project_root or os.environ.get("LAMPWAY_PROJECT_ROOT") or os.getcwd()
        self.config_writer = config_writer                # (home, gateway_url, token, model_id) -> None; E1.3
        self.sessions: dict[str, EngineSession] = {}

    # ------------------------------------------------------------------ children (E1.2)
    def _session(self, session_id: str) -> EngineSession:
        es = self.sessions.get(session_id)
        if es is None:
            home = self.state_dir / "agent" / "hermes" / session_id
            es = self.sessions[session_id] = EngineSession(session_id, home)
        return es

    def mcp_token(self, session_id: str) -> str:
        return self._session(session_id).mcp_token

    def session_for_token(self, session_id: str, token: str) -> Optional[EngineSession]:
        es = self.sessions.get(session_id)
        return es if es is not None and es.mcp_token and secrets.compare_digest(es.mcp_token, token or "") else None

    async def _ensure_child(self, es: EngineSession) -> None:
        if es.proc is not None and es.proc.returncode is None and es.conn is not None:
            return
        from acp import connect_to_agent
        from acp.schema import HttpHeader, HttpMcpServer
        es.home.mkdir(parents=True, exist_ok=True)
        os.chmod(es.home, 0o700)
        (es.home / "home").mkdir(exist_ok=True)
        es.model_token = self.model_token_for(es.session_id)
        es.mcp_token = es.mcp_token or secrets.token_urlsafe(32)
        if self.config_writer is not None:
            # A worker's config is its parent's choices minus what would let it act outside its task (spec S2).
            self.config_writer(es.home, self.gateway_url, es.model_token, self.model_id, **({"worker": True} if es.worker else {}))
        else:
            cfg = es.home / "config.yaml"
            cfg.write_text(minimal_config(self.gateway_url, es.model_token, self.model_id))
            os.chmod(cfg, 0o600)
        es.proc = await asyncio.create_subprocess_exec(
            self.engine["entry_path"], stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL, env=child_env(es.home, self.proxy_url), cwd=self.project_root,
            limit=16 * 1024 * 1024)
        es.conn = connect_to_agent(LampwayACPClient(es, self), es.proc.stdin, es.proc.stdout)
        await asyncio.wait_for(es.conn.initialize(protocol_version=1), 60)
        lampway = HttpMcpServer(type="http", name="lampway", url=self.mcp_url_for(es.session_id),
                                headers=[HttpHeader(name="Authorization", value=f"Bearer {es.mcp_token}")])
        known = es.home / "lampway_session.json"
        acp_id = json.loads(known.read_text()).get("acp_session_id") if known.is_file() else ""
        if acp_id:                                       # Hermes keeps the conversation (captain, 2026-10-07): reattach to it
            loaded = await asyncio.wait_for(es.conn.load_session(cwd=self.project_root, session_id=acp_id, mcp_servers=[lampway]), 180)
            if loaded is None:
                acp_id = ""
        if not acp_id:
            created = await asyncio.wait_for(es.conn.new_session(cwd=self.project_root, mcp_servers=[lampway]), 180)
            acp_id = created.session_id
            known.write_text(json.dumps({"acp_session_id": acp_id}))
            os.chmod(known, 0o600)
        es.acp_session_id = acp_id

    async def stop(self, session_id: Optional[str] = None) -> None:
        for sid in ([session_id] if session_id else list(self.sessions)):
            es = self.sessions.get(sid)
            if es is None or es.proc is None:
                continue
            if es.proc.returncode is None:
                es.proc.terminate()
                try:
                    await asyncio.wait_for(es.proc.wait(), 10)
                except asyncio.TimeoutError:
                    es.proc.kill()
            es.proc, es.conn = None, None

    def kill_all(self) -> None:
        """Server shutdown from any thread or loop: every engine child gets SIGTERM by its recorded PID (never a pattern kill)."""
        import signal
        for es in self.sessions.values():
            if es.proc is not None and es.proc.returncode is None:
                try:
                    os.kill(es.proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    async def reap_idle(self, now: Optional[float] = None) -> int:
        now = time.time() if now is None else now
        n = 0
        for sid, es in list(self.sessions.items()):
            busy = es.prompt_task is not None and not es.prompt_task.done()
            if es.proc is not None and not busy and now - es.last_used > IDLE_REAP_S:
                await self.stop(sid)
                n += 1
        return n

    # ------------------------------------------------------------------ the turn (E1.7)
    async def drive(self, socket, session, turn, stream, bubble_id, steps, user_text: Optional[str]) -> None:
        """Run (or continue) the session's engine prompt for this client turn. Returns when the prompt ends or stops for a
        question (then ``turn.asked`` is set and the prompt keeps running)."""
        es = self._session(session.session_id)
        es.last_used = time.time()
        async with es.lock:
            await self._ensure_child(es)
            if user_text is not None:
                from acp import text_block
                if es.prompt_task is not None and not es.prompt_task.done():
                    await es.conn.cancel(session_id=es.acp_session_id)       # R4's join-the-turn is not built yet: a new message replaces
                    try:
                        await es.prompt_task
                    except BaseException:  # noqa: BLE001
                        pass
                es.prompt_task = asyncio.create_task(es.conn.prompt(session_id=es.acp_session_id, prompt=[text_block(user_text)]))
            if es.prompt_task is None:
                return
            es.sink = Sink(socket, session, turn, stream, bubble_id, steps)
            es.asked = asyncio.Event()
        asked = asyncio.create_task(es.asked.wait())
        try:
            done, _ = await asyncio.wait({es.prompt_task, asked}, return_when=asyncio.FIRST_COMPLETED)
        except asyncio.CancelledError:
            asked.cancel()
            if es.conn is not None and es.prompt_task is not None and not es.prompt_task.done():
                try:
                    await es.conn.cancel(session_id=es.acp_session_id)
                except Exception:  # noqa: BLE001
                    log.debug("engine cancel failed", exc_info=True)
            raise
        asked.cancel()
        if es.prompt_task in done:
            resp = es.prompt_task.result()
            text = "".join(es.sink.text).strip()
            stop = str(getattr(resp, "stop_reason", "") or "")
            if stop == "max_tokens":
                text += "\n\n(The reply was cut off at the model's output limit.)"
            if text:
                await stream.emit({"bubble_id": bubble_id, "content": {"set": text}})
            es.sink = None
            es.prompt_task = None
        # else: a question: the hub's _ask already ended the client turn's bubble; the prompt continues

    def has_question(self, session_id: str) -> bool:
        es = self.sessions.get(session_id)
        return es is not None and es.question is not None and not es.question.done()

    def answer(self, session_id: str, text: str) -> None:
        es = self.sessions.get(session_id)
        if es is not None and es.question is not None and not es.question.done():
            es.question.set_result(text)

    # ------------------------------------------------------------------ swarm workers (S2)
    def provider_for(self, session_id: Optional[str]):
        """The provider the gateway answers this engine session with: a worker's own (agent.worker), else None (the main one)."""
        es = self.sessions.get(session_id or "")
        return es.provider if es is not None else None

    async def run_worker(self, key: str, home: Path, prompt_text: str, *, tools: list, tool_router, provider=None,
                         on_progress=None) -> str:
        """One swarm worker as one engine session: a fresh child and conversation, one prompt, its text as the summary. The child
        is stopped afterwards (a worker is one task)."""
        from acp import text_block
        es = self.sessions.get(key) or EngineSession(key, Path(home))
        self.sessions[key] = es
        es.worker, es.tools, es.tool_router, es.provider, es.on_progress = True, list(tools), tool_router, provider, on_progress
        es.collector = []
        es.last_used = time.time()
        try:
            async with es.lock:
                await self._ensure_child(es)
            resp = await es.conn.prompt(session_id=es.acp_session_id, prompt=[text_block(prompt_text)])
            stop = str(getattr(resp, "stop_reason", "") or "")
            if stop == "cancelled":
                raise RuntimeError("the worker's engine turn was cancelled")
            return "".join(es.collector).strip()
        except asyncio.CancelledError:
            if es.conn is not None:
                try:
                    await es.conn.cancel(session_id=es.acp_session_id)
                except Exception:  # noqa: BLE001
                    pass
            raise
        finally:
            await self.stop(key)
            self.sessions.pop(key, None)

    # ------------------------------------------------------------------ tools (E1.6)
    def tool_specs(self, session_id: Optional[str] = None) -> list:
        from .. import capabilities as CAP
        from ..agent.swarm import SWARM_SPECS
        from ..agent.tools import TOOLS
        es = self.sessions.get(session_id or "")
        if es is not None and es.tools is not None:                 # a worker: only its job's tools, as Capabilities allow
            return [t for t in es.tools if CAP.tool_offered(t.name)]
        return [t for t in list(TOOLS) + list(SWARM_SPECS) if CAP.tool_offered(t.name)]

    async def call_tool(self, session_id: str, name: str, arguments: dict) -> tuple:
        from ..agent.providers.base import ToolCall
        from ..agent.tools import ASK_USER
        from ..agent.turns import clip_result
        es = self.sessions.get(session_id)
        if es is not None and es.tool_router is not None:           # a worker: its job's door to its own headless Lampway
            if name not in {t.name for t in self.tool_specs(session_id)}:
                return f"refused: {name} is not one of this worker's tools", True
            content, is_error = await es.tool_router(name, arguments if isinstance(arguments, dict) else {})
            return clip_result(content), is_error
        sink = es.sink if es is not None else None
        if sink is None:
            return "no turn is running for this session", True
        call = ToolCall(id=f"eng_{uuid.uuid4().hex[:12]}", name=name, arguments=arguments if isinstance(arguments, dict) else {})
        if name == ASK_USER:
            return await self._ask(es, sink, call), False
        content, is_error = await self.hub._run_tool(sink.socket, sink.session, sink.turn, call, sink.stream, sink.bubble_id, sink.steps)
        return clip_result(content), is_error

    async def _ask(self, es: EngineSession, sink: Sink, call) -> str:
        """The question goes to the island exactly as the built-in loop asks it; the call waits for the user's answer."""
        es.question = asyncio.get_running_loop().create_future()
        await self.hub._ask(sink.session, sink.turn, sink.stream, sink.bubble_id, "".join(sink.text).strip(), call)
        sink.text.clear()
        es.asked.set()
        try:
            return await es.question
        finally:
            es.question = None
