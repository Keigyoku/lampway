# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Private, read-only source FBX properties; never evaluated Blender/UE transforms.

Run with ordinary Python: --fbx FILE --out NEW_PRIVATE_JSON. Only the pinned
Blender binary FBX parser and its pure dependencies are loaded, without bpy or
the io_scene_fbx package bootstrap. No geometry or scene is imported.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import sys
import types
from pathlib import Path

SCHEMA = "lampway.source-fbx-bind-diagnostic/1"
PARSER_ROOT = Path(__file__).resolve().parents[2] / "upstream/scripts/addons_core/io_scene_fbx"
UPSTREAM_GITLINK = "fbe6228777e7d9afefcd61a413844e790ae75db7"
PARSER_HASHES = {
    "parse_fbx": "c976b04da54a50051df68834df09a675e43ddef616c8226becbf1f9671af7f93",
    "data_types": "1697b26e84cdabdebf8cf8c1dbb6e3b303705917aaf84eab835f0cdad6b26e20",
    "fbx_utils_threading": "2f33b0913f4ca89c5845009053d78558bef47b3487153cba43145901a45ab879",
}
TRANSFORM_PROPERTIES = {
    "Lcl Translation", "Lcl Rotation", "Lcl Scaling", "PreRotation", "PostRotation",
    "RotationOrder", "RotationActive", "InheritType", "RotationOffset", "RotationPivot",
    "ScalingOffset", "ScalingPivot", "GeometricTranslation", "GeometricRotation", "GeometricScaling",
}
VECTOR_PROPERTIES = TRANSFORM_PROPERTIES - {"RotationOrder", "RotationActive", "InheritType"}


def load_parser():
    sources = {}
    for child, expected in PARSER_HASHES.items():
        sources[child] = (PARSER_ROOT / (child + ".py")).read_bytes()
        if hashlib.sha256(sources[child]).hexdigest() != expected:
            raise ValueError("pinned parser source differs")
    name = "_lampway_source_fbx_parser"
    if name + ".parse_fbx" in sys.modules:
        return sys.modules[name + ".parse_fbx"]
    package = types.ModuleType(name)
    package.__path__ = [str(PARSER_ROOT)]
    sys.modules[name] = package
    keep_bytecode = sys.dont_write_bytecode
    try:
        sys.dont_write_bytecode = True
        for child in ("data_types", "fbx_utils_threading", "parse_fbx"):
            spec = importlib.util.spec_from_file_location(name + "." + child, PARSER_ROOT / (child + ".py"))
            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            # Execute the verified source bytes, never an existing bytecode cache.
            exec(compile(sources[child], str(PARSER_ROOT / (child + ".py")), "exec"), module.__dict__)
    finally:
        sys.dont_write_bytecode = keep_bytecode
    return sys.modules[name + ".parse_fbx"]


def _text(value):
    if not isinstance(value, bytes):
        raise ValueError("expected FBX string")
    return value.decode("utf-8")


def _values(values):
    out = []
    for value in values:
        if isinstance(value, bytes):
            value = _text(value)
        if not isinstance(value, (str, int, float, bool)):
            raise ValueError("unsupported property value")
        if isinstance(value, float) and not math.isfinite(value):
            raise ValueError("nonfinite property")
        out.append(value)
    return out


def _properties(element, selected=None):
    out = {}
    for block in element.elems:
        if block.id != b"Properties70":
            continue
        for prop in block.elems:
            if prop.id != b"P" or len(prop.props) < 4:
                raise ValueError("unsupported property layout")
            name = _text(prop.props[0])
            if selected is not None and name not in selected:
                continue
            if name in out:
                raise ValueError("duplicate property")
            out[name] = {"type": _text(prop.props[1]), "subtype": _text(prop.props[2]),
                         "flags": _text(prop.props[3]), "values": _values(prop.props[4:])}
            if selected is not None and name in VECTOR_PROPERTIES:
                values = out[name]["values"]
                if len(values) != 3 or any(type(v) not in (int, float) for v in values):
                    raise ValueError("invalid transform vector")
    return out


def _matrix(element):
    if len(element.props) != 1:
        raise ValueError("unsupported raw matrix layout")
    values = _values(element.props[0])
    if len(values) != 16 or any(type(v) not in (int, float) for v in values):
        raise ValueError("invalid raw matrix")
    return values


