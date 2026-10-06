"""codex_app_server (specs/mrmak/02): a model provider on the user's own Codex login with structured tool calls. One persistent ``codex app-server`` child (JSON-RPC over stdio lines) per
Lampway agent session; Lampway's tools are registered as the thread's DYNAMIC tools; each ``item/tool/call`` becomes an ordinary ``ToolCall`` event for Lampway's own loop, so journaling, the
viewport lock and the spend gate stay where they are. Codex keeps ONE turn open across tool calls while Lampway's loop calls ``stream()`` once per step, so the turn is inverted: the pending
JSON-RPC requests wait while ``stream()`` returns, and the next ``stream()`` answers them from the ``tool_result`` parts. Codex's shell, patching and sub-agents are off; the child gets the
server's environment minus every Lampway secret and provider key and an empty working folder of its own. The tool-registration field is EXPERIMENTAL: a startup probe names what is missing."""

import asyncio
import json
import os
import shutil
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Optional

from .base import Message, ModelRequest, Stop, Text, ToolCall

REQUIRED = ("initialize", "thread/start", "turn/start", "turn/interrupt", "item/tool/call", "item/agentMessage/delta", "item/completed", "turn/completed", "DynamicToolCallParams",
            "DynamicToolCallResponse")
EFFORTS = ("medium", "high", "xhigh")
DROP_EXACT = {"CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT", "CODEX_THREAD_ID", "CODEX_TURN_ID", "CODEX_SHELL", "OPENROUTER_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GITHUB_TOKEN", "GH_TOKEN"}
KEEP_PREFIX = "LAMPWAY_CLI_"
CLOSED = "Codex closed; Lampway sessions are unaffected"
UNSUPPORTED = "This coordinator only supports its registered workspace tools"
NO_TURN = "No active authorized request or unknown tool"


class CodexAppServerError(RuntimeError):
    pass


def child_env(env: dict) -> dict:
    """The server's environment minus host-agent identity, every Lampway secret and every provider key; LAMPWAY_CLI_* is the user's own forwarding door."""
    out = {}
    for k, v in env.items():
        if k.startswith(KEEP_PREFIX):
            out[k] = v
        elif k in DROP_EXACT or k.startswith("LAMPWAY_") or any(t in k.upper() for t in ("API_KEY", "SECRET", "TOKEN", "PASSWORD")):
            continue
        else:
            out[k] = v
    return out


def probe_schema(schema_dir: str, version: str = "unknown") -> dict:
    text = "\n".join(p.read_text(errors="replace") for p in Path(schema_dir).rglob("*.json"))
    missing = [n for n in REQUIRED if n not in text]
    if missing:
        raise CodexAppServerError(f"this Codex ({version}) does not expose {', '.join(missing)} in app-server: update Codex, or use LAMPWAY_PROVIDER=codex_cli")
    if "dynamicTools" not in text:
        raise CodexAppServerError(f"this Codex ({version}) does not expose dynamic tools in app-server: update Codex, or use LAMPWAY_PROVIDER=codex_cli")
    return {"dynamic_tools": True, "version": version}


def probe_binary(binary: str, out_dir: str) -> dict:
    """Run ``codex app-server generate-json-schema --experimental`` (local: no network, no model call) and check it."""
    r = subprocess.run([binary, "--version"], capture_output=True, text=True, timeout=30)
    version = r.stdout.strip() or "unknown"
    os.makedirs(out_dir, exist_ok=True)
    g = subprocess.run([binary, "app-server", "generate-json-schema", "--experimental", "--out", out_dir], capture_output=True, text=True, timeout=120)
    if g.returncode != 0:
        raise CodexAppServerError(f"this Codex ({version}) could not generate its app-server schema: update Codex, or use LAMPWAY_PROVIDER=codex_cli")
    return probe_schema(out_dir, version)


