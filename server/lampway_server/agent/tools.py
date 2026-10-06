"""Tools v0. Every tool is a Python script the client runs in its sandbox via
blender.execute_script (executor.py); the reply envelope is executor_result.py's
``{success, <__RESULT__ keys>, output, created_objects, ..., error, traceback}``."""

import json

from .providers.base import ToolSpec
from . import lampway_tools as lt
from . import server_tools as st
from . import studio_tools as stu
from . import video_tools as vt
from . import prompt_tools as pt
from . import ledger_tools as lgt
from . import seed_tools as sdt
from . import image_tools as it
from . import engine_tools as eng
from . import compute_tools as cpt
from . import vault_tools as lib_
from . import cards_tools as crd
from . import files_tools as flt
from . import workbench_tools as wbt
from . import plan_tools as plt
from . import orphan_server_tools as ost
from . import connections_tools as cnt
from . import choices_tools as cht

RUN_BLENDER_PYTHON = "run_blender_python"
SCENE_SUMMARY = "scene_summary"
ASK_USER = "ask_user"

SCENE_SUMMARY_LIMIT = 100                     # audit F8: 1,016 objects answered 203 KB; a page is bounded, full=true is the caller's choice
SCENE_SUMMARY_SCRIPT = '''import bpy
_all = list(bpy.data.objects)
_page = _all if _FULL else _all[_OFFSET:_OFFSET + _LIMIT]
_objects = []
for _o in _page:
    _objects.append({
        "name": _o.name,
        "type": _o.type,
        "location": [round(float(v), 3) for v in _o.location],
        "dimensions": [round(float(v), 3) for v in _o.dimensions],
        "parent": _o.parent.name if _o.parent else None,
        "materials": [s.material.name for s in _o.material_slots if s.material],
        "hidden": bool(_o.hide_get()) if hasattr(_o, "hide_get") else False,
    })
_mats = list(bpy.data.materials)
_materials = [{"name": _m.name, "users": _m.users} for _m in (_mats if _FULL else _mats[:_LIMIT])]
_scene = bpy.context.scene
__RESULT__ = {
    "scene": _scene.name,
    "frame": _scene.frame_current,
    "object_count": len(_all),
    "offset": 0 if _FULL else _OFFSET,
    "next_offset": None if _FULL or _OFFSET + _LIMIT >= len(_all) else _OFFSET + _LIMIT,
    "objects": _objects,
    "material_count": len(_mats),
    "materials": _materials,
    "selected": [o.name for o in bpy.context.selected_objects] if bpy.context.selected_objects else [],
    "active": bpy.context.view_layer.objects.active.name if bpy.context.view_layer.objects.active else None,
}
'''

TOOLS = [
    ToolSpec(
        name=RUN_BLENDER_PYTHON,
        description=(
            "Run Python source inside the user's Blender. The script executes in a sandbox with "
            "bpy, bmesh, mathutils, bpy_extras, numpy, json, math, random, re and similar modules "
            "available; os, sys, pathlib and subprocess are not. Anything printed is returned as "
            "`output`. To return structured data, assign a JSON-serialisable dict to the variable "
            "`__RESULT__` (do not print it). The reply also lists created/modified/deleted object "
            "names and any error with its traceback."
        ),
        parameters={
            "type": "object",
            "properties": {"script": {"type": "string", "description": "Python source to run in Blender."}},
            "required": ["script"],
            "additionalProperties": False,
        },
    ),
    ToolSpec(
        name=SCENE_SUMMARY,
        description=(
            "List the objects (name, type, location, dimensions, parent, materials) and materials "
            "in the current Blender scene, plus the selection and active object. A page of `limit` objects (default 100) "
            "from `offset`, with object_count and next_offset; full=true lists every object."
        ),
        parameters={"type": "object", "properties": {
            "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "description": "Objects per page, default 100"},
            "offset": {"type": "integer", "minimum": 0, "description": "First object of the page, default 0 (next_offset of the previous page)"},
            "full": {"type": "boolean", "description": "Every object and material, no paging"}}, "additionalProperties": False},
    ),
]

