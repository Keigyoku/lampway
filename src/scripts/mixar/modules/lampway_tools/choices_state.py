# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Choices window shows: the last GET /app/choices answer, the selected purpose's view, the open proposals, the
last refusal per purpose. One writer (the window's operators and its timer), many readers; draw() reads this only.
``missing`` is a server that has no Choices yet (an HTTP 404): the window then offers the old Providers dialog."""

import os
import time

STATE = {"ok": False, "missing": False, "error": "", "groups": [], "as_of": 0.0, "group": "", "selected": "", "detail": {},
         "proposals": [], "refusal": {}, "project": os.environ.get("LAMPWAY_PROJECT_ROOT", "")}


def update(listing: dict, proposals: list) -> None:
    STATE.update(ok=True, missing=False, error="", groups=list(listing.get("groups") or []), proposals=list(proposals or []), as_of=time.time())


def fail(message: str) -> None:
    STATE.update(ok=False, error=message, missing="HTTP 404" in message)


def summaries() -> list:
    return [p for g in STATE["groups"] for p in g.get("purposes") or []]


def waiting() -> set:
    return {p.get("purpose") for p in STATE["proposals"] if p.get("state") == "open"}
