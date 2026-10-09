# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""The rig tools' Blender side (specs/canon/rig_tools): read an armature, hand the numbers to rig_tools/core, write receipts.

rig_inspect reads any skeleton and says what it is (never refuses on a defect of the rig: it reports it) and stamps the armature with its
receipt's sha256: every other rig tool refuses an armature it did not read, or one that changed since. rig_map writes map.json (a receipt that
reproduces byte for byte). rig_normalize applies the object scale and the unit factor exactly (rest joints scaled, location keys scaled,
rotation keys untouched; a non-uniform scale only on an unanimated rig), checks the world drift on 8 frames and rolls back above 1e-6 m.
rig_readback imports an FBX through canon_io and compares every bone's rest to the reference at the bind_mismatch bars (canon 21).
Never: rename the user's objects, change preferences, delete the user's actions or objects, exec scene text."""

import json
import math
import os
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix

from . import common as C
from ..rig_tools import core as RC
from ..canon_geom.native_topology import AUXILIARY

MANNY = Path(__file__).resolve().parents[1] / "rig_convert" / "recipes" / "anim-profile-manny.json"
STAMP = "lw_rig_inspect"
UNITS = {"m": 1.0, "cm": 0.01, "in": 0.0254}


def _armature(name):
    ob = bpy.data.objects.get(name)
    if ob is None or ob.type != "ARMATURE":
        arms = sorted(o.name for o in bpy.data.objects if o.type == "ARMATURE")
        raise C.FeatureError(f"no armature named {name!r}; the armatures are: {', '.join(arms) or 'none'}")
    return ob


def read(ob):
    """{names, parents, heads (world m), frames (world 3x3, columns X Y Z), deform, ...} of the armature's rest."""
    mw = ob.matrix_world
    names, parents, heads, frames = [], {}, {}, {}
    for b in ob.data.bones:
        names.append(b.name)
        parents[b.name] = b.parent.name if b.parent else None
        heads[b.name] = list(mw @ b.head_local)
        M = np.array((mw @ b.matrix_local).to_3x3())
        frames[b.name] = M / np.linalg.norm(M, axis=0)
    return {"names": names, "parents": parents, "heads": heads, "frames": frames}


def _fingerprint(ob, rig):
    return RC.sha({"names": rig["names"], "parents": rig["parents"], "heads": {k: [round(x, 9) for x in v] for k, v in rig["heads"].items()},
                   "frames": {k: np.round(v, 9).tolist() for k, v in rig["frames"].items()}, "matrix": [list(r) for r in ob.matrix_world]})


def reference_convention(ob, rig=None):
    """Verify private independent native binds for writer-axis routing only."""
    raw = ob.get("lw_native_reference_bind")
    if not raw:
        return None
    rig = rig or read(ob)
    rig = {**rig, "scales": {b.name: np.linalg.norm(np.array((ob.matrix_world @ b.matrix_local).to_3x3()), axis=0)
                            for b in ob.data.bones}}
    try:
        return RC.reference_bind_convention(rig, json.loads(raw), _fingerprint(ob, rig))
    except (ValueError, TypeError, KeyError, RC.RigRefused) as exc:
        raise C.FeatureError(str(exc)) from None


def _fcurves(action):
    """Every f-curve of an action: the legacy list, or (Blender 4.4+) the layered channelbags."""
    out = list(getattr(action, "fcurves", []) or [])
    for layer in getattr(action, "layers", []) or []:
        for strip in layer.strips:
            for bag in getattr(strip, "channelbags", []) or []:
                out += list(bag.fcurves)
    return out


def _actions(ob):
    ad = ob.animation_data
    acts = []
    if ad is not None:
        if ad.action is not None:
            acts.append(ad.action)
        for tr in ad.nla_tracks:
            acts += [s.action for s in tr.strips if s.action is not None and s.action not in acts]
    return acts


def _bone_of(path):
    if path.startswith('pose.bones["'):
        return path[len('pose.bones["'):path.index('"]')]
    return None


def _reference():
    p = json.loads(MANNY.read_text())
    bones = {b["name"]: b for b in p["bones"]}
    torso = [(s, bones[s]["bind"]["translation"]) for s in RC.TORSO]
    zs = [b["bind"]["translation"][2] for b in p["bones"]]
    return {"name": "ue5_manny (rig_convert/recipes/anim-profile-manny.json)", "torso": torso, "height_m": (max(zs) - min(zs)) / 100.0,
            "sha256": RC.sha(p["bones"])}


