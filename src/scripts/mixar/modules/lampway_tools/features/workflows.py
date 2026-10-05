# SPDX-FileCopyrightText: 2026 Keigyoku
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""Stefan's wiki workflows as Client tools. Each is the wiki's checklist turned into measured gates on real data, composed from
the proven feature code: ``mesh_prep`` (geometry-game-mesh-preparation: branch the source, hash it, report and repair only the
defects found), ``asset_acceptance`` (engine-asset-acceptance: identity / orientation / geometry / materials gates against an
optional reference) and ``rig_armor`` (rigging-existing-armor: fit a COPY of the piece, rigid on one bone or weights transferred
from the aligned body, then measure stretch in a pose set). No model is called."""

import hashlib
import math

import bmesh
import bpy
import numpy as np

from . import common as C
from . import rig as _rig

# The wiki's eight poses (rigging-existing-armor:20), as bone rotations in the bone's OWN axes on the algorithmic rig (measured on it: an arm bone's local X
# raises it, its local Z swings it forward/back; a thigh's local X swings it forward/back; a spine bone's local Y twists). The ANGLES are approximations, not
# the wiki's numbers (it gives none): a pose is a stress test, and the captain's own poses go in through ``poses``. Bones the armature lacks are skipped.
WIKI8 = [
    ("idle", []),
    ("shoulders_raised", [("upperarm_l", [80, 0, 0]), ("upperarm_r", [80, 0, 0])]),
    ("arm_across_chest", [("upperarm_l", [0, 0, -60]), ("lowerarm_l", [0, 0, -110])]),
    ("elbow_flexion", [("lowerarm_l", [0, 0, -90]), ("lowerarm_r", [0, 0, 90])]),
    ("crouch", [("thigh_l", [-70, 0, 0]), ("thigh_r", [-70, 0, 0]), ("calf_l", [100, 0, 0]), ("calf_r", [100, 0, 0])]),
    ("torso_twist", [("spine_02", [0, 25, 0]), ("spine_03", [0, 25, 0])]),
    ("walk", [("thigh_l", [-25, 0, 0]), ("thigh_r", [25, 0, 0]), ("calf_l", [20, 0, 0]), ("upperarm_l", [0, 0, 25]), ("upperarm_r", [0, 0, 25])]),
    ("weapon_grip", [("upperarm_r", [0, 0, 40]), ("lowerarm_r", [0, 0, 80]), ("hand_r", [0, 30, 0])]),
]
SEAM_LIMIT_M = 0.01             # [UNVERIFIED default] the captain measured a 7.3 cm cuirass seam tear as a failure; 1 cm is the line this tool draws until he names one


def mesh_hash(ob) -> str:
    me = ob.data
    co = np.empty(len(me.vertices) * 3, dtype=np.float32)
    me.vertices.foreach_get("co", co)
    loops = np.empty(len(me.loops), dtype=np.int32)
    me.loops.foreach_get("vertex_index", loops)
    h = hashlib.sha256()
    h.update(co.tobytes())
    h.update(loops.tobytes())
    return h.hexdigest()


def uv_hash(ob) -> str:
    """sha256 over every UV layer (name + loop coordinates): a UV edit is a legitimate derivative with its own record."""
    h = hashlib.sha256()
    for layer in ob.data.uv_layers:
        uv = np.empty(len(layer.data) * 2, dtype=np.float32)
        layer.data.foreach_get("uv", uv)
        h.update(layer.name.encode())
        h.update(uv.tobytes())
    return h.hexdigest()


def material_hash(ob) -> str:
    return hashlib.sha256("|".join(s.material.name if s.material else "" for s in ob.material_slots).encode()).hexdigest()


def _shell_faces(bm) -> list:
    """The face indices of each connected shell."""
    bm.faces.ensure_lookup_table()
    seen, shells = set(), []
    for f in bm.faces:
        if f.index in seen:
            continue
        stack, members = [f], []
        seen.add(f.index)
        while stack:
            cur = stack.pop()
            members.append(cur.index)
            for e in cur.edges:
                for nb in e.link_faces:
                    if nb.index not in seen:
                        seen.add(nb.index)
                        stack.append(nb)
        shells.append(members)
    return shells


def shell_orientation(ob, eps=1e-4) -> list:
    """Per connected shell: the fraction of faces whose NORMAL RAY escapes the shell. A right-way-out shell is near 1; a flipped one points into itself
    (near 0) whether it is closed or an OPEN piece, which the signed-volume test cannot see. Limit: a shell with no opposite wall (a half-cylinder)
    has nothing for an inward ray to hit and reads as outward."""
    from mathutils.bvhtree import BVHTree
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    shells = _shell_faces(bm)
    shell_of = {i: k for k, members in enumerate(shells) for i in members}
    tree = BVHTree.FromBMesh(bm)
    out = []
    for k, members in enumerate(shells):
        inward = 0
        for i in members:
            f = bm.faces[i]
            hit = tree.ray_cast(f.calc_center_median() + f.normal * eps, f.normal)
            if hit[0] is not None and shell_of.get(hit[2]) == k:
                inward += 1
        out.append({"shell": k, "faces": len(members), "outward_fraction": round(1.0 - inward / len(members), 4)})
    bm.free()
    return out


def turn_flipped_shells(ob) -> int:
    """Reverse every shell that points into itself; returns how many."""
    flipped = {s_["shell"] for s_ in shell_orientation(ob) if s_["outward_fraction"] < FLIPPED_BELOW}
    if not flipped:
        return 0
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    shells = _shell_faces(bm)
    bmesh.ops.reverse_faces(bm, faces=[bm.faces[i] for k in flipped for i in shells[k]])
    bm.to_mesh(ob.data)
    bm.free()
    return len(flipped)


FLIPPED_BELOW = 0.2


def _signed_volume(ob) -> float:
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    vol = bm.calc_volume(signed=True)
    bm.free()
    return vol


def _bounds(ob):
    pts = np.array([ob.matrix_world @ v.co for v in ob.data.vertices], dtype=np.float64).reshape(-1, 3)
    return pts.min(axis=0), pts.max(axis=0)


def _pivot_offset(ob) -> float:
    lo, hi = _bounds(ob)
    return round(float(np.linalg.norm(np.asarray(ob.matrix_world.translation) - (lo + hi) / 2)), 6)


def mesh_prep(object, merge_distance=1e-5):
    src = C.need_object(object)
    before = C.mesh_report(src)
    digest = mesh_hash(src)
    branch = C.duplicate(src, "_prep")
    branch["lw_source"] = src.name
    branch["lw_source_hash"] = digest
    bm = bmesh.new()
    bm.from_mesh(branch.data)
    doubles = bmesh.ops.find_doubles(bm, verts=bm.verts, dist=merge_distance)["targetmap"]
    shells = shell_orientation(src)
    flipped = [s_["shell"] for s_ in shells if s_["outward_fraction"] < FLIPPED_BELOW]
    closed_inverted = _signed_volume(src) < 0 and before["open_boundary_edges"] == 0
    found = {"loose_vertices": before["loose_vertices"], "doubled_vertices": len(doubles),
             "inverted": closed_inverted or bool(flipped), "flipped_shells": flipped}
    if doubles:
        bmesh.ops.weld_verts(bm, targetmap=doubles)
    loose = [v for v in bm.verts if not v.link_edges]
    if loose:
        bmesh.ops.delete(bm, geom=loose, context="VERTS")
    if closed_inverted:
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(branch.data)
    bm.free()
    if flipped and not closed_inverted:               # an OPEN flipped shell has no volume to recalc from: turn each flagged shell over
        found["shells_turned"] = turn_flipped_shells(branch)
    after = C.mesh_report(branch)
    hashes = {"geometry": digest, "uv": uv_hash(src), "material": material_hash(src)}
    branch["lw_uv_hash"], branch["lw_material_hash"] = hashes["uv"], hashes["material"]
    return {"object": branch.name, "source": src.name, "source_hash": digest, "hash": hashes, "shell_orientation": shells, "before": before, "after": after, "found": found,
            "dimensions": [round(float(d), 6) for d in branch.dimensions], "pivot_offset_from_bounds_centre": _pivot_offset(branch),
            "note": "the source is untouched; only loose vertices, doubled vertices and inverted normals are repaired"}


def _identity_gate(ob, ref, digest, source_hash) -> dict:
    """Identity passes only when the object says what it is derived from AND that matches the anchor: the explicit ``source_hash``, else the reference's
    hash, else (no anchor to check against) a recorded ``lw_source_hash``. A derivative that names no source cannot pass."""
    recorded = str(ob.get("lw_source_hash") or "")
    ref_hash = mesh_hash(ref) if ref is not None else ""
    identical = bool(ref_hash) and ref_hash == digest
    anchor = source_hash or ref_hash
    if source_hash:
        matched = recorded == source_hash or digest == source_hash
    elif ref is not None:
        matched = identical or recorded == ref_hash
    else:
        matched = bool(recorded)
    checks = [{"id": "source_recorded", "pass": bool(recorded) or identical, "value": recorded[:12] or None, "limit": "an lw_source_hash, or identical geometry",
               "reason": "derived from " + (str(ob.get("lw_source")) or "?") + f" ({recorded[:12]})" if recorded else
               ("identical to the reference" if identical else "no source recorded: a derivative must say what it came from (mesh_prep records it)")},
              {"id": "source_matches", "pass": matched, "value": recorded[:12] or digest[:12], "limit": anchor[:12] or "a recorded source",
               "reason": ("matches the anchor" if matched else "the recorded source is not the reference" if anchor else "nothing recorded to check")}]
    ok = all(c["pass"] for c in checks)
    return {"pass": ok, "reasons": [c["reason"] for c in checks] + [f"hash {digest[:12]}"], "hash": digest, "checks": checks}


def asset_acceptance(object, reference="", tolerance=0.1, source_hash=""):
    ob = C.need_object(object)
    ref = C.need_object(reference) if reference else None
    if ref is not None and ref is ob:
        raise C.FeatureError("a derivative cannot be accepted against itself; pass the approved source as the reference")
    digest = mesh_hash(ob)
    rep = C.mesh_report(ob)
    gates = {}
    gates["identity"] = _identity_gate(ob, ref, digest, source_hash)
    reasons, ok = [f"dimensions {[round(float(d), 4) for d in ob.dimensions]}", f"pivot {_pivot_offset(ob)} from the bounds centre"], True
    if ref is not None:
        lo, hi = _bounds(ob)
        rlo, rhi = _bounds(ref)
        diag = max(1e-9, float(np.linalg.norm(rhi - rlo)))
        shift = float(np.linalg.norm((lo + hi) / 2 - (rlo + rhi) / 2)) / diag
        size = float(np.max(np.abs((hi - lo) - (rhi - rlo)))) / diag
        if shift > tolerance:
            ok = False
            reasons.append(f"bounds centre moved {shift:.2f} of the reference diagonal (> {tolerance})")
        if size > tolerance:
            ok = False
            reasons.append(f"extent differs by {size:.2f} of the reference diagonal (> {tolerance})")
    scale = max(abs(s - 1.0) for s in ob.scale)
    if scale > 1e-4:
        ok = False
        reasons.append(f"object scale {tuple(round(s, 4) for s in ob.scale)} is not applied")
    gates["orientation"] = {"pass": ok, "reasons": reasons}
    geo, ok = [], True
    if rep["non_manifold_edges"]:
        ok = False
        geo.append(f"{rep['non_manifold_edges']} non-manifold edges")
    if rep["loose_vertices"]:
        ok = False
        geo.append(f"{rep['loose_vertices']} loose vertices")
    if rep["open_boundary_edges"] == 0 and _signed_volume(ob) < 0:
        ok = False
        geo.append("inverted normals (negative signed volume)")
    gates["geometry"] = {"pass": ok, "reasons": geo or ["closed, outward, no loose geometry"], "report": rep}
    mat, ok = [], True
    empty = [i for i, s in enumerate(ob.material_slots) if s.material is None]
    if empty:
        ok = False
        mat.append(f"empty material slots {empty}")
    if ob.material_slots and not ob.data.uv_layers:
        ok = False
        mat.append("materials but no UV layer")
    gates["materials"] = {"pass": ok, "reasons": mat or [f"{len(ob.material_slots)} slots, {len(ob.data.uv_layers)} UV layers"]}
    return {"object": ob.name, "reference": ref.name if ref else None, "gates": gates,
            "accepted": all(g["pass"] for g in gates.values()),
            "not_checked": ["engine import settings", "collision", "skeleton in the target engine"]}


def rig_armor(object, armature, bone="", body="", poses=None, max_stretch=None, clearance_body="", min_clearance_m=0.0, seam_limit_m=SEAM_LIMIT_M):
    """Fit a COPY of the piece and test it in a pose set. Rigid mode cannot stretch (one bone at weight 1 is a rigid transform), so what can fail it is
    CLEARANCE: with ``clearance_body`` (the body rigged to the same armature) every pose is judged by the piece's distance to the posed body. In every
    mode a SEAM between shells that opens wider than ``seam_limit_m`` fails, however little any single edge stretches."""
    src = C.need_object(object)
    arm_ob = C.need_object(armature, "ARMATURE")
    if bone and body:
        raise C.FeatureError("pick one: rigid (bone) or transfer (body); clearance_body is the body to measure clearance against")
    if bone:
        mode, kw = "rigid", {"bone": bone}
    elif body:
        mode, kw = "transfer", {"source": body}
    else:
        mode, kw = "auto", {}
    fit = C.duplicate(src, "_fit")
    bound = _rig.bind_to_armature(fit.name, arm_ob.name, mode, **kw)
    if poses is None:
        poses = [{"name": n, "bones": [{"bone": b, "rotate": r} for b, r in bones if b in arm_ob.data.bones]} for n, bones in WIKI8]
    tested = _rig.pose_test(arm_ob.name, fit.name, poses, clearance_body=clearance_body)["poses"]
    limit = float(max_stretch) if max_stretch is not None else (1.001 if mode == "rigid" else 1.35)
    worst = max((p["max_edge_stretch"] for p in tested), default=1.0)
    seam = max((p["seam_gap_m"] for p in tested), default=0.0)
    clear = [p["clearance"]["min_m"] for p in tested if "clearance" in p]
    worst_clear = min(clear) if clear else None
    stretch_ok = True if mode == "rigid" else worst < limit
    seam_ok = seam <= float(seam_limit_m)
    clear_ok = worst_clear is None or worst_clear >= float(min_clearance_m)
    not_checked = [] if worst_clear is not None else ["clearance (no clearance_body given" + ("; a rigid plate cannot stretch, so nothing here can fail it)" if mode == "rigid" else ")")]
    return {"object": fit.name, "source": src.name, "armature": arm_ob.name, "mode": mode, "bind": bound, "poses": tested,
            "max_stretch_limit": limit, "worst_stretch": worst, "stretch_check": "vacuous in rigid mode" if mode == "rigid" else "measured",
            "max_seam_gap_m": seam, "max_seam_gap_limit_m": float(seam_limit_m), "worst_clearance_m": worst_clear, "min_clearance_m": float(min_clearance_m),
            "accepted": bool(tested) and stretch_ok and seam_ok and clear_ok, "not_checked": not_checked,
            "note": "the original is never bound; a new geometry stage invalidates this test; the pose angles are approximations (WIKI8)"}
