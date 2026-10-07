# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
# SPDX-License-Identifier: GPL-2.0-or-later
"""One schema authority for local relay, MCP, and QA callers."""

from ..constants import UIError


# Public parameter meanings apply identically to relay, MCP and QA schemas.
_PARAMETER_DESCRIPTIONS = {
    "release": "Release this connection's native input ownership.",
    "instance": "Opaque running application instance identifier to bind.",
    "session": "Opaque scene session identifier returned by the scene list.",
    "context": "Fresh opaque observation context handle; observe again after the UI changes.",
    "target": "Opaque control or region handle from the same observation context.",
    "action": "Native event action selected by this schema alternative.",
    "query": "Match visible controls by their observed labels and metadata.",
    "image": "Include a fresh screenshot in the observation receipt.",
    "window": "Opaque observed window identifier to inspect.",
    "limit": "Maximum controls in this observation page, from 1 to 200.",
    "offset": "Number of matching controls to skip before this page.",
    "double": "Send a double click instead of a single click.",
    "modifiers": "Keyboard modifiers held during this native event.",
    "shift": "Hold Shift during the event.", "ctrl": "Hold Control during the event.",
    "alt": "Hold Alt during the event.", "oskey": "Hold the platform command key during the event.",
    "text": "Visible text to match or literal text to enter, without control characters.",
    "enter": "Press Enter after entering the text.",
    "item": "Visible item label to choose.",
    "key": "Native uppercase key identifier to press.",
    "steps": "Signed scroll steps; positive and negative values select opposite directions.",
    "points": "Gesture path of normalized bottom-left region coordinates, each between 0 and 1.",
    "button": "Mouse button held during the gesture.",
    "duration": "Gesture duration in seconds, from 0.05 to 5.",
    "present": "Wait for matching controls to be present when true or absent when false.",
    "timeout": "Maximum wait in seconds, from 0 to 30.",
    "call_id": "Durable local UI call identifier whose receipt should be recovered.",
    "name": "New scene tab name, at most 63 characters without control characters.",
    "project": "Opaque recent project identifier returned by the project list.",
    "unsaved": "Explicit user decision for unsaved work: refuse, save or discard.",
    "op": "Observed operator identifier to match.",
    "prop": "Observed property identifier to match.",
    "surface": "Observed UI surface name to match.",
    "area_type": "Observed editor area type to match.",
    "region_type": "Observed editor region type to match.",
    "panel": "Observed panel label to match.",
    "value": "Observed displayed control value to match.",
}


def obj(properties=None, required=()):
    described = {name: {**value, "description": _PARAMETER_DESCRIPTIONS[name]}
                 for name, value in (properties or {}).items()}
    return {"type": "object", "properties": described,
            "required": list(required), "additionalProperties": False}


TOKEN = {"type": "string", "minLength": 1, "maxLength": 128}
TEXT = {"type": "string", "maxLength": 4096, "pattern": r"^[^\x00-\x09\x0b-\x1f\x7f\ud800-\udfff]*$"}
BOOL = {"type": "boolean"}
QUERY = obj({key: TEXT for key in (
    "text", "op", "prop", "surface", "area_type", "region_type", "panel", "value")})
POINT = {"type": "array", "items": {"type": "number", "minimum": 0, "maximum": 1},
         "minItems": 2, "maxItems": 2}
MODS = obj({key: BOOL for key in ("shift", "ctrl", "alt", "oskey")})
_base = {"context": TOKEN, "target": TOKEN}


def action(name, props=None, required=()):
    return obj({**_base, "action": {"const": name}, **(props or {})},
               ("context", "target", "action", *required))


