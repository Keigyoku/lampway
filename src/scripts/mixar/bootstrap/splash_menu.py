# SPDX-FileCopyrightText: 2025 Mixar Authors
# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Splash Menu Replacement

Replaces the native WM_MT_splash menu (facelift contract 02): four recent files, the way in
(New scene, Recover, Zen or Engine), the setup as four glance cues, and Help.

Also exposes `is_splash_visible()` so other modules (notably the
agent bubble auto-show) can react to splash dismissal regardless of
HOW the user dismissed it (workspace-switching mode pickers, the
File-New entries, or simply clicking outside the popup). The
detection works by timestamping each draw() call: while the splash
popup is on screen Blender re-runs draw() once per frame; once
dismissed, draws stop entirely and the timestamp goes stale.
"""

import os
import time

import bpy
from bpy.types import Menu

from mixar.config.brand import website_url


# Updated on every WM_MT_splash.draw() call. We treat the splash as
# "visible" if a draw has happened within SPLASH_VISIBLE_WINDOW_S; once
# the user dismisses the popup (mode pick, File-New, click-outside, ESC)
# draws stop firing and this stamp goes stale.
_splash_last_drawn_ts: float = 0.0
# Keep this comfortably above a short bootstrap frame stall so consumers
# do not treat one missed redraw as splash dismissal.
SPLASH_VISIBLE_WINDOW_S = 2.0
_module_load_ts: float = time.monotonic()
_SPLASH_STARTUP_GRACE_S = 3.0  # assume splash is coming for first 3s
# Draw-staleness "splash is gone" window for onboarding_can_start(), used
# only on builds without the native ``WindowManager.mixar_splash_open``.
_SPLASH_GONE_FALLBACK_S = 2.5


def is_splash_visible() -> bool:
    """True iff the splash is likely on screen."""
    if _splash_last_drawn_ts != 0.0:
        return (time.monotonic() - _splash_last_drawn_ts) < SPLASH_VISIBLE_WINDOW_S
    try:
        prefs = bpy.context.preferences
        if prefs is not None and not prefs.view.show_splash:
            return False
    except Exception:
        pass
    # Splash hasn't drawn yet; assume it's coming if we're early in startup.
    return (time.monotonic() - _module_load_ts) < _SPLASH_STARTUP_GRACE_S


# Set True the moment the user leaves the splash by picking a workspace
# mode (Start with Zen Mode / Engine Mode — see workflow.ui_mode_ops).
# A static, still-open popup stops redrawing, so draw-staleness alone
# can't tell "dismissed" from "idle but on screen". Onboarding keys off
# this explicit signal (and the native splash-open flag) so the tour never
# starts *behind* an open splash.
_splash_mode_chosen = False


def notify_mode_chosen() -> None:
    """Record that the user picked a workspace mode from the splash."""
    global _splash_mode_chosen
    _splash_mode_chosen = True


def _native_splash_open():
    """``WindowManager.mixar_splash_open`` (set while the splash popup is
    alive, cleared on every close path), or None on a build without it."""
    try:
        wm = bpy.context.window_manager
        if wm is None:
            return None
        return bool(wm.mixar_splash_open)
    except Exception:
        return None


def onboarding_can_start() -> bool:
    """True once it's safe to start the onboarding tour.

    The tour must only start *after* the user has left the splash — by a
    button or a click outside it — so its opening beat isn't lost behind
    the splash or to the dismissing click.

    * The native flag (``WindowManager.mixar_splash_open``) is authoritative:
      while the popup is alive, wait, however long it sits idle. An idle
      splash stops redrawing, so draw-staleness would read it as closed.
    * Splash closed (or never opened) → go once it has drawn, a mode was
      picked, or the startup grace has passed (Blender suppresses the
      splash on some launch paths, e.g. opening a .blend directly; waiting
      for a splash that never comes would block the tour forever).
    * Builds without the native flag fall back to draw staleness.
    """
    native_open = _native_splash_open()
    if native_open is not None:
        if native_open:
            return False
        return (
            _splash_mode_chosen
            or _splash_last_drawn_ts != 0.0
            or (time.monotonic() - _module_load_ts) >= _SPLASH_STARTUP_GRACE_S
        )
    if _splash_mode_chosen:
        return True
    try:
        prefs = bpy.context.preferences
        if prefs is not None and not prefs.view.show_splash:
            return not is_splash_visible()
    except Exception:
        pass
    if _splash_last_drawn_ts != 0.0:
        return (time.monotonic() - _splash_last_drawn_ts) >= _SPLASH_GONE_FALLBACK_S
    return (time.monotonic() - _module_load_ts) >= _SPLASH_STARTUP_GRACE_S


_bubble_hidden_for_splash = False


def _note_bubble_state(state: str) -> None:
    """Keep telemetry's dedup guard in step with splash-driven bubble changes."""
    try:
        from mixar.modules.common.analytics.bubble_events import (
            note_programmatic_bubble_state,
        )
        note_programmatic_bubble_state(state)
    except Exception:  # noqa: BLE001 — telemetry must never break the splash
        pass


