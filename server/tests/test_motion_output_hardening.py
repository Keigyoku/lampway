# SPDX-FileCopyrightText: 2026 Lampway contributors
# SPDX-License-Identifier: GPL-3.0-or-later
"""Review falsifiers for immutable, jailed motion output and input refusals."""
import pytest

from lampway_server import motion as M
from .fake_motion import FakeCapture
from .test_motion_graphics import put_scene, SMALL


def test_explicit_empty_formats_is_refused():
    with pytest.raises(M.Refused, match="non-empty subset"):
        M.inputs({"scene": "scene", "formats": []})


def test_each_render_preserves_earlier_receipt_and_media(tmp_path):
    scene = put_scene(tmp_path, "repeat", "<!doctype html>")
    args = {"scene": scene, **SMALL, "formats": ["mp4"]}
    first = M.render(tmp_path, args, FakeCapture)
    directory = tmp_path / first["out_dir"]
    original = {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()}
    second = M.render(tmp_path, dict(args, fps=5), FakeCapture)
    third = M.render(tmp_path, args, FakeCapture)
    assert len({first["out_dir"], second["out_dir"], third["out_dir"]}) == 3
    assert {p.name: p.read_bytes() for p in directory.iterdir() if p.is_file()} == original
    assert M.verify(tmp_path, {"receipt": str(directory.relative_to(tmp_path) / "receipt.json")}, FakeCapture)["reproduced"]


@pytest.mark.parametrize("component", ["motion", "motion/out"])
def test_output_parent_symlink_cannot_escape_project(tmp_path, component):
    root = tmp_path / "project"
    root.mkdir()
    scene = "scene"
    (root / scene).mkdir()
    (root / scene / "index.html").write_text("<!doctype html>")
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.txt"
    sentinel.write_text("keep")
    target = root / component
    target.parent.mkdir(parents=True, exist_ok=True)
    target.symlink_to(outside, target_is_directory=True)
    with pytest.raises(M.Refused, match="outside|symlink"):
        M.render(root, {"scene": scene, **SMALL, "formats": ["mp4"]}, FakeCapture)
    assert list(outside.iterdir()) == [sentinel]
    assert sentinel.read_text() == "keep"


def test_inline_scene_cannot_overwrite_external_entry_symlink(tmp_path):
    outside = tmp_path / "outside.html"
    outside.write_text("keep")
    root = tmp_path / "project"
    directory = root / "motion/scenes/inline"
    directory.mkdir(parents=True)
    (directory / "index.html").symlink_to(outside)
    before = outside.stat().st_mtime_ns
    with pytest.raises(M.Refused):
        M.render(root, {"html": "keep", "name": "inline", **SMALL}, FakeCapture)
    assert outside.stat().st_mtime_ns == before, "refusal must precede writing through the symlink"
    assert outside.read_text() == "keep"


def test_probe_only_network_request_fails_render(tmp_path):
    made = []
    def fresh():
        cap = FakeCapture(requests=() if not made else ["https://example.invalid/probe"])
        made.append(cap)
        return cap
    scene = put_scene(tmp_path, "probe-egress", "<!doctype html>")
    result = M.render(tmp_path, {"scene": scene, **SMALL, "formats": ["mp4"]}, fresh)
    assert not result["ok"]
    assert result["network"]["non_file"] == ["https://example.invalid/probe"]


def test_untrusted_capture_outside_file_request_cannot_pass_network_gate(tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("synthetic")
    scene = put_scene(tmp_path, "file-egress", "<!doctype html>")
    result = M.render(tmp_path, {"scene": scene, **SMALL, "formats": ["mp4"]},
                      lambda: FakeCapture(requests=[outside.as_uri()]))
    assert not result["ok"]
    assert result["network"]["non_file"] == [outside.as_uri()]


def test_missing_audit_refused_before_output_creation(tmp_path):
    class MissingAudit(FakeCapture):
        def has_audit(self):
            return False
    scene = put_scene(tmp_path, "no-audit", "<!doctype html>")
    with pytest.raises(M.Refused, match="__audit"):
        M.render(tmp_path, {"scene": scene, **SMALL}, MissingAudit)
    assert not (tmp_path / "motion/out").exists()


def test_output_parent_swap_cannot_write_outside_project(tmp_path, monkeypatch):
    root, outside = tmp_path / "project", tmp_path / "outside"
    outside.mkdir()
    scene = put_scene(root, "raced", "<!doctype html>")
    original = M.tempfile.mkdtemp
    def swap(*args, **kwargs):
        parent = root / "motion/out"
        parent.rmdir()
        parent.symlink_to(outside, target_is_directory=True)
        return original(*args, **kwargs)
    monkeypatch.setattr(M.tempfile, "mkdtemp", swap)
    with pytest.raises(M.Refused, match="outside|symlink|changed"):
        M.render(root, {"scene": scene, **SMALL, "formats": ["mp4"]}, FakeCapture)
    assert not list(outside.rglob("*"))


def test_verify_refuses_receipt_frame_path_outside_project(tmp_path):
    import json
    root, outside = tmp_path / "project", tmp_path / "outside"
    outside.mkdir()
    scene = put_scene(root, "verify-jail", "<!doctype html>")
    result = M.render(root, {"scene": scene, **SMALL, "formats": ["mp4"]}, FakeCapture)
    directory = root / result["out_dir"]
    (outside / "frames.sha256").write_bytes((directory / "frames.sha256").read_bytes())
    receipt_path = directory / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    receipt["out_dir"] = str(outside)
    receipt_path.write_text(json.dumps(receipt))
    with pytest.raises(M.Refused, match="outside"):
        M.verify(root, {"receipt": str(receipt_path.relative_to(root))}, FakeCapture)


def test_verify_detects_frame_file_swapped_during_rerender(tmp_path, monkeypatch):
    root, outside = tmp_path / "project", tmp_path / "outside"
    outside.mkdir()
    scene = put_scene(root, "verify-race", "<!doctype html>")
    result = M.render(root, {"scene": scene, **SMALL, "formats": ["mp4"]}, FakeCapture)
    frames = root / result["out_dir"] / "frames.sha256"
    external = outside / "frames.sha256"
    external.write_bytes(frames.read_bytes())
    original = M.E.Encoder
    def swap(*args, **kwargs):
        frames.unlink()
        frames.symlink_to(external)
        return original(*args, **kwargs)
    monkeypatch.setattr(M.E, "Encoder", swap)
    with pytest.raises(M.Refused, match="outside"):
        M.verify(root, {"receipt": result["out_dir"] + "/receipt.json"}, FakeCapture)


def test_setup_can_install_required_audit_before_output_creation(tmp_path):
    class SetupAudit(FakeCapture):
        ready = False
        def has_audit(self):
            return self.ready
        def setup(self):
            self.ready = True
            return super().setup()
    scene = put_scene(tmp_path, "setup-audit", "<!doctype html>")
    result = M.render(tmp_path, {"scene": scene, **SMALL, "formats": ["mp4"]}, SetupAudit)
    assert result["ok"]
