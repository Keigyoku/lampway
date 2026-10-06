# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 13: the spend card, state 'price_changed' (fake state; see _spend.py)."""

import os
import runpy

_s = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_spend.py"))
facts, regions, surfaces = _s["facts"], _s["regions"], _s["surfaces"]
SETTLE_TICKS = 12


def setup(bpy):
    _s["open_card"](bpy, "price_changed", "the price shown was 21.0, not 18.0: nothing was confirmed")
