# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""``lampway_capabilities``: the agent's window onto the Capabilities board (docs/reports/agent-modes-spec.md E2). It lists what the
agent may do, explains one capability, and proposes a change with a reason, which the user accepts or declines. There is no
action that sets anything: an agent never enables its own capability."""

import json

from .. import capabilities as CAP
from .providers.base import ToolSpec

NAMES = {"lampway_capabilities"}
ACTIONS = ["list", "explain", "propose", "proposals"]
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["action"], "properties": {
    "action": {"type": "string", "enum": ACTIONS, "description": "list | explain | propose | proposals"},
    "id": {"type": "string", "description": "a capability id (list shows them); explain and propose need it"},
    "enabled": {"type": "boolean", "description": "propose: the state you would like"},
    "reason": {"type": "string", "description": "propose: why, in one sentence the user reads"}}}


def specs() -> list:
    return [ToolSpec("lampway_capabilities",
                     "What you may do in Lampway, as the user set it: `list` every capability with whether it is in force and why not, "
                     "`explain` one, and `propose` turning one on or off with a reason - the user accepts or declines it. You cannot "
                     "change a capability yourself. When a tool is refused because its capability is off, propose it instead of "
                     "working around it.", SCHEMA)]


def _answer(args: dict, origin: str) -> dict:
    extra = set(args) - set(SCHEMA["properties"])
    if extra:
        raise ValueError(f"unknown field {sorted(extra)[0]!r}")
    action = args.get("action")
    if action not in ACTIONS:
        raise ValueError(f"action is one of {', '.join(ACTIONS)}: there is no set")
    store = CAP.ACTIVE
    if store is None:
        raise ValueError("the Capabilities board is not available on this server")
    if action == "list":
        return {"capabilities": [{k: r[k] for k in ("id", "label", "in_force", "why_not", "risk")} for r in store.view(CAP.project())]}
    if action == "proposals":
        return {"proposals": [{k: p[k] for k in ("pid", "id", "change", "reason", "state")} for p in store.proposals()]}
    cid = str(args.get("id") or "")
    cap = CAP.get(cid)
    if action == "explain":
        on, why = store.effective(cid, CAP.project())
        return {"id": cid, "label": cap.label, "does": cap.does, "risk": cap.risk, "routes": list(cap.routes), "in_force": on,
                "why_not": why}
    if "enabled" not in args:
        raise ValueError("a proposal says enabled: true or false")
    pid = store.propose(origin, cid, {"enabled": bool(args["enabled"])}, str(args.get("reason") or ""))
    return {"proposal": pid, "state": "proposed", "note": "the user decides in Capabilities; nothing has changed"}


def call(name: str, arguments, origin: str = "agent") -> tuple:
    try:
        return json.dumps(_answer(arguments if isinstance(arguments, dict) else {}, origin)), False
    except (ValueError, CAP.UnknownCapability, CAP.Refused) as exc:
        return str(exc), True
