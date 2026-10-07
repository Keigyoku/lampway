# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Test support for Mode 1 (docs/reports/agent-modes-spec.md A2): a scripted ``hermes serve`` peer, the real server on a real port,
and an island client that speaks the Lampway client's frames.

``FakeServe`` speaks the contract measured on the pinned build (2026-10-07), in the test's own event loop: ``gateway.ready`` first;
``client.capabilities``; ``session.create`` / ``session.resume`` (by stored id, attaching additively; fan-out to every attached
client); ``prompt.submit`` -> ``{status: streaming}``, then the turn's events ``{method: event, params: {type, session_id, payload,
seq}}`` with a per-session seq, ``message.start`` without a payload, ``message.complete {text, status}``; ``image.attach_bytes``;
``session.steer``; ``session.interrupt`` -> the running turn completes ``interrupted``; ``session.history`` (``{role, text, row_id}``);
``session.events.since`` from a bounded ring (``truncated`` past it); ``session.status`` / ``session.active_list``; server requests
``clarify`` and ``approval`` to EVERY attached client that asked for them, first answer wins, no ``request.cancel`` to the others;
``/new`` from another client closes the session for everyone (``sessions.changed``, then ``4001``).

A turn is a script of steps: ``("say", text)`` streams deltas; ``("reason", text)``; ``("tool", name, args, result)``;
``("mcp", tool, args)`` calls Lampway's MCP endpoint over HTTP like Hermes does (``mcp__lampway__<tool>`` in the events);
``("clarify", question, choices)``; ``("approval", command)``; ``("gate", asyncio.Event)`` waits for the test; ``("until_interrupt",)``;
``("end", status)`` ends with that status (default ``complete``, the text said so far).
"""

import asyncio
import collections
import itertools
import json
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import uvicorn
import websockets

from lampway_server.engine.units import UnitInfo

RING = 512


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@dataclass
class FSession:
    live_id: str
    stored_id: str
    cwd: str
    started_at: float = field(default_factory=time.time)
    history: list = field(default_factory=list)
    ring: collections.deque = field(default_factory=lambda: collections.deque(maxlen=RING))
    seq: int = 0
    clients: set = field(default_factory=set)
    task: object = None
    interrupted: object = None
    closed: bool = False
    steers: list = field(default_factory=list)
    images: list = field(default_factory=list)
    answers: list = field(default_factory=list)


class FakeServe:
    def __init__(self, token="serve-token"):
        self.token = token
        self.sessions: dict = {}
        self.clients: set = set()
        self.wants_requests: set = set()
        self.calls: list = []                    # (method, params) every client sent
        self.scripts: collections.deque = collections.deque()
        self.epoch = uuid.uuid4().hex
        self.rows = itertools.count(1)
        self.mcp = None                          # (url, bearer) of Lampway's endpoint for this unit
        self.mcp_results: list = []
        self.mcp_post = None                     # (url, body, headers) -> reply, when Lampway runs under a TestClient (ServeThread)
        self._srq: dict = {}
        self.port = None
        self.server = None

    # ------------------------------------------------------------------ lifecycle
    async def start(self, port=0):
        self.server = await websockets.serve(self._handler, "127.0.0.1", port, max_size=None)
        self.port = self.server.sockets[0].getsockname()[1]
        return self

    async def stop(self):
        for ws in list(self.clients):
            await ws.close()
        self.server.close()
        await self.server.wait_closed()

    async def restart(self):
        """serve killed and started again on the same port: the live ids and the replay epoch change; history survives."""
        port = self.port
        await self.stop()
        for s in self.sessions.values():
            if s.task is not None:
                s.task.cancel()
            s.clients.clear()
        self.epoch = uuid.uuid4().hex
        self.sessions = {uuid.uuid4().hex[:8]: s for s in self.sessions.values()}
        for live, s in self.sessions.items():
            s.live_id, s.seq, s.ring = live, 0, collections.deque(maxlen=RING)
        await self.start(port)

    # ------------------------------------------------------------------ sessions
    def create(self, cwd="/project") -> FSession:
        s = FSession(uuid.uuid4().hex[:8], time.strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:6], cwd)
        self.sessions[s.live_id] = s
        return s

    def by_stored(self, stored) -> FSession:
        return next((s for s in self.sessions.values() if s.stored_id == stored and not s.closed), None)

    def only(self) -> FSession:
        live = [s for s in self.sessions.values() if not s.closed]
        assert len(live) == 1, live
        return live[0]

    async def event(self, s: FSession, kind: str, payload=None):
        s.seq += 1
        params = {"type": kind, "session_id": s.live_id, "seq": s.seq}
        if payload is not None:
            params["payload"] = payload
        s.ring.append(params)
        await self._fan(s.clients, {"jsonrpc": "2.0", "method": "event", "params": params})

    async def _fan(self, clients, frame):
        for ws in list(clients):
            try:
                await ws.send(json.dumps(frame))
            except Exception:  # noqa: BLE001 - a client that left
                pass

    async def ask(self, s: FSession, method: str, params: dict):
        rid = f"srq-{uuid.uuid4().hex[:12]}"
        fut = asyncio.get_running_loop().create_future()
        self._srq[rid] = fut
        targets = {ws for ws in s.clients if ws in self.wants_requests}
        await self._fan(targets, {"jsonrpc": "2.0", "id": rid, "method": method, "params": {"session_id": s.live_id, **params}})
        return await fut

    # ------------------------------------------------------------------ turns
    async def run_turn(self, s: FSession, steps):
        text = []
        status = "complete"
        s.interrupted = asyncio.Event()
        await self.event(s, "message.start")
        try:
            for step in steps:
                op = step[0]
                if s.interrupted.is_set():
                    status = "interrupted"
                    break
                if op == "say":
                    for word in step[1].split(" "):
                        piece = (" " if text else "") + word
                        text.append(piece)
                        await self.event(s, "message.delta", {"text": piece})
                elif op == "reason":
                    await self.event(s, "reasoning.delta", {"text": step[1]})
                elif op == "tool":
                    tid = f"call_{uuid.uuid4().hex[:8]}"
                    await self.event(s, "tool.start", {"tool_id": tid, "name": step[1], "args": step[2]})
                    await self.event(s, "tool.complete", {"tool_id": tid, "name": step[1], "args": step[2], "result": step[3],
                                                          "duration_s": 0.01})
                elif op == "mcp":
                    tid = f"call_{uuid.uuid4().hex[:8]}"
                    name = f"mcp__lampway__{step[1]}"
                    await self.event(s, "tool.start", {"tool_id": tid, "name": name, "args": step[2]})
                    result = await self.call_mcp(step[1], step[2])
                    self.mcp_results.append(result)
                    await self.event(s, "tool.complete", {"tool_id": tid, "name": name, "args": step[2],
                                                          "result": {"result": result["content"][0]["text"]} if not result["isError"]
                                                          else {"error": result["content"][0]["text"]}, "duration_s": 0.1})
                elif op == "clarify":
                    tid = f"call_{uuid.uuid4().hex[:8]}"
                    await self.event(s, "tool.start", {"tool_id": tid, "name": "clarify", "args": {"question": step[1]}})
                    answer = await self.ask(s, "clarify", {"question": step[1], "choices": list(step[2])})
                    s.answers.append(("clarify", answer))
                    await self.event(s, "tool.complete", {"tool_id": tid, "name": "clarify", "result": answer})
                elif op == "approval":
                    tid = f"call_{uuid.uuid4().hex[:8]}"
                    await self.event(s, "tool.start", {"tool_id": tid, "name": "terminal", "args": {"command": step[1]}})
                    choice = await self.ask(s, "approval", {"command": step[1], "description": "delete in root path",
                                                            "request_id": uuid.uuid4().hex, "choices": ["once", "session", "always", "deny"]})
                    s.answers.append(("approval", choice))
                    ok = choice.get("choice") in ("once", "session", "always")
                    await self.event(s, "tool.complete", {"tool_id": tid, "name": "terminal",
                                                          "result": {"output": "ran"} if ok else {"error": "denied by the user"}})
                elif op == "gate":
                    await step[1].wait()
                elif op == "until_interrupt":
                    await s.interrupted.wait()
                    status = "interrupted"
                    break
                elif op == "end":
                    status = step[1]
                    break
        except asyncio.CancelledError:
            return
        reply = "".join(text)
        if status == "complete" and reply:
            s.history.append({"role": "assistant", "text": reply, "row_id": next(self.rows)})
        await self.event(s, "message.complete", {"text": reply, "status": status, "usage": {}})
        s.task = None

    async def pane_prompt(self, s: FSession, text: str, steps):
        """A turn the user types in the pane (the TUI, another client): no event carries its text (measured)."""
        s.history.append({"role": "user", "text": text, "row_id": next(self.rows)})
        s.task = asyncio.ensure_future(self.run_turn(s, steps))
        return s.task

    async def pane_new(self, s: FSession) -> FSession:
        """``/new`` confirmed in the pane: the TUI closes the shared session and makes another."""
        s.closed = True
        await self._fan(self.clients, {"jsonrpc": "2.0", "method": "event", "params": {"type": "sessions.changed", "session_id": "", "payload": {}}})
        new = self.create(s.cwd)
        await self._fan(self.clients, {"jsonrpc": "2.0", "method": "event", "params": {"type": "sessions.changed", "session_id": "", "payload": {}}})
        return new

    async def call_mcp(self, tool, args):
        url, bearer = self.mcp
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}}
        if self.mcp_post is not None:
            return (await asyncio.to_thread(self.mcp_post, url, body, {"Authorization": f"Bearer {bearer}"}))["result"]
        async with httpx.AsyncClient(timeout=120) as http:
            r = await http.post(url, json={"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": tool, "arguments": args}},
                                headers={"Authorization": f"Bearer {bearer}"})
        return r.json()["result"]

    # ------------------------------------------------------------------ the socket
    async def _handler(self, ws):
        query = parse_qs(urlparse(ws.request.path).query)
        if query.get("token") != [self.token]:
            await ws.close(4401, "bad token")
            return
        self.clients.add(ws)
        try:
            await ws.send(json.dumps({"jsonrpc": "2.0", "method": "event", "params": {"type": "gateway.ready",
                                                                                    "payload": {"replay_epoch": self.epoch}}}))
            async for raw in ws:
                frame = json.loads(raw)
                if "method" not in frame:
                    fut = self._srq.get(frame.get("id"))
                    if fut is not None and not fut.done():           # the first answer wins; later ones are ignored
                        fut.set_result(frame.get("result") or {})
                    continue
                self.calls.append((frame["method"], frame.get("params") or {}))
                try:
                    result = await self._method(ws, frame["method"], frame.get("params") or {})
                    out = {"jsonrpc": "2.0", "id": frame["id"], "result": result}
                except LookupError:
                    out = {"jsonrpc": "2.0", "id": frame["id"], "error": {"code": 4001, "message": "session not found"}}
                except NotImplementedError:
                    out = {"jsonrpc": "2.0", "id": frame["id"], "error": {"code": -32601, "message": "method not found"}}
                await ws.send(json.dumps(out))
        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(ws)
            self.wants_requests.discard(ws)
            for s in self.sessions.values():
                s.clients.discard(ws)

    def _live(self, params) -> FSession:
        s = self.sessions.get(params.get("session_id"))
        if s is None or s.closed:
            raise LookupError
        return s

    async def _method(self, ws, method, params):
        if method == "client.capabilities":
            if params.get("server_requests"):
                self.wants_requests.add(ws)
            return {"server_requests": ["approval", "clarify"]}
        if method == "session.create":
            s = self.create(params.get("cwd") or "/project")
            s.clients.add(ws)
            asyncio.get_running_loop().call_soon(lambda: asyncio.ensure_future(self.event(s, "session.info", {"tools": {}})))
            return {"session_id": s.live_id, "stored_session_id": s.stored_id, "message_count": 0, "messages": []}
        if method == "session.resume":
            s = self.by_stored(params.get("session_id"))
            if s is None:
                raise LookupError
            s.clients.add(ws)
            running = s.task is not None and not s.task.done()
            users = [m for m in s.history if m["role"] == "user"]
            return {"session_id": s.live_id, "session_key": s.stored_id, "resumed": s.stored_id, "running": running,
                    "status": "working" if running else "idle", "messages": list(s.history), "message_count": len(s.history),
                    "inflight": {"user": users[-1]["text"], "assistant": "", "streaming": True} if running and users else None}
        if method == "prompt.submit":
            s = self._live(params)
            row = next(self.rows)
            s.history.append({"role": "user", "text": params["text"], "row_id": row})
            steps = self.scripts.popleft() if self.scripts else [("say", "(no script)")]
            s.task = asyncio.ensure_future(self.run_turn(s, steps))
            return {"status": "streaming", "user_row_id": row}
        if method == "image.attach_bytes":
            s = self._live(params)
            s.images.append((params.get("filename"), params.get("content_base64")))
            return {"attached": True, "name": params.get("filename"), "count": len(s.images)}
        if method == "session.steer":
            s = self._live(params)
            s.steers.append(params.get("text"))
            return {"status": "queued", "text": params.get("text")}
        if method == "session.interrupt":
            s = self._live(params)
            if s.interrupted is not None:
                s.interrupted.set()
            return {"status": "interrupted"}
        if method == "session.history":
            s = self._live(params)
            return {"count": len(s.history), "messages": list(s.history)}
        if method == "session.events.since":
            s = self._live(params)
            last = int(params.get("last_seen", -1))
            first = s.ring[0]["seq"] if s.ring else s.seq + 1
            if last + 1 < first and s.ring:
                return {"truncated": True, "events": [], "latest_seq": s.seq, "epoch": self.epoch}
            events = [e for e in s.ring if e["seq"] > last]
            return {"events": events, "latest_seq": s.seq, "truncated": False, "count": len(events), "epoch": self.epoch}
        if method == "session.status":
            s = self._live(params)
            return {"output": f"Session ID: {s.stored_id}"}
        if method == "session.active_list":
            return {"sessions": [{"id": s.live_id, "session_key": s.stored_id, "started_at": s.started_at,
                                  "status": "working" if s.task is not None else "idle"} for s in self.sessions.values() if not s.closed]}
        raise NotImplementedError


class FakeUnits:
    """``Mode1Units`` played: the unit's pane is the FakeServe (its wrapper and serve already up), opened on the user's chat."""

    def __init__(self, serve: FakeServe, loop, base: str, cockpit=None):
        self.serve, self.loop, self.base = serve, loop, base
        self.cockpit = cockpit or type("C", (), {"root": "/nonexistent"})()
        self.opened: list = []
        self.infos: dict = {}
        self.bearer = "unit-bearer"
        self.dead: set = set()

    def missing(self):
        return None

    def known(self, unit):
        return None if unit in self.dead else self.infos.get(unit)

    def alive(self, info):
        return info.unit not in self.dead

    async def open(self, unit, label=None):
        async def make():
            return self.serve.create("/project")
        s = await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(make(), self.loop))
        info = UnitInfo(unit, f"rec-{len(self.opened) + 1}", None, self.serve.port, self.serve.token, s.stored_id)
        self.infos[unit] = info
        self.dead.discard(unit)
        self.opened.append(unit)
        self.serve.mcp = (f"{self.base}/engine/mcp/{unit}", self.bearer)
        return info

    def record_session(self, info, stored):
        self.infos[info.unit] = info

    def check_mcp(self, unit, token):
        return token == self.bearer and unit in self.infos


class Stack:
    """The real server (create_app) on a real loopback port, in a thread; a scripted serve and an island in the test's loop."""

    def __init__(self, app, settings):
        self.app, self.settings = app, settings
        self.base = f"http://127.0.0.1:{settings.port}"
        self.server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=settings.port, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            assert time.monotonic() < deadline, "uvicorn did not start"
            time.sleep(0.05)
        return self

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(timeout=15)


