# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""A new profile (no preferences) in its default theme, the Layout workspace, the Cube selected and active.

Surfaces (contract 01, T9): the outliner's active row and the outliner's back.
"""

import json  # noqa: F401  (states may read the QA dump as JSON)


def _outliner(bpy):
    win = bpy.context.window_manager.windows[0]
    area = next(a for a in win.screen.areas if a.type == 'OUTLINER')
    return win, area, next(r for r in area.regions if r.type == 'WINDOW')


def setup(bpy):
    win = bpy.context.window_manager.windows[0]
    win.workspace = bpy.data.workspaces["Layout"]
    cube = bpy.data.objects["Cube"]
    with bpy.context.temp_override(window=win):
        bpy.context.view_layer.objects.active = cube
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.object.select_pattern(pattern="Cube", extend=False)  # tags the outliner's selection sync


def surfaces(bpy, dump):
    _win, area, region = _outliner(bpy)
    # The Cube row: the dump's widgets in this outliner whose RNA owner is the Cube (its restrict toggles).
    rows = [w["rect"] for w in dump["widgets"]
            if w.get("a") is not None and w.get("prop_owner") == "Cube" and w.get("at") == 3 and w.get("rt") == 0]
    if not rows:
        raise RuntimeError("no outliner row for Cube in the QA dump")
    ymin, ymax = rows[0][1], rows[0][3]
    centre, row = (ymin + ymax) // 2, ymax - ymin
    return {
        "outliner_active_row": (region.x + int(region.width * 0.55), centre),
        # Empty rows alternate between the back and the 3 percent stripe (`row_alternate`); the stripes fall on the
        # Cube's parity, so three rows below the Cube (past Light, in the empty list) is plain back.
        "outliner_back": (region.x + int(region.width * 0.55), centre - 3 * row),
    }


def regions(bpy):
    _win, area, region = _outliner(bpy)
    return {"outliner": [region.x, region.y, region.x + region.width, region.y + region.height]}
