# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""batch_export (specs/mixar_docs/batch_export.md): audit the scene against the user's convention (names, scale, origin, materials), fix it as ONE pass (plan first: bulk renaming is hard to undo selectively),
and export each object to its own file from a temporary copy, verified by re-import. The convention is the USER's: the tool will not invent one. The project's convention (unit scale and axes) is recorded on the
first real run and a later call that differs is refused ("pick one convention and never mix"). Engine presets are defaults for the axes only, and are [UNVERIFIED] against each engine's importer: the user's convention
overrides them. Writes only under the project root. Names are undone through rename_map.json; applied transforms and origins are not (the file's undo history has them)."""

import hashlib
import json
import re
import time
from pathlib import Path

import bmesh
import bpy

from .. import canon_io
import numpy as np
from mathutils import Vector

from . import common as C

FORMATS = {"fbx": ".fbx", "glb": ".glb", "gltf": ".gltf", "obj": ".obj"}
PRESETS = {"unreal": {"forward": "-Y", "up": "Z", "unit_scale": 1.0}, "unity": {"forward": "-Z", "up": "Y", "unit_scale": 1.0}, "godot": {"forward": "-Z", "up": "Y", "unit_scale": 1.0}}
DEFAULT_APPLY = ("transforms", "merge_materials", "drop_unused_slots")
APPLIES = ("transforms", "modifiers", "merge_materials", "drop_unused_slots", "exclude_helpers")
_NUM = re.compile(r"\.\d{3,}$")
_DEFAULT_MAT = re.compile(r"^Material(\.\d+)?$")
_AXIS = {"X": "X", "-X": "NEGATIVE_X", "Y": "Y", "-Y": "NEGATIVE_Y", "Z": "Z", "-Z": "NEGATIVE_Z"}


def _targets(objects, collection):
    if collection:
        col = bpy.data.collections.get(collection)
        if col is None:
            raise C.FeatureError(f"no collection named {collection!r}; the collections are {sorted(c.name for c in bpy.data.collections)}")
        obs = list(col.all_objects)
    elif objects is not None:
        obs = [C.need_object(n, kind="") for n in objects]
    else:
        obs = list(bpy.context.scene.objects)
    meshes = [o for o in obs if o.type == "MESH"]
    if not meshes:
        raise C.FeatureError("no mesh objects to export: helpers (empties, cameras, lights) are never exported")
    return meshes


def _piece(name, conv) -> str:
    n = _NUM.sub("", name)
    pre = conv.get("prefix", "")
    if pre and n.startswith(pre):
        n = n[len(pre):]
    return re.sub(r"[^A-Za-z0-9_]+", "_", n).strip("_") or "Piece"


def _names(obs, conv) -> dict:
    pattern = conv.get("pattern") or "{prefix}{set}_{piece}_{nn}"
    if "{set}" in pattern and not conv.get("set"):
        raise C.FeatureError("the convention's pattern uses {set} but no set is given: pass convention.set")
    groups, out = {}, {}
    for o in obs:
        groups.setdefault(_piece(o.name, conv), []).append(o)
    for piece, members in groups.items():
        for i, o in enumerate(members, 1):
            out[o.name] = pattern.format(prefix=conv.get("prefix", ""), set=conv.get("set", ""), piece=piece, nn=f"{i:02d}", name=o.name)
    dup = sorted({n for n in out.values() if list(out.values()).count(n) > 1})
    if dup:
        raise C.FeatureError(f"name collision: {dup} would be the name of more than one object: add {{nn}} to the pattern or rename them")
    taken = {o.name for o in bpy.data.objects} - set(out)
    clash = sorted(n for n in out.values() if n in taken)
    if clash:
        raise C.FeatureError(f"name collision: {clash} already name other objects in the file")
    return out


def _bbox(ob):
    pts = np.array([tuple(ob.matrix_world @ v.co) for v in ob.data.vertices]) if len(ob.data.vertices) else np.zeros((1, 3))
    return pts.min(axis=0), pts.max(axis=0)


def _violations(ob, new_name, conv, apply) -> list:
    v = []
    if ob.name != new_name:
        v.append("name")
    if "transforms" in apply and (any(abs(s - 1) > 1e-9 for s in ob.scale) or any(abs(r) > 1e-9 for r in ob.rotation_euler)):
        v.append("scale")
    if conv.get("origin", "base") == "base":
        lo, hi = _bbox(ob)
        base = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        if float(np.linalg.norm(np.array(ob.matrix_world.translation) - base)) > 1e-4 * max(1e-9, float(np.linalg.norm(hi - lo))):
            v.append("origin")
    if any(m and _DEFAULT_MAT.match(m.name) for m in ob.data.materials):
        v.append("materials")
    used = {p.material_index for p in ob.data.polygons}
    if "drop_unused_slots" in apply and any(i not in used for i in range(len(ob.data.materials))):
        v.append("unused_slots")
    if "modifiers" in apply and ob.modifiers:
        v.append("modifiers")
    return v


def _apply_transforms(ob):
    m = ob.matrix_basis.copy()
    m.translation = (0.0, 0.0, 0.0)
    ob.data.transform(m)
    if m.determinant() < 0:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(ob.data)
        bm.free()
    ob.rotation_euler, ob.scale = (0.0, 0.0, 0.0), (1.0, 1.0, 1.0)


def _set_origin_base(ob):
    lo, hi = _bbox(ob)
    base = Vector(((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]))
    delta = base - ob.matrix_world.translation
    ob.data.transform(__import__("mathutils").Matrix.Translation(-delta))
    ob.location = ob.location + delta


def _apply_modifiers(ob):
    dg = bpy.context.evaluated_depsgraph_get()
    ev = ob.evaluated_get(dg)
    new = bpy.data.meshes.new_from_object(ev)
    old = ob.data
    ob.modifiers.clear()
    ob.data = new
    new.name = old.name
    if old.users == 0:
        bpy.data.meshes.remove(old)


def _drop_unused_slots(ob):
    me = ob.data
    used = sorted({p.material_index for p in me.polygons})
    drop = [i for i in range(len(me.materials)) if i not in used]
    if drop:
        remap = {old: new for new, old in enumerate(i for i in range(len(me.materials)) if i not in drop)}
        for p in me.polygons:
            p.material_index = remap[p.material_index]
        for i in reversed(drop):
            me.materials.pop(index=i)


def _material_key(m):
    """Duplicates by value: the same base name (without .NNN) and the same principled inputs."""
    vals = []
    if m and m.use_nodes:
        for n in m.node_tree.nodes:
            if n.type == "BSDF_PRINCIPLED":
                for k in ("Base Color", "Metallic", "Roughness"):
                    s = n.inputs.get(k)
                    if s is not None and not s.is_linked:
                        d = s.default_value
                        vals.append(tuple(round(x, 5) for x in d) if hasattr(d, "__len__") else round(float(d), 5))
    return (_NUM.sub("", m.name) if m else "", tuple(vals))


def _merge_materials(obs):
    seen = {}
    merged = 0
    for ob in obs:
        for i, m in enumerate(ob.data.materials):
            if m is None:
                continue
            k = _material_key(m)
            if k in seen and seen[k] is not m:
                ob.data.materials[i] = seen[k]
                merged += 1
            else:
                seen.setdefault(k, m)
    return merged


def _rename_default_materials(ob, new_name):
    for m in ob.data.materials:
        if m and _DEFAULT_MAT.match(m.name) and m.users == 1:
            m.name = f"M_{new_name}"


def _axes(conv, preset):
    p = PRESETS[preset]
    return conv.get("forward") or p["forward"], conv.get("up") or p["up"], float(conv.get("unit_scale") if conv.get("unit_scale") is not None else p["unit_scale"])


def _export_one(ob, path, fmt, fwd, up, unit):
    for o in list(bpy.context.selected_objects):
        o.select_set(False)
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    if fmt == "fbx":
        bpy.ops.export_scene.fbx(filepath=str(path), use_selection=True, object_types={"MESH"}, axis_forward=fwd, axis_up=up, global_scale=unit, apply_unit_scale=True,
                                 apply_scale_options="FBX_SCALE_NONE", add_leaf_bones=False, mesh_smooth_type="FACE", path_mode="COPY", embed_textures=False)
    elif fmt in ("glb", "gltf"):
        bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB" if fmt == "glb" else "GLTF_SEPARATE", use_selection=True)
    else:
        bpy.ops.wm.obj_export(filepath=str(path), export_selected_objects=True, forward_axis=_AXIS[fwd], up_axis=_AXIS[up], global_scale=unit)


def _import(path, fmt, fwd, up, unit):
    before = set(bpy.data.objects)
    if fmt == "fbx":
        canon_io.import_raw(str(path), axis_forward=fwd, axis_up=up, global_scale=1.0 / unit)
    elif fmt in ("glb", "gltf"):
        canon_io.import_raw(str(path))
    else:
        canon_io.import_raw(str(path), forward_axis=_AXIS[fwd], up_axis=_AXIS[up], global_scale=1.0 / unit)
    return [o for o in bpy.data.objects if o not in before]


def _dims(obs):
    pts = [tuple(o.matrix_world @ v.co) for o in obs if o.type == "MESH" for v in o.data.vertices]
    a = np.array(pts)
    return sorted(float(x) for x in (a.max(axis=0) - a.min(axis=0)))


def _verify(copy_ob, path, fmt, fwd, up, unit):
    bpy.context.view_layer.update()
    want = _dims([copy_ob])
    before = canon_io.snapshot_ids()
    try:
        new = _import(path, fmt, fwd, up, unit)
        bpy.context.view_layer.update()
        got = _dims(new)
        err = max(abs(a - b) for a, b in zip(want, got))
    finally:
        canon_io.remove_new_ids(before)
    return err


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def undo(map_path):
    m = json.loads(Path(map_path).read_text())
    restored = 0
    for old, new in m["renames"].items():
        ob = bpy.data.objects.get(new)
        if ob is None:
            continue
        ob.name = old
        restored += 1
    return {"ok": True, "restored": restored}


def batch_export(root, objects=None, collection=None, convention=None, format="glb", preset="unreal", apply=None, out_dir="export", per="object", textures=None, plan_only=True, verify=True, undo_map=None, resolve=None):  # noqa: A002
    if undo_map:
        return undo(undo_map)
    if not convention:
        raise C.FeatureError("I cannot invent your project's naming, origin, unit and axis convention: pass convention (prefix, set, pattern, origin, unit_scale, forward, up)")
    if preset not in PRESETS and not str(preset).startswith("custom:"):
        raise C.FeatureError(f"unknown preset {preset!r}: the presets are {sorted(PRESETS)} (or custom:<name>)")
    if str(preset).startswith("custom:"):
        raise C.FeatureError(f"no saved custom preset {preset!r}: custom presets are saved by the user in the Client; none exist yet")
    if format == "usd":
        raise C.FeatureError("usd export is not built: use fbx, glb, gltf or obj")
    if format not in FORMATS:
        raise C.FeatureError(f"unknown format {format!r}: fbx, glb, gltf or obj")
    apply = list(DEFAULT_APPLY if apply is None else apply)
    bad = [a for a in apply if a not in APPLIES]
    if bad:
        raise C.FeatureError(f"unknown apply {bad}: {list(APPLIES)}")
    fwd, up, unit = _axes(convention, preset)
    if format in ("glb", "gltf") and abs(unit - 1.0) > 1e-12:
        raise C.FeatureError("glTF is metres by definition: unit_scale must be 1.0 (use fbx or obj for another unit)")
    out = Path(resolve(out_dir)) if resolve else Path(out_dir)
    obs = _targets(objects, collection)
    editing = [o.name for o in obs if o.mode == "EDIT"]
    if editing:
        raise C.FeatureError(f"leave Edit Mode first: {editing}")
    names = _names(obs, convention)
    plan = [{"object": o.name, "new_name": names[o.name], "fixes": _violations(o, names[o.name], convention, apply)} for o in obs]
    res = {"ok": True, "plan_only": bool(plan_only), "plan": plan, "violations": sum(1 for p in plan if p["fixes"]), "exported": [], "convention": {"forward": fwd, "up": up, "unit_scale": unit}}
    if plan_only:
        return res
    rec_path = Path(root) / "export_convention.json"
    rec = {"forward": fwd, "up": up, "unit_scale": unit}
    if rec_path.exists():
        old = json.loads(rec_path.read_text())
        if old != rec:
            raise C.FeatureError(f"the requested convention {rec} differs from the project's recorded convention {old}: pick one convention and never mix; delete export_convention.json only if you mean to change it for the whole project")
    else:
        rec_path.write_text(json.dumps(rec, indent=1))
    out.mkdir(parents=True, exist_ok=True)
    renames = {}
    for o in obs:
        renames[o.name] = names[o.name]
    (out / "rename_map.json").write_text(json.dumps({"renames": renames, "at": time.time()}, indent=1))
    for o in obs:
        o.name = names[o.name]
    if "modifiers" in apply:
        for o in obs:
            if o.modifiers:
                _apply_modifiers(o)
    if "transforms" in apply:
        for o in obs:
            if o.data.users > 1:
                o.data = o.data.copy()
            _apply_transforms(o)
    if convention.get("origin", "base") == "base":
        for o in obs:
            _set_origin_base(o)
    if "merge_materials" in apply:
        res["materials_merged"] = _merge_materials(obs)
    if "drop_unused_slots" in apply:
        for o in obs:
            _drop_unused_slots(o)
    for o in obs:
        _rename_default_materials(o, o.name)
    bpy.context.view_layer.update()
    exported = []
    for o in obs:
        copy = o.copy()
        copy.data = o.data.copy()
        for c in o.users_collection or [bpy.context.scene.collection]:
            c.objects.link(copy)
        try:
            f = out / f"{o.name}{FORMATS[format]}"
            _export_one(copy, f, format, fwd, up, unit)
            err = _verify(copy, f, format, fwd, up, unit) if verify else None
        finally:
            d = copy.data
            bpy.data.objects.remove(copy)
            if d.users == 0:
                bpy.data.meshes.remove(d)
        exported.append({"object": o.name, "file": str(f), "sha256": _sha(f), "verified": bool(verify and err is not None and err < 1e-4), "bbox_error": err, "units": "m" if abs(unit - 1.0) < 1e-12 else f"x{unit:g}", "axes": f"forward {fwd}, up {up}"})
    res["exported"] = exported
    manifest = out / "manifest.json"
    manifest.write_text(json.dumps({"format": format, "preset": preset, "convention": convention, "applied": apply, "objects": exported, "rename_map": "rename_map.json"}, indent=1))
    res["manifest"] = str(manifest)
    res["rename_map"] = str(out / "rename_map.json")
    return res
