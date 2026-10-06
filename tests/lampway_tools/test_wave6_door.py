# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Wave 6 tool functions live in api_wave6.py and their Defs in agent/wave6_tools.py (the Wave 5 door test reads api.py and lampway_tools.py only).
This pins the three lists to each other: every api_wave6 tool passes the door, has a Def, and every Def names one of them."""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]


def test_every_wave6_tool_passes_the_door_and_has_exactly_one_def():
    r = run_script('''
import json
from mixar.modules.lampway_tools import api, api_wave6
print("RESULT", json.dumps({"door": list(api.TOOL_FUNCS), "w6": list(api_wave6.TOOLS),
                            "probe": api.call(api_wave6.TOOLS[0], '{"action": "nonsense", "character_id": "x"}')}))
''', timeout=120)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[-1]
    assert set(d["w6"]) <= set(d["door"]), sorted(set(d["w6"]) - set(d["door"]))
    defs = re.findall(r'api="(\w+)"', (ROOT / "server/lampway_server/agent/wave6_tools.py").read_text())
    assert sorted(defs) == sorted(d["w6"]) and len(defs) == len(set(defs))
    assert d["probe"]["ok"] is False and d["probe"]["help"]                         # the @tool envelope, not a traceback
