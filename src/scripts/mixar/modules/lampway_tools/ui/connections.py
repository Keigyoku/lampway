# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The Connections window (specs/connections/connections_face.md, P0: native widgets). One drawing, two entry points:
a pop-out ("Connections" in the Lampway menu, the plug beside the status bar's wire chip, or Connect on a row elsewhere)
and Preferences > Interface > Connections. Left the list, right the selected row.

draw reads the cache (connections_state) only; a timer refreshes it. Every write is the user's click: it refuses while
a script runs. A pasted key lives in a password field that is never saved and is emptied after the request returns,
whatever it returned; it never reaches a report, a message or a drawn word. The window never switches a route: it links
to Privacy."""

import time

import bpy
from bpy.props import EnumProperty, StringProperty
from bpy.types import Operator, Panel

from mixar.modules.lampway_tools import connections_client, connections_face, connections_state, human_gate, studio_client

CLIENT_FACTORY = lambda: connections_client.ConnectionsClient()  # noqa: E731  (tests swap it)
OPEN_URL = lambda url: __import__("webbrowser").open(url)  # noqa: E731  (tests swap it)
POLL_S = 60.0
MODES = [("auto", "On this machine", "Use what is already on this machine (a login, a variable, a file)"),
         ("manual", "Paste a key", "Paste a key: it is kept in your keyring, or in a file only you can read"),
         ("pointer", "Point to a file or variable", "Point at a file or an environment variable that holds it"),
         ("signin", "Sign in", "Sign in in your browser")]


def _preview(name):
    try:
        from mixar.modules.common.lampway_icons import icon_id
        return icon_id(name)
    except Exception:  # noqa: BLE001  (no previews in a headless run)
        return 0


def _redraw():
    for window in getattr(bpy.context.window_manager, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def refresh() -> None:
    try:
        connections_state.update(CLIENT_FACTORY().list())
    except studio_client.StudioError as exc:
        connections_state.fail(str(exc))
    _redraw()


REFRESH = refresh   # tests swap it


def _tick():
    refresh()
    return POLL_S


class _Write(Operator):
    """A write: the user's click only."""
    bl_options = {"REGISTER", "INTERNAL"}
    connection: StringProperty(options={"SKIP_SAVE"})

    def _cid(self):
        return self.connection or connections_state.STATE["selected"]

    def _done(self, context, message, ok=True):
        props = getattr(context.scene, "lampway_tools", None)
        if props is not None:
            props.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}

    def execute(self, context):
        if human_gate.script_running():
            context.window_manager.lampway_conn_secret = ""
            return self._done(context, connections_face.SCRIPT_REFUSAL, ok=False)
        cid = self._cid()
        if not cid:
            return self._done(context, "choose a connection first", ok=False)
        try:
            view = self.write(context, CLIENT_FACTORY(), cid)
        except studio_client.StudioError as exc:
            connections_state.STATE["refusal"][cid] = str(exc)
            _redraw()
            return self._done(context, str(exc), ok=False)
        finally:
            self.cleanup(context)
        connections_state.STATE["refusal"].pop(cid, None)
        if isinstance(view, dict) and view.get("id"):
            connections_state.put_view(view)
        _redraw()
        return self._done(context, self.said(cid))

    def write(self, context, client, cid):
        raise NotImplementedError

    def cleanup(self, context):
        pass

    def said(self, cid):
        return f"{cid}: done"


class LAMPWAY_OT_connections_save_secret(_Write):
    """Save the pasted key and test it. The field empties itself; the key is never shown again"""
    bl_idname = "lampway.connections_save_secret"
    bl_label = "Save and test"

    def write(self, context, client, cid):
        secret = context.window_manager.lampway_conn_secret
        if not secret:
            raise studio_client.StudioError("paste the key first: nothing was saved")
        return client.put_secret(cid, {"key": secret})

    def cleanup(self, context):
        context.window_manager.lampway_conn_secret = ""

    def said(self, cid):
        return f"{cid}: saved and tested"


class LAMPWAY_OT_connections_test(_Write):
    """Check that it works now"""
    bl_idname = "lampway.connections_test"
    bl_label = "Test"

    def write(self, context, client, cid):
        return client.test(cid)

    def said(self, cid):
        return f"{cid}: tested"


class LAMPWAY_OT_connections_set_source(_Write):
    """Use this way in for the connection"""
    bl_idname = "lampway.connections_set_source"
    bl_label = "Use this"

    def write(self, context, client, cid):
        wm = context.window_manager
        mode = wm.lampway_conn_mode
        ref = {"env": wm.lampway_conn_env} if mode == "pointer" and wm.lampway_conn_env else \
            {"path": bpy.path.abspath(wm.lampway_conn_pointer)} if mode == "pointer" and wm.lampway_conn_pointer else None
        return client.set_source(cid, mode, ref)

    def said(self, cid):
        return f"{cid}: source set"


