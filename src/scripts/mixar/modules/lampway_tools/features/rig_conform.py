# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_conform (specs/canon/rig_tools/rig_conform.md; canon 16 B.4-B.7, 17): a mapped rig turned into the project's skeleton, ON A COPY.

Re-implemented from MB UE5 Rig Creator Pro's documented "Create UE5 Rig" behaviour; nothing ported. The plan is rig_tools/core.conform_plan
(names from map.json, missing torso bones at the reference's arc-length fractions, the reference's hierarchy, frames from the joints and the
reference's Z); this module applies it to a copy of the armature and of every mesh it deforms, renames the vertex groups with their bones,
merges only the groups named in merge_weights, and verifies:

* every head that existed is where it was, exactly (the copy's float32 rest, compared bit for bit);
* the skins at rest: the conformed copy against an untouched baseline copy, both evaluated by Blender (float32: the bar is the brief's
  1e-9 m plus the float32 resolution of the coordinates, both printed);
* the skins under a test pose given in WORLD terms (each source bone turned about its own head by its own angle, the same in both rigs):
  a skin deforms the same whatever the rest frames are, so a vertex group that did not follow its bone shows here.

For a verified complete native topology, implicit Manny is refused. Reserved reference='source_copy' preserves authored rest data
on independent copies, with identity mapping and no synthesis, offsets, IK additions or weight merging. The measured anatomical
convention must match the requested convention. This is source preservation, not independent native UE bind acceptance.

The source armature, its meshes and its actions are never touched; the copy carries no animation (rig_retarget / rig_convert carry motion
across frames). Never: delete a bone, clear every parent, apply a pose as rest, exec scene text."""

import hashlib
import json
import math
import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

from . import common as C
from . import rig_tools as RT
from ..rig_tools import core as RC
from ..canon_geom import native_topology as NT

POSE_AXIS = (0.267261242, 0.534522484, 0.801783726)       # the test pose's axis (1, 2, 3)/|.|: no bone of a symmetric rig lies on it
POSED_BAR_M = 1e-5                                        # float32 skinning of a posed mesh: the posed skins agree to this


def _q(xyzw):
    x, y, z, w = xyzw
    return Quaternion((w, x, y, z))


def reference_rig(path, ob):
    """The reference skeleton in the armature's own (local) space: {names, parents, heads, frames, name, sha256}. A titan.animation-profile/1
    (default: the shipped UE5 Manny) read through the to-blender adapter: translations reflected across Y and scaled by centimeters_per_unit,
    rotations conjugated by the reflection (q -> (-x, y, -z, w))."""
    p = Path(path) if path else RT.MANNY
    if not p.is_file():
        raise C.FeatureError(f"no reference profile at {p}: pass a titan.animation-profile/1 (rig_convert verb=profile writes one), or leave it empty for UE5 Manny")
    doc = json.loads(p.read_text())
    if doc.get("schema") != "titan.animation-profile/1":
        raise C.FeatureError(f"{p.name} is not a titan.animation-profile/1 (schema {doc.get('schema')!r}): rig_convert verb=profile writes one")
    k = float(doc["adapter"]["centimeters_per_unit"]) / 100.0
    inv = ob.matrix_world.inverted()
    inv3 = np.array(inv.to_3x3())
    names, parents, heads, frames = [], {}, {}, {}
    for b in doc["bones"]:
        t, q = b["bind"]["translation"], b["bind"]["rotation"]
        names.append(b["name"])
        parents[b["name"]] = b["parent"]
        heads[b["name"]] = tuple(inv @ Vector((t[0] * k, -t[1] * k, t[2] * k)))
        frames[b["name"]] = inv3 @ np.array(_q((-q[0], q[1], -q[2], q[3])).to_matrix())
    return {"names": names, "parents": parents, "heads": heads, "frames": frames, "name": f"{doc.get('name')} ({p.name})", "sha256": RC.sha(doc["bones"])}


def _source(ob):
    names, parents, heads, frames, lengths = [], {}, {}, {}, {}
    for b in ob.data.bones:
        names.append(b.name)
        parents[b.name] = b.parent.name if b.parent else None
        heads[b.name] = tuple(b.head_local)
        M = np.array(b.matrix_local.to_3x3())
        frames[b.name] = M / np.linalg.norm(M, axis=0)
        lengths[b.name] = float(b.length)
    return {"names": names, "parents": parents, "heads": heads, "frames": frames, "lengths": lengths}


def _skinned(ob):
    return [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object is ob for m in o.modifiers)]


def _copy(ob, name, meshes, suffix):
    """The armature and its meshes copied with their own data, linked beside the originals; no animation on the copies."""
    new = ob.copy()
    new.data = ob.data.copy()
    new.name = new.data.name = name
    new.animation_data_clear()
    new.data.animation_data_clear()
    for coll in ob.users_collection or [bpy.context.scene.collection]:
        coll.objects.link(new)
    for pb in new.pose.bones:
        pb.matrix_basis = Matrix.Identity(4)
    copies = []
    for m in meshes:
        c = m.copy()
        c.data = m.data.copy()
        c.name = c.data.name = f"{m.name}{suffix}"
        c.animation_data_clear()
        for coll in m.users_collection or [bpy.context.scene.collection]:
            coll.objects.link(c)
        for mod in c.modifiers:
            if mod.type == "ARMATURE" and mod.object is ob:
                mod.object = new
        if c.parent is ob:
            c.parent = new
        copies.append(c)
    return new, copies


def _remove(objs):
    for o in objs:
        data = o.data
        bpy.data.objects.remove(o)
        if data is not None and data.users == 0:
            (bpy.data.armatures if isinstance(data, bpy.types.Armature) else bpy.data.meshes).remove(data)


def _evaluated(meshes):
    dg = bpy.context.evaluated_depsgraph_get()
    out = []
    for m in meshes:
        e = m.evaluated_get(dg)
        me = e.to_mesh()
        mw = np.array(m.matrix_world)
        co = np.array([v.co for v in me.vertices], float)
        out.append(co @ mw[:3, :3].T + mw[:3, 3])
        e.to_mesh_clear()
    return out


def _world_pose(arm, delta, depth):
    """Pose every bone of ``arm`` so its armature-space matrix is delta[source name] @ rest (identity for a bone without one), parents first."""
    for d in sorted(set(depth.values())):
        for pb in arm.pose.bones:
            if depth[pb.name] == d:
                pb.matrix = delta.get(pb.name, Matrix.Identity(4)) @ pb.bone.matrix_local
        bpy.context.view_layer.update()


def _depth(arm):
    out = {}
    for b in arm.data.bones:
        n, d = b, 0
        while n.parent is not None:
            n, d = n.parent, d + 1
        out[b.name] = d
    return out


def _file_sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def conform(armature, map, root, reference="", convention="blender", ik_bones=False, offsets=None, merge_weights=None, out_name="", dry_run=True):
    ob = RT._armature(armature)
    stamp = RT._inspected(ob)
    if not map:
        raise C.FeatureError("map is required: run lampway_rig_map on the armature first and pass its out path")
    mp = Path(map) if os.path.isabs(map) else Path(root, map)
    if not mp.is_file():
        raise C.FeatureError(f"no map at {mp}: run lampway_rig_map armature={ob.name} out=<path> first")
    doc = json.loads(mp.read_text())
    if doc.get("schema") != "lampway.rig-map/1":
        raise C.FeatureError(f"{mp.name} is not a lampway.rig-map/1 map (schema {doc.get('schema')!r})")
    if doc["sha256"]["source_rest"] != stamp["input"]:
        raise C.FeatureError(f"{mp.name} was made from a different rest of {ob.name} (its source sha differs): run lampway_rig_map again")
    if any(abs(s - 1.0) > 1e-9 for s in ob.scale):
        raise C.FeatureError(f"{ob.name} carries object scale {list(ob.scale)}: run lampway_rig_normalize (canon 18) before conforming")
    src = _source(ob)
    preserving = reference == "source_copy"
    if not reference and src["parents"] == NT.PARENTS:
        raise C.FeatureError("the verified native rig needs an explicit native reference; reference='source_copy' preserves its authored rest without claiming UE parity; implicit Manny is refused")
    if preserving:
        if merge_weights:
            raise C.FeatureError("source_copy cannot merge weights")
        ref = {"name": "source_copy", "sha256": stamp["input"]}
    else:
        ref = reference_rig(Path(root, reference) if reference and not os.path.isabs(reference) else reference, ob)
    mapping = {s: v["source"] for s, v in doc["map"].items()}
    synth = {s: v["fraction"] for s, v in doc.get("synthesized", {}).items()}
    try:
        if preserving:
            measured = RC.classify_convention(list(RT.convention_angles(RT.read(ob)).values()))
            plan = RC.source_copy_plan(src, mapping, synth, convention, measured, offsets, bool(ik_bones))
        else:
            plan = RC.conform_plan(src, mapping, synth, ref, convention, offsets, bool(ik_bones))
    except RC.RigRefused as exc:
        raise C.FeatureError(str(exc)) from None
    meshes = _skinned(ob)
    final = {b["name"]: b for b in plan["bones"]}
    rename = {b["source"]: b["name"] for b in plan["bones"] if b["source"] is not None}
    merge = dict(merge_weights or {})
    for g, to in merge.items():
        if not any(g in m.vertex_groups for m in meshes):
            raise C.FeatureError(f"merge_weights: no mesh deformed by {ob.name} has a vertex group {g!r}")
        if to not in final:
            raise C.FeatureError(f"merge_weights: {to!r} is not a bone of the conformed rig (its bones are named after the map)")
    name = out_name or f"{ob.name}_ue"
    suffix = f"_{name}"
    clash = sorted(n for n in [name] + [f"{m.name}{suffix}" for m in meshes] if n in bpy.data.objects)
    if clash:
        raise C.FeatureError(f"{', '.join(clash)} already exist: conform never overwrites an object; pass another out_name")
    summary = {"armature": ob.name, "out": name, "convention": convention, "renamed": plan["renamed"], "synthesized": plan["synthesized"],
               "reparented": plan["reparented"], "frames": plan["frames"], "unreferenced": plan["unreferenced"], "meshes": [m.name for m in meshes],
               "merged_groups": merge, "reference": ref["name"],
               "sha256": {"input": stamp["input"], "map": _file_sha(mp), "reference": ref["sha256"]}}
    if preserving:
        summary.update(reference_scope="source_preservation", engine_bind_acceptance="unverified; source rest preservation is not native UE parity")
    if dry_run:
        return {**summary, "dry_run": True, "how": "dry_run=false writes the conformed copy (the source is never touched)"}
    visibility = [(o.hide_viewport, o.hide_get()) for o in [ob, *meshes]]
    made = []
    try:
        new, copies = _copy(ob, name, meshes, suffix)
        made += [new, *copies]
        base, base_meshes = _copy(ob, f"{name}__baseline", meshes, f"__baseline_{name}")
        made += [base, *base_meshes]
        # The source is never revealed. Only disposable working copies must
        # participate in Edit Mode and depsgraph skin verification.
        for working in made:
            working.hide_viewport = False
            working.hide_set(False)
        bpy.context.view_layer.update()
        if not preserving:
            groups = [[g.name for g in c.vertex_groups] for c in copies]
            tmp = {old: f"lw_conform_tmp_{i}" for i, old in enumerate(rename)}
            for old in rename:                                  # two phases, so a rename never lands on a name still in use
                new.data.bones[old].name = tmp[old]
            for old, n in rename.items():
                new.data.bones[tmp[old]].name = n
            C.activate(new)
            bpy.ops.object.mode_set(mode="EDIT")
            ebs = new.data.edit_bones
            for b in plan["bones"]:
                if b["name"] not in ebs:
                    e = ebs.new(b["name"])
                    e.head, e.tail = b["head"], np.add(b["head"], (0.0, 0.0, max(b["length"], 1e-3)))
            for b in plan["bones"]:
                e = ebs[b["name"]]
                e.use_connect = False
                e.parent = ebs[b["parent"]] if b["parent"] else None
            for b in plan["bones"]:
                e = ebs[b["name"]]
                R = np.asarray(b["frame"], float)
                M = Matrix(((*R[0], b["head"][0]), (*R[1], b["head"][1]), (*R[2], b["head"][2]), (0, 0, 0, 1)))
                e.matrix = M
                e.length = max(b["length"], 1e-4)
            bpy.ops.object.mode_set(mode="OBJECT")
            for c, names in zip(copies, groups):                # the vertex groups follow their bones, by index (two phases)
                for i, g in enumerate(c.vertex_groups):
                    g.name = f"lw_conform_vg_{i}"
                for i, g in enumerate(c.vertex_groups):
                    g.name = rename.get(names[i], names[i])
        merged = {}
        for c in copies:
            for g, to in merge.items():
                src_g = c.vertex_groups.get(rename.get(g, g))
                if src_g is None:
                    continue
                dst = c.vertex_groups.get(to) or c.vertex_groups.new(name=to)
                n = 0
                for v in c.data.vertices:
                    for ge in v.groups:
                        if ge.group == src_g.index and ge.weight > 0:
                            dst.add([v.index], ge.weight, "ADD")
                            n += 1
                c.vertex_groups.remove(src_g)
                merged.setdefault(g, {"to": to, "vertices": 0})["vertices"] += n
        bpy.context.view_layer.update()
        # verify: heads that existed did not move (bit for bit), frames are the plan's
        moved = []
        for b in plan["bones"]:
            got = tuple(new.data.bones[b["name"]].head_local)
            if b["source"] is not None and max(abs(x - y) for x, y in zip(got, src["heads"][b["source"]])) > 1e-9:
                moved.append(b["name"])
        if moved:
            raise C.FeatureError(f"the frame rewrite moved the rest head of {', '.join(moved[:8])} (> 1e-9 m): rolled back")
        frame_errs = {b["name"]: RC.angle_deg(np.array(new.data.bones[b["name"]].matrix_local.to_3x3()), b["frame"]) for b in plan["bones"]}
        worst = max(frame_errs, key=frame_errs.get)
        frame_err = {"bone": worst, "deg": frame_errs[worst]}
        rest_new, rest_base = _evaluated(copies), _evaluated(base_meshes)
        drift = max((float(np.max(np.abs(a - b))) for a, b in zip(rest_new, rest_base) if len(a)), default=0.0)
        span = max((float(np.max(np.abs(a))) for a in rest_base if len(a)), default=1.0)
        bar = 1e-9 + float(np.finfo(np.float32).eps) * max(1.0, span) * 4
        if drift > bar:
            raise C.FeatureError(f"a vertex's rest position changed by {drift:.3g} m (> {bar:.3g}): rolled back")
        # the posed check: the same world pose on both rigs, keyed by the source bone
        srcs = sorted(rename)

        def delta(head, a):
            h = Matrix.Translation(head)
            return h @ Quaternion(POSE_AXIS, a).to_matrix().to_4x4() @ h.inverted()
        d_base = {s: delta(ob.data.bones[s].head_local, math.radians(10.0 + 7.0 * (k % 5))) for k, s in enumerate(srcs)}
        for g, to in merge.items():                     # a merged bone moves exactly as the bone it merged into: the skins agree
            back = next((s for s, n in rename.items() if n == to), None)
            if g in d_base and back in d_base:
                d_base[g] = d_base[back]
        d_new = {rename[s]: d_base[s] for s in srcs}
        _world_pose(base, d_base, _depth(base))
        _world_pose(new, d_new, _depth(new))
        posed_new, posed_base = _evaluated(copies), _evaluated(base_meshes)
        posed = max((float(np.max(np.abs(a - b))) for a, b in zip(posed_new, posed_base) if len(a)), default=0.0)
        for pb in new.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        bpy.context.view_layer.update()
        if posed > POSED_BAR_M:
            raise C.FeatureError(f"the conformed skin deforms differently under the same world pose ({posed:.3g} m > {POSED_BAR_M}): a vertex group "
                                 "did not follow its bone; rolled back")
    except Exception:
        _remove([o for o in made if o.name in bpy.data.objects])
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        raise
    _remove([base, *base_meshes])
    for output, (viewport, hidden) in zip([new, *copies], visibility):
        output.hide_viewport = viewport
        output.hide_set(hidden)
    out = {**summary, "dry_run": False, "meshes_out": [c.name for c in copies], "merged_groups": merged, "rest_vertex_drift_m": drift,
           "rest_bar_m": bar, "posed_skin_drift_m": posed, "posed_bar_m": POSED_BAR_M, "max_frame_error_deg": frame_err,
           "animation": "not carried: the copy has no action (rig_retarget or rig_convert carries motion across rest frames)",
           "help": [f"run lampway_rig_inspect armature={name} before the next rig tool"]}
    out["sha256"] = {**summary["sha256"], "output": RT._fingerprint(new, RT.read(new))}
    return out
