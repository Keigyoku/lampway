"""The MCP endpoint behind the client's connector ("Connect AI apps"): one JSON-RPC 2.0 message from an external AI app per POST.

``initialize``, ``ping``, ``tools/list`` and ``tools/call`` are served; notifications are accepted (202). A tool call runs in the
app instance named by ``X-Mixar-Instance-Id`` and the scene session named by ``X-Mixar-Session-Id``, as a ``blender.execute_script``
round trip inside an MCP operation (``mcp.begin_operation`` leases the scene, the script carries its ``mcp_operation_id``,
``mcp.end_operation`` releases it), the client's condition for admitting a script from an external app. Offered: the scene tools, the Lampway tools that are one script in Blender, and the Asset Vault family
(``lampway_vault_*``, run here on the server with the external client's authority: read and curate, never spend, never enrol a folder).
NOT offered: the studio tools (they spend credits on the owner's subscription) and the swarm (only a Lampway pane bound to a scene tab
starts one, below). The other server-run tools are Lampway Agent's (Mode 1, through its unit's endpoint, ``engine/mcp_endpoint.py``).

The pane endpoint (``POST /api/v1/mcp/pane``, docs/reports/agent-modes-spec.md S3) is not for external apps. Loopback only, it
answers only a pane Lampway started on its own herdr server, proven by that pane's own bearer, which lives only in the pane's own
MCP config (0600 under the Lampway root):
  * a **swarm worker pane** (session header ``swarm:<swarm_id>:<worker_id>``, bearer = that worker's token, minted by its
    ``PaneBrain``): offered ``worker_tools()`` as Capabilities allow, plus ``lampway_worker_done``; every call runs through the
    worker's ``WorkerJob.call_tool``, on the worker's own headless Lampway. Never the swarm, the studios or the workbench;
  * a **bound BYOA pane** (B2; bearer = the pane's key, its sha256 in the cockpit's record): offered only ``swarm_start``,
    ``swarm_status``, ``swarm_cancel`` and ``swarm_collect``, only with capability ``swarm`` in force and the BYOA switch on. Its
    swarm is Mode 2's: its workers are panes on the pane's own harness (``PaneBrain``, the one brain; the unit's mode picks the
    adapter), split into the pane's tab, and its work lands in the pane's bound scene tab; it reaches only the swarms it started.
    No swarm tool spends.
On the external route a ``swarm:`` session header is refused: a binding is not a credential.
"""

import asyncio
import json
import uuid
from collections import OrderedDict

from .agent import choices_tools as CHT
from .agent import connections_tools as CNT
from .agent import lampway_tools as lt
from .agent import vault_tools as lib
from .agent.providers.base import ToolSpec
from .agent.tools import RUN_BLENDER_PYTHON, SCENE_SUMMARY, TOOLS, UnknownTool, format_tool_result, script_for

JOURNAL_MAX = 200
SPEND_POLICY = "Nothing offered here spends credits. Generation and studio actions are not offered over MCP; an external agent can plan, and the user confirms in the Client (no tool here confirms a spend)."
SERVER_TOOLS = (
    ToolSpec("lampway_credit_balance", "What the local ledger says was spent, by provider and unit, the job states, and the configured caps. Read-only; it never reads a studio's credit balance or any secret.",
             {"type": "object", "additionalProperties": False, "properties": {}}),
    ToolSpec("lampway_call_status", "The recorded outcome of an earlier tool call by its call id (every result names one): running, or complete with its text. Use it after your own request timed out.",
             {"type": "object", "additionalProperties": False, "required": ["call_id"], "properties": {"call_id": {"type": "string"}}}),
)

PROTOCOL_VERSION = "2025-06-18"
LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}
WORKER_INSTRUCTIONS = ("You are one worker of a Lampway swarm. These tools act on YOUR OWN headless Lampway scene, never the user's. "
                       "Do your task, then call lampway_worker_done once with one sentence saying what you made.")
