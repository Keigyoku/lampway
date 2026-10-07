# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 16 in Blender (real binary, fake client): Get / Open / Remove are the user's clicks; a refused Get says the
server's reason where it was pressed; Open places the window beside Blender; the panel says what Get downloads."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import human_gate, studio_client, workbench_state
from mixar.modules.lampway_tools.ui.operators import workbench_ops as WO
from mixar.modules.lampway_tools.ui.panels import lampway_panels as PANELS
class FakeClient:
    def __init__(self): self.calls = []
    def home(self): return {"server": {"running": False}, "sessions": [], "offered": []}
    def terminal(self): self.calls.append("terminal"); return {"installed": False, "window": "gone", "pin": {"version": "20240203-110809-5046fc22", "bytes": 49505472}}
    def terminal_get(self):
        self.calls.append("get")
        raise studio_client.StudioError("github.com is off: open it in Privacy to download the Lampway terminal (about 49 MB); nothing was sent")
    def terminal_open(self, position=None): self.calls.append(["open", position]); return {"gui_pid": 1}
    def terminal_remove(self): self.calls.append("remove"); return {"removed": True}
fake = FakeClient()
WO.CLIENT_FACTORY = lambda: fake
def call(op, **kw):
    try:
        return sorted(op(**kw))
    except RuntimeError as e:
        return ["REFUSED", str(e)[:200]]
class Rec:
    def __init__(self, log): self.log = log
    def label(self, text="", **k): self.log.append(text)
    def operator(self, idname, text="", **k): self.log.append("op:" + idname + "|" + text); return type("P", (), {})()
    def row(self, **k): return self
    def box(self): return self
    def column(self, **k): return self
    def separator(self, **k): pass
'''


def test_get_open_remove_are_clicks_and_say_why(tmp_path):
    r = run(tmp_path, PRE + '''
WO.refresh_state()
log = []
panel = PANELS.LAMPWAY_PT_cockpit
panel.layout = Rec(log)
panel.draw(panel, bpy.context)
res = {"get": call(bpy.ops.lampway.terminal_get), "msg": bpy.context.scene.lampway_tools.last_message}
with human_gate.scripting():
    res["script_get"] = call(bpy.ops.lampway.terminal_get)
    res["script_open"] = call(bpy.ops.lampway.terminal_open)
    res["script_remove"] = call(bpy.ops.lampway.terminal_remove)
res["open"] = call(bpy.ops.lampway.terminal_open)
print("RESULT", json.dumps({"res": res, "calls": fake.calls, "log": log}))
''')
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert any("about 49 MB from github.com" in x for x in d["log"]), d["log"]
    assert any(x.startswith("op:lampway.terminal_get|") for x in d["log"])
    assert d["res"]["get"][0] in ("CANCELLED", "REFUSED") and d["res"]["msg"].startswith("github.com is off")
    for k in ("script_get", "script_open", "script_remove"):
        assert d["res"][k][0] == "REFUSED", (k, d["res"][k])
    assert d["calls"].count("get") == 1 and "remove" not in d["calls"]
    opened = next(c for c in d["calls"] if isinstance(c, list) and c[0] == "open")
    assert d["res"]["open"] == ["FINISHED"] and opened[0] == "open"   # no window in a headless run: the placement is tested on the host


FOCUS = '''
class Open(FakeClient):
    def terminal(self):
        self.calls.append("terminal")
        return {"installed": True, "window": "re-adopted", "version": "20230712-072601-f4abf8fd", "update": True,
                "pin": {"version": "20240203-110809-5046fc22", "bytes": 49505472}}
fake = Open()
WO.CLIENT_FACTORY = lambda: fake
WO.refresh_state()
log = []
panel = PANELS.LAMPWAY_PT_cockpit
panel.layout = Rec(log)
panel.draw(panel, bpy.context)
res = {"focus_op": hasattr(bpy.types, "LAMPWAY_OT_terminal_focus")}
kc = bpy.context.window_manager.keyconfigs.addon
keys = [[km.name, k.idname, k.type, k.ctrl, k.alt, k.shift] for km in (kc.keymaps if kc else []) for k in km.keymap_items
        if k.idname == "lampway.terminal_open"]
print("RESULT", json.dumps({"res": res, "calls": fake.calls, "log": log, "keys": keys, "background": bpy.app.background}))
'''


def test_update_and_the_shortcut_and_no_focus(tmp_path):
    """Update appears when the pin moved past the installed version, and Ctrl Alt T opens the terminal from anywhere in the
    window. No Focus (the coordinator's audit, W6): the window is a viewport the user raises himself."""
    r = run(tmp_path, PRE + FOCUS)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    ops = [x for x in d["log"] if x.startswith("op:")]
    assert not [o for o in ops if "terminal_focus" in o], ops
    assert "op:lampway.terminal_get|Update to 20240203-110809-5046fc22" in ops, ops
    assert d["res"]["focus_op"] is False
    assert ["Window", "lampway.terminal_open", "T", True, True, False] in d["keys"], d["keys"]
