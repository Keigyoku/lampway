# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the cockpit panel shows: the last /app/workbench snapshot. One writer (the refresh operator), many readers; draw() reads this and never the network."""

STATE = {"server": {}, "sessions": [], "offered": [], "error": ""}


def update(home: dict) -> None:
    STATE.update(server=home.get("server") or {}, sessions=home.get("sessions") or [], offered=home.get("offered") or [], error="")


def fail(message: str) -> None:
    STATE["error"] = message


def chips(s: dict) -> list:
    """The status chips of one session row: working / waiting / unread / ended, from the session record."""
    out = []
    if s.get("state") == "ended":
        return ["ended"]
    act = s.get("activity")
    if act in ("working", "waiting"):
        out.append(act)
    if s.get("unread"):
        out.append("unread")
    return out or ["idle"]


def summary_line() -> str:
    srv = STATE["server"]
    if not srv.get("running"):
        return "herdr server: not running (Start, or Resume sessions)"
    live = sum(1 for s in STATE["sessions"] if s.get("state") == "live")
    return f"herdr server: running ({srv.get('method') or '?'}), {live} live / {len(STATE['sessions'])} sessions"
