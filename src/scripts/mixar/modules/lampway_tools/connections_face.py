# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Connections window says (specs/connections/connections_face.md). No bpy, no network: it reads the cached
GET /app/connections views. It reads only the fields named in ``READ`` (and inside them only the named keys), so a field
a future server adds - or one that should never have been there - cannot reach a draw.

    cue(view)          the connection glyph (a colour-baked preview) and its word; route_off is NOT part of it
    route_cell(view)   the route column: the wire when the route is on, nothing when off; the word on hover
    glows(view, waiting)  only a sign-in waiting for the browser is lit
    action(view)       the one action that clears the state (tier 1)
    groups(views)      the list: Agents, Studios, Video and images, Compute, Your tools, then any other group
    detail(view)       tiers 1-2 of the right side: name, state, source line, identity, expiry, next step
"""

GROUP_ORDER = ("Agents", "Studios", "Video and images", "Compute", "Your tools")
CUES = {"connected": ("conn_connected", "connected"), "not_checked": ("conn_unchecked", "not checked"),
        "signed_out": ("conn_signed_out", "signed out"), "expired": ("conn_expired", "expired"),
        "missing": ("conn_missing", "not connected"), "error": ("conn_error", "error")}
SOURCE_WORD = {"host": "your login", "signin": "your login", "manual": "keyring", "env": "environment", "pointer": "file", "auto": "found on this machine"}
READ = ("id", "label", "group", "kind", "state", "qualifiers", "route", "active_source", "identity", "expires_at", "check_age_s",
        "fingerprint", "next_step", "conflict")
SCRIPT_REFUSAL = "this is the user's click: a script cannot press it"


def _get(view, key, default=None):
    if key not in READ:
        raise KeyError(f"connections_face reads no {key!r}")
    value = view.get(key)
    return default if value is None else value


def cue(view) -> dict:
    state = _get(view, "state", "")
    if state == "connected" and "warning" in _get(view, "qualifiers", []):
        return {"glyph": "conn_warning", "word": "connected, with a warning"}
    glyph, word = CUES.get(state, ("conn_error", f"unknown state: {state}"))
    return {"glyph": glyph, "word": word}


def route_cell(view) -> dict:
    route = _get(view, "route", {}) or {}
    rid = route.get("id") or ""
    if not rid:
        return {"icon": "", "tooltip": "no route: nothing leaves this machine for it"}
    if route.get("on"):
        return {"icon": "LAMPWAY_WIRE", "tooltip": f"route on: {rid} (data may leave for it)"}
    return {"icon": "", "tooltip": f"route off: {rid} (switch it on in Privacy to use it)"}


def glows(view, waiting) -> bool:
    return _get(view, "id") in (waiting or set())


def action(view) -> dict:
    state, kind, label = _get(view, "state", ""), _get(view, "kind", ""), _get(view, "label", "")
    if state in ("signed_out", "expired") or (state == "missing" and kind == "oauth"):
        return {"label": f"Sign in with {label}", "op": "lampway.connections_sign_in"}
    if state == "missing":
        return {"label": "Paste a key", "op": "lampway.connections_select_mode", "mode": "manual"}
    return {"label": "Test", "op": "lampway.connections_test"}


def _age(seconds) -> str:
    if seconds is None:
        return "never checked"
    s = int(seconds)
    if s < 90:
        return "checked now"
    if s < 3600:
        return f"checked {round(s / 60)} min ago"
    return f"checked {round(s / 3600)} h ago"


def _source_word(view) -> str:
    src = _get(view, "active_source", {}) or {}
    return SOURCE_WORD.get(src.get("mode"), src.get("label") or "no source")


def groups(views) -> list:
    """[(group, [row])] with row = {id, name, glyph, word, route_icon, tooltip}."""
    by = {}
    for v in views or []:
        c, r = cue(v), route_cell(v)
        by.setdefault(_get(v, "group", "Other"), []).append(
            {"id": _get(v, "id"), "name": _get(v, "label", _get(v, "id")), "glyph": c["glyph"], "word": c["word"], "route_icon": r["icon"],
             "tooltip": f"{c['word']}; {_source_word(v)}; {_age(_get(v, 'check_age_s'))}; {r['tooltip']}"})
    order = [g for g in GROUP_ORDER if g in by] + sorted(g for g in by if g not in GROUP_ORDER)
    return [(g, by[g]) for g in order]


def _fingerprint(view) -> str:
    fp = _get(view, "fingerprint", {}) or {}
    return f"•••• {fp['last4']}" if fp.get("last4") else ""


def detail(view) -> dict:
    c = cue(view)
    src = _get(view, "active_source", {}) or {}
    ident = _get(view, "identity", {}) or {}
    line = f"from {src.get('label') or 'nowhere yet'}"
    fp = _fingerprint(view)
    if fp:
        line = f"{fp}, {src.get('label') or 'kept by Lampway'}"
    who = ", ".join(x for x in (ident.get("masked"), ident.get("plan"), ident.get("tier")) if x)
    bal = ident.get("balance") or {}
    balance = f"{bal.get('amount')} {bal.get('unit') or ''}".strip() if bal.get("amount") is not None else ""
    return {"name": _get(view, "label", _get(view, "id")), "glyph": c["glyph"], "word": c["word"], "action": action(view),
            "source": line, "identity": who, "balance": balance, "expires": _get(view, "expires_at", "") or "",
            "next_step": _get(view, "next_step", "") or "", "conflict": _get(view, "conflict", "") or "", "foot": _foot(view)}


def _foot(view) -> list:
    """Sign out for a login Lampway holds; Forget for a key or pointer Lampway holds; nothing for what it only reads."""
    mode = (_get(view, "active_source", {}) or {}).get("mode")
    if _get(view, "state") == "missing":
        return []
    if _get(view, "kind") == "oauth" and mode == "signin":
        return ["sign_out"]
    if mode in ("manual", "pointer"):
        return ["forget"]
    return []
