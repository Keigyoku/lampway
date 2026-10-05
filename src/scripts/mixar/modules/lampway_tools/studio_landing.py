# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Land a Studio job's file in the scene: import it, prefix what it made with the job id, and gather it in the ``Studio`` collection
(never the user's own collections, and never over an existing object: Blender's own numbering keeps names unique)."""

import os

import bpy

COLLECTION = "Studio"
_IMPORTERS = {".glb": "import_scene.gltf", ".gltf": "import_scene.gltf", ".fbx": "import_scene.fbx", ".obj": "wm.obj_import"}


def import_file(path: str, prefix: str = "") -> dict:
    ext = os.path.splitext(path)[1].lower()
    op = _IMPORTERS.get(ext)
    if op is None:
        raise ValueError(f"cannot import {ext or 'a file without an extension'}; Studio meshes are .glb, .gltf, .fbx or .obj")
    before = set(bpy.data.objects.keys())
    module, name = op.split(".")
    getattr(getattr(bpy.ops, module), name)(filepath=path)
    new = [bpy.data.objects[n] for n in bpy.data.objects.keys() if n not in before]
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
