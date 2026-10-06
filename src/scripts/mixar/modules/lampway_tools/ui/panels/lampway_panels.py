# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Lampway tools panel: the 3D viewport sidebar, tab "Lampway"."""

import textwrap

import bpy
from bpy.types import Panel

from mixar.modules.lampway_tools import api, clip_state, egress_state, jobs, mcp_state, studio_state, workbench_state


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
        row = layout.row(align=True)
        row.operator("lampway.higgsfield_signin", icon="URL")
        for q in studio_state.questions():
            box = layout.box()
            box.label(text=str(q["settings"].get("question") or q["label"])[:80], icon="QUESTION")
            qrow = box.row(align=True)
            for answer, text in ((True, "Yes"), (False, "No")):
                op = qrow.operator("lampway.studio_answer", text=text)
                op.approval_id, op.answer = q["id"], answer
        waiting = studio_state.pending()
        if waiting:
            box = layout.box()
            box.label(text="Waiting for YOUR confirmation", icon="TIME")
            for ap in waiting:
                col = box.column(align=True)
                col.label(text=f"{ap['label']}")
                unit = (ap.get("settings") or {}).get("unit") or "credits"
                col.label(text=f"{ap['price']:g} {unit}, read back from {str(ap.get('studio') or 'Studio').capitalize()}")
                row = col.row(align=True)
                c = row.operator("lampway.studio_confirm", text="Confirm and spend", icon="CHECKMARK")
                c.approval_id, c.price, c.label = ap["id"], float(ap["price"]), ap["label"]
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


class LAMPWAY_PT_prompts(Panel):
    bl_idname = "LAMPWAY_PT_prompts"
    bl_label = "Prompts"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        col.operator("lampway.prompts_refresh", icon="FILE_REFRESH")
        col.prop(p, "prompt_template")
        col.operator("lampway.prompt_load", icon="IMPORT")
        for row in p.prompt_vars:
            col.prop(row, "value", text=row.name)
        if len(p.prompt_vars):
            col.prop(p, "prompt_model")
            col.operator("lampway.prompt_preview", icon="VIEWZOOM")
            col.operator("lampway.prompt_fork", icon="DUPLICATE")
        if p.prompt_preview:
            for line in textwrap.wrap(p.prompt_preview, 46)[:8]:
                col.label(text=line)
            col.operator("lampway.prompt_use", icon="PLAY")
        col.separator()
        col.prop(p, "prompt_job_id")
        col.prop(p, "prompt_rating")
        col.prop(p, "prompt_note")
        col.operator("lampway.prompt_rate", icon="SOLO_ON")
        if p.last_message:
            col.label(text=p.last_message[:80])


class LAMPWAY_PT_cockpit(Panel):
    """The cockpit: the user's real agent CLIs as panes of Lampway's own herdr server. draw() reads the cached state only: it never touches the network."""
    bl_idname = "LAMPWAY_PT_cockpit"
    bl_label = "Cockpit (agent sessions)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        st = workbench_state.STATE
        row = layout.row(align=True)
        row.operator("lampway.wb_refresh", icon="FILE_REFRESH")
        row.operator("lampway.wb_reconcile", icon="CHECKMARK")
        layout.label(text=workbench_state.summary_line(), icon="CHECKMARK" if st["server"].get("running") else "ERROR")
        if st["error"]:
            for line in textwrap.wrap(st["error"], 46)[:4]:
                layout.label(text=line)
        if not st["server"].get("running"):
            layout.operator("lampway.wb_start_server", icon="PLAY")
        else:
            layout.operator("lampway.wb_new", icon="ADD")
        for s in st["sessions"]:
            box = layout.box()
            box.label(text=f"{s['name']} ({s['agent']})  [{', '.join(workbench_state.chips(s))}]", icon="TEXT")
            if s.get("state") == "live":
                r = box.row(align=True)
                r.operator("lampway.wb_read_to_text", text="Read").session_id = s["id"]
                r.operator("lampway.wb_popout", text="Window").session_id = s["id"]
                r.operator("lampway.wb_send", text="Send").session_id = s["id"]
                r.operator("lampway.wb_close", text="Close").session_id = s["id"]
        if st["server"].get("running"):
            layout.operator("lampway.wb_stop_server", icon="CANCEL")


