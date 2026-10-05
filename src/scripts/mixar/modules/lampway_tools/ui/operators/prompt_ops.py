# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The prompt library in the Client: refresh the list, load a template (the variable form is generated from its schema), preview the render, edit it as my own (a
fork to the user scope with the next version), use it in a generation surface, and rate a finished job 1-5."""

import json

import bpy
from bpy.types import Operator

from mixar.modules.lampway_tools import prompt_attach, studio_client, studio_state
from mixar.modules.lampway_tools.ui.operators import studio_ops


def _client():
    return studio_ops.CLIENT_FACTORY()


class _PromptOp(Operator):
    bl_options = {"REGISTER"}

    def _done(self, context, message, ok=True):
        context.scene.lampway_tools.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


def _typed(row) -> object:
    kind, text = row.kind, row.value
    if kind == "integer":
        return int(float(text))
    if kind == "number":
        return float(text)
    if kind == "boolean":
        return text.strip().lower() in ("true", "1", "yes", "on")
    return text


def _variables(p) -> dict:
    out = {}
    for row in p.prompt_vars:
        try:
            out[row.name] = _typed(row)
        except ValueError:
            raise ValueError(f"{row.name}: {row.value!r} is not a {row.kind}")
    return out


class LAMPWAY_OT_prompts_refresh(_PromptOp):
    """Read the prompt templates from the server"""
    bl_idname = "lampway.prompts_refresh"
    bl_label = "Refresh templates"

    def execute(self, context):
        try:
            studio_state.PROMPTS["templates"] = _client().prompts().get("templates", [])
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        return self._done(context, f"{len(studio_state.PROMPTS['templates'])} templates")


class LAMPWAY_OT_prompt_load(_PromptOp):
    """Load the chosen template: its variables become a form with their types, bounds and defaults"""
    bl_idname = "lampway.prompt_load"
    bl_label = "Load template"

    def execute(self, context):
        p = context.scene.lampway_tools
        if not p.prompt_template:
            return self._done(context, "choose a template first", ok=False)
        try:
            t = _client().prompt(p.prompt_template)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        studio_state.PROMPTS["current"] = t
        p.prompt_vars.clear()
        for name, spec in (t.get("variables") or {}).items():
            row = p.prompt_vars.add()
            row.name, row.kind = name, spec["type"]
            default = spec.get("default", "")
            row.value = str(default).lower() if isinstance(default, bool) else str(default)
            row.vmin, row.vmax = float(spec.get("min", -1e9)), float(spec.get("max", 1e9))
            row.choices = "|".join(spec.get("enum") or [])
            row.help = spec.get("description", "")
        p.prompt_preview = ""
        return self._done(context, f"{t['title']} ({t['scope']}, v{t['version']})")


class LAMPWAY_OT_prompt_preview(_PromptOp):
    """Render the template with the form's values (through the server: nothing is generated)"""
    bl_idname = "lampway.prompt_preview"
    bl_label = "Preview"

    def execute(self, context):
        p = context.scene.lampway_tools
        try:
            out = _client().render_prompt(p.prompt_template, _variables(p), p.prompt_model or None)
        except (studio_client.StudioError, ValueError) as exc:
            return self._done(context, str(exc), ok=False)
        p.prompt_preview = out["prompt"]
        studio_state.PROMPTS["rendered"] = out
        return self._done(context, "rendered: " + out["template"] + (" | " + "; ".join(out["warnings"]) if out.get("warnings") else ""))


class LAMPWAY_OT_prompt_fork(_PromptOp):
    """Edit as my own: save a copy of this template in YOUR scope as the next version (the built-in is untouched)"""
    bl_idname = "lampway.prompt_fork"
    bl_label = "Edit as my own"

    def execute(self, context):
        t = studio_state.PROMPTS.get("current")
        if not t:
            return self._done(context, "load a template first", ok=False)
        major, minor, patch = (int(x) for x in t["version"].split("."))
        mine = {k: v for k, v in t.items() if k not in ("scope", "versions", "file")}
        mine["version"] = f"{major}.{minor}.{patch + 1}"
        mine["title"] = t["title"] if t["title"].startswith("My ") else "My " + t["title"]
        prov = dict(t.get("provenance") or {})
        prov["note"] = f"forked from {t['id']}@{t['version']}" + (" | " + prov["note"] if prov.get("note") else "")
        mine["provenance"] = prov
        try:
            _client().save_prompt(mine)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        return self._done(context, f"saved {mine['id']}@{mine['version']} in your scope; edit the JSON in <LAMPWAY_HOME>/prompts and refresh")


class LAMPWAY_OT_prompt_use(_PromptOp):
    """Use the rendered prompt in the Video Gen / Image Gen surface; the job then records the template and its variables"""
    bl_idname = "lampway.prompt_use"
    bl_label = "Use in generation"

    def execute(self, context):
        r = studio_state.PROMPTS.get("rendered")
        if not r:
            return self._done(context, "preview the prompt first", ok=False)
        tid, _, version = r["template"].partition("@")
        prompt_attach.remember(context.scene, tid, version, r["variables"], r["prompt"])
        sidebar = getattr(context.scene, "mixie_moodboard_sidebar", None)
        media = (studio_state.PROMPTS.get("current") or {}).get("media")
        tab = getattr(sidebar, "tab_video_gen" if media == "video" else "tab_imagegen", None) if sidebar else None
        if tab is not None and hasattr(tab, "prompt"):
            tab.prompt = r["prompt"]
        return self._done(context, "the prompt is in the " + ("Video" if media == "video" else "Image") + " Gen box; generate there and the run keeps the template")


class LAMPWAY_OT_prompt_rate(_PromptOp):
    """Rate a finished generation 1 to 5 (the captain's judgement tunes the wording)"""
    bl_idname = "lampway.prompt_rate"
    bl_label = "Rate"

    def execute(self, context):
        p = context.scene.lampway_tools
        if not p.prompt_job_id:
            return self._done(context, "enter the job id to rate", ok=False)
        try:
            _client().rate_prompt(p.prompt_job_id, p.prompt_rating, p.prompt_note)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        return self._done(context, f"rated {p.prompt_job_id}: {p.prompt_rating}/5")


classes = [LAMPWAY_OT_prompts_refresh, LAMPWAY_OT_prompt_load, LAMPWAY_OT_prompt_preview, LAMPWAY_OT_prompt_fork, LAMPWAY_OT_prompt_use, LAMPWAY_OT_prompt_rate]
