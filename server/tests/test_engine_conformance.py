# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Engine conformance (docs/reports/agent-modes-spec.md E1.7, E1.8): the REAL pinned Hermes engine in Mode 1's seat, driven by the
real server over a real socket, the way the Lampway client drives it.

The model is a scripted fake on loopback (no provider, no spend); every proxy variable of the engine points at a refusing loopback
proxy, so nothing leaves the machine and every attempt is recorded. The engine reaches Lampway's tools only through the session's
MCP endpoint, as ``mcp__lampway__<tool>``; a tool call that needs Blender arrives at the fake client as ``blender.execute_script``.

These tests need a built engine (``scripts/lampway/engine_env.py``; ``LAMPWAY_ENGINES_DIR`` or ``build/engines`` in the
repository) and the ACP SDK. Without them they SKIP, and a skip is not a pass. Each starts one engine child (~20 s cold)."""

import asyncio
import json
import os
import socket
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
import uvicorn
import websockets

from lampway_server.app import create_app
from lampway_server.engine.runtime import EngineRuntime, find_engine

from .fake_client import FakeMixarClient

ENGINES = Path(os.environ.get("LAMPWAY_ENGINES_DIR") or Path(__file__).resolve().parents[2] / "build" / "engines")
ENGINE = find_engine(ENGINES)
try:
    import acp  # noqa: F401
    HAVE_ACP = True
except ImportError:
    HAVE_ACP = False

pytestmark = [pytest.mark.skipif(ENGINE is None, reason=f"no built engine under {ENGINES}: run scripts/lampway/engine_env.py"),
              pytest.mark.skipif(not HAVE_ACP, reason="the ACP SDK (agent-client-protocol) is not installed"),
              pytest.mark.timeout(300)]


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class FakeModel:
    """An OpenAI-compatible model on loopback. ``plan`` is a list of steps for the streamed turn calls: ``("call", tool, args)``
    calls a Lampway tool through Hermes's ``tool_call`` bridge (or directly when the tool is visible); ``("say", text)`` answers.
    Auxiliary non-streamed calls (titles) get a short text and do not consume the plan."""

    def __init__(self, plan):
        self.plan = list(plan)
        self.seen = []
        self.tool_results = []
        model = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                data = body if isinstance(body, bytes) else json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path.rstrip("/").endswith("/models"):
                    return self._send(200, {"object": "list", "data": [{"id": "lampway", "object": "model", "context_length": 131072}]})
                self._send(404, {})

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                model.seen.append({"auth": self.headers.get("Authorization"), "stream": body.get("stream"),
                                   "tools": [t.get("function", {}).get("name") for t in body.get("tools") or []],
                                   "text": json.dumps(body.get("messages") or [])})
                msgs = body.get("messages") or []
                if msgs and msgs[-1].get("role") == "tool":
                    model.tool_results.append(str(msgs[-1].get("content")))
                if not body.get("stream"):
                    return self._send(200, {"id": "x", "object": "chat.completion", "created": 1, "model": "lampway",
                                            "choices": [{"index": 0, "message": {"role": "assistant", "content": "Title"},
                                                         "finish_reason": "stop"}]})
                step = model.plan.pop(0) if model.plan else ("say", "(no more steps)")
                if step[0] == "hold":                                      # ("hold", event, step): answer only once the test says
                    step[1].wait(120)
                    step = step[2]
                if step[0] == "native":                                    # one of Hermes's own tools, called directly
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"call_{len(model.seen)}", "type": "function",
                                                                  "function": {"name": step[1], "arguments": json.dumps(step[2])}}]}
                    finish = "tool_calls"
                elif step[0] == "call":
                    names = model.seen[-1]["tools"]
                    full = "mcp__lampway__" + step[1]
                    name, args = (full, step[2]) if full in names else ("tool_call", {"calls": [{"name": full, "arguments": step[2]}]})
                    delta = {"role": "assistant", "tool_calls": [{"index": 0, "id": f"call_{len(model.seen)}", "type": "function",
                                                                  "function": {"name": name, "arguments": json.dumps(args)}}]}
                    finish = "tool_calls"
                else:
                    delta, finish = {"role": "assistant", "content": step[1]}, "stop"
                chunks = [{"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "lampway",
                           "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
                          {"id": "c", "object": "chat.completion.chunk", "created": 1, "model": "lampway",
                           "choices": [{"index": 0, "delta": {}, "finish_reason": finish}]}]
                self._send(200, b"".join(b"data: " + json.dumps(c).encode() + b"\n\n" for c in chunks) + b"data: [DONE]\n\n",
                           "text/event-stream")

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/v1"


class RefusingProxy:
    def __init__(self):
        self.denied = []
        proxy = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _deny(self):
                proxy.denied.append(self.path)
                self.send_response(403)
                self.send_header("Content-Length", "0")
                self.end_headers()

            do_CONNECT = do_GET = do_POST = do_HEAD = _deny

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"


@pytest.fixture
def stack(settings, provider, tmp_path):
    settings.port = free_port()
    app = create_app(settings, provider=provider)
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=settings.port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        assert time.monotonic() < deadline, "uvicorn did not start"
        time.sleep(0.05)
    base = f"http://127.0.0.1:{settings.port}"
    proxy = RefusingProxy()
    project = tmp_path / "project"
    project.mkdir()

    def attach(model: FakeModel):
        app.state.agent.engine = EngineRuntime(
            app.state.agent, engine=ENGINE, state_dir=settings.state_dir, gateway_url=model.url,
            model_token_for=lambda sid: "engine-model-token", model_id="lampway",
            mcp_url_for=lambda sid: f"{base}/engine/mcp/{sid}", proxy_url=proxy.url, project_root=str(project),
            supports_vision=True)                                     # the scripted model "sees" (R3)
        return app.state.agent.engine

    yield {"app": app, "base": base, "settings": settings, "proxy": proxy, "attach": attach}
    server.should_exit = True
    thread.join(timeout=15)


def _login(base, settings):
    with httpx.Client(base_url=base) as http:
        fake = FakeMixarClient(http, password=settings.user_password)
        fake.login()
    return fake


async def _turn(ws, method, payload, on_script, timeout=120):
    command_id = str(uuid.uuid4())
    await ws.send(json.dumps({"jsonrpc": "2.0", "id": f"r_{command_id[:6]}", "method": method,
                              "params": {"command_id": command_id, "payload": payload}}))
    frames = []
    deadline = time.monotonic() + timeout
    while True:
        frame = json.loads(await asyncio.wait_for(ws.recv(), max(1, deadline - time.monotonic())))
        frames.append(frame)
        if frame.get("method") == "blender.execute_script" and frame.get("id"):
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": frame["id"], "result": on_script(frame["params"])}))
        if frame.get("method") == "agent.turn.ended" and frame["params"].get("turn_id") == command_id:
            return [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"], frames


def _run(stack, script):
    fake = _login(stack["base"], stack["settings"])
    ws_url = stack["base"].replace("http://", "ws://") + f"/api/agent/ws/{fake.instance_id}"

    async def go():
        headers = {"Authorization": f"Bearer {fake.access_token}", "x-telemetry-consent": "1", "X-Mixar-Locale": "en_US"}
        async with websockets.connect(ws_url, additional_headers=headers, open_timeout=10, max_size=None) as ws:
            hs = fake.handshake_frame()
            await ws.send(json.dumps(hs))
            json.loads(await asyncio.wait_for(ws.recv(), 10))
            try:
                return await script(ws, fake)
            finally:
                engine = stack["app"].state.agent.engine
                if engine is not None:
                    engine.kill_all()

    return asyncio.run(go())


SCENE = {"success": True, "scene": "Scene", "object_count": 1, "objects": [{"name": "Cube", "type": "MESH"}]}


def test_a_tool_turn_runs_lampways_tool_through_the_engine(stack):
    model = FakeModel([("call", "scene_summary", {}), ("say", "There is one cube.")])
    stack["attach"](model)
    scripts = []

    async def script(ws, fake):
        sid = str(uuid.uuid4())
        return await _turn(ws, "agent.chat", fake.chat_payload("What is in my scene?", sid),
                           lambda p: (scripts.append(p["script"]), SCENE)[1])

    events, _ = _run(stack, script)
    assert scripts, "the engine's tool call never reached Blender"
    final = [e for e in events if (e.get("content") or {}).get("set")]
    assert final and final[-1]["content"]["set"] == "There is one cube."
    steps = [e for e in events if e.get("steps")]
    assert steps and any(s["label"] == "scene_summary" and s["status"] == "done" for s in steps[-1]["steps"]["items"])
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "completed"
    assert model.tool_results and "Cube" in model.tool_results[0]
    turn_calls = [s for s in model.seen if s["stream"]]
    assert all(s["auth"] == "Bearer engine-model-token" for s in turn_calls), "the engine holds no key of its own"
    for host in stack["proxy"].denied:                                   # nothing left the machine; record what was tried
        assert not host.startswith("127.0.0.1")


def test_a_question_is_asked_in_the_island_and_the_answer_continues_the_same_prompt(stack):
    model = FakeModel([("call", "ask_user", {"question": "Round or square table?", "options": ["Round", "Square"]}),
                       ("say", "Round it is.")])
    stack["attach"](model)

    async def script(ws, fake):
        sid = str(uuid.uuid4())
        first, _ = await _turn(ws, "agent.chat", fake.chat_payload("Make a table", sid), lambda p: SCENE)
        asked = [e for e in first if e.get("interrupt_id")]
        assert asked, first
        q = asked[-1]
        second, _ = await _turn(ws, "agent.input", {"session_id": sid, "action": "respond", "text": "Round", "answers": ["Round"],
                                                    "interrupt_id": q["interrupt_id"]}, lambda p: SCENE)
        return first, q, second

    first, q, second = _run(stack, script)
    assert [a["value"] for a in q["actions"]] == ["Round", "Square"] and "Round or square table?" in q["content"]["set"]
    assert first[-1]["type"] == "turn_end"
    final = [e for e in second if (e.get("content") or {}).get("set")]
    assert final and final[-1]["content"]["set"] == "Round it is."
    assert model.tool_results and "Round" in model.tool_results[-1]


def test_a_message_during_the_engines_turn_joins_it(stack):
    """R4: the second message steers the running turn (Hermes /steer); the client's command is answered ok, no turn is cancelled."""
    model = FakeModel([("call", "run_blender_python", {"script": "import bpy"}), ("say", "Red it is.")])
    stack["attach"](model)

    async def script(ws, fake):
        sid = str(uuid.uuid4())
        command_id = str(uuid.uuid4())
        await ws.send(json.dumps({"jsonrpc": "2.0", "id": "r1", "method": "agent.chat",
                                  "params": {"command_id": command_id, "payload": fake.chat_payload("Make a chair", sid)}}))
        frames, joined, steer_reply = [], None, None
        deadline = time.monotonic() + 120
        while True:
            frame = json.loads(await asyncio.wait_for(ws.recv(), max(1, deadline - time.monotonic())))
            frames.append(frame)
            if frame.get("method") == "blender.execute_script" and frame.get("id"):
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": "r2", "method": "agent.chat", "params": {
                    "command_id": str(uuid.uuid4()), "payload": fake.chat_payload("Actually make it red", sid)}}))
                while steer_reply is None:
                    f2 = json.loads(await asyncio.wait_for(ws.recv(), 30))
                    frames.append(f2)
                    if f2.get("id") == "r2":
                        steer_reply = f2
                await ws.send(json.dumps({"jsonrpc": "2.0", "id": frame["id"], "result": SCENE}))
            if frame.get("method") == "agent.turn.ended" and frame["params"].get("turn_id") == command_id:
                return frames, steer_reply

    frames, steer_reply = _run(stack, script)
    assert steer_reply["result"] == {"state": "complete", "result": {"ok": True, "joined": True}}
    events = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "completed", "the turn was not cancelled"
    final = [e for e in events if (e.get("content") or {}).get("set")]
    assert final and final[-1]["content"]["set"] == "Red it is.", "the steer acknowledgement is not the agent's words"
    later = [s for s in model.seen if s["stream"]][1:]
    assert later and any("Actually make it red" in s["text"] for s in later), "the model saw the steer in the same turn"


