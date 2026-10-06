# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_rest_pose (specs/canon/rig_tools/rig_rest_pose.md; canon 19 B.7-B.8, canon 04): make a pose the rest of a COPY, once, and say what it
cost. Re-implemented from MB's documented helperT / PoseUE behaviour; their side effects (joining every skinned mesh, renaming every UV layer
UVMap, deleting actions without a fake user) are refused, and nothing is ported.

The copy armature (<armature><out_suffix>) takes the pose as its rest (Blender's Apply Pose as Rest on the copy); each skinned mesh is copied
(<mesh><out_suffix>, no join, UV layers untouched) and its vertices moved to v1 = LBS_P(v0) over the normalized deform weights (canon 04,
float64); each listed action is copied (<action><out_suffix>) with every key re-expressed by basis' = (rest'_local)^-1 rest_local basis - an
affine map of each channel group, applied to the keys AND their handles, so the copy plays exactly as the original between keys too
(quaternion bones; an Euler bone is resampled per frame and says so). The copy is stamped: its rest is never changed again (no chaining).
The receipt keeps the original rest's sha256 and states the return cost: the blend of inverses a naive return through the new bind would give,
against the exact inverse (R07: 12.5 mm on 46 vertices, against 0)."""

import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion

from . import common as C
from . import rig_tools as RT
from ..canon_geom.lbs import lbs as _lbs
from ..rig_tools import core as RC

STAMP = "lw_rest_pose"


def _np(M):
    return np.array([[M[r][c] for c in range(4)] for r in range(4)], float)


def _pose_bases(ob, pose, root):
    """{bone: matrix_basis (4x4 Matrix)} and the pose's sha256."""
    if pose == "reference":
        raise C.FeatureError("pose 'reference' (a profile's reference posture) is not built here: pass a pose.json (lampway.pose/1: {bone: "
                             "{matrix_basis}}) or action:<name>:<frame>")
    if pose.startswith("action:"):
        _a, name, frame = (pose.split(":") + ["", ""])[:3]
        act = bpy.data.actions.get(name)
        if act is None:
            raise C.FeatureError(f"pose {pose}: no action named {name!r}")
        ad = ob.animation_data_create()
        keep, keep_f = ad.action, bpy.context.scene.frame_current
        try:
            ad.action = act
            bpy.context.scene.frame_set(int(float(frame or act.frame_range[0])))
            bases = {pb.name: pb.matrix_basis.copy() for pb in ob.pose.bones}
        finally:
            ad.action = keep
            bpy.context.scene.frame_set(keep_f)
    else:
        p = Path(pose) if Path(pose).is_absolute() else Path(root, pose)
        if not p.is_file():
            raise C.FeatureError(f"no pose file at {p}: a lampway.pose/1 JSON, or action:<name>:<frame>")
        doc = json.loads(p.read_text())
        if doc.get("schema") != "lampway.pose/1":
            raise C.FeatureError(f"{p.name} is not a lampway.pose/1 pose")
        unknown = sorted(set(doc["bones"]) - set(ob.pose.bones.keys()))
        if unknown:
            raise C.FeatureError(f"{p.name} poses bones {ob.name} lacks: {', '.join(unknown[:10])}")
        bases = {pb.name: Matrix(doc["bones"][pb.name]["matrix_basis"]) if pb.name in doc["bones"] else Matrix.Identity(4) for pb in ob.pose.bones}
    return bases, RC.sha({n: np.round(_np(m), 9).tolist() for n, m in sorted(bases.items())})


def _weights(m, bones):
    names = [g.name for g in m.vertex_groups]
    cols = [b for b in bones if b in names]
    W = np.zeros((len(m.data.vertices), len(cols)))
    idx = {m.vertex_groups[b].index: k for k, b in enumerate(cols)}
    for v in m.data.vertices:
        for g in v.groups:
            if g.group in idx:
                W[v.index, idx[g.group]] = g.weight
    s = W.sum(axis=1, keepdims=True)
    return cols, np.divide(W, s, out=np.zeros_like(W), where=s > 0), (s[:, 0] > 0)


def _fc_groups(action, bone):
    out = {}
    for fc in RT._fcurves(action):
        if RT._bone_of(fc.data_path) == bone:
            out.setdefault(fc.data_path.rsplit(".", 1)[1], {})[fc.array_index] = fc
    return out


def _lmat(q):
    """The 4x4 that left-multiplies a (w, x, y, z) quaternion by q."""
    w, x, y, z = q
    return np.array([[w, -x, -y, -z], [x, w, -z, y], [y, z, w, -x], [z, -y, x, w]])