class _Client:
    def __init__(self, argv, env, cwd):
        self.argv, self.env, self.cwd = argv, env, cwd
        self.proc = None
        self.events: asyncio.Queue = asyncio.Queue()
        self.futures = {}
        self.next_id = 1
        self.thread_id = None
        self.turn_active = False
        self.pending = {}          # callId -> rpc id awaiting our answer
        self.duplicates = {}       # callId -> [more rpc ids]
        self.results = {}          # callId -> stored result
        self.closed = False
        self.needs_replay = False

    async def start(self):
        self.proc = await asyncio.create_subprocess_exec(*self.argv, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL, env=self.env, cwd=self.cwd)
        self._reader = asyncio.get_running_loop().create_task(self._read())

    async def _send(self, obj):
        try:
            self.proc.stdin.write((json.dumps(obj) + "\n").encode())
            await self.proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError):
            self.closed = True

    async def _read(self):
        try:
            while True:
                line = await self.proc.stdout.readline()
                if not line:
                    break
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if "method" in msg and "id" in msg:                      # a server REQUEST
                    if msg["method"] == "item/tool/call":
                        if not self.turn_active:
                            await self._send({"id": msg["id"], "error": {"code": -32600, "message": NO_TURN}})
                            continue
                        self.events.put_nowait(("request", msg["method"], msg["id"], msg.get("params") or {}))
                    else:
                        await self._send({"id": msg["id"], "error": {"code": -32601, "message": UNSUPPORTED}})
                elif "method" in msg:
                    self.events.put_nowait(("notify", msg["method"], None, msg.get("params") or {}))
                elif "id" in msg and msg["id"] in self.futures:
                    fut = self.futures.pop(msg["id"])
                    if not fut.done():
                        fut.set_result(msg)
        finally:
            self.closed = True
            for fut in self.futures.values():
                if not fut.done():
                    fut.set_exception(CodexAppServerError(CLOSED))
            self.events.put_nowait(("closed", None, None, {}))

    async def request(self, method, params, timeout=60.0):
        rid = self.next_id
        self.next_id += 1
        fut = asyncio.get_running_loop().create_future()
        self.futures[rid] = fut
        await self._send({"id": rid, "method": method, "params": params})
        try:
            msg = await asyncio.wait_for(fut, timeout)
        except asyncio.TimeoutError:
            self.futures.pop(rid, None)
            raise CodexAppServerError(f"Codex did not answer {method} within {timeout:g} s") from None
        if "error" in msg:
            raise CodexAppServerError(f"Codex refused {method}: {msg['error'].get('message', '')}"[:300])
        return msg.get("result") or {}

    async def notify(self, method, params=None):
        await self._send({"method": method, "params": params or {}})

    async def request_raw(self, obj):
        await self._send(obj)

    async def answer(self, call_id, text, is_error):
        result = {"success": not is_error, "contentItems": [{"type": "inputText", "text": text}]}
        self.results[call_id] = result
        for rid in [self.pending.pop(call_id, None)] + self.duplicates.pop(call_id, []):
            if rid is not None:
                await self._send({"id": rid, "result": result})

    async def close(self):
        if self.proc is not None and self.proc.returncode is None:
            try:
                self.proc.stdin.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                await asyncio.wait_for(self.proc.wait(), 3)
            except asyncio.TimeoutError:
                self.proc.kill()
        if getattr(self, "_reader", None):
            self._reader.cancel()


