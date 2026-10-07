# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_fit_template (specs/canon/rig_tools/rig_fit_template.md; canon 20): rig the fitted example at its OWN joints.

TITAN rig-axi is the prior art (its joints schema and required-joint list reused, the code re-implemented): a titan.rig-joints/1 file measured on the example, provenance checked by the
example's sha256, the template's heads written to the measured joints (closed form, canon 20 B.2), the other bones placed by their measured
segments (rig_tools/core.fit_template), frames by canon 17 (core.conform_plan, the template's Z as the up hint), an inside check of six axis
rays per joint, and the example's own weights from the fitted bone segments (canon 07 falloff; never copied from the native body). GRT's
Unreal module (appended Mannequin, hand-placed controls, Apply Rig) is not ported: the measurement replaces the hand placement.

Writes the armature <example>_rig and a weighted copy <example>_rigged (the example itself is never touched) and saves both to ``out``
(.blend). Refused: a joints file measured on another mesh, joints copied from the template's body (copied_not_fitted), a required joint
missing, joints outside the example unless allow_outside names them, joints or hands from views (the pose environment is not here)."""

import hashlib
import json
import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

from .. import canon_io
from . import common as C
from . import rig_conform as RF
from ..canon_geom import bones as CB
from ..canon_geom import skinweights as SW
from ..rig_tools import core as RC

SCHEMA = "titan.rig-joints/1"
HIDDEN_DEFAULT = ("pelvis", "thigh_l", "thigh_r")
WEIGHT_MARGIN_M = 0.03          # canon 07 falloff: every bone within 3 cm of the nearest segment shares the vertex (Lampway's choice)
RAYS = [Vector(v) for v in ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))]


def _sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


@canon_io.rollback_imports
def _example(example, root):
    """(object, sha256, how): a scene mesh (its geometry sha256, canon_io) or a .glb/.fbx/.obj imported through canon_io (the file's)."""
    from .. import canon_io
    if os.path.splitext(example)[1].lower() in canon_io.IMPORTERS:
        p = Path(example) if os.path.isabs(example) else Path(root, example)
        if not p.is_file():
            raise C.FeatureError(f"no example file at {p}")
        rec = canon_io.import_raw(str(p))
        meshes = [bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "MESH"]
        if len(meshes) != 1:
            raise C.FeatureError(f"{p.name} holds {len(meshes)} meshes: the example is one mesh")
        return meshes[0], rec["sha256"], "file"
    ob = C.need_object(example, "MESH")
    return ob, canon_io.geometry_sha256(ob), "geometry"


def _joints(joints, ob, sha, root, template):
    if joints == "views":
        raise C.FeatureError("joints from views need the pose environment (canon 11: a 2D keypoint detector, the captain's choice, is not installed "
                             "here): measure the joints elsewhere and pass a titan.rig-joints/1 file")
    if joints.startswith("rig:"):
        arm = C.need_object(joints[4:], "ARMATURE")
        if not any(m.type == "ARMATURE" and m.object is arm for m in ob.modifiers):
            raise C.FeatureError(f"{arm.name} does not deform {ob.name}: joints from a rig must be the example's own rig")
        J = {b.name: list(arm.matrix_world @ b.head_local) for b in arm.data.bones if b.name in template["heads"]}
        return J, {"source": f"rig:{arm.name}"}, None
    p = Path(joints) if os.path.isabs(joints) else Path(root, joints)
    if not p.is_file():
        raise C.FeatureError(f"no joints file at {p}: a titan.rig-joints/1 file measured on the example, 'rig:<armature>' or 'views'")
    raw = p.read_bytes()
    doc = json.loads(raw)
    if doc.get("schema") != SCHEMA:
        raise C.FeatureError(f"{p.name}: schema must be {SCHEMA}, not {doc.get('schema')!r}")
    J = doc.get("joints")
    if not isinstance(J, dict) or not all(isinstance(v, list) and len(v) == 3 and all(np.isfinite(v)) for v in J.values()):
        raise C.FeatureError(f"{p.name}: a 'joints' map of name -> [x, y, z] (metres, the example's frame)")
    measured_on = doc.get("example_sha256") or (doc.get("views") or {}).get("example_sha256")
    if measured_on != sha:
        raise C.FeatureError(f"{p.name} was measured on another mesh (example_sha256 {str(measured_on)[:12]}... is not {ob.name}'s {sha[:12]}...): "
                             "measure the joints on this example")
    return J, {"source": str(p)}, _sha_bytes(raw)


def _inside(ob, points):
    dg = bpy.context.evaluated_depsgraph_get()
    tree = BVHTree.FromObject(ob, dg)
    inv = ob.matrix_world.inverted()
    out = {}
    for n, p in points.items():
        q = inv @ Vector(p)
        out[n] = sum(1 for d in RAYS if tree.ray_cast(q, d)[0] is not None)
    return out


@canon_io.rollback_imports
def fit(example, joints, root, template="", hands="none", hidden=None, convention="blender", weights="procedural", allow_outside=None, out="",
        dry_run=False):
    if hands != "none":
        raise C.FeatureError("hands from views need the pose environment (canon 11; the hand model is not installed here): pass hands=none and "
                             "measure the finger joints into the joints file")
    if weights not in ("procedural", "none"):
        raise C.FeatureError("weights is procedural | none")
    ob, sha, how = _example(example, root)
    probe = bpy.data.objects.new("lw_fit_probe", None)
    try:
        tpl = RF.reference_rig(Path(root, template) if template and not os.path.isabs(template) else template, probe)
    finally:
        bpy.data.objects.remove(probe)
    J, src, joints_sha = _joints(joints, ob, sha, root, tpl)
    required = [n for n in RC.REQUIRED_JOINTS if n in tpl["heads"]]
    try:
        f = RC.fit_template(tpl, J, required)
    except RC.RigRefused as exc:
        raise C.FeatureError(str(exc)) from None
    if f["copied_not_fitted"]:
        raise C.FeatureError("copied_not_fitted: every measured bone length equals the template's within 0.1 % - these joints were taken from "
                             "the template's own body (the 2026-09-28 defect), not measured on the example")
    rays = _inside(ob, {n: f["heads"][n] for n in f["measured"]})
    outside = sorted(n for n, k in rays.items() if k < len(RAYS))
    allowed = set(allow_outside or [])
    if set(outside) - allowed:
        raise C.FeatureError(f"joints outside {ob.name} (fewer than six axis rays hit it): {', '.join(sorted(set(outside) - allowed))}; re-measure "
                             "them, or name them in allow_outside")
    src_rig = {"names": tpl["names"], "parents": tpl["parents"], "heads": f["heads"], "frames": tpl["frames"], "lengths": {}}
    kids, rkids = {}, {}
    for n, p in tpl["parents"].items():
        if p is not None:
            kids.setdefault(p, []).append(n)
    for n in tpl["names"]:
        nxt = RC._next_joint(n, f["heads"], tpl["parents"], kids, kids)
        src_rig["lengths"][n] = max(float(np.linalg.norm(nxt - np.asarray(f["heads"][n]))) if nxt is not None else 0.0, 0.01)
    try:
        plan = RC.conform_plan(src_rig, {n: n for n in tpl["names"]}, {}, tpl, convention)
    except RC.RigRefused as exc:
        raise C.FeatureError(str(exc)) from None
    hid = list(HIDDEN_DEFAULT if hidden is None else hidden)
    name = f"{ob.name}_rig"
    target = Path(out) if out and os.path.isabs(out) else Path(root, out or f"rig/{ob.name}.rig.blend")
    receipt = {"example": ob.name, "residual": f["residual"], "ratios": {k: round(v, 9) for k, v in f["ratios"].items()}, "synthesized": f["synthesized"],
               "hidden": hid, "outside": outside, "inside_rays": rays, "unused_joints": f["unused"], "convention": convention, "template": tpl["name"],
               "joints": src, "out": str(target)}
    if dry_run:
        return {**receipt, "dry_run": True, "sha256": {"example": sha, "joints": joints_sha, "template": tpl["sha256"]}}
    clash = sorted(n for n in (name, f"{ob.name}_rigged") if n in bpy.data.objects)
    if clash or target.exists():
        raise C.FeatureError(f"{', '.join(clash) or target} already exist: a fit never overwrites; remove them or pass another out")
    arm = bpy.data.armatures.new(name)
    arm_ob = bpy.data.objects.new(name, arm)
    bpy.context.scene.collection.objects.link(arm_ob)
    made = [arm_ob]
    try:
        C.activate(arm_ob)
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = {}
        for b in plan["bones"]:
            e = arm.edit_bones.new(b["name"])
            e.head = b["head"]
            e.tail = np.add(b["head"], (0.0, 0.0, b["length"]))
            ebs[b["name"]] = e
        for b in plan["bones"]:
            e = ebs[b["name"]]
            e.parent = ebs[b["parent"]] if b["parent"] else None
            R = np.asarray(b["frame"], float)
            e.matrix = Matrix(((*R[0], b["head"][0]), (*R[1], b["head"][1]), (*R[2], b["head"][2]), (0, 0, 0, 1)))
            e.length = b["length"]
        bpy.ops.object.mode_set(mode="OBJECT")
        rigged = ob.copy()
        rigged.data = ob.data.copy()
        rigged.name = rigged.data.name = f"{ob.name}_rigged"
        for coll in ob.users_collection or [bpy.context.scene.collection]:
            coll.objects.link(rigged)
        made.append(rigged)
        for g in list(rigged.vertex_groups):
            rigged.vertex_groups.remove(g)
        grammar = [n for n in RC.REQUIRED_JOINTS if n in f["heads"]]
        wdoc = {"source": "procedural: canon 07 falloff over the fitted bone segments (never the native body's weights)", "margin_m": WEIGHT_MARGIN_M,
                "bones": len(grammar), "unweighted": 0}
        if weights == "procedural":
            gpar = {}
            for n in grammar:
                p = tpl["parents"].get(n)
                while p is not None and p not in grammar:
                    p = tpl["parents"].get(p)
                gpar[n] = p
            segs = CB.bone_segments({n: f["heads"][n] for n in grammar}, gpar, main_child=CB.CONTINUATION)
            groups = {n: rigged.vertex_groups.new(name=n) for n in grammar}
            mw = rigged.matrix_world
            for v in rigged.data.vertices:
                w = SW.falloff_weights(np.array(mw @ v.co), segs, WEIGHT_MARGIN_M)
                for b, x in w.items():
                    groups[b].add([v.index], float(x), "REPLACE")
            wdoc["unweighted"] = sum(1 for v in rigged.data.vertices if not v.groups)
        else:
            wdoc = {"source": "none"}
        mod = rigged.modifiers.new("Armature", "ARMATURE")
        mod.object = arm_ob
        target.parent.mkdir(parents=True, exist_ok=True)
        bpy.data.libraries.write(str(target), set(made), fake_user=False)
    except Exception:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in made:
            data = o.data
            bpy.data.objects.remove(o)
            if data is not None and data.users == 0:
                (bpy.data.armatures if isinstance(data, bpy.types.Armature) else bpy.data.meshes).remove(data)
        raise
    return {**receipt, "dry_run": False, "armature": name, "rigged": f"{ob.name}_rigged", "weights": wdoc,
            "sha256": {"example": sha, "joints": joints_sha, "template": tpl["sha256"], "out": _sha_bytes(target.read_bytes())}}
