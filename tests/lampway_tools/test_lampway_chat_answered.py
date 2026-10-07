# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04 (the calm pass): an answered question collapses to one line, "Which glass? Clear, you answered 14:30", with the
other choices in an expander. Real binary: a question bubble with three choices is answered through the island's own
operator (the transport is a fake that records the call; nothing reaches a server); then the expander opens and closes."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from features_support import run  # noqa: E402

BODY = '''
import bpy, json
import bootstrap
for _ in range(100000):
    if bootstrap._load_ui_batch_tick() is None: break
import mixar.modules.space_mixie_chat.core as CORE
from mixar.modules.space_mixie_chat.core import turn_transport as TT
sent = []
class Session:
    def is_connected(self, scene): return True
    def get_session_id(self, scene): return "s1"
    def set_state(self, scene, state): pass
    def clear_streaming(self): pass
class Transport:
    def start_input_stream(self, **kw):
        sent.append({"action": kw["action"], "user": kw["user_message"].text}); return True
CORE.get_session_manager = lambda: Session()
TT.create_turn_handler = lambda **kw: Transport()
sc = bpy.context.scene
q = sc.mixie_chat_messages.add()
q.sender = "AGENT"; q.bubble_id = "b-glass"; q.content = "Which glass?"
for label, value in (("Clear", "clear"), ("Frosted", "frosted"), ("Amber", "amber")):
    a = q.action_items.add(); a.label = label; a.value = value
bpy.ops.mixie_chat.select_slot_action(bubble_id="b-glass", action_value="clear")
after = {"content": q.content, "actions": [[a.label, a.value] for a in q.action_items]}
expander = q.action_items[0].value if len(q.action_items) else ""
bpy.ops.mixie_chat.select_slot_action(bubble_id="b-glass", action_value=expander)
opened = {"content": q.content, "actions": [a.label for a in q.action_items]}
bpy.ops.mixie_chat.select_slot_action(bubble_id="b-glass", action_value=expander)
closed = {"content": q.content, "actions": [a.label for a in q.action_items]}
print("RESULT", json.dumps({"sent": sent, "after": after, "opened": opened, "closed": closed,
                            "messages": [[m.sender, m.content or m.text] for m in sc.mixie_chat_messages]}))
'''


def test_an_answered_question_collapses_to_one_line_with_the_others_in_an_expander(tmp_path):
    r = run(tmp_path, BODY)
    assert r.rc == 0, r.out[-2500:]
    d = r.results[0]
    assert d["sent"] == [{"action": "clear", "user": "Clear"}], "the answer still goes to the agent, once"
    line = d["after"]["content"]
    assert line.startswith("Which glass? Clear, you answered ") and len(line.split("answered ")[1]) == 5, line   # HH:MM
    assert d["after"]["actions"] == [["2 other choices", d["after"]["actions"][0][1]]], d["after"]
    assert d["after"]["actions"][0][1].startswith("lampway_answered:"), "the expander is handled here, never sent"
    assert d["opened"]["content"] == line + "\nOther choices: Frosted, Amber" and d["opened"]["actions"] == ["Hide other choices"], d["opened"]
    assert d["closed"] == {"content": line, "actions": ["2 other choices"]}, d["closed"]
    assert len(d["sent"]) == 1, "opening the expander sends nothing"
