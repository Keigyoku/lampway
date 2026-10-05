# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""topbar.py:241 printed its path ten times at boot: while the login panel registers, the top bar's fallback drew an operator
(mixie_chat.login) that is not registered yet, and Blender reports every such draw. The login entry is drawn only with something
that exists: the popover when its panel is registered, else the operator when registered, else a plain label. REAL binary."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

FAKE = '''
import bpy, json
class Row:
    def __init__(self): self.calls = []
    def popover(self, **kw): self.calls.append(("popover", kw.get("panel")))
    def operator(self, name, **kw): self.calls.append(("operator", name))
    def label(self, **kw): self.calls.append(("label", kw.get("text")))
from mixar.modules.space_mixie_chat.ui import topbar
'''


def test_the_login_entry_draws_only_what_is_registered():
    r = run_script(FAKE + '''
before = Row(); topbar.draw_login_entry(before, "Login")
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
after = Row(); topbar.draw_login_entry(after, "Login")
print("RESULT", json.dumps({"before": before.calls, "after": after.calls, "panel": hasattr(bpy.types, "MIXIE_CHAT_PT_login")}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["before"] == [["label", "Login"]], "nothing registered yet: no popover, no operator to complain about"
    assert o["after"] in ([["popover", "MIXIE_CHAT_PT_login"]], [["operator", "mixie_chat.login"]]), o
