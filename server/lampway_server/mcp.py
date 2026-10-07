"""The MCP endpoint behind the client's connector ("Connect AI apps"): one JSON-RPC 2.0 message from an external AI app per POST.

``initialize``, ``ping``, ``tools/list`` and ``tools/call`` are served; notifications are accepted (202). A tool call runs in the
app instance named by ``X-Mixar-Instance-Id`` and the scene session named by ``X-Mixar-Session-Id``, as a ``blender.execute_script``
round trip, exactly like the agent's own tool calls. Offered: the scene tools, the Lampway tools that are one script in Blender, and the Asset Vault family
(``lampway_vault_*``, run here on the server with the external client's authority: read and curate, never spend, never enrol a folder).
NOT offered: the studio tools (they spend credits on the owner's subscription), the swarm and ``ask_user`` (they need the agent loop).
"""

import asyncio
import json
import uuid
from collections import OrderedDict

from .agent import choices_tools as CHT
from .agent import blender_docs_tools as BDT
from .agent import connections_tools as CNT
from .agent import lampway_tools as lt
from .agent import vault_tools as lib
from .agent.providers.base import ToolSpec
from .agent.tools import RUN_BLENDER_PYTHON, SCENE_SUMMARY, TOOLS, UnknownTool, format_tool_result, script_for
from . import mcp_envelope as ENVELOPE

JOURNAL_MAX = 200
SPEND_POLICY = "Nothing offered here spends credits. Generation and studio actions are not offered over MCP; an external agent can plan, and the user confirms in the Client (no tool here confirms a spend)."
SERVER_TOOLS = (
    ToolSpec("lampway_credit_balance", "What the local ledger says was spent, by provider and unit, the job states, and the configured caps. Read-only; it never reads a studio's credit balance or any secret.",
             {"type": "object", "additionalProperties": False, "properties": {}}),
    ToolSpec("lampway_call_status", "The recorded outcome of an earlier tool call by its call id (every result names one): running, or complete with its text. Use it after your own request timed out.",
             {"type": "object", "additionalProperties": False, "required": ["call_id"], "properties": {"call_id": {"type": "string"}}}),
)

PROTOCOL_VERSION = "2025-06-18"
PARSE_ERROR, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32601, -32602


def _instructions() -> str:
    from .agent_files import generate as GEN
    return GEN.mcp_instructions()


