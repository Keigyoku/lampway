# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Where the native composer reads the route line (facelift contract 04; written by lampway_tools/chat_route.py)."""

import bpy
from bpy.props import BoolProperty, StringProperty

_PROPS = ("lampway_chat_route_host", "lampway_chat_route_tip", "lampway_chat_send_ok", "lampway_generate_estimates")


def register():
    wm = bpy.types.WindowManager
    wm.lampway_chat_route_host = StringProperty(name="Route", options={'SKIP_SAVE'})
    wm.lampway_chat_route_tip = StringProperty(name="Where the next message goes", options={'SKIP_SAVE'})
    wm.lampway_chat_send_ok = BoolProperty(name="Send may leave", default=True, options={'SKIP_SAVE'})
    wm.lampway_generate_estimates = StringProperty(name="Generate estimates", options={'SKIP_SAVE'})


def unregister():
    for name in _PROPS:
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
