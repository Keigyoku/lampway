# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""lampway_rig_convert and lampway_rig_skin (STATUS O36; canon 22; specs/canon/rig_tools/rig_convert.md): the external rig-conversion and
normalization tool over the modules ported from TITAN (rig_convert/). The game reads only this tool's output.

The to-blender adapter (canon 22 H.2): Lampway's working frame is right-handed (Z up, faces -Y, metres); the interchange's native leg is
left-handed, so a Blender transform is REFLECTED across Y on the way out (p -> (x, -y, z); q -> (-x, y, -z, w)) and the profile carries
100 cm per unit and the UE5 Manny's adapter basis (a qz(-90) turn) unless the caller states its own. A profile's reference is the bind
unless authored alignment rules are given (animation_canon.align_reference: processing data, never a skeleton edit).

Every output is an immutable publication with an adjacent ``<out>.receipt.json`` (the input, profile, rules and output sha256, the owner
modules' sha256): an identical repeat keeps the bytes, a different existing output is refused. The skin and morph half is WIP tooling:
canon 22 B.10 and canon 07 are DRAFT; its receipts and refusals carry the WIP badge."""

import hashlib
import json
import math
import os
from pathlib import Path

from . import common as C
from ..rig_convert import animation_canon as AC
from ..rig_convert import canon as MC
from ..rig_convert import skin_bind as SB

RIG_CONVERT = Path(AC.__file__).parent
MANNY_BASIS = [0, 0, -0.707106781, 0.707106781]
A1_BARS = {"position_cm": 0.1, "rotation_deg": 0.1, "scale": 1e-5}
WIP = "WIP: skin and morph tooling (canon 22 B.10 and canon 07 are DRAFT; dogfooded and improved through Lampway)"
VERBS = ("profile", "extract", "normalize", "adapt", "retarget", "compare", "verify")
SKIN_VERBS = ("mesh_normalize", "mesh_adapt", "capture", "rebind", "evaluate")


def _sha(b):
    return hashlib.sha256(b).hexdigest()


def _owners():
    return {m: _sha((RIG_CONVERT / f"{m}.py").read_bytes()) for m in ("animation_canon", "canon", "skin_bind")}


def _path(root, p):
    if not p:
        return None
    q = Path(p) if os.path.isabs(p) else Path(root, p)
    real_root, real = os.path.realpath(root), os.path.realpath(q)
    if real != real_root and not real.startswith(real_root + os.sep):
        raise C.FeatureError(f"{p} is outside the project root")
    return q


def _read(root, p, what):
    q = _path(root, p)
    if q is None or not q.is_file():
        raise C.FeatureError(f"no {what} at {p}")
    raw = q.read_bytes()
    return json.loads(raw), _sha(raw)


def _publish(root, out, data, receipt):
    """Both destinations are checked before either is written; an identical repeat keeps the bytes (canon.py's publication rule)."""
    target = _path(root, out)
    if target is None:
        raise C.FeatureError("out is required: every result is a published file")
    rec_path = Path(str(target) + ".receipt.json")
    receipt = dict(receipt, sha256=dict(receipt.get("sha256", {}), output=_sha(data)))
    rdata = (json.dumps(receipt, sort_keys=True, indent=1) + "\n").encode()
    for p, d in ((target, data), (rec_path, rdata)):
        if p.is_symlink() or (p.exists() and p.read_bytes() != d):
            raise C.FeatureError(f"different existing output: {p} (publication never overwrites; choose another out)")
    state = "unchanged" if target.exists() else "written"
    for p, d in ((target, data), (rec_path, rdata)):
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            with p.open("xb") as fh:
                fh.write(d)
    return {"out": str(target), "receipt": str(rec_path), "state": state, "sha256": receipt["sha256"]}


# ---------------------------------------------------------------- the to-blender adapter (Blender side)
def _reflect(matrix):
    """A Blender 4x4 (right-handed) as a native left-handed transform {translation, rotation xyzw, scale}, reflected across Y."""
    loc, q, s = matrix.decompose()
    return {"translation": [loc.x, -loc.y, loc.z], "rotation": [-q.x, q.y, -q.z, q.w], "scale": [s.x, s.y, s.z]}


def _ordered(ob):
    order, seen = [], set()

    def visit(b):
        if b.name in seen:
            return
        if b.parent is not None:
            visit(b.parent)
        seen.add(b.name)
        order.append(b)
    for b in ob.data.bones:
        visit(b)
    roots = [b for b in order if b.parent is None]
    if len(roots) != 1:
        raise C.FeatureError(f"{ob.name} has {len(roots)} root bones ({', '.join(b.name for b in roots)}): a profile has exactly one root")
    return order


def object_root(ob):
    """The armature OBJECT as the profile's root when its root bone is not at the object's origin (a Mixamo Hips): a profile's root sits
    at the origin (make_profile), and TITAN's Blender read-back names the object the same way (anim-compare-blender object_root)."""
    root = _ordered(ob)[0]
    if root.head_local.length <= 1e-9:
        return None
    if ob.name in ob.data.bones:
        raise C.FeatureError(f"the armature object {ob.name!r} shares its name with a bone: it cannot stand as the profile root; rename one")
    return ob.name


def profile_from_armature(ob, name, rules=None, basis=None, centimeters_per_unit=100.0):
    mw = ob.matrix_world
    top = object_root(ob)
    bones = [{"name": top, "parent": None, "bind": _reflect(mw)}] if top else []
    bones += [{"name": b.name, "parent": b.parent.name if b.parent else top, "bind": _reflect(mw @ b.matrix_local)} for b in _ordered(ob)]
    if rules:
        by = {}
        local = []
        for b in bones:
            t = AC._transform(b["bind"])
            loc = AC._relative(by[b["parent"]], t) if b["parent"] else t
            by[b["name"]] = t
            local.append({"name": b["name"], "parent": b["parent"], "local": loc})
        aligned = AC.align_reference(local, rules)
        bones = [{"name": a["name"], "parent": a["parent"], "bind": a["bind"], "reference": a["reference"]} for a in aligned]
    else:
        bones = [dict(b, reference=b["bind"]) for b in bones]
    return AC.make_profile(name, bones, basis=basis or MANNY_BASIS, centimeters_per_unit=centimeters_per_unit)


def extract_samples(ob, action, duration):
    import bpy
    acts = bpy.data.actions
    act = acts.get(action)
    if act is None:
        raise C.FeatureError(f"no action named {action!r}")
    ad = ob.animation_data or ob.animation_data_create()
    keep, scene = ad.action, bpy.context.scene
    keep_frame = scene.frame_current
    fps = scene.render.fps / scene.render.fps_base
    start = act.frame_range[0]
    ad.action = act
    top = object_root(ob)
    out = []
    try:
        for t in AC.sample_times(duration):
            f = start + t[0] / t[1] * fps
            scene.frame_set(int(math.floor(f)), subframe=f - math.floor(f))
            bpy.context.view_layer.update()
            pose = {pb.name: _reflect(ob.matrix_world @ pb.matrix) for pb in ob.pose.bones}
            if top:
                pose[top] = _reflect(ob.matrix_world)
            out.append({"time": t, "pose": pose})
    finally:
        ad.action = keep
        scene.frame_set(keep_frame)
    return out


# ---------------------------------------------------------------- the verbs
def _samples_of(doc):
    if isinstance(doc, dict) and doc.get("schema") == AC.SCHEMA:
        return doc["samples"]
    if isinstance(doc, dict) and isinstance(doc.get("samples"), list):
        return doc["samples"]
    if isinstance(doc, list):
        return doc
    raise C.FeatureError("expected a sample packet: {samples: [...]} or a canonical titan.animation/1 packet")


def _receipt(verb, **sha):
    return {"tool": "lampway_rig_convert", "verb": verb, "sha256": {k: v for k, v in sha.items() if v}, "owners": _owners(),
            "wire_contract": "the schema ids are a stable contract shared with TITAN"}


def convert(verb, root, input="", profile="", target_profile="", rules="", target="", out="", armature="", action="", duration="",
            name="", basis=None, centimeters_per_unit=100.0, channels=None, inspected=None):
    if verb not in VERBS:
        raise C.FeatureError(f"verb is one of {', '.join(VERBS)}")
    try:
        if verb in ("profile", "extract"):
            import bpy
            ob = bpy.data.objects.get(armature)
            if ob is None or ob.type != "ARMATURE":
                raise C.FeatureError(f"no armature named {armature!r}")
            if inspected is not None:
                inspected(ob)
            if verb == "profile":
                rule_doc, rule_sha = _read(root, rules, "rules") if rules else (None, None)
                value = profile_from_armature(ob, name or ob.name, rule_doc, basis, float(centimeters_per_unit))
                pub = _publish(root, out, AC.encode(value), _receipt(verb, rules=rule_sha))
                return {**pub, "bones": len(value["bones"]), "profile_sha256": value["sha256"], "adapter": value["adapter"]}
            AC._duration(duration)
            value = {"schema": "lampway.native-samples/1", "armature": ob.name, "action": action, "duration": str(duration),
                     "frame": "to-blender: reflected across Y, metres", "samples": extract_samples(ob, action, duration), "channels": channels or {}}
            pub = _publish(root, out, AC.encode(value), _receipt(verb))
            return {**pub, "samples": len(value["samples"])}
        doc, in_sha = _read(root, input, "input")
        if verb == "normalize":
            prof, p_sha = _read(root, profile, "profile")
            if isinstance(doc, dict) and doc.get("schema") == AC.SCHEMA:
                value = AC.normalize(doc, prof)
            else:
                value = AC.normalize(_samples_of(doc), prof, duration=doc.get("duration", duration), channels=doc.get("channels", channels or {}))
            pub = _publish(root, out, AC.encode(value), _receipt(verb, input=in_sha, profile=p_sha))
            return {**pub, "samples": len(value["samples"]), "packet_sha256": value["sha256"]}
        if verb == "adapt":
            prof, p_sha = _read(root, profile, "profile")
            value = {"schema": "lampway.native-samples/1", "duration": doc["duration"], "frame": "native (the profile's world)",
                     "samples": AC.adapt(doc, prof), "channels": doc.get("channels", {})}
            return _publish(root, out, AC.encode(value), _receipt(verb, input=in_sha, profile=p_sha))
        if verb == "retarget":
            tprof, t_sha = _read(root, target_profile, "target profile")
            rule_doc, r_sha = _read(root, rules, "rules")
            value = AC.retarget(doc, tprof, rule_doc)
            pub = _publish(root, out, AC.encode(value), _receipt(verb, input=in_sha, target_profile=t_sha, rules=r_sha))
            cmp = AC.compare(doc["samples"], value["samples"]) if set(doc["samples"][0]["pose"]) == set(value["samples"][0]["pose"]) else None
            return {**pub, "packet_sha256": value["sha256"],
                    "compare": {k: v for k, v in cmp.items() if k != "measurements"} if cmp else "rosters differ: compare the adapted motion"}
        other, o_sha = _read(root, target, "target")
        if verb == "compare":
            r = AC.compare(_samples_of(doc), _samples_of(other))
            return {k: v for k, v in r.items() if k != "measurements"} | {"rows": len(r["measurements"]), "sha256": {"input": in_sha, "target": o_sha}}
        prof, p_sha = _read(root, profile, "profile")                         # verify: a native emission against the canonical packet
        expected = AC.adapt(doc, prof)
        r = AC.compare(expected, _samples_of(other))
        units = prof["adapter"]["centimeters_per_unit"]
        over = {}
        for m in r["measurements"]:
            if m["translation"] * units > A1_BARS["position_cm"] or m["rotation_degrees"] > A1_BARS["rotation_deg"] or m["scale"] > A1_BARS["scale"]:
                row = over.setdefault(m["bone"], {"bone": m["bone"], "position_cm": 0.0, "rotation_deg": 0.0, "scale": 0.0, "times": []})
                row["position_cm"] = max(row["position_cm"], m["translation"] * units)
                row["rotation_deg"] = max(row["rotation_deg"], m["rotation_degrees"])
                row["scale"] = max(row["scale"], m["scale"])
                row["times"].append(m["time"])
        return {"verdict": "FAIL" if over else "PASS", "bars": A1_BARS, "worst_position_cm": r["translation_max"] * units,
                "worst_rotation_deg": r["rotation_max_degrees"], "worst_scale": r["scale_max"], "over_bars": sorted(over.values(), key=lambda x: x["bone"]),
                "sha256": {"canonical": doc.get("sha256"), "canonical_file": in_sha, "native": o_sha, "profile": p_sha},
                "note": "an independently emitted native artifact is judged by the A1 bars; both hashes are recorded, nothing close is called identical"}
    except ValueError as exc:
        if isinstance(exc, C.FeatureError):
            raise
        raise C.FeatureError(str(exc)) from None


def skin(verb, root, input="", space="", joints="", weights="", pose="", joint_map="", out="", geometry_only=False):
    if verb not in SKIN_VERBS:
        raise C.FeatureError(f"WIP (canon 22 DRAFT): verb is one of {', '.join(SKIN_VERBS)}")
    try:
        doc, in_sha = _read(root, input, "input")
        if verb in ("mesh_normalize", "mesh_adapt"):
            sp, s_sha = _read(root, space, "space") if space else (None, None)
            value = MC.normalize_mesh(doc, sp) if verb == "mesh_normalize" else MC.adapt_mesh(doc, sp)
            data, extra = MC.serialize(value), {"space": s_sha}
            summary = {"meshes": len(value["meshes"]), "morphs": sum(len(m.get("morphs", {})) for m in value["meshes"])}
        elif verb == "capture":
            jt, j_sha = _read(root, joints, "joints")
            wt, w_sha = _read(root, weights, "weights")
            value = SB.capture(doc, jt, wt)
            data, extra, summary = MC.serialize(value), {"joints": j_sha, "weights": w_sha}, {"joints": len(value["joints"])}
        elif verb == "rebind":
            jt, j_sha = _read(root, joints, "target joints")
            jm, m_sha = _read(root, joint_map, "joint map")
            value, rec = SB.rebind(doc, jt, jm)
            data, extra, summary = MC.serialize(value), {"joints": j_sha, "joint_map": m_sha}, {"merged_targets": rec["merged_targets"],
                                                                                                    "dropped_mass": rec["dropped_mass"]}
        else:
            ps, p_sha = _read(root, pose, "pose")
            value = SB.evaluate(doc, ps, geometry_only=bool(geometry_only))
            data, extra, summary = MC.serialize(value), {"pose": p_sha}, {"meshes": len(value["meshes"])}
        rec = dict(_receipt(verb, input=in_sha, **extra), tool="lampway_rig_skin", wip=True, status=WIP)
        return {**_publish(root, out, data, rec), **summary, "wip": True, "status": WIP}
    except (ValueError, TypeError, KeyError) as exc:
        msg = str(exc)
        raise C.FeatureError(msg if msg.startswith("WIP") else f"WIP (canon 22 DRAFT): {msg}") from None
