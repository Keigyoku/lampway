# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ported part-set tools ran inside an open .blend on the shelf; the runner starts Blender empty, so each opens its mesh first: a .blend as it is
(face order and attributes untouched), a .glb/.gltf or .fbx imported into an empty scene."""
import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        raise SystemExit(f"error: no mesh file at {path}")
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        return
    if ext not in (".glb", ".gltf", ".fbx"):
        raise SystemExit(f"error: {path}: a .blend, .glb, .gltf or .fbx")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    import lw_canon                                          # canon_io, the one importer: the import is stamped lw_raw
    lw_canon.io.import_raw(path)
