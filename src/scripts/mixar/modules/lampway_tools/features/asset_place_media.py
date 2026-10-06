# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""asset_place's media and motion kinds: an image as a reference empty, a video as a Movie Clip or a sequencer strip at the current frame, an action onto an armature whose
bones it names (a mismatch is refused with the list: mapping is animation_retarget's job), a rig brought in and bound to a target mesh."""

import os
import re

import bpy

from .. import canon_io
from .asset_place import (PlaceError, collection, drop_point, entry, file_of, load_blend, place_rig_objects, scene, stamp, target_object, where)

_BONE = re.compile(r'pose\.bones\["((?:[^"\\]|\\.)*)"\]')


def reference_image(asset, opts, target) -> list:
    sc = scene()
    path, sha, _ = file_of(asset, ("main",))
    img = canon_io.load_image(path, check_existing=True)
    stamp(img, asset, sha)
    ob = bpy.data.objects.new(str(asset.get("name")), None)
    ob.empty_display_type = "IMAGE"
    ob.data = img
    coll = collection(sc, opts)
    coll.objects.link(ob)
    ob.location = drop_point(sc, target)
    stamp(ob, asset, sha)
    return [entry("object", ob, datablock=img.name, object=ob.name, collection=coll.name, location=[round(v, 6) for v in ob.location], bytes_loaded=os.path.getsize(path))]


def add_clip(asset, opts, target) -> list:
    sc = scene()
    path, sha, _ = file_of(asset, ("main", "proxy"))
    if where(target) == "sequencer":
        se = sc.sequence_editor or sc.sequence_editor_create()
        used = {s.channel for s in se.strips_all}
        channel = next(c for c in range(1, 129) if c not in used)
        strip = se.strips.new_movie(str(asset.get("name")), path, channel, sc.frame_current)
        stamp(strip, asset, sha)
        return [{"kind": "strip", "datablock": None, "name": strip.name, "channel": channel, "frame_start": strip.frame_start}]
    clip = bpy.data.movieclips.load(path)
    clip.name = str(asset.get("name"))
    stamp(clip, asset, sha)
    return [entry("movieclip", clip, frames=clip.frame_duration, size=list(clip.size))]


def _action_bones(act) -> set:
    names = set()
    for layer in act.layers:
        for strip in layer.strips:
            for bag in strip.channelbags:
                for fc in bag.fcurves:
                    m = _BONE.match(fc.data_path)
                    if m:
                        names.add(m.group(1))
    return names


def apply_animation(asset, opts, target) -> list:
    arm = target_object(target, ("ARMATURE",)) if where(target).startswith("object:") else bpy.context.view_layer.objects.active
    if arm is None or arm.type != "ARMATURE":
        raise PlaceError("apply_animation needs an armature: select one or pass target object:<armature>")
    path, sha, _ = file_of(asset, ("main",))
    if not path.lower().endswith(".blend"):
        raise PlaceError(f"only a .blend action is placeable yet; {os.path.basename(path)} is not one: import it (File > Import), save its action in a .blend and ingest that")
    act = load_blend(path, "actions", str(asset.get("name")), "action")
    missing = sorted(_action_bones(act) - {b.name for b in arm.data.bones})
    if missing:
        raise PlaceError(f"{arm.name} has no bones named {missing[:30]}: map them with animation_retarget, then place the retargeted clip")
    stamp(act, asset, sha)
    ad = arm.animation_data or arm.animation_data_create()
    if opts.get("as_nla_strip"):                                  # to the timeline: a new NLA track at the current frame; the active action is left alone
        track = ad.nla_tracks.new()
        track.name = act.name
        strip = track.strips.new(act.name, int(bpy.context.scene.frame_current), act)
        return [{"kind": "nla_strip", "datablock": act.name, "name": strip.name, "object": arm.name, "track": track.name,
                 "frame_start": strip.frame_start, "frame_end": strip.frame_end}]
    ad.action = act
    if ad.action_slot is None and len(act.slots):
        ad.action_slot = act.slots[0]
    return [entry("action", act, object=arm.name, slot=ad.action_slot.identifier if ad.action_slot else None)]


def attach_rig(asset, opts, target) -> list:
    mesh = target_object(target, ("MESH",))
    placed, _, _ = place_rig_objects(asset, opts, target)
    arms = [bpy.data.objects[p["object"]] for p in placed if bpy.data.objects[p["object"]].type == "ARMATURE"]
    if not arms:
        raise PlaceError(f"{asset.get('name')!r} holds no armature")
    arm = arms[0]
    if mesh is not None:
        mw = mesh.matrix_world.copy()
        mesh.parent = arm
        mesh.matrix_world = mw
        mod = mesh.modifiers.new("Armature", "ARMATURE")
        mod.object = arm
        for p in placed:
            if p["object"] == arm.name:
                p["bound"] = mesh.name
    return placed
