# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Studios panel shows: the last /app/studio snapshot. One writer (the refresh operator and the poll timer), many readers."""

PROVIDERS = {}          # the last GET /app/provider-settings: {values, source, choices}
STATE = {"actions": [], "approvals": [], "jobs": [], "engine": {}, "error": ""}


def update(home: dict) -> None:
    STATE.update(actions=home.get("actions") or [], approvals=home.get("approvals") or [], jobs=home.get("jobs") or [],
                 engine=home.get("engine") or {}, error="")


def fail(message: str) -> None:
    STATE["error"] = message


def pending() -> list:
    return [a for a in STATE["approvals"] if a.get("state") == "pending"]


def busy() -> bool:
    return bool(pending()) or any(j.get("state") == "running" for j in STATE["jobs"])
