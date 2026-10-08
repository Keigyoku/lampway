# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Verification distinguishes recorded reproduction from current artifact and source identity."""
from pathlib import Path
import json
import errno

import pytest

from lampway_server import motion as M
from .fake_motion import FakeCapture
from .test_motion_graphics import SMALL, put_scene


def rendered(root, formats=("mp4",)):
    scene = put_scene(root, "integrity", "<!doctype html>")
    out = M.render(root, {"scene": scene, **SMALL, "formats": list(formats)}, FakeCapture)
    return out, {"receipt": out["out_dir"] + "/receipt.json"}


def test_intact_artifacts_report_independent_integrity_and_provenance(tmp_path):
    out, args = rendered(tmp_path, ("mp4", "webm"))
    result = M.verify(tmp_path, args, FakeCapture)
    assert result["reproduced"]
    assert result.get("integrity_matches") is True
    assert result.get("provenance_matches") is True
    assert set(result["integrity"]) == {"mp4", "webm"}
    assert all(item["matches"] for item in result["integrity"].values())
    assert all(item["matches"] for item in result["provenance"].values())
    assert (tmp_path / out["files"]["mp4"]).exists()


@pytest.mark.parametrize("fmt", ["mp4", "webm"])
@pytest.mark.parametrize("change", ["missing", "corrupt"])
def test_original_media_damage_does_not_masquerade_as_artifact_integrity(tmp_path, fmt, change):
    out, args = rendered(tmp_path, (fmt,))
    video = tmp_path / out["files"][fmt]
    if change == "missing":
        video.unlink()
    else:
        video.write_bytes(b"synthetic corrupt video")
    result = M.verify(tmp_path, args, FakeCapture)
    assert result["reproduced"] and result[fmt + "_equal"], "retain recorded reproduction semantics"
    assert result.get("integrity_matches") is False
    assert result["integrity"][fmt]["matches"] is False
    assert result["provenance_matches"] is True
    if change == "corrupt":
        assert video.read_bytes() == b"synthetic corrupt video", "verification preserves evidence"


@pytest.mark.parametrize("replacement", ["same_bytes", "corrupt", "outside_symlink"])
def test_original_video_replacement_during_rerender_is_detected(tmp_path, monkeypatch, replacement):
    root = tmp_path / "project"
    out, args = rendered(root)
    video = root / out["files"]["mp4"]
    expected = video.read_bytes()
    outside = tmp_path / "outside.mp4"
    outside.write_bytes(expected)
    original = M.E.Encoder
    def swap(*a, **kw):
        saved = video.with_suffix(".original.mp4")
        video.rename(saved)
        if replacement == "outside_symlink":
            video.symlink_to(outside)
        else:
            video.write_bytes(expected if replacement == "same_bytes" else b"replacement")
        return original(*a, **kw)
    monkeypatch.setattr(M.E, "Encoder", swap)
    result = M.verify(root, args, FakeCapture)
    assert result["reproduced"]
    assert result.get("integrity_matches") is False
    assert result["integrity"]["mp4"]["replaced"] is True
    assert video.with_suffix(".original.mp4").read_bytes() == expected
    assert outside.read_bytes() == expected


@pytest.mark.parametrize("changed", ["source", "driver", "flags"])
def test_provenance_difference_is_reported_separately_from_pixel_reproduction(tmp_path, monkeypatch, changed):
    out, args = rendered(tmp_path)
    capture = FakeCapture
    if changed == "source":
        (tmp_path / "motion/scenes/integrity/index.html").write_text("<!doctype html><!-- source edit -->")
    elif changed == "driver":
        original = M.F.sha256_file
        def different_driver(path, **kwargs):
            return "0" * 64 if Path(path) == Path(M.F.__file__) else original(path, **kwargs)
        monkeypatch.setattr(M.F, "sha256_file", different_driver)
    else:
        class DifferentFlags(FakeCapture):
            flags = [*FakeCapture.flags, "--synthetic-different-flag"]
        capture = DifferentFlags
    result = M.verify(tmp_path, args, capture)
    assert result["reproduced"] and result["integrity_matches"]
    assert result.get("provenance_matches") is False
    assert result["provenance"][changed]["matches"] is False
    assert all(item["matches"] for key, item in result["provenance"].items() if key != changed)


