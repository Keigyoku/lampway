# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Rest-frame diagnostics classify matrices without correcting their values."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

SPEC = importlib.util.spec_from_file_location("native_frame_diagnostics", Path(__file__).parents[2] / "scripts/lampway/read_native_frame_diagnostics.py")
DIAG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DIAG)


@pytest.mark.parametrize("matrix,proper", [
    (np.eye(3), True), (np.diag([-1, 1, 1]), False),
    ([[1, .01, 0], [0, 1, 0], [0, 0, 1]], False),
])
def test_rotation_reflection_and_material_shear(matrix, proper):
    original = np.asarray(matrix, dtype=float)
    before = original.copy()
    result = DIAG.matrix_metrics(original)
    assert result["proper_rotation"] is proper
    assert np.array_equal(original, before)
    assert np.array_equal(np.array(result["matrix"]), before)


def test_float32_rotation_is_retained_and_decimal_quantization_is_visible():
    # Float32 representation of this proper axis-angle rotation passes; six
    # decimal serialization exceeds the unchanged strict orthogonality bar.
    rng = np.random.default_rng(1729)
    for _ in range(1000):
        q, _ = np.linalg.qr(rng.normal(size=(3, 3)))
        q[:, 0] *= np.linalg.det(q)
        raw = q.astype(np.float32).astype(float)
        variants = DIAG.frame_variants(raw)
        if not variants["round6"]["proper_rotation"]:
            break
    assert variants["normalized"]["proper_rotation"]
    assert variants["round12"]["proper_rotation"]
    assert not variants["round6"]["proper_rotation"]
    assert np.array_equal(variants["raw"]["matrix"], raw)


@pytest.mark.parametrize("matrix", [np.zeros((3, 3)), np.full((3, 3), np.nan), np.eye(4)])
def test_invalid_frames_refuse(matrix):
    with pytest.raises(ValueError):
        DIAG.frame_variants(matrix)


def test_receipt_is_strict_exclusive_and_private(tmp_path):
    path = tmp_path / "frames.json"
    DIAG.write_exclusive(path, {"schema": DIAG.SCHEMA, "read_only": True})
    before = path.read_bytes()
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        DIAG.write_exclusive(path, {"replacement": True})
    assert path.read_bytes() == before
    with pytest.raises(ValueError):
        DIAG.write_exclusive(tmp_path / "nan.json", {"value": float("nan")})
    assert not (tmp_path / "nan.json").exists()


def test_convention_capture_retains_axis_evidence_and_strict_outliers():
    # Synthetic geometric stand-in for the reported 103.97325-degree outlier;
    # this is not a replay of private original bone measurements.
    import sys
    sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts"))
    from mixar.modules.lampway_tools.rig_tools import core as rc
    angle = 103.97325
    frame = rc.rot("z", angle - 90)
    rig = {"names": ["joint", "child", "helper"],
           "heads": {"joint": [0, 0, 0], "child": [1, 0, 0], "helper": [0, 1, 0]},
           "frames": {"joint": frame, "child": np.eye(3), "helper": np.eye(3)},
           "parents": {"joint": None, "child": "joint", "helper": None}}
    before = frame.copy()
    rt = SimpleNamespace(RC=rc, convention_angles=lambda _: {"joint": angle},
                         _single_child=lambda _: {"joint": "child"})
    got = getattr(DIAG, "convention_diagnostics", lambda *_: {})(rt, rig)
    assert got.get("class") == "mixed", "private capture lacks convention evidence"
    assert got["tolerance_deg"] == 10
    assert got["outside_ue_y_bar"] == ["joint"]
    assert got["outside_blender_y_bar"] == ["joint"]
    row = got["rows"][0]
    assert row["bone"] == "joint" and row["child"] == "child"
    assert row["angles_deg"]["y"] == pytest.approx(angle)
    assert row["angles_deg"]["x"] == pytest.approx(angle-90)
    assert row["angles_deg"]["z"] == pytest.approx(90)
    assert got["unsampled"] == ["child", "helper"]
    assert np.array_equal(before, frame)


def test_convention_capture_uses_loaded_classifier_and_sampling():
    rt = SimpleNamespace(RC=SimpleNamespace(classify_convention=lambda _: "unknown"),
                         convention_angles=lambda _: {}, _single_child=lambda _: {})
    got = getattr(DIAG, "convention_diagnostics", lambda *_: {})(rt, {"names": ["root"]})
    assert got.get("class") == "unknown", "private capture lacks classifier identity"
    assert got["rows"] == []
    assert got["unsampled"] == ["root"]
