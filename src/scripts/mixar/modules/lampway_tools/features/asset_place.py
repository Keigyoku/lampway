# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_place (specs/asset_library/asset_place.md): bring a library asset into the open Blender file in the way its kind needs, reversibly (one undo step), stamping where it came from
(``lw_asset_id`` / ``lw_asset_version`` / ``lw_asset_sha256``). The asset record is what the server's ``AssetLibrary.get`` returns (a texture set or PBR set also carries ``members``, the
map records it groups); this module never opens the user's file for write.

A placement that fails removes whatever datablocks it created: nothing is left half-placed. The shading kinds live in ``asset_place_shading``, the media and animation kinds in
``asset_place_media``; this module owns the record, the transaction, the drop point and the meshes."""

import os

import bpy

from .. import canon_io
from . import common as C

MODES = ("auto", "append", "link", "import", "assign_material", "assign_maps", "add_node_group", "set_world", "add_clip", "apply_animation", "attach_rig", "reference_image")
MAX_TRIS = 5_000_000
IMPORT_EXTS = (".glb", ".gltf", ".fbx", ".obj", ".usd", ".usda", ".usdc", ".usdz")   # read through canon_io (flavour native: FBX by wm.fbx_import)
# the datablock collections a placement can create; a failure removes what is new in them (objects first, so their data is free to go)
TRACKED = ("objects", "meshes", "materials", "images", "collections", "cameras", "lights", "armatures", "actions", "node_groups", "worlds", "movieclips", "curves", "textures",
           "libraries")
NOT_PLACEABLE = {"uv_layout": "a UV layout is not placeable: use lampway_vault_render for an overlay on its mesh, or uv_unwrap to make a new layout",
                 "prompt": "a prompt is not placeable: use it in a generation tool", "receipt": "a receipt is not placeable: read it with lampway_vault_get",
                 "collection": "a board or smart collection is not placeable: place its members one by one"}


class PlaceError(C.FeatureError):
    pass


# ---- the record

def file_of(asset: dict, roles: tuple) -> tuple:
    """(path, sha256, storage) of the first file of the first role present whose copy is on disk."""
    files = [f for r in roles for f in asset.get("files") or [] if f.get("role") == r]
    if not files:
        raise PlaceError(f"{asset.get('name')!r} has no {'/'.join(roles)} file in the library")
    for f in files:
        for loc in f.get("locations") or []:
            if not loc.get("missing") and os.path.isfile(loc.get("path") or ""):
                return loc["path"], f.get("sha256"), loc.get("storage")
    raise PlaceError("the file moved: re-run lampway_vault {action: verify}")


def stamp(idb, asset: dict, sha: str) -> None:
    idb["lw_asset_id"] = str(asset.get("id"))
    idb["lw_asset_version"] = str(asset.get("version"))
    idb["lw_asset_sha256"] = str(sha)


def entry(kind: str, idb, **extra) -> dict:
    return {"kind": kind, "datablock": getattr(idb, "name", None), "name": getattr(idb, "name", None), **extra}


# ---- the transaction

def _snapshot() -> dict:
    return {k: {i.as_pointer() for i in getattr(bpy.data, k)} for k in TRACKED}


def new_since(before: dict) -> dict:
    return {k: [i for i in getattr(bpy.data, k) if i.as_pointer() not in before[k]] for k in TRACKED}


def _discard(before: dict) -> None:
    new = new_since(before)
    for k in TRACKED:
        for i in new[k]:
            try:
                getattr(bpy.data, k).remove(i)
            except (RuntimeError, ReferenceError):
                pass


# ---- the scene

def scene():
    sc = bpy.context.scene
    if sc is None:
        raise PlaceError("no open scene")
    return sc


def where(target) -> str:
    return str((target or {}).get("where") or "cursor")


def target_object(target, types=None):
    """The object a ``object:<name>`` target names (None for any other target)."""
    w = where(target)
    if not w.startswith("object:"):
        return None
    name = w.split(":", 1)[1]
    ob = bpy.data.objects.get(name)
    if ob is None:
        raise PlaceError(f"no object named {name!r}: the target is object:<name> of an object in this scene")
    if types and ob.type not in types:
        raise PlaceError(f"{name!r} is a {ob.type.lower()}: this target needs a {' or '.join(t.lower() for t in types)}")
    return ob


def drop_point(sc, target) -> tuple:
    w = where(target)
    if w == "origin":
        return (0.0, 0.0, 0.0)
    ob = target_object(target)
    if ob is not None:
        return tuple(ob.matrix_world.translation)
    if w == "cursor":
        return tuple(sc.cursor.location)
    raise PlaceError(f"target {w!r} does not apply here: use cursor, origin or object:<name>")


def _spawn():
    from mixar.modules.agent_bubble.core import spawn_asset as SA
    return SA


def collection(sc, opts: dict):
    name = opts.get("collection")
    if name:
        coll = bpy.data.collections.get(name) or bpy.data.collections.new(name)
        if coll.name not in {c.name for c in sc.collection.children_recursive}:
            sc.collection.children.link(coll)
        return coll
    return _spawn()._visible_collection(sc, bpy.context.view_layer)


def link_objects(coll, objs) -> None:
    for ob in objs:
        for c in list(ob.users_collection):
            if c is not coll:
                c.objects.unlink(ob)
        if ob.name not in coll.objects:
            coll.objects.link(ob)


def place_objects(sc, members: list, asset: dict, sha: str, opts: dict, target, loaded_bytes: int, rename=True) -> list:
    """Scale to the library's unit, drop the members' footprint centre on the drop point (their lowest point on it), stamp them."""
    SA = _spawn()
    bpy.context.view_layer.update()
    roots = SA._roots(members)
    scale = (asset.get("stats") or {}).get("unit_scale")
    if opts.get("scale_to_unit", True) and scale and abs(float(scale) - 1.0) > 1e-9:
        for r in roots:
            r.scale = tuple(v * float(scale) for v in r.scale)
        bpy.context.view_layer.update()
    point = drop_point(sc, target)
    pts = [p for ob in members for p in SA._world_points(ob, 0)]
    if pts:
        off = ((min(p[0] for p in pts) + max(p[0] for p in pts)) / 2.0, (min(p[1] for p in pts) + max(p[1] for p in pts)) / 2.0, min(p[2] for p in pts))
        for r in roots:
            r.location = (r.location[0] + point[0] - off[0], r.location[1] + point[1] - off[1], r.location[2] + point[2] - off[2])
    if rename and len(roots) == 1:
        roots[0].name = str(asset.get("name"))
    for ob in members:
        stamp(ob, asset, sha)
    bpy.context.view_layer.update()
    return [entry("object", r, datablock=getattr(r.data, "name", None), object=r.name, collection=r.users_collection[0].name if r.users_collection else None,
                  location=[round(v, 6) for v in r.location], bytes_loaded=loaded_bytes) for r in roots]


# ---- meshes (and the objects of a rig)

def _import(asset, path, sha, opts, target) -> list:
    sc = scene()
    ext = os.path.splitext(path)[1].lower()
    if ext not in IMPORT_EXTS:
        raise PlaceError(f"no importer for {ext!r}: the importers are {sorted(IMPORT_EXTS)}")
    before = _snapshot()
    try:
        res = canon_io.import_raw(path, flavour="native")["result"]
        if "FINISHED" not in res:
            raise RuntimeError(f"the importer returned {sorted(res)}")
        objs = new_since(before)["objects"]
        if not objs:
            raise RuntimeError("the file held no objects")
    except Exception as exc:  # noqa: BLE001 - whatever the importer raised: nothing of it stays
        _discard(before)
        raise PlaceError(f"import failed: {exc}; the file is kept as is; try the CAS copy") from None
    link_objects(collection(sc, opts), objs)
    return place_objects(sc, objs, asset, sha, opts, target, os.path.getsize(path))


def _pick(names: list, wanted: str, what: str, path: str) -> str:
    if wanted in names:
        return wanted
    if len(names) == 1:
        return names[0]
    raise PlaceError(f"{os.path.basename(path)} holds no {what} named {wanted!r}; it holds {sorted(names)[:20]}")


def load_blend(path: str, slot: str, wanted: str, what: str, link=False):
    """One datablock of ``bpy.data.<slot>`` from a .blend: the one named like the asset, else the file's only one."""
    with canon_io.load_library(path, link=link) as (src, dst):
        name = _pick(list(getattr(src, slot)), wanted, what, path)
        setattr(dst, slot, [name])
    got = [i for i in getattr(dst, slot) if i is not None]
    if not got:
        raise PlaceError(f"{name!r} could not be read from {os.path.basename(path)}")
    return got[0]


