# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A background (-b) run prints only what its script prints (#10 item 3): no line per agent-bubble class, and Lampway's splash menus
replace upstream's without Blender's "registered before, unregistering previous" notice. They are still Lampway's own menus."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402


def test_a_background_run_has_no_registration_chatter_and_keeps_lampways_splash_menus():
    r = run_script('''
import json, bpy
print("RESULT", json.dumps({m: getattr(bpy.types, m).__module__ for m in ("WM_MT_splash", "WM_MT_splash_quick_setup")}))
''')
    assert r.rc == 0, r.out[-2500:]
    assert "[agent_bubble] registered" not in r.out, r.out[:2000]
    assert "has been registered before, unregistering previous" not in r.out, r.out[:2000]
    assert r.results == [{"WM_MT_splash": "mixar.bootstrap.splash_menu", "WM_MT_splash_quick_setup": "mixar.bootstrap.splash_quick_setup"}]
