# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Operators of the Lampway tools panel. Each is a thin button over ``mixar.modules.lampway_tools.api``: the API does the
work and returns JSON; the operator turns it into one report line (also kept in ``scene.lampway_tools.last_message``)."""

import shlex

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import api, jobs


def summarize(res: dict) -> str:
    """One line for the status area."""
    if not res.get("ok"):
        return res.get("error", "failed")
    if "candidates" in res:
        s = f"{res['candidates']} candidates ({res['open_loops']} open loops, {res['loose_shells']} floating shells)"
        return s + (f", drew {res['drawn']}" if "drawn" in res else "")
    if "strokes" in res:
        st = res["strokes"]
        s = f"read {st['delete']} red / {st['mislabel']} green / {st['hole']} yellow strokes"
        if res["hole_loops"]:
            s += f"; holes: {', '.join(res['hole_loops'])}"
        if res["orphans"]:
            s += f"; {len(res['orphans'])} hole(s) no candidate had"
        if res["deleted"]:
            s += f"; deleted {res['deleted']} faces (shells {', '.join(res['shells']) or 'none'})"
        if res["relabelled"]:
            s += f"; relabelled {res['relabelled']} faces"
        if res["relabels_needing_a_target"]:
            s += f"; green strokes {[r['stroke'] for r in res['relabels_needing_a_target']]} still need a target part"
        return s
    if "job" in res:
        return f"started {res['job']}: the new version loads beside the old one when it finishes"
    if "drawn" in res:
        return f"drew {res['drawn']} candidates into {res['collection']}"
    if "layers" in res:
        return "tag layers: " + ", ".join(res["layers"])
    if "rc" in res:
        return f"rc {res['rc']}: " + (res["output"].strip().splitlines() or [""])[-1][:160]
    return ", ".join(f"{k}={v}" for k, v in res.items() if k != "ok")[:200]


class _ApiOp(Operator):
    bl_options = {"REGISTER"}

    def _finish(self, context, res):
        msg = summarize(res)
        context.scene.lampway_tools.last_message = msg
        self.report({"INFO" if res.get("ok") else "ERROR"}, msg)
        return {"FINISHED"} if res.get("ok") else {"CANCELLED"}


class LAMPWAY_OT_qa_setup(_ApiOp):
    """Point mesh QA at the active mesh object"""
    bl_idname = "lampway.qa_setup"
    bl_label = "Set up Mesh QA"

    def execute(self, context):
        p = context.scene.lampway_tools
        ob = context.active_object
        if ob is None or ob.type != "MESH":
            return self._finish(context, {"ok": False, "error": "select the piece's mesh object first"})
        return self._finish(context, api.qa_setup(object=ob.name, recipe=p.qa_recipe, owner=p.qa_owner, piece=p.qa_piece,
                                                  offset=(0, 0, p.qa_offset_z), orig_poly=p.qa_orig_poly, turn=p.qa_turn))


class LAMPWAY_OT_qa_tag_layers(_ApiOp):
    """Add the three tag layers to the annotations: Red = Delete, Green = Mislabel, Yellow = Hole"""
    bl_idname = "lampway.qa_tag_layers"
    bl_label = "Add tag layers"

    def execute(self, context):
        return self._finish(context, api.qa_tag_layers())


class LAMPWAY_OT_qa_candidates(_ApiOp):
    """Find open loops and floating shells on the piece and write them as typed candidates"""
    bl_idname = "lampway.qa_candidates"
    bl_label = "Find candidates"

    def execute(self, context):
        return self._finish(context, api.qa_candidates())


class LAMPWAY_OT_qa_draw(_ApiOp):
    """Draw the candidates into the scene (collection QA_candidates): yellow tubes and rings with their ids"""
    bl_idname = "lampway.qa_draw"
    bl_label = "Draw candidates"

    def execute(self, context):
        return self._finish(context, api.qa_draw())


class LAMPWAY_OT_qa_read_tags(_ApiOp):
    """Read the Red/Green/Yellow annotation strokes into decisions and rulings"""
    bl_idname = "lampway.qa_read_tags"
    bl_label = "Read tags"

    def execute(self, context):
        p = context.scene.lampway_tools
        targets = {}
        for pair in filter(None, (x.strip() for x in p.mislabel_to.split(","))):
            k, _, v = pair.partition(":")
            if not v:
                return self._finish(context, {"ok": False, "error": f"'{pair}' should be stroke:part, e.g. 0:cuirass_back_plate"})
            targets[k.strip()] = v.strip()
        return self._finish(context, api.qa_read_tags(close_round=p.close_round, mislabel_to=targets))


class LAMPWAY_OT_rebuild_setup(_ApiOp):
    """Save what a rebuild needs besides the rulings"""
    bl_idname = "lampway.rebuild_setup"
    bl_label = "Save rebuild setup"

    def execute(self, context):
        p = context.scene.lampway_tools
        return self._finish(context, api.rebuild_setup(source_mesh=p.rb_source_mesh, source_owner=p.rb_source_owner,
                                                       relief_dir=p.rb_relief_dir, plates_dir=p.rb_plates_dir,
                                                       template_material=p.rb_template, lift=p.rb_lift, turn=p.qa_turn or -90.0))


class LAMPWAY_OT_rebuild(_ApiOp):
    """Read tags, write rulings, rebuild, and load the result beside the previous version"""
    bl_idname = "lampway.rebuild"
    bl_label = "Read tags and rebuild"

    def execute(self, context):
        p = context.scene.lampway_tools
        targets = {}
        for pair in filter(None, (x.strip() for x in p.mislabel_to.split(","))):
            k, _, v = pair.partition(":")
            targets[k.strip()] = v.strip()
        res = api.rebuild(p.rb_tag, res=int(p.rb_res), color_full=p.rb_color_full, ornament=p.rb_ornament,
                          mesh_gold=p.rb_mesh_gold, close_round=p.close_round, mislabel_to=targets)
        return self._finish(context, res)


class LAMPWAY_OT_run_tool(_ApiOp):
    """Run one of the ported batch tools (parts, proportions, textures) in the background"""
    bl_idname = "lampway.run_tool"
    bl_label = "Run tool"

    def execute(self, context):
        p = context.scene.lampway_tools
        name, args = p.tool, shlex.split(p.tool_args)
        scene = context.scene

        def work():
            return api.run_tool(name, args)

        def done(job):
            scene.lampway_tools.last_message = f"{name}: " + summarize(job.result)

        job = jobs.start("tool-" + name, work, on_done=done)
        jobs.ensure_timer()
        return self._finish(context, {"ok": True, "job": job.id})


class LAMPWAY_OT_settings_open(Operator):
    """Project root, interpreters and texture libraries"""
    bl_idname = "lampway.settings_open"
    bl_label = "Lampway settings"

    project_root: StringProperty(name="Project root", subtype="DIR_PATH")
    python_science: StringProperty(name="Science python", subtype="FILE_PATH", description="A python with numpy, scipy, Pillow and OpenCV")
    blender: StringProperty(name="Blender for batch tools", subtype="FILE_PATH", description="Empty = this app")
    tiles_dir: StringProperty(name="Colour tiles", subtype="DIR_PATH")
    ambientcg_dir: StringProperty(name="ambientCG library", subtype="DIR_PATH")
    hdri: StringProperty(name="Studio HDRI", subtype="FILE_PATH")

    def invoke(self, context, event):
        cur = api.settings_get()["settings"]
        for k in ("project_root", "python_science", "blender", "tiles_dir", "ambientcg_dir", "hdri"):
            setattr(self, k, cur.get(k) or "")
        return context.window_manager.invoke_props_dialog(self, width=520)

    def execute(self, context):
        kw = {k: getattr(self, k) for k in ("project_root", "python_science", "blender", "tiles_dir", "ambientcg_dir", "hdri") if getattr(self, k)}
        res = api.settings_set(**kw)
        context.scene.lampway_tools.last_message = "settings saved" if res["ok"] else res["error"]
        return {"FINISHED"} if res["ok"] else {"CANCELLED"}


classes = [LAMPWAY_OT_qa_setup, LAMPWAY_OT_qa_tag_layers, LAMPWAY_OT_qa_candidates, LAMPWAY_OT_qa_draw, LAMPWAY_OT_qa_read_tags,
           LAMPWAY_OT_rebuild_setup, LAMPWAY_OT_rebuild, LAMPWAY_OT_run_tool, LAMPWAY_OT_settings_open]
