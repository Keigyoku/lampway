# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look's UI (the captain's click): a profile picker and one toggle in the Lampway sidebar, registered by the app's
own bootstrap, in the REAL binary. The toggle applies the picked profile and the next click reverts it; the panel's draw
reads no file (it is drawn with the receipt's directory removed)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402


def test_the_toggle_applies_then_reverts_and_the_panel_draws_without_reading_files(tmp_path):
    r = run(tmp_path, '''
import bootstrap, shutil
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools.ue import look
S = bpy.context.scene
out = {"panel": hasattr(bpy.types, "LAMPWAY_PT_ue_look"), "field": hasattr(S, "lampway_ue_look"), "exp0": S.view_settings.exposure}
out["on"] = list(bpy.ops.lampway.ue_look_toggle())
out["key_on"] = bool(S.get(look.STATE_KEY)); out["exp1"] = S.view_settings.exposure
class L:
    def __getattr__(self, n): return lambda *a, **k: self
pnl = bpy.types.LAMPWAY_PT_ue_look
saved = look.data_dir().with_name("moved"); shutil.move(str(look.data_dir()), str(saved))
try:
    pnl.draw(type("P", (), {"layout": L()})(), bpy.context); out["draw"] = "ok"
except Exception as exc:
    out["draw"] = repr(exc)
shutil.move(str(saved), str(look.data_dir()))
out["off"] = list(bpy.ops.lampway.ue_look_toggle())
out["key_off"] = bool(S.get(look.STATE_KEY)); out["exp2"] = S.view_settings.exposure
print("RESULT", json.dumps(out))
''', timeout=600)
    assert r.rc == 0, r.out[-3000:]
    d = r.results[0]
    assert d["panel"] and d["field"] and d["draw"] == "ok", d
    assert d["on"] == ["FINISHED"] and d["key_on"] and round(d["exp1"], 3) == 0.509
    assert d["off"] == ["FINISHED"] and not d["key_off"] and d["exp2"] == d["exp0"]
