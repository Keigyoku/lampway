# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The cockpit's operators. Reading, refreshing and reconciling are ordinary buttons. STARTING the herdr server, stopping it, closing a session and sending into one are the USER's clicks
(human_gate.py refuses them while any script is running: an agent's script, a swarm worker's or the bridge's). Nothing here stops anything implicitly: unregister and Blender exit leave the
herdr server and every pane running (the decoupling invariant, specs/mrmak/01 section 14)."""

import bpy
from bpy.props import BoolProperty, EnumProperty, StringProperty
from bpy.types import Operator

from mixar.modules.lampway_tools import human_gate, studio_client, workbench_client, workbench_state

CLIENT_FACTORY = lambda: workbench_client.WorkbenchClient()  # noqa: E731  (tests swap it)
OPEN_URL = lambda url: __import__("webbrowser").open(url)  # noqa: E731  (tests swap it)
TEXT_PREFIX = "LW_session_"
_POLL_S = 2.0
_MIRRORS = set()


def _redraw():
    wm = getattr(bpy.context, "window_manager", None)
    for window in getattr(wm, "windows", []) or []:
        for area in window.screen.areas:
            area.tag_redraw()


def refresh_state() -> None:
    try:
        client = CLIENT_FACTORY()
        workbench_state.update(client.home())
        try:
            workbench_state.STATE["terminal"] = client.terminal()
        except (studio_client.StudioError, AttributeError):
            workbench_state.STATE["terminal"] = {}
    except studio_client.StudioError as exc:
        workbench_state.fail(str(exc))
    _redraw()


def screen_to_text(name: str, screen: str, lines: int = 70):
    """The last ``lines`` lines of a screen into the Text datablock LW_session_<name> (created or replaced)."""
    text = bpy.data.texts.get(TEXT_PREFIX + name) or bpy.data.texts.new(TEXT_PREFIX + name)
    text.clear()
    text.write("\n".join(screen.splitlines()[-int(lines):]))
    return text


def _mirror_tick():
    """The cockpit window's mirror: while a mirrored session's Text exists, refresh it from the server (read-only, never acknowledges anything)."""
    for sid in list(_MIRRORS):
        s = next((x for x in workbench_state.STATE["sessions"] if x["id"] == sid), None)
        if s is None or bpy.data.texts.get(TEXT_PREFIX + s["name"]) is None:
            _MIRRORS.discard(sid)
            continue
        try:
            screen_to_text(s["name"], CLIENT_FACTORY().screen(sid))
        except studio_client.StudioError:
            pass
    _redraw()
    return _POLL_S if _MIRRORS else None


class _WbOp(Operator):
    bl_options = {"REGISTER"}

    def _done(self, context, message, ok=True):
        context.scene.lampway_tools.last_message = message
        self.report({"INFO" if ok else "ERROR"}, message)
        return {"FINISHED"} if ok else {"CANCELLED"}


class _UserClick(_WbOp):
    def _gate(self, context):
        if human_gate.script_running():
            return self._done(context, "this is the user's click: a script (the agent's, a worker's or the bridge's) cannot press it", ok=False)
        return None


class LAMPWAY_OT_wb_refresh(_WbOp):
    """Read the cockpit state from the server: the herdr server, the sessions and their chips"""
    bl_idname = "lampway.wb_refresh"
    bl_label = "Refresh sessions"

    def execute(self, context):
        refresh_state()
        if workbench_state.STATE["error"]:
            return self._done(context, workbench_state.STATE["error"], ok=False)
        return self._done(context, workbench_state.summary_line())


class LAMPWAY_OT_wb_start_server(_UserClick):
    """Start Lampway's own herdr server (detached: it outlives Blender). Your click only"""
    bl_idname = "lampway.wb_start_server"
    bl_label = "Start the herdr server"

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        try:
            out = CLIENT_FACTORY().start_server()
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, "herdr server running" + (" (already)" if out.get("already_running") else f" ({out.get('method')})"))


