# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The two-view SKINNED-silhouette analysis-by-synthesis of anim_multiview_fit (specs/generation/anim_multiview_fit.md step 4, canitcode's method): for every
frame the character's OWN rig is posed, its skinned mesh (the evaluated depsgraph, so the Armature modifier deforms it) is rasterised through the recorded
front and side cameras (anim_ref.raster_mask: the cameras anim_reference_render rendered with), and the chosen bones' rotations are moved by coordinate
descent until (1 - IoU_front) + (1 - IoU_side) stops falling (the step halves each round; the cost never rises). Twist about a bone's own axis (local Y) is
not observable from two silhouettes and is not searched. No render: a raster of the evaluated mesh, headless and niced with the rest of the run."""

import json
import math
import os

import bpy
import numpy as np

from . import common as C
from ..pipeline import anim_ref as AR

DEFAULT_BONES = ("thigh_l", "thigh_r", "calf_l", "calf_r", "upperarm_l", "upperarm_r", "lowerarm_l", "lowerarm_r")
AXES = (0, 2)                                   # local X and Z; Y is the bone's own (twist) axis


def silhouettes(arm, mesh, cams):
    bpy.context.view_layer.update()
    dg = bpy.context.evaluated_depsgraph_get()
    ev = mesh.evaluated_get(dg)
    me = ev.to_mesh()
    try:
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mw = np.array(mesh.matrix_world)
        co = (mw[:3, :3] @ co.reshape(-1, 3).T).T + mw[:3, 3]
        tris = np.empty(len(me.loop_triangles) * 3, dtype=np.int64)
        me.loop_triangles.foreach_get("vertices", tris)
        tris = tris.reshape(-1, 3)
    finally:
        ev.to_mesh_clear()
    return {v: AR.raster_mask(co, tris, cams[v]) for v in ("front", "side")}


def _iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 1.0


def _cost(arm, mesh, cams, target):
    m = silhouettes(arm, mesh, cams)
    i = {v: _iou(m[v], target[v]) for v in ("front", "side")}
    return 2.0 - i["front"] - i["side"], i


def refine_frame(arm, mesh, cams, target, bones=DEFAULT_BONES, step_deg=8.0, rounds=5, sweep_deg=60.0, sweep_step_deg=10.0):
    pbs = []
    for b in bones:
        pb = arm.pose.bones.get(b)
        if pb is None:
            raise C.FeatureError(f"no bone {b!r} in {arm.name}: the bones to refine are the rig's own")
        pb.rotation_mode = "XYZ"
        pbs.append(pb)
    best, i0 = _cost(arm, mesh, cams, target)
    before = (best, i0)
    hist = [round(best, 5)]
    ib = i0
    # a coarse sweep first: a limb crossing its twin in one view makes the cost rise before it falls, so small steps from rest stall
    if sweep_deg > 0:
        offs = [math.radians(d) for d in np.arange(-sweep_deg, sweep_deg + 1e-9, sweep_step_deg) if abs(d) > 1e-9]
        for pb in pbs:
            for ax in AXES:
                old = pb.rotation_euler[ax]
                keep = old
                for o in offs:
                    pb.rotation_euler[ax] = old + o
                    v, i = _cost(arm, mesh, cams, target)
                    if v < best - 1e-9:
                        best, ib, keep = v, i, old + o
                pb.rotation_euler[ax] = keep
        hist.append(round(best, 5))
    step = math.radians(step_deg)
    for _ in range(int(rounds)):
        for pb in pbs:
            for ax in AXES:
                for sgn in (1, -1):
                    old = pb.rotation_euler[ax]
                    pb.rotation_euler[ax] = old + sgn * step
                    v, i = _cost(arm, mesh, cams, target)
                    if v < best - 1e-9:
                        best, ib = v, i
                    else:
                        pb.rotation_euler[ax] = old
        hist.append(round(best, 5))
        step /= 2
    bpy.context.view_layer.update()
    return {"cost_before": round(before[0], 5), "cost_after": round(best, 5), "iou_before": {k: round(v, 4) for k, v in before[1].items()},
            "iou_after": {k: round(v, 4) for k, v in ib.items()}, "history": hist,
            "rotations": {pb.name: [round(math.degrees(pb.rotation_euler[a]), 3) for a in range(3)] for pb in pbs}}


def _mask_frames(d):
    from PIL import Image
    files = sorted(f for f in os.listdir(d) if f.lower().endswith(".png"))
    return files, [np.asarray(Image.open(os.path.join(d, f)).convert("L")) > 127 for f in files]


def refine(armature, mesh, masks, cameras, out, bones=None, step_deg=8.0, rounds=5, key=False, sweep_deg=60.0):
    arm = C.need_object(armature, "ARMATURE")
    me = C.need_object(mesh)
    if not any(m.type == "ARMATURE" and m.object == arm for m in me.modifiers):
        raise C.FeatureError(f"{me.name} is not skinned to {arm.name}: the silhouette must come from the rig's own deformation")
    if not masks or set(masks) != {"front", "side"}:
        raise C.FeatureError("masks is {front: dir, side: dir} of per-frame silhouette PNGs: one view cannot tell a leg forward from a leg back")
    with open(cameras) as fh:
        cams = json.load(fh)
    cams = cams.get("cameras", cams)
    if set(cams) < {"front", "side"}:
        raise C.FeatureError("cameras is the cameras.json of anim_reference_render (front and side)")
    ff, fm = _mask_frames(masks["front"])
    sf, sm = _mask_frames(masks["side"])
    if len(fm) != len(sm) or not fm:
        raise C.FeatureError(f"the front and side mask folders hold {len(fm)} and {len(sm)} frames: one per frame in each, the same count")
    for v, m in (("front", fm[0]), ("side", sm[0])):
        if list(m.shape[::-1]) != list(cams[v]["size"]):
            raise C.FeatureError(f"{v} masks are {m.shape[1]} x {m.shape[0]}; the {v} camera records {cams[v]['size']}: masks and camera must share a frame")
    receipt = []
    for k, (a, b) in enumerate(zip(fm, sm)):
        r = refine_frame(arm, me, cams, {"front": a, "side": b}, tuple(bones or DEFAULT_BONES), step_deg, rounds, sweep_deg if k == 0 else min(sweep_deg, 20.0))
        r["frame"] = k
        receipt.append(r)
        if key:
            for name in r["rotations"]:
                arm.pose.bones[name].keyframe_insert("rotation_euler", frame=k + 1)
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    with open(out, "w") as fh:
        json.dump({"armature": arm.name, "mesh": me.name, "bones": list(bones or DEFAULT_BONES), "receipt": receipt}, fh, indent=1)
    worst = sorted(receipt, key=lambda r: -r["cost_after"])[:5]
    return {"frames": len(receipt), "out": out, "receipt": receipt, "worst_frames": [w["frame"] for w in worst], "keyed": bool(key),
            "note": "twist about each bone's own axis is not observable from two silhouettes: it is left at rest"}