def _blend_objects(asset, path, sha, opts, target, link: bool) -> list:
    sc = scene()
    wanted = str(asset.get("name"))
    with canon_io.load_library(path, link=link) as (src, dst):
        if wanted in src.collections and wanted not in src.objects:
            slot, name = "collections", wanted
        else:
            slot, name = "objects", _pick(list(src.objects), wanted, "object or collection", path)
        setattr(dst, slot, [name])
    got = [i for i in getattr(dst, slot) if i is not None]
    if not got:
        raise PlaceError(f"{name!r} could not be read from {os.path.basename(path)}")
    coll = collection(sc, opts)
    size = os.path.getsize(path)
    if link:
        holder = bpy.data.collections.new(f"{wanted} (linked)")
        if slot == "collections":
            holder.children.link(got[0])
        else:
            holder.objects.link(got[0])
        inst = bpy.data.objects.new(wanted, None)
        inst.instance_type, inst.instance_collection = "COLLECTION", holder
        coll.objects.link(inst)
        inst.location = drop_point(sc, target)
        stamp(inst, asset, sha)
        return [entry("object", inst, object=inst.name, collection=coll.name, location=list(inst.location), bytes_loaded=size, linked=True)]
    if slot == "collections":
        coll.children.link(got[0])
        members = list(got[0].all_objects)
    else:
        link_objects(coll, got)
        members = got
    return place_objects(sc, members, asset, sha, opts, target, size, rename=slot == "objects")


