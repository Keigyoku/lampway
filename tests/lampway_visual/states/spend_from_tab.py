# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contracts 08 and 13: Spend in the island's tab was pressed (the approvals then waiting are noted); the server's next
spend approval appears in the status answer; the status refresh opens its card. Fake state: nothing reaches a server."""

import os
import runpy
import sys

_s = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_spend.py"))
facts, regions, surfaces = _s["facts"], _s["regions"], _s["surfaces"]
SETTLE_TICKS = 12


def setup(bpy):
    from mixar.modules.lampway_tools import generate_face, statusbar_state, studio_state
    statusbar = sys.modules["mixar.modules.lampway_tools.ui.statusbar"]
    if bpy.app.timers.is_registered(statusbar._tick):
        bpy.app.timers.unregister(statusbar._tick)
    generate_face.await_card([])                         # Spend pressed while nothing waited
    ap = _s["APPROVAL"]
    studio_state.STATE.update(approvals=[ap], actions=[], jobs=[], engine={}, error="")
    statusbar_state.update(egress={"routes": []}, spend=_s["SPEND"], studio={"approvals": [ap]})

    def later():
        statusbar._open_awaited_card()
        return None

    bpy.app.timers.register(later, first_interval=0.5)
