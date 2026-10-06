# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 05: seven agents fan out; the three on screen need you, work and failed; four wait behind the chevron."""

import math
import os
import runpy

_c = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_cards.py"))
facts, regions = _c["facts"], _c["regions"]

RECORDS = [("BLOCKED", "Lantern texture", {"needs": "answer"}), ("RUNNING", "Brass frame", {}),
           ("FAILED", "Glass shader", {"reason": "OpenRouter refused: session cap $3.00 reached"}),
           ("RUNNING", "Wick", {}), ("RUNNING", "Base", {}), ("DONE", "Handle", {}), ("PAUSED", "Bake", {"waiting_on": "quota"})]


def setup(bpy):
    _c["feed"](bpy, RECORDS)


def surfaces(bpy, dump):
    p = _c["ring_point"]
    return {"blocked_ring": p(dump, 0, 0.0), "working_arc": p(dump, 1, 0.0), "working_ring": p(dump, 1, -math.pi / 2),
            "failed_ring": p(dump, 2, 0.0)}
