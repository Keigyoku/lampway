# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Signed bind deltas keep all current bars and preserve captured input."""
import copy
import importlib.util
import hashlib
import json
import math
import os
import subprocess
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("compare_ue_bind_capture", Path(__file__).parents[2] / "scripts/lampway/compare_ue_bind_capture.py")
COMPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(COMPARE)


def transform(scale=(1., 1., 1.), q=(0., 0., 0., 1.), t=(0., 0., 0.)):
    return {"translation_cm": list(t), "quaternion_xyzw": list(q), "scale_xyz": list(scale)}


def bone(name, parent=None, **kwargs):
    return {"name": name, "parent": parent, "local": transform(**kwargs), "component": transform(**kwargs)}


def capture():
    return {"schema": COMPARE.CAPTURE_SCHEMA,
        "provenance": {"candidate_fbx_sha256": "a" * 64, "native_reference_sha256": "b" * 64,
            "engine": "UE5.8-test", "capture_code_sha256": "c" * 64, "comparator_description": "raw declared transforms from a synthetic control"},
        "conventions": {"translation_unit": "cm", "quaternion_order": "xyzw", "spaces": {"local": "parent_local", "component": "component"}},
        "tables": {"native": [bone("root"), bone("child", "root")], "candidate": [bone("root"), bone("child", "root")]}}


def test_scale100_is_not_hidden_by_local_or_container_stripping():
    data = capture()
    data["tables"]["candidate"] = [bone("container", scale=(100., 100., 100.)), bone("root", "container"), bone("child", "root")]
    for row in data["tables"]["candidate"][1:]:
        row["component"]["scale_xyz"] = [100., 100., 100.]
    before = copy.deepcopy(data)
    out = COMPARE.compare_capture(data)
    assert out["extra"] == ["container"]
    assert out["parent_changes"] == [{"name": "root", "native_parent": None, "candidate_parent": "container"}]
    assert out["component"][0]["scale_delta"] == [99., 99., 99.]
    assert out["component"][0]["scale_ratio"] == [100., 100., 100.]
    assert out["component_summary"]["over_limit_count"] == 2
    assert out["local_summary"]["over_limit_count"] == 0
    assert out["pass"] is False
    assert data == before


def test_equivalent_quaternion_signs_and_nonunit_magnitudes_do_not_mutate_input():
    data = capture()
    for row in data["tables"]["candidate"]:
        for space in ("local", "component"):
            row[space]["quaternion_xyzw"] = [0., 0., 0., -7.]
    before = copy.deepcopy(data)
    report = COMPARE.compare_capture(data)
    assert report["pass"]
    assert report["component"][0]["metrics"]["rotation_deg"] == 0
    assert report["component"][0]["quaternion_delta_xyzw"] == [0., 0., 0., -1.]
    assert data == before


def test_wrong_axis_and_perbone_inconsistent_frames_remain_distinct():
    data = capture()
    s = math.sqrt(.5)
    data["tables"]["candidate"][0]["component"]["quaternion_xyzw"] = [s, 0., 0., s]
    data["tables"]["candidate"][1]["component"]["quaternion_xyzw"] = [0., s, 0., s]
    report = COMPARE.compare_capture(data)
    assert report["component_summary"]["over_limit_count"] == 2
    assert report["local_summary"]["over_limit_count"] == 0
    deltas = {r["name"]: r for r in report["component"]}
    assert deltas["root"]["quaternion_delta_xyzw"] != deltas["child"]["quaternion_delta_xyzw"]
    assert all(r["metrics"]["rotation_deg"] == pytest.approx(90) for r in deltas.values())
    assert report["pass"] is False


