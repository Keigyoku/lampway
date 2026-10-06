# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""motion_experiment: the wiki's A/B/C motion comparison from a typed brief (specs/wiki/motion_experiment.md).

A is keyed on the armature from the brief's explicit start pose (frame 1), an optional contact pose (at the contact time) and the end pose (at the duration),
with Blender's default interpolation; the contact landmark is a pose marker. B and C are actions imported from an external tool (Kimodo, HY-Motion,
Cascadeur exports): their first and last frames must reproduce A's start and end poses (every bone the brief names, within POSE_TOL_DEG), or the
comparison is refused, because a comparison of motions that start or end elsewhere measures the poses, not the motion. Each variant is measured on every
frame (duration, start/end/contact pose error, the largest bone angular speed and acceleration) and tabulated; ``grade`` names the smoothest variant by
its largest angular acceleration and leaves the choice to a person. No seed is recorded: none of these tools exposes one here (``not_exposed``)."""

import math

import bpy
from mathutils import Euler

from . import clearance as _cl
from . import clip_classify as _cc
from . import common as C

POSE_TOL_DEG = 0.5            # [UNVERIFIED] how far an imported variant's start or end may sit from the brief's pose
TAG = "lw_motion_experiment"


def _pose(spec, arm, label) -> dict:
    """{bone: euler degrees} from {bones: [{bone, rotate}]}, {bone: [rx, ry, rz]}, a clearance pose name (rest, wiki8 names) or None."""
    if spec in (None, "", {}):
        raise C.FeatureError("explicit start and end poses are required (a pose is {bones: [{bone, rotate}]}, {bone: [rx, ry, rz]} or a named pose)")
    if isinstance(spec, str):
        named = {p["name"]: p for p in _cl._poses("wiki8")}
        named["rest"] = {"bones": []}
        if spec not in named:
            raise C.FeatureError(f"{label}: unknown pose {spec!r}; the named poses are {sorted(named)}")
        spec = named[spec]
    bones = spec.get("bones") if isinstance(spec, dict) and "bones" in spec else [{"bone": k, "rotate": v} for k, v in (spec or {}).items()]
    out = {}
    for b in bones:
        if b["bone"] not in arm.pose.bones:
            raise C.FeatureError(f"{label}: no bone {b['bone']!r} in {arm.name}; the bones are {sorted(x.name for x in arm.pose.bones)[:30]}")
        out[b["bone"]] = [float(x) for x in b.get("rotate", [0, 0, 0])]
    return out


def _check_brief(brief):
    if not isinstance(brief, dict):
        raise C.FeatureError("brief is {duration_s, start, contact: {time_s, landmark}, end, action, weapon_hand, preserve}")
    d = brief.get("duration_s")
    if not isinstance(d, (int, float)) or not 0.5 <= float(d) <= 10:
        raise C.FeatureError("duration_s is 0.5..10 seconds (a 2-3 second action is the wiki's small experiment)")
    contact = brief.get("contact") or {}
    if "foot_contact" in (brief.get("preserve") or []) and not str(contact.get("landmark") or "").strip():
        raise C.FeatureError("preserve names foot_contact: the brief needs its contact landmark (contact {time_s, landmark}); words alone do not keep a foot planted")
    if contact and not 0 <= float(contact.get("time_s", -1)) <= float(d):
        raise C.FeatureError("contact.time_s lies inside the duration")
    if brief.get("weapon_hand") not in (None, "left", "right"):
        raise C.FeatureError("weapon_hand is left | right | null (the wearer's)")


def _key(arm, pose, frame, bones):
    """Key each bone in ITS OWN rotation mode (an Euler curve on a quaternion bone drives nothing): the pose's XYZ degrees converted to it."""
    for b in bones:
        pb = arm.pose.bones[b]
        e = Euler([math.radians(x) for x in pose.get(b, [0, 0, 0])], "XYZ")
        if pb.rotation_mode == "QUATERNION":
            pb.rotation_quaternion = e.to_quaternion()
            pb.keyframe_insert("rotation_quaternion", frame=frame)
        elif pb.rotation_mode == "AXIS_ANGLE":
            ax, ang = e.to_quaternion().to_axis_angle()
            pb.rotation_axis_angle = [ang, *ax]
            pb.keyframe_insert("rotation_axis_angle", frame=frame)
        else:
            pb.rotation_euler = e.to_matrix().to_euler(pb.rotation_mode)
            pb.keyframe_insert("rotation_euler", frame=frame)


def _make_a(arm, start, end, contact_pose, contact_frame, last, marker):
    name = f"{arm.name}_motion_A"
    for a in [a for a in bpy.data.actions if a.name == name]:
        if not a.get(TAG):
            raise C.FeatureError(f"an action named {name!r} exists and is not this tool's: rename it first")
        bpy.data.actions.remove(a)
    ad = arm.animation_data or arm.animation_data_create()
    prev = ad.action
    prev_rot = {pb.name: (tuple(pb.rotation_quaternion), tuple(pb.rotation_euler), tuple(pb.rotation_axis_angle)) for pb in arm.pose.bones}
    ad.action = None
    bones = sorted(set(start) | set(end) | set(contact_pose or {}))
    try:
        _key(arm, start, 1, bones)
        if contact_pose:
            _key(arm, contact_pose, contact_frame, bones)
        _key(arm, end, last, bones)
        act = ad.action
        act.name = name
        act[TAG] = True
        act.use_fake_user = True
        if marker:
            m = act.pose_markers.new(marker)
            m.frame = contact_frame
    finally:
        ad.action = prev
        for pb in arm.pose.bones:
            pb.rotation_quaternion, pb.rotation_euler, pb.rotation_axis_angle = prev_rot[pb.name]
        bpy.context.view_layer.update()
    return act


