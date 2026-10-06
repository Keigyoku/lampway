# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Blender side of the cockpit (specs/mrmak/01 section 10, test 10): the panel draws chips from cached state with ZERO network calls; the operators are thin buttons over the client; the
user's clicks refuse while a script runs; unregistering leaves the herdr server alone. Real binary; the client is a fake."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import workbench_state, human_gate
from mixar.modules.lampway_tools.ui.operators import workbench_ops as WO
from mixar.modules.lampway_tools.ui.panels import lampway_panels as PANELS

class FakeClient:
    def __init__(self): self.calls = []
    def home(self): self.calls.append("home"); return {"server": {"running": True, "method": "systemd"}, "sessions": SESSIONS, "offered": []}
    def screen(self, sid, lines=70): self.calls.append(("screen", sid)); return "\\n".join(f"line {i}" for i in range(100))
    def send(self, sid, text, submit=True): self.calls.append(("send", sid, text)); return {"sent": True}
    def close(self, sid, confirm): self.calls.append(("close", sid, confirm)); return {"closed": sid}
    def start_server(self): self.calls.append("start"); return {"already_running": False, "method": "setsid"}
    def stop_server(self, confirm): self.calls.append(("stop", confirm)); return {"stopped": True}
    def reconcile(self): self.calls.append("reconcile"); return {"server": "running", "adopted": ["a1"], "ended": [], "unadopted": [], "new_panes": 0}
    def create(self, agent, name, cwd="", task="", command=None): self.calls.append(("create", agent, name)); return {"name": name}

SESSIONS = [{"id": "a1", "name": "Chest fit audit", "agent": "claude", "state": "live", "activity": "working", "unread": True},
            {"id": "b2", "name": "Boots seed read", "agent": "codex", "state": "ended", "activity": "idle", "unread": False},
            {"id": "c3", "name": "Idle one", "agent": "shell", "state": "live", "activity": "idle", "unread": False}]
def call(op, **kw):
    try:
        return sorted(op(**kw))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:120]]
fake = FakeClient()
WO.CLIENT_FACTORY = lambda: fake
'''


def go(body, tmp_path=None):
    return run(tmp_path, PRE + body)


def test_the_chips_come_from_the_session_record(tmp_path):
    r = go('''
chips = [workbench_state.chips(s) for s in SESSIONS]
print("RESULT", json.dumps(chips))
''', tmp_path)
    assert r.rc == 0, r.out[-1500:]
    assert r.results[0] == [["working", "unread"], ["ended"], ["idle"]]


def test_the_panel_draws_the_rows_and_chips_with_zero_network_calls(tmp_path):
    r = go('''
workbench_state.update({"server": {"running": True, "method": "systemd"}, "sessions": SESSIONS, "offered": []})
class Rec:
    def __init__(self, log): self.log = log
    def label(self, text="", icon="", **k): self.log.append(text)   # contract 10: the row's Spark is an icon_value
    def operator(self, idname, text="", icon="", **k): self.log.append("op:" + idname); return type("P", (), {})()
    def row(self, align=False): return self
    def box(self): return self
    def column(self, align=False): return self
    def separator(self): pass
log = []
panel = PANELS.LAMPWAY_PT_cockpit
panel.layout = Rec(log)
panel.draw(panel, bpy.context)
print("RESULT", json.dumps({"log": log, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-1500:]
    log, calls = r.results[0]["log"], r.results[0]["calls"]
    assert calls == [] and any("Chest fit audit (claude)  [working, unread]" in x for x in log) and any("[ended]" in x for x in log)
    assert "op:lampway.wb_stop_server" in log and "op:lampway.wb_new" in log and not any(x == "op:lampway.wb_start_server" for x in log)


def test_read_to_text_keeps_the_last_70_lines_in_a_text_datablock_and_the_send_and_close_are_clicks(tmp_path):
    r = go('''
WO.refresh_state()
res = {}
res["read"] = call(bpy.ops.lampway.wb_read_to_text, session_id="a1")
t = bpy.data.texts["LW_session_Chest fit audit"]
res["lines"] = [ln.body for ln in t.lines]
res["send"] = call(bpy.ops.lampway.wb_send, session_id="a1", text="hello")
res["close_no_confirm"] = call(bpy.ops.lampway.wb_close, session_id="a1", confirm=False)
res["close_yes"] = call(bpy.ops.lampway.wb_close, session_id="a1", confirm=True)
with human_gate.scripting():                                   # an agent's script is running: the user's clicks refuse
    res["gated_send"] = call(bpy.ops.lampway.wb_send, session_id="a1", text="from a script")
    res["gated_start"] = call(bpy.ops.lampway.wb_start_server)
    res["gated_stop"] = call(bpy.ops.lampway.wb_stop_server, confirm=True)
print("RESULT", json.dumps({"r": {k: v for k, v in res.items() if k != "lines"}, "lines": res["lines"], "calls": [c if isinstance(c, str) else list(c) for c in fake.calls]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert len(d["lines"]) == 70 and d["lines"][0] == "line 30" and d["lines"][-1] == "line 99"
    assert d["r"]["send"] == ["FINISHED"] and d["r"]["close_no_confirm"][0] == "REFUSED" and d["r"]["close_yes"] == ["FINISHED"]
    assert all(d["r"][k][0] == "REFUSED" for k in ("gated_send", "gated_start", "gated_stop"))
    assert ["send", "a1", "hello"] in d["calls"] and ["close", "a1", True] in d["calls"] and ["send", "a1", "from a script"] not in d["calls"] and "start" not in d["calls"]
    assert not any(isinstance(c, list) and c[0] == "close" and c[2] is False for c in d["calls"])


def test_reconcile_reports_what_it_adopted_and_unregistering_the_cockpit_calls_no_stop(tmp_path):
    r = go('''
res = call(bpy.ops.lampway.wb_reconcile)
msg = bpy.context.scene.lampway_tools.last_message
for cls in list(WO.classes):
    try: bpy.utils.unregister_class(cls)
    except Exception: pass
print("RESULT", json.dumps({"r": res, "msg": msg, "calls": [c if isinstance(c, str) else list(c) for c in fake.calls]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["r"] == ["FINISHED"] and "adopted 1" in d["msg"] and "new panes: 0" in d["msg"]
    assert not any(isinstance(c, list) and c[0] == "stop" for c in d["calls"]) and "start" not in d["calls"]          # unregister stopped and started nothing
