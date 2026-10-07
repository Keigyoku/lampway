# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Capabilities page says (docs/reports/agent-modes-spec.md E2, "The interface"). No bpy, no network: it reads the rows of the
cached GET /app/capabilities answer (``capabilities_state``), so a draw never waits on the server.

    groups(rows)           the rows grouped by risk, in words, in the server's order
    line(row)              one row: label, sentence, on / off / waiting for a route, its routes and where to switch them, its approval
                           setting and its options (the terminal's backend)
    warning(row)           the one plain sentence shown before a capability that runs code or acts outside Lampway is turned on
    summary(rows)          "Agent can: scene, web, terminal": what is in force now, in short words
    proposal_cards(...)    an agent's open proposals as cards the user accepts or declines

A row is the server's: ``id label does risk enabled in_force why_not approval options chosen_options scope default routes``. Only those
keys are read."""

# The server's order (capabilities/__init__.py RISKS), named in the words a person uses.
RISK_ORDER = ("reads", "writes_project", "runs_code", "reaches_internet", "acts_outside", "spends_plan")
RISK_TITLE = {"reads": "Looks only", "writes_project": "Changes your project", "runs_code": "Runs code",
              "reaches_internet": "Reaches the internet", "acts_outside": "Acts outside Lampway", "spends_plan": "Plans paid work"}
WARNED = ("runs_code", "acts_outside")
APPROVAL_LABEL = (("none", "Never asks"), ("ask_each_time", "Asks every time"), ("ask_once_per_session", "Asks once per session"))
# What an option is called on the page, and the key the Client writes it under (the server keeps ``options`` as the Client sends it).
OPTION_KEY = {"terminal": "backend"}
OPTION_LABEL = {"backend": "Where commands run"}
BACKEND_WORD = {"local": "this computer", "docker": "Docker", "ssh": "ssh", "modal": "Modal"}
LOCAL_TERMINAL = "Commands run on this computer as you."
# The route ids the server names, in words. An id nobody listed here shows as it is.
ROUTE_WORD = {"web:any": "web (any site)", "web_search": "web search"}
ROUTES_FIX = {"label": "Open Routes", "op": "lampway.privacy_open"}
# The page's one-word names for the summary; a family member (messaging.telegram) takes its family's.
SHORT = {"scene.read": "scene", "scene.edit": "scene", "ui.control": "interface", "files.project": "files", "terminal": "terminal",
         "code.execute": "code", "web.search": "web", "web.browse": "web", "vision": "images", "memory": "memory", "history.search": "history",
         "skills.use": "skills", "skills.write": "skill writing", "subagents": "helpers", "swarm": "workers", "schedule": "schedule",
         "computer.use": "desktop", "messaging.*": "messaging", "mcp.*": "MCP servers", "studio.plan": "studios", "panes.drive": "panes"}


def route_word(route_id: str) -> str:
    return ROUTE_WORD.get(route_id, route_id)


def risk_title(risk: str) -> str:
    return RISK_TITLE.get(risk) or str(risk).replace("_", " ").capitalize()


def groups(rows) -> list:
    """[{risk, title, rows}] for the risks that have rows: the server's order, then any risk it added since, each in the rows' own order."""
    seen = {}
    for r in rows or []:
        seen.setdefault(r.get("risk") or "", []).append(r)
    order = [k for k in RISK_ORDER if k in seen] + [k for k in seen if k not in RISK_ORDER]
    return [{"risk": k, "title": risk_title(k), "rows": seen[k]} for k in order]


def _backend(row: dict) -> str:
    key = OPTION_KEY.get(row.get("id"), "")
    chosen = (row.get("chosen_options") or {}).get(key) if key else None
    return chosen or (row.get("options") or [""])[0]


def needs_confirm(row: dict) -> bool:
    """Turning this on shows its warning first: it runs code or acts outside Lampway."""
    return row.get("risk") in WARNED


def warning(row: dict) -> str:
    """The one plain sentence naming what the capability allows ('' when it needs none). The local terminal is the user's own words from the
    spec; any other is the server's sentence for it, so a backend is never said to run where it does not."""
    if not needs_confirm(row):
        return ""
    if row.get("id") == "terminal" and _backend(row) in ("local", ""):
        return LOCAL_TERMINAL
    does = str(row.get("does") or row.get("label") or row.get("id") or "").strip().rstrip(".")
    return f"This lets your agent {does[:1].lower() + does[1:]}." if does else ""


def _routes(row: dict) -> list:
    return [{"id": r["id"], "name": route_word(r["id"]), "on": bool(r.get("on"))} for r in row.get("routes") or []]


def _route_note(routes: list) -> str:
    off = [r["name"] for r in routes if not r["on"]]
    if not off:
        return ""
    return f"Needs the {', '.join(off)} route{'s' if len(off) > 1 else ''}, which {'are' if len(off) > 1 else 'is'} off"


def line(row: dict) -> dict:
    """One row of the page. ``state`` is on (in force), waiting (chosen, but a route it needs is off) or off."""
    enabled = bool(row.get("enabled"))
    state = "off" if not enabled else "on" if row.get("in_force") else "waiting"
    routes = _routes(row)
    note = _route_note(routes)
    cid = row.get("id") or ""
    options = None
    if row.get("options"):
        key = OPTION_KEY.get(cid, "choice")
        current = _backend(row) if cid in OPTION_KEY else ((row.get("chosen_options") or {}).get(key) or row["options"][0])
        options = {"key": key, "label": OPTION_LABEL.get(key, "Option"),
                   "choices": [{"value": o, "label": BACKEND_WORD.get(o, o) if key == "backend" else o, "on": o == current} for o in row["options"]]}
    approval = row.get("approval") or "none"
    return {"id": cid, "label": row.get("label") or cid, "does": row.get("does") or "", "state": state,
            "word": {"on": "On", "off": "Off", "waiting": "Waiting for a route"}[state], "enabled": enabled,
            "scope_tag": "this project" if row.get("scope") == "project" else "",
            "routes": routes, "route_note": note, "route_fix": dict(ROUTES_FIX) if note else None,
            "approval": {"current": approval, "choices": [{"value": v, "label": w, "on": v == approval} for v, w in APPROVAL_LABEL]},
            "options": options}


def summary(rows) -> str:
    """'Agent can: scene, images, web' - the capabilities in force, once each, in the catalogue's order."""
    said = []
    for r in rows or []:
        if not (r.get("enabled") and r.get("in_force")):
            continue
        cid = str(r.get("id") or "")
        word = SHORT.get(cid) or SHORT.get(cid.partition(".")[0] + ".*") or r.get("label") or cid
        if word not in said:
            said.append(word)
    return "Agent can: " + (", ".join(said) if said else "nothing")


def proposal_cards(proposals, rows, dismissed=()) -> list:
    """[{pid, id, line, warning, put}] for the proposals still waiting: open, not hidden here, and not already the state they ask for.
    ``put`` is the body the Client sends when the user accepts (the proposal's own change)."""
    by_id = {r.get("id"): r for r in rows or []}
    out = []
    for p in proposals or []:
        if p.get("state") != "open" or p.get("pid") in (dismissed or ()):
            continue
        change = p.get("change") or {}
        row = by_id.get(p.get("id"))
        want = change.get("enabled")
        if row is not None and want is not None and bool(row.get("enabled")) == bool(want):
            continue
        put = {k: change[k] for k in ("enabled", "approval", "options") if k in change}
        name = (row or {}).get("label") or p.get("id") or "a capability"
        turn = "" if want is None else f" to turn {'on' if want else 'off'}"
        reason = str(p.get("reason") or "").strip()
        said = f"The agent asks{turn} {name}" if turn else f"The agent asks to change {name}"
        # A member of a family (messaging.telegram) has no row of its own: it is warned by its family's, so the card never turns on less than it says.
        family = row or by_id.get(str(p.get("id") or "").partition(".")[0] + ".*")
        out.append({"pid": p.get("pid"), "id": p.get("id"), "put": put, "line": said + (f": {reason}" if reason else ""),
                    "warning": warning(family) if family is not None and want else ""})
    return out