def _err(arm, pose) -> tuple:
    worst, where = 0.0, None
    for b, r in pose.items():
        want = Euler([math.radians(x) for x in r], "XYZ").to_quaternion()
        got = arm.pose.bones[b].matrix_basis.to_quaternion()
        e = math.degrees(want.rotation_difference(got).angle)
        if e > worst:
            worst, where = e, b
    return round(worst, 4), where


def _audit(arm, act, start, end, contact_pose, contact_t, fps) -> dict:
    sc = bpy.context.scene
    f0, f1 = int(round(act.frame_range[0])), int(round(act.frame_range[1]))
    ad = arm.animation_data or arm.animation_data_create()
    prev, prev_slot, prev_frame = ad.action, getattr(ad, "action_slot", None), sc.frame_current
    bones = sorted(set(start) | set(end))
    try:
        _cc._set_action(arm, act)
        quats, out = [], {}
        for f in range(f0, f1 + 1):
            sc.frame_set(f)
            quats.append({b: arm.pose.bones[b].matrix_basis.to_quaternion() for b in bones})
            if f == f0:
                out["start_error_deg"], out["start_worst_bone"] = _err(arm, start)
            if f == f1:
                out["end_error_deg"], out["end_worst_bone"] = _err(arm, end)
            if contact_pose and f == f0 + int(round(contact_t * fps)):
                out["contact_error_deg"], _ = _err(arm, contact_pose)
    finally:
        ad.action = prev
        if prev_slot is not None:
            try:
                ad.action_slot = prev_slot
            except (TypeError, RuntimeError):
                pass
        sc.frame_set(prev_frame)
    speed = [max(math.degrees(a[b].rotation_difference(c[b]).angle) for b in bones) * fps for a, c in zip(quats, quats[1:])] or [0.0]
    accel = [abs(y - x) * fps for x, y in zip(speed, speed[1:])] or [0.0]
    out.update(frames=f1 - f0 + 1, duration_s=round((f1 - f0) / fps, 4), max_angular_speed_dps=round(max(speed), 3), max_angular_accel_dps2=round(max(accel), 3))
    return out


def motion_experiment(brief, armature, variants=None):
    _check_brief(brief)
    arm = C.need_object(armature, "ARMATURE")
    start, end = _pose(brief.get("start"), arm, "start"), _pose(brief.get("end"), arm, "end")
    contact = brief.get("contact") or {}
    contact_pose = _pose(contact["pose"], arm, "contact") if contact.get("pose") else None
    variants = dict(variants or {"A": "keyed"})
    if variants.get("A", "keyed") not in ("keyed", "interpolation"):
        raise C.FeatureError("variant A is keyed | interpolation (it is made here from the brief)")
    imported = {}
    for k in ("B", "C"):
        if variants.get(k):
            act = bpy.data.actions.get(variants[k])
            if act is None:
                raise C.FeatureError(f"variant {k}: no action {variants[k]!r}; import the external tool's export first. The actions are: {sorted(a.name for a in bpy.data.actions)[:30]}")
            imported[k] = act
    fps = bpy.context.scene.render.fps / bpy.context.scene.render.fps_base
    last = 1 + int(round(float(brief["duration_s"]) * fps))
    cframe = 1 + int(round(float(contact.get("time_s", 0)) * fps))
    marker = f"contact: {contact['landmark']}" if contact.get("landmark") else None
    rows = {}
    for k, act in imported.items():
        a = _audit(arm, act, start, end, contact_pose, float(contact.get("time_s", 0)), fps)
        for which in ("start", "end"):
            if a[f"{which}_error_deg"] > POSE_TOL_DEG:
                raise C.FeatureError(f"variant {k} ({act.name}) does not share the {which} pose: {a[f'{which}_worst_bone']} is {a[f'{which}_error_deg']} deg away "
                                     f"(> {POSE_TOL_DEG}); every variant starts and ends on the same poses, or the comparison measures the poses")
        rows[k] = {"action": act.name, "audit": a}
    a_act = _make_a(arm, start, end, contact_pose, cframe, last, marker)
    rows["A"] = {"action": a_act.name, "audit": _audit(arm, a_act, start, end, contact_pose, float(contact.get("time_s", 0)), fps)}
    metrics = ("duration_s", "frames", "start_error_deg", "end_error_deg", "max_angular_speed_dps", "max_angular_accel_dps2")
    table = [{"metric": m, **{k: rows[k]["audit"].get(m) if k in rows else None for k in ("A", "B", "C")}} for m in metrics]
    smooth = min(rows, key=lambda k: rows[k]["audit"]["max_angular_accel_dps2"])
    return {"A": rows["A"], "B": rows.get("B"), "C": rows.get("C"), "comparison": table, "seed": "not_exposed",
            "grade": {"smoothest": smooth, "by": "the smallest largest angular acceleration over the brief's bones", "note": "a measurement, not a verdict: a person picks the motion"},
            "brief": {k: brief.get(k) for k in ("duration_s", "action", "weapon_hand", "preserve", "contact")}}
