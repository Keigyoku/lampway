# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only rest-frame inspection in Blender; writes an exclusive private JSON.

FRAME_DIAG_ARMATURE and FRAME_DIAG_OUTPUT are required. No scene writes, saving,
normalization, projection, credential reads or asset copying occur here.
"""
import hashlib
import inspect
import json
import os
from pathlib import Path

import numpy as np

SCHEMA = "lampway.native-frame-diagnostic/1"
TARGETS = frozenset(("pinky_02_in_l", "ring_03_half_l", "ring_02_dip_l"))


def matrix_metrics(matrix):
    frame = np.asarray(matrix, dtype=float)
    if frame.shape != (3, 3) or not np.isfinite(frame).all():
        raise ValueError("frame must be a finite 3x3 matrix")
    gram = frame.T @ frame
    det = float(np.linalg.det(frame))
    return {"matrix": frame.tolist(), "det": det,
            "gram_max_error": float(np.max(np.abs(gram - np.eye(3)))),
            "singular_values": np.linalg.svd(frame, compute_uv=False).tolist(),
            "proper_rotation": bool(abs(det - 1) < 1e-6 and np.allclose(gram, np.eye(3), atol=1e-6))}


def frame_variants(matrix):
    raw = np.asarray(matrix, dtype=float)
    matrix_metrics(raw)
    norms = np.linalg.norm(raw, axis=0)
    if np.any(norms == 0):
        raise ValueError("frame contains a zero column")
    normalized = raw / norms
    return {label: matrix_metrics(frame) for label, frame in (
        ("raw", raw), ("normalized", normalized),
        ("round6", np.round(normalized, 6)), ("round12", np.round(normalized, 12)))}


def module_evidence(module):
    path = Path(module.__file__).resolve()
    return {"loaded_file": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def convention_diagnostics(rt, rig):
    """Explain the installed detector's samples without changing its verdict.

    Orthogonality of Y to a joint line does not establish alignment of X; record
    all three axes so geometry and frame disagreement remain distinguishable.
    """
    sampled = rt.convention_angles(rig)
    children = rt._single_child(rig)
    parameter = inspect.signature(rt.RC.classify_convention).parameters.get("tol")
    tolerance = float(parameter.default) if parameter is not None else 10.0
    rows = []
    for name, measured_y in sorted(sampled.items()):
        child = children[name]
        angles = {axis: rt.RC.along_axis_angle(rig["frames"][name], rig["heads"][name],
                                             rig["heads"][child], axis)
                  for axis in "xyz"}
        if not np.isclose(angles["y"], measured_y, atol=1e-9, rtol=0):
            raise ValueError("installed convention sample disagrees with its axis measurement")
        rows.append({"bone": name, "child": child, "angles_deg": angles})
    return {"class": rt.RC.classify_convention(list(sampled.values())),
            "tolerance_deg": tolerance, "rows": rows,
            "outside_blender_y_bar": [r["bone"] for r in rows if r["angles_deg"]["y"] > tolerance],
            "outside_ue_y_bar": [r["bone"] for r in rows if abs(r["angles_deg"]["y"] - 90) > tolerance],
            "unsampled": sorted(set(rig["names"]) - set(sampled))}


def collect(bpy, rt, nr, armature):
    ob = bpy.data.objects.get(armature)
    if ob is None or ob.type != "ARMATURE":
        raise ValueError("explicit armature must exist and have ARMATURE type")
    rig = rt.read(ob)
    read_frames = rig["frames"]
    rows, invalid = {}, {}
    for bone in ob.data.bones:
        raw = np.asarray((ob.matrix_world @ bone.matrix_local).to_3x3(), dtype=float)
        variants = frame_variants(raw)
        variants["rt_read"] = matrix_metrics(read_frames[bone.name])
        for label, metrics in variants.items():
            if not metrics["proper_rotation"]:
                invalid.setdefault(label, []).append(bone.name)
        if bone.name in TARGETS or any(not v["proper_rotation"] for v in variants.values()):
            rows[bone.name] = {"local_matrix": [list(r) for r in bone.matrix_local],
                               "bone_matrix": [list(r) for r in bone.matrix],
                               "head": list(bone.head), "tail": list(bone.tail),
                               "parent": bone.parent.name if bone.parent else None,
                               "variants": variants}
    return {"schema": SCHEMA, "read_only": True, "armature": ob.name,
            "bone_count": len(ob.data.bones), "object_matrix": [list(r) for r in ob.matrix_world],
            "blender_version": bpy.app.version_string, "frames": rows, "invalid_by_variant": invalid,
            "convention": convention_diagnostics(rt, rig),
            "rest_fingerprint": rt._fingerprint(ob, rig),
            "rest_input": {"names": rig["names"], "parents": rig["parents"], "heads_m": rig["heads"],
                           "frames": {name: np.asarray(frame).tolist() for name, frame in read_frames.items()}},
            "loaded_modules": {"rig_tools": module_evidence(rt), "normalize_rigged": module_evidence(nr),
                               "rig_core": module_evidence(rt.RC)},
            "convention_function_source": inspect.getsource(rt.convention_angles),
            "classifier_function_source": inspect.getsource(rt.RC.classify_convention),
            "bones_function_source": inspect.getsource(nr._bones)}


def write_exclusive(path, result):
    payload = json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(payload)


def main():
    try:
        import bpy
        from mixar.modules.lampway_tools.features import rig_tools as rt, normalize_rigged as nr
        armature = os.environ["FRAME_DIAG_ARMATURE"]
        output = Path(os.environ["FRAME_DIAG_OUTPUT"])
        if not output.is_absolute():
            raise ValueError("diagnostic output must be absolute")
        result = collect(bpy, rt, nr, armature)
        write_exclusive(output, result)
    except Exception as error:
        # Private paths and object names belong only in the private receipt.
        print("error: native frame diagnostic refused (" + type(error).__name__ + ")")
        print("help[1]: supply an existing armature and a new absolute private JSON path")
        return 1
    print("LAMPWAY_NATIVE_FRAME_DIAGNOSTIC " + json.dumps({
        "schema": SCHEMA, "read_only": True, "json_written": True, "bone_count": result["bone_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