def _rewrite(src_act, new_act, arm, bone, K):
    """Copy one bone's channels into new_act with basis' = K basis: location t' = K_r t + K_t, quaternion q' = q_K q (linear in the components),
    scale unchanged; keys and handles mapped together, so the curves between keys map too. Returns the keyed frames."""
    groups = _fc_groups(src_act, bone)
    if not groups:
        return []
    pb = arm.pose.bones[bone]
    Kr, Kt = _np(K)[:3, :3], _np(K)[:3, 3]
    qK = np.array(K.to_quaternion())
    frames = sorted({k.co[0] for g in groups.values() for fc in g.values() for k in fc.keyframe_points})
    rot_path = "rotation_quaternion" if pb.rotation_mode == "QUATERNION" else None
    if pb.rotation_mode != "QUATERNION" and any(p.startswith("rotation") for p in groups):
        raise C.FeatureError(f"{bone} keys {pb.rotation_mode} rotations: re-expressing them is exact for quaternion bones only; set its rotation "
                             "mode to QUATERNION (and re-key) first")
    plans = []
    if "location" in groups:
        plans.append(("location", 3, np.zeros(3), lambda V: V @ Kr.T + Kt))
    if rot_path in groups:
        plans.append((rot_path, 4, np.array([1.0, 0, 0, 0]), lambda V: V @ _lmat(qK).T))
    if "scale" in groups:
        plans.append(("scale", 3, np.ones(3), lambda V: V))
    for path, n, default, fn in plans:
        g = groups[path]
        same = all(i in g for i in range(n)) and len({tuple(round(k.co[0], 6) for k in g[i].keyframe_points) for i in range(n)}) == 1
        if same:
            ref = g[0].keyframe_points
            co = np.array([[g[i].keyframe_points[j].co[1] for i in range(n)] for j in range(len(ref))])
            hl = np.array([[g[i].keyframe_points[j].handle_left[1] for i in range(n)] for j in range(len(ref))])
            hr = np.array([[g[i].keyframe_points[j].handle_right[1] for i in range(n)] for j in range(len(ref))])
            nco, nhl, nhr = fn(co), fn(hl), fn(hr)
            for i in range(n):
                fc = new_act.fcurve_ensure_for_datablock(arm, f'pose.bones["{bone}"].{path}', index=i)
                fc.keyframe_points.add(len(ref))
                for j, k in enumerate(fc.keyframe_points):
                    src = g[i].keyframe_points[j]
                    k.interpolation, k.easing = src.interpolation, src.easing
                    k.handle_left_type = k.handle_right_type = "FREE"
                    k.co = (src.co[0], nco[j, i])
                    k.handle_left = (src.handle_left[0], nhl[j, i])
                    k.handle_right = (src.handle_right[0], nhr[j, i])
                fc.update()
        else:                                                 # components keyed apart: resampled on the union of their frames, linear
            vals = np.array([[g[i].evaluate(f) if i in g else default[i] for i in range(n)] for f in frames])
            out = fn(vals)
            for i in range(n):
                fc = new_act.fcurve_ensure_for_datablock(arm, f'pose.bones["{bone}"].{path}', index=i)
                fc.keyframe_points.add(len(frames))
                fc.keyframe_points.foreach_set("co", [x for f, v in zip(frames, out[:, i]) for x in (f, v)])
                for k in fc.keyframe_points:
                    k.interpolation = "LINEAR"
                fc.update()
    return frames


