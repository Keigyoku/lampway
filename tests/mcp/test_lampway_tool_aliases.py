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


def _assert_full_public_registry_has_no_deprecated_names_or_descriptions():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server'))
    from lampway_server.agent import tools as registry
    from lampway_server.mcp import McpServer
    raw_server = registry.TOOLS
    public = aliases.expose(schema.tools() + McpServer(None, None).tools_payload())
    for name, description in [(t.name, t.description) for t in raw_server] + [(t['name'], t['description']) for t in public]:
        assert not name.startswith("mixar_"), name
        assert not __import__("re").search(r"\bmixar_[a-zA-Z0-9_]+", description), (name, description)
    assert len({tool['name'] for tool in public}) == len(public)


def test_deprecated_names_and_mentions_are_absent_from_the_whole_real_registry():
    _assert_full_public_registry_has_no_deprecated_names_or_descriptions()


@pytest.mark.parametrize("old_name", ["mixar_ui_act", "mixar_future_tool"])
def test_whole_registry_alias_gate_rejects_a_backend_description_plant(monkeypatch, old_name):
    from lampway_server.agent import tools as registry
    from lampway_server.agent.providers.base import ToolSpec
    monkeypatch.setattr(registry, 'TOOLS', [*registry.TOOLS, ToolSpec('lampway_alias_plant', f'First use {old_name}.', {'type':'object'})])
    with pytest.raises(AssertionError, match=old_name):
        _assert_full_public_registry_has_no_deprecated_names_or_descriptions()


def _assert_local_schema_debt_absent(tools=None):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'server/tests'))
    from test_tool_schema_ratchet import _counts
    from lampway_server.agent.providers.base import ToolSpec
    registry = aliases.expose(schema.tools()) if tools is None else tools
    objects = [ToolSpec(t['name'], t['description'], t['inputSchema']) for t in registry]
    undescribed, unbounded = _counts(objects)
    assert not undescribed, undescribed
    assert not unbounded, unbounded


def test_every_local_ui_parameter_is_described_and_numeric_bounds_are_recursive():
    _assert_local_schema_debt_absent()


def test_local_nested_schema_negative_control_cannot_escape_the_gate():
    from copy import deepcopy
    tools = deepcopy(aliases.expose(schema.tools()))
    tools[0]['inputSchema']['properties']['planted'] = {'type':'object', 'description':'Negative control', 'properties':{'hidden':{'type':'number'}}}
    with pytest.raises(AssertionError, match='hidden'):
        _assert_local_schema_debt_absent(tools)
