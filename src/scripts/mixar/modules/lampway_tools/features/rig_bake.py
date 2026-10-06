# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_bake (specs/canon/rig_tools/rig_bake.md; canon 19 B.6): a driver's actions to plain keys on the target, action by action.

The semantics are Game Rig Tools 4.3.0's Action Bakery as specs/canon/rig_tools records them (TinkerBoi, GPL-2.0-or-later; no code copied):
frame ranges action | [start, end] | trim:[a, b] with an inclusive end, naming suffix | prefix | replace | local, the same-name refusal,
overwrite by rename-remap-remove, offset to frame one, push to NLA (a stale track of the same name replaced), the target's constraints
unmuted for the bake and muted after. The bake itself is re-implemented: every frame the target's evaluated pose matrices are sampled and
written as LOCAL keys through Blender's own space conversion against the sampled parent (parent-first), so the result does not depend on
constraint evaluation order; then the baked action is played with the constraints muted and compared with the samples frame by frame. An
action over 1e-4 m or 0.01 deg is removed and reported failed (no partial action stays). The driver's previous action is restored, even none."""

import json

import bpy
import numpy as np

from . import common as C
from . import rig_tools as RT

BAR_M, BAR_DEG = 1e-4, 0.01
CHANNELS = ("location", "rotation", "scale")


def _bones_driven(action, arm):
    return sorted({p for fc in RT._fcurves(action) for p in [RT._bone_of(fc.data_path)] if p and p in arm.data.bones})


def _frames(spec, action):
    s, e = int(round(action.frame_range[0])), int(round(action.frame_range[1]))
    if spec in (None, "", "action"):
        return s, e
    if isinstance(spec, str) and spec.startswith("trim:"):
        a, b = json.loads(spec[5:])
        return s + int(a), e - int(b)
    if isinstance(spec, (list, tuple)) and len(spec) == 2:
        return int(spec[0]), int(spec[1])
    raise C.FeatureError("frames is action | [start, end] | trim:[a, b]")


def _baked_name(src, rule, count):
    rule = dict({"mode": "suffix", "value": "_baked", "to": ""}, **(rule or {}))
    mode, val = rule["mode"], str(rule["value"])
    if mode == "suffix":
        return src + val
    if mode == "prefix":
        return val + src
    if mode == "replace":
        return src.replace(val, str(rule.get("to", "")))
    if mode == "local":
        if count != 1:
            raise C.FeatureError("name mode local names one action: bake one action per call, or use suffix | prefix | replace")
        return val
    raise C.FeatureError("name.mode is suffix | prefix | replace | local")


def _rot_path(pb):
    return {"QUATERNION": ("rotation_quaternion", 4), "AXIS_ANGLE": ("rotation_axis_angle", 4)}.get(pb.rotation_mode, ("rotation_euler", 3))


def _rot_values(pb, q, prev):
    """(the key values in the bone's rotation mode, the state the next frame stays continuous with)."""
    if pb.rotation_mode == "QUATERNION":
        v = [q.w, q.x, q.y, q.z]
        if prev is not None and np.dot(v, prev) < 0:
            v = [-x for x in v]
        return v, v
    if pb.rotation_mode == "AXIS_ANGLE":
        axis, angle = q.to_axis_angle()
        return [angle, axis.x, axis.y, axis.z], None
    e = q.to_euler(pb.rotation_mode, prev) if prev is not None else q.to_euler(pb.rotation_mode)
    return [e.x, e.y, e.z], e


def _sample(driver, target, frames):
    """{frame: {bone: (armature-space matrix, local basis)}}: the target's evaluated pose and its LOCAL form against the sampled parent."""
    scene = bpy.context.scene
    out = {}
    for f in frames:
        scene.frame_set(f)
        bpy.context.view_layer.update()
        row = {}
        for pb in target.pose.bones:
            M = pb.matrix.copy()
            row[pb.name] = (target.matrix_world @ M, target.convert_space(pose_bone=pb, matrix=M, from_space="POSE", to_space="LOCAL"))
        out[f] = row
    return out


def _write(target, action, samples, frames, channels, shift):
    keys = 0
    order = sorted(frames)
    for pb in target.pose.bones:
        cols = {}
        prev = None
        for f in order:
            loc, q, s = samples[f][pb.name][1].decompose()
            r, prev = _rot_values(pb, q, prev)
            for ch, vals in (("location", list(loc)), ("rotation", r), ("scale", list(s))):
                if ch in channels:
                    cols.setdefault(ch, []).append(vals)
        for ch, rows in cols.items():
            path = _rot_path(pb)[0] if ch == "rotation" else ch
            for i in range(len(rows[0])):
                fc = action.fcurve_ensure_for_datablock(target, f'pose.bones["{pb.name}"].{path}', index=i)
                fc.keyframe_points.add(len(order))
                co = []
                for f, v in zip(order, rows):
                    co += [f + shift, v[i]]
                fc.keyframe_points.foreach_set("co", co)
                for k in fc.keyframe_points:
                    k.interpolation = "LINEAR"
                fc.update()
                keys += len(order)
    return keys


