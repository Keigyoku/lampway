# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 16's image fallback, windowed: an image path clicked in the Lampway terminal reaches Blender as one queue line
under the Lampway home; the status refresh drains it and the image shows in an Image Editor. Fake state: no terminal runs."""

import json
import os
import sys

SETTLE_TICKS = 12


def setup(bpy):
    from mixar.modules.lampway_tools import settings
    statusbar = sys.modules["mixar.modules.lampway_tools.ui.statusbar"]
    if bpy.app.timers.is_registered(statusbar._tick):
        bpy.app.timers.unregister(statusbar._tick)
    home = settings.lampway_home()
    png = str(home / "clicked.png")
    home.mkdir(parents=True, exist_ok=True)
    img = bpy.data.images.new("clicked_src", 8, 8)
    img.pixels = [1.0, 0.0, 1.0, 1.0] * 64
    img.filepath_raw = png
    img.file_format = "PNG"
    img.save()
    bpy.data.images.remove(img)
    q = home / "wezterm" / "show_in_blender.jsonl"
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text(json.dumps({"path": png}) + "\n", encoding="utf-8")

    def later():
        statusbar._show_terminal_images()
        return None

    bpy.app.timers.register(later, first_interval=0.5)


def facts(bpy, dump):
    shown, in_main = [], []
    main = bpy.context.window_manager.windows[0]
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'IMAGE_EDITOR' and area.spaces.active.image is not None:
                shown.append(os.path.basename(area.spaces.active.image.filepath))
                in_main.append(window == main)
    return {"shown": shown, "in_main": in_main, "main_areas": sorted(a.type for a in main.screen.areas)}


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}