class LAMPWAY_PT_clips(Panel):
    """The clip table: one row per action (primary class, speed, loop, an inferred marker, the proposed name). draw() reads the cache only."""
    bl_idname = "LAMPWAY_PT_clips"
    bl_label = "Animation clips"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_main"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        col.prop(context.scene.lampway_tools, "clip_height")
        col.operator("lampway.clip_classify", icon="ACTION")
        for r in sorted(clip_state.ROWS, key=lambda r: not r["scales_joints"]):
            box = col.box()
            box.label(text=("SCALES JOINTS  " if r["scales_joints"] else "") + r["action"][:40], icon="ACTION")
            box.label(text=clip_state.line(r))
            box.label(text=f"-> {r['label']}")
        if clip_state.ROWS:
            col.operator("lampway.clip_apply_names", icon="CHECKMARK")


class LAMPWAY_PT_privacy(Panel):
    """Privacy: every outbound route, off until you switch it on, with its retention and training policy; the DATA LEAVING badge; the last log rows. draw() reads the cache only."""
    bl_idname = "LAMPWAY_PT_privacy"
    bl_label = "Privacy (what leaves this machine)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"

    def draw(self, context):
        layout = self.layout
        st = egress_state.STATE
        lit = st["indicator"].get("over_the_wire")
        layout.label(text=egress_state.badge(), icon="ERROR" if lit else "CHECKMARK")
        layout.operator("lampway.egress_refresh", icon="FILE_REFRESH")
        if st["error"]:
            layout.label(text=st["error"][:80])
        for r in st["routes"]:
            box = layout.box()
            row = box.row(align=True)
            row.label(text=egress_state.route_line(r), icon="CHECKBOX_HLT" if r["enabled"] else "CHECKBOX_DEHLT")
            op = row.operator("lampway.egress_route", text="Switch off" if r["enabled"] else "Switch on")
            op.route, op.enabled = r["id"], not r["enabled"]
            box.label(text=egress_state.policy_line(r))
        for row in st["log"][-20:]:
            layout.label(text=f"{row.get('event')} {row.get('route')} {row.get('provider', '')} {row.get('kind', '')} {row.get('bytes', 0)} B")
        layout.operator("lampway.egress_export", icon="EXPORT")


class LAMPWAY_PT_mcp(Panel):
    """Connections: which MCP servers your agent apps have, where each comes from and whether it is ready; a Check starts a short probe (your click). draw() reads the cache only."""
    bl_idname = "LAMPWAY_PT_mcp"
    bl_label = "Connections (MCP servers)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        st = mcp_state.STATE
        layout.operator("lampway.mcp_refresh", icon="FILE_REFRESH")
        layout.label(text=mcp_state.lampway_line())
        for note in st["lampway"].get("notes") or []:
            layout.label(text=note[:80], icon="ERROR")
        if st["error"]:
            layout.label(text=st["error"][:80], icon="ERROR")
        for s in st["servers"]:
            box = layout.box()
            box.label(text=mcp_state.card_line(s))
            if s.get("missing_env"):
                box.label(text="needs " + ", ".join(s["missing_env"]))
            box.label(text=mcp_state.connection_line(s))
            row = box.row(align=True)
            if s.get("can_check"):
                row.operator("lampway.mcp_check", text="Check").server_id = s["id"]
            row.operator("lampway.mcp_open_config", text="Show config file").server_id = s["id"]
        for p in st["problems"]:
            layout.label(text=p["message"][:80], icon="ERROR")


classes = [LAMPWAY_PT_privacy, LAMPWAY_PT_cockpit, LAMPWAY_PT_main, LAMPWAY_PT_clips, LAMPWAY_PT_studios, LAMPWAY_PT_qa_review, LAMPWAY_PT_features, LAMPWAY_PT_prompts, LAMPWAY_PT_qa, LAMPWAY_PT_rebuild, LAMPWAY_PT_meshpaint, LAMPWAY_PT_tools]
