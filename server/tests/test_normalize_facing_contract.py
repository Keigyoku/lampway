# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""An explicit facing decision must survive the agent registry and script boundary."""
import ast
import json

from lampway_server.agent import tools


def test_facing_margin_is_bounded_and_forwarded_without_a_guessed_default():
    tool = next(t for t in tools.TOOLS if t.name == "lampway_normalize_mesh")
    schema = tool.parameters["properties"]["facing_margin"]
    assert schema["type"] == "number"
    assert schema["minimum"] == 0 and schema["maximum"] == 1
    assert schema["description"] and "default" not in schema
    for supplied in ({"input": "raw", "plate": "Front.png"},
                     {"input": "raw", "plate": "Front.png", "facing_margin": 0.125}):
        tree = ast.parse(tools.script_for(tool.name, supplied))
        call = next(n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "call")
        assert json.loads(ast.literal_eval(call.args[1])) == supplied
