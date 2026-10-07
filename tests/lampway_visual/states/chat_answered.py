# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04: an answered question drawn as one line with its expander row, and no lamplight (nothing waits there). The
question is answered through lampway_tools/answered.py exactly as the island's action operator does."""

import os
import sys

SETTLE_TICKS = 34
OUT = {"island": None}


def _island(bpy):
    return next((w for w in bpy.context.window_manager.windows if w.parent is not None and w.width > 200), None)


def setup(bpy):
    from mixar.modules.lampway_tools import answered
    m = bpy.context.scene.mixie_chat_messages
    q = m.add()
    q.sender = 'AGENT'
    q.bubble_id = "b-glass"
    q.content = "Which glass?"
    for label, value in (("Clear", "clear"), ("Frosted", "frosted"), ("Amber", "amber")):
        a = q.action_items.add()
        a.label, a.value = label, value
    answered.collapse(q, "clear", "14:30")
    u = m.add()
    u.sender = 'USER'
    u.text = "Clear"


def surfaces(bpy, dump):
    isl = _island(bpy)
    if isl is not None:
        out_dir = sys.argv[sys.argv.index("--") + 2]
        isl.mixar_qa_capture_frame(filepath=os.path.join(out_dir, "frame.png"), x=0, y=0, width=isl.width, height=isl.height)
        OUT["island"] = [isl.width, isl.height]
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    q = bpy.context.scene.mixie_chat_messages[0]
    return dict(OUT, content=q.content, actions=[a.label for a in q.action_items])
