import tempfile
# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Reading the chat transcript from outside (the bridge). ``scene.mixie_chat_messages[i].content`` is '' for a USER message (the
text is in ``.text``) and for an AGENT bubble while its turn runs (live narration goes to ``.ephemeral`` / ``.thinking_text`` and the
steps; ``.content`` holds only the curated final answer). ``api.chat_transcript`` is the supported reader. REAL binary."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from blender_run import run_script  # noqa: E402

PRE = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
from mixar.modules.lampway_tools import api
sc = bpy.context.scene
for m in list(sc.mixie_chat_messages): pass
sc.mixie_chat_messages.clear()
u = sc.mixie_chat_messages.add(); u.sender = "USER"; u.text = "check the helmet"
a = sc.mixie_chat_messages.add(); a.sender = "AGENT"; a.bubble_id = "b-run"
a["ephemeral"] = "looking at the open loops"; a["thinking_text"] = "pondering the collar"; a.thinking_active = True
s = a.step_items.add(); s.label = "lampway_qa_candidates"
d = sc.mixie_chat_messages.add(); d.sender = "AGENT"; d.bubble_id = "b-done"
d["content"] = "Found 3 loops."; d["text"] = "Found 3 loops."
'''


def run(body):
    return run_script(PRE + body, env={"LAMPWAY_HOME": "@RUN_TMP@/home"})


def test_the_raw_content_is_empty_but_chat_transcript_returns_every_message_text():
    r = run('''
raw = [m.content for m in sc.mixie_chat_messages]
res = api.call("chat_transcript", "{}")
last = api.call("chat_transcript", json.dumps({"last": 1}))
print("RESULT", json.dumps({"raw": raw, "res": res, "last": last}))
''')
    assert r.rc == 0, r.out[-2500:]
    o = r.results[0]
    assert o["raw"] == ["", "", "Found 3 loops."], "the quirk: content is empty for the user's text and for a running bubble"
    rows = o["res"]["messages"]
    assert o["res"]["ok"] is True and [m["sender"] for m in rows] == ["USER", "AGENT", "AGENT"]
    assert rows[0]["text"] == "check the helmet"
    assert rows[1]["running"] is True and rows[1]["text"] == "looking at the open loops" and rows[1]["thinking"] == "pondering the collar"
    assert rows[1]["steps"] == ["lampway_qa_candidates"]
    assert rows[2]["running"] is False and rows[2]["text"] == "Found 3 loops." and rows[2]["bubble_id"] == "b-done"
    assert [m["text"] for m in o["last"]["messages"]] == ["Found 3 loops."]
