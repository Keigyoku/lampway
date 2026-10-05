# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Lampway tools panel: the 3D viewport sidebar, tab "Lampway"."""

import textwrap

import bpy
from bpy.types import Panel

from mixar.modules.lampway_tools import jobs


class LAMPWAY_PT_main(Panel):
    bl_idname = "LAMPWAY_PT_main"
    bl_label = "Lampway tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"

    def draw(self, context):
        layout = self.layout
        p = context.scene.lampway_tools
        layout.operator("lampway.settings_open", icon="PREFERENCES")
        if p.last_message:
            box = layout.box()
            for line in textwrap.wrap(p.last_message, 46)[:6]:
                box.label(text=line)
        rows = [j for j in jobs.status() if j["state"] == "running"]
        for j in rows:
            layout.label(text=f"{j['id']} running ({j['seconds']:.0f} s)", icon="TIME")


class LAMPWAY_PT_qa(Panel):
    bl_idname = "LAMPWAY_PT_qa"
    bl_label = "Mesh QA"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        col.prop(p, "qa_recipe")
        col.prop(p, "qa_owner")
        col.prop(p, "qa_piece")
        col.prop(p, "qa_offset_z")
        col.prop(p, "qa_orig_poly")
        col.operator("lampway.qa_setup", icon="MESH_DATA")
        col.separator()
        col.operator("lampway.qa_candidates", icon="VIEWZOOM")
        col.operator("lampway.qa_draw", icon="GREASEPENCIL")
        col.separator()
        col.label(text="Tags: Red = Delete, Green = Mislabel, Yellow = Hole")
        col.operator("lampway.qa_tag_layers", icon="OUTLINER_DATA_GREASEPENCIL")
        col.prop(p, "mislabel_to")
        col.prop(p, "close_round")
        col.operator("lampway.qa_read_tags", icon="IMPORT")


class LAMPWAY_PT_rebuild(Panel):
    bl_idname = "LAMPWAY_PT_rebuild"
    bl_label = "Rebuild"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        for prop in ("rb_source_mesh", "rb_source_owner", "rb_relief_dir", "rb_plates_dir", "rb_template", "rb_lift"):
            col.prop(p, prop)
        col.operator("lampway.rebuild_setup", icon="FILE_TICK")
        col.separator()
        col.prop(p, "rb_tag")
        col.prop(p, "rb_res")
        col.prop(p, "rb_color_full")
        col.prop(p, "rb_ornament")
        col.prop(p, "rb_mesh_gold")
        col.operator("lampway.rebuild", icon="FILE_REFRESH")


class LAMPWAY_PT_tools(Panel):
    bl_idname = "LAMPWAY_PT_tools"
    bl_label = "Parts and proportion tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        col.prop(p, "tool")
        col.prop(p, "tool_args")
        col.operator("lampway.run_tool", icon="PLAY")


classes = [LAMPWAY_PT_main, LAMPWAY_PT_qa, LAMPWAY_PT_rebuild, LAMPWAY_PT_tools]
