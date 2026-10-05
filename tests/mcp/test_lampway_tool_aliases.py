# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ten local MCP tools are named ``lampway_*`` for AI apps; the old ``mixar_*`` names stay for one release as deprecated aliases (rebrand M6).

The connector also prints a setup that says ``lampway`` (``python mcp.py --config claude|codex``).
"""

import json
import tomllib

import pytest

from mixar import mcp as launcher
from mixar.modules.common.ui_control.core import schema
from mixar.modules.mcp_bridge.core import aliases

TEN = {"mixar_scenes": "lampway_scenes", "mixar_scene_new": "lampway_scene_new", "mixar_scene_switch": "lampway_scene_switch",
       "mixar_projects": "lampway_projects", "mixar_project_open": "lampway_project_open", "mixar_ui_context": "lampway_ui_context",
       "mixar_ui_observe": "lampway_ui_observe", "mixar_ui_act": "lampway_ui_act", "mixar_ui_wait": "lampway_ui_wait",
       "mixar_ui_call_status": "lampway_ui_call_status"}


def test_the_table_is_exactly_the_ten_local_tools():
    assert aliases.OLD_TO_NEW == TEN
    assert set(aliases.OLD_TO_NEW) == set(schema.SCHEMAS)


def test_every_tool_is_offered_under_both_names_and_the_old_one_says_deprecated():
    offered = {t["name"]: t for t in aliases.expose(schema.tools())}
    assert len(offered) == 2 * len(TEN)
    for old, new in TEN.items():
        assert offered[new]["description"] == schema.DESCRIPTIONS[old]
        assert offered[old]["description"].startswith(f"Deprecated alias of {new}.")
        assert offered[new]["inputSchema"] == offered[old]["inputSchema"]


def test_a_call_by_either_name_reaches_the_same_internal_tool():
    for old, new in TEN.items():
        assert aliases.internal_name(new) == old and aliases.internal_name(old) == old
    assert aliases.internal_name("render_viewport") == "render_viewport"


def test_hidden_interface_tools_stay_hidden_under_the_new_names():
    shown = {t["name"] for t in aliases.expose([t for t in schema.tools() if t["name"] not in schema.UI_INPUT])}
    assert not shown & {"lampway_ui_act", "mixar_ui_act", "lampway_ui_observe", "lampway_ui_wait"}


def test_the_printed_setup_says_lampway():
    claude = json.loads(launcher.configuration("claude", python="/usr/bin/python3"))
    assert list(claude["mcpServers"]) == ["lampway"]
    codex = tomllib.loads(launcher.configuration("codex", python="/usr/bin/python3"))
    assert list(codex["mcp_servers"]) == ["lampway"]