SCHEMAS = {
    "mixar_ui_context": obj({"release": BOOL, "instance": TOKEN, "session": TOKEN}),
    "mixar_ui_observe": obj({"query": QUERY, "image": BOOL, "window": TOKEN,
                             "limit": {"type": "integer", "minimum": 1, "maximum": 200},
                             "offset": {"type": "integer", "minimum": 0}}),
    "mixar_ui_act": {"type": "object", "oneOf": [
        action("click", {"double": BOOL, "modifiers": MODS}),
        action("set_text", {"text": TEXT, "enter": BOOL}, ("text",)),
        action("choose", {"item": TEXT}, ("item",)),
        action("press", {"key": {"type": "string", "pattern": "^[A-Z][A-Z_0-9]{0,31}$"},
                         "modifiers": MODS}, ("key",)),
        action("scroll", {"steps": {"type": "integer", "minimum": -20, "maximum": 20}}, ("steps",)),
        action("gesture", {"points": {"type": "array", "items": POINT,
                                       "minItems": 2, "maxItems": 256},
                           "button": {"enum": ["LEFTMOUSE", "MIDDLEMOUSE", "RIGHTMOUSE"]},
                           "modifiers": MODS,
                           "duration": {"type": "number", "minimum": 0.05, "maximum": 5}}, ("points",)),
    ]},
    "mixar_ui_wait": obj({"query": QUERY, "present": BOOL,
                           "timeout": {"type": "number", "minimum": 0, "maximum": 30}}, ("query",)),
    "mixar_ui_call_status": obj({"call_id": TOKEN}, ("call_id",)),
    "mixar_scenes": obj({}),
    "mixar_scene_new": obj({"name": {"type": "string", "minLength": 1, "maxLength": 63,
                                     "pattern": r"^[^\x00-\x1f\x7f]*$"}}),
    "mixar_scene_switch": obj({"session": TOKEN}, ("session",)),
    "mixar_projects": obj({}),
    "mixar_project_open": obj({"project": {"type": "string", "pattern": "^[0-9a-f]{16}$"},
                               "unsaved": {"enum": ["refuse", "save", "discard"], "default": "refuse"}},
                              ("project",)),
}
READ_ONLY = {"mixar_ui_observe", "mixar_ui_wait", "mixar_ui_call_status", "mixar_scenes", "mixar_projects"}
#: Native interface input: offered only while the user has opted in.
UI_INPUT = {"mixar_ui_observe", "mixar_ui_act", "mixar_ui_wait"}
#: Replaces the open document (its unsaved changes only with explicit consent).
DESTRUCTIVE = {"mixar_project_open"}
DOMAINS = {name: ("scenes" if name.startswith(("mixar_scene", "mixar_project")) else "ui") for name in SCHEMAS}
DESCRIPTIONS = {
    "mixar_ui_context": "Read UI readiness and current/bound scene. Explicitly select an instance or bind its current session after changing documents. Can release your input ownership.",
    "mixar_ui_observe": "Inspect visible Lampway controls and regions. Returns fresh opaque context/target handles; optionally a screenshot. Each control has a label (its text, else its tooltip). Pages with offset/limit (next_offset while more remain). Inspect before each action.",
    "mixar_ui_act": "Drive one observed Lampway control or region through native events. User input cancels control. Gesture points are normalized bottom-left region coordinates. Never blindly retry an uncertain action.",
    "mixar_ui_wait": "Wait for matching visible controls to appear/disappear, with a bounded deadline. No Python expressions.",
    "mixar_ui_call_status": "Recover a local UI action's durable receipt without executing it again.",
    "mixar_scenes": "List the open Lampway scene tabs: name, session id, state and which one is shown. Free.",
    "mixar_scene_new": "Create a new Lampway scene tab exactly like the app's + New scene (camera, light, the current tab's render/unit/colour settings), show it, and pin this connection to it so later scene and UI tools target it. Use this instead of bpy.data.scenes.new in a script. Free.",
    "mixar_scene_switch": "Pin this connection to an existing scene tab by its session id from mixar_scenes and show it in the app. Free.",
    "mixar_projects": "List the user's recent Lampway project files (name, folder, last modified, which is open) and whether the open file has unsaved changes. Use when the user asks to continue earlier work. Free.",
    "mixar_project_open": "Open a recent project by its id from mixar_projects, replacing the open file, and pin this connection to its shown scene tab so later tools target it. Refused while the open file is still working (an agent task, a render or running generation jobs). If the open file has unsaved changes it is refused unless unsaved is 'save' or 'discard': ask the user which first, never choose for them. Free.",
}


def validate(name, args):
    import json
    from jsonschema import Draft202012Validator
    if name not in SCHEMAS:
        raise UIError("unknown_tool", "Unknown UI tool")
    try:
        json.dumps(args, allow_nan=False)
    except (ValueError, TypeError):
        raise UIError("invalid_arguments", "UI arguments must be finite JSON values") from None
    if next(Draft202012Validator(SCHEMAS[name]).iter_errors(args), None):
        raise UIError("invalid_arguments", "Arguments do not match the UI tool schema")


def tools():
    return [{"name": name, "description": DESCRIPTIONS[name], "inputSchema": schema,
             "annotations": {"readOnlyHint": name in READ_ONLY, "destructiveHint": name in DESTRUCTIVE},
             "_meta": {"mixar/billing": {"invocation_credits": 0, "surface": "local_ui"},
                       "mixar/domain": DOMAINS[name]}}
            for name, schema in SCHEMAS.items()]
