# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Lampway Night for existing profiles (facelift decision F2).

A new profile starts in Lampway Night: it is the compiled default theme. An existing profile keeps the colours it
saved (the fork's rule: a user's theme changes only when the user picks one), so it is offered Night once, as a toast
with one button. The offer is recorded in the user config whether it was shown or not needed, so it never returns.
"""

import xml.etree.ElementTree as ET

PRESET = "Lampway_Night.xml"
OFFERED_KEY = "lampway_night_offered"
TOAST_ID = "lampway_night_offer"
APPLY_OPERATOR = "lampway.apply_night_theme"
TITLE = "Try Lampway Night"
BODY = "Lampway's own theme: night slate and lamplight. Your colours stay until you choose."

# A profile wears Night when these read back as the preset's: the fork's chrome, Blender's widgets, the viewport.
FINGERPRINT = (
    ("user_interface", "mixar_canvas", "user_interface/ThemeUserInterface"),
    ("user_interface.wcol_regular", "inner", "user_interface/ThemeUserInterface/wcol_regular/ThemeWidgetColors"),
    ("view_3d.space.gradients", "high_gradient",
     "view_3d/ThemeView3D/space/ThemeSpaceGradient/gradients/ThemeGradientColors"),
)


def preset_path(directories):
    """The shipped Night preset in the first preset directory that has it, or None."""
    import os
    for directory in directories:
        path = os.path.join(directory, PRESET)
        if os.path.isfile(path):
            return path
    return None


def wears(theme, preset):
    """True when the theme's fingerprint colours are the preset's (within one step of 255)."""
    root = ET.parse(preset).getroot().find("Theme")
    for rna_path, attr, xml_path in FINGERPRINT:
        hx = root.find(xml_path).attrib[attr][1:]
        want = [int(hx[i:i + 2], 16) / 255 for i in range(0, len(hx), 2)]
        owner = theme
        for part in rna_path.split("."):
            owner = getattr(owner, part)
        got = list(getattr(owner, attr))[:len(want)]
        if len(got) != len(want) or any(abs(a - b) > 1.5 / 255 for a, b in zip(got, want)):
            return False
    return True


def schedule_offer(bpy, delay=3.0):
    """At startup, in a UI session only: offer Night once the preferences and the toast layer are up.

    A headless run never offers (and so never uses up the one offer). Returns whether a timer was registered.
    """
    if bpy.app.background:
        return False

    def _offer():
        from mixar.config import config
        from mixar.modules.common.notifications.store import get_notification_store
        path = preset_path(bpy.utils.preset_paths("interface_theme"))
        if path is not None:
            offer_once(bpy.context.preferences.themes[0], path, config, get_notification_store())
        return None

    bpy.app.timers.register(_offer, first_interval=delay)
    return True


def offer_once(theme, preset, config, store):
    """Offer Night to a profile that does not wear it, once. Returns what happened.

    ``config`` has ``get_config()``/``add_config()`` (mixar.config.config); ``store`` has ``push()`` (the
    notification store). Nothing about the theme changes here: the toast's button does that, if pressed.
    """
    if config.get_config().get(OFFERED_KEY):
        return "already-offered"
    if wears(theme, preset):
        config.add_config(OFFERED_KEY, True)
        return "wears-night"
    from mixar.modules.common.notifications.store import NotificationAction

    store.push(type_str="info", title=TITLE, body=BODY, priority="normal",
               actions=[NotificationAction(label=TITLE, operator=APPLY_OPERATOR, style="primary")],
               ttl_ms=0, id=TOAST_ID, dismissible=True)
    config.add_config(OFFERED_KEY, True)
    return "offered"
