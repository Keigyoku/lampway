# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preferences > Interface: "Floating agent pill" (off by default; agent_bubble/core/pill_pref.py), and the one-time
note's dismiss button."""

import bpy
from bpy.props import BoolProperty
from bpy.types import Operator, Panel

from .onboarding import iface_, n_

_VISION_ERROR = ''


def _vision_failed(message):
    """Publish on the main thread without keeping an ended operator's RNA alive."""
    global _VISION_ERROR
    _VISION_ERROR = message
    for window in getattr(bpy.context.window_manager, 'windows', ()):
        for area in window.screen.areas:
            area.tag_redraw()


class LAMPWAY_OT_chatgpt_vision_open(Operator):
    """A human click prepares the browser form; the form's separate consent runs the check."""
    bl_idname = "lampway.chatgpt_vision_open"
    bl_label = "Check ChatGPT image support"

    def invoke(self, context, event):
        return self.execute(context)

    def execute(self, context):
        from .. import human_gate, studio_client
        from . import launch_notice
        if human_gate.script_running():
            return {'CANCELLED'}
        global _VISION_ERROR
        _VISION_ERROR = ''
        client = studio_client.StudioClient()
        def done(result, error):
            failure = iface_(n_('The vision check could not open; try again from Agent preferences.'))
            if error:
                _vision_failed(failure)
                return
            if human_gate.script_running():
                _vision_failed(failure)
                return
            import re
            path = result.get('path') if isinstance(result, dict) else None
            if not isinstance(path, str) or not re.fullmatch(r'/app/chatgpt/vision\?ticket=[A-Za-z0-9_-]{32}', path):
                _vision_failed(failure)
                return
            import webbrowser
            try:
                opened = webbrowser.open(client.base() + path)
            except Exception:
                opened = False
            if not opened:
                _vision_failed(failure)
        launch_notice._background(client.chatgpt_vision_ticket, done)
        return {'FINISHED'}


def _get(self):
    from mixar.modules.agent_bubble.core import pill_pref
    return pill_pref.enabled()


def _note_pending():
    from mixar.modules.agent_bubble.core import pill_pref
    return pill_pref.note_pending()


def _set(self, value):
    from mixar.modules.agent_bubble.core import pill_pref
    was = pill_pref.enabled()
    pill_pref.set_enabled(bool(value))
    if bool(value) != was and not bpy.app.timers.is_registered(_reopen_chat):
        bpy.app.timers.register(_reopen_chat, first_interval=0.0)


def _reopen_chat():
    """The pill is made with the chat window, so an open chat is reopened to gain (or lose) it now."""
    try:
        from mixar.modules.agent_bubble.core.bubble_lifecycle import has_agent_bubble_windows
        if not has_agent_bubble_windows():
            return None
        bpy.ops.mixar.agent_bubble_purge_windows()
        from mixar.modules.agent_bubble.core.bubble_autoshow import try_invoke_bubble
        try_invoke_bubble()
    except Exception:  # noqa: BLE001 - a preference change must never raise
        pass
    return None


class LAMPWAY_OT_agent_pill_note_dismiss(Operator):
    """Hide this note (the pill stays off; the preference brings it back)"""
    bl_idname = "lampway.agent_pill_note_dismiss"
    bl_label = "Dismiss"
    bl_options = {'INTERNAL'}

    def execute(self, context):
        from mixar.modules.agent_bubble.core import pill_pref
        pill_pref.mark_note_seen()
        for window in context.window_manager.windows:
            for area in window.screen.areas:
                area.tag_redraw()
        return {'FINISHED'}


class LAMPWAY_PT_agent_pill_preferences(Panel):
    bl_space_type = 'PREFERENCES'
    bl_region_type = 'WINDOW'
    bl_context = "interface"
    bl_label = "Agent"

    def draw(self, context):
        self.layout.prop(context.window_manager, "lampway_floating_agent_pill")
        from . import capabilities
        capabilities.draw_agent_features(self.layout)
        self.layout.operator("lampway.chatgpt_vision_open", text=iface_(n_("Check ChatGPT image support")))
        if _VISION_ERROR:
            self.layout.label(text=_VISION_ERROR, icon='ERROR', translate=False)


classes = (LAMPWAY_OT_agent_pill_note_dismiss, LAMPWAY_OT_chatgpt_vision_open, LAMPWAY_PT_agent_pill_preferences)


def register():
    bpy.types.WindowManager.lampway_floating_agent_pill = BoolProperty(
        name="Floating agent pill",
        description="When the chat is minimised, leave a small floating pill with the agent's state. Off: minimising "
                    "closes the chat, and the agent chip in the top bar carries the state and opens it again",
        get=_get, set=_set, options={'SKIP_SAVE'})
    bpy.types.WindowManager.lampway_pill_note_pending = BoolProperty(
        name="Pill note pending", get=lambda self: _note_pending(), options={'SKIP_SAVE', 'HIDDEN'})
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    for name in ("lampway_floating_agent_pill", "lampway_pill_note_pending"):
        if hasattr(bpy.types.WindowManager, name):
            delattr(bpy.types.WindowManager, name)