class LAMPWAY_OT_connections_sign_in(_Write):
    """Sign in in your browser; the row waits, lit, until the browser comes back"""
    bl_idname = "lampway.connections_sign_in"
    bl_label = "Sign in"

    def write(self, context, client, cid):
        answer = client.signin(cid)
        if answer.get("url"):
            OPEN_URL(answer["url"])
            connections_state.STATE["waiting"].add(cid)
        return None

    def said(self, cid):
        return f"{cid}: finish signing in in your browser"


class LAMPWAY_OT_connections_sign_out(_Write):
    """Sign out: the login is removed from Lampway"""
    bl_idname = "lampway.connections_sign_out"
    bl_label = "Sign out"

    def write(self, context, client, cid):
        connections_state.STATE["waiting"].discard(cid)
        return client.signout(cid)

    def said(self, cid):
        return f"{cid}: signed out"


class LAMPWAY_OT_connections_forget(_Write):
    """Forget the key Lampway keeps for this connection"""
    bl_idname = "lampway.connections_forget"
    bl_label = "Forget this key"
    mode: StringProperty(default="manual", options={"SKIP_SAVE"})

    def write(self, context, client, cid):
        return client.forget(cid, self.mode)

    def said(self, cid):
        return f"{cid}: forgotten"


class LAMPWAY_OT_connections_move_to_keyring(_Write):
    """Move the key from a file into your keyring"""
    bl_idname = "lampway.connections_move_to_keyring"
    bl_label = "Move into keyring"

    def write(self, context, client, cid):
        return client.move_to_keyring(cid)

    def said(self, cid):
        return f"{cid}: moved into the keyring"


class LAMPWAY_OT_connections_select(Operator):
    """Show this connection"""
    bl_idname = "lampway.connections_select"
    bl_label = "Select"
    bl_options = {"INTERNAL"}
    connection: StringProperty(options={"SKIP_SAVE"})
    hover: StringProperty(options={"SKIP_SAVE"})

    @classmethod
    def description(cls, context, properties):
        return properties.hover or "Show this connection"

    def execute(self, context):
        connections_state.STATE["selected"] = self.connection
        context.window_manager.lampway_conn_secret = ""
        _redraw()
        return {"FINISHED"}


class LAMPWAY_OT_connections_select_mode(Operator):
    """Choose how Lampway gets it"""
    bl_idname = "lampway.connections_select_mode"
    bl_label = "How Lampway gets it"
    bl_options = {"INTERNAL"}
    mode: StringProperty(options={"SKIP_SAVE"})

    def execute(self, context):
        context.window_manager.lampway_conn_mode = self.mode
        return {"FINISHED"}


class LAMPWAY_OT_connections_refresh(Operator):
    """Read the connections again"""
    bl_idname = "lampway.connections_refresh"
    bl_label = "Refresh"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        REFRESH()
        return {"FINISHED"}


class LAMPWAY_OT_connections_open(Operator):
    """Connections: which of your accounts work now, and which may send data"""
    bl_idname = "lampway.connections_open"
    bl_label = "Connections"
    connection: StringProperty(options={"SKIP_SAVE"}, description="Open on this row")

    def execute(self, context):
        REFRESH()
        if self.connection:
            connections_state.STATE["selected"] = self.connection
        if not bpy.app.timers.is_registered(_tick):
            bpy.app.timers.register(_tick, first_interval=POLL_S, persistent=True)
        if not bpy.app.background:
            bpy.ops.wm.call_panel(name="LAMPWAY_PT_connections_popout", keep_open=True)
        return {"FINISHED"}


def _list(layout):
    st = connections_state.STATE
    waiting = st["waiting"]
    for group, rows in connections_face.groups(st["connections"]):
        layout.label(text=group)
        for row in rows:
            line = layout.row(align=True)
            if row["id"] in waiting:
                line.alert = False
            op = line.operator("lampway.connections_select", text=row["name"], icon_value=_preview("conn_waiting" if row["id"] in waiting else row["glyph"]),
                               emboss=row["id"] == st["selected"], depress=row["id"] in waiting)
            op.connection, op.hover = row["id"], row["tooltip"]
            if row["route_icon"]:
                line.label(text="", icon_value=_preview("wire"))


