# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later

"""Preview icons for Python surfaces (facelift contract 14).

A native Lampway icon (``icon='LAMPWAY_COIN'``) takes the theme's text colour; a cue that means something by its colour
(an agent state, the gauge, the sending wire: DESIGN.md 13) needs its colour baked in, and a Python panel cannot colour
an icon. These are the same SVGs, rendered with the cue colour of each theme by
``scripts/dev/brand_art/lampway_icons.py``: ``night/`` for a dark theme, ``paper/`` for a light one.

    from mixar.modules.common.lampway_icons import icon_id
    row.label(text="Working", icon_value=icon_id("agent_working"))
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
_collections = {}


def theme_set(theme):
    """'night' for a dark theme, 'paper' for a light one, read from the theme's own canvas."""
    r, g, b = list(theme.user_interface.mixar_canvas)[:3]
    return "night" if 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5 else "paper"


def path(name, size=32, theme_name="night"):
    key = name if size == 32 else f"{name}_{size}"
    file = os.path.join(HERE, theme_name, key + ".png")
    if not os.path.isfile(file):
        raise KeyError(f"no Lampway preview icon {key!r} for {theme_name}: render it with "
                       "scripts/dev/brand_art/lampway_icons.py")
    return key, file


def icon_id(name, size=32, theme=None):
    """The preview icon id of a Lampway glyph in the current theme's colours (16 px exists for the agent states)."""
    import bpy
    import bpy.utils.previews
    theme_name = theme_set(theme or bpy.context.preferences.themes[0])
    key, file = path(name, size, theme_name)
    collection = _collections.get(theme_name)
    if collection is None:
        collection = _collections[theme_name] = bpy.utils.previews.new()
    if key not in collection:
        collection.load(key, file, 'IMAGE')
    return collection[key].icon_id


def unregister():
    import bpy.utils.previews
    for collection in _collections.values():
        bpy.utils.previews.remove(collection)
    _collections.clear()
