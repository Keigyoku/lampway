# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""ESC / close-button → minimise-to-pill operator.

The bubble must never be destroyed by the user — it should always be
present as either the full chat window or the floating status pill.
ESC and the header close button both route here, which minimises the
bubble to the pill instead of calling wm.window_close.

Why this exists instead of binding wm.window_close to the AGENT_BUBBLE
keymap directly:

Blender's event dispatcher consults the global "Window" keymap before
any space-specific keymap, so ESC bindings on a space keymap never
fire. This operator is bound in the global "Window" keymap; poll()
restricts it to the AGENT_BUBBLE space so ESC in every other editor
is unaffected.
"""

from __future__ import annotations

import bpy
from bpy.types import Operator

from mixar.modules.agent_bubble.constants import (
    BUBBLE_WINDOW_CONTROLS_SUPPORTED,
)
from mixar.modules.common.analytics.capture import capture
from mixar.modules.common.analytics.constants import EVENT_BUBBLE_EXPAND
from mixar.modules.common.analytics.bubble_events import capture_bubble_state


# Every operator here drives a native window-state operator that only acts
# on macOS, Windows and Linux/X11 (see BUBBLE_WINDOW_CONTROLS_SUPPORTED).
# Elsewhere the native side cannot touch a window, so these gate
# themselves rather than running their side effects around a call that will
# not do anything:
#
#   * mixar.bubble_close records the user-dismissal that mutes the
#     workspace-change autoshow. Setting it when nothing minimised is how ESC
#     could arm a pill-only reopen on a platform that cannot leave the pill.
#   * mixar.bubble_toggle_minimise reads CANCELLED from minimise as "already
#     minimised, so restore instead", ignores the restore result and returns
#     FINISHED. On a stubbed platform both calls fail, so every Ctrl/Cmd+
#     Shift+B reported success and logged a "maximized" analytics event for a
#     window that never moved.
#
# poll() is the gate wherever there is one: it also greys out the button for
# any surface that draws these without checking the platform first.


def _pill_off() -> bool:
    from mixar.modules.agent_bubble.core import pill_pref
    return not pill_pref.enabled()


def _island_open() -> bool:
    from mixar.modules.agent_bubble.core.bubble_lifecycle import is_agent_bubble_window
    return any(getattr(w, "parent", None) is not None and is_agent_bubble_window(w)
               for w in bpy.context.window_manager.windows)


def _close_island() -> int:
    """Close the chat window (the pill is off, so minimising has nowhere to go). Only the floating chat windows, the
    main window's children: an Agent Bubble area the user put in a main window is not the island."""
    from mixar.modules.agent_bubble.core import pill_pref, unread
    from mixar.modules.agent_bubble.core.bubble_lifecycle import is_agent_bubble_window
    unread.closed(getattr(bpy.context, "scene", None))
    pill_pref.mark_note_seen()   # the one-time note in the chat header has been there for a whole session
    purge = getattr(getattr(bpy.ops, "mixar", None), "agent_bubble_purge_windows", None)
    if purge is not None:
        try:
            # The native side closes exactly its own transient chat windows (never a main window).
            if 'CANCELLED' not in purge() and not _island_open():
                return 1
        except Exception:  # noqa: BLE001 - fall back to closing the windows one by one
            pass
    closed = 0
    for window in list(bpy.context.window_manager.windows):
        if getattr(window, "parent", None) is None or not is_agent_bubble_window(window):
            continue
        area = next((a for a in window.screen.areas if a.type == 'AGENT_BUBBLE'), None)
        region = next((r for r in area.regions if r.type == 'WINDOW'), None) if area else None
        override = {"window": window, "screen": window.screen}
        if area is not None:
            override["area"] = area
        if region is not None:
            override["region"] = region
        try:
            with bpy.context.temp_override(**override):
                if 'CANCELLED' not in bpy.ops.wm.window_close():
                    closed += 1
        except Exception:  # noqa: BLE001 - never break the close path
            pass
    return closed


def _open_island():
    from mixar.modules.agent_bubble.core import unread
    unread.opened()
    return bpy.ops.mixar.agent_bubble_open_window('INVOKE_DEFAULT')


def _tour_wants_exit_dialog() -> bool:
    """While the interactive tour runs, Escape in the island asks the tour
    to exit (its dialog lives in the main window) instead of minimising
    the island the tour is pointing at. Missing module → False."""
    try:
        from mixar.modules.onboarding.core.tour import session as tour_session
        live = tour_session.current()
        if live is None or not live.running:
            return False
        live.request_exit_confirm()
        return True
    except Exception:  # noqa: BLE001
        return False


class MIXAR_OT_bubble_close(Operator):
    bl_idname = "mixar.bubble_close"
    bl_label = "Minimise"
    bl_description = "Minimise"
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        if not BUBBLE_WINDOW_CONTROLS_SUPPORTED:
            return False
        space = getattr(context, "space_data", None)
        return space is not None and space.type == 'AGENT_BUBBLE'

    def execute(self, context):
        if _tour_wants_exit_dialog():
            return {'FINISHED'}
        # Mark the bubble as user-dismissed so the workspace-change
        # autoshow doesn't immediately re-open it.
        try:
            from mixar.bootstrap import agent_bubble_module
            agent_bubble_module.mark_user_closed()
        except Exception:  # noqa: BLE001 — never break the close path
            pass

        if _pill_off():
            # The floating pill is off (the default): close the chat; the top bar's agent chip opens it again.
            _close_island()
            try:
                capture_bubble_state("minimized", context=context)
            except Exception:
                pass
            return {'FINISHED'}

        # Minimise to pill instead of destroying the window.
        try:
            result = bpy.ops.mixar.bubble_minimise()
            if result == {'FINISHED'}:
                try:
                    capture_bubble_state("minimized", context=context)
                except Exception:
                    pass
            return result
        except RuntimeError:
            return {'CANCELLED'}


