# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Land a Studio job's file in the scene: import it, prefix what it made with the job id, and gather it in the ``Studio`` collection
(never the user's own collections, and never over an existing object: Blender's own numbering keeps names unique)."""

import os

import bpy

from . import canon_io

COLLECTION = "Studio"
_LANDS = (".glb", ".gltf", ".fbx", ".obj")


def import_file(path: str, prefix: str = "") -> dict:
    ext = os.path.splitext(path)[1].lower()
    if ext not in _LANDS:
        raise ValueError(f"cannot import {ext or 'a file without an extension'}; Studio meshes are .glb, .gltf, .fbx or .obj")
    new = [bpy.data.objects[n] for n in canon_io.import_raw(path)["objects"]]
    coll = bpy.data.collections.get(COLLECTION) or bpy.data.collections.new(COLLECTION)
    if COLLECTION not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for ob in new:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
        if prefix and not ob.name.startswith(prefix):
            ob.name = prefix + ob.name
    return {"objects": sorted(o.name for o in new), "collection": coll.name}
