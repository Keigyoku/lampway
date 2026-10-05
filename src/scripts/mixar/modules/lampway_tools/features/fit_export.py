# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""fit_export: the rigged export of a fitted piece, behind gates, with a read-back.

Gates (each names its fix): a validation with FAIL, roles with no declared limits (unless allow_unverified, and then the README says so), a bind check that is not ok, textures whose recorded mesh hash is
not this mesh (a geometry step discards the texture), vertex groups naming a bone the body does not have, an existing tag directory. The FBX is written with the contract's settings (primary bone axis Z,
secondary X, leaf bones off, units applied) and READ BACK: every joint's position AND its axes against the body package (a position-only check passed exports whose frames were 90 degrees off, so it is
never the gate)."""

import hashlib
import json
import math
import shutil
from pathlib import Path

import bpy
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


def _readback(fbx, joints):
    before_o, before_a = set(bpy.data.objects), set(bpy.data.armatures)
    bpy.ops.import_scene.fbx(filepath=str(fbx), automatic_bone_orientation=False, primary_bone_axis="Z", secondary_bone_axis="X", ignore_leaf_bones=False)
    new = [o for o in bpy.data.objects if o not in before_o]
    arms = [o for o in new if o.type == "ARMATURE"]
    try:
        if not arms:
            return {"ok": False, "error": "the exported FBX has no armature"}
        arm = arms[0]
        pos, ang, n = 0.0, 0.0, 0
        for j in joints:
            nm = j["name"]
            b = arm.data.bones.get(nm)
            if b is None:
                return {"ok": False, "error": f"the exported FBX is missing bone {nm}"}
            head = np.array((arm.matrix_world @ b.head_local)[:])
            pos = max(pos, float(np.linalg.norm(head - np.array(j["head"]))))
            rot = (arm.matrix_world @ b.matrix_local).to_3x3()
            for k, axis in enumerate("xyz"):
                got = np.array(rot.col[k][:])
                want = np.array(j["axes"][axis])
                ang = max(ang, math.degrees(math.acos(float(np.clip(got @ want, -1, 1)))))
            n += 1
        return {"ok": pos < POS_TOL_M and ang < AXIS_TOL_DEG, "position_max_m": pos, "axis_max_deg": ang, "bones_compared": n}
    finally:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in [a for a in bpy.data.armatures if a not in before_a]:
            bpy.data.armatures.remove(a)


def run(object, armature, out_dir, body, textures, validation, bind_check, note, allow_unverified, root, bone_axis="Z"):
    ob = C.need_object(object)
    arm = C.need_object(armature, "ARMATURE")
    out = Path(root) / out_dir
    if out.exists():
        raise C.FeatureError(f"{out_dir} exists: a tag directory is never reused (pick a new one)")
    pkg = Path(body)
    FB.verify(body)
    joints = json.loads((pkg / "joints.json").read_text())["joints"]
    val = _json(root, validation, "validation")
    counts = (val.get("summary") or {}).get("counts", {})
    if counts.get("FAIL", 0) or counts.get("UNPROVEN", 0):
        raise C.FeatureError(f"validation has {counts.get('FAIL', 0)} FAIL" + (f" and {counts['UNPROVEN']} UNPROVEN" if counts.get("UNPROVEN") else "") + ": fix or rule before export")
    roles = sorted({p["role"] for row in val.get("poses", []) for p in row.get("pieces", {}).values() if p.get("judge", {}).get("verdict") == "UNVERIFIED"})
    if roles and not allow_unverified:
        raise C.FeatureError(f"roles without declared limits: {roles}; pass allow_unverified=true to export with the report saying so")
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
    out.mkdir(parents=True)
    fbx = out / f"{ob.name}.fbx"
    sel = [o for o in bpy.context.view_layer.objects if o.select_get()]
    active = bpy.context.view_layer.objects.active
    try:
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        arm.select_set(True)
        bpy.context.view_layer.objects.active = arm
        bpy.ops.export_scene.fbx(filepath=str(fbx), use_selection=True, object_types={"ARMATURE", "MESH"}, add_leaf_bones=False, primary_bone_axis=bone_axis, secondary_bone_axis="X",
                                 global_scale=1.0, apply_unit_scale=True, bake_anim=False, path_mode="COPY", embed_textures=False, mesh_smooth_type="FACE")
    finally:
        bpy.ops.object.select_all(action="DESELECT")
        for o in sel:
            o.select_set(True)
        bpy.context.view_layer.objects.active = active
    (out / "Textures").mkdir()
    files = {fbx.name: hashlib.sha256(fbx.read_bytes()).hexdigest()}
    for t in tex_paths:
        shutil.copy(t, out / "Textures" / t.name)
        files[f"Textures/{t.name}"] = hashlib.sha256(t.read_bytes()).hexdigest()
    rb = _readback(fbx, joints)
    limits_line = f"limits: {(val.get('summary') or {}).get('limits_status', 'proposed')}" + (f"; roles without limits: {', '.join(roles)}" if roles else "")
    readme = ["# " + ob.name, "", note or "", "", "## Files (sha256)"] + [f"- {k}: {v}" for k, v in files.items()] + [
        "", "## Conventions", "UnitScaleFactor 1 (units applied), centimetres in the engine, primary bone axis Z, secondary X, no leaf bones.", "ORM: R occlusion, G roughness, B metallic (Unreal order), linear. Normal_DX has green flipped from Normal_GL.",
        "", "## Validation", f"counts: {counts}", limits_line, "", "## Read-back", f"joints compared {rb.get('bones_compared')}, position max {rb.get('position_max_m')} m, axis max {rb.get('axis_max_deg')} degrees: {'ok' if rb.get('ok') else 'FAILED'}"]
    (out / "README.md").write_text("\n".join(readme))
    (out / "export.json").write_text(json.dumps({"object": ob.name, "files": files, "validation_counts": counts, "limits": limits_line, "readback": rb, "mesh_sha256": mesh_sha, "unverified_roles": roles}, indent=1))
    if not rb.get("ok"):
        return {"ok": False, "error": f"read-back failed: the exported bone axes or positions do not equal the body package's (position {rb.get('position_max_m')} m, axes {rb.get('axis_max_deg')} degrees): the export settings are wrong", "readback": rb, "out_dir": str(out)}
    return {"ok": True, "out_dir": str(out), "files": files, "readback": rb, "limits": limits_line}
