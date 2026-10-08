# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_export: the rigged export of a fitted piece, behind gates, with a read-back.

Gates (each names its fix): a validation with FAIL, roles with no declared limits (unless allow_unverified, and then the README says so), a bind check that is not ok, textures whose recorded mesh hash is
not this mesh (a geometry step discards the texture), vertex groups naming a bone the body does not have, an existing tag directory.
Canon21 measured convention recipes write independent centimetre copies, then
raw units/carriers and authored position/rotation/scale/hierarchy are verified
against the body package. Imported display errors remain explicit diagnostics."""

import hashlib
import json
import shutil
from pathlib import Path

import bpy

from .. import canon_io
import numpy as np

from . import common as C
from . import fit_body as FB
from . import workflows as W

POS_TOL_M = 1e-4
AXIS_TOL_DEG = 0.5


def _json(root, p, what):
    q = Path(root) / p if not Path(p).is_absolute() else Path(p)
    if not q.exists():
        raise C.FeatureError(f"{what} {p} is missing: run it first")
    return json.loads(q.read_text())


def export_settings(arm, settings, bone_axis=None):
    """Use canon21's measured convention recipe for both fitted-piece routes."""
    from . import rig_export as RE
    convention = RE._convention(arm)
    doc, _path = RE._recipe("auto", "", convention)
    out = dict(settings)
    for key in ("axis_forward", "axis_up", "primary_bone_axis", "secondary_bone_axis"):
        out[key] = doc["exporter"][key]
    if bone_axis is not None:  # retained wrong-pair falsifier, never the default
        out["primary_bone_axis"] = bone_axis
        out["secondary_bone_axis"] = "X"
    out.update(apply_scale_options="FBX_SCALE_NONE", apply_unit_scale=True, global_scale=1.0)
    return out, convention, {"selected": doc["name"], "measured_convention": convention,
                            "requested": "auto" if bone_axis is None else "explicit_axis_override",
                            "ue_armature_container": doc["ue_armature_container"]}


def _joint_reference(joints, convention):
    from . import rig_export as RE
    from ..rig_tools import fbx_bind as BIND
    if convention not in ("blender", "ue_axes") or not joints:
        raise C.FeatureError("read-back needs a nonempty body skeleton and its measured convention")
    table, parents = {}, {}
    turn = RE.ENGINE_FROM_BLENDER if convention == "blender" else np.eye(3)
    for j in joints:
        if j["name"] in table:
            raise C.FeatureError("body package has duplicate joint identities")
        matrix = np.eye(4)
        matrix[:3, :3] = np.array([j["axes"][a] for a in "xyz"]).T
        matrix[:3, 3] = np.array(j["head"]) * 100.0
        try:
            scale, frame = BIND._rigid(matrix)
        except BIND.BindRefused as exc:
            raise C.FeatureError("body package rest frame refused: " + str(exc)) from None
        table[j["name"]] = {"translation": list(matrix[:3, 3]),
                            "rotation": list(BIND._quaternion(frame @ turn)), "scale": list(scale)}
        parents[j["name"]] = j["parent"]
    return table, parents


