# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Asset Vault's drag and drop, end to end in the window: a tile (a ``mixar.asset_library_select`` button, as lane vault-ui
draws it) is dragged from the Vault editor and dropped on the Cube in the 3D viewport; the drop calls
``mixar.asset_library_place`` with the asset and where it landed.

Lane vault-ui owns the two operators; this build may not carry them, so the state registers stand-ins that record what they
were given. The gestures are real: a click on the tile (it selects), then a press, mouse moves past the drag threshold and a release
over the Cube."""

import json

SETTLE_TICKS = 16          # the gesture is queued one second after setup, once the tile has been drawn
PLACED = []
SELECTED = []
STATE = {"queued": False, "tile": None, "drop": None}


def _stand_ins(bpy):
    from bpy.props import StringProperty
    from bpy.types import Operator, Panel

    class MIXAR_OT_asset_library_select(Operator):
        bl_idname = "mixar.asset_library_select"
        bl_label = "Select"
        asset_id: StringProperty()

        def execute(self, context):
            SELECTED.append(self.asset_id)
            return {'FINISHED'}

    class MIXAR_OT_asset_library_place(Operator):
        bl_idname = "mixar.asset_library_place"
        bl_label = "Place in scene"
        asset_id: StringProperty()
        target_where: StringProperty()

        def execute(self, context):
            PLACED.append({"asset_id": self.asset_id, "where": self.target_where})
            return {'FINISHED'}

    class LAMPWAY_PT_vault_drag_probe(Panel):
        bl_space_type = 'MIXAR_ASSETS'
        bl_region_type = 'WINDOW'
        bl_label = "Tiles"

        def draw(self, context):
            self.layout.operator("mixar.asset_library_select", text="Brass lamp").asset_id = "a-42"

    for cls in (MIXAR_OT_asset_library_select, MIXAR_OT_asset_library_place, LAMPWAY_PT_vault_drag_probe):
        if getattr(bpy.types, cls.__name__, None) is None:
            bpy.utils.register_class(cls)


def _gesture(bpy):
    win = bpy.context.window_manager.windows[0]
    dump = json.loads(bpy.context.window_manager.mixar_qa_ui_dump)
    tile = next((w["rect"] for w in dump["widgets"] if w.get("op") == "MIXAR_OT_asset_library_select"), None)
    view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
    region = next(r for r in view.regions if r.type == 'WINDOW')
    if tile is None:
        return 0.25
    x0, y0 = (tile[0] + tile[2]) // 2, (tile[1] + tile[3]) // 2
    x1, y1 = region.x + region.width // 2, region.y + region.height // 2   # the Cube sits at the viewport's centre
    STATE.update(tile=[x0, y0], drop=[x1, y1])
    with bpy.context.temp_override(window=win):
        win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x0, y=y0)
        win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x0, y=y0)      # a plain click still selects the tile
        win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x0, y=y0)
        win.event_simulate(type='LEFTMOUSE', value='PRESS', x=x0, y=y0)      # and a drag carries it
        for i in range(1, 11):
            win.event_simulate(type='MOUSEMOVE', value='NOTHING', x=x0 + (x1 - x0) * i // 10, y=y0 + (y1 - y0) * i // 10)
        win.event_simulate(type='LEFTMOUSE', value='RELEASE', x=x1, y=y1)
    STATE["queued"] = True
    return None


def setup(bpy):
    _stand_ins(bpy)
    win = bpy.context.window_manager.windows[0]
    others = [a for a in win.screen.areas if a.type != 'VIEW_3D']
    if not others:  # the Zen layout is one viewport: split a third off its left for the Vault
        view = next(a for a in win.screen.areas if a.type == 'VIEW_3D')
        with bpy.context.temp_override(window=win, area=view, region=next(r for r in view.regions if r.type == 'WINDOW')):
            bpy.ops.screen.area_split(direction='VERTICAL', factor=0.3)
        others = [a for a in win.screen.areas if a.type == 'VIEW_3D']
    host = min(others, key=lambda a: a.x)   # the leftmost becomes the Vault; the viewport keeps the rest
    host.type = 'MIXAR_ASSETS'
    bpy.app.timers.register(lambda: _gesture(bpy), first_interval=1.0)


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    return {"placed": PLACED, "selected": SELECTED, "queued": STATE["queued"], "tile": STATE["tile"], "drop": STATE["drop"]}
