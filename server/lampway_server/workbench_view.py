"""What the cockpit window shows (facelift contract 10 over specs/mrmak/01): one row per session with its Spark state and
what the page may offer on it, and the sentence a restart's reconcile owes the user. Computed here, drawn by the page
(web/workbench/cockpit.js), so the rule "a pane Lampway did not create gets nothing to type into and nothing to stop" is
the server's, not the page's."""

SPARK = ("working", "waiting", "unread", "idle", "ended")


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def banner(reconcile):
    """{text, tooltip} for the last reconcile, or None before one ran."""
    if not reconcile:
        return None
    n, u = len(reconcile.get("adopted") or []), len(reconcile.get("unadopted") or [])
    text = f"{n} {_plural(n, 'session', 'sessions')} re-adopted with {_plural(n, 'its', 'their')} state."
    if u:
        text += f" {u} {_plural(u, 'pane is', 'panes are')} not ours: left running, never typed into."
    ended = len(reconcile.get("ended") or [])
    tip = text + (f" {ended} ended while Lampway was away: listed, never restarted." if ended else "") + " Nothing was restarted, nothing was killed."
    return {"text": text, "tooltip": tip}


def _spark(s: dict) -> str:
    if s.get("state") == "ended":
        return "ended"
    if s.get("activity") in ("working", "waiting"):
        return s["activity"]
    return "unread" if s.get("unread") else "idle"


def view(home: dict, reconcile=None) -> dict:
    rows = []
    for s in (home or {}).get("sessions") or []:
        live = s.get("state") == "live"
        rows.append({"id": s["id"], "name": s.get("name") or s["id"], "agent": s.get("agent") or "", "folder": s.get("cwd") or "",
                     "state": s.get("state") or "", "spark": _spark(s), "adopted": True, "can_type": live, "can_stop": live,
                     "agent_sends": bool(s.get("agent_sends", False))})
    for pane in (reconcile or {}).get("unadopted") or []:
        rows.append({"id": str(pane), "name": f"pane {pane}", "agent": "", "folder": "", "state": "not adopted", "spark": "idle",
                     "adopted": False, "can_type": False, "can_stop": False, "agent_sends": False})
    return {"server": (home or {}).get("server") or {}, "rows": rows, "banner": banner(reconcile)}
