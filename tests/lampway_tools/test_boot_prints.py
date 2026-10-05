# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Boot printed bare 'file:line' lines from the toolbar draws (zen_scene_controls.py:165 ten times, :206 five times, and the top bar's
login fallback in the user's session): a header draw that adds an operator which is not registered yet makes Blender report the
Python location on every redraw. The draws now add an operator only when it exists. REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

FAKE = '''
import bpy, json
class L:
    def __init__(self): self.calls = []
    def mixar_surface(self, **kw): return self
    def mixar_style(self, **kw): return None
    def row(self, **kw): return self
    def column(self, **kw): return self
    def operator(self, idname, **kw): self.calls.append(idname); return type("R", (), {"show": False})()
    def prop(self, *a, **kw): return None
    def label(self, **kw): return None
    def popover(self, **kw): return None
    def menu(self, *a, **kw): return None
    def separator(self, **kw): return None
    enabled = True
    ui_units_x = 0.0
class Shading: type = "SOLID"; show_xray = False
class View: shading = Shading(); show_region_tool_header = True
class Ctx:
    space_data = View()
    class scene:
        class mixar_director: is_directing = False
from mixar.modules.workflow.ui.headers import zen_scene_controls as Z
def drawn():
    a, b = L(), L()
    Z.draw_guides(a, Ctx)
    Z.draw_cinema(b, Ctx)
    return a.calls + b.calls
'''


def test_the_toolbar_draws_add_an_operator_only_once_it_is_registered():
    r = run_script(FAKE + '''
before = drawn()
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
after = drawn()
print("RESULT", json.dumps({"before": before, "after": after}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["before"] == [], f"drew unregistered operators: {o['before']}"
    assert "mixar.zen_toggle_guides" in o["after"] and any(n.startswith("mixar.director_") for n in o["after"])
