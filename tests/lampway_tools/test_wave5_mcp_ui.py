# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connections panel (specs/mrmak/03 section 6): one card per MCP server with its readiness and scope, the Lampway row, Check and Show config. draw() reads cached state and makes no network call; Check
is the user's click (it starts a probe) and refuses while a script runs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import mcp_state, human_gate
from mixar.modules.lampway_tools.ui.operators import mcp_ops as MO
from mixar.modules.lampway_tools.ui.panels import lampway_panels as PANELS

INV = {"servers": [{"id": "codex:shared", "name": "shared", "client": "codex", "scope": "project", "enabled": True, "readiness": "configured", "transport": "http", "endpoint": "https://x.example.test",
                    "sources": [{"scope": "project", "path": "/p/.codex/config.toml", "effective": True}], "missing_env": [], "credential_names": ["X-Api"], "can_check": True, "connection": None},
                   {"id": "claude:needs", "name": "needs", "client": "claude", "scope": "project", "enabled": True, "readiness": "missing-env", "transport": "stdio", "endpoint": None,
                    "sources": [{"scope": "project", "path": "/p/.mcp.json", "effective": True}], "missing_env": ["LAMPWAY_MCP_X"], "credential_names": [], "can_check": False, "connection": None}],
       "problems": [{"path": "/p/bad.json", "message": "could not be read as valid JSON; it was skipped"}],
       "lampway": {"launcher": "python3", "launcher_ok": True, "opted_in": True, "eligible": False, "eligibility_detail": "desktop not connected", "tools_offered": 120, "notes": []}}
class Fake:
    def __init__(self): self.calls = []
    def inventory(self, client="all", scope="all"): self.calls.append("inventory"); return INV
    def check(self, sid): self.calls.append(("check", sid)); return {"id": sid, "connection": {"status": "available", "tool_count": 8, "more_tools": False, "stale": False}}
fake = Fake()
MO.CLIENT_FACTORY = lambda: fake
def call(op, **kw):
    try:
        return sorted(op(**kw))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:140]]
class Rec:
    def __init__(self, log): self.log = log
    def label(self, text="", icon=""): self.log.append(text)
    def operator(self, idname, text="", icon=""):
        self.log.append("op:" + idname); return type("P", (), {})()
    def row(self, align=False): return self
    def box(self): return self
    def column(self, align=False): return self
'''


def go(body, tmp_path):
    return run(tmp_path, PRE + body)


def test_the_panel_draws_cards_and_the_lampway_row_from_the_cache_with_no_network_call(tmp_path):
    r = go('''
mcp_state.update(INV)
fake.calls.clear()
log = []
panel = PANELS.LAMPWAY_PT_mcp
panel.layout = Rec(log)
panel.draw(panel, bpy.context)
print("RESULT", json.dumps({"log": log, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[0]
    assert d["calls"] == []
    log = d["log"]
    assert "Lampway: launcher python3, 120 tools, not eligible (desktop not connected)" in log
    assert "codex / shared: configured (project)" in log and "claude / needs: missing-env (project)" in log and "needs LAMPWAY_MCP_X" in log
    assert log.count("op:lampway.mcp_check") == 1 and any("could not be read as valid JSON" in x for x in log)         # Check only where the entry can be checked


def test_check_is_a_click_that_stores_the_result_and_refuses_while_a_script_runs(tmp_path):
    r = go('''
mcp_state.update(INV)
res = {}
res["user"] = call(bpy.ops.lampway.mcp_check, server_id="codex:shared")
state_after = mcp_state.STATE["servers"][0]["connection"]
with human_gate.scripting():
    res["script"] = call(bpy.ops.lampway.mcp_check, server_id="codex:shared")
res["refresh"] = call(bpy.ops.lampway.mcp_refresh)
print("RESULT", json.dumps({"r": res, "conn": state_after, "calls": [c if isinstance(c, str) else list(c) for c in fake.calls]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["r"]["user"] == ["FINISHED"] and d["r"]["script"][0] == "REFUSED" and d["r"]["refresh"] == ["FINISHED"]
    assert d["conn"]["status"] == "available" and d["conn"]["tool_count"] == 8 and d["calls"].count(["check", "codex:shared"]) == 1