def _tables():
    return {f: RC.load_family(f)["map"] for f in RC.families()}


def _single_child(rig):
    kids = {}
    for b, p in rig["parents"].items():
        if p is not None:
            kids.setdefault(p, []).append(b)
    return {b: k[0] for b, k in kids.items() if len(k) == 1 and np.linalg.norm(np.subtract(rig["heads"][k[0]], rig["heads"][b])) > 1e-6}


def convention_angles(rig):
    """{bone: angle of its local Y to its head -> single child line}, limb bones only: UE's ik_* bones copy their target's (or the root's)
    frame and point at nothing, so they say nothing about the rig's convention."""
    return {b: RC.along_axis_angle(rig["frames"][b], rig["heads"][b], rig["heads"][c]) for b, c in _single_child(rig).items()
            if b not in RC.IK_TARGETS and b not in AUXILIARY}


def inspect(armature, reference="", family="auto", profile="ue5_body"):
    ob = _armature(armature)
    if profile not in RC.REQUIRED:
        raise C.FeatureError(f"profile is one of {', '.join(RC.REQUIRED)}")
    rig = read(ob)
    names = rig["names"]
    tables = _tables()
    fam = {"name": None, "hits": {f: sum(1 for s in t.values() if s in set(names)) for f, t in tables.items()}}
    try:
        if family == "auto":
            fam["name"], fam["hits"] = RC.detect_family(names, tables)
        else:
            RC.load_family(family)
            fam["name"] = family
    except RC.RigRefused as exc:
        fam["note"] = str(exc)
    mapped, missing = RC.map_slots(names, tables[fam["name"]], RC.REQUIRED[profile]) if fam["name"] else ({}, list(RC.REQUIRED[profile]))
    vals = list(convention_angles(rig).values())
    joint_class = RC.classify_convention(vals)
    reference_class = reference_convention(ob, rig)
    ref = _reference()
    zs = [h[2] for h in rig["heads"].values()]
    height = (max(zs) - min(zs)) if zs else 0.0
    try:
        factor, ratio = RC.unit_factor(height, ref["height_m"])
    except RC.RigRefused as exc:
        factor, ratio = None, height / ref["height_m"] if ref["height_m"] else None
        unit_note = str(exc)
    else:
        unit_note = None
    acts = _actions(ob)
    keys = {"rotation_keys": 0, "location_keys": 0, "scale_keys": 0}
    ranges = {}
    for a in acts:
        ranges[a.name] = [float(a.frame_range[0]), float(a.frame_range[1])]
        for fc in _fcurves(a):
            if _bone_of(fc.data_path) is None:
                continue
            kind = fc.data_path.rsplit(".", 1)[-1]
            n = len(fc.keyframe_points)
            if kind.startswith("rotation"):
                keys["rotation_keys"] += n
            elif kind == "location":
                keys["location_keys"] += n
            elif kind == "scale":
                keys["scale_keys"] += n
    bones = ob.data.bones
    receipt = {"armature": ob.name, "bones": len(bones), "deform": sum(1 for b in bones if b.use_deform),
               "roots": sorted(b.name for b in bones if b.parent is None), "family": fam,
               "slots": {"mapped": mapped, "missing_required": missing, "required_set": profile},
               "convention": {"class": reference_class or joint_class, "joint_class": joint_class,
                              "evidence": "independent_native_reference" if reference_class else "joint_axes",
                              "bones_measured": len(vals),
                              "angles_deg": {"median": round(float(np.median(vals)), 6) if vals else None, "min": round(min(vals), 6) if vals else None,
                                             "max": round(max(vals), 6) if vals else None}},
               "units": {"scene_scale_length": float(bpy.context.scene.unit_settings.scale_length), "object_scale": [round(v, 9) for v in ob.scale],
                         "height_m": round(height, 6), "reference": ref["name"], "ratio_to_reference": round(ratio, 6) if ratio else None,
                         "factor": factor, **({"note": unit_note} if unit_note else {})},
               "animation": {"actions": [a.name for a in acts], "frame_ranges": ranges, **keys},
               "constraints": sum(len(pb.constraints) for pb in ob.pose.bones),
               "bbones": sorted(b.name for b in bones if b.bbone_segments > 1),
               "leaf_bones": sorted(b.name for b in bones if not b.children and b.name.lower().endswith(("_end", "_leaf", "end_site"))),
               "helpers": sorted(b.name for b in bones if not b.use_deform),
               "sha256": {"input": _fingerprint(ob, rig), "reference": ref["sha256"]}}
    receipt["sha256"]["receipt"] = RC.sha(receipt)
    ob[STAMP] = json.dumps({"receipt": receipt["sha256"]["receipt"], "input": receipt["sha256"]["input"]})
    return receipt