def _hide_bubble_for_splash():
    """Hide the agent bubble/pill while the splash is on screen."""
    global _bubble_hidden_for_splash
    if _bubble_hidden_for_splash:
        if not bpy.app.timers.is_registered(_restore_bubble_after_splash):
            bpy.app.timers.register(_restore_bubble_after_splash, first_interval=0.5)
        return
    try:
        if bpy.ops.mixar.bubble_minimise() == {'FINISHED'}:
            _note_bubble_state("minimized")
    except Exception:
        pass
    _bubble_hidden_for_splash = True
    if not bpy.app.timers.is_registered(_restore_bubble_after_splash):
        bpy.app.timers.register(_restore_bubble_after_splash, first_interval=0.5)


def _restore_bubble_after_splash():
    """Timer: once the splash stops drawing, restore the bubble."""
    global _bubble_hidden_for_splash
    if is_splash_visible():
        return 0.3
    if _bubble_hidden_for_splash:
        try:
            if bpy.ops.mixar.bubble_restore() == {'FINISHED'}:
                _note_bubble_state("maximized")
        except Exception:
            pass
        _bubble_hidden_for_splash = False
    return None


def has_splash_ever_drawn() -> bool:
    """True once the splash has been drawn at least once this session."""
    return _splash_last_drawn_ts != 0.0


def _recent_files_path() -> str:
    return os.path.join(bpy.utils.user_resource('CONFIG'), "recent-files.txt")


def recent_files(limit: int = 4) -> list:
    """The last files opened that still exist, newest first (Blender's own recent-files list)."""
    try:
        with open(_recent_files_path(), encoding="utf-8") as fh:
            lines = [line.strip() for line in fh]
    except OSError:
        return []
    return [path for path in lines if path and os.path.isfile(path)][:limit]


class LAMPWAY_MT_splash_help(Menu):
    """Docs, what is new and how to report a bug, in one place"""
    bl_label = "Help"

    def draw(self, context):
        layout = self.layout
        layout.operator("wm.url_open", text="Documentation", icon='HELP').url = website_url("/docs")
        layout.operator("wm.url_open", text="What is new", icon='URL').url = website_url("/changelog")
        layout.operator("wm.url_open", text="Report a bug", icon='URL').url = website_url("/issues")


class WM_MT_splash(Menu):
    """Recent files, the way in, and your setup at a glance"""

    # Facelift contract 02. Reads cached state only (the status bar's cache): never the network in draw().

    bl_label = "Splash"

    def draw(self, context):
        global _splash_last_drawn_ts
        _splash_last_drawn_ts = time.monotonic()

        # Native window-manager code suppresses Mixar floating dock
        # windows while the splash UI block is open. Do not minimise
        # the bubble here; doing both creates conflicting restore state.

        layout = self.layout
        layout.operator_context = 'EXEC_DEFAULT'
        layout.emboss = 'PULLDOWN_MENU'
        layout.scale_y = 1.3

        split = layout.split()
        recent = split.column()
        recent.label(text="Recent Files")
        paths = recent_files()
        for path in paths:
            recent.operator("wm.open_mainfile", text=os.path.basename(path), icon='FILE_BLEND').filepath = path
        if not paths:
            recent.label(text="No recent files")

        start = split.column()
        start.label(text="Start")
        start.operator("wm.read_homefile", text="New scene", icon='FILE_NEW')
        start.operator("wm.recover_last_session", text="Recover last session", icon='RECOVER_LAST')
        way = start.row(align=True)
        way.operator("mixar.set_ui_mode_ai", text="Start in Lamplight")
        way.operator("mixar.set_ui_mode_pro", text="Start in Workshop")

        layout.separator()
        _draw_setup(layout.row(align=True))
        layout.menu("LAMPWAY_MT_splash_help", text="Help", icon='HELP')


def _draw_setup(row) -> None:
    """Four glance cues: the server, the agent's plan, the routes, today's spend (DESIGN.md 13)."""
    from mixar.modules.lampway_tools import statusbar_state as S
    from mixar.modules.lampway_tools import studio_state
    if not S.STATE["ok"]:
        row.label(text="Lampway's server is not running", icon='LAMPWAY_LAMP')
        return
    row.label(text="server on this machine", icon='LAMPWAY_LAMP')
    provider = ((studio_state.PROVIDERS or {}).get("values") or {}).get("provider")
    row.label(text=f"agent: {provider}" if provider else "agent: open Providers to choose", icon='LAMPWAY_SPARK')
    row.operator("lampway.status_wire", text=S.wire_chip()[0], icon='LAMPWAY_WIRE', emboss=False)
    row.operator("lampway.status_spend", text=S.spend_line()[0], icon='LAMPWAY_COIN', emboss=False)
    row.operator("lampway.providers_open", text="Providers and privacy", icon='LAMPWAY_SHIELD')


def register():
    """Replace native WM_MT_splash with custom one."""
    global _splash_mode_chosen
    _splash_mode_chosen = False
    bpy.utils.register_class(LAMPWAY_MT_splash_help)
    bpy.utils.register_class(WM_MT_splash)


def unregister():
    """Restore native WM_MT_splash."""

    # Stop the bubble-restore poll timer if it's still scheduled — its
    # closure keeps the bubble operator wired in even after teardown.
    try:
        if bpy.app.timers.is_registered(_restore_bubble_after_splash):
            bpy.app.timers.unregister(_restore_bubble_after_splash)
    except Exception:
        pass

    # Unregister our custom menu
    bpy.utils.unregister_class(WM_MT_splash)
    bpy.utils.unregister_class(LAMPWAY_MT_splash_help)
