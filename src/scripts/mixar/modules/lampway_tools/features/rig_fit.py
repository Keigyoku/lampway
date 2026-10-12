# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_fit_template (specs/canon/rig_tools/rig_fit_template.md; canon 20): rig the fitted example at its OWN joints.

TITAN rig-axi is the prior art (its joints schema and required-joint list reused, the code re-implemented): a titan.rig-joints/1 file measured on the example, provenance checked by the
example's sha256, the template's heads written to the measured joints (closed form, canon 20 B.2), the other bones placed by their measured
segments (rig_tools/core.fit_template), frames by canon 17 (core.conform_plan, the template's Z as the up hint), an inside check of six axis
rays per joint, and the example's own weights transferred from its fitted procedural body (canon20 B5 / canon07 B7). GRT's
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
from ..canon_geom import procedural_body as PB
from ..rig_tools import core as RC

SCHEMA = "titan.rig-joints/1"
HIDDEN_DEFAULT = ("pelvis", "thigh_l", "thigh_r")
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


def _joints(joints, ob, sha, root, template, hidden=None):
    if joints == "views":
        raise C.FeatureError("joints from views need the pose environment (canon 11: a 2D keypoint detector, the captain's choice, is not installed "
                             "here): measure the joints elsewhere and pass a titan.rig-joints/1 file")
    if joints.startswith("centre:rig:"):
        from . import rig_fit_measure as RM
        arm = C.need_object(joints[len("centre:rig:"):], "ARMATURE")
        doc = RM.measure_own_rig(ob, arm, hidden=HIDDEN_DEFAULT if hidden is None else hidden)
        if doc["example_sha256"] != sha:
            raise C.FeatureError("centred own-rig measurement does not match the example SHA256; use the scene mesh object")
        raw = json.dumps(doc, sort_keys=True, allow_nan=False).encode()
        return doc["joints"], {"source": joints, "example_sha256": sha, "measurement": doc["measurement"]}, _sha_bytes(raw)
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
    # Measured rig joints are REST heads. An existing action must not turn this
    # provenance/inside check into a comparison against animated geometry.
    arms = {m.object for m in ob.modifiers if m.type == "ARMATURE" and m.object is not None}
    poses = {arm: arm.data.pose_position for arm in arms}
    try:
        for arm in arms:
            arm.data.pose_position = "REST"
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        tree = BVHTree.FromObject(ob, dg)
        inv = ob.matrix_world.inverted()
        out = {}
        for n, p in points.items():
            q = inv @ Vector(p)
            out[n] = sum(1 for d in RAYS if tree.ray_cast(q, d)[0] is not None)
        return out
    finally:
        for arm, pose in poses.items():
            arm.data.pose_position = pose
        bpy.context.view_layer.update()


def _procedural_weights(example, rigged, arm, heads, parents):
    """Titan rig-blender m_weights: measured elliptical limbs, nearest face transfer.

    These recipe constants reproduce the referenced implementation; they are
    construction parameters, not motion quality thresholds or fit acceptance.
    """
    arms = {m.object for m in example.modifiers if m.type == "ARMATURE" and m.object is not None}
    poses = {a: a.data.pose_position for a in arms}
    body_ob = None
    body_mesh = None
    try:
        for a in arms:
            a.data.pose_position = "REST"
        bpy.context.view_layer.update()
        evaluated = example.evaluated_get(bpy.context.evaluated_depsgraph_get())
        mesh = evaluated.to_mesh()
        try:
            tree = BVHTree.FromPolygons([example.matrix_world @ v.co for v in mesh.vertices], [list(p.vertices) for p in mesh.polygons])
        finally:
            evaluated.to_mesh_clear()
        segments = CB.bone_segments(heads, parents, main_child=CB.CONTINUATION)
        bones = {}
        def radii(point, x, z, reach):
            values = []
            for axis in (x, z):
                hits = [tree.ray_cast(point, sign * axis, reach) for sign in (1, -1)]
                distances = [h[3] for h in hits if h[0] is not None]
                values.append(0.85 * sum(distances) / len(distances) if distances else None)
            a, b = values
            a = a if a is not None else (b if b is not None else 0.02)
            return (a, b if b is not None else a)
        for name in sorted(heads):
            head, tail = map(Vector, segments[name])
            along = (tail - head).normalized()
            frame = arm.data.bones[name].matrix_local.to_3x3()
            across = min((frame.col[i].normalized() for i in range(3)), key=lambda v: abs(v.dot(along)))
            x = (across - along * across.dot(along)).normalized()
            z = x.cross(along)
            reach = 0.03 if name.split("_")[0] in ("thumb", "index", "middle", "ring", "pinky") else (0.08 if name.startswith(("hand", "foot", "ball")) else 0.3)
            bones[name] = {"parent": parents[name], "length": (tail - head).length,
                           "frame": ((x.x, along.x, z.x, head.x), (x.y, along.y, z.y, head.y), (x.z, along.z, z.z, head.z), (0, 0, 0, 1)),
                           "head": radii(head, x, z, reach), "tail": radii(tail, x, z, reach)}
        widths = PB.joint_blends(bones, 0.25)
        for name, width in widths.items():
            bones[name]["blend"] = width
        body = PB.body(bones, stations=6, sides=12, blend=min(widths.values(), default=0))
        body_mesh = bpy.data.meshes.new("lw_fit_weight_body")
        body_mesh.from_pydata(body["verts"], [], body["faces"])
        body_mesh.update()
        body_ob = bpy.data.objects.new("lw_fit_weight_body", body_mesh)
        bpy.context.scene.collection.objects.link(body_ob)
        groups = {n: body_ob.vertex_groups.new(name=n) for n in sorted(bones)}
        for i, weights in enumerate(body["weights"]):
            for name, value in weights.items():
                groups[name].add([i], value, "REPLACE")
        mod = rigged.modifiers.new("lw_fit_weight_transfer", "DATA_TRANSFER")
        mod.object = body_ob
        mod.use_vert_data = True
        mod.data_types_verts = {"VGROUP_WEIGHTS"}
        mod.vert_mapping = "POLYINTERP_NEAREST"
        mod.layers_vgroup_select_src = "ALL"
        mod.layers_vgroup_select_dst = "NAME"
        with bpy.context.temp_override(object=rigged, active_object=rigged, selected_objects=[rigged]):
            bpy.ops.object.datalayout_transfer(modifier=mod.name)
            bpy.ops.object.modifier_apply(modifier=mod.name)
        unweighted = sum(not any(g.weight > 1e-6 for g in v.groups) for v in rigged.data.vertices)
        if unweighted:
            raise C.FeatureError(f"procedural body transfer left {unweighted} vertices unweighted: audit the example's fitted body")
        return {"source": "fitted example procedural body (canon20 B5 / canon07 B7)", "method": "procedural_body_nearest_face",
                "bones": len(bones), "body_verts": len(body["verts"]), "body_faces": len(body["faces"]),
                "joint_blend_fraction": 0.25, "joint_blends_m": widths, "unweighted": unweighted}
    finally:
        if body_ob is not None:
            bpy.data.objects.remove(body_ob, do_unlink=True)
        if body_mesh is not None and body_mesh.users == 0:
            bpy.data.meshes.remove(body_mesh)
        for a, pose in poses.items():
            a.data.pose_position = pose
        bpy.context.view_layer.update()


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
    J, src, joints_sha = _joints(joints, ob, sha, root, tpl, hidden)
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
        if rigged.parent is not None and rigged.parent.type == "ARMATURE":
            world = rigged.matrix_world.copy()
            rigged.parent = None
            rigged.parent_type = "OBJECT"
            rigged.matrix_world = world
        for g in list(rigged.vertex_groups):
            rigged.vertex_groups.remove(g)
        # This is a replacement bind on a new mesh, including when the example
        # arrived rigged. Keeping its old Armature would deform the copy twice.
        for mod in list(rigged.modifiers):
            if mod.type == "ARMATURE":
                rigged.modifiers.remove(mod)
        grammar = [n for n in RC.REQUIRED_JOINTS if n in f["heads"]]
        if weights == "procedural":
            gpar = {}
            for n in grammar:
                p = tpl["parents"].get(n)
                while p is not None and p not in grammar:
                    p = tpl["parents"].get(p)
                gpar[n] = p
            wdoc = _procedural_weights(ob, rigged, arm_ob, {n: f["heads"][n] for n in grammar}, gpar)
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
