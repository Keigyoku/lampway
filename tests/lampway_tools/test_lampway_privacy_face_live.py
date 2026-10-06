# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 12 in the real binary: switching a route on is the user's click and needs the confirm row; a refusal's
override writes through POST /app/egress/override; the Privacy panel draws the route rows, the confirm row, the refusal
and the log from the cache with no network call (fake client: nothing reaches a server)."""

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
from mixar.modules.lampway_tools.ui import privacy as PV

ROUTES = [{"id": "openrouter", "label": "OpenRouter", "enabled": False, "retention": "per model", "training": "per model",
           "privacy_class": "conditional", "hosts": ["openrouter.ai"], "last_used": None},
          {"id": "fal", "label": "fal.ai", "enabled": True, "retention": "unknown (terms not read)", "training": "unknown",
           "privacy_class": "unknown", "hosts": ["fal.ai"], "last_used": 1.0}]
LOG = [{"t": 1.0, "event": "send", "route": "fal", "provider": "fal.ai", "kind": "image", "bytes": 1200},
       {"t": 2.0, "event": "refused", "route": "fal", "kind": "image", "asset_ids": ["a1"], "content_class": "private",
        "reason": "this asset is private and fal.ai keeps what it is sent: use a verified route, run it locally, or flip the per-asset override (logged)"}]
class FakeClient:
    def __init__(self): self.calls = []
    def state(self): self.calls.append("state"); return {"routes": ROUTES, "indicator": {"over_the_wire": False, "active": [], "last": None}, "overrides": []}
    def set_route(self, route, on): self.calls.append(["set", route, on]); return {"route": route, "enabled": on}
    def override(self, asset_id, route): self.calls.append(["override", asset_id, route]); return {"ok": True}
    def log(self, limit=20): self.calls.append("log"); return LOG
    def export(self): return ""
fake = FakeClient()
PV.CLIENT_FACTORY = lambda: fake
def call(op, **kw):
    try:
        return sorted(op(**kw))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:160]]
class Rec:
    def __init__(self, log): self.log = log; self.alert = False; self.enabled = True
    def label(self, text="", icon="NONE", icon_value=0, **k): self.log.append(("label", text))
    def operator(self, idname, text="", icon="NONE", icon_value=0, depress=False, **k):
        self.log.append(("op", idname, text, depress)); return type("P", (), {})()
    def prop(self, *a, **k): pass
    def row(self, align=False, **k): return Rec(self.log)
    def box(self): return Rec(self.log)
    def column(self, align=False, **k): return Rec(self.log)
    def split(self, **k): return Rec(self.log)
    def separator(self, **k): pass
'''


def go(body, tmp_path):
    return run(tmp_path, PRE + body)


def test_route_switch_refuses_a_script(tmp_path):
    r = go('''
with human_gate.scripting():
    res = call(bpy.ops.lampway.egress_route, route="openrouter", enabled=True)
    res2 = call(bpy.ops.lampway.egress_route, route="openrouter", enabled=True, confirm=True)
print("RESULT", json.dumps({"res": res, "res2": res2, "calls": fake.calls, "pending": egress_state.PENDING["route"]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    for res in (d["res"], d["res2"]):
        assert res[0] == "REFUSED" and "A script cannot open a route: switch it on in Privacy yourself" in res[1], d
    assert d["calls"] == [] and d["pending"] == ""


def test_route_switch_needs_the_confirm_row(tmp_path):
    r = go('''
egress_state.update(fake.state(), fake.log())
fake.calls.clear()
first = call(bpy.ops.lampway.egress_route, route="openrouter", enabled=True)
after_first = list(fake.calls)
log = []
PV.draw_privacy(Rec(log), bpy.context)
second = call(bpy.ops.lampway.egress_route, route="openrouter", enabled=True, confirm=True)
print("RESULT", json.dumps({"first": first, "after_first": after_first, "log": log, "second": second, "calls": fake.calls,
                            "pending": egress_state.PENDING["route"]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["first"] == ["FINISHED"] and d["after_first"] == [], "the first click only opens the row"
    log = [tuple(e) for e in d["log"]]
    assert ("label", "Let data leave for openrouter.ai?") in log
    assert ("op", "lampway.egress_route", "Let it leave", True) in log, log
    assert d["second"] == ["FINISHED"] and ["set", "openrouter", True] in d["calls"] and d["pending"] == ""


def test_refusal_override_writes_through_the_server(tmp_path):
    r = go('''
egress_state.update(fake.state(), fake.log())
fake.calls.clear()
log = []
PV.draw_privacy(Rec(log), bpy.context)
res = call(bpy.ops.lampway.egress_override, asset_id="a1", route="fal")
with human_gate.scripting():
    res_script = call(bpy.ops.lampway.egress_override, asset_id="a1", route="fal")
print("RESULT", json.dumps({"log": log, "res": res, "res_script": res_script, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    texts = [e[1] if e[0] == "label" else e[2] for e in d["log"]]
    assert "a private asset on a route that may keep it" in texts
    for way in ("Use OpenRouter, zero retention", "Run it here instead", "Allow this asset once (logged)"):
        assert way in texts, texts
    assert d["res"] == ["FINISHED"] and d["res_script"][0] == "REFUSED"
    assert d["calls"].count(["override", "a1", "fal"]) == 1


def test_the_panel_makes_no_network_call_and_shows_no_content(tmp_path):
    r = go('''
egress_state.update(fake.state(), fake.log())
fake.calls.clear()
log = []
PV.draw_privacy(Rec(log), bpy.context)
print("RESULT", json.dumps({"log": log, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["calls"] == []
    texts = [e[1] if e[0] == "label" else e[2] for e in d["log"]]
    assert "OpenRouter" in texts and "fal.ai" in texts and "Nothing is leaving this machine" in texts
