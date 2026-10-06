# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preferences > Interface: "Floating agent pill" (off by default; agent_bubble/core/pill_pref.py), and the one-time
note's dismiss button."""

import bpy
from bpy.props import BoolProperty
from bpy.types import Operator, Panel


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


classes = (LAMPWAY_OT_agent_pill_note_dismiss, LAMPWAY_PT_agent_pill_preferences)


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
