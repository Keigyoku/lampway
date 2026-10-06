# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connections panel's operators. Refresh reads the inventory (read-only). Check starts a short probe of the server the user configured: the USER's click, refused while a script runs. Show config
reports the path of the effective source file; it never shows the file's contents."""

import bpy
from bpy.props import StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import human_gate, mcp_client, mcp_state, studio_client

CLIENT_FACTORY = lambda: mcp_client.McpClient()  # noqa: E731  (tests swap it)


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


class _Op(Operator):
    bl_options = {"REGISTER"}

    def _done(self, context, message, ok=True):
        context.scene.lampway_tools.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


class LAMPWAY_OT_mcp_refresh(_Op):
    """Read which MCP servers your agent apps have, from where, and whether each is ready"""
    bl_idname = "lampway.mcp_refresh"
    bl_label = "Refresh connections"

    def execute(self, context):
        try:
            mcp_state.update(CLIENT_FACTORY().inventory())
        except studio_client.StudioError as exc:
            mcp_state.fail(str(exc))
            _redraw()
            return self._done(context, str(exc), ok=False)
        _redraw()
        return self._done(context, f"{len(mcp_state.STATE['servers'])} MCP servers found")


class LAMPWAY_OT_mcp_check(_Op):
    """Open a short connection to this server and list its tools (no tool is ever called). Your click only"""
    bl_idname = "lampway.mcp_check"
    bl_label = "Check"
    server_id: StringProperty()

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, "this is the user's click: a script (the agent's, a worker's or the bridge's) cannot press it", ok=False)
        try:
            res = CLIENT_FACTORY().check(self.server_id)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        mcp_state.set_connection(self.server_id, res["connection"])
        _redraw()
        return self._done(context, f"{self.server_id}: {res['connection']['status']}")


class LAMPWAY_OT_mcp_open_config(_Op):
    """Show where this server's effective configuration lives (the path only, never the contents)"""
    bl_idname = "lampway.mcp_open_config"
    bl_label = "Show config file"
    server_id: StringProperty()

    def execute(self, context):
        s = next((x for x in mcp_state.STATE["servers"] if x["id"] == self.server_id), None)
        src = next((x for x in (s or {}).get("sources", []) if x.get("effective")), None)
        if src is None:
            return self._done(context, "no such server: refresh first", ok=False)
        return self._done(context, f"{self.server_id} is defined in {src['path']}")


classes = [LAMPWAY_OT_mcp_refresh, LAMPWAY_OT_mcp_check, LAMPWAY_OT_mcp_open_config]
