# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 07 in the window (the sidebar's classes register with the deferred UI, which a background run never
reaches): the Way's step panels and one typed operator per tool are registered, the free-text runners are gone, and a
tool run from its typed operator (Retopology on the Cube, 200 faces, the real tool) marks its step done on the piece."""

import json

SETTLE_TICKS = 6
OUT = {}


def setup(bpy):
    from mixar.modules.lampway_tools import the_way
    OUT["panels"] = [s["id"] for s in the_way.steps() if hasattr(bpy.types, "LAMPWAY_PT_way_" + s["id"])]
    props = bpy.ops.lampway.tool_retopo.get_rna_type().properties
    OUT["kinds"] = {p.identifier: p.type for p in props if p.identifier in ("object", "target_faces", "symmetry", "adaptivity")}
    OUT["free_text"] = [n for n in ("LAMPWAY_PT_tools", "LAMPWAY_PT_features") if hasattr(bpy.types, n)]
    cube = bpy.data.objects["Cube"]
    bpy.context.view_layer.objects.active = cube
    win = bpy.context.window_manager.windows[0]
    with bpy.context.temp_override(window=win):
        OUT["run"] = list(bpy.ops.lampway.tool_retopo(object="Cube", target_faces=200))
    OUT["done"] = sorted(the_way.done_steps(cube))
    OUT["message"] = bpy.context.scene.lampway_tools.last_message[:200]


def surfaces(bpy, dump):
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    return OUT
