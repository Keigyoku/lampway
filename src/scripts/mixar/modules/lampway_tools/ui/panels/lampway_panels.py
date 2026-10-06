# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Lampway tools panel: the 3D viewport sidebar, tab "Lampway"."""

import textwrap

import bpy
from bpy.types import Panel, UIList

from mixar.modules.lampway_tools import api, clip_state, jobs, mcp_state, studio_state, the_way, workbench_state
from mixar.modules.lampway_tools.ui.operators import tool_ops

QA_CACHE = {"result": None}
QA_REFRESH_S = 2.0


def _qa_refresh():
    """The Review panel's proposals, read on a timer (a draw never does the work)."""
    try:
        QA_CACHE["result"] = api.qa_proposals()
    except Exception as exc:  # noqa: BLE001
        QA_CACHE["result"] = {"ok": False, "error": str(exc)}
    return QA_REFRESH_S


def ensure_qa_refresh():
    if not bpy.app.background and not bpy.app.timers.is_registered(_qa_refresh):
        bpy.app.timers.register(_qa_refresh, first_interval=0.0, persistent=True)


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
            # One line and "more" (facelift contract 07), not six wrapped labels.
            row = layout.row(align=True)
            row.label(text=p.last_message[:60] + ("..." if len(p.last_message) > 60 else ""))
            if len(p.last_message) > 60:
                row.popover("LAMPWAY_PT_last_message", text="more")
        rows = [j for j in jobs.status() if j["state"] == "running"]
        for j in rows:
            layout.label(text=f"{j['id']} running ({j['seconds']:.0f} s)", icon="TIME")


class LAMPWAY_PT_last_message(Panel):
    """The whole last result (the main panel shows one line)."""
    bl_idname = "LAMPWAY_PT_last_message"
    bl_label = "Last result"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 18

    def draw(self, context):
        for line in textwrap.wrap(context.scene.lampway_tools.last_message, 70)[:20]:
            self.layout.label(text=line)


class LAMPWAY_PT_way(Panel):
    """The Way (facelift contract 07): the captain's piece runbook, one step per panel, a node for this piece."""
    bl_idname = "LAMPWAY_PT_way"
    bl_label = "The way"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"

    def draw(self, context):
        obj = context.active_object
        done = the_way.done_steps(obj)
        self.layout.label(text=f"{obj.name if obj else 'No piece selected'}: {the_way.progress(done)}")


def _way_step_panel(step):
    """A step of the Way: the node (this piece) and the name in the header, the tool's word in the header's right."""

    def draw_header(self, context):
        from mixar.modules.common.lampway_icons import icon_id
        try:
            icon = icon_id(the_way.node(step["id"], the_way.done_steps(context.active_object)))
        except Exception:  # noqa: BLE001 - a header draw never raises
            icon = 0
        self.layout.label(text="", icon_value=icon)

    def draw_header_preset(self, context):
        self.layout.label(text=the_way.WORD[step["status"]], icon=the_way.WORD_ICON[step["status"]])

    def draw(self, context):
        layout = self.layout
        if step.get("note"):
            layout.label(text=step["note"][:80])
        status = the_way.tool_status()
        for name in step.get("tools", []):
            spec = tool_ops.SPECS.get(name)
            if spec is not None:
                the_way.draw_tool(layout, spec, status.get(name, {"status": step["status"], "when": step.get("when", "")}))

    return type(f"LAMPWAY_PT_way_{step['id']}", (Panel,), {
        "bl_idname": f"LAMPWAY_PT_way_{step['id']}", "bl_label": step["name"], "bl_space_type": "VIEW_3D",
        "bl_region_type": "UI", "bl_category": "Lampway", "bl_parent_id": "LAMPWAY_PT_way", "bl_options": {"DEFAULT_CLOSED"},
        "draw_header": draw_header, "draw_header_preset": draw_header_preset, "draw": draw})


WAY_STEPS = [_way_step_panel(step) for step in the_way.steps()]


class LAMPWAY_PT_qa(Panel):
    bl_idname = "LAMPWAY_PT_qa"
    bl_label = "Find and draw candidates"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_way_mesh_qa"

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
    bl_parent_id = "LAMPWAY_PT_way_mesh_paint"
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
    bl_parent_id = "LAMPWAY_PT_way_mesh_paint"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        col = self.layout.column(align=True)
        p = context.scene.lampway_tools
        for prop in ("mp_mesh", "mp_design_dir", "mp_recipe", "mp_relief_dir", "mp_out_root", "mp_tag", "mp_template", "mp_lift", "mp_live"):
            col.prop(p, prop)
        col.operator("lampway.meshpaint_run", icon="BRUSH_DATA")
        col.operator("lampway.meshpaint_albedo", icon="SHADING_TEXTURE")


class LAMPWAY_PT_qa_review(Panel):
    bl_idname = "LAMPWAY_PT_qa_review"
    bl_label = "Review proposals"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"
    bl_parent_id = "LAMPWAY_PT_way_mesh_qa"

    def draw(self, context):
        col = self.layout.column(align=True)
        res = QA_CACHE["result"]                     # filled by a timer: never an api call in a draw (contract 07)
        if res is None:
            ensure_qa_refresh()
            col.label(text="Reading the proposals...")
            return
        if not res.get("ok"):
            col.label(text="Set a piece up first (Mesh QA)")
            return
        col.label(text=f"{res['piece']}: " + ", ".join(f"{v} {n}" for v, n in res["counts"].items()))
        for cid, p in list(res["proposals"].items())[:12]:
            col.label(text=f"{cid}  {p['verdict'].upper()}  {p.get('note', '')}"[:80])
        col.label(text="Proposals are not rulings: tag it to decide.")
        col.operator("lampway.qa_refresh", icon="COLOR")