class Island:
    """The Lampway client's agent socket, as frames: commands, the turn events, and Blender's script calls answered by ``on_script``."""

    def __init__(self, base, settings, on_script=None):
        from .fake_client import FakeMixarClient
        self.base, self.settings = base, settings
        with httpx.Client(base_url=base) as http:
            self.fake = FakeMixarClient(http, password=settings.user_password)
            self.fake.login()
        self.on_script = on_script or (lambda params: {"success": True, "output": "ok"})
        self.frames: list = []
        self.scripts: list = []
        self.hold_scripts = False                # True: Blender's script calls are recorded in ``held`` and left unanswered
        self.held: list = []
        self.ws = None
        self.reader = None
        self.changed = asyncio.Event()

    async def connect(self):
        url = self.base.replace("http://", "ws://") + f"/api/agent/ws/{self.fake.instance_id}"
        headers = {"Authorization": f"Bearer {self.fake.access_token}", "x-telemetry-consent": "1", "X-Mixar-Locale": "en_US"}
        self.ws = await websockets.connect(url, additional_headers=headers, open_timeout=10, max_size=None)
        await self.ws.send(json.dumps(self.fake.handshake_frame()))
        json.loads(await asyncio.wait_for(self.ws.recv(), 10))
        self.reader = asyncio.ensure_future(self._read())
        return self

    async def close(self):
        await self.ws.close()
        if self.reader is not None:
            await asyncio.gather(self.reader, return_exceptions=True)

    async def _read(self):
        try:
            async for raw in self.ws:
                frame = json.loads(raw)
                self.frames.append(frame)
                if frame.get("method") == "blender.execute_script" and frame.get("id"):
                    self.scripts.append(frame["params"])
                    if self.hold_scripts:
                        self.held.append(frame["id"])
                        self.changed.set()
                        continue
                    await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": frame["id"], "result": self.on_script(frame["params"])}))
                self.changed.set()
        except websockets.ConnectionClosed:
            pass

    async def send(self, method, params):
        rid = f"r_{uuid.uuid4().hex[:8]}"
        await self.ws.send(json.dumps({"jsonrpc": "2.0", "id": rid, "method": method, "params": params}))
        return rid

    async def command(self, method, payload):
        command_id = str(uuid.uuid4())
        rid = await self.send(method, {"command_id": command_id, "payload": payload})
        return command_id, rid

    async def wait(self, pred, timeout=30):
        deadline = time.monotonic() + timeout
        while True:
            for f in self.frames:
                if pred(f):
                    return f
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise AssertionError(f"no such frame within {timeout}s; frames: {json.dumps(self.frames)[-3000:]}")
            self.changed.clear()
            try:
                await asyncio.wait_for(self.changed.wait(), min(remaining, 0.5))
            except asyncio.TimeoutError:
                pass

    async def reply(self, rid, timeout=30):
        return await self.wait(lambda f: f.get("id") == rid and ("result" in f or "error" in f), timeout)

    async def ended(self, turn_id, timeout=30):
        return await self.wait(lambda f: f.get("method") == "agent.turn.ended" and f["params"].get("turn_id") == turn_id, timeout)

    def events(self, turn_id):
        return [f["params"]["event"] for f in self.frames if f.get("method") == "agent.turn.event" and f["params"].get("turn_id") == turn_id]

    def started(self):
        return [f["params"] for f in self.frames if f.get("method") == "agent.turn.started"]

    def chat(self, message, session_id):
        return self.fake.chat_payload(message, session_id)


