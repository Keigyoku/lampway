# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Vault canvas operator (specs/asset_library/asset_ui_views.md section 6): OPEN a picture (a lineage graph with its layout for clicks, an overlay, a sheet, a frame),
FIT, CLOSE. Invoked from a button it stays modal over the Vault area: the wheel zooms about the cursor, the middle button drags, a click on a lineage node selects that
asset, Esc closes. Every other event passes through."""

import json

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator

from mixar.modules.asset_library.core import canvas_view as CV

STEP = 1.25


class MIXAR_OT_asset_library_canvas(Operator):
    """Open this picture on the pan/zoom canvas (wheel zooms, middle-drag pans, a click on a lineage node selects it, Esc closes)"""
    bl_idname = "mixar.asset_library_canvas"
    bl_label = "Canvas"
    bl_options = {"INTERNAL"}
    action: EnumProperty(items=[("OPEN", "Open", ""), ("FIT", "Fit", ""), ("CLOSE", "Close", ""), ("MODAL", "Modal", "attach the pan/zoom handling to what is already open")],
                         default="OPEN")
    path: StringProperty()
    lineage: StringProperty(description="the lineage layout as JSON, for clicks")

    def execute(self, context):
        if self.action == "OPEN":
            CV.install()
            CV.open_canvas(self.path, json.loads(self.lineage) if self.lineage else None)
        elif self.action == "FIT" and CV.STATE["canvas"] is not None:
            CV.STATE["canvas"].fit()
        elif self.action == "CLOSE":
            CV.close()
        CV.redraw()
        return {"FINISHED"}

    def invoke(self, context, event):
        self.execute(context)
        if self.action not in ("OPEN", "MODAL"):
            return {"FINISHED"}
        self._pan = None
        context.window_manager.modal_handler_add(self)
        return {"RUNNING_MODAL"}

    @staticmethod
    def _local(context, event):
        area = context.area
        if area is None:
            return None
        region = next((r for r in area.regions if r.type == "WINDOW"), None)
        if region is None:
            return None
        return region, event.mouse_x - region.x, event.mouse_y - region.y

    def modal(self, context, event):
        if not CV.STATE["open"]:
            return {"FINISHED"}
        where = self._local(context, event)
        if where is None:
            return {"PASS_THROUGH"}
        region, mx, my = where
        c = CV.ensure_fitted(region)
        if event.type == "MOUSEMOVE" and CV.board_drag(mx, my):
            CV.redraw()
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "RELEASE" and CV.board_release():
            CV.redraw()
            return {"RUNNING_MODAL"}
        if event.type == "MOUSEMOVE" and self._pan is not None:
            c.pan(mx - self._pan[0], my - self._pan[1])
            self._pan = (mx, my)
            CV.redraw()
            return {"RUNNING_MODAL"}
        if not c.inside(mx, my):
            return {"PASS_THROUGH"}
        if event.type in ("WHEELUPMOUSE", "WHEELDOWNMOUSE"):
            c.zoom_at(STEP if event.type == "WHEELUPMOUSE" else 1 / STEP, mx, my)
            CV.redraw()
            return {"RUNNING_MODAL"}
        if event.type == "MIDDLEMOUSE":
            self._pan = (mx, my) if event.value == "PRESS" else None
            return {"RUNNING_MODAL"}
        if CV.STATE.get("board") and event.type == "LEFTMOUSE" and event.value == "PRESS" and CV.board_press(mx, my):
            return {"RUNNING_MODAL"}
        if event.type == "LEFTMOUSE" and event.value == "PRESS" and CV.STATE["layout"]:
            if CV.click(mx, my):
                CV.redraw()
                return {"RUNNING_MODAL"}
        if event.type == "ESC" and event.value == "PRESS":
            CV.close()
            CV.redraw()
            return {"FINISHED"}
        return {"PASS_THROUGH"}


classes = (MIXAR_OT_asset_library_canvas,)