class LAMPWAY_OT_wb_reconcile(_WbOp):
    """Re-adopt the live panes by the server's truth: nothing is spawned or killed"""
    bl_idname = "lampway.wb_reconcile"
    bl_label = "Reconcile sessions"

    def execute(self, context):
        try:
            out = CLIENT_FACTORY().reconcile()
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        if out.get("server") == "not_running":
            return self._done(context, "the herdr server is not running: Start it (or Resume sessions) yourself; nothing is relaunched automatically")
        return self._done(context, f"adopted {len(out['adopted'])}, ended {len(out['ended'])}, unadopted {len(out['unadopted'])} (new panes: {out['new_panes']})")


class LAMPWAY_OT_wb_new(_UserClick):
    """Open a new agent session in the cockpit (your own CLI login)"""
    bl_idname = "lampway.wb_new"
    bl_label = "New session"
    agent: EnumProperty(name="Agent", items=[("claude", "Claude Code", ""), ("codex", "Codex", ""), ("opencode", "OpenCode", ""), ("shell", "Shell", "")], default="claude")
    name: StringProperty(name="Name", default="")
    task: StringProperty(name="Task", default="")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        try:
            rec = CLIENT_FACTORY().create(self.agent, self.name, "", self.task)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, f"session {rec['name']} started")


class LAMPWAY_OT_wb_read_to_text(_WbOp):
    """Copy the last 70 screen lines of a session into a Text datablock (reading never marks an answer seen)"""
    bl_idname = "lampway.wb_read_to_text"
    bl_label = "Read to Text"
    session_id: StringProperty()

    def execute(self, context):
        s = next((x for x in workbench_state.STATE["sessions"] if x["id"] == self.session_id), None)
        if s is None:
            return self._done(context, "no such session: refresh first", ok=False)
        try:
            screen = CLIENT_FACTORY().screen(self.session_id)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        text = screen_to_text(s["name"], screen)
        return self._done(context, f"{text.name}: {len(text.lines)} lines")


class LAMPWAY_OT_wb_send(_UserClick):
    """Type into a session (your own keystrokes: this is the user's send)"""
    bl_idname = "lampway.wb_send"
    bl_label = "Send"
    session_id: StringProperty()
    text: StringProperty(name="Text")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        try:
            CLIENT_FACTORY().send(self.session_id, self.text)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        return self._done(context, "sent")


class LAMPWAY_OT_wb_close(_UserClick):
    """Close a session's pane (its agent process ends; its history stays). Needs your confirm"""
    bl_idname = "lampway.wb_close"
    bl_label = "Close session"
    session_id: StringProperty()
    confirm: BoolProperty(name="Yes, end this agent", default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        if not self.confirm:
            return self._done(context, "closing a session is an explicit action: tick the confirm", ok=False)
        try:
            CLIENT_FACTORY().close(self.session_id, True)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, "session closed")


class LAMPWAY_OT_wb_stop_server(_UserClick):
    """Stop Lampway's herdr server: every agent pane in it ends. Needs your confirm"""
    bl_idname = "lampway.wb_stop_server"
    bl_label = "Stop the herdr server"
    confirm: BoolProperty(name="Yes, end every session", default=False)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        if not self.confirm:
            return self._done(context, "stopping the server ends every agent in it: tick the confirm", ok=False)
        try:
            CLIENT_FACTORY().stop_server(True)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, "herdr server stopped")


class LAMPWAY_OT_wb_popout(_WbOp):
    """Open the cockpit window: a read-only mirror of the session in a Text editor, refreshed every two seconds"""
    bl_idname = "lampway.wb_popout"
    bl_label = "Cockpit window"
    session_id: StringProperty()

    def execute(self, context):
        s = next((x for x in workbench_state.STATE["sessions"] if x["id"] == self.session_id), None)
        if s is None:
            return self._done(context, "no such session: refresh first", ok=False)
        try:
            text = screen_to_text(s["name"], CLIENT_FACTORY().screen(self.session_id))
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        _MIRRORS.add(self.session_id)
        if not bpy.app.background:
            bpy.ops.wm.window_new()
            area = context.window_manager.windows[-1].screen.areas[0]
            area.type = "TEXT_EDITOR"
            area.spaces.active.text = text
            if not bpy.app.timers.is_registered(_mirror_tick):
                bpy.app.timers.register(_mirror_tick, first_interval=_POLL_S, persistent=True)
        return self._done(context, f"cockpit window for {s['name']}")