# ---------------------------------------------------------------------------------------------------- the island against a scripted serve
@pytest.fixture
def stack(settings, provider, monkeypatch):
    """The real server on a real loopback port, with a herdr server that reports running (no pane is started: ``FakeUnits``)."""
    from lampway_server.app import create_app
    from lampway_server.herdr import launcher as L
    settings.port = free_port()
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    monkeypatch.setattr(L, "bin_path", lambda: "/usr/bin/herdr-played")
    app = create_app(settings, provider=provider)
    with Stack(app, settings) as st:
        yield st


def run(stack, scenario, on_script=None):
    """``scenario(serve, units, island, front)`` against a scripted serve, the hub's real ``HermesFront`` and the Lampway client's
    frames; the unit's pane is ``FakeUnits``."""
    from lampway_server.engine.front import HermesFront

    async def go():
        serve = await FakeServe().start()
        units = FakeUnits(serve, asyncio.get_running_loop(), stack.base)
        front = HermesFront(stack.app.state.agent, units)
        stack.app.state.agent.engine = front
        island = await Island(stack.base, stack.settings, on_script=on_script or (lambda p: SCENE)).connect()
        try:
            return await scenario(serve, units, island, front)
        finally:
            for link in list(front.links.values()):
                link.closing = True
            await island.close()
            await serve.stop()
            stack.app.state.agent.engine = None
    return asyncio.run(go())


