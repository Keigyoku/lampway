# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_normalize_rigged (specs/canon/normalization contracts/normalize_rig.md, N5): canon R1 `rig_inspect` + R3 `rig_normalize`
(lane orphans, features/rig_tools) behind the ingress door, then the canonical documents.

* Refused (contract section 8): a `mixed` convention (canon 17 INV-17.1); a roster incomplete against the profile (the missing bones
  named); a joint height no known unit factor explains (canon 18 B.1, the inspect's own note); a unit with no normalizer; a non-uniform
  scale on an animated rig (rig_normalize's refusal); a turn (turning an armature's rest and actions is not built: the rig must face -Y).
* `dry_run` (the default) changes nothing and answers the plan. A real run applies the unit and the object scale through
  rig_normalize (drift-checked), then stamps `lw_canon` on the armature (kind `skeleton`) and on every mesh skinned to it (kind
  `rigged_mesh`, its transform kept when it is not the identity: `skinned_rig_preserved`).
* Bones: `along` is head -> the head of the continuation child (`canon_geom.chain_ends`; `child_head`, `named_continuation`, or
  `leaf_parent_line` for a last bone), never the imported tail (canon 01 C.1, INV-17.5); `frame` the bone's rest frame in the body frame.
* Naming: rig_inspect's family table (ue | mixamo | rigify; canon 16) maps the bones to the canonical slots; a rig no table matches is
  refused (map it first)."""

import hashlib
import json

import bpy
import numpy as np

from .. import canon_asset as CA
from .. import canon_io
from ..canon_geom.bones import CONTINUATION, MAIN_CHILD, chain_ends, terminal_auxiliary_leaf
from ..canon_geom import native_topology as NT
from ..canon_geom.rest_frames import canonical_rest_frame
from ..rig_tools import core as RC
from . import common as C
from . import normalize as NZ
from . import rig_tools as RT

TOOL, TOOL_VERSION = "lampway_normalize_rigged", "1.0.0"
UNIT_OF = {f: u for u, f in RT.UNITS.items()}          # the factor rig_inspect measures -> rig_normalize's unit name
REFERENCE_ID = {"ue5_body": "ue5_manny", "ue5_body_fingers": "ue5_manny", "metahuman": "metahuman_fullbody"}
IK_PARENTS = {"ik_foot_root": "root", "ik_foot_l": "ik_foot_root", "ik_foot_r": "ik_foot_root",
              "ik_hand_root": "root", "ik_hand_gun": "ik_hand_root", "ik_hand_l": "ik_hand_gun", "ik_hand_r": "ik_hand_gun",
              "interaction": "root", "center_of_mass": "root"}
FRAME_HELPERS = frozenset(IK_PARENTS)


def validate_ik_parents(parents):
    """Only the named mannequin IK graph can use authored target frames."""
    for name in FRAME_HELPERS:
        target = RC.IK_TARGETS.get(name, "root")
        if name not in parents:
            continue
        expected = IK_PARENTS[name]
        # The measured own-warrior rigs omit the optional origin bone. Their
        # two IK roots are independent roots, rather than anatomical branches.
        if expected == "root" and "root" not in parents:
            expected = None
        if parents[name] != expected or (target != "root" and target not in parents):
            raise C.FeatureError(f"{name}: IK helper requires parent {expected} and target {target}")
        unknown = [n for n, p in parents.items() if p == name and IK_PARENTS.get(n) != name]
        if unknown:
            raise C.FeatureError(f"{name}: unknown IK helper children {', '.join(sorted(unknown))}")


def canonical_helper_ends(ob, *, native_raw=False):
    """Canon-17 authored helpers: validated rest stamp, or explicit verified native bind intake."""
    stamp = ob.get("lw_canon")
    if not stamp:
        if native_raw:
            rig = RT.read(ob)
            # Only the complete measured native graph admits unstamped authored
            # drivers. Generic or partial rigs retain the normal segment rule.
            if not (set(rig["names"]) & NT.AUXILIARY):
                return {}
            roster = NT.audit(rig["parents"])
            if not roster["complete"]:
                raise C.FeatureError(f"{ob.name}: native bind needs the complete verified native topology; re-run normalize_rigged")
            convention = RT.reference_convention(ob, rig) or RC.classify_convention(list(RT.convention_angles(rig).values()))
            if convention not in ("blender", "ue_axes"):
                raise C.FeatureError(f"{ob.name}: native bind refuses {convention} bone axes; inspect and conform first")
            axis = 1 if convention == "blender" else 0
            out = {}
            for name in sorted(NT.AUXILIARY):
                frame, _correction = canonical_rest_frame(rig["frames"][name], CA._proper)
                length = float((ob.matrix_world.to_3x3() @ ob.data.bones[name].vector).length)
                out[name] = np.asarray(rig["heads"][name]) + frame[:, axis] * length
            return out
        return {}
    doc = json.loads(stamp)
    rows = [row for row in doc.get("body", {}).get("bones", [])
            if row.get("along_source") == "authored_helper_frame"
            or (row.get("name") in FRAME_HELPERS and row.get("along_source") == "reference_transport")]
    if not rows:
        return {}
    errors = CA.validate(doc)
    if (errors or doc.get("kind") != "skeleton" or doc.get("normalized_by", {}).get("tool") != TOOL
            or (any(row.get("along_source") == "authored_helper_frame" for row in rows)
                and doc["body"].get("reference_skeleton", {}).get("id") != REFERENCE_ID["metahuman"])):
        raise C.FeatureError(f"{ob.name}: corrective helper endpoints need a valid normalized skeleton; re-run normalize_rigged")
    rig = RT.read(ob)
    if RT._fingerprint(ob, rig) != doc["body"]["rest_pose"]["sha256"]:
        raise C.FeatureError(f"{ob.name}: the normalized corrective rest frames changed; re-run normalize_rigged")
    out = {}
    if any(row.get("along_source") == "authored_helper_frame" for row in rows):
        NT.audit(rig["parents"])
    validate_ik_parents(rig["parents"])
    for row in rows:
        name = row["name"]
        if ((name not in NT.AUXILIARY and name not in FRAME_HELPERS) or name not in rig["heads"]):
            raise C.FeatureError(f"{name}: authored helper endpoints require a verified native auxiliary role")
        out[name] = np.asarray(row["head_m"], float) + np.asarray(row["along"], float) * row["length_m"]
    return out


def require_complete_native(ob):
    """A partial normalized native profile cannot become a full body/export."""
    stamp = ob.get("lw_canon")
    if not stamp:
        return
    doc = json.loads(stamp)
    if doc.get("body", {}).get("reference_skeleton", {}).get("id") != REFERENCE_ID["metahuman"]:
        return
    roster = NT.audit(RT.read(ob)["parents"])
    if not roster["complete"] or not doc["body"]["roster"]["complete"]:
        raise C.FeatureError(f"{ob.name}: native full-body reference is incomplete; missing {', '.join(roster['missing'])}")
    canonical_helper_ends(ob)


def _bones(ob, mapped, convention="blender", profile="ue5_body"):
    rig = RT.read(ob)
    names, parents = rig["names"], rig["parents"]
    heads = {n: tuple(rig["heads"][n]) for n in names}
    # Only the canonical document is orthogonalized. Raw reads, fingerprints,
    # authored rest/pose matrices and export/readback validation remain intact.
    canonical_frames, corrections = {}, {}
    for n in names:
        try:
            canonical_frames[n], correction = canonical_rest_frame(rig["frames"][n], CA._proper)
        except ValueError as error:
            raise C.FeatureError(f"bone {n}: {error}") from error
        if correction is not None:
            corrections[n] = correction
    rig["canonical_frame_corrections"] = corrections
    # MetaHuman corrective roots fan out to auxiliary drivers. Their authored
    # rest frame/roll is the authority, not an arbitrary continuation child.
    helpers = {}
    validate_ik_parents(parents)
    axis = 1 if convention == "blender" else 0
    for n in names:
        if n in FRAME_HELPERS:
            b = ob.data.bones[n]
            world_length = float((ob.matrix_world.to_3x3() @ b.vector).length)
            helpers[n] = np.asarray(heads[n]) + canonical_frames[n][:, axis] * world_length
    if profile == "metahuman":
        NT.audit(parents)
        axis = 1 if convention == "blender" else 0
        for n in names:
            if n in NT.AUXILIARY:
                b = ob.data.bones[n]
                direction = canonical_frames[n][:, axis]
                world_length = float((ob.matrix_world.to_3x3() @ b.vector).length)
                helpers[n] = np.asarray(heads[n]) + direction * world_length
    ends = chain_ends(heads, parents, main_child=dict(CONTINUATION, **MAIN_CHILD), helper_ends=helpers)
    kids = {}
    for n in names:
        if parents.get(n) is not None:
            kids.setdefault(parents[n], []).append(n)
    canon = {bone: slot for slot, bone in mapped.items()}
    deform = {b.name: bool(b.use_deform) for b in ob.data.bones}
    out = []
    for n in names:
        h = np.asarray(heads[n], float)
        e = np.asarray(ends[n], float)
        v = e - h
        L = float(np.linalg.norm(v))
        if L < 1e-9:
            raise C.FeatureError(f"bone {n}: its next joint is at its own head (zero length): a skeleton cannot carry it")
        children = kids.get(n, [])
        src = "reference_transport" if n in FRAME_HELPERS else "authored_helper_frame" if n in helpers else (
            "leaf_parent_line" if not children or terminal_auxiliary_leaf(n, children) else
            ("child_head" if len(children) == 1 else "named_continuation"))
        F = canonical_frames[n]
        out.append({"name": n, "canonical_name": canon.get(n), "parent": parents.get(n), "head_m": [round(float(x), 9) for x in h],
                    "along": [round(float(x), 12) for x in v / L], "along_source": src, "frame": [[round(float(x), 12) for x in r] for r in F],
                    "length_m": round(L, 9), "deform": deform.get(n, False)})
    return out, rig


def _conventions(turn):
    return {"frame": CA.FRAME, "up": "+Z", "front": "-Y", "wearer_left": "+X", "handedness": "right", "units": "m",
            "source_frame": {"name": "blender_import", "up": "+Z", "front": "-Y"}, "axis_map": [[1, 0, 0], [0, 1, 0], [0, 0, 1]], "axis_map_det": 1,
            "turn_deg": turn, "winding_reversed": False, "frame_decision": {"kind": "declared", "evidence": {"method": "caller_turn", "value": turn}}}


def _transform(ob):
    M = np.array(ob.matrix_world)
    if np.allclose(M, np.eye(4), atol=CA.TOL_M):
        return {"applied": True, "object_matrix": np.eye(4).tolist()}
    return {"applied": False, "object_matrix": [[round(float(x), 9) for x in r] for r in M], "not_applied_reason": "skinned_rig_preserved"}


def _skin(mob, bone_names):
    me = mob.data
    idx = {g.index: g.name for g in mob.vertex_groups}
    infl, sums, unweighted = 0, True, 0
    for v in me.vertices:
        w = [g.weight for g in v.groups if idx.get(g.group) in bone_names and g.weight > 0]
        infl = max(infl, len(w))
        if not w:
            unweighted += 1
        elif abs(sum(w) - 1.0) > 1e-4:
            sums = False
    return {"max_influences": max(infl, 1), "sums_normalized": sums, "unweighted_vertices": unweighted,
            "groups_not_bones": sorted(n for n in idx.values() if n not in bone_names)}


def _doc(kind, raw_sha, name, conventions, transform, scale, body, receipt, pivot=None):
    rbytes = json.dumps(receipt, sort_keys=True, indent=1).encode()
    canonical = CA.digest(json.dumps(body, sort_keys=True).encode())
    doc = {"schema": "lampway.canonical-asset", "schema_version": 1, "kind": kind, "asset_id": f"{kind}-{raw_sha[:12]}",
           "raw": {"sha256": raw_sha, "container": "none", "bytes": 0, "generator": {"source": "unknown"}, "path_hint": name},
           "conventions": conventions, "transform": transform, "scale": scale,
           "normalized_by": {"tool": TOOL, "tool_version": TOOL_VERSION, "blender_version": bpy.app.version_string},
           "canonical_sha256": canonical, "receipt_sha256": hashlib.sha256(rbytes).hexdigest(), "body": body}
    if pivot:
        doc["pivot"] = pivot
    errs = CA.validate(doc)
    if errs:
        raise C.FeatureError(f"the canonical {kind} document does not validate (a normalizer bug): {errs[:3]}")
    return doc


def run(armature, meshes=None, profile="ue5_body", turn_deg=0.0, dry_run=True, unit="auto"):
    if unit not in ("auto", *RT.UNITS):
        raise C.FeatureError(f"unit is auto | {' | '.join(RT.UNITS)}")
    if float(turn_deg) != 0.0:
        raise C.FeatureError("turning an armature (its rest and its actions) is not built: the rig must already face -Y (turn_deg 0)")
    if profile not in RC.REQUIRED:
        raise C.FeatureError(f"profile is one of {', '.join(RC.REQUIRED)}")
    ob = RT._armature(armature)
    native_roster = NT.audit({b.name: b.parent.name if b.parent else None for b in ob.data.bones}) if profile == "metahuman" else None
    rec = RT.inspect(armature, profile=profile)
    conv = rec["convention"]["class"]
    if conv not in ("blender", "ue_axes"):
        next_step = ("conform a disposable copy with an explicit independently measured native reference: "
                     f"lampway_rig_conform armature={ob.name} map=<reviewed-map> reference=<independent-native-profile> "
                     "out_name=<new-copy> convention=<declared-convention> dry_run=false"
                     if native_roster is not None else "conform it to one convention first (rig_conform)")
        raise C.FeatureError(f"{ob.name}'s bone axes are {conv} (median {rec['convention']['angles_deg']['median']} deg, max "
                             f"{rec['convention']['angles_deg']['max']} deg off head -> next joint): canon 17 refuses a mixed armature; {next_step}")
    names = [b.name for b in ob.data.bones]
    family = rec["family"]["name"]
    if family is None:
        raise C.FeatureError(f"no naming family matches {ob.name}'s bones ({rec['family'].get('note', 'no table hits')}): map it first (rig_map)")
    mapped, missing = dict(rec["slots"]["mapped"]), list(rec["slots"]["missing_required"])
    if missing:
        raise C.FeatureError(f"roster incomplete against {profile}: missing {', '.join(missing)} (canon 01 C.6)")
    u = rec["units"]
    if unit == "auto" and u["factor"] is None:
        raise C.FeatureError(f"units undecided: {u.get('note') or 'no known unit factor explains the joint height'} (canon 18 B.1)")
    factor = u["factor"] if unit == "auto" else RT.UNITS[unit]
    chosen_unit = UNIT_OF.get(round(float(factor), 12))
    if chosen_unit is None:
        raise C.FeatureError(f"the measured unit factor {u['factor']} has no normalizer here (rig_normalize knows {', '.join(RT.UNITS)})")
    skinned = [m for m in bpy.data.objects if m.type == "MESH" and any(x.type == "ARMATURE" and x.object is ob for x in m.modifiers)]
    if meshes:
        skinned = [bpy.data.objects[n] for n in meshes]
    plan = {"armature": ob.name, "convention": conv, "family": family, "unit": chosen_unit, "unit_factor": factor,
            "object_scale": u["object_scale"], "ratio_to_reference": u["ratio_to_reference"], "meshes": sorted(m.name for m in skinned)}
    if native_roster is not None:
        plan["native_roster"] = native_roster
    if dry_run:
        return {**plan, "dry_run": True, "how": "dry_run=false applies the unit and object scale (rig_normalize) and stamps the documents"}
    applied = None
    if chosen_unit != "m" or not np.allclose(ob.scale, 1.0):
        applied = RT.normalize(armature, unit=chosen_unit, apply_scale=True, dry_run=False)
    bones, rig = _bones(ob, mapped, conv, profile)
    raw_sha = rec["sha256"]["input"]
    root = sorted(b.name for b in ob.data.bones if b.parent is None)[0]
    scale = {"state": "real", "decision": "measured" if unit == "auto" else "declared", "factor_applied": float(factor), "uniform": True,
             "evidence": {"method": "reference_height_ratio", "value": float(u["ratio_to_reference"]), "reference": u["reference"]}}
    if unit != "auto":
        scale["evidence"] = {"method": "unit_metadata", "value": float(factor), "reference": unit}
    body = {"reference_skeleton": {"id": REFERENCE_ID.get(profile, "custom"), "sha256": rec["sha256"]["reference"]},
            "convention": conv, "rest_pose": {"name": "rest", "sha256": RT._fingerprint(ob, rig)},
            "naming": {"family": family, "map_sha256": CA.digest(json.dumps(mapped, sort_keys=True).encode()),
                       "unmapped": sorted(n for n in names if n not in set(mapped.values()))},
            "roster": NT.audit(rig["parents"]) if profile == "metahuman" else {"complete": True, "missing": []}, "root": {"name": root, "at_origin": bool(np.linalg.norm(rig["heads"][root]) < 1e-6)},
            "bones": bones, "non_uniform_bone_scale": False}
    if profile == "metahuman":
        body["reference_skeleton"]["bones"] = len(NT.PARENTS)
    receipt = {"schema": "lampway.normalize-receipt/1", "tool": TOOL, "inspect": rec["sha256"]["receipt"], "plan": plan, "applied": applied}
    receipt["canonical_frame_corrections"] = rig["canonical_frame_corrections"]
    doc = _doc("skeleton", raw_sha, ob.name, _conventions(0.0), _transform(ob), scale, body, receipt)
    ob["lw_canon"] = json.dumps(doc, sort_keys=True)
    # Full evidence stays with the private armature; MCP receives a bounded
    # aggregate. The canonical document hashes this exact receipt, and its
    # rest fingerprint still identifies unmodified raw authored frames.
    ob["lw_canon_normalize_receipt"] = json.dumps(receipt, sort_keys=True, indent=1)
    ref = {"asset_id": doc["asset_id"], "canonical_sha256": doc["canonical_sha256"]}
    out_meshes = []
    for mob in skinned:
        me = mob.data
        f = canon_io.facts(mob)
        co = np.empty(len(me.vertices) * 3)
        me.vertices.foreach_get("co", co)
        mesh = {"bbox_min_m": NZ._r9(f["bbox_min_m"]), "bbox_max_m": NZ._r9(f["bbox_max_m"]),
                "topology": NZ._topology(me, False, {"rule": "none", "refused_reason": "authored_rig"}, False),
                "uv_sets": NZ._uv_sets(me, co.reshape(-1, 3)), "material_slots": [{"slot": i, **({"name": s.material.name} if s.material else {})}
                                                                                for i, s in enumerate(mob.material_slots)],
                "normals": {"custom_split": bool(getattr(me, "has_custom_normals", False)), "shading": "mixed"}, "geometry_sha256": f["geometry_sha256"]}
        mbody = {"mesh": mesh, "skeleton": ref, "skin": _skin(mob, set(names)), "bind": {"pose_name": "rest", "equals_reference": False}}
        mdoc = _doc("rigged_mesh", f["geometry_sha256"], mob.name, _conventions(0.0), _transform(mob), scale, mbody,
                    {"schema": "lampway.normalize-receipt/1", "tool": TOOL, "skeleton": ref}, pivot={"rule": "skeleton_root"})
        mob["lw_canon"] = json.dumps(mdoc, sort_keys=True)
        out_meshes.append(mob.name)
    corrections = list(rig["canonical_frame_corrections"].values())
    correction_summary = {"count": len(corrections),
                          "max_spectral_correction": max((c["spectral_correction"] for c in corrections), default=0.0),
                          "max_axis_correction_deg": max((c["max_axis_correction_deg"] for c in corrections), default=0.0)}
    return {**plan, "dry_run": False, "skeleton": {"asset_id": doc["asset_id"], "canonical_sha256": doc["canonical_sha256"]},
            "rigged": out_meshes, "applied": applied, "canonical_frame_corrections": correction_summary}
