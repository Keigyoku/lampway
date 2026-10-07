# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the privacy face says (facelift contract 12). No bpy, no network: everything here reads the cached
/app/egress routes and log rows (egress_state), so a draw never waits on the server.

    chip        one vocabulary wherever a provider is named: the lamp and "this machine", or the wire and the host
    route_rows  a row per route: name, a shield for its privacy class, the switch (off, waiting for your confirm, on);
                host, last use and the policy on hover
    last_refusal  the most recent refusal and its ways forward
    log_rows    time, event, route, what; host, class and retention on hover. Only the keys named here are read, so a
                row the server would never send with content still renders none of it
"""

import time

SCRIPT_REFUSAL = "A script cannot open a route: switch it on in Privacy yourself"
SHIELD = {"ok": "LAMPWAY_SHIELD", "conditional": "LAMPWAY_SHIELD_HALF", "retains": "LAMPWAY_SHIELD_OPEN", "unknown": "LAMPWAY_SHIELD_UNKNOWN"}
EVENT_GLYPH = {"send": "LAMPWAY_WIRE", "refused": "LAMPWAY_GATE", "override": "LAMPWAY_HAND"}
EVENT_BED = {"send": "wire_bed", "refused": "stop_bed"}
PRIVATE_TITLE = "a private asset on a route that may keep it"
# "Run it here instead" opens Choices on the job's kind, where an option that runs on this machine can be put first.
KIND_GROUP = {"image": "images", "video": "video", "mesh": "3d", "text": "agents"}


def _route(route_id: str, routes):
    return next((r for r in routes or [] if r.get("id") == route_id), None)


def _host(row: dict) -> str:
    return (row.get("hosts") or [None])[0] or row.get("label") or row["id"]


def chip(route_id: str, routes) -> dict:
    """{icon, text, tone, tooltip} for a route id, or for ``local``. An id no table names is said, in stop: never blank."""
    if route_id == "local":
        return {"icon": "LAMPWAY_LAMP", "text": "this machine", "tone": "muted", "tooltip": "Runs on this machine: nothing leaves"}
    row = _route(route_id, routes)
    if row is None:
        if not routes:   # the table is not known yet (the server has not answered): the id, as it is
            return {"icon": "LAMPWAY_WIRE", "text": route_id, "tone": "muted", "tooltip": f"{route_id}: Lampway's server has not said where it goes"}
        return {"icon": "LAMPWAY_WIRE", "text": "unknown route", "tone": "stop", "tooltip": f"{route_id} is not a route Lampway knows: nothing is sent through it"}
    state = "on" if row.get("enabled") else "off"
    return {"icon": "LAMPWAY_WIRE", "text": _host(row), "tone": "muted", "tooltip": f"{row.get('label') or route_id} ({state}): {row.get('retention') or 'unknown'}"}


def _when(t) -> str:
    if not t:
        return "never used"
    return "last used " + time.strftime("%Y-%m-%d %H:%M", time.localtime(float(t)))


def route_rows(routes, pending: str = "") -> list:
    """[{id, name, shield, switch, confirm, tooltip}] in the server's order; ``pending`` is the route whose confirm row is open."""
    out = []
    for r in routes or []:
        switch = "on" if r.get("enabled") else "confirm" if r.get("id") == pending else "off"
        out.append({"id": r["id"], "name": r.get("label") or r["id"], "shield": SHIELD.get(r.get("privacy_class"), SHIELD["unknown"]),
                    "switch": switch, "confirm": f"Let data leave for {_host(r)}?",
                    "tooltip": f"{', '.join(r.get('hosts') or []) or 'no fixed host'}; {_when(r.get('last_used'))}. "
                               f"Retention: {r.get('retention') or 'unknown'}. Training: {r.get('training') or 'unknown'}"})
    return out


def last_refusal(log) -> dict:
    """The most recent refused row as a card {title, tooltip, route, ways}, or None."""
    row = next((r for r in reversed(list(log or [])) if r.get("event") == "refused"), None)
    if row is None:
        return None
    route, reason = row.get("route") or "", row.get("reason") or ""
    if "private" in reason:
        asset = (row.get("asset_ids") or [""])[0]
        ways = [{"label": "Use OpenRouter, zero retention", "action": "route_on", "route": "openrouter", "tone": "text"},
                {"label": "Run it here instead", "action": "local", "route": "local", "tone": "text", "op": "lampway.choices_open",
                 "group": KIND_GROUP.get(str(row.get("kind") or ""), "")},
                {"label": "Allow this asset once (logged)", "action": "override", "asset_id": asset, "route": route, "tone": "stop"}]
        return {"title": PRIVATE_TITLE, "tooltip": reason, "route": route, "ways": ways}
    if reason == "route off" or reason.startswith(f"{route} is off"):
        return {"title": f"{route} is off", "tooltip": f"{route} is off: switch it on in Privacy to let data leave", "route": route,
                "ways": [{"label": f"Switch {route} on", "action": "route_on", "route": route, "tone": "text"}]}
    return {"title": f"refused on {route or 'an unknown route'}", "tooltip": reason, "route": route, "ways": []}


def log_rows(log, routes=None) -> list:
    """[{time, event, glyph, route, what, tooltip, bed}] for the log view. Reads only the keys named here."""
    out = []
    for r in log or []:
        event = str(r.get("event") or "")
        kind = str(r.get("kind") or "request")
        nbytes = r.get("bytes")
        what = f"{kind}, {int(nbytes)} bytes" if isinstance(nbytes, (int, float)) and nbytes else kind
        tip = "; ".join(x for x in (f"host {r['provider']}" if r.get("provider") else "", f"class {r.get('content_class') or 'unclassified'}",
                                     f"retention {r['retention']}" if r.get("retention") else "") if x)
        out.append({"time": time.strftime("%H:%M:%S", time.localtime(float(r.get("t") or 0))), "event": event,
                    "glyph": EVENT_GLYPH.get(event, "LAMPWAY_WIRE"), "route": str(r.get("route") or ""), "what": what, "tooltip": tip,
                    "bed": EVENT_BED.get(event, "")})
    return out