def rest_pose(armature, pose, root, meshes=None, actions="all", keep_original=True, out_suffix="_rest2", dry_run=True):
    ob = RT._armature(armature)
    RT._inspected(ob)
    if ob.get(STAMP):
        prev = json.loads(ob[STAMP])
        raise C.FeatureError(f"{ob.name}'s rest was already changed by rig_rest_pose (from {prev['original']}): rests never chain; return "
                             f"through the original {prev['original']} first")
    if not keep_original:
        raise C.FeatureError("keep_original=false is refused: the outputs are copies (<name><out_suffix>) and the original rest is the return path")
    S = np.array(ob.scale)
    if np.ptp(S) > 1e-9 * max(1.0, float(abs(S).max())):
        raise C.FeatureError(f"{ob.name} has a non-uniform scale {list(S)}: run lampway_rig_normalize (canon 18) first")
    mesh_obs = [C.need_object(n, "MESH") for n in meshes] if meshes else \
        [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object is ob for m in o.modifiers)]
    keyed = sorted(o.name for o in mesh_obs if o.data.shape_keys)
    if keyed:
        raise C.FeatureError(f"{', '.join(keyed)} carry shape keys: each would need re-baking through the same LBS; refused until requested")
    if actions == "all":
        acts = [a for a in bpy.data.actions if any((RT._bone_of(fc.data_path) or "") in ob.data.bones for fc in RT._fcurves(a))]
    else:
        acts = [bpy.data.actions.get(a) for a in actions]
    if None in acts:
        raise C.FeatureError(f"no action named {actions[acts.index(None)]!r}")
    bases, pose_sha = _pose_bases(ob, pose, root)
    names = [f"{ob.name}{out_suffix}"] + [f"{m.name}{out_suffix}" for m in mesh_obs]
    clash = sorted(n for n in names if n in bpy.data.objects) + sorted(f"{a.name}{out_suffix}" for a in acts if f"{a.name}{out_suffix}" in bpy.data.actions)
    if clash:
        raise C.FeatureError(f"{', '.join(clash)} already exist: pass another out_suffix")
    original_sha = RT._fingerprint(ob, RT.read(ob))
    plan = {"armature": ob.name, "armature_out": names[0], "meshes": [m.name for m in mesh_obs], "actions": [a.name for a in acts],
            "pose": pose, "pose_sha256": pose_sha, "original_rest_sha256": original_sha}
    if dry_run:
        return {**plan, "dry_run": True}
    new = ob.copy()
    new.data = ob.data.copy()
    new.name = new.data.name = names[0]
    new.animation_data_clear()
    for coll in ob.users_collection or [bpy.context.scene.collection]:
        coll.objects.link(new)
    made = [new]
    try:
        for pb in new.pose.bones:
            pb.matrix_basis = bases[pb.name]
        bpy.context.view_layer.update()
        R = {b.name: b.matrix_local.copy() for b in new.data.bones}
        Mpose = {pb.name: pb.matrix.copy() for pb in new.pose.bones}
        deform = [b.name for b in new.data.bones if b.use_deform]
        D = {n: _np(Mpose[n] @ R[n].inverted()) for n in deform}
        out_meshes, costs, v1s = {}, {}, {}
        amw, amw_inv = _np(new.matrix_world), np.linalg.inv(_np(new.matrix_world))
        for m in mesh_obs:
            cols, W, weighted = _weights(m, deform)
            mw = _np(m.matrix_world)
            co = np.array([v.co for v in m.data.vertices], float)
            a0 = (np.c_[co, np.ones(len(co))] @ (amw_inv @ mw).T)[:, :3]          # armature space
            mats = np.array([D[c] for c in cols]) if cols else np.zeros((0, 4, 4))
            a1 = _lbs(a0, W, mats) if cols else a0.copy()
            a1[~weighted] = a0[~weighted]
            v1 = (np.c_[a1, np.ones(len(a1))] @ (np.linalg.inv(mw) @ amw).T)[:, :3]
            costs[m.name] = RC.return_cost(a1[weighted], a0[weighted], W[weighted], mats) if weighted.any() and cols else \
                {"blend_of_inverses_max_m": 0.0, "vertices_over_1mm": 0, "exact_return_max_m": 0.0, "rigid_vertices_error_m": 0.0}
            v1s[m.name] = v1
            out_meshes[m.name] = {"out": f"{m.name}{out_suffix}", "moved_max_m": float(np.linalg.norm(a1 - a0, axis=1).max()) if len(a0) else 0.0}
        C.activate(new)
        bpy.ops.object.mode_set(mode="POSE")
        bpy.ops.pose.armature_apply(selected=False)
        bpy.ops.object.mode_set(mode="OBJECT")
        for pb in new.pose.bones:
            pb.matrix_basis = Matrix.Identity(4)
        R2 = {b.name: b.matrix_local.copy() for b in new.data.bones}
        for m in mesh_obs:
            c = m.copy()
            c.data = m.data.copy()
            c.name = c.data.name = f"{m.name}{out_suffix}"
            c.animation_data_clear()
            for coll in m.users_collection or [bpy.context.scene.collection]:
                coll.objects.link(c)
            made.append(c)
            c.data.vertices.foreach_set("co", v1s[m.name].astype(np.float32).ravel())
            c.data.update()
            for mod in c.modifiers:
                if mod.type == "ARMATURE" and mod.object is ob:
                    mod.object = new
            if c.parent is ob:
                c.parent = new
        rewritten = []
        nad = new.animation_data_create()
        for a in acts:
            na = bpy.data.actions.new(f"{a.name}{out_suffix}")
            nad.action = na
            frames = set()
            for b in new.data.bones:
                p = b.parent.name if b.parent else None
                rest_local = (R[p].inverted() @ R[b.name]) if p else R[b.name]
                rest2_local = (R2[p].inverted() @ R2[b.name]) if p else R2[b.name]
                frames |= set(_rewrite(a, na, new, b.name, rest2_local.inverted() @ rest_local))
            rewritten.append({"source": a.name, "out": na.name, "frames": sorted(frames)})
        nad.action = None
        bpy.context.view_layer.update()
    except Exception:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        for o in made:
            data = o.data
            bpy.data.objects.remove(o)
            if data is not None and data.users == 0:
                (bpy.data.armatures if isinstance(data, bpy.types.Armature) else bpy.data.meshes).remove(data)
        raise
    new_sha = RT._fingerprint(new, RT.read(new))
    new[STAMP] = json.dumps({"original": ob.name, "original_rest_sha256": original_sha, "pose_sha256": pose_sha})
    return {**plan, "dry_run": False, "new_rest_sha256": new_sha, "meshes": out_meshes, "actions_rewritten": rewritten, "return_cost": costs,
            "help": [f"run lampway_rig_inspect armature={new.name} before the next rig tool",
                     f"to return, use the original {ob.name} (kept); a return through the new bind costs the blend of inverses above"]}