PANE_INSTRUCTIONS = ("Lampway's swarm for this pane's scene tab: swarm_start runs workers, each in its own pane with its own headless "
                     "Lampway; swarm_collect brings their work into this tab. Scene tools are on the pane's lampway entry.")
MAX_LEASE_SECONDS = 600            # the client caps an operation at 600 s (mcp_bridge/constants.py MAX_TIMEOUT_SECONDS)
LEASE_MARGIN_SECONDS = 30          # the lease outlives the script's own timeout
LEASE_RPC_SECONDS = 30             # begin/end are main-thread bookkeeping in the client
PARSE_ERROR, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32601, -32602


def _instructions() -> str:
    from .agent_files import generate as GEN
    return GEN.mcp_instructions()


def offered_tools() -> list:
    return [t for t in TOOLS if t.name in (RUN_BLENDER_PYTHON, SCENE_SUMMARY) or t.name in lt.BY_NAME or t.name in lib.NAMES or t.name in CNT.NAMES or t.name in CHT.NAMES] + list(SERVER_TOOLS)


def _error(request_id, code, message):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


class McpServer:
    def __init__(self, hub, agent, ledger=None, caps=None, byoa_enabled=None):
        from .herdr.swarm_brain import WorkerBindings
        self.hub = hub
        self.agent = agent
        self.ledger = ledger
        self.caps = caps or (lambda: {})
        self.journal: "OrderedDict[str, dict]" = OrderedDict()               # call id -> recorded outcome (bounded)
        # spec S3: the swarm's worker panes, by binding: the swarm's own table, whichever mode started it
        swarm = getattr(agent, "swarm", None)
        self.workers = swarm.bindings if swarm is not None else WorkerBindings()
        self.byoa_enabled = byoa_enabled or (lambda: False)
        self._pane_swarms: dict = {}                                         # swarm id -> the cockpit session that started it

    def tools_payload(self) -> list:
        return [{"name": t.name, "description": t.description, "inputSchema": t.parameters, "_meta": {"spend": False, "spend_policy": SPEND_POLICY}} for t in offered_tools()]

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
        if str(session_id or "").startswith("swarm:"):                 # spec S3: a binding is not a credential
            return self._result(request_id, "refused: a swarm worker's binding is served only to that worker's own pane, on Lampway's pane "
                                            "endpoint with its own token; this route never reaches a worker", True)
        from . import capabilities as CAP
        refusal = CAP.check_tool(name, params.get("arguments") or {}, origin="mcp:" + (instance_id or "client"))   # spec E2
        if refusal is not None:
            return self._result(request_id, refusal, True)
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
            return self._result(request_id, "the desktop app is not connected to this server (open Lampway and sign in)", True)
        try:
            script = script_for(name, params.get("arguments") or {})
        except (UnknownTool, lt.BadArguments) as exc:
            return self._result(request_id, str(exc), True)
        call_id = str(uuid.uuid4())
        self._remember(call_id, {"state": "running", "tool": name})
        task = asyncio.ensure_future(self._leased_script(socket, session_id, call_id, name, script))

        def record(t):
            if t.cancelled():
                self._remember(call_id, {"state": "complete", "tool": name, "is_error": True, "text": "the call was cancelled"})
            elif t.exception() is not None:
                self._remember(call_id, {"state": "complete", "tool": name, "is_error": True, "text": f"Blender could not run the tool: {type(t.exception()).__name__}: {t.exception()}"})
            else:
                text, is_error = format_tool_result(t.result())
                self._remember(call_id, {"state": "complete", "tool": name, "is_error": bool(is_error), "text": text})

        task.add_done_callback(record)
        try:
            await asyncio.shield(task)                                       # the external app's request may die; the call and its record survive
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - recorded by the callback; the external app is told, the server stays up
            pass
        rec = self.journal[call_id]
        res = self._result(request_id, f"{rec['text']}\n(call id: {call_id})", rec["is_error"])
        res["result"]["_meta"] = {"call_id": call_id}
        return res

    async def _leased_script(self, socket, session_id, call_id, name, script):
        """The script inside an MCP operation (audit F2): the client admits a script only while its scene is leased and only with
        that lease's id in the agent context. Begin over the socket, run, and end in ``finally`` (a failed or dropped script
        still releases the scene). A refused lease is the call's answer; no script is sent."""
        operation_id = str(uuid.uuid4())
        timeout = max(1, min(MAX_LEASE_SECONDS, int(getattr(self.agent, "script_timeout_s", MAX_LEASE_SECONDS)) + LEASE_MARGIN_SECONDS))
        begun = await socket.request("mcp.begin_operation", {"operation_id": operation_id, "session_id": session_id or "", "timeout_seconds": timeout},
                                     timeout=LEASE_RPC_SECONDS)
        if not isinstance(begun, dict) or not begun.get("success"):
            return begun if isinstance(begun, dict) else {"success": False, "error": "the app did not lease a scene for this call"}
        leased = begun.get("session_id") or session_id
        try:
            return await self.agent._blender_script(socket, session_id=leased, chat_session_id=leased, turn_id="mcp", call_id=call_id, tool_name=name,
                                                    script=script, mcp_operation_id=operation_id)
        finally:
            try:
                await socket.request("mcp.end_operation", {"operation_id": operation_id, "session_id": leased}, timeout=LEASE_RPC_SECONDS)
            except Exception:  # noqa: BLE001 - the lease also expires on its own deadline; the call's outcome stands
                pass

    @staticmethod
    def _result(request_id, text, is_error):
        return {"jsonrpc": "2.0", "id": request_id, "result": {"content": [{"type": "text", "text": text}], "isError": bool(is_error)}}


    # ------------------------------------------------------------------------------------------------- the pane endpoint (spec S3)
    def pane_caller(self, token: str, session: str):
        """("worker", binding) for a swarm worker's own pane, ("pane", record) for a bound BYOA pane's key, else None."""
        if str(session or "").startswith("swarm:"):
            binding = self.workers.resolve(session, token)
            return ("worker", binding) if binding is not None else None
        cockpit = getattr(self.agent, "cockpit", None)
        rec = cockpit.pane_for_key(token) if token and hasattr(cockpit, "pane_for_key") else None
        return ("pane", rec) if rec is not None else None

    @staticmethod
    def worker_specs() -> list:
        from . import capabilities as CAP
        from .agent.swarm import worker_tools
        from .herdr.swarm_brain import WORKER_DONE
        return [t for t in worker_tools() if CAP.tool_offered(t.name)] + [WORKER_DONE]

    @staticmethod
    def pane_specs() -> list:
        from . import capabilities as CAP
        from .agent.swarm import SWARM_SPECS
        return [s for s in SWARM_SPECS if CAP.tool_offered(s.name)]

    async def handle_pane(self, message, caller):
        """One JSON-RPC message from a pane ``pane_caller`` proved; None for a notification."""
        kind, who = caller
        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _error(None, -32600, "not a JSON-RPC 2.0 request")
        method, request_id, params = message.get("method"), message.get("id"), message.get("params") or {}
        if request_id is None:
            return None
        if method == "initialize":
            return {"jsonrpc": "2.0", "id": request_id, "result": {
                "protocolVersion": (params.get("protocolVersion") if isinstance(params, dict) else None) or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}}, "serverInfo": {"name": "lampway", "version": "0.1.0"},
                "instructions": WORKER_INSTRUCTIONS if kind == "worker" else PANE_INSTRUCTIONS}}
        if method == "ping":
            return {"jsonrpc": "2.0", "id": request_id, "result": {}}
        specs = self.worker_specs() if kind == "worker" else self.pane_specs()
        if method == "tools/list":
            return {"jsonrpc": "2.0", "id": request_id, "result": {"tools": [
                {"name": t.name, "description": t.description, "inputSchema": t.parameters, "_meta": {"spend": False}} for t in specs]}}
        if method == "tools/call":
            name = str(params.get("name") or "")
            arguments = params.get("arguments") if isinstance(params.get("arguments"), dict) else {}
            text, is_error = await (self._worker_call(who, name, arguments, specs) if kind == "worker" else self._pane_call(who, name, arguments))
            return self._result(request_id, text, is_error)
        return _error(request_id, METHOD_NOT_FOUND, f"Method not found: {method}")

    async def _worker_call(self, binding, name, arguments, specs) -> tuple:
        from . import capabilities as CAP
        from .herdr.swarm_brain import WORKER_DONE
        if name not in {t.name for t in specs}:
            return f"refused: {name} is not one of a swarm worker's tools (call lampway_worker_done when your task is done)", True
        if not binding.live:
            return (f"refused: {binding.name} has {'finished' if binding.state == 'done' else 'been stopped'}: this pane can no longer "
                    "use Lampway's tools"), True
        if name == WORKER_DONE.name:
            summary = " ".join(str(arguments.get("summary") or "").split())[:2000]
            if not summary:
                return "lampway_worker_done needs `summary`: one sentence saying what you made", True
            self.workers.finish(binding, summary)
            return "Done: your work is being brought into the user's scene. You can stop now.", False
        refusal = CAP.check_tool(name, arguments, origin=f"worker:{binding.name}")
        if refusal is not None:
            return refusal, True
        try:
            return await binding.job.call_tool(name, arguments)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - the worker's Lampway silent or gone: the pane is told
            return f"{name} could not run: {type(exc).__name__}: {exc}", True

    async def _pane_call(self, rec, name, arguments) -> tuple:
        from . import capabilities as CAP
        from .agent.swarm import SWARM_NAMES, SwarmContext
        if name not in SWARM_NAMES:
            return f"refused: {name} is not served here: this entry is the swarm's; Lampway's scene tools are on the pane's lampway entry", True
        refusal = CAP.check_tool(name, arguments, origin=f"pane:{rec['id']}")
        if refusal is not None:
            return refusal, True
        if not rec.get("scene_session_id"):
            return ("refused: this pane is not bound to a scene tab: bind it to a tab in Lampway first (a swarm's work lands in "
                    "that tab)"), True
        if not self.byoa_enabled():
            return "refused: your own agents in Lampway's panes are off (the BYOA switch): the user switches them on", True
        if name != "swarm_start" and self._pane_swarms.get(str(arguments.get("swarm_id") or "")) != rec["id"]:
            return f"refused: swarm {arguments.get('swarm_id')!r} was not started by this pane", True
        desktops = [s for s in self.hub.sockets.values() if getattr(s, "role", "") != "sandbox"]
        if name == "swarm_start" and len(desktops) != 1:
            return ("the desktop app is not connected to this server (open Lampway and sign in)" if not desktops else
                    "several Lampway apps are connected to this server: a pane's swarm needs exactly one"), True
        # Mode 2 (a bound pane): its workers run on the pane's own harness (S3, Q10), in its unit's tab (the bound scene tab, A4)
        ctx = SwarmContext(socket=desktops[0] if len(desktops) == 1 else None, session_id=rec["scene_session_id"], turn_id=f"pane:{rec['id']}",
                           call_id=str(uuid.uuid4()), mode="byoa", harness=rec.get("harness") or rec.get("agent"), cwd=rec.get("cwd"),
                           project_root=rec.get("project_root"))
        text, is_error = await self.agent.swarm.call(name, arguments, ctx)
        if name == "swarm_start" and not is_error:
            try:
                self._pane_swarms[json.loads(text)["swarm_id"]] = rec["id"]
            except (ValueError, KeyError, TypeError):
                pass
        return text, is_error


def parse(body: bytes):
    try:
        return json.loads(body.decode("utf-8")), None
    except (ValueError, UnicodeDecodeError):
        return None, _error(None, PARSE_ERROR, "Parse error")