def test_engine_mismatch_still_reports_original_artifact_and_provenance_checks(tmp_path):
    _, args = rendered(tmp_path)
    class DifferentEngine(FakeCapture):
        product = "FakeChrome/2.0"
    result = M.verify(tmp_path, args, DifferentEngine)
    assert result["engine_matches"] is False and result["reproduced"] is False
    assert result.get("integrity_matches") is True
    assert result.get("provenance_matches") is False
    assert result["frames_differing"] == []


@pytest.mark.parametrize("field,value", [
    ("inputs", []), ("engine", []), ("outputs", []), ("files", []),
    ("scene_files", {}), ("code_sha256", "invalid"), ("frames", True),
    ("frames_sha256_digest", "invalid"),
])
def test_malformed_receipt_is_correctively_refused_before_rerender(tmp_path, monkeypatch, field, value):
    _, args = rendered(tmp_path)
    path = tmp_path / args["receipt"]
    receipt = json.loads(path.read_text())
    receipt[field] = value
    path.write_text(json.dumps(receipt))
    def must_not_render(*a, **kw):
        raise AssertionError("invalid receipt reached renderer")
    monkeypatch.setattr(M, "_run", must_not_render)
    with pytest.raises(M.Refused, match="receipt"):
        M.verify(tmp_path, args, FakeCapture)


@pytest.mark.parametrize("kind", ["malformed_row", "changed_digest", "wrong_inventory"])
def test_receipt_frame_and_source_inventory_must_be_internally_consistent(tmp_path, monkeypatch, kind):
    out, args = rendered(tmp_path)
    path = tmp_path / args["receipt"]
    receipt = json.loads(path.read_text())
    frames = tmp_path / out["out_dir"] / "frames.sha256"
    if kind == "malformed_row":
        frames.write_text("bad frame row\n")
    elif kind == "changed_digest":
        receipt["frames_sha256_digest"] = "0" * 64
    else:
        receipt["scene_files"][0]["sha256"] = "0" * 64
    path.write_text(json.dumps(receipt))
    def must_not_render(*a, **kw):
        raise AssertionError("invalid inventory reached renderer")
    monkeypatch.setattr(M, "_run", must_not_render)
    with pytest.raises(M.Refused, match="receipt"):
        M.verify(tmp_path, args, FakeCapture)


@pytest.mark.parametrize("fields,value", [
    (("inputs", "duration_s"), None), (("inputs", "entry"), None),
    (("engine", "encoder", "threads"), True), (("engine", "chrome_flags"), {}),
    (("outputs", "mp4", "sha256"), "invalid"), (("outputs", "mp4", "bytes"), True),
])
def test_malformed_nested_receipt_fields_are_correctively_refused(tmp_path, monkeypatch, fields, value):
    _, args = rendered(tmp_path)
    path = tmp_path / args["receipt"]
    receipt = json.loads(path.read_text())
    container = receipt
    for field in fields[:-1]:
        container = container[field]
    container[fields[-1]] = value
    path.write_text(json.dumps(receipt))
    monkeypatch.setattr(M, "_run", lambda *a, **kw: pytest.fail("invalid receipt reached renderer"))
    with pytest.raises(M.Refused, match="receipt"):
        M.verify(tmp_path, args, FakeCapture)


def test_integrity_check_does_not_convert_resource_failure_into_a_normal_result(tmp_path, monkeypatch):
    out, args = rendered(tmp_path)
    video = tmp_path / out["files"]["mp4"]
    original = M.F._open_scene_file
    def exhausted(path, root):
        if Path(path) == video:
            raise OSError(errno.EMFILE, "synthetic descriptor exhaustion")
        return original(path, root)
    monkeypatch.setattr(M.F, "_open_scene_file", exhausted)
    with pytest.raises(OSError) as caught:
        M.verify(tmp_path, args, FakeCapture)
    assert caught.value.errno == errno.EMFILE
