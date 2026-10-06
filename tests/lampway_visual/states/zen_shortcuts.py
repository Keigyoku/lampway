# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Keyboard shortcuts fire in the Zen workspace (found by lane vault-ui: none did, Blender's own ctrl+Space included,
while they fired in Layout). Two real key presses over the 3D viewport: N toggles its sidebar (an area keymap), and
ctrl+alt+Space takes the viewport full screen (the window's Screen keymap).

Plain ctrl+Space is not one of them: Zen is a single-area screen, and Blender refuses to maximise a single area
(screen_maximize_area_exec, upstream #144740: "SCREENMAXIMIZED is not useful when a singleton"). That refusal is what
looked like a dead keymap."""

SETTLE_TICKS = 10
STATE = {"before": None, "after_n": None, "workspace": None, "screen_before": None}


def _viewport(win):
    area = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    return area, next(r for r in area.regions if r.type == 'WINDOW')


def _press(win, key, x, y, ctrl=False, alt=False):
    with __import__("bpy").context.temp_override(window=win):
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x, y=y)
        win.event_simulate(type=key, value='PRESS', x=x, y=y, ctrl=ctrl, alt=alt)
        win.event_simulate(type=key, value='RELEASE', x=x, y=y, ctrl=ctrl, alt=alt)


def _second(bpy):
    win = bpy.context.window_manager.windows[0]
    area, region = _viewport(win)
    STATE["after_n"] = area.spaces.active.show_region_ui
    STATE["screen_before"] = win.screen.name
    _press(win, 'SPACE', region.x + region.width // 2, region.y + region.height // 2, ctrl=True, alt=True)
    return None


def setup(bpy):
    win = bpy.context.window_manager.windows[0]
    STATE["workspace"] = win.workspace.name
    area, region = _viewport(win)
    STATE["before"] = area.spaces.active.show_region_ui
    _press(win, 'N', region.x + region.width // 2, region.y + region.height // 2)
    bpy.app.timers.register(lambda: _second(bpy), first_interval=0.75)


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    win = bpy.context.window_manager.windows[0]
    return {"workspace": STATE["workspace"], "sidebar_toggled": STATE["after_n"] is not None and STATE["after_n"] != STATE["before"],
            "full_screen": win.screen.name != STATE["screen_before"]}
