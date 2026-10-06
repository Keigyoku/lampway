# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""What the Privacy panel shows: the last /app/egress snapshot and the last log rows. One writer (the refresh operator and its timer), many readers; draw() reads this and never the network."""

STATE = {"routes": [], "indicator": {"over_the_wire": False, "active": [], "last": None}, "log": [], "error": ""}


def update(state: dict, log: list) -> None:
    STATE.update(routes=state.get("routes") or [], indicator=state.get("indicator") or {"over_the_wire": False, "active": [], "last": None}, log=list(log or []), error="")


def fail(message: str) -> None:
    STATE["error"] = message


def route_line(r: dict) -> str:
    return f"{r['label']}: {'ON' if r['enabled'] else 'OFF'}"


def policy_line(r: dict) -> str:
    return f"retention: {r['retention'][:70]} | training: {r['training'][:50]}"


def badge() -> str:
    ind = STATE["indicator"]
    return f"DATA LEAVING: {', '.join(ind.get('active') or [])}" if ind.get("over_the_wire") else "nothing is leaving this machine"
