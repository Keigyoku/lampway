# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_export_ue, the write half (specs/canon/rig_tools/rig_export_ue.md; canon 21): write the FBX with a recipe that states every exporter
argument, read the written file back, and publish it only when every bone matches the reference (the bind_mismatch bars: 0.01 cm, 0.01 deg,
1e-4 scale). Re-implemented; MB's exporter (no axis or scale arguments, mesh_smooth_type EDGE, batch export deleting the scene) is not ported.

* The read-back reads RAW frames: the file is imported through canon_io with automatic bone orientation off and no axis correction (primary Y,
  secondary X), which is how an engine reads the bones. Measured 2026-10-06: a canon-17 'blender' rig reads back as UE axes with primary X /
  secondary -Y, a 'ue_axes' rig with primary Y / secondary X; the other pair reads 90 deg off while every head matches (G21.2).
* Blender's importer compensates the file's UnitScaleFactor, so the read-back cannot see the x100 a metre-scaled file gives UE (G21.3): the
  factor is read from the FBX itself (Blender's own FBX parser) and gated by the recipe's expectation.
* The reference: "" = the armature itself in engine axes (a 'blender' rig's frames turned X <- Y, Y <- -X); an armature object; or an FBX
  read raw. Root and hierarchy must equal the reference's (one container top bone in the read-back is accepted and named).

A failing file is moved to export/rejected/ and the rows over tolerance are named. The armature, meshes and actions are never changed: the
one action exported is made active for the export and the previous one restored."""

import hashlib
import json
import os
import shutil
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

from . import common as C
from . import rig_tools as RT
from ..rig_tools import core as RC

RECIPES = Path(__file__).resolve().parents[1] / "rig_tools" / "recipes"
REQUIRED = ("object_types", "apply_unit_scale", "apply_scale_options", "global_scale", "axis_forward", "axis_up", "primary_bone_axis",
            "secondary_bone_axis", "use_armature_deform_only", "add_leaf_bones", "use_mesh_modifiers", "mesh_smooth_type", "use_tspace",
            "use_custom_props", "bake_anim_step", "bake_anim_simplify_factor", "bake_anim_force_startend_keying")
RAW_IMPORT = {"automatic_bone_orientation": False, "primary_bone_axis": "Y", "secondary_bone_axis": "X", "global_scale": 1.0,
              "use_custom_normals": True, "ignore_leaf_bones": False}
ENGINE_FROM_BLENDER = np.array([[0.0, -1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])   # X_e = Y_b, Y_e = -X_b, Z_e = Z_b


def _recipe(recipe, root):
    if recipe in ("", "titan_cm_native"):
        p = RECIPES / "titan_cm_native.json"
    else:
        p = Path(recipe) if os.path.isabs(recipe) else Path(root, recipe)
    if not p.is_file():
        raise C.FeatureError(f"no recipe at {p}: titan_cm_native, or a recipe JSON like {RECIPES / 'cm_native_blender_convention.json'}")
    doc = json.loads(p.read_text())
    ex = doc.get("exporter") or {}
    missing = [k for k in REQUIRED if k not in ex]
    if missing:
        raise C.FeatureError(f"the recipe {p.name} leaves {', '.join(missing)} to Blender's defaults: a recipe states every exporter argument")
    return doc, p


def unit_scale_factor(path):
    """The FBX's own GlobalSettings UnitScaleFactor (Blender's FBX parser, no import)."""
    from io_scene_fbx import parse_fbx
    root, _version = parse_fbx.parse(str(path))
    for e in root.elems:
        if e.id == b"GlobalSettings":
            for sub in e.elems:
                if sub.id == b"Properties70":
                    for p in sub.elems:
                        if p.props and p.props[0] == b"UnitScaleFactor":
                            return float(p.props[4])
    return None


def _deform_parents(ob):
    """{deform bone: nearest deform ancestor} - the hierarchy a deform-only export writes."""
    out = {}
    for b in ob.data.bones:
        if not b.use_deform:
            continue
        p = b.parent
        while p is not None and not p.use_deform:
            p = p.parent
        out[b.name] = p.name if p else None
    return out


def _table(ob, names=None, turn=None):
    out = {}
    for b in ob.data.bones:
        if names is not None and b.name not in names:
            continue
        M = ob.matrix_world @ b.matrix_local
        loc, q, s = M.decompose()
        R = np.array([[c for c in row] for row in q.to_matrix()], float)
        if turn is not None:
            R = R @ turn
        qq = Matrix([list(r) for r in R]).to_quaternion()
        out[b.name] = {"translation": [x * 100.0 for x in loc], "rotation": [qq.x, qq.y, qq.z, qq.w], "scale": list(s)}
    return out


def _convention(ob):
    return RC.classify_convention(list(RT.convention_angles(RT.read(ob)).values()))


def _import(path):
    from .. import canon_io
    rec = canon_io.import_raw(str(path), **RAW_IMPORT)
    return rec


def _discard(rec):
    for n in rec["objects"]:
        o = bpy.data.objects.get(n)
        if o is not None:
            bpy.data.objects.remove(o)
    for kind in ("armatures", "meshes", "actions", "materials", "images"):
        for n in rec.get(kind, []):
            d = getattr(bpy.data, kind).get(n)
            if d is not None and d.users == 0:
                getattr(bpy.data, kind).remove(d)
    bpy.context.view_layer.update()


def _corner_normals(ob):
    me = ob.data
    N = np.array([c.vector for c in me.corner_normals], float).reshape(-1, 3)
    W = np.array(ob.matrix_world.to_3x3().inverted().transposed())
    N = N @ W.T
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _reference(reference, ob, convention, root):
    """(table, parents, name, sha256, imported record or None)."""
    if not reference:
        turn = ENGINE_FROM_BLENDER if convention == "blender" else None
        par = _deform_parents(ob)
        t = _table(ob, set(par), turn)
        return t, par, f"{ob.name} (itself, in engine axes)", RT._fingerprint(ob, RT.read(ob)), None
    if reference.lower().endswith(".fbx"):
        p = Path(reference) if os.path.isabs(reference) else Path(root, reference)
        if not p.is_file():
            raise C.FeatureError(f"no reference FBX at {p}")
        rec = _import(p)
        arms = [bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "ARMATURE"]
        if len(arms) != 1:
            _discard(rec)
            raise C.FeatureError(f"the reference FBX holds {len(arms)} armatures: one is the reference")
        par = {b.name: b.parent.name if b.parent else None for b in arms[0].data.bones}
        return _table(arms[0]), par, p.name, rec["sha256"], rec
    ref = RT._armature(reference)
    par = {b.name: b.parent.name if b.parent else None for b in ref.data.bones}
    return _table(ref), par, ref.name, RT._fingerprint(ref, RT.read(ref)), None


def export_ue(armature, out, root, meshes=None, actions=None, reference="", recipe="titan_cm_native", readback=True):
    ob = RT._armature(armature)
    RT._inspected(ob)
    doc, recipe_path = _recipe(recipe, root)
    if not readback:
        raise C.FeatureError("readback=false is refused: no export without a read-back of every bone (canon 21 INV-21.1)")
    convention = _convention(ob)
    if convention not in ("blender", "ue_axes"):
        raise C.FeatureError(f"{ob.name}'s frames are {convention}: one convention per rig (canon 17); run lampway_rig_conform first")
    constrained = sorted(f"{pb.name} ({c.type.lower()})" for pb in ob.pose.bones for c in pb.constraints)
    if constrained:
        raise C.FeatureError(f"constraints on {', '.join(constrained)}: bake them (lampway_rig_bake) and remove them before exporting")
    leaves = sorted(b.name for b in ob.data.bones if not b.children and b.name.lower().endswith(("_end", "_leaf", "end_site")))
    if leaves:
        raise C.FeatureError(f"leaf bones {', '.join(leaves)}: an engine skeleton has none; remove them before exporting")
    if meshes is None:
        mesh_obs = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object is ob for m in o.modifiers)]
    else:
        mesh_obs = [C.need_object(n, "MESH") for n in meshes]
    acts = list(actions or [])
    if len(acts) > 1:
        raise C.FeatureError(f"{len(acts)} actions: one action per FBX (one clip per file); call once per action")
    act = None
    if acts:
        act = bpy.data.actions.get(acts[0])
        if act is None:
            raise C.FeatureError(f"no action named {acts[0]!r}")
    target = Path(out) if os.path.isabs(out) else Path(root, out)
    if target.suffix.lower() != ".fbx":
        raise C.FeatureError(f"out must be an .fbx path, not {target.name}")
    if target.exists():
        raise C.FeatureError(f"{target} exists: an export never overwrites a published file (an FBX carries its creation time); choose another out")
    ref_table, ref_parents, ref_name, ref_sha, ref_rec = _reference(reference, ob, convention, root)
    try:
        deform = _deform_parents(ob)
        bones = set(ob.data.bones.keys())
        lacking = sorted({g.name for m in mesh_obs for g in m.vertex_groups if g.name in bones and g.name not in ref_table})
        if lacking:
            raise C.FeatureError(f"vertex groups {', '.join(lacking)} name bones the reference {ref_name} lacks")
        missing, extra = sorted(set(ref_table) - set(deform)), sorted(set(deform) - set(ref_table))
        moved = sorted(b for b in deform if b in ref_parents and ref_parents[b] != deform[b])
        if missing or extra or moved:
            raise C.FeatureError(f"the deform hierarchy differs from the reference {ref_name}: missing {missing}, extra {extra}, other parent "
                                 f"{moved}; conform the rig to the reference first (lampway_rig_conform)")
    except Exception:
        if ref_rec:
            _discard(ref_rec)
        raise
    if ref_rec:
        _discard(ref_rec)
    target.parent.mkdir(parents=True, exist_ok=True)
    writing = target.with_name(target.stem + ".writing.fbx")
    ex = dict(doc["exporter"])
    ex["object_types"] = set(ex["object_types"])
    ad = ob.animation_data
    keep = ad.action if ad is not None else None
    layer = [o for o in bpy.context.view_layer.objects if o is not None]
    keep_sel = [o for o in layer if o.select_get()]
    keep_active = bpy.context.view_layer.objects.active
    try:
        if act is not None:
            ob.animation_data_create().action = act
        for o in layer:
            o.select_set(o is ob or o in mesh_obs)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.export_scene.fbx(filepath=str(writing), use_selection=True, bake_anim=act is not None, bake_anim_use_all_actions=False,
                                 bake_anim_use_nla_strips=False, **ex)
    finally:
        if act is not None:
            ob.animation_data.action = keep
        for o in layer:
            o.select_set(o in keep_sel)
        bpy.context.view_layer.objects.active = keep_active
    usf = unit_scale_factor(writing)
    rec = _import(writing)
    try:
        arms = [bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "ARMATURE"]
        if len(arms) != 1:
            raise C.FeatureError(f"the written FBX reads back {len(arms)} armatures")
        got = _table(arms[0])
        got_parents = {b.name: b.parent.name if b.parent else None for b in arms[0].data.bones}
        container = None
        extra = sorted(set(got) - set(ref_table))
        if len(extra) == 1 and got_parents[extra[0]] is None and any(got_parents.get(r) == extra[0] for r, p in ref_parents.items() if p is None):
            container = extra[0]
            got.pop(container)
        try:
            rows = RC.readback_rows(ref_table, got)
        except RC.RigRefused as exc:
            rows = None
            roster = str(exc)
        corner = []
        for m in mesh_obs:
            back = next((bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "MESH"
                         and bpy.data.objects[n].name.rsplit(".", 1)[0] == m.name), None)
            if back is None or len(back.data.loops) != len(m.data.loops):
                corner.append(None)
                continue
            a, b = _corner_normals(m), _corner_normals(back)
            corner.append(float(np.degrees(np.arccos(np.clip(np.min(np.sum(a * b, axis=1)), -1.0, 1.0)))) if len(a) else 0.0)
        anim = None
        if act is not None:
            got_acts = [n for n in rec.get("actions", [])]
            anim = {"action": act.name, "frame_range": [float(act.frame_range[0]), float(act.frame_range[1])], "read_back_actions": len(got_acts)}
    finally:
        _discard(rec)
    expect = doc.get("expect", {}).get("unit_scale_factor")
    problems = []
    if rows is None:
        problems.append(f"the read-back roster differs: {roster}")
    elif rows["over_tolerance"]:
        worst = sorted(rows["over_tolerance"], key=lambda r: -r["rotation_deg"])[:8]
        problems.append("the read-back is over the bind_mismatch bars on " + ", ".join(
            f"{r['bone']} ({r['position_cm']:.3g} cm, {r['rotation_deg']:.3g} deg, scale {r['scale']:.3g})" for r in worst))
    if expect is not None and (usf is None or abs(usf - float(expect)) > 1e-9):
        problems.append(f"the file says UnitScaleFactor {usf:g} where the recipe {doc.get('name')} expects {float(expect):g}")
    fbx_sha = hashlib.sha256(writing.read_bytes()).hexdigest()
    summary = {"recipe": {"name": doc.get("name"), "path": str(recipe_path), "exporter": doc["exporter"]}, "convention": convention,
               "unit_scale_factor": usf, "reference": ref_name, "container_top_bone": container, "animation": anim,
               "normals": {"corner_max_deg": max((c for c in corner if c is not None), default=0.0), "unmatched_meshes": corner.count(None)},
               "sha256": {"fbx": fbx_sha, "reference": ref_sha, "armature_rest": RT._fingerprint(ob, RT.read(ob))}}
    if rows is not None:
        summary["readback"] = {k: v for k, v in rows.items() if k != "rows"}
    if problems:
        rej = target.parent / "rejected" / target.name
        rej.parent.mkdir(parents=True, exist_ok=True)
        k = 1
        while rej.exists():
            k += 1
            rej = rej.with_name(f"{target.stem}.{k}.fbx")
        shutil.move(str(writing), str(rej))
        raise C.FeatureError(f"refused, the file moved to {os.path.relpath(rej, root)}: " + "; ".join(problems))
    os.replace(writing, target)
    return {**summary, "verdict": "PASS", "out": str(target), "rows": rows["rows"]}