class LAMPWAY_UL_studio_plan_args(UIList):
    """One typed plan argument per row: name, kind, value."""

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        row = layout.row(align=True)
        row.prop(item, "key", text="", emboss=False)
        row.prop(item, "kind", text="")
        row.prop(item, {"TEXT": "text", "NUMBER": "number", "FILE": "path", "FLAG": "flag"}[item.kind], text="")


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
        # A waiting spend is a card with its price on the button (facelift 06; contract 13's words): the one glow here.
        for n, ap in enumerate(studio_state.pending()):
            box = layout.box()
            col = box.column(align=True)
            unit = (ap.get("settings") or {}).get("unit") or "credits"
            col.label(text=f"{ap['label']}", icon='TIME')
            col.label(text=f"{ap['price']:g} {unit}, read back from {str(ap.get('studio') or 'Studio').capitalize()}")
            # The price is on the button and the button has the row to itself: a narrow sidebar never clips the number.
            c = col.operator("lampway.studio_confirm", text=f"Spend {ap['price']:g} {unit}", icon="CHECKMARK", depress=n == 0)
            c.approval_id, c.price, c.label = ap["id"], float(ap["price"]), ap["label"]
            col.operator("lampway.studio_reject", text="Not now", icon="X").approval_id = ap["id"]
        # A job Lampway cannot account for: the user's two ways out, visible, never glowing, nothing that sends it again.
        for r in studio_state.maybe_sent():
            box = layout.box()
            box.label(text=f"{r.get('label') or r.get('key')}: maybe sent", icon='QUESTION')
            row = box.row(align=True)
            row.operator("lampway.receipt_acknowledge", text="It did not run").key = r["key"]
            row.operator("lampway.receipt_link", text="Link its job id").key = r["key"]
        p = context.scene.lampway_tools
        header, body = layout.panel("lampway_studio_plan", default_closed=True)
        header.label(text="Plan an action (clicks nothing)")
        if body is not None:
            body.prop(p, "studio_action", text="")
            row = body.row()
            row.template_list("LAMPWAY_UL_studio_plan_args", "", p, "studio_plan_args", p, "studio_plan_args_index", rows=3)
            side = row.column(align=True)
            side.operator("lampway.studio_plan_arg_add", text="", icon='ADD')
            side.operator("lampway.studio_plan_arg_remove", text="", icon='REMOVE')
            from mixar.modules.lampway_tools.ui.operators.studio_ops import plan_args
            import json
            op = body.operator("lampway.studio_plan", text="Plan", icon="VIEWZOOM")
            op.action, op.args_json = p.studio_action, json.dumps(plan_args(p.studio_plan_args))
        for job in list(reversed(st["jobs"]))[:5]:
            row = layout.box().column(align=True)
            row.label(text=f"{job['label']}: {job['state']}", icon="CHECKMARK" if job["state"] == "done" else "TIME" if job["state"] == "running" else "ERROR")
            if job.get("error"):
                row.label(text=job["error"][:70])
            for f in job.get("files", [])[:6]:
                if f["name"].lower().endswith((".glb", ".gltf", ".fbx", ".obj")):
                    imp = row.operator("lampway.studio_import", text=f"Import {f['name']}", icon="IMPORT")
                    imp.job_id, imp.name = job["id"], f["name"]


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
        # The library is a list (facelift contract 08): name, version and mean price per row; runs and rating on hover.
        col.row(align=True).prop(p, "prompt_library_filter", expand=True)
        col.template_list("LAMPWAY_UL_prompt_library", "", p, "prompt_library", p, "prompt_library_index", rows=6)
        col.operator("lampway.prompt_load", icon="IMPORT")
        for row in p.prompt_vars:
            col.prop(row, "value", text=row.name)
        if len(p.prompt_vars):
            col.prop(p, "prompt_model")
            col.operator("lampway.prompt_preview", icon="VIEWZOOM")
            col.operator("lampway.prompt_fork", icon="DUPLICATE")
        if p.prompt_preview:
            col.popover("LAMPWAY_PT_prompt_preview", text=textwrap.shorten(p.prompt_preview, 40, placeholder="..."))
            col.operator("lampway.prompt_use", icon="PLAY")
        col.separator()
        col.prop(p, "prompt_job_id")
        col.prop(p, "prompt_rating")
        col.prop(p, "prompt_note")
        col.operator("lampway.prompt_rate", icon="SOLO_ON")
        if p.last_message:
            col.label(text=p.last_message[:80])


class LAMPWAY_PT_prompt_preview(Panel):
    """The rendered prompt, whole (it was eight cut labels)."""
    bl_idname = "LAMPWAY_PT_prompt_preview"
    bl_label = "Rendered prompt"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 22

    def draw(self, context):
        col = self.layout.column(align=True)
        for line in textwrap.wrap(context.scene.lampway_tools.prompt_preview, 60):
            col.label(text=line)


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



classes = [LAMPWAY_UL_studio_plan_args, LAMPWAY_PT_last_message, LAMPWAY_PT_prompt_preview, LAMPWAY_PT_cockpit, LAMPWAY_PT_main,
           LAMPWAY_PT_way, *WAY_STEPS, LAMPWAY_PT_qa, LAMPWAY_PT_qa_review, LAMPWAY_PT_meshpaint, LAMPWAY_PT_rebuild,
           LAMPWAY_PT_clips, LAMPWAY_PT_studios, LAMPWAY_PT_prompts]
