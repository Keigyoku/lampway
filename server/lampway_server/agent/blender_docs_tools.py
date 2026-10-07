# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only offline Blender API/manual tool. No Blender execution or egress."""
import asyncio
import re
from jsonschema import Draft202012Validator
from .providers.base import ToolSpec
from ..blender_docs import index

NAME = "lampway_blender_docs"
NAMES = {NAME}
PARAMETERS = {
    "type": "object", "additionalProperties": False,
    "properties": {
        "view": {"type": "string", "enum": ["get", "search", "help"]},
        "identifier": {"type": "string"}, "query": {"type": "string"},
        "scope": {"type": "string", "enum": ["api", "manual"], "default": "api"},
        "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
        "context": {"type": "integer", "minimum": 0, "maximum": 10, "default": 0},
        "full": {"type": "boolean", "default": False},
    },
}


def specs():
    return [ToolSpec(NAME, "Look up Blender API identifiers or search the pinned offline API/manual for Lampway's Blender release. Read-only, no network; view=get identifier=bpy.types.Object.location, view=search query=bevel scope=manual; view=help lists defaults and refusals.", PARAMETERS)]


async def call(name, arguments):
    if name not in NAMES:
        return _refuse("unknown_tool", f"unknown documentation tool {name!r}"), True
    if not isinstance(arguments, dict):
        return _refuse("bad_argument", "arguments must be an object"), True
    unknown = sorted(set(arguments) - set(PARAMETERS["properties"]))
    if unknown:
        return _refuse("unknown_argument", "unknown arguments: " + ", ".join(unknown)), True
    errors = sorted(Draft202012Validator(PARAMETERS).iter_errors(arguments), key=lambda error: str(error.path))
    if errors:
        return _refuse("bad_argument", errors[0].message), True
    view = arguments.get("view", "home")
    identifier = arguments.get("identifier", "")
    query = arguments.get("query", "")
    scope = arguments.get("scope", "api")
    identifier_pattern = (r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*" if scope == "manual"
                          else r"\*|[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*(?:\.\*)?")
    if view == "get" and not re.fullmatch(identifier_pattern, identifier):
        return _refuse("bad_argument", "get needs a fully qualified API identifier or X.*, or a manual page identifier with scope=manual"), True
    if view == "search" and not query.strip():
        return _refuse("bad_argument", "search needs a non-empty query"), True
    return await asyncio.to_thread(_run, arguments, view)


def _refuse(code, error):
    return {"view": "error", "count": 0, "total": 0, "data": {}, "error": error, "code": code,
            "help": [f"{NAME} view=help"]}


def _run(arguments, view):
    scope = arguments.get("scope", "api")
    help_ = [f"{NAME} view=get identifier=<id> scope={scope}", f'{NAME} view=search query="<query>" scope={scope}']
    limit, full = arguments.get("limit", 10), arguments.get("full", False)
    if view == "home":
        meta = index.manifest()
        data = {"versions": {"blender": meta["blender_version_string"], "core": meta["core_version"]},
                "index_sizes": meta["file_counts"], "manual_revision": meta["manual_revision"],
                "manual_pin_kind": meta["manual_pin_kind"]}
        count = total = 0
    elif view == "help":
        data = {"arguments": PARAMETERS["properties"], "defaults": {"scope": "api", "limit": 10, "context": 0, "full": False},
                "views": ["home", "get", "search", "help"],
                "refusals": ["unknown_argument", "bad_argument"],
                "fields": {"get": ["identifier", "kind", "signature", "doc", "children"],
                           "search": ["rank", "identifier", "title", "snippet"]}}
        count = total = 0
    elif view == "get":
        if scope == "manual":
            data, count, total = index.get_manual(arguments["identifier"], full)
        else:
            data, count, total = index.get(arguments["identifier"], limit, full)
        if not count:
            help_ = [f'{NAME} view=search query="<identifier>" scope={scope}']
        elif not full and "full=true" in data.get("doc", ""):
            help_.append(f'{NAME} view=get identifier={arguments["identifier"]} scope={scope} full=true')
    else:
        data, count, total = index.search(arguments["query"], arguments.get("scope", "api"), limit, arguments.get("context", 0), full)
    return {"tool": NAME, "description": "Read the pinned Blender API and manual offline",
            "view": view, "count": count, "total": total, "data": data, "help": help_}, False
