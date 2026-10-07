# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Compare captured UE bind TRS locally; no UE API or transform composition.

Input schema lampway.ue-bind-capture/1 declares translation_unit cm,
quaternion_order xyzw, and spaces local=parent_local/component=component.
Both native and candidate tables retain every bone, including extra containers.
No basis conversion is inferred. Output contains derived deltas only.
"""
import argparse
import hashlib
import json
import math
import os
import re
import tempfile
from pathlib import Path

SCHEMA = "lampway.ue-bind-comparison/1"
CAPTURE_SCHEMA = "lampway.ue-bind-capture/1"
BARS = {"position_cm": 0.01, "rotation_deg": 0.01, "scale": 0.0001}
CONVENTIONS = {"translation_unit": "cm", "quaternion_order": "xyzw",
               "spaces": {"local": "parent_local", "component": "component"}}
BOOL_SETTINGS = {"convert_scene", "force_front_x", "convert_scene_unit", "use_t0_as_ref_pose",
                 "update_skeleton_reference_pose", "import_animations", "import_meshes_in_bone_hierarchy"}


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise ValueError("invalid capture fields")


def _vector(value, length):
    if not isinstance(value, list) or len(value) != length or any(type(v) not in (int, float) for v in value):
        raise ValueError("invalid numeric vector")
    result = [float(v) for v in value]
    if not all(math.isfinite(v) for v in result):
        raise ValueError("nonfinite vector")
    return result


def _unit(q):
    # Scaling first avoids overflow even for finite very large quaternions.
    largest = max(abs(v) for v in q)
    if largest == 0:
        raise ValueError("zero quaternion")
    scaled = [v / largest for v in q]
    norm = math.hypot(*scaled)
    return [v / norm for v in scaled]


def _name(value):
    if (not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value)
            or any(c in value for c in ("/", "\\")) or value.startswith("~") or re.match(r"^[A-Za-z]:", value)):
        raise ValueError("invalid bone identity")
    return value


def _table(rows):
    if not isinstance(rows, list) or not rows:
        raise ValueError("empty bone table")
    result = {}
    for row in rows:
        _keys(row, ("name", "parent", "local", "component"))
        name = _name(row["name"])
        if name in result:
            raise ValueError("duplicate bone identity")
        parent = None if row["parent"] is None else _name(row["parent"])
        result[name] = {"parent": parent}
        for space in ("local", "component"):
            transform = row[space]
            _keys(transform, ("translation_cm", "quaternion_xyzw", "scale_xyz"))
            result[name][space] = {"translation_cm": _vector(transform["translation_cm"], 3),
                                  "quaternion_xyzw": _vector(transform["quaternion_xyzw"], 4),
                                  "scale_xyz": _vector(transform["scale_xyz"], 3)}
            _unit(result[name][space]["quaternion_xyzw"])
    for name in result:
        seen, current = set(), name
        while current is not None:
            if current not in result:
                raise ValueError("unrecorded parent")
            if current in seen:
                raise ValueError("cyclic hierarchy")
            seen.add(current)
            current = result[current]["parent"]
    return result


def _importer_settings(settings):
    if not isinstance(settings, dict) or set(settings) - BOOL_SETTINGS - {"offset_uniform_scale", "skeleton_selection", "import_method"}:
        raise ValueError("unsupported importer metadata")
    for name, value in settings.items():
        if name in BOOL_SETTINGS and type(value) is not bool:
            raise ValueError("invalid importer boolean")
        if name == "offset_uniform_scale" and (type(value) not in (int, float) or not math.isfinite(value)):
            raise ValueError("invalid importer scalar")
        if name == "skeleton_selection" and value not in ("new_transient", "existing", "none"):
            raise ValueError("unsafe skeleton metadata")
        if name == "import_method" and value not in ("legacy", "interchange"):
            raise ValueError("unsafe importer metadata")
    return dict(settings)


def _delta(reference, candidate):
    t = [g - r for g, r in zip(candidate["translation_cm"], reference["translation_cm"])]
    s = [g - r for g, r in zip(candidate["scale_xyz"], reference["scale_xyz"])]
    ratios = [g / r if r != 0 else None for g, r in zip(candidate["scale_xyz"], reference["scale_xyz"])]
    rx, ry, rz, rw = _unit(reference["quaternion_xyzw"])
    gx, gy, gz, gw = _unit(candidate["quaternion_xyzw"])
    # Hamilton product got * inverse(ref), xyzw; no hemisphere/sign rewrite.
    q = [-gw * rx + gx * rw - gy * rz + gz * ry,
         -gw * ry + gx * rz + gy * rw - gz * rx,
         -gw * rz - gx * ry + gy * rx + gz * rw,
         gw * rw + gx * rx + gy * ry + gz * rz]
    angle = math.degrees(2 * math.acos(min(1.0, abs(math.fsum(a * b for a, b in zip((gx, gy, gz, gw), (rx, ry, rz, rw)))))))
    metrics = {"position_cm": math.hypot(*t), "rotation_deg": angle, "scale": max(abs(v) for v in s)}
    if not all(math.isfinite(v) for v in (*t, *s, *q, *(r for r in ratios if r is not None), *metrics.values())):
        raise ValueError("nonfinite derived comparison")
    return {"translation_delta_cm": t, "quaternion_delta_xyzw": q, "scale_delta": s, "scale_ratio": ratios,
            "metrics": metrics, "over_limit": any(metrics[k] > BARS[k] for k in BARS)}


def _summary(rows):
    return {"compared_count": len(rows), "over_limit_count": sum(row["over_limit"] for row in rows),
            "worst": {key: max((row["metrics"][key] for row in rows), default=None) for key in BARS}}


def compare_capture(capture):
    _keys(capture, ("schema", "provenance", "conventions", "tables"), ("native_self_control", "importer_settings"))
    if capture["schema"] != CAPTURE_SCHEMA or capture["conventions"] != CONVENTIONS:
        raise ValueError("unsupported capture schema or frame declaration")
    provenance = capture["provenance"]
    _keys(provenance, ("candidate_fbx_sha256", "native_reference_sha256", "engine", "capture_code_sha256", "comparator_description"))
    for key in ("candidate_fbx_sha256", "native_reference_sha256", "capture_code_sha256"):
        if not isinstance(provenance[key], str) or not re.fullmatch(r"[0-9a-f]{64}", provenance[key]):
            raise ValueError("invalid provenance hash")
    for key in ("engine", "comparator_description"):
        if not isinstance(provenance[key], str) or not provenance[key].strip():
            raise ValueError("missing capture provenance")
    self_control = capture.get("native_self_control", False)
    if type(self_control) is not bool:
        raise ValueError("invalid self-control flag")
    if provenance["candidate_fbx_sha256"] == provenance["native_reference_sha256"] and not self_control:
        raise ValueError("native reference must be independent")
    _keys(capture["tables"], ("native", "candidate"))
    native, candidate = (_table(capture["tables"][key]) for key in ("native", "candidate"))
    missing, extra = sorted(set(native) - set(candidate)), sorted(set(candidate) - set(native))
    shared = sorted(set(native) & set(candidate))
    parent_changes = [{"name": name, "native_parent": native[name]["parent"], "candidate_parent": candidate[name]["parent"]}
                      for name in shared if native[name]["parent"] != candidate[name]["parent"]]
    tables = {space: [{"name": name, **_delta(native[name][space], candidate[name][space])} for name in shared]
              for space in ("local", "component")}
    summaries = {space + "_summary": _summary(rows) for space, rows in tables.items()}
    report = {"schema": SCHEMA, "bars": dict(BARS), "spaces": dict(CONVENTIONS["spaces"]),
        "quaternion_delta_convention": "got * inverse(ref), normalized for comparison only, xyzw Hamilton product",
        "native_self_control": self_control, "provenance_hashes": {key: provenance[key] for key in
            ("candidate_fbx_sha256", "native_reference_sha256", "capture_code_sha256")},
        "missing": missing, "extra": extra, "parent_changes": parent_changes, **tables, **summaries,
        "counts": {"native": len(native), "candidate": len(candidate), "compared": len(shared),
                   "missing": len(missing), "extra": len(extra), "parent_changes": len(parent_changes)},
        "pass": bool(shared) and not missing and not extra and not parent_changes and
                not any(summary["over_limit_count"] for summary in summaries.values()),
        "limits": "derived diagnostics only; differently parented local frames are identified by parent_changes; no importer calibration, transform composition, or native bind acceptance inferred"}
    if "importer_settings" in capture:
        report["importer_settings"] = _importer_settings(capture["importer_settings"])
    return report


def write_atomic_exclusive(path, report):
    payload = (json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n").encode()
    target = Path(path)
    fd, temporary = tempfile.mkstemp(prefix=".ue-bind-", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        # A link installs the complete file atomically and refuses every existing
        # destination, including symlinks; no replace/overwrite operation exists.
        os.link(temporary, target)
    finally:
        os.unlink(temporary)


def _unique_json(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def compare_file(path):
    source = Path(path)
    data = source.read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    capture = json.loads(data, object_pairs_hook=_unique_json)
    report = compare_capture(capture)
    if hashlib.sha256(source.read_bytes()).hexdigest() != digest:
        raise ValueError("source capture changed")
    report["capture_sha256"] = digest
    return report


class PrivateArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        self.exit(2, "error: invalid bind comparison arguments\nhelp[1]: supply --capture FILE --out NEW_JSON\n")


def main(argv=None):
    parser = PrivateArgumentParser(description=__doc__)
    parser.add_argument("--capture", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    try:
        report = compare_file(args.capture)
        write_atomic_exclusive(args.out, report)
    except Exception as error:
        print("error: bind capture comparison refused (" + type(error).__name__ + ")")
        print("help[1]: supply a valid declared bind capture and a new output file")
        return 1
    counts = {**report["counts"], "local_over_limit": report["local_summary"]["over_limit_count"],
              "component_over_limit": report["component_summary"]["over_limit_count"]}
    print(json.dumps({"capture_sha256": report["capture_sha256"], "counts": counts}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
