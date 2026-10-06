# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""clip_classify (specs/mrmak/08-clip-classify.md): what kind of motion is this clip, what should it be called, does it loop. Measured, never guessed.

The pure layer (pipeline/clip_features.py, Apache-2.0 translation) holds the vector, the table, the loop rule and the naming. THIS module is the Blender sampling layer: for each action it sets the action on the
armature, steps ``samples`` evenly spaced times across the key range, reads six landmark bones' WORLD head positions (converted to the upstream Y-up convention), the per-sample joint-scale delta and the
first-to-last pose return, and restores the frame, the action and the pose. Duration is in SECONDS ((last - first) / fps): the same keyed motion at another fps changes speed by the fps ratio."""

import math
import re

import bpy

from ..pipeline import clip_features as CF
from . import common as C

LANDMARK_NAMES = {"hip": ("pelvis", "hips", "hip"), "head": ("head",), "hand.l": ("handl", "lefthand"), "hand.r": ("handr", "righthand"), "foot.l": ("footl", "leftfoot"), "foot.r": ("footr", "rightfoot")}
PROVENANCE = "single-subject (11 clips, one rig, H = 1.0), Apache-2.0 img2threejs: confirm the gaps on a second rig before trusting them"
LEGACY_LOOP_DEGREES = 1.0       # anim_loop_export's G-LOOP; unverified, like upstream's 0.5: both are reported, neither chosen here


def _norm(name):
    return re.sub(r"[^a-z0-9]", "", name.lower()).replace("mixamorig", "")


def resolve_landmarks(arm, given=None):
    bones = {b.name: b for b in arm.data.bones}
    out = {}
    for lm in CF.REQUIRED_LANDMARKS:
        if given and lm in given:
            if given[lm] not in bones:
                raise C.FeatureError(f"landmark {lm} is not a bone of {arm.name}: pass landmarks to map it; all six are required, a range over the joints that happened to exist is not measured")
            out[lm] = given[lm]
            continue
        hit = next((n for n in bones if _norm(n) in LANDMARK_NAMES[lm]), None)
        if hit is None:
            raise C.FeatureError(f"landmark {lm} is not a bone of {arm.name}: pass landmarks to map it; all six are required, a range over the joints that happened to exist is not measured")
        out[lm] = hit
    return out


def _fcurve_paths(act):
    if hasattr(act, "fcurves"):
        return [fc.data_path for fc in act.fcurves]
    paths = []
    for layer in getattr(act, "layers", []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                paths += [fc.data_path for fc in cb.fcurves]
    return paths


def _drives(act, arm):
    paths = _fcurve_paths(act)
    return any(f'pose.bones["{b.name}"]' in p for b in arm.data.bones for p in paths)


def _snake(d, rename=None):
    """The upstream dict is camelCase (kept for fidelity); the contract's outputs (section 5) are snake_case."""
    out = {}
    for k, v in d.items():
        k2 = (rename or {}).get(k) or re.sub(r"([A-Z])", lambda m: "_" + m.group(1).lower(), k)
        out[k2] = {n: list(a) for n, a in v.items()} if k == "landmarkRanges" else v
    return out


def _y_up(v):
    return (float(v[0]), float(v[2]), -float(v[1]))


