"""The agent's prompt-library tools. ``lampway_prompt_save`` writes the USER scope only (built-ins and project templates are never written by a tool); a saved
template is validated and a version is never overwritten."""

import asyncio
import json

from ..prompts.library import LibraryError
from ..prompts.render import RenderError
from .providers.base import ToolSpec

NAMES = {"lampway_prompt_list", "lampway_prompt_get", "lampway_prompt_render", "lampway_prompt_save", "lampway_prompt_rate", "lampway_prompt_stats"}


def specs() -> list:
    obj = lambda props, req=(): {"type": "object", "properties": props, "required": list(req), "additionalProperties": False}  # noqa: E731
    return [
        ToolSpec("lampway_prompt_list", "List the prompt templates (image and video): id, newest version, title, purpose, scope (builtin, user, project). Use `media` to filter.",
                 obj({"media": {"type": "string", "description": "image | video"}})),
        ToolSpec("lampway_prompt_get", "One template in full: the five-part body (subject, action, camera, style, constraints), its typed variables with bounds, negatives, timed beats, "
                 "the input roles in order, per-model adapters, gates and provenance.", obj({"id": {"type": "string"}, "version": {"type": "string"}}, ["id"])),
        ToolSpec("lampway_prompt_render", "Render a template with variables for a model: returns the prompt text, negatives, the inputs it needs (in order), the params and warnings. A bad "
                 "variable is refused by name. For purpose motion-graphics, use the brief to author a local scene with its setup/audit contract, then pass the scene "
                 "and the same `template` + `variables` to lampway_motion_graphics. Motion briefs are refused by provider generation. For other provider templates, "
                 "pass the same `template` + `variables` to lampway_video_gen / lampway_image_gen.",
                 obj({"id": {"type": "string"}, "variables": {"type": "object"}, "model": {"type": "string"}, "version": {"type": "string"}}, ["id"])),
        ToolSpec("lampway_prompt_save", "Save a template to the USER scope (validated; an existing id@version is never overwritten: bump the version). Fork a built-in by getting it, "
                 "editing and saving it with a higher version.", obj({"template": {"type": "object"}}, ["template"])),
        ToolSpec("lampway_prompt_rate", "Record the user's rating (1 to 5, with a note) for a finished generation job, so wording is tuned on measured results and his judgement.",
                 obj({"job_id": {"type": "string"}, "rating": {"type": "integer"}, "note": {"type": "string"}}, ["job_id", "rating"])),
        ToolSpec("lampway_prompt_stats", "Per template version: runs, rated, mean rating, mean cost and the gate pass rates; use it to compare two versions (A/B).",
                 obj({"template": {"type": "string"}})),
    ]


async def call(svc, name: str, arguments: dict) -> tuple:
    a = arguments if isinstance(arguments, dict) else {}
    try:
        if name == "lampway_prompt_list":
            return json.dumps({"templates": [{k: t[k] for k in ("id", "version", "title", "purpose", "media", "scope")} for t in svc.library.list(a.get("media"))],
                               "errors": svc.library.errors}), False
        if name == "lampway_prompt_get":
            t = svc.library.get(str(a.get("id") or ""), a.get("version"))
            return json.dumps({k: v for k, v in t.items() if k != "file"}), False
        if name == "lampway_prompt_render":
            return json.dumps(svc.render(str(a.get("id") or ""), a.get("variables"), a.get("model"), a.get("version"))), False
        if name == "lampway_prompt_save":
            path = await asyncio.to_thread(svc.library.save, a.get("template"))
            return json.dumps({"saved": path, "scope": "user"}), False
        if name == "lampway_prompt_rate":
            svc.runlog.rate(str(a.get("job_id") or ""), a.get("rating"), a.get("note") or "")
            return json.dumps({"ok": True}), False
        if name == "lampway_prompt_stats":
            return json.dumps({"stats": svc.runlog.stats(a.get("template"))}), False
    except (LibraryError, RenderError, ValueError) as exc:
        return str(exc), True
    return f"unknown prompt tool {name!r}", True
