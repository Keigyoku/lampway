# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Connections panel shows: the last /app/mcp/inventory snapshot. One writer (refresh and check), many readers; draw() reads this and never the network."""

STATE = {"servers": [], "problems": [], "lampway": {}, "error": ""}


def update(inv: dict) -> None:
    STATE.update(servers=inv.get("servers") or [], problems=inv.get("problems") or [], lampway=inv.get("lampway") or {}, error="")


def fail(message: str) -> None:
    STATE["error"] = message


def set_connection(server_id: str, connection: dict) -> None:
    for s in STATE["servers"]:
        if s["id"] == server_id:
            s["connection"] = connection


def lampway_line() -> str:
    l = STATE["lampway"]
    if not l:
        return "Lampway: not scanned yet"
    elig = "eligible" if l.get("eligible") else f"not eligible ({l.get('eligibility_detail') or 'unknown'})"
    return f"Lampway: launcher {l.get('launcher') or 'not found'}, {l.get('tools_offered', 0)} tools, {elig}"


def card_line(s: dict) -> str:
    return f"{s['client']} / {s['name']}: {s['readiness']} ({s['scope']})"


def connection_line(s: dict) -> str:
    c = s.get("connection")
    if not c:
        return "not checked"
    n = "" if c.get("tool_count") is None else f", {c['tool_count']} tools"
    return f"{c['status']}{n}" + (" (stale)" if c.get("stale") else "")
