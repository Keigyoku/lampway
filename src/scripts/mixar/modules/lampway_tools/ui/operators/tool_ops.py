# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""One operator per tool of the Way, with the tool's own typed properties (facelift contract 07: no free-text runner).
Generated at import from ``tool_specs.json``, which is generated from the agent's tool definitions: the form the user
fills and the schema the agent calls are the same. Run opens the form as a dialog; a batch tool runs as a background
job, a feature tool through ``api.call``; success marks the tool's step done on the active object (the Way's node)."""

import json

import bpy
from bpy.props import BoolProperty, FloatProperty, IntProperty, StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import api, jobs, the_way, tool_specs
from mixar.modules.lampway_tools.ui.operators.lampway_ops import summarize


def _prop(p):
    desc = (p.get("desc") or "")[:240] + (" (required)" if p.get("required") else "")
    name = p["name"].replace("_", " ").capitalize()
    if p["type"] == "boolean":
        return BoolProperty(name=name, description=desc)
    if p["type"] == "integer":
        return IntProperty(name=name, description=desc)
    if p["type"] == "number":
        return FloatProperty(name=name, description=desc)
    if p["type"] == "array":
        return StringProperty(name=name, description=desc + " (comma separated)")
    return StringProperty(name=name, description=desc)


def values_of(op, spec) -> dict:
    """The form's values; a number the user did not set, an empty string and an empty list are left out."""
    out = {}
    for p in spec["params"]:
        v = getattr(op, p["name"], None)
        if p["type"] in ("integer", "number"):
            if not op.properties.is_property_set(p["name"]):
                continue
        elif p["type"] == "array":
            v = [x.strip() for x in (v or "").split(",") if x.strip()]
            if not v:
                continue
        elif p["type"] == "boolean":
            if not v:
                continue
        elif v in (None, ""):
            continue
        out[p["name"]] = v
    return out


def _make(spec):
    key = spec.get("batch") or spec.get("api")

    def invoke(self, context, event):
        if any(p["name"] == "object" for p in spec["params"]) and not self.properties.is_property_set("object") \
                and context.active_object is not None:
            self.object = context.active_object.name
        return context.window_manager.invoke_props_dialog(self, width=460, title=tool_specs.title(spec), confirm_text="Run")

    def execute(self, context):
        values = values_of(self, spec)
        missing = [p["name"] for p in spec["params"] if p.get("required") and p["name"] not in values]
        if missing:
            self.report({'ERROR'}, f"{tool_specs.title(spec)} needs {', '.join(missing)}")
            return {'CANCELLED'}
        scene, obj, step = context.scene, context.active_object, the_way.step_of(spec["name"])
        if spec.get("batch"):
            argv = tool_specs.argv(spec, values)

            def work():
                return api.run_tool(spec["batch"], argv)

            def done(job):
                scene.lampway_tools.last_message = f"{tool_specs.title(spec)}: " + summarize(job.result)
                if (job.result or {}).get("ok") and step:
                    the_way.mark_done(obj, step)

            job = jobs.start("tool-" + key, work, on_done=done)
            jobs.ensure_timer()
            scene.lampway_tools.last_message = f"{tool_specs.title(spec)} started ({job.id})"
            return {'FINISHED'}
        res = api.call(spec["api"], json.dumps(values))
        msg = summarize(res)
        scene.lampway_tools.last_message = f"{tool_specs.title(spec)}: {msg}"
        self.report({'INFO' if res.get("ok") else 'ERROR'}, msg)
        if res.get("ok") and step:
            the_way.mark_done(obj, step)
        return {'FINISHED'} if res.get("ok") else {'CANCELLED'}

    return type(f"LAMPWAY_OT_tool_{key}", (Operator,), {
        "bl_idname": tool_specs.operator_id(spec), "bl_label": tool_specs.title(spec),
        "bl_description": spec["description"][:400], "bl_options": {'REGISTER'},
        "__annotations__": {p["name"]: _prop(p) for p in spec["params"]},
        "invoke": invoke, "execute": execute})


SPECS = tool_specs.load()
classes = [_make(spec) for spec in SPECS.values()]