def offered_tools() -> list:
    return [t for t in TOOLS if t.name in (RUN_BLENDER_PYTHON, SCENE_SUMMARY) or t.name in lt.BY_NAME or t.name in lib.NAMES or t.name in CNT.NAMES or t.name in CHT.NAMES or t.name in BDT.NAMES] + list(SERVER_TOOLS)


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class McpServer:
    def __init__(self, hub, agent, ledger=None, caps=None):
        self.hub = hub
        self.agent = agent
        self.ledger = ledger
        self.caps = caps or (lambda: {})
        self.journal: "OrderedDict[str, dict]" = OrderedDict()               # call id -> recorded outcome (bounded)

    def tools_payload(self) -> list:
        payload = []
        for t in offered_tools():
            row = {"name": t.name, "description": t.description, "inputSchema": t.parameters,
                   "_meta": {"spend": False, "spend_policy": SPEND_POLICY}}
            if t.name in ENVELOPE.NAMES:
                row["outputSchema"] = ENVELOPE.output_schema(t.name)
            payload.append(row)
        return payload

    async def handle(self, message, instance_id: str, session_id: str):
        """The JSON-RPC response for one request, or None for a notification."""
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "not a JSON-RPC 2.0 request")
        method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {}
        if request_id is None:
            return None                                              # a notification (notifications/initialized, cancelled, ...)
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": PROTOCOL_VERSION, "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "lampway", "version": "0.1.0"},
                "instructions": _instructions()}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": self.tools_payload()}}
        if method == "tools/call":
            return await self._call(request_id, params, instance_id, session_id)
        return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    def _credit_balance(self) -> dict:
        totals, states = {}, {}
        for row in (self.ledger.rows("job") if self.ledger is not None else []):
            price = row.get("price") or {}
            if price.get("amount") is not None:
                k = (row.get("provider"), price.get("unit") or "")
                t = totals.setdefault(k, {"provider": k[0], "unit": k[1], "amount": 0.0, "jobs": 0})
                t["amount"] += float(price["amount"])
                t["jobs"] += 1
            states[row.get("state")] = states.get(row.get("state"), 0) + 1
        return {"ok": True, "spend_by_provider": [{**t, "amount": round(t["amount"], 6)} for t in totals.values()], "jobs_by_state": states, "caps": self.caps(),
                "note": "from the local ledger only; a studio's own credit balance is read-only state in the Client and is never read here"}

    def _call_status(self, request_id, call_id):
        rec = self.journal.get(str(call_id))
        if rec is None:
            return self._result(request_id, f"no call {call_id!r} in the journal (it keeps the last {JOURNAL_MAX})", True)
        return self._result(request_id, json.dumps({"call_id": call_id, **rec}), False)

    def _remember(self, call_id, rec):
        self.journal[call_id] = rec
        while len(self.journal) > JOURNAL_MAX:
            self.journal.popitem(last=False)

    async def _call(self, request_id, params, instance_id, session_id):
        name = params.get("name")
        if name not in {t.name for t in offered_tools()}:
            return _error(request_id, INVALID_PARAMS, f"unknown or not offered tool {name!r}")
        arguments = params.get("arguments", {})
        if name in ENVELOPE.NAMES:
            schema = next(t.parameters for t in offered_tools() if t.name == name)
            bad = ENVELOPE.argument_error(name, arguments, schema)
            if bad:
                return ENVELOPE.result(request_id, bad, name=name)
        if name in BDT.NAMES:
            data, is_error = await BDT.call(name, arguments)
            return ENVELOPE.result(request_id, data, name=name, full=arguments.get("full", False))
        if name == "lampway_credit_balance":
            return self._result(request_id, json.dumps(self._credit_balance()), False)
        if name in CNT.NAMES:                                       # the same read-only projection the main agent gets
            text, is_error = await CNT.call(name, params.get("arguments") or {})
            return self._result(request_id, text, is_error)
        if name in CHT.NAMES:                                       # read and propose, attributed to the MCP client
            text, is_error = await CHT.call(name, params.get("arguments") or {}, origin="mcp:" + (instance_id or "client"))
            return self._result(request_id, text, is_error)
        if name == "lampway_call_status":
            return self._call_status(request_id, (params.get("arguments") or {}).get("call_id"))
        if name in lib.NAMES:                                              # the Vault answers here: no scene, no instance needed
            text, is_error = await lib.call(getattr(self.agent, "assets", None), name, params.get("arguments") or {}, {"origin": "mcp", "agent_id": "mcp"})
            return self._result(request_id, text, is_error)
        socket = self.hub.sockets.get(instance_id)
        if socket is None:
            if name in ENVELOPE.NAMES:
                return ENVELOPE.result(request_id, ENVELOPE.refusal("app_not_connected",
                    "The desktop app is not connected to this server; open Lampway and sign in", []))
            return self._result(request_id, "the desktop app is not connected to this server (open Lampway and sign in)", True)
        try:
            script = script_for(name, params.get("arguments") or {})
        except (UnknownTool, lt.BadArguments) as exc:
            if name in ENVELOPE.NAMES:
                return ENVELOPE.result(request_id, ENVELOPE.refusal("bad_argument", str(exc),
                    [f"{name} {'action' if name == 'lampway_view' else 'view'}=help"]))
            return self._result(request_id, str(exc), True)
        call_id = str(uuid.uuid4())
        self._remember(call_id, {"state": "running", "tool": name})
        task = asyncio.ensure_future(self.agent._blender_script(socket, session_id=session_id, chat_session_id=session_id, turn_id="mcp", call_id=call_id, tool_name=name, script=script))

        def record(t):
            if t.cancelled():
                self._remember(call_id, {"state": "complete", "tool": name, "is_error": True, "text": "the call was cancelled"})
            elif t.exception() is not None:
                self._remember(call_id, {"state": "complete", "tool": name, "is_error": True, "text": f"Blender could not run the tool: {type(t.exception()).__name__}: {t.exception()}"})
            else:
                text, is_error = format_tool_result(t.result())
                rec = {"state": "complete", "tool": name, "is_error": bool(is_error), "text": text}
                if name in ENVELOPE.NAMES:
                    rec["data"] = t.result()
                self._remember(call_id, rec)

        task.add_done_callback(record)
        try:
            await asyncio.shield(task)                                       # the external app's request may die; the call and its record survive
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - recorded by the callback; the external app is told, the server stays up
            pass
        rec = self.journal[call_id]
        if name in ENVELOPE.NAMES:
            data = rec.get("data")
            if rec["is_error"]:
                raw = data if isinstance(data, dict) else {}
                data = ENVELOPE.refusal(raw.get("error_type") or "execution_failed", raw.get("error") or rec["text"],
                    ["lampway_call_status call_id=<call_id>"])
            res = ENVELOPE.result(request_id, data, name=name, full=arguments.get("full", False),
                                  max_bytes=arguments.get("max_bytes", 750000))
            res["result"]["_meta"] = {"call_id": call_id}
            return res
        res = self._result(request_id, f"{rec['text']}\n(call id: {call_id})", rec["is_error"])
        res["result"]["_meta"] = {"call_id": call_id}
        return res

    @staticmethod
    def _result(request_id, text, is_error):
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}}


def parse(body: bytes):
    try:
        return json.loads(body.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError):
        return None, _error(None, PARSE_ERROR, "Parse error")
