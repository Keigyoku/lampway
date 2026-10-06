# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Privacy panel's operators. Reading is an ordinary button and a 1.5 s timer (the badge must light while data leaves). Switching a route ON or OFF is the USER's click: human_gate refuses it while any
script runs (an agent's, a worker's or the bridge's), so no script can opt the user in."""

import bpy
from bpy.types import Operator

from mixar.modules.lampway_tools import egress_client, egress_state, human_gate, studio_client

CLIENT_FACTORY = lambda: egress_client.EgressClient()  # noqa: E731  (tests swap it)
_POLL_S = 1.5


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def refresh_state() -> None:
    try:
        c = CLIENT_FACTORY()
        egress_state.update(c.state(), c.log(20))
    except studio_client.StudioError as exc:
        egress_state.fail(str(exc))
    _redraw()


def _tick():
    refresh_state()
    return _POLL_S


def start_timer() -> None:
    if not bpy.app.background and not bpy.app.timers.is_registered(_tick):
        bpy.app.timers.register(_tick, first_interval=_POLL_S, persistent=True)


class _Op(Operator):
    bl_options = {"REGISTER"}

    def _done(self, context, message, ok=True):
        context.scene.lampway_tools.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}

    def _gate(self, context):
        if human_gate.script_running():
            return self._done(context, "this is the user's click: a script (the agent's, a worker's or the bridge's) cannot press it", ok=False)
        return None


class LAMPWAY_OT_egress_refresh(_Op):
    """Read the Privacy state from the server and keep it fresh while data may leave"""
    bl_idname = "lampway.egress_refresh"
    bl_label = "Refresh privacy"

    def execute(self, context):
        refresh_state()
        start_timer()
        return self._done(context, egress_state.STATE["error"] or egress_state.badge(), ok=not egress_state.STATE["error"])


class LAMPWAY_OT_egress_export(_Op):
    """Put the egress log (what left, to whom, when) into a Text datablock you can save"""
    bl_idname = "lampway.egress_export"
    bl_label = "Export egress log"

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        try:
            body = CLIENT_FACTORY().export()
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        text = bpy.data.texts.get("LW_egress_log") or bpy.data.texts.new("LW_egress_log")
        text.clear()
        text.write(body)
        return self._done(context, f"egress log: {len(body.splitlines())} rows in the Text 'LW_egress_log'")


classes = [LAMPWAY_OT_egress_refresh, LAMPWAY_OT_egress_export]   # switching a route: ui/privacy.py
