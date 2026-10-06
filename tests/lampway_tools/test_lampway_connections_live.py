# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connections window in the real binary (specs/connections/connections_face.md section 10): the pasted key lives in
a password field that is never saved and is emptied after the request whatever it returned; no secret reaches a report
or a drawn word; every write refuses a script; draw reads the cache only and says when the server is not running; and
the open operator lands on the row it is asked for. Fake client: nothing reaches a server."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import connections_state, human_gate, studio_client
from mixar.modules.lampway_tools.ui import connections as CN

SENTINEL = "sk-or-v1-SENTINEL-0000"
VIEWS = [{"id": "openrouter", "label": "OpenRouter", "group": "Agents", "kind": "key", "state": "connected", "qualifiers": [],
          "route": {"id": "openrouter", "on": True}, "active_source": {"mode": "env", "label": "OPENROUTER_API_KEY"},
          "identity": {"masked": "c•••@g•••.com"}, "check_age_s": 30, "fingerprint": {"last4": "7f3a"}, "next_step": ""},
         {"id": "studio:meshy", "label": "Meshy", "group": "Studios", "kind": "key", "state": "missing", "qualifiers": [],
          "route": {"id": "studio:meshy", "on": False}, "active_source": {}, "identity": {}, "check_age_s": None,
          "fingerprint": {}, "next_step": "Meshy is not connected: connect it in Connections"}]
class FakeClient:
    def __init__(self, fail=False): self.calls = []; self.fail = fail
    def list(self): self.calls.append("list"); return {"store": {"kind": "keyring"}, "scanned_at": 1.0, "connections": VIEWS}
    def one(self, cid): self.calls.append(["one", cid]); return dict(next(v for v in VIEWS if v["id"] == cid), sources=[], uses=[], history=[])
    def put_secret(self, cid, fields):
        self.calls.append(["secret", cid, sorted(fields)])
        if self.fail: raise studio_client.StudioError("this does not look like a Meshy key: nothing was saved")
        return dict(VIEWS[1], state="not_checked", fingerprint={"last4": "0000"})
    def test(self, cid): self.calls.append(["test", cid]); return VIEWS[0]
    def set_source(self, cid, mode, ref=None): self.calls.append(["source", cid, mode]); return VIEWS[0]
    def signin(self, cid): self.calls.append(["signin", cid]); return {"url": "http://127.0.0.1:9/x"}
    def signout(self, cid): self.calls.append(["signout", cid]); return VIEWS[0]
    def forget(self, cid, mode): self.calls.append(["forget", cid, mode]); return VIEWS[0]
    def move_to_keyring(self, cid): self.calls.append(["move", cid]); return VIEWS[0]
fake = FakeClient()
CN.CLIENT_FACTORY = lambda: fake
CN.OPEN_URL = lambda url: fake.calls.append(["browser", url])
reports = []
def call(op, **kw):
    try:
        out = sorted(op(**kw))
    except RuntimeError as e:
        out = ["REFUSED", str(e)[:200]]
    reports.append(out)
    return out
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


def test_secret_field_is_password_skip_save(tmp_path):
    r = go('''
p = bpy.types.WindowManager.bl_rna.properties["lampway_conn_secret"]
print("RESULT", json.dumps({"subtype": p.subtype, "skip_save": p.is_skip_save}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["subtype"] == "PASSWORD" and d["skip_save"] is True, d


def test_secret_cleared_after_save_and_never_reported_or_drawn(tmp_path):
    r = go('''
wm = bpy.context.window_manager
connections_state.update(fake.list())
connections_state.STATE["selected"] = "studio:meshy"
wm.lampway_conn_secret = SENTINEL
ok = call(bpy.ops.lampway.connections_save_secret)
after_ok = wm.lampway_conn_secret
fake.fail = True
wm.lampway_conn_secret = SENTINEL
bad = call(bpy.ops.lampway.connections_save_secret)
after_bad = wm.lampway_conn_secret
log = []
CN.draw_connections(Rec(log), bpy.context)
print("RESULT", json.dumps({"ok": ok, "bad": bad, "after_ok": after_ok, "after_bad": after_bad, "log": log, "reports": reports,
                            "calls": fake.calls, "last": bpy.context.scene.lampway_tools.last_message,
                            "refusal": connections_state.STATE["refusal"]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["after_ok"] == "" and d["after_bad"] == "", "emptied whatever the request returned"
    assert d["ok"] == ["FINISHED"] and d["bad"][0] in ("CANCELLED", "REFUSED")
    assert ["secret", "studio:meshy", ["key"]] in d["calls"]
    assert "SENTINEL" not in repr(d["log"]) + repr(d["reports"]) + d["last"] + repr(d["refusal"])
    assert d["refusal"].get("studio:meshy") == "this does not look like a Meshy key: nothing was saved"
    assert "this does not look like a Meshy key: nothing was saved" in d["log"], "the refusal is drawn where it happened"


def test_writes_refuse_a_script(tmp_path):
    r = go('''
wm = bpy.context.window_manager
connections_state.update(fake.list())
connections_state.STATE["selected"] = "openrouter"
fake.calls.clear()
out = {}
with human_gate.scripting():
    wm.lampway_conn_secret = SENTINEL
    for name in ("connections_save_secret", "connections_test", "connections_set_source", "connections_sign_in",
                 "connections_sign_out", "connections_forget", "connections_move_to_keyring"):
        out[name] = call(getattr(bpy.ops.lampway, name))
print("RESULT", json.dumps({"out": out, "calls": fake.calls, "secret": wm.lampway_conn_secret}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    for name, res in d["out"].items():
        assert res[0] == "REFUSED" and "this is the user's click: a script cannot press it" in res[1], (name, res)
    assert d["calls"] == [] and d["secret"] == ""


def test_draw_is_pure_and_says_when_the_server_is_not_running(tmp_path):
    r = go('''
connections_state.update(fake.list())
fake.calls.clear()
log = []
CN.draw_connections(Rec(log), bpy.context)
connections_state.fail("the server could not be reached")
down = []
CN.draw_connections(Rec(down), bpy.context)
print("RESULT", json.dumps({"log": log, "down": down, "calls": fake.calls}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["calls"] == []
    assert any("OpenRouter" in x for x in d["log"]) and any("Meshy" in x for x in d["log"])
    assert any(x.startswith("Lampway's server is not running") for x in d["down"])
    assert any("as of" in x for x in d["down"]), "the last rows stay, dated"


def test_open_lands_on_the_row_it_is_asked_for(tmp_path):
    r = go('''
CN.REFRESH = lambda: connections_state.update(fake.list())
res = call(bpy.ops.lampway.connections_open, connection="studio:meshy")
print("RESULT", json.dumps({"res": res, "selected": connections_state.STATE["selected"]}))
''', tmp_path)
    assert r.rc == 0, r.out[-2000:]
    d = r.results[0]
    assert d["selected"] == "studio:meshy", d
