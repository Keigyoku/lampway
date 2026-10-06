# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connections window, 'waiting' (fake cache; see _connections.py)."""

import os
import runpy

_c = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_connections.py"))
facts, regions, surfaces = _c["facts"], _c["regions"], _c["surfaces"]
SETTLE_TICKS = 12


def setup(bpy):
    _c["open_window"](bpy, "higgsfield", waiting=("higgsfield",))
