# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the next chat message goes (facelift contract 04): the host beside Send, the full sentence as its hover, and
whether Send may be pressed. No bpy, no network: it reads the egress answer the status bar already holds. It names the
kinds of content a message carries, never the content."""

from .onboarding import PROVIDER_ROUTE

OFF = "Your next message cannot leave: the agent's provider is off in Privacy"
PLAN_ROUTES = {"chatgpt_plan", "claude_plan"}


def _carries(content: dict) -> str:
    words = [word for key, word in (("text", "text"), ("names", "object names"), ("transforms", "transforms")) if content.get(key)]
    images = int(content.get("images") or 0)
    if images:
        words.append(f"{images} image{'s' if images != 1 else ''}")
    said = words[0] if len(words) == 1 else ", ".join(words[:-1]) + " and " + words[-1] if words else "nothing"
    return said + ("." if images else ". No images attached.")


def route_line(provider: str, egress, content: dict) -> dict:
    """{host, send_ok, tooltip} for the active main provider and the last /app/egress answer (None when unknown)."""
    if egress is None or not provider:
        # Not known (the server is not answering, or has not said which provider is the agent's): say so, never guess.
        return {"host": "", "send_ok": True, "tooltip": "Lampway's server is not answering: where the message goes is unknown"}
    route = PROVIDER_ROUTE.get(provider)
    if route is None:
        return {"host": "this machine", "send_ok": True, "tooltip": "Your next message stays on this machine: " + _carries(content)}
    row = next((r for r in egress.get("routes") or [] if r.get("id") == route), None)
    if row is None or not row.get("enabled"):
        return {"host": "", "send_ok": False, "tooltip": OFF}
    host = (row.get("hosts") or [row.get("label") or route])[0]
    how = "on your plan" if route in PLAN_ROUTES else f"with your {row.get('label') or route} key"
    return {"host": host, "send_ok": True, "tooltip": f"Your next message goes to {host} {how}: " + _carries(content)}