SCENE = {"success": True, "scene": "Scene", "object_count": 1, "objects": [{"name": "Cube", "type": "MESH"}]}


async def chat(island, text, sid, **extra):
    payload = {**island.chat(text, sid), **extra}
    cid, rid = await island.command("agent.chat", payload)
    return cid, rid


def final_text(events):
    sets = [e["content"]["set"] for e in events if (e.get("content") or {}).get("set")]
    return sets[-1] if sets else None


class ServeThread:
    """A ``FakeServe`` in an event loop of its own, for a test whose server runs under Starlette's ``TestClient`` (no real port):
    the island is the test's ``FakeMixarClient`` socket, and the pane's calls to Lampway's MCP endpoint go through the TestClient
    (``http``). ``front(agent)`` puts the hub's real ``HermesFront`` in the seat, its unit's pane played by ``FakeUnits``."""

    def __init__(self, http=None, base="http://127.0.0.1:8787"):
        self.http, self.base = http, base
        self.loop = asyncio.new_event_loop()
        self.thread = threading.Thread(target=self.loop.run_forever, daemon=True)
        self.serve = None
        self.fronts: list = []

    def __enter__(self):
        self.thread.start()
        self.serve = self.call(FakeServe().start())
        if self.http is not None:
            self.serve.mcp_post = self._post
        return self

    def call(self, coro, timeout=60):
        return asyncio.run_coroutine_threadsafe(coro, self.loop).result(timeout)

    def _post(self, url, body, headers):
        return self.http.post(urlparse(url).path, json=body, headers=headers).json()

    def front(self, agent) -> "FakeUnits":
        from lampway_server.engine.front import HermesFront
        units = FakeUnits(self.serve, self.loop, self.base)
        front = HermesFront(agent, units)
        agent.engine = front
        self.fronts.append((agent, front))
        return units

    def __exit__(self, *exc):
        for agent, front in self.fronts:
            for link in list(front.links.values()):
                link.closing = True
            if agent.engine is front:
                agent.engine = None
        try:
            self.call(self.serve.stop(), timeout=15)
        finally:
            self.loop.call_soon_threadsafe(self.loop.stop)
            self.thread.join(5)
            self.loop.close()


def mode1_turn(monkeypatch, http, fake, steps, message="Go", session_id=None, on_script=None, drive=None):
    """One Mode 1 turn under a TestClient, the pane's Hermes playing ``steps`` (FakeServe's script). The user's Client is ``fake``
    (logged in); ``drive(ws, command_id)`` replaces ``fake.run_turn`` (e.g. a swarm's fleet). Returns (frames, the serve)."""
    from lampway_server.herdr import launcher as L
    monkeypatch.setattr(L, "bin_path", lambda: "/usr/bin/herdr-played")
    monkeypatch.setattr(L, "server_status", lambda root: {"running": True})
    session_id = session_id or str(uuid.uuid4())
    with ServeThread(http) as st:
        st.front(http.app.state.agent)
        st.serve.scripts.append(list(steps))
        with fake.connect_ws() as ws:
            fake.handshake(ws)
            command_id = fake.command(ws, "chat", fake.chat_payload(message, session_id))
            if drive is not None:
                frames = drive(ws, command_id)
            else:
                frames = fake.run_turn(ws, command_id, on_script=on_script or (lambda p: fake.execute_script_result(p["script"])))
        return frames, st.serve