def test_a_permission_request_is_the_users_choice_in_the_island(stack, tmp_path):
    """R4/E2: Hermes asks before a file edit; the island shows its own options; Allow lets the write happen."""
    model = FakeModel([("native", "write_file", {"path": "note.txt", "content": "hello"}), ("say", "Wrote the note.")])
    stack["attach"](model)

    async def script(ws, fake):
        sid = str(uuid.uuid4())
        first, _ = await _turn(ws, "agent.chat", fake.chat_payload("Write a note", sid), lambda p: SCENE)
        asked = [e for e in first if e.get("interrupt_id")]
        assert asked, first
        q = asked[-1]
        allow = next(a["value"] for a in q["actions"] if "allow" in a["value"].lower())
        second, _ = await _turn(ws, "agent.input", {"session_id": sid, "action": "respond", "text": allow, "answers": [allow],
                                                    "interrupt_id": q["interrupt_id"]}, lambda p: SCENE)
        return q, second

    q, second = _run(stack, script)
    assert q["content"]["set"].startswith("Allow the agent to") and len(q["actions"]) >= 2
    final = [e for e in second if (e.get("content") or {}).get("set")]
    assert final and final[-1]["content"]["set"] == "Wrote the note."
    project = tmp_path / "project"
    assert (project / "note.txt").read_text() == "hello", "the allowed write happened in the project"