def test_quaternion_delta_has_got_times_reference_inverse_order():
    data = capture()
    s = math.sqrt(.5)
    data["tables"]["native"][0]["component"]["quaternion_xyzw"] = [s, 0., 0., s]
    data["tables"]["candidate"][0]["component"]["quaternion_xyzw"] = [0., s, 0., s]
    row = next(r for r in COMPARE.compare_capture(data)["component"] if r["name"] == "root")
    assert row["quaternion_delta_xyzw"] == pytest.approx([-.5, .5, .5, .5])
    assert row["metrics"]["rotation_deg"] == pytest.approx(120)


def test_right_relative_order_and_invariant_differences_are_derived():
    data = capture()
    s = math.sqrt(.5)
    data["tables"]["native"][0]["component"] = transform(q=(s, 0., 0., s), t=(3., 4., 0.))
    data["tables"]["candidate"][0]["component"] = transform(q=(0., s, 0., s), t=(0., 0., 7.))
    row = next(r for r in COMPARE.compare_capture(data)["component"] if r["name"] == "root")
    assert row["quaternion_delta_xyzw"] == pytest.approx([-.5, .5, .5, .5])
    assert row["quaternion_right_delta_xyzw"] == pytest.approx([-.5, .5, -.5, .5])
    assert row["rotation_angle_identity_delta_deg"] == pytest.approx(0.)
    assert row["translation_norm_delta_cm"] == 2.


def multiply(a, b):
    x, y, z, w = a; X, Y, Z, W = b
    return [w * X + x * W + y * Z - z * Y,
            w * Y - x * Z + y * W + z * X,
            w * Z + x * Y - y * X + z * W,
            w * W - x * X - y * Y - z * Z]


def inverse(q):
    return [-q[0], -q[1], -q[2], q[3]]


def rotation(axis, degrees):
    half = math.radians(degrees) / 2
    q = [0., 0., 0., math.cos(half)]; q[axis] = math.sin(half)
    return q


def rotate_vector(q, vector):
    return multiply(multiply(q, [*vector, 0.]), inverse(q))[:3]


@pytest.mark.parametrize("side", ["left", "right"])
def test_noncommuting_common_left_and_right_rotations_have_distinct_relative_deltas(side):
    data = capture()
    common = rotation(2, 45)
    originals = [rotation(0, 75), rotation(1, 40)]
    for index, q in enumerate(originals):
        data["tables"]["native"][index]["component"]["quaternion_xyzw"] = q
        got = multiply(common, q) if side == "left" else multiply(q, common)
        data["tables"]["candidate"][index]["component"]["quaternion_xyzw"] = got
    before = copy.deepcopy(data)
    report = COMPARE.compare_capture(data)
    assert data == before and not report["pass"]
    same = "quaternion_delta_xyzw" if side == "left" else "quaternion_right_delta_xyzw"
    varying = "quaternion_right_delta_xyzw" if side == "left" else "quaternion_delta_xyzw"
    assert report["component"][0][same] == pytest.approx(common)
    assert report["component"][1][same] == pytest.approx(common)
    assert report["component"][0][varying] != pytest.approx(report["component"][1][varying])


def test_common_basis_conjugation_preserves_angle_and_translation_norm_without_becoming_a_fix():
    data = capture()
    basis = rotation(2, 35)
    for index, q in enumerate((rotation(0, 75), rotation(1, 40))):
        t = [2. + index, 3., 4.]
        data["tables"]["native"][index]["component"] = transform(q=q, t=t)
        data["tables"]["candidate"][index]["component"] = transform(
            q=multiply(multiply(basis, q), inverse(basis)), t=rotate_vector(basis, t))
    report = COMPARE.compare_capture(data)
    first, second = report["component"]
    assert first["quaternion_delta_xyzw"] != pytest.approx(second["quaternion_delta_xyzw"])
    assert first["quaternion_right_delta_xyzw"] != pytest.approx(second["quaternion_right_delta_xyzw"])
    for row in report["component"]:
        assert row["rotation_angle_identity_delta_deg"] == pytest.approx(0., abs=1e-10)
        assert row["translation_norm_delta_cm"] == pytest.approx(0., abs=1e-10)
        assert row["over_limit"]
    assert report["component_summary"]["over_limit_count"] == 2 and not report["pass"]


