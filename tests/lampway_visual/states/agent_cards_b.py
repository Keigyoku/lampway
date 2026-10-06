# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 05: a paused agent, a done one and one still queued, each in its own ring."""

import math
import os
import runpy

_c = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cards.py"))
facts, regions = _c["facts"], _c["regions"]

SETTLE_TICKS = 3   # 0.75 s: the cards have arrived (0.26 s + stagger) and the done card is inside its 1.2 s dwell, not sliding out
RECORDS = [("PAUSED", "Bake", {"waiting_on": "quota"}), ("DONE", "Handle", {}), ("PENDING", "Wick", {})]


def setup(bpy):
    _c["feed"](bpy, RECORDS)


def surfaces(bpy, dump):
    p = _c["ring_point"]
    return {"paused_dash": p(dump, 0, math.pi / 32), "done_ring": p(dump, 1, 0.0), "idle_ring": p(dump, 2, 0.0)}