def _inspected(ob):
    raw = ob.get(STAMP)
    if not raw:
        raise C.FeatureError(f"{ob.name} was not read by rig_inspect: run lampway_rig_inspect armature={ob.name} first")
    if json.loads(raw)["input"] != _fingerprint(ob, read(ob)):
        raise C.FeatureError(f"{ob.name} changed since rig_inspect read it: run lampway_rig_inspect again")
    return json.loads(raw)


def _publish(path, data):
    p = Path(path)
    if p.exists():
        if p.read_bytes() != data:
            raise C.FeatureError(f"{p} exists with different content: a map is never overwritten; choose another out")
        return "unchanged"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return "written"


def map_(armature, out, root, family="auto", profile="ue5_body", synthesize=True, dry_run=False):
    ob = _armature(armature)
    stamp = _inspected(ob)
    if profile not in RC.REQUIRED:
        raise C.FeatureError(f"profile is one of {', '.join(RC.REQUIRED)}")
    rig = read(ob)
    names = rig["names"]
    tables = _tables()
    if family == "auto":
        try:
            fam, hits = RC.detect_family(names, tables)
        except RC.RigRefused as exc:
            raise C.FeatureError(str(exc)) from None
        table, tables_sha = tables[fam], RC.sha(tables)
    elif str(family).endswith(".json"):
        doc = json.loads(Path(root, family).read_text() if not os.path.isabs(family) else Path(family).read_text())
        fam, table, hits = doc.get("family", "custom"), doc["map"], None
        tables_sha = RC.sha(table)
    else:
        try:
            fam, table = family, RC.load_family(family)["map"]
        except RC.RigRefused as exc:
            raise C.FeatureError(str(exc)) from None
        hits, tables_sha = {fam: sum(1 for s in table.values() if s in set(names))}, RC.sha(table)
    m, missing = RC.map_slots(names, table, RC.REQUIRED[profile])
    if missing:
        raise C.FeatureError(f"required slots missing for {profile} with family {fam}: {', '.join(missing)} (no synthesis rule fills a required slot)")
    dup = sorted({s for s in m.values() if list(m.values()).count(s) > 1})
    if dup:
        raise C.FeatureError(f"two slots map to one bone: {', '.join(dup)}")
    ref = _reference()
    synthesized = {}
    if synthesize:
        present = [(s, rig["heads"][m[s]]) for s in RC.TORSO if s in m]
        missing_torso = [s for s in RC.TORSO if s not in m]
        if missing_torso:
            try:
                fr = RC.chain_fractions(ref["torso"])
                RC.synthesize_chain(present, fr)
            except RC.RigRefused as exc:
                raise C.FeatureError(f"torso slots {', '.join(missing_torso)} cannot be synthesized: {exc}") from None
            synthesized = {s: {"chain": "torso", "fraction": fr[s], "reference": ref["name"]} for s in missing_torso}
    doc = {"schema": "lampway.rig-map/1", "armature": ob.name, "family": fam, "hits": hits, "required_set": profile,
           "map": {s: {"source": src, "by": "table"} for s, src in sorted(m.items())}, "synthesized": synthesized,
           "unmapped": sorted(set(names) - set(m.values())),
           "collision_renames": sorted(n for n in names if n in RC.UE_SLOTS and m.get(n) != n),
           "sha256": {"source_rest": stamp["input"], "reference_rest": ref["sha256"], "tables": tables_sha}}
    data = (json.dumps(doc, sort_keys=True, indent=1) + "\n").encode()
    target = Path(root, out)
    state = "dry_run" if dry_run else _publish(target, data)
    return {**doc, "out": str(target), "state": state, "sha256_file": RC.sha(doc)}


