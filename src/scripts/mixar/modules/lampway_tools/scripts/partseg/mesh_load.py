# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ported part-set tools ran inside an open .blend on the shelf; the runner starts Blender empty, so each opens its mesh first: a .blend as it is
(face order and attributes untouched), a .glb/.gltf or .fbx imported into an empty scene."""
import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import lw_canon  # noqa: E402  (canon_io by path: the one importer)


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        raise SystemExit(f"error: no mesh file at {path}")
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext in (".glb", ".gltf", ".fbx"):
        lw_canon.io.import_raw(path)               # a raw part-set source, stamped lw_raw
    else:
        raise SystemExit(f"error: {path}: a .blend, .glb, .gltf or .fbx")
