# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the status bar states: the bar fed from a fake server answer (the refresh timer is stopped, so nothing reaches the network)."""

ROUTES = [{"id": "openrouter", "label": "OpenRouter"}, {"id": "fal", "label": "fal.ai"}]
SPEND = {"scope": "day", "providers": [
    {"provider": "openrouter", "unit": "USD", "spent": 0.31, "day_cap": 5.0, "job_cap": 1.0, "click": "above", "above": 0.25},
    {"provider": "higgsfield", "unit": "credits", "spent": 0.0, "day_cap": None, "job_cap": None, "click": "always", "above": None}]}


def feed(bpy, on, sending, waiting):
    import sys
    statusbar = sys.modules["mixar.modules.lampway_tools.ui.statusbar"]
    from mixar.modules.lampway_tools import statusbar_state as S
    if bpy.app.timers.is_registered(statusbar._tick):
        bpy.app.timers.unregister(statusbar._tick)
    routes = [dict(r, enabled=r["id"] in on) for r in ROUTES]
    indicator = {"over_the_wire": bool(sending), "active": list(sending), "last": None}
    approvals = [{"id": "a1", "state": "pending", "label": "Tripo texture", "price": 30, "settings": {"unit": "credits"}}] if waiting else []
    S.update(egress={"routes": routes, "indicator": indicator}, spend=SPEND, studio={"approvals": approvals, "jobs": []})
    statusbar.sync_animation()


def facts(bpy, dump):
    ops = {"LAMPWAY_OT_status_waiting": "waiting", "LAMPWAY_OT_status_spend": "spend", "LAMPWAY_OT_status_wire": "wire"}
    out = {}
    for w in dump["widgets"]:
        if w.get("op") in ops:
            out[ops[w["op"]]] = w.get("text")
    return out


def _bar(bpy):
    """The status bar is a global area: ``Window.global_areas``, never ``screen.areas``."""
    win = bpy.context.window_manager.windows[0]
    return next(a for a in win.global_areas if a.type == 'STATUSBAR')


def regions(bpy):
    area = _bar(bpy)
    return {"statusbar": [area.x, area.y, area.x + area.width, area.y + area.height]}


def surfaces(bpy, dump):
    area = _bar(bpy)
    return {"statusbar_back": (area.x + 4, area.y + area.height // 2)}