def _readback(fbx, joints, convention="blender", exporter=None):
    """Admit raw unit carriers, then compare authored binds under canon21 bars.

    Import reconstruction errors stay visible; temporary IDs and selection are
    restored on success and failure. No readback matrix or source data is changed.
    """
    from . import rig_export as RE, rig_export_space as ES, export_checks as EC
    from ..rig_tools import core as RC
    before = canon_io.snapshot_ids()
    result = {"ok": False, "bones_compared": 0,
              "engine_bind_acceptance": "unverified; requires actual native Unreal reference capture"}
    try:
        imported = canon_io.import_raw(str(fbx), **RE.RAW_IMPORT)
        objects = [bpy.data.objects[n] for n in imported["objects"]]
        arms = [o for o in objects if o.type == "ARMATURE"]
        if len(arms) != 1:
            return dict(result, error="the exported FBX needs exactly one armature")
        if not joints:
            return dict(result, error="the body package has no joints; no bind is proven")
        unit = RE.unit_scale_factor(fbx)
        carriers = EC.fbx_container_scale_failures(fbx)
        scales = {n: s for n, s in EC.fbx_bone_scale(fbx).items()
                  if any(abs(v - 1.0) > RC.BARS["scale"] for v in s)}
        result.update(unit_scale_factor=unit, container_scale_failures=carriers,
                      authored_bone_scale_failures=scales)
        if unit != 1.0 or carriers or scales:
            return dict(result, error="raw FBX units, Null ancestry or bone scales are not centimetre identity carriers")
        units = ES.readback_representation(arms[0], objects, unit)
        result["readback_representation"] = units
        reference, parents = _joint_reference(joints, convention)
        display = RE._table(arms[0], representation=units)
        if "Armature" not in reference:
            display.pop("Armature", None)
        try:
            diagnostics = RC.readback_rows(reference, display)
            result["display_reconstruction_errors"] = diagnostics["over_tolerance"]
        except RC.RigRefused as exc:
            result["display_reconstruction_roster_error"] = str(exc)
        got, got_parents, proof = RE._authored_table(fbx, exporter or {"axis_forward": "-Z", "axis_up": "Y"})
        rows = RC.readback_rows(reference, got)
        result.update(bones_compared=rows["bones_compared"], position_max_m=rows["worst_position_cm"] / 100.0,
                      axis_max_deg=rows["worst_rotation_deg"], scale_max=rows["worst_scale"],
                      over_tolerance=rows["over_tolerance"], bars=rows["bars"],
                      authored_bind_verification=proof, hierarchy_matches=got_parents == parents)
        result["ok"] = (not rows["over_tolerance"] and got_parents == parents
                        and result["position_max_m"] < POS_TOL_M and result["axis_max_deg"] < AXIS_TOL_DEG)
        if not result["ok"]:
            result["error"] = "the exported bind axes, scales or hierarchy differ from the body package"
        return result
    except (C.FeatureError, RC.RigRefused, ValueError) as exc:
        return dict(result, error=str(exc))
    finally:
        canon_io.remove_new_ids(before)


def gates(ob, body, textures, validation, bind_check, allow_unverified, root):
    """Every gate of a rigged export of ``ob`` against the body package, in order; returns what the export needs. Shared with
    ue_export's skinned_piece path (specs/ue_parity/contracts/ue_export.md §8: fit_export's gates)."""
    FB.verify(body)
    joints = json.loads((Path(body) / "joints.json").read_text())["joints"]
    val = _json(root, validation, "validation")
    counts = (val.get("summary") or {}).get("counts", {})
    if counts.get("FAIL", 0) or counts.get("UNPROVEN", 0):
        raise C.FeatureError(f"validation has {counts.get('FAIL', 0)} FAIL" + (f" and {counts['UNPROVEN']} UNPROVEN" if counts.get("UNPROVEN") else "") + ": fix or rule before export")
    roles = sorted({p["role"] for row in val.get("poses", []) for p in row.get("pieces", {}).values() if p.get("judge", {}).get("verdict") == "UNVERIFIED"})
    if roles and not allow_unverified:
        missing = sorted({m for row in val.get("poses", []) for p in row.get("pieces", {}).values() for m in p.get("judge", {}).get("missing", [])})
        raise C.FeatureError(f"roles without declared limits: {roles} (or with a metric not measured: {missing}; a metal part's body crossings need `body` in "
                             "the validation); pass allow_unverified=true to export with the report saying so")
    bc = _json(root, bind_check, "bind_check")
    if not bc.get("ok"):
        bones = [r.get("bone") for r in bc.get("over_tolerance", [])]
        raise C.FeatureError(f"the piece's bind does not equal the native reference pose (bones {bones}): leader-driven validation is meaningless")
    names = {j["name"] for j in joints}
    unknown = sorted(g.name for g in ob.vertex_groups if g.name not in names)
    if unknown:
        raise C.FeatureError(f"vertex groups name bones the native skeleton does not have: {unknown}")
    mesh_sha = W.mesh_hash(ob)
    tex_paths = [Path(root) / t if not Path(t).is_absolute() else Path(t) for t in textures or []]
    for t in tex_paths:
        mj = t.parent / "merge.json"
        if mj.exists() and json.loads(mj.read_text()).get("mesh_sha256") not in (None, mesh_sha):
            raise C.FeatureError(f"the textures predate the openings/bind geometry (their merge.json names another mesh): re-run steps 13-14 (a geometry step discards the texture)")
    return {"joints": joints, "counts": counts, "roles": roles, "mesh_sha256": mesh_sha, "textures": tex_paths, "validation": val}