def _mesh(asset, mode, opts, target):
    path, sha, storage = file_of(asset, ("main",))
    is_blend = path.lower().endswith(".blend")
    used = mode if mode != "auto" else ("append" if is_blend else "import")
    tris = (asset.get("stats") or {}).get("tris")
    if tris and int(tris) > MAX_TRIS and not opts.get("force"):
        raise PlaceError(f"{int(tris)} triangles: place a LOD (lod:2) or confirm force:true")
    if used == "link" and storage == "cas":
        raise PlaceError("managed files are immutable: use append or import")
    if used in ("append", "link"):
        if not is_blend:
            raise PlaceError(f"{used} reads a .blend; {os.path.basename(path)} is not one: use import")
        return used, _blend_objects(asset, path, sha, opts, target, used == "link")
    if used == "import":
        return used, _import(asset, path, sha, opts, target)
    raise PlaceError(f"mode {used!r} does not place a mesh: use auto, import, append or link")


def place_rig_objects(asset, opts, target) -> tuple:
    """The objects of a rig asset (a .blend's armature, or an imported file's), placed like a mesh; (objects entries, path, sha)."""
    path, sha, _ = file_of(asset, ("main",))
    if path.lower().endswith(".blend"):
        return _blend_objects(asset, path, sha, opts, {"where": "origin"} if target_object(target) else target, False), path, sha
    return _import(asset, path, sha, opts, {"where": "origin"} if target_object(target) else target), path, sha


# ---- the verb

def _auto(kind: str, asset: dict, target) -> str:
    if kind == "material":
        return "assign_maps" if asset.get("subtype") == "pbr_set" or asset.get("members") else "assign_material"
    if kind == "map":
        return "assign_maps" if where(target).startswith("slot:") else "reference_image"
    return {"image": "reference_image", "texture_set": "assign_maps", "hdri": "set_world", "video": "add_clip", "animation": "apply_animation", "rig": "attach_rig"}[kind]


def asset_place(asset: dict, mode: str = "auto", target: dict = None, options: dict = None) -> dict:
    from . import asset_place_media as M
    from . import asset_place_shading as SH
    if mode not in MODES:
        raise PlaceError(f"mode is one of {list(MODES)}")
    opts = dict(options or {})
    kind = asset.get("kind")
    if kind in NOT_PLACEABLE:
        raise PlaceError(NOT_PLACEABLE[kind])
    scene()
    verbs = {"assign_material": SH.assign_material, "assign_maps": SH.assign_maps, "add_node_group": SH.add_node_group, "set_world": SH.set_world,
             "reference_image": M.reference_image, "add_clip": M.add_clip, "apply_animation": M.apply_animation, "attach_rig": M.attach_rig}
    before = _snapshot()
    try:
        if kind == "mesh":
            used, placed = _mesh(asset, mode, opts, target or {})
        else:
            used = _auto(kind, asset, target) if mode == "auto" else mode
            if used not in verbs:
                raise PlaceError(f"mode {used!r} does not place a {kind}: use auto")
            placed = verbs[used](asset, opts, target or {})
    except Exception:
        _discard(before)
        raise
    if opts.get("undo_step", True):
        bpy.ops.ed.undo_push(message=f"Place {asset.get('name')}")
    out = {"placed": placed, "mode_used": used, "undo": bool(opts.get("undo_step", True)), "relations_recorded": []}
    if asset.get("attribution"):
        out["attribution"] = asset["attribution"]
    return out
