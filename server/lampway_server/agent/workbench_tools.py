"""The agent's cockpit tool: list the sessions, read a session's screen, and send input ONLY where the user enabled agent sends for that session. It can never create, close or stop anything:
those are the user's actions in the cockpit. Reading never acknowledges an unread answer."""
import json

from ..herdr.host import Cockpit, CockpitError
from ..herdr import launcher as L
from . import server_tools as ST
from .providers.base import ToolSpec

NAMES = {"lampway_workbench"}


def specs() -> list:
    return [ToolSpec("lampway_workbench", "The cockpit's agent sessions (the user's real Claude Code / Codex / OpenCode in Lampway's own herdr server). action list: the sessions with their state; read (id, lines "
                     "<= 150): a session's screen text; send (id, text, submit): types into a session ONLY if the user enabled agent sends for it (default off), never into a shell session, never while the "
                     "user is typing. You cannot create, stop or close sessions: those are the user's actions.",
                     {"type": "object", "additionalProperties": False, "required": ["action"], "properties": {
                         "action": {"type": "string", "description": "list | read | send"}, "id": {"type": "string"}, "lines": {"type": "integer"}, "text": {"type": "string"},
                         "submit": {"type": "boolean"}}})]


async def call(cockpit: Cockpit, name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    try:
        act = a.get("action")
        if act == "list":
            return json.dumps({"server": {"running": bool(L.server_status(cockpit.root).get("running"))},
                               "sessions": [{k: s.get(k) for k in ("id", "name", "agent", "cwd", "state", "agent_sends", "task", "end_reason")} for s in cockpit.list_sessions()]}), False
        if act == "read":
            return json.dumps({"screen": cockpit.read_screen(a.get("id") or "", int(a.get("lines") or 70))}), False
        if act == "send":
            cockpit.send_input(a.get("id") or "", str(a.get("text") or ""), bool(a.get("submit", True)), by="agent")
            return json.dumps({"sent": True}), False
        return "action is list | read | send", True
    except (CockpitError, L.HerdrError) as exc:
        return str(exc), True
