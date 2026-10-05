# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""Which backend tools an MCP session lists, and the status mixar_ui_context reports.

An AI app asks for tools once, when it connects. Every tool is listed up front:
the live backend list when Mixar is ready, otherwise the copy the app saved
while signed in (tool_snapshot). Nothing waits for Mixar. A call made before
Mixar is ready returns why (sign in, connecting, not open) and the agent tries
again; mixar_ui_context reports the same as ``scene_tools`` + ``next_step``.
"""

import asyncio

from . import tool_snapshot

CATALOG_TIMEOUT_SECONDS = 7

RECONNECT = ("ask the user to reconnect the Lampway MCP server (Claude Code: /mcp, then reconnect lampway; "
             "Codex: start a new session)")
NEXT_STEPS = {
    "available": "",
    "reconnect": "The scene tools were not available when this session started; " + RECONNECT + ".",
    "signed_out": "Ask the user to sign in to Lampway, then try again.",
    "starting": "Lampway is starting; wait a moment and try again.",
    "absent": "Lampway is not open; ask the user to open Lampway and sign in, then try again.",
    "connecting": "Lampway is signed in but still connecting to its server; wait a moment and try again.",
    "choose": "Several Lampway apps are open; call mixar_ui_context with one of their instance ids.",
    "closed": "The Lampway app this connection used was closed; call mixar_ui_context to choose a running one.",
}


async def fetch_tools(connector):
    """(backend tools or None, readiness): live when Mixar is ready, else the saved copy."""
    check = getattr(connector, "readiness", lambda: ("ready", ""))
    state, _ = await asyncio.to_thread(check)
    if state == "ready":
        try:
            tools = await asyncio.wait_for(asyncio.to_thread(connector.catalog), CATALOG_TIMEOUT_SECONDS)
        except (OSError, ValueError, KeyError, RuntimeError, TimeoutError):
            state = "connecting"
        else:
            await asyncio.to_thread(tool_snapshot.save, tools)  # The freshest list for the next session.
            return tools, state
    return await asyncio.to_thread(tool_snapshot.load), state


def scene_tools(listed, readiness, health):
    """Is scene work possible in this session, and if not, what should the user do?"""
    if readiness == "ready" and not health.get("connected"):
        status = "connecting"
    elif readiness == "ready":
        status = "available" if listed else "reconnect"
    else:
        status = readiness
    return {"scene_tools": status, "next_step": NEXT_STEPS.get(status, "")}
