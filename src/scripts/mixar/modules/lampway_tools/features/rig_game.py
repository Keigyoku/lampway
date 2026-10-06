# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""rig_game_extract (specs/canon/rig_tools/rig_game_extract.md; canon 19 B.4): an engine-clean deform rig from any control rig.

Re-implemented from the documented behaviour of Game Rig Tools 4.3.0's "Generate Game Rig" and "Convert Bendy Bones To Bones" (TinkerBoi,
GPL-2.0-or-later; behaviour as specs/canon/rig_tools records it, no code copied), with its measured defects fixed: every kept bone lands in the
one collection (GRT reset the collections inside the per-bone loop: 1 of 5 kept), the hierarchy mode is the one hierarchy argument, no Text
datablock is ever executed, removals collect names first.

Steps: copy the control (object and data) as ``name``; keep the bones the extract mode names; hierarchy keep (nearest kept ancestor) |
rigify_fix (an ORG- ancestor's DEF- twin first) | flat; disconnect; inherit rotation, full scale, local location; drop shapes, custom
properties, animation and every constraint; B-Bones refused or converted (one bone per segment, each copying the bendy bone's transform at
its segment start along the curve, the weights of meshes it deforms split between segments as Blender's straight B-Bone mapping does); one
collection holding every kept bone; each game bone constrained to its control twin (lotrot: Copy Location + Copy Rotation, world; transform:
Copy Transforms; none); meshes re-pointed with their world matrix kept. Verified: the game rig follows the control (world error per bone)."""

import re

import bpy
import numpy as np

from . import common as C
from . import rig_tools as RT

EXTRACT = ("deform", "selected", "selected_deform", "deform_and_selected")
HIERARCHY = ("keep", "rigify_fix", "flat")
CONSTRAINT = ("lotrot", "transform", "none")
# The spec (GRT) converts a B-Bone to ONE BONE PER SEGMENT. Blender deforms a vertex by blending the bone's JOINTS k and k+1 (segments + 1 of
# them), so the tail joint has no bone and its share rides the last segment: measured 1.87 mm on the 4-segment probe. True adds that tail
# joint as one more bone (<bone>_seg<segments>) and the conversion becomes exact (measured 1.2e-7 m). The spec governs: False.
TAIL_JOINT_BONE = False


def _kept(ob, extract):
    out = []
    for b in ob.data.bones:
        pb = ob.pose.bones[b.name]
        d, s = b.use_deform, bool(pb.select if hasattr(pb, "select") else b.select)       # Blender 5 selects pose bones
        if {"deform": d, "selected": s, "selected_deform": d and s, "deform_and_selected": d or s}[extract]:
            out.append(b.name)
    return out


def _parents(ob, kept, hierarchy):
    """{kept bone: game parent}: keep - the nearest kept ancestor; rigify_fix - walking up, an ORG-<base> ancestor's DEF-<base> twin (one;
    several numbered twins and no exact one refuse) before the ancestor itself; flat - none."""
    ks = set(kept)
    out = {}
    for n in kept:
        if hierarchy == "flat":
            out[n] = None
            continue
        a = ob.data.bones[n].parent
        p = None
        while a is not None:
            if a.name in ks:
                p = a.name
                break
            if hierarchy == "rigify_fix" and a.name.startswith("ORG-"):
                base = a.name[4:]
                twins = [k for k in ks if k != n and (k == f"DEF-{base}" or re.fullmatch(re.escape(f"DEF-{base}") + r"\.\d{3}", k))]
                if f"DEF-{base}" in twins:
                    p = f"DEF-{base}"
                    break
                if len(twins) > 1:
                    raise C.FeatureError(f"{n}: its ancestor {a.name} has {len(twins)} DEF- twins ({', '.join(sorted(twins))}) and no exact one: "
                                         "the nearest deform ancestor is ambiguous; use hierarchy=keep or rename")
                if len(twins) == 1:
                    p = twins[0]
                    break
            a = a.parent
        out[n] = p
    return out


def _world_error(ctl, game):
    bpy.context.view_layer.update()
    pos = rot = 0.0
    for pb in game.pose.bones:
        src = ctl.pose.bones.get(pb.name)
        if src is None:
            continue
        a, b = ctl.matrix_world @ src.matrix, game.matrix_world @ pb.matrix
        pos = max(pos, (a.translation - b.translation).length)
        rot = max(rot, float(np.degrees(a.to_quaternion().rotation_difference(b.to_quaternion()).angle)))
    return {"max_position_m": pos, "max_rotation_deg": rot, "bones": len(game.pose.bones)}


def _split_bbone_weights(meshes, ctl, bone, segs):
    """A vertex weighted w to the bendy bone moves to the bones of its two joints, as Blender's straight mapping blends them (the position
    along the bone's rest axis, segments * y / length; joint k and k+1); without a tail joint bone the last joint's share goes to the last
    segment."""
    b = ctl.data.bones[bone]
    inv = b.matrix_local.inverted()
    n = b.bbone_segments
    for m in meshes:
        g = m.vertex_groups.get(bone)
        if g is None:
            continue
        new = [m.vertex_groups.get(s) or m.vertex_groups.new(name=s) for s in segs]
        to_arm = ctl.matrix_world.inverted() @ m.matrix_world
        for v in m.data.vertices:
            w = next((e.weight for e in v.groups if e.group == g.index), 0.0)
            if w <= 0.0:
                continue
            y = (inv @ (to_arm @ v.co)).y
            pos = min(max(y / b.length, 0.0), 1.0) * n
            k = min(int(pos), n - 1)
            f = pos - k
            new[k].add([v.index], w * (1.0 - f), "ADD")
            if f > 0:
                new[min(k + 1, len(new) - 1)].add([v.index], w * f, "ADD")
        m.vertex_groups.remove(g)


def extract(control, name="", extract="deform", hierarchy="keep", constraint="lotrot", root_scale_from="auto", bbones="refuse", rebind_meshes=True,
            collection="Deform", dry_run=False):
    ctl = RT._armature(control)
    RT._inspected(ctl)
    for arg, val, allowed in (("extract", extract, EXTRACT), ("hierarchy", hierarchy, HIERARCHY), ("constraint", constraint, CONSTRAINT),
                              ("bbones", bbones, ("refuse", "convert"))):
        if val not in allowed:
            raise C.FeatureError(f"{arg} is {' | '.join(allowed)}, not {val!r}")
    name = name or f"{ctl.name}_game"
    if name in bpy.data.objects:
        raise C.FeatureError(f"{name} is taken by another object: pass another name (an extraction never overwrites)")
    kept = sorted(_kept(ctl, extract))
    if not kept:
        raise C.FeatureError(f"extract={extract} keeps no bone of {ctl.name}")
    dropped = sorted(set(ctl.data.bones.keys()) - set(kept))
    bendy = sorted(n for n in kept if ctl.data.bones[n].bbone_segments > 1)
    if bendy and bbones == "refuse":
        raise C.FeatureError(f"B-Bones on {', '.join(bendy)}: an engine skeleton has none; pass bbones=convert (one bone per segment) or set "
                             "their segments to 1")
    parents = _parents(ctl, kept, hierarchy)
    changes = [{"bone": n, "from": ctl.data.bones[n].parent.name if ctl.data.bones[n].parent else None, "to": parents[n]} for n in kept
               if (ctl.data.bones[n].parent.name if ctl.data.bones[n].parent else None) != parents[n]]
    meshes = [o for o in bpy.data.objects if o.type == "MESH" and any(m.type == "ARMATURE" and m.object is ctl for m in o.modifiers)]
    meshes += [o for o in bpy.data.objects if o.parent is ctl and o.type == "MESH" and o not in meshes]
    if rebind_meshes:
        bad = sorted(o.name for o in meshes if o.parent is ctl and o.parent_type == "BONE" and o.parent_bone not in kept)
        if bad:
            raise C.FeatureError(f"{', '.join(bad)} hang from control bones the game rig drops: their parent inverse cannot be kept; parent them "
                                 "to the object first")
    root_scale = None
    if root_scale_from == "auto":                           # the game rig's own root carries the control root's scale, when it kept one
        root_scale = "root" if "root" in kept else None
    elif root_scale_from != "none":
        if root_scale_from not in ctl.data.bones:
            raise C.FeatureError(f"root_scale_from: no bone {root_scale_from!r} in {ctl.name}")
        root_scale = root_scale_from
    plan = {"control": ctl.name, "game": name, "bones": {"kept": kept, "dropped": dropped}, "hierarchy": hierarchy, "hierarchy_changes": changes,
            "constraint": constraint, "root_scale_from": root_scale, "bbones": bendy, "meshes": [o.name for o in meshes] if rebind_meshes else []}
    if dry_run:
        return {**plan, "dry_run": True}
    game = ctl.copy()
    game.data = ctl.data.copy()
    game.name = game.data.name = name
    for coll in ctl.users_collection or [bpy.context.scene.collection]:
        coll.objects.link(game)
    try:
        game.animation_data_clear()
        game.data.animation_data_clear()
        for k in list(game.keys()):
            del game[k]
        for pb in game.pose.bones:
            for c in list(pb.constraints):
                pb.constraints.remove(c)
        C.activate(game)
        bpy.ops.object.mode_set(mode="EDIT")
        ebs = game.data.edit_bones
        for n in [e.name for e in ebs if e.name not in kept]:
            ebs.remove(ebs[n])
        for n in kept:
            e = ebs[n]
            e.use_connect = False
        for n in kept:
            ebs[n].parent = ebs[parents[n]] if parents[n] else None
        converted = {}
        for n in bendy:
            src = ctl.pose.bones[n]
            rest = ctl.data.bones[n].matrix_local
            segs = []
            prev = ebs[n].parent
            count = ctl.data.bones[n].bbone_segments
            joints = [rest @ src.bbone_segment_matrix(i, rest=True) for i in range(count + 1)]
            for i in range(count + (1 if TAIL_JOINT_BONE else 0)):
                s = ebs.new(f"{n}_seg{i}")
                s.head = joints[i].translation
                s.tail = joints[i + 1].translation if i < count else 2 * joints[i].translation - joints[i - 1].translation
                s.align_roll(joints[i].to_3x3().col[2])
                s.use_deform, s.parent = True, prev
                prev = s
                segs.append(s.name)
            for e in ebs:
                if e.parent is not None and e.parent.name == n:
                    e.parent = prev
            ebs.remove(ebs[n])
            converted[n] = segs
        for e in ebs:
            e.use_connect = False
            e.bbone_segments = 1
            e.inherit_scale = "FULL"
            e.use_inherit_rotation = True
            e.use_local_location = True
        bpy.ops.object.mode_set(mode="OBJECT")
        for b in game.data.bones:
            for k in list(b.keys()):
                del b[k]
        for pb in game.pose.bones:
            pb.custom_shape = None
            for k in list(pb.keys()):
                del pb[k]
        for c in [c.name for c in game.data.collections_all]:          # names first, then remove: never iterate what is being emptied
            if c in game.data.collections_all:
                game.data.collections.remove(game.data.collections_all[c])
        coll = game.data.collections.new(collection)
        for b in game.data.bones:                                        # once, after the loop: every kept bone in the one collection
            coll.assign(b)
        added = []
        seg_of = {s: (n, i, ctl.data.bones[n].bbone_segments) for n, v in converted.items() for i, s in enumerate(v)}
        for pb in game.pose.bones:
            if constraint == "none":
                break
            if pb.name in seg_of:
                n, i, cnt = seg_of[pb.name]
                c = pb.constraints.new("COPY_TRANSFORMS")
                c.target, c.subtarget, c.head_tail, c.use_bbone_shape = ctl, n, i / cnt, True
                added.append({"bone": pb.name, "type": "COPY_TRANSFORMS", "target": n, "head_tail": i / cnt})
                if constraint == "lotrot":
                    ls = pb.constraints.new("LIMIT_SCALE")
                    for ax in "xyz":
                        setattr(ls, f"use_min_{ax}", True)
                        setattr(ls, f"use_max_{ax}", True)
                        setattr(ls, f"min_{ax}", 1.0)
                        setattr(ls, f"max_{ax}", 1.0)
                    added.append({"bone": pb.name, "type": "LIMIT_SCALE"})
                continue
            kinds = ("COPY_LOCATION", "COPY_ROTATION") if constraint == "lotrot" else ("COPY_TRANSFORMS",)
            for kind in kinds:
                c = pb.constraints.new(kind)
                c.target, c.subtarget = ctl, pb.name
                added.append({"bone": pb.name, "type": kind})
            if constraint == "lotrot" and root_scale and (pb.name == root_scale if root_scale_from == "auto" else pb.parent is None):
                c = pb.constraints.new("COPY_SCALE")
                c.target, c.subtarget = ctl, root_scale
                added.append({"bone": pb.name, "type": "COPY_SCALE", "target": root_scale})
        repointed = []
        if rebind_meshes:
            for n, segs in converted.items():
                _split_bbone_weights(meshes, ctl, n, segs)
            for o in meshes:
                mw = o.matrix_world.copy()
                for m in o.modifiers:
                    if m.type == "ARMATURE" and m.object is ctl:
                        m.object = game
                if o.parent is ctl:
                    o.parent = game
                bpy.context.view_layer.update()
                if any(abs(a - b) > 1e-9 for ra, rb in zip(mw, o.matrix_world) for a, b in zip(ra, rb)):
                    o.matrix_world = mw
                repointed.append(o.name)
        follow = _world_error(ctl, game) if constraint != "none" else None
    except Exception:
        if bpy.context.object is not None and bpy.context.object.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        data = game.data
        bpy.data.objects.remove(game)
        if data.users == 0:
            bpy.data.armatures.remove(data)
        raise
    members = sorted(b.name for b in coll.bones)
    out = {**plan, "dry_run": False, "constraints_added": added, "meshes_repointed": repointed, "collection": collection, "collection_members": members,
           "bbones_converted": converted, "follow": follow,
           "sha256": {"control": RT._fingerprint(ctl, RT.read(ctl)), "game": RT._fingerprint(game, RT.read(game))}}
    out["bones"] = {"kept": sorted(game.data.bones.keys()), "dropped": dropped}
    return out
