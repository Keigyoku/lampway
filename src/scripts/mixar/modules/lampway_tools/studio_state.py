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


def questions() -> list:
    """Pending questions for the captain (e.g. Higgsfield's unlim_choice): an answer, not a spend."""
    return [a for a in STATE["approvals"] if a.get("state") == "pending" and (a.get("settings") or {}).get("unit") == "answer"]


def pending() -> list:
    """Pending SPENDS: approvals that are not questions."""
    return [a for a in STATE["approvals"] if a.get("state") == "pending" and (a.get("settings") or {}).get("unit") != "answer"]


def busy() -> bool:
    return bool(pending()) or bool(questions()) or any(j.get("state") == "running" for j in STATE["jobs"])