class MIXAR_OT_bubble_restore_user(Operator):
    """Restore the bubble and clear the user-minimised workspace intent."""

    bl_idname = "mixar.bubble_restore_user"
    bl_label = "Restore"
    bl_description = "Restore"
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        if not BUBBLE_WINDOW_CONTROLS_SUPPORTED:
            return False
        space = getattr(context, "space_data", None)
        return space is not None and space.type == 'AGENT_BUBBLE'

    def execute(self, context):
        try:
            from mixar.bootstrap import agent_bubble_module
            agent_bubble_module.mark_user_opened()
        except Exception:  # noqa: BLE001 - never break restore
            pass

        try:
            result = bpy.ops.mixar.bubble_restore()
            if result == {'FINISHED'}:
                try:
                    capture_bubble_state("maximized", context=context)
                except Exception:
                    pass
            return result
        except RuntimeError:
            return {'CANCELLED'}


class MIXAR_OT_bubble_toggle_minimise(Operator):
    """Toggle the Agent Bubble between the full window and the floating pill.

    This is the keyboard-shortcut entry point (Cmd/Ctrl+Shift+B). Unlike
    mixar.bubble_close / mixar.bubble_restore_user — which poll for
    AGENT_BUBBLE focus and so only fire while the bubble itself is active —
    this operator has no space restriction, so it works from any editor
    (e.g. while painting in the viewport).

    It drives the raw C++ minimise/restore operators (which have no poll and
    act on the global bubble window handles) and records the user-minimise
    intent so the workspace-change autoshow respects the user's choice, the
    same way the ESC / close-button path does.
    """

    bl_idname = "mixar.bubble_toggle_minimise"
    bl_label = "Toggle Agent Bubble"
    bl_description = "Minimise the Agent Bubble to its pill, or restore it"
    bl_options = {'REGISTER', 'INTERNAL'}

    @classmethod
    def poll(cls, context):
        # No space restriction — the shortcut fires from any editor. The
        # platform gate is the only thing this poll enforces.
        return BUBBLE_WINDOW_CONTROLS_SUPPORTED

    def execute(self, context):
        if _tour_wants_exit_dialog():
            return {'FINISHED'}
        if _pill_off():
            # No pill (the default): the shortcut closes an open chat and opens a closed one.
            if _island_open():
                _close_island()
                MIXAR_OT_bubble_toggle_minimise._mark(closed=True)
            else:
                try:
                    _open_island()
                except RuntimeError:
                    return {'CANCELLED'}
                MIXAR_OT_bubble_toggle_minimise._mark(closed=False)
            return {'FINISHED'}

        # bubble_minimise returns FINISHED when it actually minimises, and
        # CANCELLED when there is no bubble or it is already a pill.
        try:
            result = bpy.ops.mixar.bubble_minimise()
        except RuntimeError:
            result = {'CANCELLED'}

        if result == {'FINISHED'}:
            self._mark(closed=True)
            try:
                capture_bubble_state("minimized", context=context)
            except Exception:
                pass
            return {'FINISHED'}

        # Already minimised (or no bubble): restore. bubble_restore is a safe
        # no-op when the bubble isn't minimised.
        try:
            bpy.ops.mixar.bubble_restore()
        except RuntimeError:
            return {'CANCELLED'}
        self._mark(closed=False)
        try:
            capture_bubble_state("maximized", context=context)
        except Exception:
            pass
        return {'FINISHED'}

    @staticmethod
    def _mark(*, closed: bool) -> None:
        try:
            from mixar.bootstrap import agent_bubble_module
            if closed:
                agent_bubble_module.mark_user_closed()
            else:
                agent_bubble_module.mark_user_opened()
        except Exception:  # noqa: BLE001 — never break the toggle path
            pass


class MIXAR_OT_bubble_toggle_expand_tracked(Operator):
    """Python bridge for the native expand toggle so the user action is visible."""

    bl_idname = "mixar.bubble_toggle_expand_tracked"
    bl_label = "Expand or Collapse Agent Bubble"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        return BUBBLE_WINDOW_CONTROLS_SUPPORTED

    def execute(self, context):
        try:
            result = bpy.ops.mixar.bubble_toggle_expand()
        except RuntimeError:
            return {'CANCELLED'}
        if result == {'FINISHED'}:
            try:
                capture(EVENT_BUBBLE_EXPAND, context=context)
            except Exception:
                pass
        return result


class MIXAR_OT_bubble_block_context_menu(Operator):
    """Consume right-clicks in the bubble/pill without opening UI menus."""

    bl_idname = "mixar.bubble_block_context_menu"
    bl_label = "Block Context Menu"
    bl_description = "Block Context Menu"
    bl_options = {'INTERNAL'}

    @classmethod
    def poll(cls, context):
        space = getattr(context, "space_data", None)
        return space is not None and space.type == 'AGENT_BUBBLE'

    def invoke(self, context, event):
        return {'FINISHED'}

    def execute(self, context):
        return {'FINISHED'}


classes = (
    MIXAR_OT_bubble_close,
    MIXAR_OT_bubble_restore_user,
    MIXAR_OT_bubble_toggle_minimise,
    MIXAR_OT_bubble_toggle_expand_tracked,
    MIXAR_OT_bubble_block_context_menu,
)
