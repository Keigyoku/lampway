# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared by the spend card states (facelift contract 13): a pending Higgsfield spend the agent planned, the caps from a
fake /app/spend answer, and the card opened the way the Studios panel opens it. Nothing reaches a server."""

import sys

SETTLE_TICKS = 12
APPROVAL = {"id": "a1", "action": "higgsfield.job", "studio": "higgsfield", "label": "Higgsfield video: a 5-second loop of the lantern, 720p",
            "price": 18.0, "settings": {"unit": "credits"}, "requested_by": "agent", "state": "pending", "expires": 4e9, "job_id": "j9"}
SPEND = {"scope": "day", "providers": [{"provider": "higgsfield", "unit": "credits", "spent": 31.5, "day_cap": 200.0,
                                            "job_cap": 40.0, "click": "always", "above": None}]}


def open_card(bpy, state="", message=""):
    from mixar.modules.lampway_tools import statusbar_state, studio_state
    statusbar = sys.modules["mixar.modules.lampway_tools.ui.statusbar"]
    if bpy.app.timers.is_registered(statusbar._tick):
        bpy.app.timers.unregister(statusbar._tick)
    studio_state.STATE.update(approvals=[APPROVAL], actions=[], jobs=[], engine={}, error="")
    statusbar_state.update(egress={"routes": []}, spend=SPEND, studio={"approvals": [APPROVAL]})
    win = bpy.context.window_manager.windows[0]
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in view.regions if r.type == 'WINDOW')

    def pop():
        with bpy.context.temp_override(window=win, area=view, region=region):
            bpy.ops.lampway.studio_confirm('INVOKE_DEFAULT', approval_id="a1", price=18.0, label=APPROVAL["label"], unit="credits",
                                           state=state, message=message)
        return None

    bpy.app.timers.register(pop, first_interval=0.5)


def surfaces(bpy, dump):
    popup = [w for w in dump["widgets"] if w.get("popup")]
    out = {}
    title = next((w for w in popup if (w.get("text") or "").startswith(("Higgsfield video", "Refused", "Past the", "Past today", "The price", "Agents can", "Spent:"))), None)
    if title:
        x0, y0, x1, y1 = title["rect"]
        out["card_rule"] = (x0 + 1, (y0 + y1) // 2, 1)                 # the 4 px left rule (nearest pixel in a 3x3 box)
    spend = next((w for w in popup if w.get("op") == "LAMPWAY_OT_studio_confirm"), None)
    if spend:
        x0, y0, x1, y1 = spend["rect"]
        out["spend_bed"] = (x0 + 6, (y0 + y1) // 2)
    return out


def regions(bpy):
    return {}


def facts(bpy, dump):
    popup = [w for w in dump["widgets"] if w.get("popup")]
    return {"texts": [w.get("text") for w in popup if w.get("text")],
            "spend": [(w.get("text"), w.get("enabled")) for w in popup if w.get("op") == "LAMPWAY_OT_studio_confirm"],
            "variants": [w.get("mixar_variant") for w in popup if w.get("op") == "LAMPWAY_OT_studio_confirm"]}
