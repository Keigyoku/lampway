# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Privacy panel (specs/cloud/egress_consent.md section 5): every route with its switch and policy text, a loud DATA LEAVING badge, the last log rows; drawn from cached state with zero network
calls. Opting a route in is the USER's click: it refuses while a script (an agent's, a worker's, the bridge's) runs."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import egress_state, human_gate
from mixar.modules.lampway_tools.ui.operators import egress_ops as EO
from mixar.modules.lampway_tools.ui import privacy as PANELS   # the panel moved with contract 12

ROUTES = [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "retention": "per model", "training": "per model", "privacy_class": "conditional", "last_used": None},
          {"id": "fal", "label": "fal.ai", "enabled": True, "retention": "unknown (terms not read)", "training": "unknown", "privacy_class": "unknown", "last_used": 1.0}]
class FakeClient:
    def __init__(self): self.calls = []; self.lit = False
    def state(self): self.calls.append("state"); return {"routes": ROUTES, "indicator": {"over_the_wire": self.lit, "active": ["fal"] if self.lit else [], "last": None}, "overrides": []}
    def set_route(self, route, on): self.calls.append(("set", route, on)); return {"route": route, "enabled": on}
    def log(self, limit=20): self.calls.append("log"); return [{"event": "send", "route": "fal", "provider": "queue.fal.run", "kind": "image", "bytes": 1200, "t": 1.0}]
    def export(self): self.calls.append("export"); return '{"event": "send"}\\n'
fake = FakeClient()
EO.CLIENT_FACTORY = lambda: fake
def call(op, **kw):
    try:
        return sorted(op(**kw))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:140]]
class Rec:
    def __init__(self, log): self.log = log; self.alert = False
    def label(self, text="", icon="", **k): self.log.append(text)
    def operator(self, idname, text="", icon="", **k):
        self.log.append("op:" + idname); self.log.append(text)
        log = self.log
        class P:
            def __setattr__(self, name, value):
                if name == "hover": log.append("hover:" + value)
                object.__setattr__(self, name, value)
        return P()
    def prop(self, *a, **k): pass
    def row(self, align=False): return self
    def box(self): return self
    def column(self, align=False): return self
    def separator(self): pass
'''


def go(body, tmp_path):
    return run(tmp_path, PRE + body)


def test_the_panel_lists_every_route_off_or_on_with_its_policy_and_makes_no_network_call(tmp_path):
    r = go('''
egress_state.update(fake.state(), fake.log())
fake.calls.clear()
log = []
panel = PANELS.LAMPWAY_PT_privacy
panel.layout = Rec(log)
panel.draw(panel, bpy.context)
print("RESULT", json.dumps({"log": log, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-1500:]
    d = r.results[0]
    assert d["calls"] == []
    log = d["log"]
    # Contract 12's calm pass: a row is the name, the shield and the switch; the policy is the name's hover.
    assert log[log.index("OpenRouter") + 1].startswith("hover:") and "Retention: per model. Training: per model" in log[log.index("OpenRouter") + 1]
    assert "Retention: unknown (terms not read)" in log[log.index("fal.ai") + 1]
    assert log[log.index("fal.ai") + 3] == "On" and log[log.index("OpenRouter") + 3] == "Off"
    assert "op:lampway.egress_route" in log
    assert not any("Sending now" in x for x in d["log"]) and "Nothing is leaving this machine" in d["log"]


def test_the_badge_is_loud_while_data_leaves_and_the_log_rows_show_what_went_where(tmp_path):
    r = go('''
fake.lit = True
EO.refresh_state()
log = []
panel = PANELS.LAMPWAY_PT_privacy
panel.layout = Rec(log)
panel.draw(panel, bpy.context)
print("RESULT", json.dumps({"log": log}))
''', tmp_path)
    assert r.rc == 0, r.out[-1500:]
    log = r.results[0]["log"]
    # The badge is the magenta wire and the word Sending (contract 12, decision F3), not a red DATA LEAVING.
    assert "Sending now: fal.ai" in log, log
    assert "image, 1200 bytes" in log and any(x.startswith("hover:host queue.fal.run") for x in log), log


def test_opting_a_route_in_is_the_users_click_and_refuses_while_a_script_runs(tmp_path):
    r = go('''
res = {}
res["user"] = call(bpy.ops.lampway.egress_route, route="openrouter", enabled=True)            # opens the confirm row only
res["user_confirm"] = call(bpy.ops.lampway.egress_route, route="openrouter", enabled=True, confirm=True)
with human_gate.scripting():
    res["script"] = call(bpy.ops.lampway.egress_route, route="fal", enabled=False)
    res["script_export"] = call(bpy.ops.lampway.egress_export)
res["export"] = call(bpy.ops.lampway.egress_export)
print("RESULT", json.dumps({"r": res, "calls": [c if isinstance(c, str) else list(c) for c in fake.calls], "text": [t.name for t in bpy.data.texts]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["r"]["user"] == ["FINISHED"] and d["r"]["script"][0] == "REFUSED" and d["r"]["export"] == ["FINISHED"]
    assert ["set", "openrouter", True] in d["calls"] and ["set", "fal", False] not in d["calls"] and "LW_egress_log" in d["text"]
