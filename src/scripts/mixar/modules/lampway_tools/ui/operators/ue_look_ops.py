# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The UE Look toggle and the cube's status. Off -> on: validate the cube, write the UE view's config and the launcher's state
(``api.ue_look enable``), then apply; a session started without the view is told to restart (the launcher starts the next one
with it). On -> off: revert exactly, then clear the launcher's state. ``refresh`` validates the picked cube when a path changes
and caches valid / missing / mismatch for the panel, so draw() reads no file."""

import bpy
from bpy.types import Operator

from mixar.modules.lampway_tools import api
from mixar.modules.lampway_tools.ue import cube as CB
from mixar.modules.lampway_tools.ue import look as LK

CACHE = {"line": ""}
CUBE_STATUS = {}


def _paths(scene):
    p = scene.lampway_ue_look
    ab = lambda v: bpy.path.abspath(v) if v else None              # noqa: E731
    return ab(p.profile), ab(p.cube), ab(p.cube_meta)


def refresh(scene):
    """Validate the picked (or the profile's) cube once and keep the answer for the panel."""
    profile, cube, meta = _paths(scene)
    try:
        _, prof = LK.load_profile(profile, cube, meta)
        v = CB.validate(prof)
    except ValueError as exc:
        v = {"state": "mismatch", "why": str(exc), "fix": CB.FIX}
    CUBE_STATUS.clear()
    CUBE_STATUS.update(state=v["state"], why=v["why"], sha256=v.get("sha256"), engine_version=v.get("engine_version"))
    return v


def _line(res):
    if not res.get("ok"):
        return res.get("error", "failed")
    if "reverted" in res:
        return f"UE Look off: {res['restored']} values restored"
    open_ = sorted(k for k, v in res.get("classes", {}).items() if v != "measured")
    return f"UE Look on (exposure {res['exposure_stops']:+.3f}); not yet measured: {', '.join(open_)}"


class LAMPWAY_OT_ue_look_toggle(Operator):
    """Switch this scene to the UE profile's look (its cube validated, the next launch started with the UE view), or back exactly"""
    bl_idname = "lampway.ue_look_toggle"
    bl_label = "UE Look"
    bl_options = {"REGISTER"}

    def execute(self, context):
        profile, cube, meta = _paths(context.scene)
        if api.ue_look(action="status").get("active"):
            res = api.ue_look(action="revert")
            if res.get("ok"):
                api.ue_look(action="disable")
        else:
            en = api.ue_look(action="enable", profile=profile, cube=cube, cube_meta=meta)
            refresh(context.scene)
            if not en.get("ok") or en.get("restart"):
                CACHE["line"] = en.get("message") if en.get("ok") else en.get("error", "failed")
                self.report({"WARNING"} if en.get("ok") else {"ERROR"}, CACHE["line"])
                return {"CANCELLED"}
            res = api.ue_look(action="apply", profile=profile, cube=cube, cube_meta=meta)
        CACHE["line"] = _line(res)
        self.report({"INFO"} if res.get("ok") else {"ERROR"}, CACHE["line"])
        return {"FINISHED"} if res.get("ok") else {"CANCELLED"}


classes = [LAMPWAY_OT_ue_look_toggle]
