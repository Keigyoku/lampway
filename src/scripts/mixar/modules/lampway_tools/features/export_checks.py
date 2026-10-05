# SPDX-FileCopyrightText: 2026 Lampway contributors
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""skeleton_export_check and engine_import_check: the runtime gates between a rigged piece and the engine.

skeleton_export_check reads an armature in the scene or an FBX (imported into the scene and removed again) and diffs it against a reference skeleton (a reference FBX): leaf bones (``*_end`` or a
zero-length tail the reference does not have), missing and extra bones, parents that differ, the root, the unit scale (the height ratio to the reference: a 100x export reads 100), the up axis, and
whether the rest pose is a posed frame (bones posed with no animation: the bind pose was taken from a posed scene).
engine_import_check is a static read of an exported package: the FBX binary header's version, mesh names, UCX_ collision names that match a render mesh, the textures the materials name and whether they
exist, textures nobody names, and a hand-run import's receipt recorded (never judged)."""

import re
import struct
from pathlib import Path

import bpy
import numpy as np

from . import common as C


def _within(root, p):
    p = Path(p) if Path(p).is_absolute() else Path(root) / p
    if not str(p.resolve()).startswith(str(Path(root).resolve())):
        raise C.FeatureError(f"{p} is outside the project root {root}: copy it in")
    return p


def _import_table(path):
    """Import an FBX, read its first armature as a bone table, and remove everything the import added."""
    before_o, before_a, before_ac = set(bpy.data.objects), set(bpy.data.armatures), set(bpy.data.actions)
    try:
        bpy.ops.import_scene.fbx(filepath=str(path), automatic_bone_orientation=False, ignore_leaf_bones=False)
    except Exception as exc:  # noqa: BLE001
        raise C.FeatureError(f"{path.name} could not be read as an FBX: {exc}") from exc
    new = [o for o in bpy.data.objects if o not in before_o]
    arms = [o for o in new if o.type == "ARMATURE"]
    try:
        if not arms:
            raise C.FeatureError(f"{path.name} has no armature")
        return _table(arms[0])
    finally:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
        for a in [a for a in bpy.data.armatures if a not in before_a]:
            bpy.data.armatures.remove(a)
        for a in [a for a in bpy.data.actions if a not in before_ac]:
            bpy.data.actions.remove(a)


def _table(arm_ob):
    bones = {b.name: b for b in arm_ob.data.bones}
    ws = [arm_ob.matrix_world @ b.head_local for b in bones.values()] + [arm_ob.matrix_world @ b.tail_local for b in bones.values()]
    zs = [v.z for v in ws]
    ext = [max(v[i] for v in ws) - min(v[i] for v in ws) for i in range(3)]
    rows = {n: {"parent": b.parent.name if b.parent else None, "length": float(b.length)} for n, b in bones.items()}
    posed = [pb.name for pb in arm_ob.pose.bones if (np.abs(np.array(pb.rotation_euler[:]) if pb.rotation_mode != "QUATERNION" else np.array(pb.rotation_quaternion[:]) - np.array([1, 0, 0, 0])).max() > 1e-6
                                                        or np.abs(np.array(pb.location[:])).max() > 1e-6 or np.abs(np.array(pb.scale[:]) - 1).max() > 1e-6)]
    has_action = bool(arm_ob.animation_data and arm_ob.animation_data.action)
    return {"bones": rows, "height": float(max(zs) - min(zs)) if zs else 0.0, "up": "XYZ"[int(np.argmax(ext))], "posed": posed, "animated": has_action,
            "unit_scale_length": float(bpy.context.scene.unit_settings.scale_length)}


