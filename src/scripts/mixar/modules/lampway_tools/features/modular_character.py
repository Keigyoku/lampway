# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""modular_character: a typed manifest of a character's interchangeable parts, one shared armature, the outfit matrix that proves every allowed outfit
covers the body, and only then a hidden-body variant (a copy) and per-part exports with the same armature (specs/wiki/modular_character.md).

Coverage is measured, not assumed: a ray from every body face centre along its normal either meets a part of the outfit (covered) or not. The region an
outfit must cover is the union of what any allowed outfit covers, so an outfit with a gap leaves faces of that union uncovered. A body vertex lying just
outside a garment's surface (within PEN_RANGE_M of it, on its outer side) pokes through. The matrix is stamped with a hash of the parts, the armature's
rest pose and the outfits; hidden_body refuses a missing, failing or stale matrix. The full body is never deleted."""

import hashlib
import json
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

from . import clearance as _cl
from . import common as C
from . import rig as _rig
from . import weights as _w
from . import workflows as _wf

ROLES = ("head", "body", "hands", "hair", "garment", "accessory")
KINDS = ("fixed", "deforming")
SIDES = ("left", "right", "center", "paired")
COVER_RANGE_M = 0.3          # [UNVERIFIED] how far out a garment may sit and still count as covering a face
PEN_RANGE_M = 0.02           # [UNVERIFIED] a body vertex this close to a garment, on its outer side, pokes through
SIDE_EPS_M = 0.02
GAP = "test every wardrobe combination first"


def _dir(root, cid) -> Path:
    if not str(cid or "").strip() or any(c in str(cid) for c in "/\\") or str(cid).startswith("."):
        raise C.FeatureError("character_id is a plain name (no slashes)")
    return Path(root) / str(cid)


def _load(root, cid) -> dict:
    p = _dir(root, cid) / "manifest.json"
    if not p.exists():
        raise C.FeatureError(f"no manifest for {cid!r}: call action=manifest with the parts and the armature first")
    return json.loads(p.read_text(encoding="utf-8"))


def _rest_hash(arm) -> str:
    rows = [[b.name] + [round(x, 6) for r in b.matrix_local for x in r] + [round(b.length, 6)] for b in arm.data.bones]
    return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()


def _armature_of(ob):
    for m in ob.modifiers:
        if m.type == "ARMATURE" and m.object is not None:
            return m.object
    return ob.parent if ob.parent is not None and ob.parent.type == "ARMATURE" else None


def _check_part(p) -> dict:
    if not isinstance(p, dict) or not p.get("object"):
        raise C.FeatureError("each part is {object, role, fixed_or_deforming, wearer_side, bone}")
    name = p["object"]
    C.need_object(name)
    if p.get("role") not in ROLES:
        raise C.FeatureError(f"part {name!r}: role {p.get('role')!r} is not one of {', '.join(ROLES)}")
    if p.get("fixed_or_deforming", "deforming") not in KINDS:
        raise C.FeatureError(f"part {name!r}: fixed_or_deforming is fixed | deforming")
    if p.get("wearer_side", "center") not in SIDES:
        raise C.FeatureError(f"part {name!r}: wearer_side is {' | '.join(SIDES)}")
    if p.get("fixed_or_deforming") == "fixed" and not p.get("bone"):
        raise C.FeatureError(f"part {name!r} is fixed: a rigid part names its bone (one bone at full weight)")
    return {"object": name, "role": p["role"], "fixed_or_deforming": p.get("fixed_or_deforming", "deforming"),
            "wearer_side": p.get("wearer_side", "center"), "bone": p.get("bone")}


def manifest(root, character_id, parts, armature, allowed_outfits=None, poses="rest") -> dict:
    arm = C.need_object(armature, "ARMATURE")
    if not parts:
        raise C.FeatureError("a manifest needs the parts: [{object, role, fixed_or_deforming, wearer_side, bone}]")
    rows = [_check_part(p) for p in parts]
    ids = [r["object"] for r in rows]
    if len(set(ids)) != len(ids):
        raise C.FeatureError("a part is listed twice")
    for r in rows:
        if r["bone"] and r["bone"] not in arm.data.bones:
            raise C.FeatureError(f"part {r['object']!r} names bone {r['bone']!r}, which {arm.name} lacks; the bones are: {sorted(b.name for b in arm.data.bones)[:30]}")
    outfits = [list(o) for o in (allowed_outfits or [])]
    for o in outfits:
        bad = [x for x in o if x not in ids]
        if bad or not o:
            raise C.FeatureError(f"an outfit lists parts that are not in the manifest: {bad or 'an empty outfit'}")
    mats = {}
    for r in rows:
        for s in bpy.data.objects[r["object"]].material_slots:
            if s.material:
                mats.setdefault(s.material.name, set()).add(r["object"])
    man = {"character_id": str(character_id), "source_part_ids": ids, "target_skeleton": arm.name, "rest_pose": _rest_hash(arm),
           "unit_scale": float(bpy.context.scene.unit_settings.scale_length), "wearer_left_right": {r["object"]: r["wearer_side"] for r in rows},
           "fixed_deforming": {r["object"]: r["fixed_or_deforming"] for r in rows}, "shared_materials": sorted(m for m, o in mats.items() if len(o) > 1),
           "allowed_outfits": outfits, "tested_poses": [], "accepted_checkpoint": None, "parts": rows, "poses": poses}
    d = _dir(root, character_id)
    d.mkdir(parents=True, exist_ok=True)
    (d / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return {"manifest": str((d / "manifest.json").relative_to(root)), "parts": ids, "allowed_outfits": outfits}


def _shared(man) -> object:
    arms = {r["object"]: _armature_of(bpy.data.objects[r["object"]]) for r in man["parts"]}
    names = {k: (v.name if v else None) for k, v in arms.items()}
    bound = {v for v in names.values() if v}
    if len(bound) > 1:
        raise C.FeatureError("all parts must share one armature: " + ", ".join(f"{k} -> {v}" for k, v in names.items() if v))
    return (next(a for a in arms.values() if a) if bound else None), sorted(k for k, v in names.items() if not v)


def _centroid_x(ob, arm) -> float:
    P = _rig._evaluated(ob)
    c = Vector(P.mean(axis=0).tolist())
    return float((arm.matrix_world.inverted() @ c).x) if arm else float(c.x)


def validate(root, character_id) -> dict:
    man = _load(root, character_id)
    for r in man["parts"]:
        C.need_object(r["object"])
    bpy.context.view_layer.update()
    arm, unbound = _shared(man)
    shared = arm is not None and not unbound and arm.name == man["target_skeleton"]
    rest_equal = bool(arm is not None and _rest_hash(arm) == man["rest_pose"])
    scales = [tuple(round(x, 4) for x in bpy.data.objects[r["object"]].matrix_world.to_scale()) for r in man["parts"]]
    unit_equal = len(set(scales)) == 1 and abs(scales[0][0] - scales[0][1]) < 1e-4 and abs(scales[0][0] - scales[0][2]) < 1e-4
    sides, sides_ok = {}, True
    for r in man["parts"]:
        want = r["wearer_side"]
        if want == "paired":
            continue
        x = _centroid_x(bpy.data.objects[r["object"]], arm)
        got = "left" if x > SIDE_EPS_M else "right" if x < -SIDE_EPS_M else "center"           # the figure faces -Y: its LEFT is +X
        sides[r["object"]] = {"declared": want, "measured": got}
        sides_ok = sides_ok and got == want
    weights = {}
    for r in man["parts"]:
        if r["fixed_or_deforming"] == "deforming" and arm is not None:
            try:
                weights[r["object"]] = bool(_w.audit(r["object"], arm.name)["pass"])
            except C.FeatureError as exc:
                weights[r["object"]] = f"fails: {exc}"
    weights_ok = all(v is True for v in weights.values())
    return {"shared_armature": shared, "armature": arm.name if arm else None, "unbound_parts": unbound, "rest_pose_equal": rest_equal, "unit_scale_equal": unit_equal,
            "scales": dict(zip([r["object"] for r in man["parts"]], scales)), "sides_ok": sides_ok, "sides": sides, "weight_audit": weights,
            "pass": bool(shared and rest_equal and unit_equal and sides_ok and weights_ok)}


def _faces(ob):
    """World-space face centres and unit normals of the evaluated (posed) mesh."""
    ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
    me = ev.to_mesh()
    n = len(me.polygons)
    cen, nrm = np.empty(n * 3), np.empty(n * 3)
    me.polygons.foreach_get("center", cen)
    me.polygons.foreach_get("normal", nrm)
    m = np.array(ev.matrix_world)
    cen = (m[:3, :3] @ cen.reshape(-1, 3).T).T + m[:3, 3]
    nrm = (np.linalg.inv(m[:3, :3]).T @ nrm.reshape(-1, 3).T).T
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    ev.to_mesh_clear()
    return cen, nrm


def _tree(names):
    V, T = [], []
    for name in names:
        ev = bpy.data.objects[name].evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = ev.to_mesh()
        me.calc_loop_triangles()
        base = len(V)
        V += [ev.matrix_world @ v.co for v in me.vertices]
        T += [tuple(base + i for i in t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
    return BVHTree.FromPolygons(V, T)


def _stamp(man, arm) -> str:
    parts = [[r["object"], _wf.mesh_hash(bpy.data.objects[r["object"]]), [round(x, 6) for row in bpy.data.objects[r["object"]].matrix_world for x in row]] for r in man["parts"]]
    return hashlib.sha256(json.dumps([parts, _rest_hash(arm) if arm else None, man["allowed_outfits"], man.get("poses")]).encode()).hexdigest()


def _with_pose(arm, pose):
    moved = []
    for b in (pose.get("bones") or ([{"bone": pose["bone"], "rotate": pose.get("rotate", [0, 0, 0])}] if pose.get("bone") else [])):
        pb = arm.pose.bones.get(b["bone"]) if arm else None
        if pb is None:
            continue                                                       # a bone the armature lacks is skipped, as in the clearance poses
        pb.rotation_mode = "XYZ"
        moved.append((pb, tuple(pb.rotation_euler)))
        pb.rotation_euler = [math.radians(float(a)) for a in b.get("rotate", [0, 0, 0])]
    bpy.context.view_layer.update()
    return moved


def outfit_matrix(root, character_id, poses=None) -> dict:
    man = _load(root, character_id)
    for r in man["parts"]:
        C.need_object(r["object"])
    if not man["allowed_outfits"]:
        raise C.FeatureError("the manifest has no allowed_outfits: list them in action=manifest")
    bodies = [r["object"] for r in man["parts"] if r["role"] == "body"]
    if len(bodies) != 1:
        raise C.FeatureError(f"outfit_matrix needs exactly one part with role body (found {bodies or 'none'})")
    bpy.context.view_layer.update()
    arm, _ = _shared(man)
    body = bpy.data.objects[bodies[0]]
    pose_list = _cl._poses(poses if poses is not None else man.get("poses") or "rest")
    per_pose = []
    for pose in pose_list:
        moved = _with_pose(arm, pose)
        try:
            cen, nrm = _faces(body)
            Pv = _rig._evaluated(body)
            covered, pen = {}, {}
            for o in man["allowed_outfits"]:
                tree = _tree(o)
                cov = np.zeros(len(cen), dtype=bool)
                for i in range(len(cen)):
                    hit = tree.ray_cast(Vector((cen[i] + nrm[i] * 1e-4).tolist()), Vector(nrm[i].tolist()), COVER_RANGE_M)
                    cov[i] = hit[0] is not None
                p = 0
                for v in Pv:
                    loc, n_, _i, dist = tree.find_nearest(Vector(v.tolist()), PEN_RANGE_M)
                    if loc is not None and (Vector(v.tolist()) - loc).dot(n_) > 1e-6:
                        p += 1
                covered[tuple(o)], pen[tuple(o)] = cov, p
        finally:
            for pb, before in moved:
                pb.rotation_euler = before
            bpy.context.view_layer.update()
        union = np.any(np.stack(list(covered.values())), axis=0)
        per_pose.append({"pose": pose.get("name") or "pose", "covered": covered, "pen": pen, "union": union})
    rows, all_cov = [], None
    for o in man["allowed_outfits"]:
        k = tuple(o)
        by_pose = [{"pose": pp["pose"], "uncovered_body_faces": int((pp["union"] & ~pp["covered"][k]).sum()), "penetrating_vertices": pp["pen"][k]} for pp in per_pose]
        unc, pv = max(b["uncovered_body_faces"] for b in by_pose), max(b["penetrating_vertices"] for b in by_pose)
        rows.append({"outfit": o, "uncovered_body_faces": unc, "penetrating_vertices": pv, "pass": unc == 0 and pv == 0, "poses": by_pose})
        for pp in per_pose:
            all_cov = pp["covered"][k] if all_cov is None else (all_cov & pp["covered"][k])
    ok = all(r["pass"] for r in rows)
    rec = {"stamp": _stamp(man, arm), "pass": ok, "matrix": rows, "body": body.name, "covered_by_every_outfit": [int(i) for i in np.flatnonzero(all_cov)],
           "poses": [pp["pose"] for pp in per_pose], "cover_range_m": COVER_RANGE_M, "pen_range_m": PEN_RANGE_M}
    d = _dir(root, character_id)
    (d / "outfit_matrix.json").write_text(json.dumps(rec), encoding="utf-8")
    man["tested_poses"] = rec["poses"]
    (d / "manifest.json").write_text(json.dumps(man, indent=1), encoding="utf-8")
    return {"pass": ok, "matrix": rows, "body": body.name, "poses": rec["poses"], "faces_covered_by_every_outfit": len(rec["covered_by_every_outfit"]),
            "note": f"covered = a ray from the face centre along its normal meets the outfit within {COVER_RANGE_M} m [UNVERIFIED range]"}


def hidden_body(root, character_id) -> dict:
    man = _load(root, character_id)
    p = _dir(root, character_id) / "outfit_matrix.json"
    if not p.exists():
        raise C.FeatureError(f"{GAP}: no outfit matrix for {character_id!r} (action=outfit_matrix); deleting covered skin before that can expose holes on a later outfit")
    rec = json.loads(p.read_text(encoding="utf-8"))
    if not rec["pass"]:
        bad = [r["outfit"] for r in rec["matrix"] if not r["pass"]]
        raise C.FeatureError(f"{GAP}: the outfit matrix fails for {bad}; fix those outfits and run outfit_matrix again")
    for r in man["parts"]:
        C.need_object(r["object"])
    arm, _ = _shared(man)
    if _stamp(man, arm) != rec["stamp"]:
        raise C.FeatureError(f"{GAP}: a part, the armature's rest pose or the outfits changed since the matrix; run outfit_matrix again")
    body = bpy.data.objects[rec["body"]]
    new = C.duplicate(body, "_hidden")
    import bmesh
    bm = bmesh.new()
    bm.from_mesh(new.data)
    bm.faces.ensure_lookup_table()
    gone = [bm.faces[i] for i in rec["covered_by_every_outfit"] if i < len(bm.faces)]
    bmesh.ops.delete(bm, geom=gone, context="FACES")
    bm.to_mesh(new.data)
    bm.free()
    return {"object": new.name, "source": body.name, "removed_faces": len(gone), "kept_faces": len(new.data.polygons),
            "note": "a copy: the full body is never deleted"}


def export_parts(root, character_id, out_dir, resolve) -> dict:
    man = _load(root, character_id)
    for r in man["parts"]:
        C.need_object(r["object"])
    arm, unbound = _shared(man)
    if arm is None or unbound:
        raise C.FeatureError(f"every part is bound to the one armature before export; unbound: {unbound or 'all'}")
    out = Path(resolve(str(Path(out_dir) / str(character_id))))
    out.mkdir(parents=True, exist_ok=True)
    selected, active = list(bpy.context.selected_objects), bpy.context.view_layer.objects.active
    files = []
    try:
        for r in man["parts"]:
            ob = bpy.data.objects[r["object"]]
            for o in bpy.context.view_layer.objects:
                o.select_set(False)
            ob.select_set(True)
            arm.select_set(True)
            bpy.context.view_layer.objects.active = ob
            f = out / f"{ob.name}.fbx"
            bpy.ops.export_scene.fbx(filepath=str(f), use_selection=True, add_leaf_bones=False, mesh_smooth_type="FACE", path_mode="STRIP")
            files.append({"part": ob.name, "path": str(f.relative_to(root)), "sha256": hashlib.sha256(f.read_bytes()).hexdigest()})
    finally:
        for o in bpy.context.view_layer.objects:
            o.select_set(o in selected)
        bpy.context.view_layer.objects.active = active
    return {"files": files, "armature": arm.name}


def run(root, action, character_id, parts=None, armature=None, allowed_outfits=None, poses=None, out_dir="export_parts", resolve=None) -> dict:
    if action == "manifest":
        return manifest(root, character_id, parts, armature, allowed_outfits, poses or "rest")
    if action == "validate":
        return validate(root, character_id)
    if action == "outfit_matrix":
        return outfit_matrix(root, character_id, poses)
    if action == "hidden_body":
        return hidden_body(root, character_id)
    if action == "export_parts":
        return export_parts(root, character_id, out_dir, resolve)
    raise C.FeatureError(f"unknown action {action!r}; manifest | validate | outfit_matrix | hidden_body | export_parts")
