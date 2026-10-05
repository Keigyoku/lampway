# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Public names of the ten local tools.

AI apps see ``lampway_*``. Inside the connector the original ``mixar_*`` names stay the keys (schema, lease, rebinding, the app's own dispatcher), so the
rename is one table at the MCP boundary: ``expose`` lists each tool under both names (the old one marked deprecated) and ``internal_name`` maps a call
back. The old names are kept for one release.
"""

import copy

OLD_TO_NEW = {
    "mixar_scenes": "lampway_scenes",
    "mixar_scene_new": "lampway_scene_new",
    "mixar_scene_switch": "lampway_scene_switch",
    "mixar_projects": "lampway_projects",
    "mixar_project_open": "lampway_project_open",
    "mixar_ui_context": "lampway_ui_context",
    "mixar_ui_observe": "lampway_ui_observe",
    "mixar_ui_act": "lampway_ui_act",
    "mixar_ui_wait": "lampway_ui_wait",
    "mixar_ui_call_status": "lampway_ui_call_status",
}
NEW_TO_OLD = {new: old for old, new in OLD_TO_NEW.items()}


def internal_name(name):
    """The name the connector's own code knows a tool by."""
    return NEW_TO_OLD.get(name, name)


def expose(tools):
    """The tool list an AI app is shown: every local tool under its Lampway name, and under its old name as a deprecated alias."""
    out = []
    for tool in tools:
        new = OLD_TO_NEW.get(tool["name"])
        if new is None:
            out.append(tool)
            continue
        renamed = copy.deepcopy(tool)
        renamed["name"] = new
        alias = copy.deepcopy(tool)
        alias["description"] = f"Deprecated alias of {new}. {tool['description']}"
        out += [renamed, alias]
    return out