TOOLS.append(ToolSpec(
    name=ASK_USER,
    description=(
        "Ask the user one question and wait for the answer before going on: a choice to make, a detail the request "
        "leaves open, or approval of a plan. Give short `options` when the answer is one of a few; leave them out for a "
        "free-text answer. For several independent choices, pass `questions` (2 to 4, each with options) instead: the user "
        "completes the set before you continue. The turn pauses until the user answers; their answer comes back as this tool's result."
    ),
    parameters={
        "type": "object",
        "properties": {"question": {"type": "string", "description": "The question, in plain language."},
                       "options": {"type": "array", "items": {"type": "string"},
                                   "description": "The choices to offer (2 to 6 short labels), if any."},
                       "questions": {"type": "array", "description": (
                           "A batch instead of `question`: 2 to 4 independent questions, each {question, options} (options required), shown as one "
                           "wizard and answered together; the result is the map {question: answer}."),
                                     "items": {"type": "object", "properties": {"question": {"type": "string"},
                                                                                "options": {"type": "array", "items": {"type": "string"}}},
                                               "required": ["question", "options"], "additionalProperties": False}}},
        "required": [],
        "additionalProperties": False,
    },
))

TOOLS = TOOLS + lt.SPECS + st.SPECS + stu.specs() + vt.specs() + pt.specs() + it.specs() + lgt.specs() + sdt.specs() + eng.specs() + wbt.specs() + cpt.specs() + lib_.specs() + crd.specs() + flt.specs() + plt.specs() + ost.specs() + cnt.specs() + cht.specs()
TOOL_NAMES = {t.name for t in TOOLS}


class UnknownTool(ValueError):
    pass


def script_for(name: str, arguments: dict) -> str:
    if name == RUN_BLENDER_PYTHON:
        script = arguments.get("script") if isinstance(arguments, dict) else None
        if not isinstance(script, str):
            raise UnknownTool("run_blender_python needs a string `script`")
        return script
    if name == SCENE_SUMMARY:
        args = arguments if isinstance(arguments, dict) else {}
        try:
            limit, offset = int(args.get("limit") or SCENE_SUMMARY_LIMIT), int(args.get("offset") or 0)
        except (TypeError, ValueError):
            raise UnknownTool("scene_summary takes integers: limit (1..1000) and offset (>= 0)") from None
        if not (1 <= limit <= 1000 and offset >= 0):
            raise UnknownTool("scene_summary takes limit 1..1000 and offset >= 0")
        return f"_LIMIT, _OFFSET, _FULL = {limit}, {offset}, {bool(args.get('full'))}\n" + SCENE_SUMMARY_SCRIPT
    if name == ASK_USER:
        raise UnknownTool("ask_user is answered by the user, not by Blender")
    if name in vt.NAMES or name in stu.NAMES or name in pt.NAMES or name in it.NAMES or name in lgt.NAMES or name in lgt.JOB_NAMES or name in sdt.NAMES or name in eng.NAMES or name in wbt.NAMES or name in cpt.NAMES or name in lib_.NAMES or name in crd.NAMES or name in flt.NAMES or name in plt.NAMES or name in cnt.NAMES or name in cht.NAMES:
        raise UnknownTool(f"{name} runs on the server, not in Blender")
    if name in ost.NAMES:
        raise UnknownTool(f"{name} runs on the server, not in Blender")
    if st.is_local(name):
        raise UnknownTool(f"{name} runs on the server, not in Blender")
    if name in lt.BY_NAME:
        try:
            return lt.build_script(lt.BY_NAME[name], arguments)
        except lt.BadArguments as exc:
            raise UnknownTool(str(exc)) from exc
    raise UnknownTool(f"unknown tool {name!r}")


def format_tool_result(result) -> tuple[str, bool]:
    """(text for the model, is_error) from the client's execution envelope."""
    if not isinstance(result, dict):
        return json.dumps({"success": False, "error": "no result from Blender"}), True
    is_error = not result.get("success", False)
    return json.dumps(result, default=str), is_error
