# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Raw ancestor properties expose scale omitted by a LimbNode-only read."""
import importlib.util
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("fbx_bind_diagnostics", Path(__file__).parents[2] / "scripts/lampway/diagnose_fbx_bind.py")
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


def elem(name, props=(), children=()):
    return SimpleNamespace(id=name, props=list(props), elems=list(children))


def prop(name, *values):
    return elem(b"P", (name, b"Vector3D", b"Vector", b"", *values))


def fixture():
    return elem(b"", children=[
        elem(b"GlobalSettings", children=[elem(b"Properties70", children=[prop(b"UnitScaleFactor", 1.0), prop(b"UpAxis", 1)])]),
        elem(b"Objects", children=[
            elem(b"Model", (10, b"private_container\x00\x01Model", b"Null"), [elem(b"Properties70", children=[prop(b"Lcl Scaling", 100., 100., 100.)])]),
            elem(b"Model", (20, b"private_root\x00\x01Model", b"LimbNode"), [elem(b"Properties70", children=[prop(b"Lcl Scaling", 1., 1., 1.)])]),
            elem(b"Model", (30, b"private_child\x00\x01Model", b"LimbNode"), [elem(b"Properties70", children=[prop(b"Lcl Translation", 0., 0., 1.)])]),
        ]),
        elem(b"Connections", children=[elem(b"C", (b"OO", 10, 0)), elem(b"C", (b"OO", 20, 10)), elem(b"C", (b"OO", 30, 20))]),
    ])


def test_container100_is_recorded_despite_usf1_and_local_bone_scale1():
    report = DIAG.collect(fixture(), 7400)
    rows = {r["id"]: r for r in report["models"]}
    assert rows[30]["ancestors_root_first"] == [10, 20]
    assert rows[20]["parent_id"] == 10
    assert report["global_settings"]["UnitScaleFactor"]["values"] == [1.0]
    assert rows[10]["properties"]["Lcl Scaling"]["values"] == [100., 100., 100.]
    assert rows[20]["properties"]["Lcl Scaling"]["values"] == [1., 1., 1.]
    assert report["counts"]["nonunit_scale_ancestors_of_limb_nodes"] == 1
    assert "evaluated_world_matrix" not in rows[30]


@pytest.mark.parametrize("version", [7400, 7500])
def test_raw_pose_and_cluster_arrays_are_preserved_without_conversion(version):
    root = fixture()
    matrix = list(range(16))
    root.elems[1].elems.extend([
        elem(b"Pose", (40, b"private_pose", b"BindPose"), [elem(b"PoseNode", children=[
            elem(b"Node", (20,)), elem(b"Matrix", (matrix,))])]),
        elem(b"Deformer", (50, b"private_cluster", b"Cluster"), [
            elem(b"Transform", (matrix,)), elem(b"TransformLink", (matrix[::-1],))]),
    ])
    before = copy.deepcopy(root)
    report = DIAG.collect(root, version)
    assert root == before
    assert report["poses"][0]["nodes"][0]["raw_matrix_values"] == matrix
    assert report["clusters"][0]["raw_matrices"]["TransformLink"] == matrix[::-1]
    assert "not measured" in report["frame_annotations"]["engine_interpretation"]
    assert "Lcl Scaling" not in report["models"][2]["properties"]


def test_model_to_cluster_oo_is_retained_without_becoming_a_parent():
    root = fixture()
    root.elems[1].elems.append(elem(b"Deformer", (50, b"cluster", b"Cluster")))
    root.elems[2].elems.append(elem(b"C", (b"OO", 20, 50)))
    report = DIAG.collect(root, 7400)
    assert report["models"][1]["parent_id"] == 10
    assert report["models"][2]["ancestors_root_first"] == [10, 20]
    assert report["nonhierarchy_model_connections"] == [["OO", 20, 50]]


@pytest.mark.parametrize("bad", ["cycle", "duplicate_parent", "missing_parent", "duplicate_model", "nonfinite", "matrix", "unit", "missing_connection"])
def test_invalid_or_unsupported_hierarchy_and_properties_refuse(bad):
    root = fixture()
    if bad == "cycle":
        root.elems[2].elems[0].props[2] = 30
    elif bad == "duplicate_parent":
        root.elems[2].elems.append(elem(b"C", (b"OO", 20, 0)))
    elif bad == "missing_parent":
        root.elems[2].elems[1].props[2] = 999
    elif bad == "duplicate_model":
        root.elems[1].elems.append(copy.deepcopy(root.elems[1].elems[0]))
    elif bad == "nonfinite":
        root.elems[1].elems[0].elems[0].elems[0].props[4] = float("nan")
    elif bad == "matrix":
        root.elems[1].elems.append(elem(b"Deformer", (50, b"cluster", b"Cluster"), [elem(b"Transform", ([1., 2.],))]))
    elif bad == "unit":
        root.elems[0].elems[0].elems[0].props[4] = 0.
    else:
        root.elems[2].elems.pop()
    with pytest.raises(ValueError):
        DIAG.collect(root, 7400)


def binary_fixture(path, version=7400):
    """Use Blender's maintained writer to feed its real pure binary parser."""
    DIAG.load_parser()
    spec = importlib.util.spec_from_file_location("_lampway_source_fbx_parser.encode_bin", DIAG.PARSER_ROOT / "encode_bin.py")
    encoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(encoder)
    def convert(node):
        result = encoder.FBXElem(node.id)
        for value in node.props:
            if isinstance(value, bytes):
                result.add_string(value)
            elif type(value) is int:
                result.add_int64(value)
            elif type(value) is float:
                result.add_float64(value)
            else:
                result.add_float64_array(value)
        result.elems = [convert(child) for child in node.elems]
        return result
    encoder.write(path, convert(fixture()), version)


