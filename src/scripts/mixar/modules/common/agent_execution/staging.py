# SPDX-FileCopyrightText: 2026 Adeveda Enterprises Private Limited
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Worker-side staging: write a task's objects as a native artifact.

Called from a TRUSTED backend script template that runs inside the
background worker's sandboxed executor (``mixar.*`` imports are allowed
there). The staging directory comes from the launch environment the parent
wrote (``MIXAR_SANDBOX_STAGING_DIR``); the returned manifest is path-free.
"""

from __future__ import annotations

import hashlib
import math
import os
import uuid
from typing import Iterable

from .artifacts import is_artifact_id

STAGING_ENV = "MIXAR_SANDBOX_STAGING_DIR"


def staging_root() -> str:
    root = os.environ.get(STAGING_ENV, "")
    if not root or not os.path.isdir(root):
        raise RuntimeError("worker has no staging directory (MIXAR_SANDBOX_STAGING_DIR)")
    return root


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _bbox(objects) -> tuple[list, list, bool]:
    lo = [math.inf] * 3
    hi = [-math.inf] * 3
    finite = True
    for ob in objects:
        try:
            mw = ob.matrix_world
            for corner in ob.bound_box:
                p = mw @ type(mw.translation)(corner) if hasattr(mw, "translation") else corner
                for i in range(3):
                    v = float(p[i])
                    if not math.isfinite(v):
                        finite = False
                        continue
                    lo[i] = min(lo[i], v)
                    hi[i] = max(hi[i], v)
        except Exception:
            continue
    if any(math.isinf(v) for v in lo + hi):
        return [0.0, 0.0, 0.0], [0.0, 0.0, 0.0], finite and False
    return lo, hi, finite


def stage_collection(artifact_id: str, collection_name: str, object_names: Iterable[str]) -> dict:
    """Move ``object_names`` into ``collection_name`` and write the artifact."""
    import bpy

    if not is_artifact_id(artifact_id):
        artifact_id = str(uuid.uuid4())
    if not collection_name or "/" in collection_name or "\\" in collection_name:
        raise ValueError("collection_name must be a plain datablock name")
    root = staging_root()

    coll = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
    objects = []
    missing = []
    for name in object_names:
        ob = bpy.data.objects.get(name)
        if ob is None:
            missing.append(name)
            continue
        for user in list(ob.users_collection):
            if user is not coll:
                try:
                    user.objects.unlink(ob)
                except Exception:
                    pass
        if ob.name not in coll.objects:
            coll.objects.link(ob)
        objects.append(ob)
    try:
        bpy.ops.file.pack_all()
    except Exception:
        pass

    path = os.path.join(root, f"{artifact_id}.blend")
    bpy.data.libraries.write(path, {coll}, fake_user=True)
    lo, hi, finite = _bbox(objects)
    return {
        "artifact_id": artifact_id,
        "collection_name": coll.name,
        "object_names": [o.name for o in objects],
        "missing_objects": missing,
        "content_hash": _sha256(path),
        "size_bytes": os.path.getsize(path),
        "object_count": len(objects),
        "bbox_min": lo,
        "bbox_max": hi,
        "finite": bool(finite and objects),
    }


def reset_worker_scene() -> dict:
    """Return the worker to an empty document so it can be reused."""
    import bpy

    try:
        bpy.ops.wm.read_homefile(use_empty=True)
        return {"success": True, "method": "read_homefile"}
    except Exception:
        pass
    removed = 0
    for collection_name in ("objects", "meshes", "materials", "images", "collections"):
        data = getattr(bpy.data, collection_name)
        for block in list(data):
            try:
                data.remove(block)
                removed += 1
            except Exception:
                pass
    return {"success": True, "method": "manual", "removed": removed}


# --- Lampway additions: hand a worker the objects it must work ON ---------------------------------------------------
# Mixar's harness moves results worker -> parent only; a worker that works on an existing piece (Mesh QA on Boots1_uv) needs the
# reverse. The parent copies the named objects into a staged artifact (``export_copies``, run by the server as a trusted script on
# the PARENT), the worker loads it first thing (``import_artifact``, trusted script on the WORKER). Same staging directory, same
# bare-uuid artifact ids, same hash discipline as the commit direction.

def export_copies(artifact_id: str, object_names: Iterable[str], instance_id: str = "") -> dict:
    """Write the named objects (with their data) of THIS scene to a native artifact and leave the scene exactly as it was."""
    import bpy

    from .artifacts import sha256_file
    from .paths import staging_dir

    if not is_artifact_id(artifact_id):
        raise ValueError("artifact_id must be a bare uuid")
    iid = instance_id or str(getattr(bpy.context.window_manager, "mixie_instance_id", "") or "")
    names = list(object_names)
    missing = [n for n in names if bpy.data.objects.get(n) is None]
    if missing or not names:
        raise LookupError(f"no object(s) {missing or names!r}; the objects are: {sorted(o.name for o in bpy.data.objects)[:40]}")
    holder = bpy.data.collections.new("lw_export_" + artifact_id[:8])
    try:
        for n in names:
            holder.objects.link(bpy.data.objects[n])
        path = os.path.join(staging_dir(iid), f"{artifact_id}.blend")
        bpy.data.libraries.write(path, {holder}, fake_user=True)
    finally:
        for ob in list(holder.objects):
            holder.objects.unlink(ob)
        bpy.data.collections.remove(holder)
    return {"artifact_id": artifact_id, "object_names": names, "content_hash": sha256_file(path), "size_bytes": os.path.getsize(path)}


def import_artifact(artifact_id: str) -> dict:
    """Load a parent-exported artifact into THIS (worker) scene: its objects land in the scene's own collection."""
    import bpy

    if not is_artifact_id(artifact_id):
        raise ValueError("artifact_id must be a bare uuid")
    path = os.path.join(staging_root(), f"{artifact_id}.blend")
    if not os.path.isfile(path):
        raise FileNotFoundError(f"artifact {artifact_id} is not in this worker's staging directory")
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        dst.collections = list(src.collections)
    names = []
    for coll in [c for c in dst.collections if c is not None]:
        for ob in list(coll.all_objects):
            if ob.name not in bpy.context.scene.collection.all_objects:
                bpy.context.scene.collection.objects.link(ob)
            names.append(ob.name)
        bpy.data.collections.remove(coll)
    return {"artifact_id": artifact_id, "object_names": names}


