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


@canon_io.rollback_imports
def import_file(path: str, prefix: str = "", turn_deg=None, generator: str = "unknown") -> dict:
    """Import a Studio file RAW (canon_io), then normalize every mesh it made (lampway_normalize_mesh) when the piece's facing is
    declared (``turn_deg``); without it the objects land raw (``lw_raw``) and ``normalize`` says why - every door refuses them until
    they are normalized (the frame is never guessed: one Tripo set mixes facings, canon 01 B)."""
    from .features import normalize as N
    ext = os.path.splitext(path)[1].lower()
    if ext not in _LANDS:
        raise ValueError(f"cannot import {ext or 'a file without an extension'}; Studio meshes are .glb, .gltf, .fbx or .obj")
    imp = canon_io.import_raw(path, **N.PINNED.get(ext.lstrip("."), {}))
    new = [bpy.data.objects[n] for n in imp["objects"]]
    note = None
    raw = {k: imp[k] for k in ("sha256", "container", "importer", "settings")}
    raw["bytes"] = os.path.getsize(path)
    for ob in [o for o in new if o.type == "MESH"]:
        before_normalize = canon_io.snapshot_ids()
        try:
            N.normalize_object(ob, turn_deg=turn_deg, generator=generator, raw=raw, path_hint=os.path.basename(path))
        except Exception as exc:                                             # the refusal lands the object raw and says why
            note = str(exc)
        finally:
            # Normalizing this imported asset can replace its mesh; a later landing failure owns that replacement too.
            canon_io._record_import(before_normalize)
    coll = bpy.data.collections.get(COLLECTION) or bpy.data.collections.new(COLLECTION)
    if COLLECTION not in bpy.context.scene.collection.children:
        bpy.context.scene.collection.children.link(coll)
    for ob in new:
        for c in list(ob.users_collection):
            c.objects.unlink(ob)
        coll.objects.link(ob)
        if prefix and not ob.name.startswith(prefix):
            ob.name = prefix + ob.name
    out = {"objects": sorted(o.name for o in new), "collection": coll.name, "canonical": note is None}
    if note:
        out["normalize"] = note
    return out