def _figure_height(arm, landmarks, given):
    if given is not None:
        if not (math.isfinite(float(given)) and float(given) > 0):
            raise C.FeatureError("figure_height_m must be a finite positive number")
        return float(given), "given"
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object == arm for m in o.modifiers)]
    if meshes:
        prev = arm.data.pose_position
        arm.data.pose_position = "REST"
        try:
            bpy.context.view_layer.update()
            dg = bpy.context.evaluated_depsgraph_get()
            zs = []
            for m in meshes:
                ev = m.evaluated_get(dg)
                zs += [(ev.matrix_world @ v.co).z for v in ev.data.vertices]
        finally:
            arm.data.pose_position = prev
            bpy.context.view_layer.update()
        if zs and max(zs) - min(zs) > 1e-6:
            return max(zs) - min(zs), "deform mesh rest bounding height"
    prev = arm.data.pose_position
    arm.data.pose_position = "REST"
    try:
        bpy.context.view_layer.update()
        head = arm.matrix_world @ arm.pose.bones[landmarks["head"]].head
        feet = [(arm.matrix_world @ arm.pose.bones[landmarks[k]].head) for k in ("foot.l", "foot.r")]
        h = abs(head.z - min(f.z for f in feet))
    finally:
        arm.data.pose_position = prev
        bpy.context.view_layer.update()
    if h <= 1e-6:
        raise C.FeatureError("figure_height_m could not be derived (the head and feet are at the same height): pass figure_height_m")
    return h, "head bone to foot bone distance"


def _set_action(arm, act):
    ad = arm.animation_data or arm.animation_data_create()
    ad.action = act
    if getattr(ad, "action_slot", None) is None and getattr(act, "slots", None):
        for s in act.slots:
            try:
                ad.action_slot = s
                break
            except (TypeError, RuntimeError):
                continue


def sample(arm, act, landmarks, samples, fps, height):
    """The payload clip for one action (upstream shape, Y-up). The scene's frame, the armature's action/slot and its pose position are restored."""
    sc = bpy.context.scene
    f0, f1 = float(act.frame_range[0]), float(act.frame_range[1])
    if f1 - f0 <= 0:
        raise C.FeatureError(f"action {act.name!r} has fewer than two keys: nothing to measure")
    ad = arm.animation_data or arm.animation_data_create()
    prev_action, prev_slot, prev_frame, prev_sub = ad.action, getattr(ad, "action_slot", None), sc.frame_current, sc.frame_subframe
    try:
        _set_action(arm, act)
        frames = [f0 + (f1 - f0) * i / (samples - 1) for i in range(samples)]
        tracks = {k: [] for k in landmarks}
        scale_delta, quats0, quats1 = [], {}, {}
        rot = [pb for pb in arm.pose.bones if pb.rotation_mode != "AXIS_ANGLE"]
        for i, f in enumerate(frames):
            sc.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
            bpy.context.view_layer.update()
            for k, bn in landmarks.items():
                p = _y_up(arm.matrix_world @ arm.pose.bones[bn].head)
                if not all(math.isfinite(c) for c in p):
                    raise C.FeatureError(f"action {act.name!r}: landmark {k} has a non-finite world position at frame {f:g}")
                tracks[k].append(p)
            scale_delta.append(max((max(abs(s - 1.0) for s in pb.scale) for pb in arm.pose.bones), default=0.0))
            if i == 0:
                quats0 = {pb.name: pb.matrix_basis.to_quaternion() for pb in rot}
            if i == samples - 1:
                quats1 = {pb.name: pb.matrix_basis.to_quaternion() for pb in rot}
        pose_return = max((math.degrees(quats0[n].rotation_difference(quats1[n]).angle) for n in quats0), default=0.0)
        return {"sourceName": act.name, "duration": (f1 - f0) / fps, "sampleTimes": [(f - f0) / fps for f in frames], "landmarkPositions": {k: [list(p) for p in v] for k, v in tracks.items()},
                "jointScaleDelta": scale_delta, "poseReturn": pose_return}
    finally:
        ad.action = prev_action
        if prev_slot is not None:
            try:
                ad.action_slot = prev_slot
            except (TypeError, RuntimeError):
                pass
        sc.frame_set(prev_frame, subframe=prev_sub)
        bpy.context.view_layer.update()


def _thresholds(spec):
    if spec in (None, "", "default"):
        return CF.DEFAULT_THRESHOLDS
    import json
    d = json.loads(spec) if isinstance(spec, str) else dict(spec)
    known = set(CF.Thresholds.__dataclass_fields__)
    bad = sorted(set(d) - known)
    if bad:
        raise C.FeatureError(f"unknown threshold {bad}: the table has {sorted(known)}")
    return CF.Thresholds(**d)


