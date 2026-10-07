# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 12 in the window: "What leaves this machine" as the pop-out, with one route sending, one refused row in the
log (a private asset on fal.ai) and OpenRouter's confirm row open. Fake state: the refresh timers are stopped and the
cache is filled here, so nothing reaches a server."""

import sys

SETTLE_TICKS = 12
ROUTES = [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "retention": "per model", "training": "per model",
           "privacy_class": "conditional", "hosts": ["openrouter.ai"], "last_used": None},
          {"id": "fal", "label": "fal.ai", "enabled": True, "retention": "unknown (terms not read)", "training": "unknown",
           "privacy_class": "unknown", "hosts": ["fal.ai"], "last_used": 1.7e9},
          {"id": "model_download", "label": "Model weights download (Hugging Face)", "enabled": False, "retention": "no user content",
           "training": "n/a", "privacy_class": "ok", "hosts": ["huggingface.co"], "last_used": None}]
LOG = [{"t": 1.7e9, "event": "send", "route": "fal", "provider": "fal.ai", "kind": "image", "bytes": 1200, "content_class": "public"},
       {"t": 1.7e9 + 60, "event": "refused", "route": "fal", "kind": "image", "asset_ids": ["a1"], "content_class": "private",
        "reason": "this asset is private and fal.ai keeps what it is sent: use a verified route, run it locally, or flip the per-asset override (logged)"}]


def setup(bpy):
    from mixar.modules.lampway_tools import egress_state
    ops = sys.modules["mixar.modules.lampway_tools.ui.operators.egress_ops"]
    if bpy.app.timers.is_registered(ops._tick):
        bpy.app.timers.unregister(ops._tick)
    egress_state.update({"routes": ROUTES, "indicator": {"over_the_wire": True, "active": ["fal"], "last": None}}, LOG)
    egress_state.PENDING["route"] = "openrouter"
    win = bpy.context.window_manager.windows[0]
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in view.regions if r.type == 'WINDOW')

    def pop():
        with bpy.context.temp_override(window=win, area=view, region=region):
            bpy.ops.wm.call_panel(name="LAMPWAY_PT_privacy_popout", keep_open=True)
        return None

    bpy.app.timers.register(pop, first_interval=0.5)


def surfaces(bpy, dump):
    confirm = next((w for w in dump["widgets"] if w.get("op") == "LAMPWAY_OT_egress_route" and w.get("text") == "Let it leave"), None)
    if not confirm:
        return {}
    x0, y0, x1, y1 = confirm["rect"]
    out = {"confirm_button": (x0 + 4, (y0 + y1) // 2)}
    allow = next((w for w in dump["widgets"] if w.get("op") == "LAMPWAY_OT_egress_override"), None)
    if allow:
        ax0, ay0, ax1, ay1 = allow["rect"]
        out["override_bed"] = (ax0 + 3, (ay0 + ay1) // 2)          # left of the words: the bed, if any
        out["override_text"] = ((ax0 + ax1) // 2, (ay0 + ay1) // 2, 6)  # the words themselves (nearest pixel in a box)
    on = next((w for w in dump["widgets"] if w.get("op") == "LAMPWAY_OT_egress_route" and w.get("text") == "On"), None)
    if on:
        out["on_switch"] = (on["rect"][2] - 4, (on["rect"][1] + on["rect"][3]) // 2)
    return out


def regions(bpy):
    return {}


def facts(bpy, dump):
    keep = ("LAMPWAY_OT_egress_route", "LAMPWAY_OT_egress_override", "LAMPWAY_OT_privacy_info", "LAMPWAY_OT_egress_route_cancel",
            "LAMPWAY_OT_choices_open")
    return {"buttons": [(w.get("op"), w.get("text"), w.get("enabled"), bool(w.get("sel"))) for w in dump["widgets"] if w.get("op") in keep],
            "labels": [w.get("text") for w in dump["widgets"] if w.get("popup") and not w.get("op")],
}
