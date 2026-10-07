# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 04's who line: a user message and the agent's answer, the answer stamped as lampway_tools/chat_route.py stamps a
turn's first agent message ("<HH:MM>\\x1f<host>\\x1f<plan>\\x1f<state>"). The island is captured; the fact is the stamp the renderer reads."""

import os
import sys

SETTLE_TICKS = 34
OUT = {"island": None}


def _island(bpy):
    return next((w for w in bpy.context.window_manager.windows if w.parent is not None and w.width > 200), None)


def setup(bpy):
    m = bpy.context.scene.mixie_chat_messages
    u = m.add()
    u.sender = 'USER'
    u.text = "Make the lantern glass and brass"
    a = m.add()
    a.sender = 'AGENT'
    a.text = "Done: the glass is clear and the frame is brushed brass."
    a.lampway_who = "14:32\x1fchatgpt.com\x1fChatGPT plan\x1fidle"


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
    msgs = bpy.context.scene.mixie_chat_messages
    return dict(OUT, who=[getattr(x, "lampway_who", None) for x in msgs])
