# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The ported part-set tools ran inside an open .blend on the shelf; the runner starts Blender empty, so each opens its mesh first: a .blend as it is
(face order and attributes untouched), a .glb/.gltf or .fbx imported into an empty scene."""
import os

import bpy


def load(path):
    ext = os.path.splitext(path)[1].lower()
    if not os.path.isfile(path):
        raise SystemExit(f"error: no mesh file at {path}")
    if ext == ".blend":
        bpy.ops.wm.open_mainfile(filepath=path)
        return
    bpy.ops.wm.read_factory_settings(use_empty=True)
    if ext in (".glb", ".gltf"):
        bpy.ops.import_scene.gltf(filepath=path)  # LEGACY(normalize): a raw part-set source; route through canon_io.import_canonical when it lands
    elif ext == ".fbx":
        bpy.ops.import_scene.fbx(filepath=path)  # LEGACY(normalize): a raw part-set source; route through canon_io.import_canonical when it lands
    else:
        raise SystemExit(f"error: {path}: a .blend, .glb, .gltf or .fbx")
