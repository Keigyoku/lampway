# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Lampway tools panel: the 3D viewport sidebar, tab "Lampway"."""

import textwrap

import bpy
from bpy.types import Panel

from mixar.modules.lampway_tools import api, jobs, studio_state


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


class LAMPWAY_PT_meshpaint(Panel):
    bl_idname = "LAMPWAY_PT_meshpaint"
    bl_label = "Mesh-paint texturing"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        for prop in ("mp_mesh", "mp_design_dir", "mp_recipe", "mp_relief_dir", "mp_out_root", "mp_tag", "mp_template", "mp_lift", "mp_live"):
            col.prop(p, prop)
        col.operator("lampway.meshpaint_run", icon="BRUSH_DATA")
        col.operator("lampway.meshpaint_albedo", icon="SHADING_TEXTURE")


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


class LAMPWAY_PT_qa_review(Panel):
    bl_idname = "LAMPWAY_PT_qa_review"
    bl_label = "Review proposals"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"

    def draw(self, context):
        col = self.layout.column(align=True)
        res = api.qa_proposals()
        if not res.get("ok"):
            col.label(text="Set a piece up first (Mesh QA)")
            return
        col.label(text=f"{res['piece']}: " + ", ".join(f"{v} {n}" for v, n in res["counts"].items()))
        for cid, p in list(res["proposals"].items())[:12]:
            col.label(text=f"{cid}  {p['verdict'].upper()}  {p.get('note', '')}"[:80])
        col.label(text="Proposals are not rulings: tag it to decide.")
        col.operator("lampway.qa_refresh", icon="COLOR")


class LAMPWAY_PT_studios(Panel):
    bl_idname = "LAMPWAY_PT_studios"
    bl_label = "Studios (online)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"

    def draw(self, context):
        layout = self.layout
        st = studio_state.STATE
        top = layout.row(align=True)
        top.operator("lampway.studio_refresh", icon="FILE_REFRESH")
        top.label(text="shelf engine" if st["engine"].get("shelf") else "bundled drivers")
        layout.operator("lampway.providers_open", text="Providers: agent, swarm, images", icon="PREFERENCES")
        if st["error"]:
            layout.label(text=st["error"][:80], icon="ERROR")
        waiting = studio_state.pending()
        if waiting:
            box = layout.box()
            box.label(text="Waiting for YOUR confirmation", icon="TIME")
            for ap in waiting:
                col = box.column(align=True)
                col.label(text=f"{ap['label']}")
                col.label(text=f"{ap['price']} credits, read back from Studio")
                row = col.row(align=True)
                c = row.operator("lampway.studio_confirm", text="Confirm and spend", icon="CHECKMARK")
                c.approval_id, c.price, c.label = ap["id"], int(ap["price"]), ap["label"]
                row.operator("lampway.studio_reject", text="Reject", icon="X").approval_id = ap["id"]
        p = context.scene.lampway_tools
        plan = layout.column(align=True)
        plan.prop(p, "studio_action", text="")
        plan.prop(p, "studio_args", text="")
        op = plan.operator("lampway.studio_plan", text="Plan (clicks nothing)", icon="VIEWZOOM")
        op.action, op.args_json = p.studio_action, p.studio_args
        for job in list(reversed(st["jobs"]))[:5]:
            row = layout.box().column(align=True)
            row.label(text=f"{job['label']}: {job['state']}", icon="CHECKMARK" if job["state"] == "done" else "TIME" if job["state"] == "running" else "ERROR")
            if job.get("error"):
                row.label(text=job["error"][:70])
            for f in job.get("files", [])[:6]:
                if f["name"].lower().endswith((".glb", ".gltf", ".fbx", ".obj")):
                    imp = row.operator("lampway.studio_import", text=f"Import {f['name']}", icon="IMPORT")
                    imp.job_id, imp.name = job["id"], f["name"]


class LAMPWAY_PT_features(Panel):
    bl_idname = "LAMPWAY_PT_features"
    bl_label = "Features"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        col.prop(p, "feature")
        col.prop(p, "feature_args")
        col.operator("lampway.feature_run", icon="PLAY")
        if p.last_message:
            col.label(text=p.last_message[:80])


classes = [LAMPWAY_PT_main, LAMPWAY_PT_studios, LAMPWAY_PT_qa_review, LAMPWAY_PT_features, LAMPWAY_PT_qa, LAMPWAY_PT_rebuild, LAMPWAY_PT_meshpaint, LAMPWAY_PT_tools]