class LAMPWAY_OT_terminal_get(_UserClick):
    """Get the Lampway terminal: about 49 MB from github.com (the github route must be on), checked against the SHA-256
    Lampway pins, installed under LAMPWAY_HOME"""
    bl_idname = "lampway.terminal_get"
    bl_label = "Get the Lampway terminal"

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        try:
            out = CLIENT_FACTORY().terminal_get()
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, f"the Lampway terminal {out.get('version')} is installed")


class LAMPWAY_OT_terminal_open(_UserClick):
    """Open the Lampway terminal beside Blender: one tab per agent of Lampway's herdr server (Ctrl Alt T)"""
    bl_idname = "lampway.terminal_open"
    bl_label = "Open the Lampway terminal"

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        win = getattr(context, "window", None)
        position = workbench_state.beside(win.x, win.y, win.width) if win is not None else None
        try:
            CLIENT_FACTORY().terminal_open(position)
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, "the Lampway terminal is open")


class LAMPWAY_OT_terminal_remove(_UserClick):
    """Remove the Lampway terminal: its window closes (never another WezTerm), the agents keep running"""
    bl_idname = "lampway.terminal_remove"
    bl_label = "Remove the Lampway terminal"

    def execute(self, context):
        if (r := self._gate(context)) is not None:
            return r
        try:
            CLIENT_FACTORY().terminal_remove()
        except studio_client.StudioError as exc:
            return self._done(context, str(exc), ok=False)
        refresh_state()
        return self._done(context, "the Lampway terminal is removed; the agents keep running")


class LAMPWAY_OT_wb_page_open(_WbOp):
    """Open the cockpit window: every session with its state, the selected one's terminal, the reconcile banner and the report
    cards, in your browser from Lampway's own server (facelift contract 10)"""
    bl_idname = "lampway.wb_page_open"
    bl_label = "Cockpit window"

    def execute(self, context):
        from mixar.config.config import get_server_url
        from mixar.modules.auth.core.auth import get_access_token
        url = workbench_state.page_url(get_server_url(), get_access_token() or "")
        OPEN_URL(url)
        return self._done(context, "the cockpit window is open in your browser")


classes = [LAMPWAY_OT_terminal_get, LAMPWAY_OT_terminal_open, LAMPWAY_OT_terminal_remove, LAMPWAY_OT_wb_page_open, LAMPWAY_OT_wb_refresh, LAMPWAY_OT_wb_start_server, LAMPWAY_OT_wb_reconcile, LAMPWAY_OT_wb_new, LAMPWAY_OT_wb_read_to_text, LAMPWAY_OT_wb_send, LAMPWAY_OT_wb_close,
           LAMPWAY_OT_wb_stop_server, LAMPWAY_OT_wb_popout]


_KEYMAP = []


def _register_keymap():
    """Ctrl Alt T opens the Lampway terminal from anywhere in the window (contract 16 section 3)."""
    kc = bpy.context.window_manager.keyconfigs.addon if bpy.context.window_manager else None
    if kc is None:
        return 0.5   # the add-on keyconfig is not up yet
    km = kc.keymaps.new(name="Window", space_type='EMPTY')
    _KEYMAP.append((km, km.keymap_items.new("lampway.terminal_open", 'T', 'PRESS', ctrl=True, alt=True)))
    return None


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    if _register_keymap() is not None:
        bpy.app.timers.register(_register_keymap, first_interval=0.5)


def unregister():
    for km, kmi in _KEYMAP:
        try:
            km.keymap_items.remove(kmi)
        except (ValueError, ReferenceError):
            pass
    _KEYMAP.clear()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