def collect(root, version):
    """Preserve authored values and relationships; do not compose/decompose frames.

    Raw matrices retain the parser's flat sequence. Missing properties are not
    replaced by inferred defaults. Pivots, pre/post rotations and inheritance
    modes are recorded without claiming an FBX evaluator or a UE adapter.
    """
    if version not in (7400, 7500):
        raise ValueError("unsupported binary FBX version")
    models, settings, connections, poses, clusters = {}, None, [], [], []
    object_ids = set()
    for element in root.elems:
        if element.id == b"GlobalSettings":
            if settings is not None:
                raise ValueError("duplicate global settings")
            settings = _properties(element)
        if element.id == b"Connections":
            for connection in element.elems:
                if connection.id != b"C" or len(connection.props) < 3:
                    raise ValueError("unsupported connection layout")
                values = _values(connection.props)
                if values[0] == "OO" and (len(values) != 3 or any(type(v) is not int for v in values[1:])):
                    raise ValueError("invalid OO relationship")
                connections.append(values)
        if element.id == b"Objects":
            for node in element.elems:
                if node.props and type(node.props[0]) is int:
                    if node.props[0] in object_ids:
                        raise ValueError("duplicate source object identity")
                    object_ids.add(node.props[0])
                if node.id == b"Model":
                    if len(node.props) != 3 or type(node.props[0]) is not int or node.props[0] in models or node.props[0] == 0:
                        raise ValueError("invalid or duplicate model identity")
                    models[node.props[0]] = {"id": node.props[0], "name": _text(node.props[1].split(b"\x00")[0]),
                        "kind": _text(node.props[2]), "properties": _properties(node, TRANSFORM_PROPERTIES)}
                elif node.id == b"Pose":
                    if len(node.props) != 3 or type(node.props[0]) is not int:
                        raise ValueError("invalid pose identity")
                    pose = {"id": node.props[0], "kind": _text(node.props[2]), "nodes": []}
                    pose_ids = set()
                    for entry in node.elems:
                        if entry.id == b"PoseNode":
                            row = {}
                            for field in entry.elems:
                                if field.id == b"Node":
                                    if "model_id" in row or len(field.props) != 1 or type(field.props[0]) is not int:
                                        raise ValueError("invalid or duplicate pose node identity")
                                    row["model_id"] = field.props[0]
                                elif field.id == b"Matrix":
                                    if "raw_matrix_values" in row:
                                        raise ValueError("duplicate pose matrix")
                                    row["raw_matrix_values"] = _matrix(field)
                            if set(row) != {"model_id", "raw_matrix_values"}:
                                raise ValueError("incomplete pose node")
                            if row["model_id"] in pose_ids:
                                raise ValueError("duplicate pose model")
                            pose_ids.add(row["model_id"])
                            pose["nodes"].append(row)
                    poses.append(pose)
                elif node.id == b"Deformer" and len(node.props) > 2 and node.props[2] == b"Cluster":
                    if len(node.props) != 3 or type(node.props[0]) is not int:
                        raise ValueError("invalid cluster identity")
                    cluster = {"id": node.props[0], "name": _text(node.props[1].split(b"\x00")[0]), "raw_matrices": {}}
                    for field in node.elems:
                        if field.id in (b"Transform", b"TransformLink", b"TransformAssociateModel"):
                            key = _text(field.id)
                            if key in cluster["raw_matrices"]:
                                raise ValueError("duplicate cluster matrix")
                            cluster["raw_matrices"][key] = _matrix(field)
                    clusters.append(cluster)
    if not models or settings is None:
        raise ValueError("missing source models or global settings")
    for pose in poses:
        if any(row["model_id"] not in models for row in pose["nodes"]):
            raise ValueError("pose names an unrecorded model")
    identities = [*models, *(p["id"] for p in poses), *(c["id"] for c in clusters)]
    if len(identities) != len(set(identities)):
        raise ValueError("duplicate source object identity")
    usf = settings.get("UnitScaleFactor", {}).get("values", [])
    if len(usf) != 1 or type(usf[0]) not in (int, float) or usf[0] <= 0:
        raise ValueError("missing or invalid unit scale factor")
    parents, nonhierarchy = {}, []
    for connection in connections:
        kind, child, parent = connection[:3]
        if kind == "OO" and child in models:
            if parent != 0 and parent not in models:
                if parent not in object_ids:
                    raise ValueError("unknown connection target")
                # Pinned writer: Model->Cluster OO is a skin dependency, not a
                # model parent (export_fbx_bin.py, skinning connections).
                nonhierarchy.append(connection)
                continue
            if child in parents:
                raise ValueError("unsupported multiple or nonmodel parent")
            parents[child] = parent
    for ident, row in models.items():
        if ident not in parents:
            raise ValueError("model has no recorded root relationship")
        parent, ancestors = parents[ident], []
        seen = {ident}
        while parent != 0:
            if parent in seen:
                raise ValueError("cyclic model hierarchy")
            if parent not in parents:
                raise ValueError("incomplete ancestor hierarchy")
            seen.add(parent)
            ancestors.append(parent)
            parent = parents[parent]
        row.update(parent_id=parents[ident], ancestors_root_first=list(reversed(ancestors)))
    limb = [r for r in models.values() if r["kind"] == "LimbNode"]
    ancestors = {a for r in limb for a in r["ancestors_root_first"]}
    nonunit = {ident for ident, row in models.items()
               if "Lcl Scaling" in row["properties"] and row["properties"]["Lcl Scaling"]["values"] != [1., 1., 1.]}
    return {"schema": SCHEMA, "read_only": True, "fbx_version": version,
        "source_profile": "FBX binary authored properties and OO model hierarchy",
        "frame_annotations": {"axes": "GlobalSettings authored flags; no coordinate conversion",
            "local_transforms": "Properties70 authored values; missing properties remain absent",
            "matrices": "flat raw FBX array order, not an evaluated world transform",
            "ancestors": "root-first OO parent IDs; each ancestor's properties are in models",
            "engine_interpretation": "not measured; this report is not native UE bind acceptance"},
        "global_settings": settings, "models": sorted(models.values(), key=lambda r: r["id"]),
        "raw_connections": connections, "poses": poses, "clusters": clusters,
        "nonhierarchy_model_connections": nonhierarchy,
        "scale_blind_spot": "UnitScaleFactor and LimbNode local scaling alone omit ancestor scaling; no composed engine scale inferred",
        "counts": {"models": len(models), "limb_nodes": len(limb), "model_roots": sum(p == 0 for p in parents.values()),
            "poses": len(poses), "clusters": len(clusters), "nonunit_local_scale_models": len(nonunit),
            "nonhierarchy_model_connections": len(nonhierarchy),
            "nonunit_scale_ancestors_of_limb_nodes": len(nonunit & ancestors)}}


