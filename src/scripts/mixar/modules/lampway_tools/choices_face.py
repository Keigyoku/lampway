# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Choices window says (specs/choices/choices_face.md). No bpy, no network: it reads the cached GET /app/choices
summaries and GET /app/choices/{purpose} views.

    cue(summary, waiting)   the purpose's diamond and reason word; the one glow is a proposal waiting for you
    option_row(option)      an option's six facts: where it runs, its connection's glyph, cost (hover), retention,
                            quality, and, when it is skipped, the reason and the one fix (Open in Privacy, Connect <label>)
    action(summary, ...)    the one action that clears the purpose's state
A connection is its state word only (the Connections allow-list): no identity, balance or credential is read here."""

CUE = {"preferred": ("choice_preferred", "preferred"), "fallback": ("choice_fallback", "fallback"),
       "override": ("choice_override", "this project"), "blocked": ("choice_blocked", "nothing can run"),
       "unset": ("choice_unset", "not chosen yet")}
CONNECTION_GLYPH = {"connected": "conn_connected", "not_checked": "conn_unchecked", "signed_out": "conn_signed_out",
                    "expired": "conn_expired", "missing": "conn_missing", "error": "conn_error"}
# The hub's words (choices/resolver.py _retention and the registry's facts): local, zdr, conditional, retains, unknown.
RETENTION = {"local": ("LAMPWAY_LAMP", "runs on this machine: nothing is kept anywhere else"),
             "zdr": ("LAMPWAY_SHIELD", "zero retention: the provider keeps nothing"),
             "conditional": ("LAMPWAY_SHIELD_HALF", "kept unless the call carries the route's private-content flags"),
             "retains": ("eye", "kept by the provider: terms unread"),
             "unknown": ("eye", "kept by the provider: terms unread")}


def kept(retention: str) -> bool:
    """An option whose provider may keep what it is sent: private content to it needs your acknowledgement (CH1)."""
    return retention in ("retains", "unknown")
PER = {"image": "an image", "second": "a second", "job": "a job", "call": "a call", "1k tokens": "per 1k tokens"}


def cue(summary: dict, waiting) -> dict:
    if summary.get("id") in (waiting or set()):
        return {"glyph": "conn_waiting", "word": "an agent proposal waits for you", "glows": True}
    state = summary.get("cue") or ""
    glyph, word = CUE.get(state, ("choice_blocked", f"unknown state: {state}"))
    why = summary.get("why")
    if state == "fallback" and why:
        word = f"fallback: {why}"
    elif state == "blocked" and why:
        word = f"nothing can run: {why}"
    elif state == "override":
        scope = (summary.get("now") or {}).get("scope") or "project"
        word = {"project": "this project", "job": "this job", "env": "this session (environment)"}.get(scope, f"this {scope}")
    return {"glyph": glyph, "word": word, "glows": False}


def now_line(summary: dict) -> str:
    now = summary.get("now")
    if not now:
        return "Now: nothing"
    provider = str(now.get("option") or "").split(":", 1)[0]
    return f"Now: {now.get('label') or now.get('option')}, {provider}"


def _cost(cost: dict) -> str:
    cost = cost or {}
    if cost.get("basis") == "free":
        return "costs nothing"
    if cost.get("amount") is None:
        return "cost unknown"
    amount = f"${float(cost['amount']):.2f}" if (cost.get("unit") or "USD").upper() == "USD" else f"{cost['amount']:g} {cost.get('unit')}"
    per = PER.get(cost.get("per") or "", f"per {cost.get('per')}" if cost.get("per") else "")
    when = f", {cost.get('basis') or 'estimated'} {cost['measured_at']}" if cost.get("measured_at") else f", {cost.get('basis') or 'estimated'}"
    return f"{amount} {per}{when}".replace("  ", " ")


def option_row(option: dict) -> dict:
    route = option.get("route") or None
    runs = option.get("runs") or ""
    local = runs == "this machine" or not route
    conn = option.get("connection") or None
    retention, retention_tip = RETENTION.get(option.get("retention") or "", ("LAMPWAY_SHIELD_UNKNOWN", "retention unknown"))
    quality = ", ".join(f"{q['metric']} {q['value']:g}" for q in option.get("quality") or [] if q.get("value") is not None)
    out = {"id": option.get("id"), "name": option.get("label") or option.get("id"), "rank": option.get("rank"),
           "runs": {"icon": "LAMPWAY_LAMP", "text": "this machine"} if local else {"icon": "LAMPWAY_WIRE", "text": runs},
           "connection": CONNECTION_GLYPH.get((conn or {}).get("state"), "") if conn else "",
           "connection_tip": f"{(conn or {}).get('id')}: {(conn or {}).get('state')}" if conn else "no account needed",
           "cost_tip": _cost(option.get("cost")), "retention": retention, "retention_tip": retention_tip, "quality": quality,
           "skipped": "", "fix": None, "ack": None}
    if option.get("acknowledged"):
        day = str(option["acknowledged"])[:10]
        out["ack"] = {"glyph": "eye", "tip": f"You allowed private content here on {day} (terms unread): click to take it back"}
    if option.get("verdict") == "skipped":
        skipped = option.get("skipped") or {}
        out["skipped"] = skipped.get("text") or "skipped"
        if skipped.get("constraint") == "route":
            out["fix"] = {"label": "Open in Privacy", "op": "lampway.privacy_open"}
        elif skipped.get("constraint") == "connection" and conn:
            out["fix"] = {"label": f"Connect {option.get('label') or conn.get('id')}", "op": "lampway.connections_open", "connection": conn.get("id")}
    return out


def action(summary: dict, proposal: bool, chain=None):
    """The one action that clears the state, or None when nothing waits."""
    if proposal:
        return {"label": "Accept for this project", "op": "lampway.choices_proposal_accept"}
    state = summary.get("cue")
    if state == "unset":
        return {"label": "Choose", "op": "lampway.choices_select"}
    if state in ("fallback", "blocked"):
        for o in chain or []:
            fix = option_row(o)["fix"]
            if fix:
                return fix
    return None


def proposal_line(p: dict) -> str:
    """The proposal card's line from the hub's row ({change: {preferred, fallbacks, params}, reason, origin})."""
    change = p.get("change") or {}
    what = change.get("preferred") or "new settings"
    who = "The agent" if str(p.get("origin") or "agent") != "user" else "You"
    return f"{who} proposes {what}: {p.get('reason') or ''}".rstrip(": ")
