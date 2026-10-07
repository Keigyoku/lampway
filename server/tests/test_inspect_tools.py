# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""T1 registry, script-literal and strict argument boundary."""
import json

import pytest

from lampway_server.agent import lampway_tools as LT
from lampway_server.mcp import offered_tools


def test_inspect_is_offered_with_closed_bounded_input_schema():
    found = [tool for tool in offered_tools() if tool.name == "lampway_inspect"]
    assert found, "T1 inspection must be offered over MCP"
    schema = found[0].parameters
    assert schema["additionalProperties"] is False
    assert schema["properties"]["limit"]["minimum"] == 1
    assert schema["properties"]["names"]["maxItems"] == 200
    assert schema["properties"]["view"]["enum"] == ["scene", "objects", "object", "mesh", "uv", "parts", "layers", "relations", "file", "schema", "help"]


def test_inspect_script_is_one_api_call_and_refuses_unknown_arguments():
    definition = LT.BY_NAME.get("lampway_inspect")
    assert definition is not None, "T1 needs a Def before it can run"
    script = LT.build_script(definition, {"view": "object", "name": "'; evil() #"})
    assert "api.call(\"inspect\", " in script
    compile(script, "inspect-script", "exec")
    with pytest.raises(LT.BadArguments, match="unknown argument"):
        LT.build_script(definition, {"unexpected": True})
