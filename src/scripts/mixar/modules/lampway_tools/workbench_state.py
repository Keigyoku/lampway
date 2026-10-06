# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the cockpit panel shows: the last /app/workbench snapshot. One writer (the refresh operator), many readers; draw() reads this and never the network."""

STATE = {"server": {}, "sessions": [], "offered": [], "error": "", "terminal": {}}


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


SPARK = {"working": "agent_working", "waiting": "agent_blocked", "unread": "agent_unread", "idle": "agent_idle", "ended": "agent_done"}


def spark(s: dict) -> str:
    """The Spark preview of a session row (facelift contract 10: the same states as the agent cards, contract 05)."""
    return SPARK[chips(s)[0]]


def page_url(server: str, token: str) -> str:
    """The cockpit window's page; the bearer rides in the fragment, which a browser never sends to a server."""
    from urllib.parse import quote
    return server.rstrip("/") + "/app/workbench/page#t=" + quote(token or "", safe="")


def beside(x: int, y: int, width: int, gap: int = 8) -> str:
    """WezTerm's --position for a window just right of Blender's (facelift contract 16)."""
    return f"{int(x) + int(width) + gap},{int(y)}"


def terminal_line() -> str:
    t = STATE.get("terminal") or {}
    if not t.get("installed"):
        mb = int(((t.get("pin") or {}).get("bytes") or 49505472) / 1e6)   # 49 505 472 bytes: "about 49 MB" (contract 16)
        return f"Lampway terminal: not installed (Get downloads about {mb} MB from github.com)"
    return "Lampway terminal: " + ("open" if t.get("window") == "re-adopted" else "installed, window closed")
