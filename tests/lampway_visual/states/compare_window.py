# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 11 in the window: a blind compare set of four scene objects (a cube, a sphere, a cone, a torus), opened in
its own window: one 3D view per model in local view, in Wire. The facts are the new window's views, each view's local
objects and the overlay text it draws."""

import os
import sys

SETTLE_TICKS = 24
OUT = {}


def setup(bpy):
    from mixar.modules.lampway_tools import api
    from mixar.modules.lampway_tools.ui import compare as CMP
    for add in (bpy.ops.mesh.primitive_cube_add, bpy.ops.mesh.primitive_uv_sphere_add, bpy.ops.mesh.primitive_cone_add,
                bpy.ops.mesh.primitive_torus_add):
        add()
    names = [o.name for o in bpy.context.scene.objects if o.type == 'MESH']
    built = api.model_compare(action="build", set={"id": "vt", "piece": "compare", "models": [{"object": n} for n in names[:4]]}, blind=True)
    OUT["built"] = built.get("ok", True)

    def go():
        CMP.STATE.update(manifest=None)
        man_dir = built.get("set_dir") or ""
        CMP.load_set("vt", "compare", CMP._root())
        OUT["areas"] = CMP.open_window(bpy.context)
        return None

    bpy.app.timers.register(go, first_interval=0.5)


def _compare_window(bpy):
    from mixar.modules.lampway_tools.ui import compare as CMP
    return next((w for w in bpy.context.window_manager.windows if w.as_pointer() == CMP.STATE.get("window")), None)


def surfaces(bpy, dump):
    win = _compare_window(bpy)
    if win is not None:
        out_dir = sys.argv[sys.argv.index("--") + 2]
        win.mixar_qa_capture_frame(filepath=os.path.join(out_dir, "frame.png"), x=0, y=0, width=win.width, height=win.height)
    return {}


def regions(bpy):
    return {}


def facts(bpy, dump):
    from mixar.modules.lampway_tools.ui import compare as CMP
    win = _compare_window(bpy)
    views = []
    if win is not None:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                views.append({"local": space.local_view is not None, "overlay": CMP.overlay_for(area.as_pointer()),
                              "wire": space.overlay.show_wireframes, "width": area.width})
    return dict(OUT, window=win is not None, views=views, scene=win.scene.name if win else "")
