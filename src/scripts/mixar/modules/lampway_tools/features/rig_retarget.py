# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_retarget (specs/canon/rig_tools/rig_retarget.md; canon 19 B.1-B.3, B.5): motion from one skeleton onto another, with a root bone when
asked. Built beside LT animation_retarget on the same rule (its tests and callers are untouched): every mapped target bone's world rotation is
W_t = W_s R_s^-1 R_t (rig_tools/core.retarget_world, R04), solved parent-first into LOCAL keys; non-root bones key rotation only (INV-19.1:
no bone length changes); the pelvis travels by the source pelvis's displacement times the pelvis-height ratio (in_place zeroes the ground
components); root_motion=root_bone writes a root bone from the pelvis (core.root_from_pelvis, R05: on the ground, never tilted, recomposing
the pelvis exactly; yaw none | heading). MB's offset-parent retarget (Copy Transforms in pose space) is not ported: R04's falsifier.

The map is the target's own names on the source (identity), a shipped family table, or a rig_map file whose source sha must match. After
writing, the action is played and measured: world-rotation error per mapped bone, bone-length change, and the root's tilt and recomposition."""

import hashlib
import json
import math
import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

from . import animation as AN
from . import common as C
from . import rig_bake as RB
from . import rig_tools as RT
from ..rig_tools import core as RC


def _m3(M):
    return np.array([[M[r][c] for c in range(3)] for r in range(3)], float)


def _pairs(src, tgt, map_, root):
    """([(source bone, target bone)], how, sha256)."""
    sb, tb = set(src.data.bones.keys()), set(tgt.data.bones.keys())
    if map_ in ("", "auto", None):
        same = sorted(sb & tb)
        if same and len(same) >= len(tb) / 2:
            return [(n, n) for n in same], "identity", RC.sha(same)
        try:
            fam, _hits = RC.detect_family(sorted(sb), {f: RC.load_family(f)["map"] for f in RC.families()})
        except RC.RigRefused as exc:
            raise C.FeatureError(f"no map: the target's names are not the source's and {exc}") from None
        table = RC.load_family(fam)["map"]
        pairs = [(src_name, slot) for slot, src_name in sorted(table.items()) if src_name in sb and slot in tb]
        return pairs, f"family:{fam}", RC.sha(pairs)
    p = Path(map_) if os.path.isabs(map_) else Path(root, map_)
    if not p.is_file():
        raise C.FeatureError(f"no map at {p}: run lampway_rig_map on the source first")
    raw = p.read_bytes()
    doc = json.loads(raw)
    stamp = RT._inspected(src)
    if doc.get("sha256", {}).get("source_rest") != stamp["input"]:
        raise C.FeatureError(f"{p.name} was made from a different rest of {src.name} (its source sha differs): run lampway_rig_map again")
    pairs = [(v["source"], slot) for slot, v in sorted(doc["map"].items()) if slot in tb and v["source"] in sb]
    return pairs, str(p), hashlib.sha256(raw).hexdigest()


def retarget(source, target, root, action="", map="auto", method="matrix", root_motion="keep", root_yaw="none", scale="auto", frames="action",
             fps=None, check_objects=None, name="", dry_run=False):
    if method != "matrix":
        raise C.FeatureError("method is matrix (the constraint method is lampway_rig_bake over a constraint setup)")
    if root_motion not in ("keep", "in_place", "root_bone"):
        raise C.FeatureError("root_motion is keep | in_place | root_bone")
    if root_yaw not in ("none", "heading"):
        raise C.FeatureError("root_yaw is none | heading")
    if scale != "auto" and not 0.01 <= float(scale) <= 100:
        raise C.FeatureError("scale is auto or between 0.01 and 100")
    if fps is not None and not 1 <= float(fps) <= 120:
        raise C.FeatureError("fps is between 1 and 120")
    tgt = RT._armature(target)
    RT._inspected(tgt)
    imported = None
    if bpy.data.objects.get(source) is not None:
        src = RT._armature(source)
        RT._inspected(src)
    else:
        src, *imported = AN._import(source, root)
    try:
        return _run(src, tgt, root, action, map, root_motion, root_yaw, scale, frames, fps, check_objects or [], name, dry_run)
    finally:
        if imported:
            objs, acts, col = imported
            for o in objs:
                bpy.data.objects.remove(o)
            for a in acts:
                bpy.data.actions.remove(a)
            bpy.data.collections.remove(col)


