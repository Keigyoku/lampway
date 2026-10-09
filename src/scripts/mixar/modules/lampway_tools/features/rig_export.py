# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_export_ue, the write half (specs/canon/rig_tools/rig_export_ue.md; canon 21): write the FBX with a recipe that states every exporter
argument, read the written file back, and publish it only when every bone matches the reference (the bind_mismatch bars: 0.01 cm, 0.01 deg,
1e-4 scale). Re-implemented; MB's exporter (no axis or scale arguments, mesh_smooth_type EDGE, batch export deleting the scene) is not ported.

* The Blender read-back reads RAW frames: the file is imported through canon_io with automatic bone orientation off and no axis correction (primary Y,
  secondary X). This is not physical engine parity. Measured 2026-10-06: a canon-17 'blender' rig reads back as UE axes with primary X /
  secondary -Y, a 'ue_axes' rig with primary Y / secondary X; the other pair reads 90 deg off while every head matches (G21.2).
* Raw Null ancestry, direct bone scales and UnitScaleFactor are checked before decoding the pinned Blender importer unit representation.
  Metre-coordinate legacy recipes can hide an inherited scale100 Null behind Blender readback; centimetre copies avoid that carrier.
* The reference: "" = the armature itself in engine axes (a 'blender' rig's frames turned X <- Y, Y <- -X); an armature object; or an FBX
  read raw. Root and hierarchy must equal the reference's (one container top bone in the read-back is accepted and named).

A failing file is moved to export/rejected/ and the rows over tolerance are named. The armature, meshes and actions are never changed: the
one action exported is made active for the export and the previous one restored."""

import hashlib
from contextlib import contextmanager, nullcontext
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
ENGINE_FROM_BLENDER = RC.ENGINE_FROM_BLENDER   # X_e = Y_b, Y_e = -X_b, Z_e = Z_b


@contextmanager
def _export_visibility(objects):
    """Admit only the requested export objects to FBX's selected-object query.

    Copies inherit viewport/select restrictions from hidden source rigs. Blender
    excludes those from context.selected_objects even after select_set(True).
    Restore flags on exit as metre recipes may be exporting the source itself.
    """
    states = [(ob, ob.hide_viewport, ob.hide_render, ob.hide_select, ob.hide_get()) for ob in objects]
    try:
        for ob, *_flags in states:
            ob.hide_viewport = ob.hide_render = ob.hide_select = False
            ob.hide_set(False)
        bpy.context.view_layer.update()
        yield
    finally:
        for ob, viewport, render, select, layer in states:
            ob.hide_viewport, ob.hide_render, ob.hide_select = viewport, render, select
            ob.hide_set(layer)
        bpy.context.view_layer.update()


def _recipe(recipe, root, convention=None):
    if recipe in ("", "auto", None):
        names = {"blender": "cm_native_blender_convention", "ue_axes": "cm_native_ue_axes"}
        if convention not in names:
            raise C.FeatureError("auto recipe needs a measured normalized blender or ue_axes convention; conform first")
        p = RECIPES / (names[convention] + ".json")
    elif recipe in ("titan_cm_native", "cm_native_blender_convention", "cm_native_ue_axes"):
        p = RECIPES / (recipe + ".json")
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


def _authored_table(path, exporter):
    """Read declared pinned-writer node/pose/cluster binds, without inferred tails."""
    from io_scene_fbx import export_fbx_bin, parse_fbx
    from ..rig_tools import fbx_bind as FB
    writer_sha = hashlib.sha256(Path(export_fbx_bin.__file__).read_bytes()).hexdigest()
    if writer_sha != FB.WRITER_SHA256:
        raise C.FeatureError("authored read-back requires the exact pinned Blender FBX writer")
    try:
        raw, _version = parse_fbx.parse(str(path))
        record = FB.authored_bind(raw, exporter)
        table = {}
        for name, matrix in record["matrices"].items():
            scale, frame = FB._rigid(matrix)
            table[name] = {"translation": list(matrix[:3, 3]),
                           "rotation": list(FB._quaternion(frame)), "scale": list(scale)}
        return table, record["parents"], record["diagnostics"]
    except FB.BindRefused as exc:
        raise C.FeatureError("authored read-back refused: " + str(exc)) from None
    except (ValueError, TypeError, KeyError, IndexError, OverflowError):
        raise C.FeatureError("authored read-back refused: malformed pinned-writer FBX layout") from None


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


def _table(ob, names=None, turn=None, representation=None):
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
        to_metres = representation["translation_to_metres"] if representation else 1.0
        scale_divisor = representation["scale_divisor"] if representation else 1.0
        out[b.name] = {"translation": [x * to_metres * 100.0 for x in loc], "rotation": [qq.x, qq.y, qq.z, qq.w],
                       "scale": [x / scale_divisor for x in s]}
    return out


def _convention(ob):
    rig = RT.read(ob)
    return RT.reference_convention(ob, rig) or RC.classify_convention(list(RT.convention_angles(rig).values()))


def _import(path):
    from .. import canon_io
    before = canon_io.snapshot_ids()
    rec = canon_io.import_raw(str(path), **RAW_IMPORT)
    rec["_ids_before"] = before
    return rec


def _discard(rec):
    from .. import canon_io
    canon_io.remove_new_ids(rec["_ids_before"])
    bpy.context.view_layer.update()


def _corner_normals(ob):
    me = ob.data
    N = np.array([c.vector for c in me.corner_normals], float).reshape(-1, 3)
    W = np.array(ob.matrix_world.to_3x3().inverted().transposed())
    N = N @ W.T
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def _reference(reference, ob, convention, root, exporter=None):
    """(table, parents, name, sha256, imported record or None)."""
    if not reference:
        if RT.reference_convention(ob):
            receipt = json.loads(ob["lw_native_reference_bind"])
            table = {}
            for n, bind in receipt["binds"].items():
                q = Matrix(bind["frame_engine"]).to_quaternion()
                table[n] = {"translation": [x * 100 for x in bind["head_m"]],
                            "rotation": [q.x, q.y, q.z, q.w], "scale": [1., 1., 1.]}
            return table, _deform_parents(ob), "independent native reference bind", receipt["reference_sha256"], None
        turn = ENGINE_FROM_BLENDER if convention == "blender" else None
        par = _deform_parents(ob)
        t = _table(ob, set(par), turn)
        return t, par, f"{ob.name} (itself, in engine axes)", RT._fingerprint(ob, RT.read(ob)), None
    if reference.lower().endswith(".fbx"):
        p = Path(reference) if os.path.isabs(reference) else Path(root, reference)
        if not p.is_file():
            raise C.FeatureError(f"no reference FBX at {p}")
        table, parents, _proof = _authored_table(p, exporter or {"axis_forward": "-Z", "axis_up": "Y"})
        return table, parents, p.name, hashlib.sha256(p.read_bytes()).hexdigest(), None
    ref = RT._armature(reference)
    par = {b.name: b.parent.name if b.parent else None for b in ref.data.bones}
    return _table(ref), par, ref.name, RT._fingerprint(ref, RT.read(ref)), None


def export_ue(armature, out, root, meshes=None, actions=None, reference="", recipe="auto", readback=True):
    ob = RT._armature(armature)
    from .normalize_rigged import require_complete_native
    require_complete_native(ob)
    RT._inspected(ob)
    if not readback:
        raise C.FeatureError("readback=false is refused: no export without a read-back of every bone (canon 21 INV-21.1)")
    convention = _convention(ob)
    if convention not in ("blender", "ue_axes"):
        raise C.FeatureError(f"{ob.name}'s frames are {convention}: one convention per rig (canon 17); run lampway_rig_conform first")
    doc, recipe_path = _recipe(recipe, root, convention)
    coordinates = doc.get("export_coordinates", "m")
    if coordinates not in ("m", "cm"):
        raise C.FeatureError("export_coordinates must explicitly be m or cm")
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
    ref_table, ref_parents, ref_name, ref_sha, ref_rec = _reference(reference, ob, convention, root, doc["exporter"])
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
    from . import rig_export_space as ES
    carrier = ES.centimetre_copies(ob, mesh_obs, act, ex,
                                  container_name=doc.get("ue_armature_container")) if coordinates == "cm" else nullcontext(
        {"armature": ob, "meshes": mesh_obs, "action": act, "exporter": ex, "receipt": None})
    space_receipt, effective_exporter, export_mesh_names = None, None, {}
    try:
        with carrier as prepared:
            export_arm, export_meshes = prepared["armature"], prepared["meshes"]
            space_receipt = prepared["receipt"]
            effective_exporter = {**prepared["exporter"], "object_types": sorted(prepared["exporter"]["object_types"])}
            export_mesh_names = {source.name: copied.name for source, copied in zip(mesh_obs, export_meshes)}
            if act is not None:
                export_arm.animation_data_create().action = prepared["action"]
            with _export_visibility([export_arm, *export_meshes]):
                for o in bpy.context.view_layer.objects:
                    o.select_set(o is export_arm or o in export_meshes)
                bpy.context.view_layer.objects.active = export_arm
                bpy.ops.export_scene.fbx(filepath=str(writing), use_selection=True, bake_anim=act is not None, bake_anim_use_all_actions=False,
                                         bake_anim_use_nla_strips=False, **prepared["exporter"])
    finally:
        if act is not None:
            ob.animation_data.action = keep
        for o in layer:
            o.select_set(o in keep_sel)
        bpy.context.view_layer.objects.active = keep_active
    usf = unit_scale_factor(writing)
    from .export_checks import fbx_container_scale_failures, fbx_bone_scale
    container_scale_failures = fbx_container_scale_failures(writing)
    authored_bone_scale_failures = []
    if coordinates == "cm":
        authored_bone_scale_failures = sorted(name for name, scale in fbx_bone_scale(writing).items()
                                            if any(abs(v - 1.0) > 1e-4 for v in scale))
    rec = _import(writing)
    readback_units = None
    authored_proof, authored_error, hierarchy_error = None, None, None
    display_rows, display_roster_error = None, None
    try:
        arms = [bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "ARMATURE"]
        if len(arms) != 1:
            raise C.FeatureError(f"the written FBX reads back {len(arms)} armatures")
        if coordinates == "cm" and usf == 1.0 and not container_scale_failures and not authored_bone_scale_failures:
            # Only an independently admitted identity-scale file can undergo
            # importer representation normalization; never hide a scaled Null.
            readback_units = ES.readback_representation(arms[0], [bpy.data.objects[n] for n in rec["objects"]], usf)
        got = _table(arms[0], representation=readback_units)
        got_parents = {b.name: b.parent.name if b.parent else None for b in arms[0].data.bones}
        container = None
        extra = sorted(set(got) - set(ref_table))
        if len(extra) == 1 and got_parents[extra[0]] is None and any(got_parents.get(r) == extra[0] for r, p in ref_parents.items() if p is None):
            container = extra[0]
            got.pop(container)
        try:
            display_rows = RC.readback_rows(ref_table, got)
        except RC.RigRefused as exc:
            display_roster_error = str(exc)
        if coordinates == "cm" and readback_units is not None:
            try:
                got, authored_parents, authored_proof = _authored_table(writing, prepared["exporter"])
                if authored_parents != ref_parents:
                    hierarchy_error = "authored FBX hierarchy differs from the reference"
            except C.FeatureError as exc:
                authored_error = str(exc)
        try:
            rows = RC.readback_rows(ref_table, got)
        except RC.RigRefused as exc:
            rows = None
            roster = str(exc)
        corner = []
        for m in mesh_obs:
            back = next((bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "MESH"
                         and (n == export_mesh_names[m.name] or n.rsplit(".", 1)[0] == export_mesh_names[m.name])), None)
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
    if authored_error:
        problems.append(authored_error)
    if hierarchy_error:
        problems.append(hierarchy_error)
    if container_scale_failures:
        problems.append("authored nonunit FBX Null ancestors: " + ", ".join(
            f"{r['ancestor']} -> {r['bone']} scale {r['scale']}" for r in container_scale_failures[:8]))
    if authored_bone_scale_failures:
        problems.append("authored nonunit centimetre bone scales: " + ", ".join(authored_bone_scale_failures[:8]))
    if rows is None:
        problems.append(f"the read-back roster differs: {roster}")
    elif rows["over_tolerance"]:
        worst = sorted(rows["over_tolerance"], key=lambda r: -r["rotation_deg"])[:8]
        problems.append("the read-back is over the bind_mismatch bars on " + ", ".join(
            f"{r['bone']} ({r['position_cm']:.3g} cm, {r['rotation_deg']:.3g} deg, scale {r['scale']:.3g})" for r in worst))
    if expect is not None and (usf is None or abs(usf - float(expect)) > 1e-9):
        problems.append(f"the file says UnitScaleFactor {usf} where the recipe {doc.get('name')} expects {float(expect):g}")
    fbx_sha = hashlib.sha256(writing.read_bytes()).hexdigest()
    summary = {"recipe": {"name": doc.get("name"), "path": str(recipe_path), "exporter": doc["exporter"]}, "convention": convention,
               "recipe_selection": {"requested": recipe or "auto", "measured_convention": convention,
                                    "selected": doc.get("name"), "source": (
                                        "independent_native_reference_bind" if ob.get("lw_native_reference_bind") else "measured_normalized_frames"
                                    ) if recipe in ("", "auto", None) else "explicit_caller_recipe",
                                    "ue_confirmation": "pending M-RIG-01; Blender raw-frame readback alone does not prove physical Unreal acceptance"},
               "unit_scale_factor": usf, "reference": ref_name, "container_top_bone": container, "animation": anim,
               "reference_scope": "independent_blender_reference" if reference else (
                   "independent_native_bind" if ob.get("lw_native_reference_bind") else "self_roundtrip"),
               "engine_bind_acceptance": "unverified; requires fresh actual UE import parity of the written file",
               "export_space": space_receipt, "effective_exporter": effective_exporter,
               "readback_representation": readback_units, "container_scale_failures": container_scale_failures,
               "authored_bind_verification": authored_proof,
               "display_reconstruction_errors": display_rows["over_tolerance"] if display_rows else [],
               "display_reconstruction_roster_error": display_roster_error,
               "authored_bone_scale_failures": authored_bone_scale_failures,
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
