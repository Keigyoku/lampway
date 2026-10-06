# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look toggle: one click applies the chosen profile to this scene, the next click reverts it exactly (the receipt).
A thin button over ``api.ue_look``; the result line is cached for the panel, so draw() reads no file."""

import bpy
from bpy.types import Operator

from mixar.modules.lampway_tools import api

CACHE = {"line": ""}


def _line(res):
    if not res.get("ok"):
        return res.get("error", "failed")
    if "reverted" in res:
        return f"UE Look off: {res['restored']} values restored"
    open_ = sorted(k for k, v in res.get("classes", {}).items() if v != "measured")
    return f"UE Look on (exposure {res['exposure_stops']:+.3f}); not yet measured: {', '.join(open_)}"


class LAMPWAY_OT_ue_look_toggle(Operator):
    """Switch this scene to the UE profile's look, or back exactly as it was"""
    bl_idname = "lampway.ue_look_toggle"
    bl_label = "UE Look"
    bl_options = {"REGISTER"}

    def execute(self, context):
        scene = context.scene
        if api.ue_look(action="status").get("active"):
            res = api.ue_look(action="revert")
        else:
            res = api.ue_look(action="apply", profile=bpy.path.abspath(scene.lampway_ue_look.profile) or None)
        CACHE["line"] = _line(res)
        self.report({"INFO"} if res.get("ok") else {"ERROR"}, CACHE["line"])
        return {"FINISHED"} if res.get("ok") else {"CANCELLED"}


classes = [LAMPWAY_OT_ue_look_toggle]
