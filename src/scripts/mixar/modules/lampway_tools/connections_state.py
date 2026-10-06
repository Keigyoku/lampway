# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Connections window shows: the last GET /app/connections answer, the selected row, the rows whose sign-in
waits for the browser, and the last refusal per row. One writer (the window's operators and its timer), many readers;
draw() reads this and never the network."""

import time

STATE = {"ok": False, "error": "", "store": {}, "connections": [], "as_of": 0.0, "selected": "", "detail": {}, "waiting": set(),
         "refusal": {}}


def update(listing: dict) -> None:
    STATE.update(ok=True, error="", store=listing.get("store") or {}, connections=list(listing.get("connections") or []), as_of=time.time())


def put_view(view: dict) -> None:
    """A write's answer is the row's new view: it replaces the cached row."""
    rows = STATE["connections"]
    for n, row in enumerate(rows):
        if row.get("id") == view.get("id"):
            rows[n] = {k: v for k, v in view.items() if k not in ("sources", "uses", "history")}
            return
    rows.append(view)


def fail(message: str) -> None:
    STATE.update(ok=False, error=message)


def selected() -> dict:
    return next((v for v in STATE["connections"] if v.get("id") == STATE["selected"]), {})