def test_rules_folders_and_an_image_reach_the_engines_model(stack):
    """R3: the client's rules snapshot, context folders and attached image reach the model through the engine."""
    model = FakeModel([("say", "Noted.")])
    stack["attach"](model)
    png = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="

    async def script(ws, fake):
        sid = str(uuid.uuid4())
        payload = fake.chat_payload("Model the chair.", sid)
        payload["rules"] = {"version": 1, "global": [{"id": "g", "text": "Always use metric units.", "enabled": True}], "project": []}
        payload["folder_context"] = {"version": 1, "folders": [{"name": "refs", "available": True, "file_count": 1,
                                                                 "kinds": {"image": 1}, "files": ["front.png"]}]}
        payload["content"] = [{"type": "text", "text": "Model the chair."},
                              {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{png}"}}]
        return await _turn(ws, "agent.chat", payload, lambda p: SCENE)

    events, _ = _run(stack, script)
    assert events[-1]["type"] == "turn_end"
    sent = [s for s in model.seen if s["stream"]][0]["text"]
    assert "Always use metric units." in sent and "refs: 1 files" in sent and "front.png" in sent
    assert png[:24] in sent, "the attached image reached the model"


def test_the_engines_turn_survives_the_client_and_ends_on_its_new_socket(stack):
    """E1.7/R5 (captain: Mode 1 durability is the engine's): closing the client's socket does not cancel the engine's turn. The
    Blender call in flight fails and the model is told; the client re-attaches on a new socket, replays what it missed, and the
    turn's next Blender call and its end arrive there."""
    gate = threading.Event()
    model = FakeModel([("call", "run_blender_python", {"script": "import bpy"}),
                       ("hold", gate, ("call", "scene_summary", {})), ("say", "Done after the reconnect.")])
    stack["attach"](model)
    hub = stack["app"].state.agent
    fake = _login(stack["base"], stack["settings"])
    ws_url = stack["base"].replace("http://", "ws://") + f"/api/agent/ws/{fake.instance_id}"
    headers = {"Authorization": f"Bearer {fake.access_token}", "x-telemetry-consent": "1", "X-Mixar-Locale": "en_US"}
    sid, command_id = str(uuid.uuid4()), str(uuid.uuid4())

    async def connect():
        ws = await websockets.connect(ws_url, additional_headers=headers, open_timeout=10, max_size=None)
        await ws.send(json.dumps(fake.handshake_frame()))
        json.loads(await asyncio.wait_for(ws.recv(), 10))
        return ws

    async def go():
        try:
            ws = await connect()
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": "r1", "method": "agent.chat",
                                      "params": {"command_id": command_id, "payload": fake.chat_payload("Make a chair", sid)}}))
            last_seq = -1
            while True:
                frame = json.loads(await asyncio.wait_for(ws.recv(), 120))
                if frame.get("method") == "agent.turn.event":
                    last_seq = frame["params"]["seq"]
                if frame.get("method") == "blender.execute_script" and frame.get("id"):
                    break                                                # the client goes away with Blender's call unanswered
            await ws.close()
            deadline = time.monotonic() + 30
            while not getattr(hub.sessions[sid].current, "detached", False):
                assert hub.sessions[sid].current is not None, "the turn ended when the client's socket closed"
                assert time.monotonic() < deadline, "the server never noticed the client left"
                await asyncio.sleep(0.05)
            ws = await connect()
            await ws.send(json.dumps({"jsonrpc": "2.0", "id": "a1", "method": "agent.attach",
                                      "params": {"session_id": sid, "turn_id": command_id, "after_seq": last_seq}}))
            frames, scripts = [], []
            deadline = time.monotonic() + 120
            while True:
                frame = json.loads(await asyncio.wait_for(ws.recv(), max(1, deadline - time.monotonic())))
                frames.append(frame)
                if frame.get("id") == "a1":
                    gate.set()                                           # attached: now let the engine's model go on
                if frame.get("method") == "blender.execute_script" and frame.get("id"):
                    scripts.append(frame["params"]["script"])
                    await ws.send(json.dumps({"jsonrpc": "2.0", "id": frame["id"], "result": SCENE}))
                if frame.get("method") == "agent.turn.ended" and frame["params"].get("turn_id") == command_id:
                    await ws.close()
                    return frames, scripts, last_seq
        finally:
            gate.set()
            if hub.engine is not None:
                hub.engine.kill_all()

    frames, scripts, last_seq = asyncio.run(go())
    attach = next(f for f in frames if f.get("id") == "a1")
    assert attach["result"]["status"] == "ok"
    seqs = [f["params"]["seq"] for f in frames if f.get("method") == "agent.turn.event"]
    assert seqs == list(range(last_seq + 1, last_seq + 1 + len(seqs))), "the new socket got every missed event, once, in order"
    events = [f["params"]["event"] for f in frames if f.get("method") == "agent.turn.event"]
    assert scripts, "the turn's next Blender call went to the client's new socket"
    final = [e for e in events if (e.get("content") or {}).get("set")]
    assert final and final[-1]["content"]["set"] == "Done after the reconnect."
    assert events[-1]["type"] == "turn_end" and events[-1]["status"] == "completed", "the turn was not cancelled"
    assert model.tool_results and len(model.tool_results) >= 2, "the model was told about the lost call and saw the next result"
