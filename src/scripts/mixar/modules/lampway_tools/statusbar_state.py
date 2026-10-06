# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the status bar shows (facelift contract 03): the last /app/egress, /app/spend and /app/studio answers. One writer (the status timer in
ui/statusbar.py), one reader (its draw). No bpy and no network here: draw() must never wait on the server.

When the server cannot be reached the bar says so ("spend unknown: server not running", "egress unknown") and shows no number from before."""

STATE = {"ok": False, "error": "", "egress": {}, "spend": {}, "studio": {}}
FAST_S, SLOW_S = 0.5, 5.0


def reset() -> None:
    STATE.update(ok=False, error="", egress={}, spend={}, studio={})


def update(egress=None, spend=None, studio=None) -> None:
    for key, value in (("egress", egress), ("spend", spend), ("studio", studio)):
        if value is not None:
            STATE[key] = value
    STATE.update(ok=True, error="")


def fail(message: str) -> None:
    STATE.update(ok=False, error=message)


def _indicator() -> dict:
    return (STATE["egress"] or {}).get("indicator") or {}


def routes_on() -> list:
    return [r for r in (STATE["egress"] or {}).get("routes") or [] if r.get("enabled")]


def sending() -> bool:
    return bool(STATE["ok"] and _indicator().get("over_the_wire"))


def wire_chip() -> tuple:
    """(text, glyph, tooltip): local, N routes open, or Sending to <route>. The indicator is the truth: lit with no route named still sends."""
    if not STATE["ok"]:
        return "egress unknown", "wire", f"Lampway's server is not answering: {STATE['error'] or 'not running'}"
    if sending():
        labels = {r.get("id"): r.get("label") or r.get("id") for r in (STATE["egress"] or {}).get("routes") or []}
        active = [labels.get(a, a) for a in _indicator().get("active") or []]
        return ("Sending to " + ", ".join(active) if active else "Sending"), "wire_dot", "Data is leaving this machine now"
    on = routes_on()
    if on:
        return f"{len(on)} route{'s' if len(on) != 1 else ''} open", "wire", "Open: " + ", ".join(r.get("label") or r["id"] for r in on) + "; nothing is being sent"
    return "local", "lamp", "Nothing leaves this machine: every route is off"


def spend_line() -> tuple:
    """(text, meter step 0..10 or None, tooltip). Dollars against the cap the Providers dialog set; credits after them."""
    if not STATE["ok"]:
        return "spend unknown: server not running", None, STATE["error"]
    rows = (STATE["spend"] or {}).get("providers") or []
    usd = [r for r in rows if r.get("unit") == "USD"]
    spent = sum(float(r.get("spent") or 0) for r in usd)
    caps = [float(r["session_cap"]) for r in usd if r.get("session_cap")]
    credits = sum(float(r.get("spent") or 0) for r in rows if r.get("unit") == "credits")
    tip = ("Spent this server session (Lampway keeps no day total yet); caps and clicks are set in the Providers dialog")
    tail = f" + {credits:g} credits" if credits else ""
    if caps:
        cap = sum(caps)
        step = max(0, min(10, round(10 * spent / cap)))
        return f"${spent:.2f} of ${cap:.2f}{tail}", step, tip
    return f"${spent:.2f}{tail}", None, tip


def waiting() -> int:
    """Spends and questions that wait for the user's click."""
    if not STATE["ok"]:
        return 0
    return sum(1 for a in (STATE["studio"] or {}).get("approvals") or [] if a.get("state") == "pending")


def poll_interval() -> float:
    return FAST_S if routes_on() else SLOW_S