def test_perbone_changed_rest_violates_conjugation_invariants():
    data = capture()
    data["tables"]["native"][0]["component"] = transform(q=rotation(0, 40), t=(3., 4., 0.))
    data["tables"]["candidate"][0]["component"] = transform(q=rotation(1, 60), t=(0., 0., 7.))
    report = COMPARE.compare_capture(data)
    row = next(r for r in report["component"] if r["name"] == "root")
    assert row["rotation_angle_identity_delta_deg"] == pytest.approx(20.)
    assert row["translation_norm_delta_cm"] == 2.
    assert report["component_summary"]["over_limit_count"] == 1 and not report["pass"]


def test_quaternion_sign_equivalence_is_preserved_for_both_relative_orders_and_angle_difference():
    data = capture()
    q = rotation(0, 75)
    for row in data["tables"]["native"]:
        row["component"]["quaternion_xyzw"] = q
    for row in data["tables"]["candidate"]:
        row["component"]["quaternion_xyzw"] = [-v for v in q]
    report = COMPARE.compare_capture(data)
    for row in report["component"]:
        assert row["quaternion_delta_xyzw"] == pytest.approx([0., 0., 0., -1.])
        assert row["quaternion_right_delta_xyzw"] == pytest.approx([0., 0., 0., -1.])
        assert row["rotation_angle_identity_delta_deg"] == pytest.approx(0.)
    assert report["pass"]


def test_new_norm_diagnostic_does_not_refuse_equal_finite_large_translations():
    data = capture()
    for row in data["tables"]["native"] + data["tables"]["candidate"]:
        row["component"]["translation_cm"] = [1.7e308, 1.7e308, 1.7e308]
    report = COMPARE.compare_capture(data)
    assert report["pass"]
    assert all(row["translation_norm_delta_cm"] == 0. for row in report["component"])


def test_signed_translation_scale_deltas_and_zero_reference_ratio():
    data = capture()
    data["tables"]["native"][0]["component"] = transform(scale=(-2., 0., 3.), t=(2., -3., 5.))
    data["tables"]["candidate"][0]["component"] = transform(scale=(4., -1., -6.), t=(-1., 2., 4.))
    row = next(r for r in COMPARE.compare_capture(data)["component"] if r["name"] == "root")
    assert row["translation_delta_cm"] == [-3., 5., -1.]
    assert row["scale_delta"] == [6., -1., -9.]
    assert row["scale_ratio"] == [-2., None, -2.]
    assert row["metrics"]["position_cm"] == pytest.approx(math.sqrt(35))
    assert row["metrics"]["scale"] == 9.


def test_current_bars_are_unrounded_and_never_relative_scale_limits():
    data = capture()
    row = data["tables"]["candidate"][0]
    row["component"]["translation_cm"][0] = .01
    report = COMPARE.compare_capture(data)
    assert report["bars"] == {"position_cm": .01, "rotation_deg": .01, "scale": .0001}
    assert report["pass"]
    row["component"]["translation_cm"][0] = math.nextafter(.01, math.inf)
    assert not COMPARE.compare_capture(data)["pass"]
    row["component"]["translation_cm"][0] = 0.
    data["tables"]["native"][0]["component"]["scale_xyz"] = [100., 100., 100.]
    row["component"]["scale_xyz"] = [100.0002, 100., 100.]
    assert not COMPARE.compare_capture(data)["pass"]


def test_missing_bones_do_not_disappear_from_diagnostics():
    data = capture()
    data["tables"]["candidate"].pop()
    report = COMPARE.compare_capture(data)
    assert report["missing"] == ["child"]
    assert report["counts"]["compared"] == 1 and not report["pass"]


