# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The agent reaches every tool through ``api.call(name, payload)``, which answers 'no tool function' for a name outside TOOL_FUNCS. A tool that is a function in api.py and a Def on the server
but not in that door is a tool the agent cannot run: this pins the three lists to each other."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def _door():
    r = run_script('''
import json
from mixar.modules.lampway_tools import api
print("RESULT", json.dumps({"door": list(api.TOOL_FUNCS)}))
''', timeout=120)
    assert r.rc == 0, r.out[-1500:]
    return r.results[-1]


def test_every_server_tool_def_names_a_function_the_door_lets_through():
    door = set(_door()["door"])
    defs = set(re.findall(r'api="(\w+)"', (ROOT / "server/lampway_server/agent/lampway_tools.py").read_text()))
    assert defs, "no Def with an api name found"
    assert sorted(defs - door) == [], f"Defs the agent cannot run (api.call refuses them): {sorted(defs - door)}"


def test_every_tool_function_in_api_is_in_the_door():
    src = (ROOT / "src/scripts/mixar/modules/lampway_tools/api.py").read_text()
    tools = set(re.findall(r"@tool\ndef (\w+)\(", src))
    door = set(_door()["door"])
    assert sorted(tools - door) == [], f"@tool functions missing from TOOL_FUNCS: {sorted(tools - door)}"
