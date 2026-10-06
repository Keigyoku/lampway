# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 03: the status bar fed from a fake server (('openrouter', 'fal'), (), True: routes on, sending, a decision waiting)."""

import os
import runpy

_status = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_status.py"))
facts, regions, surfaces = _status["facts"], _status["regions"], _status["surfaces"]


def setup(bpy):
    _status["feed"](bpy, ('openrouter', 'fal'), (), True)
