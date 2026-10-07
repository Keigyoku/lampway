# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""canon_io: the ONLY module that calls Blender's importers (specs/canon/normalization DOOR.md section 1).

* ``import_raw(path, **settings)``: one import, its settings passed through and RECORDED, every datablock it made (objects, their
  data, armatures, actions, images, materials) stamped ``lw_raw`` = {sha256 of the file's bytes, container, importer, settings}.
  A raw datablock is not canonical: every door refuses it until a ``lampway_normalize_<kind>`` tool has run (D9: hash-bound).
* ``load_image(path, role=None, **kw)``: the only image load; the role binds the colour space (basecolor / emission / reference
  sRGB, hdri Linear Rec.709, every data role Non-Color); stamped like an import.
* ``load_library(path, **kw)``: the only ``bpy.data.libraries.load`` (a context manager, as Blender's).
* ``facts(ob)``: what a door re-measures (object matrix, scene unit, bounds, geometry hash over the evaluated-free mesh).
* ``read_npz`` / ``write_npz``: an npz with its ``canon`` header (a 0-d string array holding the canonical document).

The tests' AST scan (tests/lampway_tools/test_canon_doors.py) fails on any importer call anywhere else, by file:line. Kept free of
package-relative imports so the batch scripts can import it from their own Blender."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
import hashlib
import json
import os

import bpy
import numpy as np

IMPORTERS = {".glb": ("import_scene", "gltf"), ".gltf": ("import_scene", "gltf"), ".fbx": ("import_scene", "fbx"),
             ".obj": ("wm", "obj_import"), ".bvh": ("import_anim", "bvh"), ".usd": ("wm", "usd_import"), ".usda": ("wm", "usd_import"),
             ".usdc": ("wm", "usd_import"), ".usdz": ("wm", "usd_import"), ".stl": ("wm", "stl_import"), ".ply": ("wm", "ply_import")}
# Blender 5's C++ FBX importer instead of the add-on: the Vault's placement and catalogue export read FBX with it (flavour="native").
NATIVE = dict(IMPORTERS, **{".fbx": ("wm", "fbx_import")})
SRGB_ROLES = ("basecolor", "emission", "reference")
LINEAR_ROLES = ("hdri",)
DATA_ROLES = ("normal", "roughness", "metallic", "ao", "orm", "height", "displacement", "opacity", "mask", "material_id", "curvature")
_KINDS = ("objects", "meshes", "armatures", "actions", "images", "materials", "curves",
          "cameras", "lights", "textures", "node_groups", "collections", "scenes", "worlds")


_IMPORT_SCOPES = ContextVar("lampway_import_scopes", default=())


def _record_import(before):
    pointers = {d.as_pointer() for k in _KINDS for d in getattr(bpy.data, k) if d not in before[k]}
    for scope in _IMPORT_SCOPES.get():
        scope.update(pointers)


def _remove_imported(pointers):
    for kind in ("objects", "scenes", *[k for k in _KINDS if k not in ("objects", "scenes")]):
        collection = getattr(bpy.data, kind)
        for data in [d for d in collection if d.as_pointer() in pointers]:
            collection.remove(data, do_unlink=True)
    bpy.context.view_layer.update()


def rollback_imports(function):
    """A failed consumer removes only IDs its imports created; successful persistent imports stay."""
    @wraps(function)
    def guarded(*args, **kwargs):
        made = set()
        selection = _selection()
        token = _IMPORT_SCOPES.set((*_IMPORT_SCOPES.get(), made))
        try:
            result = function(*args, **kwargs)
            if isinstance(result, dict) and result.get("ok") is False:
                _remove_imported(made)
                _restore_selection(selection)
            return result
        except BaseException:
            _remove_imported(made)
            _restore_selection(selection)
            raise
        finally:
            _IMPORT_SCOPES.reset(token)
    return guarded


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _selection():
    return (list(bpy.context.selected_objects), bpy.context.view_layer.objects.active)


def _restore_selection(selection):
    selected, active = selection
    present = set(bpy.context.view_layer.objects)
    for ob in bpy.context.selected_objects:
        ob.select_set(False)
    for ob in selected:
        if ob in present:
            ob.select_set(True)
    bpy.context.view_layer.objects.active = active if active in present else None
    bpy.context.view_layer.update()


def snapshot_ids():
    return {**{k: set(getattr(bpy.data, k)) for k in _KINDS}, "selection": _selection()}


def remove_new_ids(before):
    """Remove only IDs created after a transaction's snapshot, including partial imports."""
    pointers = {d.as_pointer() for k in _KINDS for d in getattr(bpy.data, k) if d not in before[k]}
    _remove_imported(pointers)
    _restore_selection(before["selection"])


def _stamp(db, record):
    try:
        db["lw_raw"] = json.dumps(record, sort_keys=True)
    except (TypeError, AttributeError):                                        # a datablock without ID properties
        pass


def importers(flavour="addon"):
    """{extension: (operator module, name)} of ``flavour``: addon (the default table) or native (FBX through wm.fbx_import)."""
    if flavour not in ("addon", "native"):
        raise ValueError(f"flavour is addon or native, not {flavour!r}")
    return NATIVE if flavour == "native" else IMPORTERS


def import_raw(path, flavour="addon", **settings):
    """{objects, meshes, armatures, actions, images, materials (names of what the import made), sha256, container, importer,
    settings, result (the operator's return set)}. Refuses a container no importer of ``flavour`` reads."""
    path = os.fspath(path)
    ext = os.path.splitext(path)[1].lower()
    table = importers(flavour)
    if ext not in table:
        raise ValueError(f"cannot import {ext or 'a file without an extension'}: canon_io reads {', '.join(sorted(table))}")
    module, name = table[ext]
    record = {"sha256": file_sha256(path), "container": ext.lstrip("."), "importer": f"{module}.{name}", "settings": dict(settings)}
    before = snapshot_ids()
    try:
        result = getattr(getattr(bpy.ops, module), name)(filepath=path, **settings)
        if "FINISHED" not in result:
            raise RuntimeError(f"{module}.{name} did not finish: {sorted(result)}")
    except BaseException:
        remove_new_ids(before)
        raise
    _record_import(before)
    out = dict(record, result=sorted(result))
    for k in _KINDS:
        new = [d for d in getattr(bpy.data, k) if d not in before[k]]
        for d in new:
            _stamp(d, record)
        out[k] = sorted(d.name for d in new)
    return out


def colour_space(role):
    if role in SRGB_ROLES:
        return "sRGB"
    if role in LINEAR_ROLES:
        return "Linear Rec.709"
    if role in DATA_ROLES:
        return "Non-Color"
    raise ValueError(f"unknown texture role {role!r}: one of {', '.join(SRGB_ROLES + LINEAR_ROLES + DATA_ROLES)}")


def load_image(path, role=None, **kw):
    """The image at ``path`` (Blender's ``images.load`` keywords pass through), its colour space bound to ``role`` when one is
    given, stamped ``lw_raw`` with the role."""
    path = os.fspath(path)
    before = snapshot_ids() if _IMPORT_SCOPES.get() else None
    img = bpy.data.images.load(path, **kw)
    if before is not None:
        _record_import(before)
    if "lw_canon" in img.keys():                                    # check_existing returned a normalized image: it stays canonical
        return img
    if role is not None:
        img.colorspace_settings.name = colour_space(role)
    _stamp(img, {"sha256": file_sha256(path) if os.path.exists(path) else None, "container": os.path.splitext(path)[1].lstrip(".").lower(),
                 "importer": "images.load", "settings": dict(kw), "role": role})
    return img


@contextmanager
def load_library(path, **kw):
    """Blender's ``bpy.data.libraries.load(path, **kw)`` context manager (the only call of it)."""
    before = snapshot_ids()
    try:
        with bpy.data.libraries.load(os.fspath(path), **kw) as library:
            yield library
    except BaseException:
        remove_new_ids(before)
        raise
    finally:
        _record_import(before)


def geometry_sha256(ob, space="world"):
    """sha256 over the mesh's vertex positions (float32 little-endian) and its face loops. ``space="world"`` (the default, what the
    normalizer stamps: its object matrix is then the identity, so world IS data) or ``"data"`` (the mesh's own coordinates: what a
    door recomputes, so a pure translation - a placement - leaves it equal; audit F11)."""
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float64)
    me.vertices.foreach_get("co", co)
    m = np.array(ob.matrix_world) if space == "world" else np.eye(4)
    P = (co.reshape(-1, 3) @ m[:3, :3].T + m[:3, 3]).astype("<f4")
    loops = np.empty(len(me.loops), dtype=np.int64)
    me.loops.foreach_get("vertex_index", loops)
    starts = np.empty(len(me.polygons), dtype=np.int64)
    me.polygons.foreach_get("loop_start", starts)
    h = hashlib.sha256(P.tobytes())
    h.update(loops.astype("<i4").tobytes())
    h.update(starts.astype("<i4").tobytes())
    return h.hexdigest()


def facts(ob):
    """What a door re-measures on a datablock now: {object_matrix, placement_m, scene_scale_length, bbox_min_m, bbox_max_m,
    geometry_sha256}. The bounds and the hash are the mesh's DATA (its own coordinates): the stamp describes the asset, and a pure
    translation of the object is its placement in the scene (``placement_m``), not a change of the asset (audit F11)."""
    m = np.array(ob.matrix_world)
    out = {"object_matrix": m.tolist(), "placement_m": m[:3, 3].tolist(), "scene_scale_length": float(bpy.context.scene.unit_settings.scale_length)}
    if ob.type == "MESH":
        me = ob.data
        co = np.empty(len(me.vertices) * 3, dtype=np.float64)
        me.vertices.foreach_get("co", co)
        P = co.reshape(-1, 3)
        out.update(bbox_min_m=P.min(0).tolist() if len(P) else [0, 0, 0], bbox_max_m=P.max(0).tolist() if len(P) else [0, 0, 0],
                   geometry_sha256=geometry_sha256(ob, space="data"))
    return out


def write_npz(path, V, T, canon, **arrays):
    np.savez(path, V=np.asarray(V), T=np.asarray(T), canon=np.array(json.dumps(canon, sort_keys=True)), **arrays)


def read_npz(path):
    """(V, T, canon document or None): an npz without a ``canon`` header is raw."""
    d = np.load(path, allow_pickle=False)
    canon = json.loads(str(d["canon"])) if "canon" in d.files else None
    return d["V"], d["T"], canon
