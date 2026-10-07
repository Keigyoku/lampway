# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ten local MCP tools are named ``lampway_*`` for AI apps; internal ``mixar_*`` keys are never advertised (issue #2 G15).

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


def test_every_tool_is_offered_only_under_its_canonical_name():
    offered = {t['name']: t for t in aliases.expose(schema.tools())}
    assert len(offered) == len(TEN)
    for old,new in TEN.items():
        assert old not in offered
        assert offered[new]['inputSchema'] == schema.SCHEMAS[old]


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


def test_g15_public_catalogue_excludes_deprecated_names_and_mentions():
    offered = aliases.expose(schema.tools())
    assert {tool['name'] for tool in offered} == set(TEN.values())
    for tool in offered:
        assert all(old not in tool['description'] for old in TEN), tool


def test_g15_whole_catalogue_size_is_bounded():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
    from lampway_server.mcp import McpServer
    public = aliases.expose(schema.tools() + McpServer(None, None).tools_payload())
    # Measured full catalogue, including opt-in UI. Less than audit's 335,426 B.
    size = len(json.dumps({'tools': public}, ensure_ascii=False).encode())
    assert size <= 335000, size
