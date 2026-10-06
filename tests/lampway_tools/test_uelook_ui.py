# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look's UI (the captain's click) in the REAL binary, registered by the app's own bootstrap: file pickers for the cube
and its sidecar with a status glyph (valid / missing / mismatch, worked out when a path changes, never in draw), and one toggle.
Off -> on validates the cube, writes the launcher's state and applies; in a session started without the UE view it says to
restart (the launcher then starts it with the view). On -> off reverts exactly and clears the launcher's state. SYNTHETIC cube."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import uelook_support as U  # noqa: E402
from features_support import run  # noqa: E402

BOOT = r'''
import bootstrap, shutil
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools.ue import launch as LA, look
from mixar.modules.lampway_tools.ui.operators import ue_look_ops as OPS
S = bpy.context.scene
class L:
    """A recording layout: every call's keywords, so the test reads the glyph the panel drew."""
    def __init__(self): self.calls = []
    def __getattr__(self, n):
        def f(*a, **k):
            self.calls.append([n, {kk: str(v) for kk, v in k.items()}, [x for x in a if isinstance(x, str)]]); return self
        return f
def draw():
    lay = L(); bpy.types.LAMPWAY_PT_ue_look.draw(type("P", (), {"layout": lay})(), bpy.context); return lay.calls
'''


def go(tmp_path, body, env=None):
    r = run(tmp_path, BOOT + body, env=env or {}, timeout=600)
    assert r.rc == 0, r.out[-3000:]
    return r.results[0]


def test_pickers_show_valid_missing_or_mismatch_and_draw_reads_no_file(tmp_path):
    prof = U.profile_with_cube(tmp_path, "ui.json")
    other = U.profile_with_cube(tmp_path, "other.json", curve="identity")
    cube, meta = json.loads(prof.read_text())["tonemap_cube"], json.loads(prof.read_text())["tonemap_cube_meta"]
    other_meta = json.loads(other.read_text())["tonemap_cube_meta"]
    d = go(tmp_path, f'''
out = {{"fields": [hasattr(S.lampway_ue_look, k) for k in ("profile", "cube", "cube_meta")], "empty": OPS.CUBE_STATUS.get("state")}}
S.lampway_ue_look.cube = {cube!r}; S.lampway_ue_look.cube_meta = {meta!r}
out["valid"] = OPS.CUBE_STATUS["state"]
real = OPS.CB.validate; OPS.CB.validate = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("draw read the cube"))
try:
    out["draw_valid"] = draw()
finally:
    OPS.CB.validate = real
S.lampway_ue_look.cube_meta = {other_meta!r}
out["mismatch"] = OPS.CUBE_STATUS["state"]; out["draw_mismatch"] = draw()
S.lampway_ue_look.cube = ""
out["missing"] = OPS.CUBE_STATUS["state"]; out["draw_missing"] = draw()
print("RESULT", json.dumps(out))
''')
    assert d["fields"] == [True, True, True] and d["valid"] == "valid" and d["mismatch"] == "mismatch" and d["missing"] == "missing", d
    icons = lambda calls: [c[1].get("icon") for c in calls if c[0] == "label"]                    # noqa: E731
    assert "CHECKMARK" in icons(d["draw_valid"]) and "ERROR" in icons(d["draw_mismatch"]) and "QUESTION" in icons(d["draw_missing"]), d
    assert {"profile", "cube", "cube_meta"} <= {x for c in d["draw_valid"] if c[0] == "prop" for x in c[2]}, d["draw_valid"]


def test_the_toggle_enables_applies_says_restart_without_the_view_and_reverts_and_disables(tmp_path):
    prof = U.profile_with_cube(tmp_path, "ui.json")
    cube, meta = json.loads(prof.read_text())["tonemap_cube"], json.loads(prof.read_text())["tonemap_cube_meta"]
    pick = f'S.lampway_ue_look.cube = {cube!r}; S.lampway_ue_look.cube_meta = {meta!r}\n'
    d = go(tmp_path, pick + '''
res = list(bpy.ops.lampway.ue_look_toggle())
print("RESULT", json.dumps({"res": res, "line": OPS.CACHE["line"], "state": LA.state_path().is_file() and LA.state_path().read_text(), "key": bool(S.get(look.STATE_KEY))}))
''')
    assert d["res"] == ["CANCELLED"] and "restart Lampway" in d["line"] and d["state"] and not d["key"], d
    config = dict(l.split("=", 1) for l in d["state"].splitlines())["config"]
    d = go(tmp_path, pick + '''
exp0 = S.view_settings.exposure
on = list(bpy.ops.lampway.ue_look_toggle())
st = {"key": bool(S.get(look.STATE_KEY)), "exp": S.view_settings.exposure, "view": S.view_settings.view_transform}
off = list(bpy.ops.lampway.ue_look_toggle())
print("RESULT", json.dumps({"on": on, "st": st, "off": off, "key_off": bool(S.get(look.STATE_KEY)), "exp_off": S.view_settings.exposure == exp0,
                            "state_off": LA.state_path().is_file()}))
''', env={"OCIO": config})
    assert d["on"] == ["FINISHED"] and d["st"]["key"] and round(d["st"]["exp"], 3) == 0.509 and d["st"]["view"].startswith("UE 5.8 Filmic"), d
    assert d["off"] == ["FINISHED"] and not d["key_off"] and d["exp_off"] and d["state_off"] is False