def run(object, armature, out_dir, body, textures, validation, bind_check, note, allow_unverified, root, bone_axis=None):
    ob = C.need_object(object)
    arm = C.need_object(armature, "ARMATURE")
    out = Path(root) / out_dir
    if out.exists():
        raise C.FeatureError(f"{out_dir} exists: a tag directory is never reused (pick a new one)")
    g = gates(ob, body, textures, validation, bind_check, allow_unverified, root)
    joints, counts, roles, mesh_sha, tex_paths, val = g["joints"], g["counts"], g["roles"], g["mesh_sha256"], g["textures"], g["validation"]
    fbx = out / f"{ob.name}.fbx"
    from . import rig_export_space as ES
    settings, convention, recipe = export_settings(arm, {
        "use_selection": True, "object_types": {"ARMATURE", "MESH"}, "add_leaf_bones": False,
        "bake_anim": False, "path_mode": "COPY", "embed_textures": False, "mesh_smooth_type": "FACE"}, bone_axis)
    out.mkdir(parents=True)
    with ES.centimetre_copies(arm, [ob], None, settings, container_name=recipe["ue_armature_container"]) as prepared:
        export_space = prepared["receipt"]
        effective = prepared["exporter"]
        for obj in bpy.context.view_layer.objects:
            obj.select_set(obj is prepared["armature"] or obj in prepared["meshes"])
        bpy.context.view_layer.objects.active = prepared["armature"]
        bpy.ops.export_scene.fbx(filepath=str(fbx), **effective)
    (out / "Textures").mkdir()
    files = {fbx.name: hashlib.sha256(fbx.read_bytes()).hexdigest()}
    for t in tex_paths:
        shutil.copy(t, out / "Textures" / t.name)
        files[f"Textures/{t.name}"] = hashlib.sha256(t.read_bytes()).hexdigest()
    rb = _readback(fbx, joints, convention, effective)
    limits_line = f"limits: {(val.get('summary') or {}).get('limits_status', 'proposed')}" + (f"; roles without limits: {', '.join(roles)}" if roles else "")
    readme = ["# " + ob.name, "", note or "", "", "## Files (sha256)"] + [f"- {k}: {v}" for k, v in files.items()] + [
        "", "## Conventions", f"UnitScaleFactor 1, independent centimetre copies, primary bone axis {effective['primary_bone_axis']}, secondary {effective['secondary_bone_axis']}, no leaf bones.", "ORM: R occlusion, G roughness, B metallic (Unreal order), linear. Normal_DX has green flipped from Normal_GL.",
        "", "## Validation", f"counts: {counts}", limits_line, "", "## Read-back", f"joints compared {rb.get('bones_compared')}, position max {rb.get('position_max_m')} m, axis max {rb.get('axis_max_deg')} degrees: {'ok' if rb.get('ok') else 'FAILED'}"]
    (out / "README.md").write_text("\n".join(readme))
    (out / "export.json").write_text(json.dumps({"object": ob.name, "files": files, "validation_counts": counts, "limits": limits_line, "readback": rb, "mesh_sha256": mesh_sha, "unverified_roles": roles, "recipe_selection": recipe, "export_space": export_space, "effective_exporter": {k: sorted(v) if isinstance(v, set) else v for k, v in effective.items()}}, indent=1))
    if not rb.get("ok"):
        return {"ok": False, "error": f"read-back failed: the exported bone axes or positions do not equal the body package's (position {rb.get('position_max_m')} m, axes {rb.get('axis_max_deg')} degrees): the export settings are wrong", "readback": rb, "out_dir": str(out)}
    return {"ok": True, "out_dir": str(out), "files": files, "readback": rb, "limits": limits_line}
