# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The prompt library's list (facelift contract 08): a UIList over ``scene.lampway_tools.prompt_library`` (mirrored
from the server by lampway.prompts_refresh), filtered Image / Video. Name, version and mean price on the row; runs and
rating on the price's hover."""

import bpy
from bpy.props import StringProperty
from bpy.types import Operator, UIList


class LAMPWAY_UL_prompt_library(UIList):
    bl_idname = "LAMPWAY_UL_prompt_library"

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.label(text=item.title, icon="FILE_MOVIE" if item.media == "video" else "IMAGE_DATA")
        row.label(text=f"v{item.version}")
        info = row.operator("lampway.prompt_row_info", text=item.price, emboss=False)
        info.hover = item.hover

    def filter_items(self, context, data, propname):
        items = getattr(data, propname)
        media = getattr(context.scene.lampway_tools, "prompt_library_filter", "ALL")
        flags = [self.bitflag_filter_item if media == "ALL" or it.media == media.lower() else 0 for it in items]
        return flags, []


class LAMPWAY_OT_prompt_row_info(Operator):
    """Runs and rating of this template version"""
    bl_idname = "lampway.prompt_row_info"
    bl_label = "Runs and rating"
    bl_options = {"INTERNAL"}

    hover: StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.hover or "No runs yet"

    def execute(self, context):
        self.report({"INFO"}, self.hover or "No runs yet")
        return {"FINISHED"}


classes = [LAMPWAY_UL_prompt_library, LAMPWAY_OT_prompt_row_info]