def _world_heads(ob, frames):
    scene = bpy.context.scene
    keep = scene.frame_current
    out = {}
    for f in frames:
        scene.frame_set(int(f))
        out[f] = {pb.name: np.array(ob.matrix_world @ pb.head) for pb in ob.pose.bones}
    scene.frame_set(keep)
    return out


def _uniform_rest_scale(ob, scale):
    """Scale joint coordinates without reconstructing every parent-local roll.

    BKE_armature_transform re-extracts roll recursively even for a scalar
    matrix. Edit coordinates keep the authored armature-space roll instead.
    """
    from .. import canon_io
    selection = canon_io._selection()
    active = bpy.context.view_layer.objects.active
    mode = active.mode if active else "OBJECT"
    hidden, viewport = ob.hide_get(), ob.hide_viewport
    rest = {b.name: (b.matrix_local.copy(), b.length) for b in ob.data.bones}
    try:
        if active and active.mode != "OBJECT":
            bpy.ops.object.mode_set(mode="OBJECT")
        ob.hide_viewport = False
        ob.hide_set(False)
        C.activate(ob)
        bpy.ops.object.mode_set(mode="EDIT")
        for b in ob.data.edit_bones:
            matrix, length = rest[b.name]
            matrix.translation *= scale
            b.matrix = matrix
            b.length = length * scale
            b.head_radius *= scale
            b.tail_radius *= scale
            b.envelope_distance *= scale
            b.bbone_x *= scale
            b.bbone_z *= scale
        bpy.ops.object.mode_set(mode="OBJECT")
    finally:
        if ob.mode == "EDIT":
            bpy.ops.object.mode_set(mode="OBJECT")
        ob.hide_set(hidden)
        ob.hide_viewport = viewport
        canon_io._restore_selection(selection)
        if active and mode != "OBJECT":
            bpy.ops.object.mode_set(mode=mode)


