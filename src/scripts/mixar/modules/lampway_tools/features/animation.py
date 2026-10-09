# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""animation_retarget: bake an animation from one skeleton onto another, the rest pose compensated, and measure the result.

Per mapped bone pair the target's world rotation is  W = Ws * Rs_rest^-1 * Rt_rest  (the source bone's world rotation at the frame, undone from its own rest and applied to the target's rest): a source
bone that turns by D in the world turns the target bone by the same D whatever the two rests are. Parents are solved first, so each bone's local key is exact. The root follows the source's travel scaled
by the pelvis-height ratio. method='constraints' is the Copy Rotation + NLA bake route (it does NOT compensate a different rest pose: the falsifier of the tests). Bone names are read by pipeline/anim_labels.py."""

import hashlib
import json
import math
import os

import bpy

from .. import canon_io
import numpy as np
from mathutils import Matrix, Vector

from ..pipeline import anim_labels as LB
from . import common as C

REQUIRED = [("pelvis", None), ("spine", None), ("head", None)] + [(b, s) for b in ("upperarm", "lowerarm", "hand", "thigh", "calf", "foot") for s in ("l", "r")]
RANK = ("spine", "neck")
STANCE_M = 0.015


def _depth(b):
    d = 0
    while b.parent:
        b, d = b.parent, d + 1
    return d


def _labelled(arm):
    out = {}
    for b in arm.data.bones:
        lab = LB.label(b.name)
        if lab is not None:
            out.setdefault((lab[0], lab[1], lab[2]), []).append(b)
    return out


def build_mapping(src, tgt):
    """[{source, target, mode, label, by}], unmapped_src, unmapped_dst. Exact names first, then (label, side, number); spine and neck pair by rank from the bottom."""
    sn, tn = {b.name: b for b in src.data.bones}, {b.name: b for b in tgt.data.bones}
    pairs, used_s, used_t = [], set(), set()
    for name in sn:
        if name in tn and LB.label(name) is not None:
            lab = LB.label(name)
            pairs.append({"source": name, "target": name, "label": "_".join(str(x) for x in lab[:2] if x), "by": "exact"})
            used_s.add(name), used_t.add(name)
    def groups(arm, used):
        g = {}
        for b in arm.data.bones:
            lab = LB.label(b.name)
            if lab is None or b.name in used:
                continue
            g.setdefault((lab[0], lab[1]), []).append((lab[2] if lab[2] is not None else 0, _depth(b), b.name))
        return {k: [n for _a, _d, n in sorted(v, key=lambda x: (x[1], x[0]))] for k, v in g.items()}
    gs, gt = groups(src, used_s), groups(tgt, used_t)
    for key in sorted(set(gs) & set(gt), key=str):
        for s_name, t_name in zip(gs[key], gt[key]) if key[0] in RANK or key[0].startswith("finger_") else [(gs[key][0], gt[key][0])]:
            pairs.append({"source": s_name, "target": t_name, "label": "_".join(str(x) for x in key if x), "by": "label"})
            used_s.add(s_name), used_t.add(t_name)
    for p in pairs:
        p["mode"] = "transform" if p["label"] == "pelvis" else "rotation"
    return pairs, sorted(set(sn) - used_s), sorted(set(tn) - used_t)


def _required_missing(pairs, src, tgt):
    # Only a terminal l/r is a side. Neck, root and other unsided labels
    # still occur in valid auto mappings even though they are not required.
    have = set()
    for pair in pairs:
        parts = pair["label"].rsplit("_", 1)
        have.add((parts[0], parts[1]) if len(parts) == 2 and parts[1] in ("l", "r") else (pair["label"], None))
    missing = []
    for lab, side in REQUIRED:
        if (lab, side) not in have:
            missing.append(lab + (f"_{side}" if side else ""))
    return missing


def _rest_sha(arm):
    rows = [[b.name] + [round(float(x), 5) for r in (arm.matrix_world @ b.matrix_local) for x in r] for b in arm.data.bones]
    return hashlib.sha256(json.dumps(rows).encode()).hexdigest()


def _import(path, root):
    full = os.path.realpath(path if os.path.isabs(path) else os.path.join(root, path))
    if root and not (full == os.path.realpath(root) or full.startswith(os.path.realpath(root) + os.sep)):
        raise C.FeatureError(f"{path} is outside the project root {root}")
    if not os.path.isfile(full):
        raise C.FeatureError(f"{path} is not a file")
    before, actions = set(bpy.data.objects), set(bpy.data.actions)
    ext = os.path.splitext(full)[1].lower()
    if ext == ".fbx":
        canon_io.import_raw(full, ignore_leaf_bones=False)
    elif ext == ".bvh":
        canon_io.import_raw(full)
    elif ext in (".glb", ".gltf"):
        canon_io.import_raw(full, guess_original_bind_pose=False)
    else:
        raise C.FeatureError("sources are .fbx, .bvh, .glb/.gltf or an armature in the scene")
    new = [o for o in bpy.data.objects if o not in before]
    arms = [o for o in new if o.type == "ARMATURE"]
    if not arms:
        raise C.FeatureError(f"{path} holds no armature")
    col = bpy.data.collections.new("lw_retarget_src")
    bpy.context.scene.collection.children.link(col)
    for o in new:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    bpy.context.view_layer.layer_collection.children["lw_retarget_src"].hide_viewport = True
    return arms[0], new, [a for a in bpy.data.actions if a not in actions], col


def _drives(act, arm):
    names = {b.name for b in arm.data.bones}
    paths = []
    if hasattr(act, "fcurves"):
        paths = [fc.data_path for fc in act.fcurves]
    else:
        for layer in getattr(act, "layers", []):
            for strip in layer.strips:
                for cb in strip.channelbags:
                    paths += [fc.data_path for fc in cb.fcurves]
    return any(any(f'pose.bones["{n}"]' in p for n in names) for p in paths)


def _angle(m1, m2):
    angle = math.degrees(m1.to_quaternion().rotation_difference(m2.to_quaternion()).angle) % 360.0
    return min(angle, 360.0 - angle)


@canon_io.rollback_imports
def retarget(source, target, action=None, mapping="auto", method="matrix", root_motion="keep", scale="auto", frame_range=None, fps=None, check_objects=None,
             sample_frames=8, name=None, dry_run=False, root="", keep_source=False):
    if method not in ("matrix", "constraints"):
        raise C.FeatureError("method is matrix | constraints")
    if root_motion not in ("keep", "in_place"):
        raise C.FeatureError("root_motion is keep | in_place")
    if scale != "auto" and not (0.01 <= float(scale) <= 100):
        raise C.FeatureError("scale must be between 0.01 and 100")
    if not 2 <= int(sample_frames) <= 64:
        raise C.FeatureError("sample_frames is between 2 and 64")
    if fps is not None and not 1 <= float(fps) <= 120:
        raise C.FeatureError("fps is between 1 and 120")
    tgt = C.need_object(target, "ARMATURE")
    if not tgt.pose.bones:
        raise C.FeatureError(f"target {target} has no pose bones")
    imported, imp_actions, imp_col = [], [], None
    sc = bpy.context.scene
    if bpy.data.objects.get(source) is not None:
        src = C.need_object(source, "ARMATURE")
    else:
        src, imported, imp_actions, imp_col = _import(source, root)
    try:
        return _retarget(src, tgt, action, mapping, method, root_motion, scale, frame_range, fps, check_objects or [], int(sample_frames), name, dry_run, root, sc)
    finally:
        if imported and not keep_source:
            for o in imported:
                bpy.data.objects.remove(o)
            for a in imp_actions:
                bpy.data.actions.remove(a)
            bpy.data.collections.remove(imp_col)


def _retarget(src, tgt, action, mapping, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, dry_run, root, sc):
    if isinstance(mapping, list):
        pairs = [{"source": m["source"], "target": m["target"], "label": (LB.label(m["target"]) or ("x", None))[0] + ("_" + LB.label(m["target"])[1] if LB.label(m["target"]) and LB.label(m["target"])[1] else ""),
                  "by": "given", "mode": m.get("mode", "rotation")} for m in mapping if m.get("mode") != "none"]
        unmapped_s = sorted({b.name for b in src.data.bones} - {p["source"] for p in pairs})
        unmapped_t = sorted({b.name for b in tgt.data.bones} - {p["target"] for p in pairs})
        missing = []
    else:
        if mapping not in ("auto", None):
            path = os.path.join(root, "anim", "presets", f"{mapping}.json")
            if not os.path.isfile(path):
                raise C.FeatureError(f"no mapping preset {mapping!r} (looked in anim/presets/)")
            return _retarget(src, tgt, action, json.load(open(path)), method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, dry_run, root, sc)
        pairs, unmapped_s, unmapped_t = build_mapping(src, tgt)
        missing = _required_missing(pairs, src, tgt)
    for p in pairs:
        p.setdefault("mode", "rotation")
    if missing:
        return {"ok": False, "error": f"target {tgt.name} lacks {missing} (or the source does): run lampway_auto_rig or pass mapping; nothing was baked", "unmapped_required": missing,
                "mapping": pairs, "unmapped_source": unmapped_s, "unmapped_target": unmapped_t}
    if dry_run:
        return {"ok": True, "dry_run": True, "mapping": pairs, "unmapped_required": [], "unmapped_source": unmapped_s, "unmapped_target": unmapped_t}
    for obj_name in check_objects:
        obj = C.need_object(obj_name, "MESH")
        rigs = [m.object for m in obj.modifiers if m.type == "ARMATURE" and m.show_viewport and m.object]
        if rigs != [tgt]:
            raise C.FeatureError(f"check_objects {obj.name} must be bound only to target {tgt.name}; inspect its Armature modifier before measuring skin")
    # ---- the action(s)
    if action == "all":
        acts = [a for a in bpy.data.actions if _drives(a, src)]
        if not acts:
            raise C.FeatureError(f"source {src.name} has no animation: pass action= or import a clip")
        return {"ok": True, "results": [_bake(src, tgt, a, pairs, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, root, sc, unmapped_s, unmapped_t) for a in acts]}
    act = bpy.data.actions.get(action) if action else (src.animation_data.action if src.animation_data else None)
    if act is None:
        raise C.FeatureError(f"source {src.name} has no animation: pass action= or import a clip")
    return _bake(src, tgt, act, pairs, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, root, sc, unmapped_s, unmapped_t)


def _bake(src, tgt, act, pairs, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, root, sc, unmapped_s, unmapped_t):
    # Sampling another action is temporary; preserve the original owner slot,
    # unkeyed pose values and exact scene time on success and failure.
    ad = src.animation_data
    previous_action = ad.action if ad else None
    previous_slot = ad.action_slot if ad and hasattr(ad, "action_slot") else None
    channels = ("location", "rotation_quaternion", "rotation_euler", "rotation_axis_angle", "scale")
    pose = {b.name: (b.rotation_mode, {key: tuple(getattr(b, key)) for key in channels}) for b in src.pose.bones}
    previous_time = (sc.frame_current, sc.frame_subframe)
    try:
        return _bake_impl(src, tgt, act, pairs, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, root, sc, unmapped_s, unmapped_t)
    finally:
        if src.animation_data:
            src.animation_data.action = previous_action
            if previous_action and previous_slot is not None:
                src.animation_data.action_slot = previous_slot
        sc.frame_set(previous_time[0], subframe=previous_time[1])
        for bone in src.pose.bones:
            mode, values = pose[bone.name]
            bone.rotation_mode = mode
            for key, value in values.items():
                setattr(bone, key, value)
        bpy.context.view_layer.update()


def _bake_impl(src, tgt, act, pairs, method, root_motion, scale, frame_range, fps, check_objects, sample_frames, name, root, sc, unmapped_s, unmapped_t):
    sad = src.animation_data_create()
    prev_src_action = sad.action
    from .rig_export_space import _action_slot
    slot_handle = _action_slot(src, act) if hasattr(act, "slots") else None
    sad.action = act
    if slot_handle is not None:
        sad.action_slot = next(slot for slot in act.slots if slot.handle == slot_handle)
    tad = tgt.animation_data_create()
    prev_tgt_action = tad.action.name if tad.action else None
    f0, f1 = (int(frame_range[0]), int(frame_range[1])) if frame_range else (int(math.floor(act.frame_range[0])), int(math.ceil(act.frame_range[1])))
    if f1 <= f0:
        f1 = f0 + 1
    scene_fps = sc.render.fps
    step = (scene_fps / float(fps)) if fps else 1.0
    times = [f0 + i * step for i in range(int(math.floor((f1 - f0) / step + 1e-9)) + 1)]
    smap = {b.name: b for b in src.data.bones}
    tmap = {b.name: b for b in tgt.data.bones}
    Rs = {p["source"]: (src.matrix_world.to_3x3().normalized() @ smap[p["source"]].matrix_local.to_3x3()).normalized() for p in pairs}
    Rt = {p["target"]: (tgt.matrix_world.to_3x3().normalized() @ tmap[p["target"]].matrix_local.to_3x3()).normalized() for p in pairs}
    rest_diff = [_angle(Rs[p["source"]], Rt[p["target"]]) for p in pairs]
    pel = next((p for p in pairs if p["mode"] == "transform"), None)
    if scale == "auto":
        hs = (src.matrix_world @ smap[pel["source"]].matrix_local).translation.z if pel else 1.0
        ht = (tgt.matrix_world @ tmap[pel["target"]].matrix_local).translation.z if pel else 1.0
        root_scale = ht / hs if abs(hs) > 1e-9 else 1.0
    else:
        root_scale = float(scale)
    src_rest_head = (src.matrix_world @ smap[pel["source"]].matrix_local).translation.copy() if pel else None
    tgt_rest_head = (tgt.matrix_world @ tmap[pel["target"]].matrix_local).translation.copy() if pel else None
    order = sorted(tgt.data.bones, key=_depth)
    Atinv = tgt.matrix_world.inverted()
    At3 = tgt.matrix_world.to_3x3().normalized()
    by_target = {p["target"]: p for p in pairs}
    keys, expected, foot_pos = [], [], {}
    for t in times:
        sc.frame_set(int(math.floor(t)), subframe=t - math.floor(t))
        W = {}
        for p in pairs:
            Ws = (src.matrix_world @ src.pose.bones[p["source"]].matrix).to_3x3().normalized()
            W[p["target"]] = (Ws @ Rs[p["source"]].inverted() @ Rt[p["target"]]).normalized()
        expected.append(W)
        if method != "matrix":
            continue
        desired_root = None
        if pel:
            sh = (src.matrix_world @ src.pose.bones[pel["source"]].matrix).translation
            delta = (sh - src_rest_head) * root_scale
            if root_motion == "in_place":
                delta.x = delta.y = 0.0
            desired_root = tgt_rest_head + delta
        M, row = {}, {}
        for b in order:
            if b.parent:
                base = M[b.parent.name] @ (b.parent.matrix_local.inverted() @ b.matrix_local)
            else:
                base = b.matrix_local.copy()
            p = by_target.get(b.name)
            if p is None:
                M[b.name] = base
                continue
            trans = base.translation.copy()
            if p["mode"] == "transform" and desired_root is not None:
                trans = Atinv @ desired_root
            want = Matrix.Translation(trans) @ (At3.inverted() @ W[b.name]).to_4x4()
            basis = base.inverted() @ want
            loc, quat, _s = basis.decompose()
            M[b.name] = want
            row[b.name] = (loc, quat)
        keys.append((t, row))
        for p in pairs:
            if p["label"] in ("foot_l", "foot_r"):
                foot_pos.setdefault(p["label"], []).append(tgt.matrix_world @ M[p["target"]].translation)
    out_name = name or f"{act.name}_rt"
    new_act = None
    if method == "matrix":
        new_act = bpy.data.actions.new(out_name)
        tad.action = new_act
        for b in tgt.pose.bones:
            b.rotation_mode = "QUATERNION"
        for i, (t, row) in enumerate(keys):
            frame = f0 + i
            for bone, (loc, quat) in row.items():
                pb = tgt.pose.bones[bone]
                pb.rotation_quaternion = quat
                pb.keyframe_insert("rotation_quaternion", frame=frame)
                if by_target[bone]["mode"] == "transform":
                    pb.location = loc
                    pb.keyframe_insert("location", frame=frame)
        for b in tgt.pose.bones:
            b.rotation_quaternion, b.location = (1, 0, 0, 0), (0, 0, 0)
    else:
        for p in pairs:
            pb = tgt.pose.bones[p["target"]]
            c = pb.constraints.new("COPY_ROTATION")
            c.target, c.subtarget, c.target_space, c.owner_space = src, p["source"], "WORLD", "WORLD"
        for o in bpy.context.selected_objects:
            o.select_set(False)
        bpy.context.view_layer.objects.active = tgt
        tgt.select_set(True)
        bpy.ops.nla.bake(frame_start=f0, frame_end=f1, step=1, only_selected=False, visual_keying=True, clear_constraints=True, use_current_action=False, bake_types={"POSE"})
        new_act = tad.action
        new_act.name = out_name
    # ---- measure what was baked
    frames_idx = sorted({int(round(x)) for x in np.linspace(0, len(times) - 1, int(sample_frames))})
    errs = []
    stretch = {}
    objs = [C.need_object(o) for o in check_objects]
    rest_geo = {}
    if objs:
        from . import rig as _R
        # Removing an action leaves its last evaluated pose in RNA. Use the
        # armature's actual REST evaluation, retaining action/pose state.
        previous_pose_position = tgt.data.pose_position
        try:
            tgt.data.pose_position = "REST"
            bpy.context.view_layer.update()
            for o in objs:
                me = o.data
                edges = np.empty(len(me.edges) * 2, dtype=np.int64)
                me.edges.foreach_get("vertices", edges)
                rest_geo[o.name] = (edges.reshape(-1, 2), _R._evaluated(o))
        finally:
            tgt.data.pose_position = previous_pose_position
            bpy.context.view_layer.update()
    for i in frames_idx:
        sc.frame_set(int(round(f0 + i)))
        for p in pairs:
            got = (tgt.matrix_world @ tgt.pose.bones[p["target"]].matrix).to_3x3().normalized()
            errs.append(_angle(got, expected[i][p["target"]]))
        for o in objs:
            from . import rig as _R
            edges, rest = rest_geo[o.name]
            cur = _R._evaluated(o)
            rl = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
            cl = np.linalg.norm(cur[edges[:, 0]] - cur[edges[:, 1]], axis=1)
            keep = rl > 1e-9
            stretch[o.name] = max(stretch.get(o.name, 1.0), round(float((cl[keep] / rl[keep]).max()), 6) if keep.any() else 1.0)
    slide = 0.0
    if foot_pos:
        for pts in foot_pos.values():
            z = np.array([p.z for p in pts])
            xy = np.array([[p.x, p.y] for p in pts])
            stance = z <= z.min() + STANCE_M
            start = None
            for j, s in enumerate(list(stance) + [False]):
                if s and start is None:
                    start = j
                if not s and start is not None:
                    if j - start >= 2:
                        slide = max(slide, float(np.linalg.norm(xy[start:j] - xy[start], axis=1).max()))
                    start = None
    sad.action = prev_src_action
    if fps:
        sc.render.fps = int(fps)
    mapping_rows = [{k: p[k] for k in ("source", "target", "mode", "label", "by")} for p in pairs]
    result = {"ok": True, "target": tgt.name, "action": new_act.name, "frames": [f0, f0 + len(times) - 1], "fps": int(fps) if fps else scene_fps, "method": method, "mapping": mapping_rows,
              "unmapped_required": [], "unmapped_source": unmapped_s, "unmapped_target": unmapped_t, "root_scale": round(root_scale, 6), "previous_target_action": prev_tgt_action,
              "rest_pose_difference_deg": {"max": round(max(rest_diff), 3), "mean": round(sum(rest_diff) / len(rest_diff), 3)},
              "metrics": {"max_world_angle_error_deg": round(max(errs), 4), "mean_world_angle_error_deg": round(sum(errs) / len(errs), 4), "foot_slide_m": round(slide, 5), "max_edge_stretch": stretch}}
    from ..pipeline import anim_gates as AG
    slide_limit = AG.THRESHOLDS["G-FOOT-SLIDE"] / 100.0
    warnings = []
    if root_motion == "in_place":
        foot_status = "unmeasured_world_contact"
        warnings.append("root_motion=in_place removes horizontal travel: foot_slide_m measures treadmill displacement, not world contact. Use root_motion=keep and lampway_anim_check with the clip's floor/contact evidence before judging foot plant.")
    else:
        foot_status = "proposed_threshold_exceeded" if slide > slide_limit else "diagnostic_only"
        if slide > slide_limit:
            warnings.append(f"Foot displacement {slide:.5f} m exceeds the existing proposed G-FOOT-SLIDE {slide_limit:.3f} m diagnostic. Review source/target stance, alignment and root scale with lampway_anim_check; this relative-height sample does not certify contact.")
    weighted_unmapped = {}
    for o in objs:
        names = {g.index: g.name for g in o.vertex_groups if g.name in unmapped_t}
        used = sorted({names[g.group] for v in o.data.vertices for g in v.groups if g.weight > 0 and g.group in names})
        if used:
            weighted_unmapped[o.name] = used
    if weighted_unmapped:
        warnings.append("Checked skin has weighted target bones omitted by the mapping. These bones inherit parent motion, which can be valid; omission alone does not establish the cause of skin distortion. Audit the target binding and authored weights before changing the supplied mapping.")
    if stretch:
        warnings.append("max_edge_stretch is measured against the target's evaluated REST mesh. Inspect skin weights and unmapped weighted bones in representative rendered frames; Run lampway_weight_audit on the checked target skin before any copy-only weight cleanup; no accepted stretch threshold or physical skin approval is established by this bake.")
    if not objs:
        warnings.append("Skin deformation was not checked: supply check_objects bound to the target and inspect representative rendered frames.")
    result["quality"] = {"accepted": False, "status": "review_required", "foot_slide": {"space": root_motion, "status": foot_status, "threshold_m": slide_limit, "threshold_status": "proposed", "stance_reference": "clip_minimum_height"},
                         "unmapped_weighted_target": weighted_unmapped, "skin_checked": [o.name for o in objs], "skin_cause": "unestablished", "stretch_reference": "evaluated_target_rest", "stretch_threshold": None,
                         "next_steps": [{"tool": "lampway_weight_audit", "next_args": {"action": "audit", "object": o.name, "armature": tgt.name}} for o in objs],
                         "candidate_next_steps": [{"tool": "lampway_weight_cleanup", "next_args": {"object": o.name, "armature": tgt.name, "ops": [{"op": "smooth", "iterations": 2, "factor": 0.5}]},
                             "review_required": True, "scope": "optional graph-smoothing preview on a new copy; select a reviewed flexible region before repair, preserve rigid roles; not a positional seam-band repair or motion acceptance"} for o in objs]}
    result["warnings"] = warnings
    if result["rest_pose_difference_deg"]["max"] > 5 and method == "constraints":
        result["warning"] = f"the rests differ by up to {result['rest_pose_difference_deg']['max']} deg and method=constraints does not compensate them: use method=matrix"
    out_dir = os.path.join(root, "anim") if root else "anim"
    os.makedirs(os.path.join(out_dir, "presets"), exist_ok=True)
    rj = os.path.join(out_dir, f"{new_act.name}.retarget.json")
    with open(rj, "w") as f:
        json.dump({**result, "parameters": {"root_motion": root_motion, "scale": scale, "frame_range": frame_range, "fps": fps}, "rest_sha256": {"source": _rest_sha(src), "target": _rest_sha(tgt)}}, f, indent=1, sort_keys=True)
    with open(os.path.join(out_dir, "presets", f"{src.name}__{tgt.name}.json"), "w") as f:
        json.dump(mapping_rows, f, indent=1)
    result["retarget_json"] = rj
    return result