def _run(src, tgt, root, action, map_, root_motion, root_yaw, scale, frames, fps, check_objects, name, dry_run):
    pairs, how, map_sha = _pairs(src, tgt, map_, root)
    if not pairs:
        raise C.FeatureError(f"the map pairs no bone of {src.name} with {tgt.name}")
    by_t = {t: s for s, t in pairs}
    pelvis = "pelvis" if "pelvis" in by_t else None
    if root_motion == "root_bone":
        if "root" not in tgt.data.bones:
            raise C.FeatureError(f"root_motion=root_bone needs a bone named root on {tgt.name}: conform with ik_bones (it adds one) or pass keep")
        if pelvis is None or tgt.data.bones["pelvis"].parent is None or tgt.data.bones["pelvis"].parent.name != "root":
            raise C.FeatureError(f"root_motion=root_bone needs {tgt.name}'s pelvis mapped and parented to root")
    unmapped_s = sorted(set(src.data.bones.keys()) - set(by_t.values()))
    unmapped_t = sorted(set(tgt.data.bones.keys()) - set(by_t))
    if action in ("", None):
        act = src.animation_data.action if src.animation_data else None
    else:
        act = bpy.data.actions.get(action)
    if act is None or not AN._drives(act, src):
        raise C.FeatureError(f"{src.name} has no animation to retarget: pass action= (an action driving its bones)")
    f0, f1 = (int(round(act.frame_range[0])), int(round(act.frame_range[1]))) if frames in ("", "action", None) else (int(frames[0]), int(frames[1]))
    if f1 < f0:
        raise C.FeatureError(f"the frame range [{f0}, {f1}] is empty")
    out_name = name or f"{act.name}_rt"
    plan = {"source": src.name, "target": tgt.name, "action": out_name, "map": how, "mapping": [{"source": s, "target": t} for s, t in pairs],
            "unmapped_source": unmapped_s, "unmapped_target": unmapped_t, "root_motion": root_motion, "frames": [f0, f1]}
    if dry_run:
        return {**plan, "dry_run": True}
    if out_name in bpy.data.actions:
        raise C.FeatureError(f"{out_name} exists: a retarget writes a NEW action; pass another name")
    sc = bpy.context.scene
    keep_frame = sc.frame_current
    sad = src.animation_data_create()
    keep_src = sad.action
    sad.action = act
    tad = tgt.animation_data_create()
    keep_tgt = tad.action
    sm, tm = src.matrix_world, tgt.matrix_world
    Rs = {s: _m3(sm.to_3x3().normalized() @ src.data.bones[s].matrix_local.to_3x3()) for s, _t in pairs}
    Rt = {t: _m3(tm.to_3x3().normalized() @ tgt.data.bones[t].matrix_local.to_3x3()) for _s, t in pairs}
    if pelvis:
        hs = (sm @ src.data.bones[by_t[pelvis]].matrix_local).translation
        ht = (tm @ tgt.data.bones[pelvis].matrix_local).translation
        rscale = (ht.z / hs.z if abs(hs.z) > 1e-9 else 1.0) if scale == "auto" else float(scale)
    else:
        rscale = 1.0
    step = sc.render.fps / float(fps) if fps else 1.0
    times = [f0 + i * step for i in range(int(math.floor((f1 - f0) / step + 1e-9)) + 1)]
    order = sorted(tgt.data.bones, key=AN._depth)
    tinv = tm.inverted()
    t3inv = Matrix(np.linalg.inv(_m3(tm.to_3x3().normalized())).tolist())
    rows, expected = [], []
    try:
        for t in times:
            sc.frame_set(int(math.floor(t)), subframe=t - math.floor(t))
            W = {tb: RC.retarget_world(_m3((sm @ src.pose.bones[sb].matrix).to_3x3().normalized()), Rs[sb], Rt[tb]) for sb, tb in pairs}
            want_pelvis = None
            if pelvis:
                sh = (sm @ src.pose.bones[by_t[pelvis]].matrix).translation
                d = (sh - hs) * rscale
                if root_motion == "in_place":
                    d.x = d.y = 0.0
                P = np.eye(4)
                P[:3, :3], P[:3, 3] = W[pelvis], np.array(ht + d)
                want_pelvis = P
            want_root = None
            if root_motion == "root_bone":                         # the facing is the rest's (-Y) turned by the pelvis's CHANGE from its rest
                want_root, _local = RC.root_from_pelvis(_with_rot(want_pelvis, W[pelvis] @ Rt[pelvis].T), root_yaw)
            expected.append({"W": W, "pelvis": want_pelvis, "root": want_root})
            M, row = {}, {}
            for b in order:
                base = M[b.parent.name] @ (b.parent.matrix_local.inverted() @ b.matrix_local) if b.parent else b.matrix_local.copy()
                if b.name == "root" and want_root is not None:
                    want = tinv @ Matrix(want_root.tolist())
                elif b.name in W:
                    trans = base.translation.copy()
                    if b.name == pelvis and want_pelvis is not None:
                        trans = tinv @ Matrix(want_pelvis.tolist()).translation
                    want = Matrix.Translation(trans) @ (t3inv @ Matrix(W[b.name].tolist())).to_4x4()
                else:
                    M[b.name] = base
                    continue
                M[b.name] = want
                row[b.name] = base.inverted() @ want
            rows.append(row)
        new = bpy.data.actions.new(out_name)
        tad.action = new
        keys = 0
        for b in tgt.pose.bones:
            if b.name not in rows[0]:
                continue
            prev, cols = None, {"rotation": [], "location": []}
            for row in rows:
                loc, q, _s = row[b.name].decompose()
                r, prev = RB._rot_values(b, q, prev)
                cols["rotation"].append(r)
                cols["location"].append(list(loc))
            chans = ["rotation"] + (["location"] if b.name in (pelvis, "root") else [])
            for ch in chans:
                path = RB._rot_path(b)[0] if ch == "rotation" else "location"
                for i in range(len(cols[ch][0])):
                    fc = new.fcurve_ensure_for_datablock(tgt, f'pose.bones["{b.name}"].{path}', index=i)
                    fc.keyframe_points.add(len(rows))
                    co = []
                    for k, v in enumerate(cols[ch]):
                        co += [f0 + k, v[i]]
                    fc.keyframe_points.foreach_set("co", co)
                    for kp in fc.keyframe_points:
                        kp.interpolation = "LINEAR"
                    fc.update()
                    keys += len(rows)
        # measure what was written
        rest_len = {b.name: (b.head_local - b.parent.head_local).length for b in tgt.data.bones if b.parent}
        ang = dl = tilt = rec = 0.0
        stretch = {}
        objs = [C.need_object(o) for o in check_objects]
        rest_geo = {}
        if objs:
            from . import rig as _R
            tad.action = None
            sc.frame_set(f0)
            for o in objs:
                e = np.empty(len(o.data.edges) * 2, dtype=np.int64)
                o.data.edges.foreach_get("vertices", e)
                rest_geo[o.name] = (e.reshape(-1, 2), _R._evaluated(o))
            tad.action = new
        for k, ex in enumerate(expected):
            sc.frame_set(f0 + k)
            bpy.context.view_layer.update()
            for tb, Wt in ex["W"].items():
                got = _m3((tm @ tgt.pose.bones[tb].matrix).to_3x3().normalized())
                ang = max(ang, RC.angle_deg(got, Wt))
            for b in tgt.pose.bones:                                # INV-19.1: only the pelvis (and the root) travel
                if b.parent is not None and b.name not in (pelvis, "root"):
                    dl = max(dl, abs((b.head - b.parent.head).length - rest_len[b.name]))
            if ex["root"] is not None:
                R4 = np.array(tm @ tgt.pose.bones["root"].matrix)
                P4 = np.array(tm @ tgt.pose.bones[pelvis].matrix)
                tilt = max(tilt, RC.tilt_deg(R4))
                rec = max(rec, float(np.abs(P4 - ex["pelvis"]).max()))
            for o in objs:
                from . import rig as _R
                edges, rest = rest_geo[o.name]
                cur = _R._evaluated(o)
                rl = np.linalg.norm(rest[edges[:, 0]] - rest[edges[:, 1]], axis=1)
                cl = np.linalg.norm(cur[edges[:, 0]] - cur[edges[:, 1]], axis=1)
                keep = rl > 1e-9
                stretch[o.name] = max(stretch.get(o.name, 1.0), round(float((cl[keep] / rl[keep]).max()), 6) if keep.any() else 1.0)
    finally:
        sad.action = keep_src
        sc.frame_set(keep_frame)
    tad.action = keep_tgt
    out = {**plan, "dry_run": False, "keys": keys, "root_scale": round(rscale, 6), "fps": int(fps) if fps else sc.render.fps,
           "metrics": {"max_world_angle_error_deg": ang, "max_bone_length_change_m": dl, "max_edge_stretch": stretch},
           "map_sha256": map_sha, "canonical_agreement_deg": None,
           "canonical_note": "not computed here: lampway_rig_convert verb=retarget on the two profiles is the canonical twin (canon 22 B.8)",
           "previous_target_action": keep_tgt.name if keep_tgt else None,
           "sha256": {"source_rest": RT._fingerprint(src, RT.read(src)), "target_rest": RT._fingerprint(tgt, RT.read(tgt))}}
    if root_motion == "root_bone":
        out["root"] = {"bone": "root", "yaw": root_yaw, "max_tilt_deg": tilt, "recompose_error_m": rec}
    return out


def _with_rot(P, R):
    """P with its rotation replaced by R (the pelvis's change from its rest, which carries the facing)."""
    Q = np.array(P, float)
    Q[:3, :3] = R
    return Q