def diagnose(path):
    path = Path(path)
    if not path.is_file():
        raise ValueError("explicit source FBX must be a file")
    parser = load_parser()
    version = parser.parse_version(path)
    if version not in (7400, 7500):
        raise ValueError("unsupported binary FBX header/version")
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    root, version = parser.parse(path)
    report = collect(root, version)
    if hashlib.sha256(path.read_bytes()).hexdigest() != before:
        raise ValueError("source changed during diagnostic")
    report["source_sha256"] = before
    report["parser"] = {"upstream_gitlink": UPSTREAM_GITLINK, "bootstrap_imported": False,
        "source_sha256": {name: hashlib.sha256((PARSER_ROOT / (name + ".py")).read_bytes()).hexdigest()
                          for name in ("parse_fbx", "data_types", "fbx_utils_threading")}}
    return report


def write_exclusive(path, report):
    payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o600)
    created = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
    except Exception:
        # Remove only this call's newly created inode, never a replaced path.
        try:
            current = os.stat(path, follow_symlinks=False)
            if (current.st_dev, current.st_ino) == (created.st_dev, created.st_ino):
                os.unlink(path)
        except OSError:
            pass
        raise


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        # argparse's message can contain caller paths; never echo it.
        self.exit(2, "error: invalid diagnostic arguments\nhelp[1]: supply --fbx FILE --out NEW_PRIVATE_JSON\n")


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument("--fbx", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        report = diagnose(args.fbx)
        write_exclusive(args.out, report)
    except Exception as error:
        print("error: source FBX diagnostic refused (" + type(error).__name__ + ")")
        print("help[1]: supply a valid binary FBX7400/7500 and a new private output file")
        return 1
    print(json.dumps({"source_sha256": report["source_sha256"], "counts": report["counts"]}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
