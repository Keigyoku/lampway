# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 08: the island's Image tab, policy state 'spend' (fake server answer; see _generate.py)."""

import os
import runpy

_g = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_generate.py"))
facts, regions, surfaces = _g["facts"], _g["regions"], _g["surfaces"]
SETTLE_TICKS = 30


def setup(bpy):
    _g["feed"](bpy, _g["answer"](0.40, True))
