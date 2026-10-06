# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 06 in the window: the Studios panel in the viewport's Lampway sidebar, with a waiting Tripo quote and a
maybe-sent job (fake state: nothing reaches a server, nothing is spent). The facts are the buttons it drew."""

SETTLE_TICKS = 12


def setup(bpy):
    from mixar.modules.lampway_tools import studio_state
    studio_state.STATE.update(
        actions=[{"id": "tripo.mesh", "label": "Smart Mesh: 4 variants at maximum polycount"}],
        approvals=[{"id": "a1", "state": "pending", "label": "Smart Mesh", "price": 13.5, "studio": "tripo",
                    "settings": {"unit": "credits"}}],
        jobs=[], engine={}, error="",
        receipts=[{"key": "k1", "label": "Texture on the Smart UV copy", "state": "submission_unknown",
                   "actions": ["acknowledge", "link"]}])
    win = bpy.context.window_manager.windows[0]
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in view.regions if r.type == 'WINDOW')

    def pop():   # the real panel, as a popover (the sidebar's tab cannot be chosen from Python)
        with bpy.context.temp_override(window=win, area=view, region=region):
            bpy.ops.wm.call_panel(name="LAMPWAY_PT_studios", keep_open=True)
        return None

    bpy.app.timers.register(pop, first_interval=0.5)


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    return {"buttons": sorted({(w.get("op") or "") + "|" + (w.get("text") or "") for w in dump["widgets"]
                               if (w.get("op") or "").startswith(("LAMPWAY_OT_studio", "LAMPWAY_OT_receipt"))})}