def skeleton_check(armature, fbx, target, expect_unit_scale, allow_extra_bones, root):
    if bool(armature) == bool(fbx):
        raise C.FeatureError("give one of armature or fbx: exactly one (the object to check)")
    names_from = (target or {}).get("names_from")
    ref = None
    if names_from:
        p = _within(root, names_from)
        if not p.exists():
            raise C.FeatureError(f"the reference {names_from} is unreadable (not found under the project root)")
        ref = _import_table(p)
    elif (target or {}).get("profile"):
        raise C.FeatureError(f"profile {(target or {}).get('profile')!r} needs a reference skeleton file: pass target.names_from (no profile table is bundled yet)")
    if armature:
        t = _table(C.need_object(armature, "ARMATURE"))
    else:
        p = _within(root, fbx)
        if not p.exists():
            raise C.FeatureError(f"{fbx} not found under the project root")
        t = _import_table(p)
    names = set(t["bones"])
    leaf = sorted(n for n in names if n.endswith("_end") and (ref is None or n not in ref["bones"]))
    reasons = []
    missing, extra, mism, root_info, scale = [], [], [], {"name": None, "expected": None}, 1.0
    if ref is not None:
        rnames = set(ref["bones"])
        missing = sorted(rnames - names)
        extra = sorted(n for n in names - rnames if n not in leaf)
        mism = [{"bone": n, "parent": t["bones"][n]["parent"], "expected_parent": ref["bones"][n]["parent"]} for n in sorted(names & rnames) if t["bones"][n]["parent"] != ref["bones"][n]["parent"]]
        roots = [n for n, b in t["bones"].items() if b["parent"] is None]
        rroots = [n for n, b in ref["bones"].items() if b["parent"] is None]
        root_info = {"name": roots[0] if roots else None, "expected": rroots[0] if rroots else None}
        scale = t["height"] / ref["height"] if ref["height"] else 1.0
    if leaf:
        reasons.append(f"{len(leaf)} leaf bone(s) the target does not have (export with add_leaf_bones off): {leaf[:6]}")
    if missing:
        reasons.append(f"missing bones: {missing[:10]}")
    if extra and not allow_extra_bones:
        reasons.append(f"extra bones: {extra[:10]}")
    if mism:
        reasons.append(f"{len(mism)} bone(s) with a different parent than the target")
    if root_info["name"] != root_info["expected"]:
        reasons.append(f"the root is {root_info['name']!r}, the target's is {root_info['expected']!r}")
    if abs(scale - float(expect_unit_scale)) > 0.05 * float(expect_unit_scale):
        reasons.append(f"unit scale reads {scale:.3g} against the reference (expected {expect_unit_scale}): a metres/centimetres or 100x export")
    posed = t["posed"] if not t["animated"] else []
    if posed:
        reasons.append(f"bones {posed[:6]} are posed with no animation: the rest pose is a posed frame (clear the pose before the export)")
    return {"ok": True, "leaf_bones": leaf, "missing_bones": missing, "extra_bones": extra, "hierarchy_mismatch": mism, "root": root_info, "unit_scale": round(scale, 4), "axes": {"up": t["up"], "forward": None},
            "rest_vs_frame": {"rest_pose_is_frame_zero": bool(posed), "posed_bones": posed}, "pass": not reasons, "reasons": reasons}


def fbx_version(path):
    with open(path, "rb") as fh:
        head = fh.read(27)
    if head.startswith(b"Kaydara FBX Binary"):
        return struct.unpack("<I", head[23:27])[0]
    with open(path, "rb") as fh:
        txt = fh.read(200).decode("latin1")
    m = re.search(r"FBX (\d+)\.(\d+)\.(\d+)", txt)
    return int(m.group(1)) * 1000 + int(m.group(2)) * 100 + int(m.group(3)) * 10 if m else 0


def engine_check(package_dir, engine, collision, receipt, root):
    pkg = _within(root, package_dir)
    fbxs = sorted(pkg.rglob("*.fbx")) if pkg.is_dir() else []
    if not fbxs:
        raise C.FeatureError(f"no FBX in {package_dir}: run export_piece first")
    fbx = fbxs[0]
    version = fbx_version(fbx)
    before_o, before_m, before_i = set(bpy.data.objects), set(bpy.data.materials), set(bpy.data.images)
    bpy.ops.import_scene.fbx(filepath=str(fbx))
    new = [o for o in bpy.data.objects if o not in before_o]
    try:
        meshes = sorted(re.sub(r"\.\d{3}$", "", o.name) for o in new if o.type == "MESH")        # an import into a scene that holds the same names suffixes them
        slots = sorted({re.sub(r"\.\d{3}$", "", s.material.name) for o in new if o.type == "MESH" for s in o.material_slots if s.material})
        refs = set()
        for mat in [m for m in bpy.data.materials if m not in before_m]:
            if mat.use_nodes:
                for n in mat.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image and n.image.filepath:
                        refs.add(n.image.filepath)
    finally:
        for o in new:
            bpy.data.objects.remove(o, do_unlink=True)
    textures_dir = pkg / "Textures"
    refpaths = {Path(bpy.path.abspath(r)).name for r in refs}
    present = {p.name for p in textures_dir.glob("*")} if textures_dir.is_dir() else set()
    missing = sorted(n for n in refpaths if n not in present)
    unref = sorted(n for n in present if n not in refpaths and n != "merge.json")
    render = [m for m in meshes if not re.match(r"^(UCX|UBX|UCP|USP)_", m)]
    cols = [m for m in meshes if re.match(r"^(UCX|UBX|UCP|USP)_", m)]
    expected = list(collision or [])
    mismatched = []
    for c in sorted(set(cols) | set(expected)):
        base = re.sub(r"^(UCX|UBX|UCP|USP)_", "", c)
        base = re.sub(r"_\d+$", "", base)
        if base not in render or (expected and c not in cols):
            mismatched.append(c)
    reasons = []
    if engine == "unreal" and version < 7400:
        reasons.append(f"FBX version {version} is older than Unreal's documented import (FBX 2020.2 = 7700)")
    if mismatched:
        reasons.append(f"collision meshes without a matching render mesh (UCX_<Render>_NN): {mismatched}")
    if missing:
        reasons.append(f"textures the materials name that are not in the package: {missing}")
    return {"ok": True, "fbx": {"file": fbx.name, "version_header": version, "mesh_names": meshes, "material_slots": slots, "texture_refs": sorted(refpaths)},
            "collision": {"expected": expected, "found": cols, "mismatched": mismatched}, "textures": {"missing": missing, "unreferenced": unref}, "receipt_recorded": bool(receipt), "receipt": receipt or None,
            "pass": not reasons, "reasons": reasons, "engine": engine}
