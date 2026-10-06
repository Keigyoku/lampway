# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The floating agent pill (the captain, facelift 04/05), live: a new profile opens the chat with no pill; Ctrl+Shift+B
closes the chat and the top bar's agent chip appears; the shortcut opens it again; turning the preference on gives the
open chat its pill; minimising then rests in the pill. Each step is recorded: the chat's child windows (with or without
the chat's body, i.e. island or pill) and the top bar's chip."""

import json

import bpy
OUT = {"steps": []}
SETTLE_TICKS = 60
def kids():
    return [[x.width, x.height, len([a for a in x.screen.areas if a.type == 'AGENT_BUBBLE' for r in a.regions if r.type == 'TOOLS'])] for x in bpy.context.window_manager.windows if x.parent is not None]
def snap(tag):
    dump = json.loads(bpy.context.window_manager.mixar_qa_ui_dump)
    main = dump["windows"][0]["ptr"] if dump.get("windows") else None
    chips = [w.get("text") for w in dump["widgets"] if w.get("op") == "MIXAR_OT_agent_bubble_open_window" and w.get("w") == main]
    OUT["steps"].append({"tag": tag, "children": kids(), "topbar_chip": chips})
def main_ctx():
    win = bpy.context.window_manager.windows[0]
    return bpy.context.temp_override(window=win, area=win.screen.areas[0])
def step(n):
    def run():
        try:
            if n == 0:
                snap("startup, pill off")
                with main_ctx():
                    OUT["toggle1"] = list(bpy.ops.mixar.bubble_toggle_minimise())
            elif n == 1:
                snap("after Ctrl+Shift+B (closes)")
                with main_ctx():
                    OUT["toggle2"] = list(bpy.ops.mixar.bubble_toggle_minimise())
            elif n == 2:
                snap("after Ctrl+Shift+B again (opens)")
                bpy.context.window_manager.lampway_floating_agent_pill = True
            elif n == 3:
                snap("pill turned on, chat open")
                with main_ctx():
                    OUT["toggle3"] = list(bpy.ops.mixar.bubble_toggle_minimise())
            elif n == 4:
                snap("pill on, minimised")
                return None
        except Exception:
            import traceback; OUT.setdefault("exc", []).append(traceback.format_exc()[-600:])
        bpy.app.timers.register(step(n + 1), first_interval=1.5)
        return None
    return run
def setup(bpy):
    bpy.app.timers.register(step(0), first_interval=5.0)
def surfaces(bpy, dump): return {}
def regions(bpy): return {}
def facts(bpy, dump): return OUT