def _detail(layout, context):
    st = connections_state.STATE
    view = connections_state.selected()
    if not view:
        layout.label(text="Choose a connection on the left")
        return
    d = connections_face.detail(view)
    cid = view["id"]
    head = layout.row()
    head.label(text=d["name"], icon_value=_preview(d["glyph"]))
    head.label(text=d["word"])
    act = d["action"]
    if act["op"] == "lampway.connections_select_mode":
        op = layout.operator(act["op"], text=act["label"])
        op.mode = act["mode"]
    else:
        layout.operator(act["op"], text=act["label"]).connection = cid
    layout.label(text="How Lampway gets it")
    modes = layout.row(align=True)
    wm = context.window_manager
    for mode, label, _desc in MODES:
        op = modes.operator("lampway.connections_select_mode", text=label, depress=wm.lampway_conn_mode == mode)
        op.mode = mode
    layout.label(text=d["source"])
    if wm.lampway_conn_mode == "manual":
        row = layout.row(align=True)
        row.prop(wm, "lampway_conn_secret", text="Key")
        row.operator("lampway.connections_save_secret", text="Save and test").connection = cid
    elif wm.lampway_conn_mode == "pointer":
        layout.prop(wm, "lampway_conn_pointer", text="File")
        layout.prop(wm, "lampway_conn_env", text="Variable")
        layout.operator("lampway.connections_set_source", text="Use it").connection = cid
    elif wm.lampway_conn_mode == "auto":
        layout.operator("lampway.connections_set_source", text="Use what is on this machine").connection = cid
    refusal = st["refusal"].get(cid)
    if refusal:
        row = layout.row()
        row.alert = True
        row.label(text=refusal)
    for text in (d["identity"], d["balance"], f"expires {d['expires']}" if d["expires"] else "", d["next_step"], d["conflict"]):
        if text:
            layout.label(text=text)
    route = connections_face.route_cell(view)
    rrow = layout.row(align=True)
    rrow.label(text=route["tooltip"], icon_value=_preview("wire") if route["icon"] else 0)
    rrow.operator("lampway.privacy_open", text="Open in Privacy")
    header, body = layout.panel("lampway_connections_more", default_closed=True)
    header.label(text="Used by, other sources, history")
    if body is not None:
        body.operator("lampway.connections_move_to_keyring", text="Move into keyring").connection = cid
    if d["foot"]:
        foot = layout.row()
        foot.alert = True    # stop-coloured, never a fill of its own
        if "sign_out" in d["foot"]:
            foot.operator("lampway.connections_sign_out", text="Sign out", emboss=False).connection = cid
        if "forget" in d["foot"]:
            op = foot.operator("lampway.connections_forget", text="Forget this key", emboss=False)
            op.connection, op.mode = cid, (view.get("active_source") or {}).get("mode") or "manual"


def draw_connections(layout, context):
    """The one drawing (pop-out, preferences). Reads the cache only."""
    st = connections_state.STATE
    top = layout.row()
    top.operator("lampway.connections_refresh", text="Refresh", icon="FILE_REFRESH")
    if not st["ok"]:
        top.label(text="Lampway's server is not running: start it, then Refresh", icon="ERROR")
        if st["connections"]:
            layout.label(text="as of " + time.strftime("%H:%M", time.localtime(st["as_of"])) + ", server stopped")
    split = layout.split(factor=0.38)
    _list(split.column())
    _detail(split.column(), context)


class LAMPWAY_PT_connections_popout(Panel):
    bl_idname = "LAMPWAY_PT_connections_popout"
    bl_label = "Connections"
    bl_space_type = "VIEW_3D"
    bl_region_type = "HEADER"
    bl_ui_units_x = 34

    def draw(self, context):
        draw_connections(self.layout, context)


class LAMPWAY_PT_connections_preferences(Panel):
    bl_space_type = "PREFERENCES"
    bl_region_type = "WINDOW"
    bl_context = "interface"
    bl_label = "Connections"

    def draw(self, context):
        draw_connections(self.layout, context)


classes = [LAMPWAY_OT_connections_save_secret, LAMPWAY_OT_connections_test, LAMPWAY_OT_connections_set_source, LAMPWAY_OT_connections_sign_in,
           LAMPWAY_OT_connections_sign_out, LAMPWAY_OT_connections_forget, LAMPWAY_OT_connections_move_to_keyring,
           LAMPWAY_OT_connections_select, LAMPWAY_OT_connections_select_mode, LAMPWAY_OT_connections_refresh, LAMPWAY_OT_connections_open,
           LAMPWAY_PT_connections_popout, LAMPWAY_PT_connections_preferences]


def register():
    wm = bpy.types.WindowManager
    # The pasted key: runtime only (never in a .blend), shown as dots, emptied after every request.
    wm.lampway_conn_secret = StringProperty(name="Key", subtype="PASSWORD", options={"SKIP_SAVE", "HIDDEN"})
    wm.lampway_conn_pointer = StringProperty(name="File", subtype="FILE_PATH", options={"SKIP_SAVE"})
    wm.lampway_conn_env = StringProperty(name="Variable", description="The NAME of an environment variable (never its value)", options={"SKIP_SAVE"})
    wm.lampway_conn_mode = EnumProperty(name="How Lampway gets it", items=MODES, default="manual", options={"SKIP_SAVE"})
    for cls in classes:
        if not getattr(cls, "is_registered", False):
            bpy.utils.register_class(cls)


def unregister():
    if bpy.app.timers.is_registered(_tick):
        bpy.app.timers.unregister(_tick)
    for cls in reversed(classes):
        if getattr(cls, "is_registered", False):
            bpy.utils.unregister_class(cls)
    for name in ("lampway_conn_secret", "lampway_conn_pointer", "lampway_conn_env", "lampway_conn_mode"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
