# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04 in the chat window (the floating island): a user message, a plan whose steps carry price chips, and a
question waiting with three choices. The island is its own window, so this state captures it (over the main window's
frame) and names surfaces in the island's coordinates, located from the QA dump."""

import json
import os
import sys

import bpy

SETTLE_TICKS = 34
OUT = {"island": None}


def _island():
    return next((w for w in bpy.context.window_manager.windows if w.parent is not None and w.width > 200), None)


def setup(bpy):
    sc = bpy.context.scene
    m = sc.mixie_chat_messages
    u = m.add()
    u.sender = 'USER'
    u.text = "Make the lantern glass and brass, under a dollar"
    a = m.add()
    a.sender = 'AGENT'
    a.bubble_id = "b1"
    a.content = "Here is the plan."
    for i, (text, status, price) in enumerate((("Block out the lantern", 'DONE', "local, no cost"),
                                               ("Texture the glass", 'PENDING', "≈ $0.07 est., openrouter.ai"))):
        item = a.todo_items.add()
        item.item_id, item.text, item.status, item.price_text = str(i), text, status, price
    q = m.add()
    q.sender = 'AGENT'
    q.bubble_id = "b2"
    q.content = "Which glass?"
    for label, style in (("Clear", 'PRIMARY'), ("Amber", 'DEFAULT')):
        item = q.action_items.add()
        item.label, item.value, item.style = label, label, style


def surfaces(bpy, dump):
    isl = _island()
    out_dir = sys.argv[sys.argv.index("--") + 2]
    isl.mixar_qa_capture_frame(filepath=os.path.join(out_dir, "frame.png"), x=0, y=0, width=isl.width, height=isl.height)
    ptr = next((w["ptr"] for w in dump.get("windows", []) if w["size"] == [isl.width, isl.height]), None)
    actions = {w.get("text"): w["rect"] for w in dump["widgets"] if w.get("surface") == "chat_action" and w.get("w") == ptr}
    clear = actions.get("Clear")
    OUT["island"] = [isl.width, isl.height]
    if not clear:
        return {}
    cx, cy = (clear[0] + clear[2]) // 2, (clear[1] + clear[3]) // 2
    return {"primary_choice": (clear[0] + 6, cy)}


def regions(bpy):
    return {}


def facts(bpy, dump):
    return dict(OUT, texts=sorted({w.get("text") for w in dump["widgets"] if w.get("surface") == "chat_action"}))