def normalize(armature, unit="auto", apply_scale=True, dry_run=True):
    ob = _armature(armature)
    _inspected(ob)
    receipt0 = json.loads(ob[STAMP])
    if unit not in ("auto", *UNITS):
        raise C.FeatureError(f"unit is auto | {' | '.join(UNITS)}")
    S = np.array(ob.scale, float) if apply_scale else np.ones(3)
    if (S <= 0).any():
        raise C.FeatureError(f"{ob.name} has a negative or zero scale {S.tolist()}: mirror it as a decision, never by applying scale")
    if unit == "auto":
        u = 1.0
    else:
        u = UNITS[unit]
    total = S * u
    uniform = bool(np.ptp(total) <= 1e-12 * max(1.0, float(np.max(np.abs(total)))))
    acts = _actions(ob)
    rot_bones = sorted({_bone_of(fc.data_path) for a in acts for fc in _fcurves(a)
                        if _bone_of(fc.data_path) and fc.data_path.rsplit(".", 1)[-1].startswith("rotation") and len(fc.keyframe_points)})
    if not uniform and rot_bones:
        raise C.FeatureError(f"a non-uniform scale {total.tolist()} cannot be applied to an animated rig exactly (rotation keys on "
                             f"{', '.join(rot_bones)}): apply it in the source application, or remove the animation first")
    loc_curves = [fc for a in acts for fc in _fcurves(a) if _bone_of(fc.data_path) and fc.data_path.endswith(".location")]
    plan = {"armature": ob.name, "unit": unit, "unit_factor": u, "applied_scale": [round(float(x), 9) for x in total], "uniform": uniform,
            "keys_scaled": {"bones": sorted({_bone_of(fc.data_path) for fc in loc_curves}), "fcurves": len(loc_curves)}}
    if np.allclose(total, 1.0):
        return {**plan, "dry_run": dry_run, "changed": False, "max_world_drift_m": 0.0}
    if dry_run:
        return {**plan, "dry_run": True, "how": "dry_run=false applies it (rest joints and location keys scaled, rotation keys untouched)"}
    ranges = [a.frame_range for a in acts] or [(1, 1)]
    lo, hi = min(r[0] for r in ranges), max(r[1] for r in ranges)
    frames = sorted({int(round(x)) for x in np.linspace(lo, hi, 8)})
    before = _world_heads(ob, frames)
    original_data = ob.data
    backup_data, backup_scale = ob.data.copy(), ob.scale.copy()
    backup_locations = {pb.name: pb.location.copy() for pb in ob.pose.bones}
    backup_keys = [(k, k.co.copy(), k.handle_left.copy(), k.handle_right.copy())
                   for fc in loc_curves for k in fc.keyframe_points]
    try:
        rest = {b.name: np.array(b.matrix_local.to_3x3()) for b in ob.data.bones}
        if uniform:
            _uniform_rest_scale(ob, float(total[0]))
        else:
            ob.data.transform(Matrix.Diagonal((*total, 1.0)))
        for fc in loc_curves:                       # uniform: the location keys scale with the rest (rotation keys never change)
            s = float(total[0])
            for k in fc.keyframe_points:
                k.co[1] *= s
                k.handle_left[1] *= s
                k.handle_right[1] *= s
        for pb in ob.pose.bones:
            if any(abs(x) > 0 for x in pb.location):
                if uniform:
                    # Keyless channels retain their current pose between frame
                    # evaluations. They need the same transfer as keyed ones.
                    pb.location = backup_locations[pb.name] * float(total[0])
                else:
                    loc, _Rn = RC.apply_scale_loc_exact(rest[pb.name], total, list(pb.location))
                    pb.location = loc
        ob.scale = (1.0, 1.0, 1.0)
        ob.data.update_tag()                        # the pose is rebuilt from the transformed rest only when the data is tagged
        ob.update_tag(refresh={"DATA"})
        bpy.context.view_layer.update()
        after = _world_heads(ob, frames)
        T = np.array(ob.matrix_world.translation)
        # removing the object scale keeps every joint where it was; a unit factor scales the rig about its own origin on purpose
        drift = max(float(np.max(np.abs(T + u * (before[f][n] - T) - after[f][n]))) for f in frames for n in before[f])
        if drift > 1e-6:
            raise C.FeatureError(f"the applied scale moved a joint by {drift:.3g} m (> 1e-6): rolled back")
    except Exception:
        ob.data, ob.scale = backup_data, backup_scale
        for k, co, left, right in backup_keys:
            k.co, k.handle_left, k.handle_right = co, left, right
        for pb in ob.pose.bones:
            pb.location = backup_locations[pb.name]
        if original_data.users == 0:
            bpy.data.armatures.remove(original_data)
        bpy.context.view_layer.update()
        raise
    if backup_data.users == 0:
        bpy.data.armatures.remove(backup_data)
    out = {**plan, "dry_run": False, "changed": True, "frames_checked": len(frames), "max_world_drift_m": drift,
           "sha256": {"input": receipt0["input"], "output": _fingerprint(ob, read(ob))}}
    if u != 1.0:
        out["note"] = f"the unit factor {u:g} scales the rig about its origin on purpose; the drift is measured against that"
    del ob[STAMP]                                   # the rig changed: it must be inspected again before the next tool
    return out


def _bone_table(ob):
    out = {}
    for b in ob.data.bones:
        loc, q, s = (ob.matrix_world @ b.matrix_local).decompose()
        out[b.name] = {"translation": [x * 100.0 for x in loc], "rotation": [q.x, q.y, q.z, q.w], "scale": list(s)}
    return out


def readback(fbx, reference, root):
    path = Path(fbx) if os.path.isabs(fbx) else Path(root, fbx)
    if not path.is_file():
        raise C.FeatureError(f"no FBX at {path}")
    ref = _armature(reference)
    from .. import canon_io
    before = canon_io.snapshot_ids()
    try:
        rec = canon_io.import_raw(str(path), automatic_bone_orientation=False)
        arms = [bpy.data.objects[n] for n in rec["objects"] if bpy.data.objects[n].type == "ARMATURE"]
        if len(arms) != 1:
            raise C.FeatureError(f"the FBX holds {len(arms)} armatures: one is compared")
        got = _bone_table(arms[0])
        want = _bone_table(ref)
        try:
            rows = RC.readback_rows(want, got)
        except RC.RigRefused as exc:
            raise C.FeatureError(str(exc)) from None
    finally:
        canon_io.remove_new_ids(before)
    return {"verdict": "PASS" if not rows["over_tolerance"] else "FAIL", "fbx": str(path), "reference": ref.name,
            "readback": {k: v for k, v in rows.items() if k != "rows"}, "rows": rows["rows"],
            "sha256": {"fbx": rec["sha256"], "reference_rest": _fingerprint(ref, read(ref))},
            "import_settings": {"automatic_bone_orientation": False}}