def stage_scene(artifact_id: str, collection_name: str, skip_objects: Iterable[str] = ()) -> dict:
    """Stage everything the worker made, KEEPING its own collections (Lampway addition). ``stage_collection`` moves objects into one flat
    collection; a worker that drew ``QA_<piece>`` wants that collection to land as it is. The staged collection holds the scene's
    top-level collections as children and its loose objects directly; ``skip_objects`` (the seeded inputs) are left out."""
    import bpy

    if not is_artifact_id(artifact_id):
        artifact_id = str(uuid.uuid4())
    if not collection_name or "/" in collection_name or "\\" in collection_name:
        raise ValueError("collection_name must be a plain datablock name")
    root = staging_root()
    skip = set(skip_objects)
    scene_root = bpy.context.scene.collection
    coll = bpy.data.collections.get(collection_name) or bpy.data.collections.new(collection_name)
    objects, kept = [], []
    for child in list(scene_root.children):
        if child is coll:
            continue
        if all(o.name in skip for o in child.all_objects):          # nothing of the worker's in it (an inputs-only collection)
            continue
        coll.children.link(child)
        kept.append(child.name)
        objects.extend(o for o in child.all_objects if o.name not in skip)
    for ob in list(scene_root.objects):
        if ob.name in skip:
            continue
        if ob.name not in coll.objects:
            coll.objects.link(ob)
        objects.append(ob)
    try:
        bpy.ops.file.pack_all()
    except Exception:
        pass
    path = os.path.join(root, f"{artifact_id}.blend")
    bpy.data.libraries.write(path, {coll}, fake_user=True)
    lo, hi, finite = _bbox(objects)
    return {
        "artifact_id": artifact_id, "collection_name": coll.name, "object_names": [o.name for o in objects],
        "collections": kept, "missing_objects": [], "content_hash": _sha256(path), "size_bytes": os.path.getsize(path),
        "object_count": len(objects), "bbox_min": lo, "bbox_max": hi, "finite": bool(finite and objects),
    }
