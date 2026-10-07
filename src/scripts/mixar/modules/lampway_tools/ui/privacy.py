# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The privacy face (facelift contract 12): one drawing of the routes, the confirm row, what is sending now, the latest
refusal with its ways forward and the egress log, shown in three places - the viewport's Lampway sidebar, a pop-out the
status bar's wire chip opens ("What leaves this machine"), and Preferences > Privacy. draw reads the cache
(egress_state); the words come from privacy_face.

Opening a route is the user's click, twice: the first click opens the confirm row ("Let data leave for <host>?"), and
only its button posts. Both refuse while a script runs (human_gate), as does the per-asset override."""

import bpy
from bpy.props import BoolProperty, StringProperty
from bpy.types import Operator, Panel

from mixar.modules.lampway_tools import capabilities_face, egress_state, human_gate, privacy_face, studio_client


def _default_client():
    from mixar.modules.lampway_tools.ui.operators import egress_ops
    return egress_ops.CLIENT_FACTORY()


CLIENT_FACTORY = _default_client   # tests swap it


def _preview(name):
    from mixar.modules.common.lampway_icons import icon_id
    return icon_id(name)


def _icon_value(icon_name: str) -> int:
    """LAMPWAY_SHIELD_HALF -> the colour-baked preview of shield_half."""
    try:
        return _preview(icon_name.removeprefix("LAMPWAY_").lower())
    except Exception:  # noqa: BLE001  (no previews in a headless run: the row still draws)
        return 0


def _redraw():
    for window in getattr(bpy.context.window_manager, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def _refresh(client) -> None:
    try:
        egress_state.update(client.state(), client.log(20))
    except studio_client.StudioError as exc:
        egress_state.fail(str(exc))
    _redraw()


class _GatedOp(Operator):
    bl_options = {"REGISTER", "INTERNAL"}

    def _done(self, context, message, ok=True):
        scene_props = getattr(context.scene, "lampway_tools", None)
        if scene_props is not None:
            scene_props.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


class LAMPWAY_OT_egress_route(_GatedOp):
    """Switch a route. Every route is off until you switch it on, and on takes two clicks of yours: this one opens the
    confirm row, its button lets data leave"""
    bl_idname = "lampway.egress_route"
    bl_label = "Switch route"
    route: StringProperty()
    enabled: BoolProperty()
    confirm: BoolProperty(description="The confirm row's own button", options={"SKIP_SAVE"})

    def execute(self, context):
        if human_gate.script_running():
            if self.enabled:
                return self._done(context, privacy_face.SCRIPT_REFUSAL, ok=False)
            return self._done(context, "this is the user's click: a script (the agent's, a worker's or the bridge's) cannot press it", ok=False)
        if self.enabled and not (self.confirm and egress_state.PENDING["route"] == self.route):
            egress_state.PENDING["route"] = self.route
            _redraw()
            return self._done(context, f"Confirm in Privacy to let data leave through {self.route}")
        client = CLIENT_FACTORY()
        try:
            client.set_route(self.route, self.enabled)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        if egress_state.PENDING["route"] == self.route:
            egress_state.PENDING["route"] = ""
        _refresh(client)
        return self._done(context, f"{self.route} is now {'ON: data may leave through it' if self.enabled else 'OFF'}")


class LAMPWAY_OT_egress_route_cancel(Operator):
    """Close the confirm row: the route stays off"""
    bl_idname = "lampway.egress_route_cancel"
    bl_label = "Not now"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        egress_state.PENDING["route"] = ""
        _redraw()
        return {"FINISHED"}


class LAMPWAY_OT_egress_override(_GatedOp):
    """Let this one asset through this route once. Logged as an override; your click only"""
    bl_idname = "lampway.egress_override"
    bl_label = "Allow this asset once"
    asset_id: StringProperty()
    route: StringProperty()

    def execute(self, context):
        if human_gate.script_running():
            return self._done(context, "A script cannot allow a private asset through: allow it in Privacy yourself", ok=False)
        client = CLIENT_FACTORY()
        try:
            client.override(self.asset_id, self.route)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        _refresh(client)
        return self._done(context, f"{self.asset_id} may go through {self.route} once (logged)")


class LAMPWAY_OT_privacy_info(Operator):
    """What this row says in full"""
    bl_idname = "lampway.privacy_info"
    bl_label = "Details"
    bl_options = {"INTERNAL"}
    hover: StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.hover or "No details"

    def execute(self, context):
        self.report({"INFO"}, self.hover or "No details")
        return {"FINISHED"}


class LAMPWAY_OT_privacy_open(Operator):
    """What leaves this machine: the routes, what is sending, the last refusal and the log"""
    bl_idname = "lampway.privacy_open"
    bl_label = "What leaves this machine"

    def execute(self, context):
        from mixar.modules.lampway_tools.ui.operators import egress_ops
        egress_ops.refresh_state()
        egress_ops.start_timer()
        bpy.ops.wm.call_panel(name="LAMPWAY_PT_privacy_popout", keep_open=True)
        return {"FINISHED"}


def _info(layout, text, hover, icon_value=0):
    op = layout.operator("lampway.privacy_info", text=text, icon_value=icon_value, emboss=False)
    op.hover = hover
    return op


def draw_privacy(layout, context):
    """The one drawing (sidebar, pop-out, preferences). Reads the cache only."""
    st = egress_state.STATE
    ind = st.get("indicator") or {}
    col = layout.column()
    if ind.get("over_the_wire"):
        hosts = [privacy_face.chip(r, st["routes"])["text"] for r in ind.get("active") or []]
        col.label(text="Sending now: " + (", ".join(hosts) or "a route"), icon_value=_icon_value("LAMPWAY_WIRE_DOT_A"))
    else:
        col.label(text="Nothing is leaving this machine", icon_value=_icon_value("LAMPWAY_LAMP"))
    col.operator("lampway.egress_refresh", icon="FILE_REFRESH")
    if st.get("error"):
        col.label(text=st["error"][:80], icon="ERROR")

    card = privacy_face.last_refusal(st.get("log"))
    if card:
        box = col.box()
        _info(box.row(), card["title"], card["tooltip"], _icon_value("LAMPWAY_GATE"))
        for way in card["ways"]:
            if way["action"] == "route_on":
                op = box.operator("lampway.egress_route", text=way["label"])
                op.route, op.enabled = way["route"], True
            elif way["action"] == "override":
                row = box.row()
                row.alert = True    # stop-coloured text, never a fill (contract 12, section 5)
                row.emboss = 'NONE'  # emboss=False alone is NONE_OR_STATUS, which paints the alert as a red bed
                op = row.operator("lampway.egress_override", text=way["label"])
                op.asset_id, op.route = way["asset_id"], way["route"]
            elif way.get("op"):
                box.operator(way["op"], text=way["label"]).group = way.get("group") or ""
            else:
                box.label(text=way["label"])

    pending = egress_state.PENDING["route"]
    for row in privacy_face.route_rows(st.get("routes"), pending):
        line = col.row(align=True)
        _info(line, row["name"], row["tooltip"], _icon_value(row["shield"]))
        on = row["switch"] == "on"   # not lit: the confirm row is the only lit thing in the window (the calm pass)
        op = line.operator("lampway.egress_route", text="On" if on else "Off", icon="CHECKBOX_HLT" if on else "CHECKBOX_DEHLT")
        op.route, op.enabled = row["id"], row["switch"] != "on"
        if row["switch"] == "confirm":
            confirm = col.box()
            confirm.label(text=row["confirm"])
            buttons = confirm.row(align=True)
            go = buttons.operator("lampway.egress_route", text="Let it leave", depress=True)
            go.route, go.enabled, go.confirm = row["id"], True, True
            buttons.operator("lampway.egress_route_cancel", text="Not now")

    # Routes decide where data may go; Capabilities decide what the agent may do with them: one click apart.
    col.operator("lampway.choices_open", text="Capabilities: what may your agent do?", icon="LAMPWAY_SPARK", emboss=False).purpose = capabilities_face.PAGE_ID

    rows = privacy_face.log_rows((st.get("log") or [])[-20:])
    if rows:
        col.separator()
        col.label(text="What left, and what was refused")
        for r in rows:
            line = col.row(align=True)
            line.label(text=r["time"])
            line.label(text=r["event"], icon_value=_icon_value(r["glyph"]))
            _info(line, r["route"], r["tooltip"])
            line.label(text=r["what"])
    col.operator("lampway.egress_export", icon="EXPORT")


class LAMPWAY_PT_privacy(Panel):
    """Privacy in the viewport's Lampway sidebar."""
    bl_idname = "LAMPWAY_PT_privacy"
    bl_label = "Privacy (what leaves this machine)"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Lampway"

    def draw(self, context):
        draw_privacy(self.layout, context)


class LAMPWAY_PT_privacy_popout(Panel):
    """The pop-out the status bar's wire chip opens."""
    bl_idname = "LAMPWAY_PT_privacy_popout"
    bl_label = "What leaves this machine"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 24

    def draw(self, context):
        draw_privacy(self.layout, context)


class LAMPWAY_PT_privacy_preferences(Panel):
    bl_space_type = "PREFERENCES"
    bl_region_type = "WINDOW"
    bl_context = "interface"
    bl_label = "Privacy"

    def draw(self, context):
        draw_privacy(self.layout, context)


classes = [LAMPWAY_OT_egress_route, LAMPWAY_OT_egress_route_cancel, LAMPWAY_OT_egress_override, LAMPWAY_OT_privacy_info,
           LAMPWAY_OT_privacy_open, LAMPWAY_PT_privacy, LAMPWAY_PT_privacy_popout, LAMPWAY_PT_privacy_preferences]