def classify_actions(armature, action=None, fps=None, samples=25, landmarks=None, figure_height_m=None, thresholds="default", apply="none", labels_for_naming=None, by="agent"):
    arm = bpy.data.objects.get(armature)
    if arm is None or arm.type != "ARMATURE":
        raise C.FeatureError(f"no armature named {armature!r}; the armatures are: {sorted(o.name for o in bpy.data.objects if o.type == 'ARMATURE')}")
    if not 8 <= int(samples) <= 120:
        raise C.FeatureError("samples is 8..120 (default 25)")
    if apply not in ("none", "rename", "props"):
        raise C.FeatureError("apply is none | rename | props")
    if apply == "rename" and by != "user":
        raise C.FeatureError("apply rename needs the user's click in the Client: an agent may only propose names")
    if arm.mode == "EDIT":
        raise C.FeatureError("the armature is in edit mode: leave it before measuring")
    sc = bpy.context.scene
    rate = float(fps) if fps else sc.render.fps / sc.render.fps_base
    if rate <= 0:
        raise C.FeatureError("fps must be positive")
    lm = resolve_landmarks(arm, landmarks)
    height, hsrc = _figure_height(arm, lm, figure_height_m)
    th = _thresholds(thresholds)
    if action:
        act = bpy.data.actions.get(action)
        if act is None:
            raise C.FeatureError(f"no action named {action!r}; the actions are: {sorted(a.name for a in bpy.data.actions)}")
        acts = [act]
    else:
        acts = [a for a in bpy.data.actions if _drives(a, arm)]
        if not acts:
            raise C.FeatureError(f"no action on {armature} drives its bones")
    entries, tripped = [], []
    for act in acts:
        feats = CF.measure_clip(sample(arm, act, lm, int(samples), rate, height), height)
        cls = CF.classify(feats, th)
        loop = CF.decide_loop(feats)
        label = (labels_for_naming or {}).get(act.name) or cls.primary or act.name
        name = CF.name_clip(feats, label, classification=cls, loop=loop.loop)
        legacy = None if feats.pose_return is None else bool(feats.pose_return <= LEGACY_LOOP_DEGREES and feats.hip_return <= CF.LOOP_HIP_TOLERANCE)
        c = cls.to_dict()
        c["thresholds"] = dict(c["thresholds"], provenance=PROVENANCE)
        e = {"action": act.name, "features": _snake(feats.to_dict(), {"duration": "duration_s", "poseReturn": "pose_return_deg"}), "classification": c,
             "loop": dict(_snake(loop.to_dict()), rule="upstream: pose_return <= 0.5 deg per rotation joint and hip <= 0.01 H", loop_at_anim_loop_export_limit=legacy, anim_loop_export_limit_deg=LEGACY_LOOP_DEGREES),
             "name": _snake(name.to_dict())}
        if feats.scales_joints:
            tripped.append(act.name)
        if apply in ("rename", "props"):
            act["lw_clip_primary"] = cls.primary or ""
            act["lw_clip_labels"] = ",".join(cls.labels)
            act["lw_clip_loop"] = "" if loop.loop is None else str(bool(loop.loop))
            act["lw_clip_measured"] = name.measured
            act["lw_clip_inferred"] = bool(name.inferred)
            act["lw_source_name"] = act.name
        if apply == "rename" and label != act.name:
            act.name = label
            e["renamed_to"] = act.name
        entries.append(e)
    entries.sort(key=lambda e: not e["features"]["scales_joints"])                      # a rig that scales joints is listed first: it changes what weight work may legally do
    return {"ok": True, "armature": armature, "figure_height": height, "figure_height_source": hsrc, "fps": rate, "samples": int(samples), "landmarks": lm, "thresholds": dict(th.to_dict(), provenance=PROVENANCE),
            "scale_tripwire": tripped, "clips": entries}