@pytest.mark.parametrize("bad", ["nonfinite", "zero_quaternion", "cycle", "duplicate", "missing_parent", "boolean_vector", "wrong_units", "wrong_order", "wrong_space", "unknown_input", "bad_hash", "owner_path"])
def test_invalid_capture_controls_refuse(bad):
    data = capture()
    candidate = data["tables"]["candidate"]
    if bad == "nonfinite":
        candidate[0]["local"]["scale_xyz"][0] = float("nan")
    elif bad == "zero_quaternion":
        candidate[0]["local"]["quaternion_xyzw"] = [0., 0., 0., 0.]
    elif bad == "cycle":
        candidate[0]["parent"] = "child"
    elif bad == "duplicate":
        candidate.append(copy.deepcopy(candidate[0]))
    elif bad == "missing_parent":
        candidate[0]["parent"] = "unrecorded"
    elif bad == "boolean_vector":
        candidate[0]["component"]["translation_cm"][0] = True
    elif bad == "wrong_units":
        data["conventions"]["translation_unit"] = "m"
    elif bad == "wrong_order":
        data["conventions"]["quaternion_order"] = "wxyz"
    elif bad == "wrong_space":
        data["conventions"]["spaces"]["component"] = "world"
    elif bad == "unknown_input":
        data["geometry"] = {"verts": []}
    elif bad == "bad_hash":
        data["provenance"]["native_reference_sha256"] = "not-a-fingerprint"
    else:
        candidate[0]["name"] = "/private-owner-path"
    with pytest.raises(ValueError):
        COMPARE.compare_capture(data)


def test_independent_native_identity_required_except_explicit_self_control():
    data = capture()
    data["provenance"]["native_reference_sha256"] = data["provenance"]["candidate_fbx_sha256"]
    with pytest.raises(ValueError):
        COMPARE.compare_capture(data)
    data["native_self_control"] = True
    assert COMPARE.compare_capture(data)["pass"]
    data["native_self_control"] = "true"
    with pytest.raises(ValueError):
        COMPARE.compare_capture(data)


def test_provenance_prose_and_absolute_transforms_are_not_copied_to_output():
    data = capture()
    data["provenance"]["engine"] = "engine /private-owner-path"
    data["provenance"]["comparator_description"] = "code /private-owner-path"
    for row in data["tables"]["native"] + data["tables"]["candidate"]:
        row["component"]["translation_cm"] = [12345., 23456., 34567.]
    report = COMPARE.compare_capture(data)
    payload = json.dumps(report)
    assert "private-owner-path" not in payload
    assert "12345" not in payload and "23456" not in payload and "34567" not in payload
    assert "translation_cm" not in report["component"][0]
    assert "quaternion_xyzw" not in report["component"][0]
    assert "scale_xyz" not in report["component"][0]


@pytest.mark.parametrize("settings", [{"owner_path": "/private"}, {"import_method": "/private"}, {"offset_uniform_scale": float("inf")}, {"convert_scene": "True"}, {"skeleton_selection": "private_asset"}])
def test_unsafe_or_untyped_importer_metadata_refuses(settings):
    data = capture(); data["importer_settings"] = settings
    with pytest.raises(ValueError):
        COMPARE.compare_capture(data)


def test_safe_importer_scalars_are_retained():
    data = capture()
    data["importer_settings"] = {"convert_scene": True, "offset_uniform_scale": 1., "import_method": "interchange", "skeleton_selection": "new_transient"}
    assert COMPARE.compare_capture(data)["importer_settings"] == data["importer_settings"]


