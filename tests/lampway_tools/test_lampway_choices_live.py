# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Choices window in the real binary (specs/choices/choices_face.md section 10): draw reads the cache; every write
refuses a script; the Providers button opens Choices on Agents; reordering the chain writes the new order; a proposal is
accepted for this project; and a server that has no Choices yet still lets you reach the old Providers dialog. Fake
client: nothing reaches a server."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import choices_state, human_gate, studio_client
from mixar.modules.lampway_tools.ui import choices as CH

def opt(oid, rank, **kw):
    o = {"id": oid, "label": oid.split(":", 1)[-1], "provider": oid.split(":")[0], "model": oid.split(":", 1)[-1], "runs": "openrouter.ai",
         "connection": {"id": "openrouter", "state": "connected"}, "route": {"id": "openrouter", "on": True}, "cost": {"basis": "unknown"},
         "retention": "zdr", "acknowledged": None, "quality": [], "verdict": "ok", "rank": rank}
    o.update(kw)
    return o
LISTING = {"doc_version": 3, "groups": [
    {"id": "agents", "label": "Agents", "purposes": [{"id": "agent.main", "label": "Main agent", "group": "agents", "cue": "preferred",
        "now": {"option": "chatgpt_plan:gpt-5.5", "label": "gpt-5.5", "scope": "global", "reason": "preferred"}}]},
    {"id": "images", "label": "Images", "purposes": [{"id": "images.plates", "label": "Plates", "group": "images", "cue": "fallback",
        "why": "studio:tripo is off", "now": {"option": "openrouter:a", "label": "a", "scope": "global", "reason": "fallback"}}]}],
    "proposals_open": 1}
PLATES = dict(LISTING["groups"][1]["purposes"][0], params={}, chain=[
    opt("studio:tripo", 0, verdict="skipped", skipped={"constraint": "route", "text": "route studio:tripo is off"}, route={"id": "studio:tripo", "on": False}),
    opt("openrouter:a", 1), opt("openrouter:b", 2)], other_options=[], scopes={"global": {"preferred": "studio:tripo"}}, history=[],
    proposals=[{"id": "p1", "purpose": "images.plates", "change": {"preferred": "openrouter:b"}, "origin": "agent", "state": "open", "reason": "flatter albedo"}])
class FakeClient:
    def __init__(self, missing=False): self.calls = []; self.missing = missing
    def list(self, project=None):
        self.calls.append("list")
        if self.missing: raise studio_client.StudioError("the server answered HTTP 404")
        return LISTING
    def one(self, pid, project=None): self.calls.append(["one", pid]); return PLATES
    def proposals(self, state="open"): self.calls.append("proposals"); return {"proposals": PLATES["proposals"]}
    def put(self, pid, body): self.calls.append(["put", pid, body]); return PLATES
    def clear(self, pid, project=None): self.calls.append(["clear", pid]); return PLATES
    def accept(self, prop_id, scope, project=None): self.calls.append(["accept", prop_id, scope]); return PLATES
    def decline(self, prop_id): self.calls.append(["decline", prop_id]); return {"declined": prop_id}
    def acknowledge(self, option, private): self.calls.append(["ack", option, private]); return {}
fake = FakeClient()
CH.CLIENT_FACTORY = lambda: fake
def call(op, **kw):
    try:
        return sorted(op(**kw))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:200]]
class Rec:
    def __init__(self, log): self.log = log; self.alert = False; self.enabled = True; self.active = True
    def label(self, text="", **k): self.log.append(text)
    def operator(self, idname, text="", **k):
        self.log.append(idname + "|" + text); return type("P", (), {})()
    def prop(self, data, name, text="", **k): self.log.append("prop:" + name)
    def row(self, **k): return Rec(self.log)
    def column(self, **k): return Rec(self.log)
    def box(self): return Rec(self.log)
    def split(self, **k): return Rec(self.log)
    def separator(self, **k): pass
    def panel(self, idname, default_closed=False): return Rec(self.log), Rec(self.log)
'''


def go(body, tmp_path):
    return run(tmp_path, PRE + body)


def test_draw_is_pure_and_says_when_the_server_is_not_running(tmp_path):
    r = go('''
CH.refresh()
CH.select("images.plates")
fake.calls.clear()
log = []
CH.draw_choices(Rec(log), bpy.context)
choices_state.fail("the server could not be reached")
down = []
CH.draw_choices(Rec(down), bpy.context)
nochoices = FakeClient(missing=True)
CH.CLIENT_FACTORY = lambda: nochoices
CH.refresh()
old = []
CH.draw_choices(Rec(old), bpy.context)
print("RESULT", json.dumps({"log": log, "down": down, "old": old, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["calls"] == []
    for text in ("Plates", "Main agent", "Now: a, openrouter", "route studio:tripo is off", "lampway.privacy_open|Open in Privacy",
                 "lampway.choices_proposal_accept|Accept for this project", "lampway.choices_proposal_decline|Decline", "Spending"):
        assert any(text in x for x in d["log"]), (text, d["log"])
    assert any(x.startswith("Lampway's server is not running") for x in d["down"]) and any("as of" in x for x in d["down"])
    assert any("lampway.providers_dialog|" in x for x in d["old"]), "a server without Choices still reaches the old dialog"


def test_writes_refuse_a_script(tmp_path):
    r = go('''
CH.refresh()
CH.select("images.plates")
fake.calls.clear()
out = {}
with human_gate.scripting():
    out["accept"] = call(bpy.ops.lampway.choices_proposal_accept, proposal="p1")
    out["decline"] = call(bpy.ops.lampway.choices_proposal_decline, proposal="p1")
    out["move"] = call(bpy.ops.lampway.choices_move, option="openrouter:b", step=-1)
    out["clear"] = call(bpy.ops.lampway.choices_clear_override)
    out["ack"] = call(bpy.ops.lampway.choices_acknowledge, option="openrouter:b", private=True)
print("RESULT", json.dumps({"out": out, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    for name, res in d["out"].items():
        assert res[0] == "REFUSED" and "this is the user's click: a script cannot press it" in res[1], (name, res)
    assert d["calls"] == []


def test_reorder_accept_and_the_providers_button(tmp_path):
    r = go('''
CH.REFRESH = CH.refresh
res = {}
res["providers"] = call(bpy.ops.lampway.providers_open)
group = choices_state.STATE["group"]
CH.select("images.plates")
fake.calls.clear()
res["move"] = call(bpy.ops.lampway.choices_move, option="openrouter:b", step=-1)
choices_state.STATE["project"] = "demo"
res["accept"] = call(bpy.ops.lampway.choices_proposal_accept, proposal="p1")
print("RESULT", json.dumps({"res": res, "group": group, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["res"]["providers"] == ["FINISHED"] and d["group"] == "agents", d
    put = next(c for c in d["calls"] if c[0] == "put")
    assert put[1] == "images.plates" and put[2]["preferred"] == "studio:tripo" and put[2]["fallbacks"] == ["openrouter:b", "openrouter:a"], put
    assert ["accept", "p1", "project"] in d["calls"]
