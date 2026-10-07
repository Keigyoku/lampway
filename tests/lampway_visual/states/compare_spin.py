# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Contract 11's Spin (mrmak/05 6.6): with Spin on, every compare view turns about the vertical together; a manual orbit in
one view turns Spin off and the others follow that view. Facts: each view's yaw sampled while spinning, then after an orbit."""

import math
import runpy
import os

_base = runpy.run_path(os.path.join(os.path.dirname(os.path.abspath(__file__)), "compare_window.py"))
SETTLE_TICKS = 40
OUT = _base["OUT"]


def _yaws(CMP):
    out = []
    for _w, area in CMP._compare_areas():
        e = area.spaces.active.region_3d.view_rotation.to_euler()
        out.append(round(math.degrees(e.z), 3))
    return out


def setup(bpy):
    _base["setup"](bpy)
    from mixar.modules.lampway_tools.ui import compare as CMP

    def spin_on():
        if not CMP.STATE["areas"]:
            return 0.25
        OUT["yaw0"] = _yaws(CMP)
        bpy.ops.lampway.compare_toggle(what="spin")
        OUT["spin_after_toggle"] = CMP.STATE["spin"]
        bpy.app.timers.register(sample, first_interval=1.5)
        return None

    def sample():
        OUT["yaw1"] = _yaws(CMP)
        # a manual orbit in the first view (as a drag would leave it)
        _w, area = CMP._compare_areas()[0]
        r3d = area.spaces.active.region_3d
        from mathutils import Quaternion
        r3d.view_rotation = Quaternion((1, 0, 0), math.radians(30)) @ r3d.view_rotation
        bpy.app.timers.register(after_orbit, first_interval=0.6)
        return None

    def after_orbit():
        OUT["spin_after_orbit"] = CMP.STATE["spin"]
        OUT["yaw2"] = _yaws(CMP)
        bpy.app.timers.register(still, first_interval=0.6)
        return None

    def still():
        OUT["yaw3"] = _yaws(CMP)
        return None

    bpy.app.timers.register(spin_on, first_interval=1.0)


surfaces = _base["surfaces"]
regions = _base["regions"]


def facts(bpy, dump):
    return dict(OUT)
