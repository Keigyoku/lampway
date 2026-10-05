# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Draw-time guards. A header draw that adds an operator which is not registered yet (the UI modules register in batches after the
first redraws) makes Blender report the Python call site on every redraw: bare ``file:line`` lines, ten of them at boot."""

import bpy


def operator_exists(idname: str) -> bool:
    """True when ``idname`` ("module.name") is a registered operator."""
    module, _, name = idname.partition(".")
    return bool(name) and name in dir(getattr(bpy.ops, module, ()))