@pytest.mark.parametrize("version", [7400, 7500])
def test_real_binary_parser_and_standalone_cli_keep_source_and_private_output(tmp_path, version):
    source = tmp_path / "private_source.fbx"
    output = tmp_path / "private_report.json"
    binary_fixture(source, version)
    before = source.read_bytes()
    code = '''import runpy,sys
d=runpy.run_path(sys.argv[1]);rc=d['main'](sys.argv[2:])
assert 'bpy' not in sys.modules and 'io_scene_fbx' not in sys.modules
raise SystemExit(rc)
'''
    process = subprocess.run([sys.executable, "-I", "-c", code, str(Path(DIAG.__file__)),
                              "--fbx", str(source), "--out", str(output)], capture_output=True, text=True)
    assert process.returncode == 0, process.stdout + process.stderr
    report = json.loads(output.read_text())
    assert report["fbx_version"] == version
    assert report["models"][2]["ancestors_root_first"] == [10, 20]
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
    assert output.stat().st_mode & 0o777 == 0o600
    summary = json.loads(process.stdout)
    assert set(summary) == {"source_sha256", "counts"}
    assert not process.stderr
    assert all(value not in process.stdout for value in (str(tmp_path), "private_container", "private_root", "private_child"))


def test_output_is_exclusive_and_symlink_safe_and_serialization_precedes_creation(tmp_path):
    output = tmp_path / "private_report.json"
    DIAG.write_exclusive(output, {"a": 1})
    before = output.read_bytes()
    with pytest.raises(FileExistsError):
        DIAG.write_exclusive(output, {"a": 2})
    link = tmp_path / "link.json"
    link.symlink_to(output)
    with pytest.raises(FileExistsError):
        DIAG.write_exclusive(link, {"a": 2})
    assert output.read_bytes() == before
    invalid = tmp_path / "invalid.json"
    with pytest.raises(ValueError):
        DIAG.write_exclusive(invalid, {"value": float("nan")})
    assert not invalid.exists()


@pytest.mark.parametrize("bad", ["missing", "ascii", "truncated", "unsupported"])
def test_cli_sanitizes_path_and_parser_failures_and_writes_no_report(tmp_path, capsys, bad):
    source = tmp_path / "private_source.fbx"
    output = tmp_path / "private_report.json"
    if bad == "ascii":
        source.write_bytes(b"; FBX 7.4.0 project-private-content")
    elif bad == "truncated":
        source.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00" + (7400).to_bytes(4, "little") + b"x")
    elif bad == "unsupported":
        source.write_bytes(b"Kaydara FBX Binary  \x00\x1a\x00" + (7800).to_bytes(4, "little"))
    assert DIAG.main(["--fbx", str(source), "--out", str(output)]) == 1
    log = capsys.readouterr()
    assert str(tmp_path) not in log.out + log.err
    assert all(value not in log.out + log.err for value in ("private_source", "private_report", "project-private-content"))
    assert not output.exists()


def test_unknown_flags_do_not_echo_owner_values(capsys):
    with pytest.raises(SystemExit) as error:
        DIAG.main(["--private-owner-path", "/private-owner-value"])
    assert error.value.code == 2
    log = capsys.readouterr()
    assert "owner" not in log.out + log.err


def test_modified_parser_sources_are_refused(tmp_path, monkeypatch):
    for name in DIAG.PARSER_HASHES:
        (tmp_path / (name + ".py")).write_text("raise RuntimeError('should not execute')")
    monkeypatch.setattr(DIAG, "PARSER_ROOT", tmp_path)
    with pytest.raises(ValueError, match="pinned parser"):
        DIAG.load_parser()


@pytest.mark.parametrize("bad", ["pose_props", "node_type", "duplicate_node", "duplicate_matrix", "duplicate_pose_model", "unknown_model", "vector"])
def test_malformed_pose_and_transform_layouts_refuse(bad):
    root = fixture()
    pose_node = elem(b"PoseNode", children=[elem(b"Node", (20,)), elem(b"Matrix", (list(range(16)),))])
    pose = elem(b"Pose", (40, b"pose", b"BindPose"), [pose_node])
    root.elems[1].elems.append(pose)
    if bad == "pose_props":
        pose.props.pop()
    elif bad == "node_type":
        pose_node.elems[0].props[0] = "20"
    elif bad == "duplicate_node":
        pose_node.elems.append(copy.deepcopy(pose_node.elems[0]))
    elif bad == "duplicate_matrix":
        pose_node.elems.append(copy.deepcopy(pose_node.elems[1]))
    elif bad == "duplicate_pose_model":
        pose.elems.append(copy.deepcopy(pose_node))
    elif bad == "unknown_model":
        pose_node.elems[0].props[0] = 999
    else:
        root.elems[1].elems[0].elems[0].elems[0].props.pop()
    with pytest.raises(ValueError):
        DIAG.collect(root, 7400)


def test_write_failure_removes_only_new_partial_output(tmp_path, monkeypatch):
    output = tmp_path / "partial.json"
    original_fchmod = DIAG.os.fchmod
    def refuse(fd, mode):
        raise OSError("private write failure")
    monkeypatch.setattr(DIAG.os, "fchmod", refuse)
    with pytest.raises(OSError):
        DIAG.write_exclusive(output, {"a": 1})
    assert not output.exists()
    monkeypatch.setattr(DIAG.os, "fchmod", original_fchmod)
    DIAG.write_exclusive(output, {"original": True})
    before = output.read_bytes()
    monkeypatch.setattr(DIAG.os, "fchmod", refuse)
    with pytest.raises(FileExistsError):
        DIAG.write_exclusive(output, {"a": 1})
    assert output.read_bytes() == before
