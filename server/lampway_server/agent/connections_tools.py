# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""The agent's view of Connections (specs/connections/connections_status_tool.md): READ status only. Seven fields per connection and no
others - never an identity, a plan, a balance, a scope, an expiry, a source, a variable name, a path, a fingerprint or the store kind.
There is no action field: nothing but reading exists, and reading never runs a check. The same projection serves Lampway's MCP server,
so an external AI app sees exactly what the main agent sees."""

import json

from .providers.base import ToolSpec

NAMES = {"lampway_connections"}
ALLOWED = ("id", "label", "state", "route_on", "usable", "checked_age_s", "next_step")
NOTE = "status only: identities, balances and secrets are the user's and are not shown to agents"
SCHEMA = {"type": "object", "additionalProperties": False, "properties": {
    "ids": {"type": "array", "items": {"type": "string"}, "maxItems": 40, "description": "connection ids (CATALOGUE.md); omit for all"},
    "for_use": {"type": "string", "description": "a tool, job service or Studio action id: answers which connection it needs and whether it is usable"}}}


def specs() -> list:
    return [ToolSpec("lampway_connections",
                     "Whether a service you want to use is connected and usable now (its credential works AND its privacy route is on), and the one "
                     "sentence to tell the user when it is not. Read-only: you cannot add, test, change, reveal or sign in to anything; the user does "
                     "that in Connections. Ask by `ids`, or by `for_use` (a tool, job service or Studio action id) to learn which connection it needs.",
                     SCHEMA)]


def _next_step(v: dict, usable: bool) -> str:
    """A fixed set of texts: the agent relays one sentence, never a path, a variable name or a provider message."""
    label, state = v["label"], v["state"]
    if usable:
        return f"{label} is ready to use"
    if state == "connected":
        return f"{label} is connected but its route is off: switch it on in Privacy"
    return {"missing": f"{label} is not connected: connect it in Connections",
            "signed_out": f"{label} is signed out: sign in again in Connections",
            "expired": f"{label} refused its credential: reconnect it in Connections",
            "error": f"{label} has a problem: open Connections to fix it",
            "not_checked": f"{label} is set up but not checked yet: press Test in Connections"}.get(state, f"{label}: open Connections")


def project(v: dict) -> dict:
    route_on = bool((v.get("route") or {"on": True}).get("on"))
    usable = v["state"] == "connected" and route_on
    return {"id": v["id"], "label": v["label"], "state": v["state"], "route_on": route_on, "usable": usable,
            "checked_age_s": v.get("check_age_s"), "next_step": _next_step(v, usable)}


def answer(arguments: dict) -> dict:
    from .. import connections as C
    from ..connections import registry as R
    args = arguments if isinstance(arguments, dict) else {}
    extra = set(args) - set(SCHEMA["properties"])
    if extra:
        raise ValueError(f"unknown field {sorted(extra)[0]!r}: this tool only reads (ids or for_use); there is no action")
    if args.get("ids") and args.get("for_use"):
        raise ValueError("ask by ids or by for_use, not both")
    if args.get("for_use"):
        cid = R.connection_for(str(args["for_use"]))
        if cid is None:
            raise ValueError(f"{args['for_use']} needs no connection Lampway knows of (the uses are {', '.join(R.known_uses())})")
        ids = [cid]
    else:
        ids = [str(i) for i in (args.get("ids") or [])][:40] or None
    return {"connections": [project(v) for v in C.active().view(ids)], "note": NOTE}


def refusal(exc) -> tuple:
    """The tool result every OTHER tool gives when its connection is not usable: the fixed text and ``needs_connection`` for the card."""
    return json.dumps({"error": str(exc), "needs_connection": exc.needs_connection}), True


async def call(name: str, arguments: dict) -> tuple:
    from .. import connections as C
    try:
        return json.dumps(answer(arguments)), False
    except (ValueError, C.Refused) as exc:
        return str(exc), True
