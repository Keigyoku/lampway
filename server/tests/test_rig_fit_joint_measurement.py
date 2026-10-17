# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Own-rig centering is available through the existing tool and safe payload."""
from lampway_server.agent import lampway_tools as LT
import ast
import json


def test_existing_fit_tool_describes_and_forwards_centred_rig_selector():
    row = next(d for d in LT.DEFS if d.name == "lampway_rig_fit_template")
    assert "centre:rig:" in row.description
    assert "procedural body" in row.description
    assert "3 cm margin" not in row.description
    payload = {"example":"example", "joints":"centre:rig:own_armature", "dry_run":True}
    script = ast.parse(LT.build_script(row,payload))
    call = next(n for n in ast.walk(script) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "call")
    assert json.loads(ast.literal_eval(call.args[1])) == payload
