# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 08's A/B action, as the coordinator ruled (2026-10-06): a stub that needs the user's click. A/B would submit two
paid generations, so the click says what it would do and sends nothing; a script cannot press it."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

BODY = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import human_gate, studio_state
from mixar.modules.lampway_tools.ui.operators import studio_ops
calls = []
class Client:
    def __getattr__(self, name):
        def record(*a, **k):
            calls.append(name); return {}
        return record
studio_ops.CLIENT_FACTORY = lambda: Client()
studio_state.PROMPTS["current"] = {"id": "seamless-tile", "version": "1.0.0", "title": "Seamless tile", "media": "image"}
def call(**kw):
    try:
        return sorted(bpy.ops.lampway.prompt_ab(**kw))
    except (RuntimeError, AttributeError) as e:
        return ["REFUSED", str(e)[:200]]
click = call()
msg = bpy.context.scene.lampway_tools.last_message
with human_gate.scripting():
    scripted = call()
print("RESULT", json.dumps({"click": click, "msg": msg, "scripted": scripted, "calls": calls}))
'''


def test_ab_is_a_stub_that_needs_the_users_click_and_spends_nothing(tmp_path):
    r = run(tmp_path, BODY)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["click"] == ["CANCELLED"] and d["msg"].startswith("A/B of seamless-tile@1.0.0 would run two paid generations"), d
    assert d["scripted"][0] == "REFUSED", d
    assert d["calls"] == [], "nothing is asked of the server, nothing is spent"