class CodexAppServerProvider:
    name = "codex_app_server"

    def __init__(self, binary="codex", model="", effort="medium", turn_timeout_s=180.0, idle_close_s=600.0, schema_dir=None, env=None, extra_env=None, workdir=None, tool_batch_quiet_s=0.25):
        if effort not in EFFORTS:
            raise CodexAppServerError(f"effort is {', '.join(EFFORTS)}")
        if not 30 <= float(idle_close_s) <= 3600 and idle_close_s != 0:
            pass
        self.binary, self.model, self.effort = binary, model, effort
        self.turn_timeout_s, self.idle_close_s, self.quiet = float(turn_timeout_s), float(idle_close_s), float(tool_batch_quiet_s)
        self.schema_dir = schema_dir
        self._env = dict(env) if env is not None else child_env(os.environ)
        self._env.update(extra_env or {})
        if workdir is None:
            self._own_workdir = tempfile.TemporaryDirectory(prefix="lampway-codex-")         # removed with the provider (it was a leaked /tmp dir per provider)
            workdir = self._own_workdir.name
        self.workdir = workdir
        self._clients: dict = {}
        self._probed = False

    # ----------------------------------------------------------------------------------------------------- setup
    def _argv(self):
        return list(self.binary) if isinstance(self.binary, (list, tuple)) else [self.binary, "app-server"]

    def _probe(self):
        if self._probed:
            return
        if self.schema_dir:
            probe_schema(self.schema_dir)
        elif not isinstance(self.binary, (list, tuple)):
            if shutil.which(self.binary) is None:
                raise CodexAppServerError(f"{self.binary} is not installed or not on PATH: install Codex and sign in once yourself")
            with tempfile.TemporaryDirectory(prefix="lampway-codex-schema-") as schema_out:
                probe_binary(self.binary, schema_out)
        self._probed = True

    @staticmethod
    def _spec(t) -> dict:
        if not isinstance(t.parameters, dict):
            raise CodexAppServerError(f"the parameters of tool {t.name} are not a JSON object schema")
        return {"type": "function", "name": t.name, "description": t.description, "inputSchema": t.parameters, "deferLoading": False}

    async def _ensure(self, session_id, request):
        c = self._clients.get(session_id)
        if c is not None and not c.closed:
            return c
        replay = c is not None
        self._probe()
        specs = [self._spec(t) for t in request.tools]
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        c = _Client(self._argv(), self._env, self.workdir)
        await c.start()
        c.needs_replay = replay
        await c.request("initialize", {"clientInfo": {"name": "lampway", "version": "0.1.0"}, "capabilities": {"experimentalApi": True}}, timeout=35.0)
        await c.notify("initialized")
        params = {"cwd": self.workdir, "baseInstructions": request.system, "dynamicTools": specs, "approvalPolicy": "never", "sandbox": "read-only", "ephemeral": True,
                  "config": {"features.shell_tool": False, "features.multi_agent": False}}
        if self.model:
            params["model"] = self.model
        res = await c.request("thread/start", params, timeout=60.0)
        c.thread_id = (res.get("thread") or {}).get("id") or res.get("threadId")
        self._clients[session_id] = c
        return c

    @staticmethod
    def _turn_text(request: ModelRequest, replay: bool) -> str:
        if not replay:
            return request.messages[-1].text()
        lines = ["[history replay] The earlier conversation, replayed because the Codex process restarted:"]
        for m in request.messages:
            t = m.text()
            if t:
                lines.append(f"{m.role}: {t}")
        return "\n".join(lines)

    # ----------------------------------------------------------------------------------------------------- stream
    async def stream(self, request: ModelRequest, session_id: Optional[str] = None):
        from ... import egress as EG
        with EG.guard("chatgpt_plan", kind="text"):                    # one turn: gated and lit while the app-server talks to its provider
            async for ev in self._stream(request, session_id):
                yield ev

    async def _stream(self, request: ModelRequest, session_id: Optional[str] = None):
        sid = session_id or getattr(request, "session_id", "") or "default"
        c = await self._ensure(sid, request)
        last = request.messages[-1]
        tool_results = [p for p in last.content if p.get("type") == "tool_result"] if last.role == "user" else []
        if tool_results and c.turn_active:
            for p in tool_results:
                await c.answer(p.get("tool_call_id"), str(p.get("content", "")), bool(p.get("is_error")))
        else:
            c.turn_active = True                                   # BEFORE the request: the first tool call can arrive right behind the response
            try:
                await c.request("turn/start", {"threadId": c.thread_id, "input": [{"type": "text", "text": self._turn_text(request, c.needs_replay)}], "effort": self.effort}, timeout=60.0)
            except CodexAppServerError:
                c.turn_active = False
                raise
            c.needs_replay = False
        deadline = time.monotonic() + self.turn_timeout_s
        yielded_call = False
        while True:
            remaining = deadline - time.monotonic()
            wait = min(self.quiet, remaining) if yielded_call else remaining
            try:
                kind, method, rid, params = await asyncio.wait_for(c.events.get(), max(wait, 0.001))
            except asyncio.TimeoutError:
                if yielded_call and remaining > 0:
                    return                                         # the turn is waiting on our tools: hand control back to Lampway's loop
                await c._send({"id": c.next_id, "method": "turn/interrupt", "params": {"threadId": c.thread_id}})
                c.next_id += 1
                c.turn_active = False
                c.pending.clear()
                yield Stop(f"Codex did not finish the turn within {self.turn_timeout_s:g} s; it was interrupted")
                return
            if kind == "closed":
                self._clients.pop(sid, None)
                self._clients[sid] = c
                c.turn_active = False
                yield Stop(CLOSED)
                return
            if kind == "notify":
                if method == "item/agentMessage/delta":
                    yield Text(str(params.get("delta", "")))
                elif method == "turn/completed":
                    c.turn_active = False
                    turn = params.get("turn") or {}
                    if turn.get("status") in ("failed", "interrupted") or turn.get("error"):
                        yield Stop(str((turn.get("error") or {}).get("message") or turn.get("status")))
                    return
                continue
            if kind == "request" and method == "item/tool/call":
                cid = params.get("callId")
                if cid in c.results:
                    await c._send({"id": rid, "result": c.results[cid]})
                elif cid in c.pending:
                    c.duplicates.setdefault(cid, []).append(rid)
                else:
                    c.pending[cid] = rid
                    yielded_call = True
                    yield ToolCall(id=cid, name=params.get("tool", ""), arguments=params.get("arguments") or {})

    async def close(self):
        for c in list(self._clients.values()):
            await c.close()
        self._clients.clear()
