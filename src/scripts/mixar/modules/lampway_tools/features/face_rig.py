# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""face_rig_validate: a face rig's inputs and outputs checked by measurement (specs/wiki/face_rig_validate.md): shape-key coverage against the ARKit (52) and
viseme (15) name lists, a separate mouth interior, and the wiki's six acceptance expressions measured on the evaluated mesh, never eyeballed.

Landmarks are vertex groups on the head: lip_upper, lip_lower (the lip gap is the distance between their centroids), brow_l, brow_r (the brow asymmetry is
the difference of their vertical moves from neutral). Teeth clearance is the smallest signed distance of any lip vertex to the teeth surface (negative =
the lip is inside the teeth). Each expression sets its keys on the head's shape keys and every value is restored afterwards. Thresholds are mine
[UNVERIFIED]: lips together <= 1 mm, a wide mouth opens past 1.5 x the neutral gap, an asymmetric brow differs by >= 2 mm.

The name lists are the public ARKit ARFaceAnchor.BlendShapeLocation names and the 15 Oculus LipSync visemes in the viseme_ naming that Blender avatar exports
use (viseme_I, viseme_O, viseme_U for Oculus's ih, oh, ou), written from those public specifications; no copy of either document is in this tree [UNVERIFIED against the resources]. Faceit and the VRM
add-on are neither run nor bundled: VRM expression bindings are reported not checked unless the add-on's data is present."""

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import common as C
from . import rig as _rig

ARKIT = ("eyeBlinkLeft", "eyeLookDownLeft", "eyeLookInLeft", "eyeLookOutLeft", "eyeLookUpLeft", "eyeSquintLeft", "eyeWideLeft", "eyeBlinkRight",
         "eyeLookDownRight", "eyeLookInRight", "eyeLookOutRight", "eyeLookUpRight", "eyeSquintRight", "eyeWideRight", "jawForward", "jawLeft", "jawRight",
         "jawOpen", "mouthClose", "mouthFunnel", "mouthPucker", "mouthLeft", "mouthRight", "mouthSmileLeft", "mouthSmileRight", "mouthFrownLeft",
         "mouthFrownRight", "mouthDimpleLeft", "mouthDimpleRight", "mouthStretchLeft", "mouthStretchRight", "mouthRollLower", "mouthRollUpper",
         "mouthShrugLower", "mouthShrugUpper", "mouthPressLeft", "mouthPressRight", "mouthLowerDownLeft", "mouthLowerDownRight", "mouthUpperUpLeft",
         "mouthUpperUpRight", "browDownLeft", "browDownRight", "browInnerUp", "browOuterUpLeft", "browOuterUpRight", "cheekPuff", "cheekSquintLeft",
         "cheekSquintRight", "noseSneerLeft", "noseSneerRight", "tongueOut")
VISEMES = tuple("viseme_" + v for v in ("sil", "PP", "FF", "TH", "DD", "kk", "CH", "SS", "nn", "RR", "aa", "E", "I", "O", "U"))
PROFILES = {"arkit": ARKIT, "arkit+visemes": ARKIT + VISEMES, "none": ()}
DEFAULT_POSES = (
    {"name": "neutral_blink", "keys": {"eyeBlinkLeft": 1.0, "eyeBlinkRight": 1.0}},
    {"name": "asymmetric_brow", "keys": {"browOuterUpLeft": 1.0}},
    {"name": "wide_mouth", "keys": {"jawOpen": 1.0}},
    {"name": "lips_together", "keys": {"mouthClose": 1.0}},
    {"name": "teeth_tongue_clearance", "keys": {"jawOpen": 1.0}},
    {"name": "speech_line", "keys": {"viseme_PP": 1.0}, "then": {"viseme_aa": 1.0}},
)
CLOSED_M, BROW_M, WIDE_X, OPEN_SOURCE_M = 0.001, 0.002, 1.5, 0.001
GROUPS = ("lip_upper", "lip_lower", "brow_l", "brow_r")


def _idx(ob, name):
    g = ob.vertex_groups.get(name)
    return [] if g is None else [v.index for v in ob.data.vertices for e in v.groups if e.group == g.index and e.weight > 0]


def _measure(ob, L, teeth_tree):
    P = _rig._evaluated(ob)
    out = {}
    if L["lip_upper"] and L["lip_lower"]:
        out["lip_gap_m"] = round(float(np.linalg.norm(P[L["lip_upper"]].mean(axis=0) - P[L["lip_lower"]].mean(axis=0))), 7)
    if L["brow_l"] and L["brow_r"]:
        out["_brow"] = (float(P[L["brow_l"]][:, 2].mean()), float(P[L["brow_r"]][:, 2].mean()))
    if teeth_tree is not None and (L["lip_upper"] or L["lip_lower"]):
        worst, pen = None, 0
        for i in L["lip_upper"] + L["lip_lower"]:
            p = Vector(P[i].tolist())
            loc, nrm, _f, dist = teeth_tree.find_nearest(p)
            if loc is None:
                continue
            sd = dist if (p - loc).dot(nrm) >= 0 else -dist
            pen += sd < 0
            worst = sd if worst is None else min(worst, sd)
        out["teeth_clearance_m"] = None if worst is None else round(float(worst), 6)
        out["penetrating_lip_vertices"] = int(pen)
    return out


def _tree(ob):
    if ob is None:
        return None
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    me.calc_loop_triangles()
    t = BVHTree.FromPolygons([ev.matrix_world @ v.co for v in me.vertices], [tuple(x.vertices) for x in me.loop_triangles])
    ev.to_mesh_clear()
    return t


def _set(blocks, keys):
    for k, v in keys.items():
        if k in blocks:
            blocks[k].value = float(v)
    bpy.context.view_layer.update()


def face_rig_validate(object, shape_key_profile="arkit", teeth=None, tongue=None, profile="generic", poses=None):
    head = C.need_object(object)
    if shape_key_profile not in PROFILES:
        raise C.FeatureError(f"shape_key_profile is {' | '.join(PROFILES)}")
    if profile not in ("generic", "vrm"):
        raise C.FeatureError("profile is generic | vrm")
    sk = head.data.shape_keys
    if shape_key_profile != "none" and (sk is None or len(sk.key_blocks) < 2):
        raise C.FeatureError(f"no shape keys on {head.name}; generate them first (Faceit or manual)")
    teeth_ob = C.need_object(teeth) if teeth else None
    tongue_ob = C.need_object(tongue) if tongue else None
    blocks = sk.key_blocks if sk else {}
    names = [b.name for b in list(blocks)[1:]] if sk else []
    expected = PROFILES[shape_key_profile]
    keys = {"expected": len(expected), "present": sorted(n for n in names if n in expected), "missing": [n for n in expected if n not in names],
            "extra": sorted(n for n in names if n not in expected)}
    L = {g: _idx(head, g) for g in GROUPS}
    saved = {b.name: b.value for b in blocks} if sk else {}
    try:
        if sk:
            _set(blocks, {n: 0.0 for n in saved})
        tt = _tree(teeth_ob)
        neutral = _measure(head, L, tt)
        cavity = bool(neutral.get("lip_gap_m", 0.0) > OPEN_SOURCE_M)
        if (teeth_ob or tongue_ob) and not cavity:
            raise C.FeatureError(f"{head.name}'s mouth is closed at neutral (lip gap {neutral.get('lip_gap_m')} m): open-mouth source needed or accept no interior "
                                 "check (leave teeth and tongue out)")
        rows = []
        for pose in (poses or DEFAULT_POSES):
            want = dict(pose.get("keys") or {})
            missing = [k for k in list(want) + list((pose.get("then") or {})) if k not in blocks]
            if sk:
                _set(blocks, {n: 0.0 for n in saved})
            _set(blocks, want)
            m = _measure(head, L, tt)
            second = None
            if pose.get("then"):
                _set(blocks, {n: 0.0 for n in saved})
                _set(blocks, pose["then"])
                second = _measure(head, L, tt)
            rows.append(_judge(pose["name"], m, neutral, missing, second))
    finally:
        for n, v in saved.items():
            blocks[n].value = v
        bpy.context.view_layer.update()
    for r in rows:
        r["measured"].pop("_brow", None)
    neutral.pop("_brow", None)
    vrm = None
    if profile == "vrm":
        ext = getattr(head.data, "vrm_addon_extension", None)
        vrm = {"state": "not_checked", "reason": "the VRM add-on is not installed: expression bindings cannot be read"} if ext is None else {"state": "present"}
    return {"object": head.name, "keys": keys, "interior": {"teeth_separate": teeth_ob is not None and teeth_ob is not head,
            "tongue_separate": tongue_ob is not None and tongue_ob is not head, "cavity": cavity}, "neutral": neutral, "expressions": rows,
            "landmarks": {g: len(v) for g, v in L.items()}, "vrm": vrm,
            "note": "thresholds are proposals [UNVERIFIED]; a still that looks right is not evidence of expression range"}


def _judge(name, m, neutral, missing, second):
    row = {"name": name, "measured": dict(m), "missing_keys": missing}
    if missing:
        row["pass"] = False
        return row
    gap, gap0 = m.get("lip_gap_m"), neutral.get("lip_gap_m")
    if name == "lips_together":
        row["pass"] = gap is not None and gap <= CLOSED_M
    elif name == "wide_mouth":
        row["pass"] = gap is not None and gap0 is not None and gap > WIDE_X * gap0
    elif name == "asymmetric_brow":
        if "_brow" in m and "_brow" in neutral:
            asym = abs((m["_brow"][0] - neutral["_brow"][0]) - (m["_brow"][1] - neutral["_brow"][1]))
            row["measured"]["brow_asym_m"] = round(asym, 7)
            row["pass"] = asym >= BROW_M
        else:
            row["pass"] = False
            row["missing_landmarks"] = ["brow_l", "brow_r"]
    elif name == "teeth_tongue_clearance":
        tc = m.get("teeth_clearance_m")
        row["pass"] = None if tc is None else bool(tc >= 0 and (neutral.get("teeth_clearance_m") or 0) >= 0)
    elif name == "speech_line":
        g2 = (second or {}).get("lip_gap_m")
        row["measured"]["second_lip_gap_m"] = g2
        row["pass"] = gap is not None and g2 is not None and gap <= CLOSED_M and g2 > gap
    else:
        row["pass"] = None
    return row