def test_standalone_cli_writes_only_derived_private_output_and_summary(tmp_path):
    source = tmp_path / "owner_capture.json"; out = tmp_path / "owner_comparison.json"
    source.write_text(json.dumps(capture()))
    before = source.read_bytes()
    run = subprocess.run([sys.executable, "-I", COMPARE.__file__, "--capture", str(source), "--out", str(out)], capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    assert source.read_bytes() == before
    assert out.stat().st_mode & 0o777 == 0o600
    summary = json.loads(run.stdout)
    assert set(summary) == {"capture_sha256", "counts"}
    assert summary["capture_sha256"] == hashlib.sha256(before).hexdigest()
    assert all(value not in run.stdout + run.stderr for value in ("owner_capture", "root", "child", str(tmp_path)))
    report = json.loads(out.read_text())
    assert report["pass"] and report["capture_sha256"] == summary["capture_sha256"]
    assert not list(tmp_path.glob(".ue-bind-*"))


def test_atomic_exclusive_output_refuses_existing_files_and_symlinks(tmp_path):
    target = tmp_path / "output.json"
    COMPARE.write_atomic_exclusive(target, {"original": True})
    before = target.read_bytes()
    with pytest.raises(FileExistsError):
        COMPARE.write_atomic_exclusive(target, {"replacement": True})
    link = tmp_path / "link.json"; link.symlink_to(target)
    with pytest.raises(FileExistsError):
        COMPARE.write_atomic_exclusive(link, {"replacement": True})
    assert target.read_bytes() == before and not list(tmp_path.glob(".ue-bind-*"))
    nan = tmp_path / "nan.json"
    with pytest.raises(ValueError):
        COMPARE.write_atomic_exclusive(nan, {"nan": float("nan")})
    assert not nan.exists() and not list(tmp_path.glob(".ue-bind-*"))


@pytest.mark.parametrize("operation", ["link", "fsync"])
def test_failed_atomic_write_cleans_own_temporary_only(tmp_path, monkeypatch, operation):
    target = tmp_path / "output.json"
    sentinel = tmp_path / "sentinel.json"; sentinel.write_bytes(b"keep")
    def fail(*args):
        raise OSError("private-owner-path")
    monkeypatch.setattr(COMPARE.os, operation, fail)
    with pytest.raises(OSError):
        COMPARE.write_atomic_exclusive(target, {"a": 1})
    assert not target.exists() and sentinel.read_bytes() == b"keep"
    assert not list(tmp_path.glob(".ue-bind-*"))


def test_capture_change_during_comparison_refuses(tmp_path, monkeypatch):
    source = tmp_path / "capture.json"; source.write_text(json.dumps(capture()))
    original = COMPARE.compare_capture
    def changing(data):
        report = original(data)
        source.write_bytes(b"changed")
        return report
    monkeypatch.setattr(COMPARE, "compare_capture", changing)
    with pytest.raises(ValueError, match="source capture changed"):
        COMPARE.compare_file(source)


@pytest.mark.parametrize("bad", ["missing", "malformed", "duplicate_json", "same_output"])
def test_cli_errors_do_not_echo_owner_names_paths_or_input(tmp_path, capsys, bad):
    source = tmp_path / "private-owner-capture.json"; target = tmp_path / "private-owner-output.json"
    if bad == "malformed":
        source.write_text("private-owner-payload")
    elif bad == "duplicate_json":
        source.write_text('{"private-owner-field":1,"private-owner-field":2}')
    elif bad == "same_output":
        source.write_text(json.dumps(capture())); target = source
    before = source.read_bytes() if source.exists() else None
    assert COMPARE.main(["--capture", str(source), "--out", str(target)]) == 1
    log = capsys.readouterr()
    assert "private-owner" not in log.out + log.err and str(tmp_path) not in log.out + log.err
    if before is not None:
        assert source.read_bytes() == before
    if target != source:
        assert not target.exists()
    assert not list(tmp_path.glob(".ue-bind-*"))


def test_unknown_cli_flags_are_sanitized(capsys):
    with pytest.raises(SystemExit) as error:
        COMPARE.main(["--private-owner-value", "/private-owner-path"])
    assert error.value.code == 2
    log = capsys.readouterr()
    assert "private-owner" not in log.out + log.err