def _verify(target, samples, frames, shift, chans):
    """(position m, rotation deg): the worst world miss of the played keys, each measured only when its channel was baked (a rotation-only
    bake does not claim positions)."""
    scene = bpy.context.scene
    pos = rot = 0.0
    for f in frames:
        scene.frame_set(f + shift)
        bpy.context.view_layer.update()
        for pb in target.pose.bones:
            a = samples[f][pb.name][0]
            b = target.matrix_world @ pb.matrix
            if "location" in chans:
                pos = max(pos, (a.translation - b.translation).length)
            if "rotation" in chans:
                rot = max(rot, float(np.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle)))
    return pos, rot


def _constraints(target, mute):
    for pb in target.pose.bones:
        for c in pb.constraints:
            c.mute = mute


def bake(driver, target, actions, frames="action", name=None, overwrite=False, offset_to_one=False, push_to_nla=True, channels=None, dry_run=False):
    drv = RT._armature(driver)
    tgt = RT._armature(target)
    RT._inspected(drv)
    RT._inspected(tgt)
    chans = list(channels or CHANNELS)
    bad = sorted(set(chans) - set(CHANNELS))
    if bad:
        raise C.FeatureError(f"channels are {', '.join(CHANNELS)}, not {', '.join(bad)}")
    if not actions:
        raise C.FeatureError("actions: name the driver's actions to bake")
    if drv.animation_data is None:
        raise C.FeatureError(f"{drv.name} has no animation data: assign one of its actions to it first (nothing is baked silently)")
    driven_by = {}
    for pb in tgt.pose.bones:
        tied = any(getattr(c, "target", None) is drv for c in pb.constraints) or pb.name in drv.data.bones
        if not tied:
            driven_by.setdefault("missing", []).append(pb.name)
    if driven_by.get("missing"):
        raise C.FeatureError(f"target bones {', '.join(driven_by['missing'])} have no constraint to {drv.name} and no same-named driver bone: "
                             "nothing would drive them")
    plan = []
    for a in actions:
        act = bpy.data.actions.get(a)
        if act is None:
            raise C.FeatureError(f"no action named {a!r}")
        if not _bones_driven(act, drv):
            raise C.FeatureError(f"{a} drives no bone of {drv.name}: nothing to bake")
        s, e = _frames(frames, act)
        if e < s:
            raise C.FeatureError(f"{a}: the frame range [{s}, {e}] is empty")
        baked = _baked_name(a, name, len(actions))
        if baked == a:
            raise C.FeatureError(f"{a}: the baked name equals its source; overwriting the source would lose it: choose a suffix, prefix or name")
        if baked in bpy.data.actions and not overwrite:
            raise C.FeatureError(f"{baked} exists: pass overwrite=true to replace it, or another name")
        plan.append({"source": a, "baked": baked, "frames": [s, e], "offset": (1 - s) if offset_to_one else 0})
    if dry_run:
        return {"dry_run": True, "actions": plan, "channels": chans}
    scene = bpy.context.scene
    keep_frame = scene.frame_current
    keep_drv = drv.animation_data.action
    tad = tgt.animation_data_create()
    keep_tgt = tad.action
    rows = []
    try:
        for p in plan:
            act = bpy.data.actions[p["source"]]
            drv.animation_data.action = act
            _constraints(tgt, False)
            tad.action = None
            fr = list(range(p["frames"][0], p["frames"][1] + 1))
            samples = _sample(drv, tgt, fr)
            new = bpy.data.actions.new(p["baked"] + ".lw_baking")
            tad.action = new
            keys = _write(tgt, new, samples, fr, chans, p["offset"])
            _constraints(tgt, True)
            pos, rot = _verify(tgt, samples, fr, p["offset"], chans)
            row = dict(p, keys=keys, max_world_error={"m": pos, "deg": rot, "measured": [c for c in ("location", "rotation") if c in chans]},
                       nla_track=None, overwrote=False)
            if pos > BAR_M or rot > BAR_DEG:
                tad.action = None
                bpy.data.actions.remove(new)
                row.update(status="failed", error=f"the baked keys miss the driver by {pos:.3g} m / {rot:.3g} deg (> {BAR_M} m / {BAR_DEG} deg): removed")
                rows.append(row)
                continue
            old = bpy.data.actions.get(p["baked"])
            if old is not None:                                     # overwrite: rename, remap the users, remove
                old.name = p["baked"] + ".lw_replaced"
                old.user_remap(new)
                bpy.data.actions.remove(old)
                row["overwrote"] = True
            new.name = p["baked"]
            if push_to_nla:
                stale = tad.nla_tracks.get(p["baked"])
                if stale is not None:
                    tad.nla_tracks.remove(stale)
                tr = tad.nla_tracks.new()
                tr.name = p["baked"]
                tr.strips.new(p["baked"], int(p["frames"][0] + p["offset"]), new)
                tad.action = None
                row["nla_track"] = p["baked"]
            row["status"] = "baked"
            rows.append(row)
        if not push_to_nla and rows and rows[-1]["status"] == "baked":
            tad.action = bpy.data.actions[rows[-1]["baked"]]
    finally:
        drv.animation_data.action = keep_drv
        if push_to_nla:
            tad.action = None if any(r["status"] == "baked" for r in rows) else keep_tgt
        scene.frame_set(keep_frame)
    return {"dry_run": False, "verdict": "PASS" if all(r["status"] == "baked" for r in rows) else "FAIL", "actions": rows, "channels": chans,
            "target_constraints": "muted (the baked keys play; unmute them to follow the driver again)",
            "driver_action_restored": keep_drv.name if keep_drv else None}
